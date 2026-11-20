"""扩测排班持久化服务：草案不占额度，确认整单占用，可中断恢复且不重复占用。"""
import time
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from src.models import (
    Roadway, ShiftQuota, SchedulePlan, ScheduleClosure, Job, Dataset,
)
from src.services import scheduling
from src.services.audit import record

PLAN_STATUSES = ('draft', 'confirming', 'confirmed')
DEFAULT_THRESHOLD = 8.0


# ---------- 登记数据 ----------
def list_roadways(db):
    return list(db.scalars(select(Roadway).order_by(Roadway.code)))


def list_quotas(db):
    return list(db.scalars(select(ShiftQuota).order_by(ShiftQuota.id)))


def register_roadway(db, data):
    code = data.code.strip()
    if not code:
        raise HTTPException(422, '巷道编号不能为空')
    teams = sorted(set((t.strip() for t in (data.teams or []) if t.strip())))
    if not teams:
        raise HTTPException(422, '至少登记一个必经小组')
    if db.scalar(select(Roadway).where(Roadway.code == code)):
        raise HTTPException(409, '巷道编号已存在，请使用其他编号')
    rw = Roadway(code=code, name=data.name.strip() or code, teams=teams, created_at=time.time())
    db.add(rw)
    db.flush()
    return rw


def upsert_quota(db, data):
    shift = data.shift.strip()
    if not shift:
        raise HTTPException(422, '班次名称不能为空')
    if data.closure_limit < 0:
        raise HTTPException(422, '封道上限不能为负')
    q = db.scalar(select(ShiftQuota).where(ShiftQuota.shift == shift))
    if q:
        q.closure_limit = data.closure_limit
        q.updated_at = time.time()
    else:
        q = ShiftQuota(shift=shift, closure_limit=data.closure_limit, updated_at=time.time())
        db.add(q)
        db.flush()
    return q


# ---------- 选包依据数据装配 ----------
def _team_catalog(db):
    """汇总每个小组的最新已批准复测任务、作业员人数。"""
    jobs = list(db.scalars(select(Job).where(Job.status == 'completed')))
    job_by_team = {}
    for j in jobs:
        team = (j.params or {}).get('team')
        if not team or team == '全部':
            continue
        lower = (j.result or {}).get('ci_lower')
        cand = {'id': j.id, 'approved': bool(j.approved), 'ci_lower': lower if j.approved else None, 'name': j.name}
        prev = job_by_team.get(team)
        # 已批准结果优先；同状态取最新任务
        if prev is None or (cand['approved'] and not prev['approved']) or \
                (cand['approved'] == prev['approved'] and j.id > prev['id']):
            job_by_team[team] = cand
    # 完全没有完成任务的小组保持缺省；有未批准任务则保留 approved=False 供页面区分
    # 人数来自数据批次（以最新批次为准）
    team_operators = {}
    for d in db.scalars(select(Dataset)):
        counts = {}
        for row in d.records:
            t = row.get('team')
            if t:
                counts[t] = counts.get(t, 0) + 1
        for t, n in counts.items():
            team_operators[t] = n
    return job_by_team, team_operators


def build_draft(db, shift_id, threshold):
    q = db.get(ShiftQuota, shift_id)
    if not q:
        raise HTTPException(404, '班次封道额度不存在')
    if threshold is None:
        threshold = DEFAULT_THRESHOLD
    if threshold < 0:
        raise HTTPException(422, '改善门槛不能为负')
    roadways = [
        {'id': rw.id, 'code': rw.code, 'name': rw.name, 'teams': rw.teams}
        for rw in list_roadways(db)
    ]
    if not roadways:
        raise HTTPException(422, '尚未登记任何必经巷道，无法排班')
    job_by_team, team_operators = _team_catalog(db)
    result = scheduling.plan_schedule(
        roadways, q.closure_limit, job_by_team, team_operators, float(threshold))
    result['shift'] = {'id': q.id, 'shift': q.shift, 'closure_limit': q.closure_limit}
    return q, result


def create_plan(db, data, user):
    q, result = build_draft(db, data.shift_id, data.threshold)
    plan = SchedulePlan(
        name=data.name.strip(), shift_id=q.id, threshold=float(result['threshold']),
        status='draft', snapshot=result, created_by=user.id, created_at=time.time())
    db.add(plan)
    db.flush()
    record(db, user.email, 'schedule.draft', {
        'id': plan.id, 'shift': q.shift,
        'covered': result['operators_covered'], 'used': result['closures_used']})
    return plan


def list_plans(db):
    return list(db.scalars(select(SchedulePlan).order_by(SchedulePlan.id.desc()).limit(100)))


def get_plan(db, plan_id):
    plan = db.get(SchedulePlan, plan_id)
    if not plan:
        raise HTTPException(404, '排班单不存在')
    return plan


def confirm_plan(db, plan_id, user):
    """整单占用封道额度。行锁 + 唯一约束保证并发与重试不重复占用。

    - draft：锁班次与相关巷道行，校验额度，写入占用并置 confirmed。
    - confirming（上次中断）：复用本单已写入的占用，补齐缺失后确认，不重复占额。
    - confirmed：幂等直接返回。
    """
    # 独立事务内加锁，避免两个确认请求同时读到同一剩余额度
    plan = db.get(SchedulePlan, plan_id)
    if not plan:
        raise HTTPException(404, '排班单不存在')
    if plan.status == 'confirmed':
        return plan, 'already_confirmed'

    shift = db.get(ShiftQuota, plan.shift_id)
    if not shift:
        raise HTTPException(409, '班次额度登记已缺失，无法确认')
    plan.status = 'confirming'
    db.flush()

    selected = plan.snapshot.get('selected', [])
    # 巷道 id -> 实际途经它的小组与作业员人数（同巷道组同进同退，人数为组内合计）
    roadway_info = {}
    rw_jobs = {}
    for cluster in selected:
        for tr in cluster['team_results']:
            rw_jobs[tr['team']] = tr.get('job_id')
        for rw in cluster['roadways']:
            roadway_info.setdefault(rw['id'], {
                'teams': list(cluster['teams']), 'operators': cluster['operators']})
    wanted = []  # (roadway_id, team, job_id, operators)
    for roadway_id, info in sorted(roadway_info.items()):
        team = sorted(info['teams'])[0]
        wanted.append((roadway_id, team, rw_jobs.get(team), info['operators']))

    # 锁定本班次已有占用与目标巷道行（MySQL 行锁随事务持有到 commit）
    existing = list(db.scalars(
        select(ScheduleClosure).where(ScheduleClosure.shift_id == shift.id).with_for_update()))
    occupied_roadway_ids = {c.roadway_id for c in existing}
    own_ids = {c.roadway_id for c in existing if c.plan_id == plan.id}
    # 其他排班单已占用且本单也需要的巷道 → 额度冲突，需按剩余额度重排
    conflicts = occupied_roadway_ids - own_ids
    wanted_ids = {w[0] for w in wanted}
    blocked = sorted(conflicts & wanted_ids)
    if blocked:
        db.rollback()
        raise HTTPException(409, {
            'message': '封道额度已被其他排班单占用，请按剩余额度重排后再确认',
            'code': 'quota_conflict',
            'blocked_roadway_ids': blocked,
        })

    # 重新核算剩余额度（含其他单据的占用）
    other_used = len(occupied_roadway_ids - own_ids)
    remaining = shift.closure_limit - other_used
    need = len(wanted_ids - own_ids)
    if need > remaining:
        db.rollback()
        raise HTTPException(409, {
            'message': '剩余封道额度 %d 条不足本单新增 %d 条，请重排' % (remaining, need),
            'code': 'quota_exceeded',
            'remaining': remaining, 'need': need,
        })

    # 幂等写入：已存在的本单占用跳过，中断恢复时只补齐缺失部分
    for roadway_id, team, job_id, operators in wanted:
        if roadway_id in own_ids:
            continue
        closure = ScheduleClosure(
            plan_id=plan.id, shift_id=shift.id, roadway_id=roadway_id,
            team=team, job_id=job_id, operators=operators, created_at=time.time())
        db.add(closure)
        try:
            db.flush()
        except IntegrityError:
            # 并发下唯一约束兜底：他单抢先占用，回滚并要求重排
            db.rollback()
            raise HTTPException(409, {
                'message': '并发确认导致巷道占用冲突，请按剩余额度重排',
                'code': 'quota_conflict',
            })
    plan.status = 'confirmed'
    plan.confirmed_at = time.time()
    record(db, user.email, 'schedule.confirm', {
        'id': plan.id, 'closures': len(wanted_ids), 'shift': shift.shift})
    db.commit()
    return plan, 'confirmed'


def recompute_plan(db, plan_id, user):
    """额度冲突后按当前剩余额度重排，生成新的草案快照供再次确认（不占额度）。

    重排同时排除其他排班单已占用的巷道，使新草案可直接确认而不再撞单。
    """
    old = get_plan(db, plan_id)
    shift = db.get(ShiftQuota, old.shift_id)
    if not shift:
        raise HTTPException(404, '班次额度登记不存在')
    # 本班次当前已占用的巷道（含原单自身——重排产出的是新单，不能重复占用原单额度）
    occupied_roadway_ids = set(db.scalars(select(ScheduleClosure.roadway_id).where(
        ScheduleClosure.shift_id == shift.id)).all())
    other_used = len(occupied_roadway_ids)
    effective_limit = max(0, shift.closure_limit - other_used)
    # 排除所有已占巷道；被排除巷道上的小组会因“巷道不可用”随其巷道组落选
    roadways = [
        {'id': rw.id, 'code': rw.code, 'name': rw.name,
         'teams': [t for t in rw.teams] if rw.id not in occupied_roadway_ids else []}
        for rw in list_roadways(db) if rw.id not in occupied_roadway_ids]
    job_by_team, team_operators = _team_catalog(db)
    result = scheduling.plan_schedule(
        roadways, effective_limit, job_by_team, team_operators, float(old.threshold))
    result['shift'] = {'id': shift.id, 'shift': shift.shift,
                       'closure_limit': shift.closure_limit,
                       'effective_limit': effective_limit,
                       'occupied_roadways': other_used,
                       'excluded_roadway_ids': sorted(occupied_roadway_ids)}
    new_plan = SchedulePlan(
        name=old.name + ' · 按剩余额度重排', shift_id=shift.id,
        threshold=float(old.threshold), status='draft', snapshot=result,
        created_by=user.id, created_at=time.time())
    db.add(new_plan)
    db.flush()
    record(db, user.email, 'schedule.replan', {
        'source_plan': old.id, 'new_plan': new_plan.id,
        'effective_limit': effective_limit, 'covered': result['operators_covered']})
    return new_plan


def closure_status(db):
    """页面查询：各班次额度使用与每条占用来源。"""
    out = []
    for q in list_quotas(db):
        closures = list(db.scalars(
            select(ScheduleClosure).where(ScheduleClosure.shift_id == q.id)))
        rw_map = {rw.id: rw for rw in db.scalars(select(Roadway))}
        used_roadways = sorted({c.roadway_id for c in closures})
        out.append({
            'shift_id': q.id, 'shift': q.shift,
            'closure_limit': q.closure_limit,
            'used': len(used_roadways),
            'remaining': q.closure_limit - len(used_roadways),
            'closures': [{
                'roadway_id': c.roadway_id,
                'roadway_code': rw_map[c.roadway_id].code if c.roadway_id in rw_map else '—',
                'team': c.team, 'plan_id': c.plan_id, 'job_id': c.job_id,
                'operators': c.operators,
            } for c in sorted(closures, key=lambda c: c.id)],
        })
    return out

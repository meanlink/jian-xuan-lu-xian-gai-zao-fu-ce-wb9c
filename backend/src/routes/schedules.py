from fastapi import APIRouter, Depends
from sqlalchemy import select
from src.config.database import get_db
from src.models import Roadway, ShiftQuota
from src.schemas.schedule import RoadwayInput, QuotaInput, PlanInput, DraftInput
from src.middlewares.auth import current_user, can_write, admin_only
from src.services import schedules
from src.services.audit import record
from src.utils.serialization import roadway_dict, quota_dict, plan_dict

router = APIRouter(prefix='/scheduling')


# ---------- 巷道与额度登记 ----------
@router.get('/roadways')
def roadways(db=Depends(get_db), u=Depends(current_user)):
    return [roadway_dict(r) for r in schedules.list_roadways(db)]


@router.post('/roadways', status_code=201)
def create_roadway(data: RoadwayInput, db=Depends(get_db), u=Depends(can_write)):
    r = schedules.register_roadway(db, data)
    record(db, u.email, 'roadway.register', {'id': r.id, 'code': r.code, 'teams': r.teams})
    db.commit()
    return roadway_dict(r)


@router.get('/quotas')
def quotas(db=Depends(get_db), u=Depends(current_user)):
    return [quota_dict(q) for q in schedules.list_quotas(db)]


@router.post('/quotas', status_code=201)
def upsert_quota(data: QuotaInput, db=Depends(get_db), u=Depends(admin_only)):
    q = schedules.upsert_quota(db, data)
    record(db, u.email, 'quota.upsert', {'shift': q.shift, 'limit': q.closure_limit})
    db.commit()
    return quota_dict(q)


# ---------- 草案预览（不占额度、不落库） ----------
@router.post('/draft-preview')
def draft_preview(data: DraftInput, db=Depends(get_db), u=Depends(current_user)):
    _, result = schedules.build_draft(db, data.shift_id, data.threshold)
    return result


# ---------- 排班单 ----------
@router.get('/plans')
def plans(db=Depends(get_db), u=Depends(current_user)):
    return [plan_dict(p) for p in schedules.list_plans(db)]


@router.post('/plans', status_code=201)
def create_plan(data: PlanInput, db=Depends(get_db), u=Depends(can_write)):
    p = schedules.create_plan(db, data, u)
    db.commit()
    return plan_dict(p)


@router.get('/plans/{id}')
def plan_detail(id: int, db=Depends(get_db), u=Depends(current_user)):
    return plan_dict(schedules.get_plan(db, id))


@router.post('/plans/{id}/confirm')
def confirm(id: int, db=Depends(get_db), u=Depends(admin_only)):
    p, outcome = schedules.confirm_plan(db, id, u)
    return {**plan_dict(p), 'confirm_outcome': outcome}


@router.post('/plans/{id}/replan', status_code=201)
def replan(id: int, db=Depends(get_db), u=Depends(can_write)):
    p = schedules.recompute_plan(db, id, u)
    db.commit()
    return plan_dict(p)


@router.get('/closure-status')
def closure_status(db=Depends(get_db), u=Depends(current_user)):
    return schedules.closure_status(db)

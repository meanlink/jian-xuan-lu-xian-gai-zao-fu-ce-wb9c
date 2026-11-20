"""扩测排班纯算法：同进同退的巷道组选包，不依赖数据库，便于单测。

规则（来自业务口径）：
- 每条巷道登记若干必经小组；同一巷道上的组同进同退，构成一个巷道组（连通分量）。
- 组仅在“已批准的小组复测结果”上合格：结果已批准、且改善区间下界达到门槛。
- 一个组没获批或下界未达门槛，整个巷道组都不排（连带落选，给出每组依据）。
- 在封道限额（每班最多封闭巷道条数）内，按覆盖作业员人数尽量多覆盖；
  人数相同时少占巷道优先，再按巷道组键序保证确定性。
"""
from collections import defaultdict


def build_clusters(roadways):
    """把共享巷道的小组合并为同进同退的巷道组（并查集）。

    roadways: [{"id", "code", "name", "teams": [...]}]
    返回 (clusters, team_to_cluster, cluster_roadways)
    """
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for rw in roadways:
        teams = list(rw.get("teams") or [])
        for t in teams:
            find(t)
        for t in teams[1:]:
            union(teams[0], t)

    # 全部 union 完成后，按最终根归并成员与巷道
    root_members = defaultdict(set)
    root_roadways = defaultdict(list)
    for t in list(parent.keys()):
        root_members[find(t)].add(t)
    for rw in roadways:
        roots = {find(t) for t in (rw.get("teams") or [])}
        # 同巷道的组在 union 后必然同根；若巷道无小组则跳过
        for root in roots:
            root_roadways[root].append(rw)

    clusters = []
    team_to_cluster = {}
    cluster_roadways_out = {}
    for index, root in enumerate(sorted(root_members.keys(), key=lambda x: x)):
        members = sorted(root_members[root])
        rws = sorted(root_roadways.get(root, []), key=lambda rw: rw["code"])
        cid = "C%d" % (index + 1)
        clusters.append({"id": cid, "teams": members})
        cluster_roadways_out[cid] = rws
        for t in members:
            team_to_cluster[t] = cid
    return clusters, team_to_cluster, cluster_roadways_out


def evaluate_team(team, job_by_team, threshold):
    """返回单组是否合格及其依据。job_by_team: team -> 最新批准 job 摘要。"""
    job = job_by_team.get(team)
    if not job:
        return False, "无已批准的小组复测结果", None
    if not job.get("approved"):
        return False, "复测结果尚未获批", job
    lower = job.get("ci_lower")
    if lower is None:
        return False, "结果缺少改善区间下界", job
    if lower < threshold:
        return False, "改善区间下界 %.4f 秒未达门槛 %.4f 秒" % (lower, threshold), job
    return True, "已批准且区间下界 %.4f 秒达到门槛 %.4f 秒" % (lower, threshold), job


def plan_schedule(roadways, closure_limit, job_by_team, team_operators, threshold):
    """生成排班草案（不占额度）。

    team_operators: team -> 该组作业员人数
    返回 dict: clusters 评估 + 入选/落选依据 + 限额使用 + 覆盖人数
    """
    clusters, team_to_cluster, cluster_roadways = build_clusters(roadways)
    evaluated = []
    for cluster in clusters:
        cid = cluster["id"]
        rws = cluster_roadways[cid]
        team_rows = []
        eligible = True
        operators = 0
        for t in cluster["teams"]:
            ok, reason, job = evaluate_team(t, job_by_team, threshold)
            team_rows.append({
                "team": t,
                "eligible": ok,
                "reason": reason,
                "job_id": job.get("id") if job else None,
                "ci_lower": job.get("ci_lower") if job else None,
                "operators": int(team_operators.get(t, 0)),
            })
            if not ok:
                eligible = False
            operators += int(team_operators.get(t, 0))
        evaluated.append({
            "cluster_id": cid,
            "teams": cluster["teams"],
            "roadways": [{"id": rw["id"], "code": rw["code"], "name": rw["name"]} for rw in rws],
            "roadway_count": len(rws),
            "operators": operators,
            "eligible": eligible,
            "team_results": team_rows,
        })

    # 候选：合格的巷道组才能参与选包
    candidates = [c for c in evaluated if c["eligible"]]
    rejected = [c for c in evaluated if not c["eligible"]]

    # 贪心：在限额内最大化覆盖人数；人数相同少占巷道优先；再按键序确定
    remaining = int(closure_limit)
    selected, skipped_quota = [], []
    pool = sorted(candidates, key=lambda c: (-c["operators"], c["roadway_count"], c["cluster_id"]))
    for c in pool:
        if c["roadway_count"] <= remaining:
            selected.append(c)
            remaining -= c["roadway_count"]
        else:
            skipped_quota.append(c)
    selected.sort(key=lambda c: c["cluster_id"])
    skipped_quota.sort(key=lambda c: c["cluster_id"])

    used = sum(c["roadway_count"] for c in selected)
    covered = sum(c["operators"] for c in selected)
    for c in skipped_quota:
        c["skip_reason"] = "剩余封道额度 %d 条不足本组所需 %d 条" % (remaining, c["roadway_count"])
    for c in rejected:
        c["skip_reason"] = "巷道组内存在未获批或未达门槛的小组，全组同退"
    return {
        "closure_limit": int(closure_limit),
        "closures_used": used,
        "closures_remaining": int(closure_limit) - used,
        "operators_covered": covered,
        "threshold": threshold,
        "selected": selected,
        "rejected": rejected,
        "skipped_quota": skipped_quota,
        "all_clusters": sorted(evaluated, key=lambda c: c["cluster_id"]),
    }

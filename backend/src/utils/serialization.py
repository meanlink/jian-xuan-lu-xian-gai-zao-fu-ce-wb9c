import hashlib, json
def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
def dataset_dict(d):
    return {'id':d.id, 'name':d.name, 'source':d.source, 'rows':len(d.records), 'checksum':d.checksum, 'created_at':d.created_at}
def job_dict(j):
    return {k:getattr(j,k) for k in ['id','name','dataset_id','params','status','result','error','approved','created_at','finished_at']}
def report_dict(r):
    return {k:getattr(r,k) for k in ['id','name','job_id','destination','interval_seconds','next_run','enabled']}
def delivery_dict(d):
    return {k:getattr(d,k) for k in ['id','report_id','created_at','checksum','filename','destination']}
def roadway_dict(r):
    return {'id':r.id,'code':r.code,'name':r.name,'teams':r.teams,'created_at':r.created_at}
def quota_dict(q):
    return {'id':q.id,'shift':q.shift,'closure_limit':q.closure_limit,'updated_at':q.updated_at}
def plan_dict(p):
    return {'id':p.id,'name':p.name,'shift_id':p.shift_id,'threshold':p.threshold,
            'status':p.status,'snapshot':p.snapshot,'created_by':p.created_by,
            'created_at':p.created_at,'confirmed_at':p.confirmed_at}

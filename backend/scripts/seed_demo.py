import time, json
from sqlalchemy import select, func
from src.config.database import Session
from migrations.initial import migrate
from src.models import User, Dataset, Job, Report, Delivery, Audit, Roadway, ShiftQuota
from src.services.business import metadata, seed_records, analyze
from src.services.reports import deliver
from src.utils.security import hash_password
from src.utils.serialization import checksum

# 演示巷道登记：编号、名称、必经小组。共享巷道的小组同进同退。
SEED_ROADWAYS = [
    ('RW-A1', '北翼主运巷', ['一组', '二组']),
    ('RW-A2', '北翼回风巷', ['二组']),
    ('RW-B1', '南翼运输巷', ['三组']),
    ('RW-B2', '南翼辅运巷', ['三组', '四组']),
    ('RW-C1', '东翼联络巷', ['四组']),
]
SEED_QUOTAS = [('早班', 3), ('中班', 2), ('夜班', 4)]


def seed():
    migrate()
    with Session() as db:
        for role,name in [('admin','林知 · 业务负责人'),('analyst','陈舟 · 分析员'),('viewer','周禾 · 观察员')]:
            email=role+'@demo.local'
            if not db.scalar(select(User).where(User.email==email)):
                db.add(User(email=email,name=name,role=role,password=hash_password('Demo123!')))
        db.flush()
        m=metadata()
        d=db.scalar(select(Dataset).where(Dataset.name==m['dataset_name']))
        if not d:
            rows=seed_records()
            d=Dataset(name=m['dataset_name'],source=m['short']+'-202611.csv',records=rows,checksum=checksum(rows),created_at=time.time())
            db.add(d); db.flush()
        if not db.scalar(select(Job).where(Job.name=='基线复核 · '+m['name'])):
            params={p['key']:p['default'] for p in m.get('parameters',[])}
            result=analyze(d.records,params)
            json.dumps(result,ensure_ascii=False,allow_nan=False)
            admin=db.scalar(select(User).where(User.role=='admin'))
            j=Job(name='基线复核 · '+m['name'],dataset_id=d.id,params=params,status='completed',result=result,created_by=admin.id,created_at=time.time()-3600,finished_at=time.time()-3595,approved=True)
            db.add(j);db.flush()
            r=Report(name='每日业务复核简报',job_id=j.id,destination='业务复核组 · 本地收件箱',interval_seconds=86400,next_run=time.time()+86400,enabled=True)
            db.add(r);db.flush();deliver(db,r)
            db.add(Audit(actor='seed',action='demo.baseline',detail={'dataset':d.id},at=time.time()))
        # 逐小组已批准复测结果，供扩测排班使用（自然键幂等）
        admin=db.scalar(select(User).where(User.role=='admin'))
        for team in ['一组','二组','三组','四组']:
            job_name='小组复测 · '+team
            if not db.scalar(select(Job).where(Job.name==job_name)):
                params={'team':team,'confidence':'0.95'}
                result=analyze(d.records,params)
                json.dumps(result,ensure_ascii=False,allow_nan=False)
                db.add(Job(name=job_name,dataset_id=d.id,params=params,status='completed',
                           result=result,created_by=admin.id,approved=True,
                           created_at=time.time()-1800,finished_at=time.time()-1790))
        db.flush()
        # 巷道与封道额度登记
        for code,name,teams in SEED_ROADWAYS:
            if not db.scalar(select(Roadway).where(Roadway.code==code)):
                db.add(Roadway(code=code,name=name,teams=teams,created_at=time.time()))
        for shift,limit in SEED_QUOTAS:
            if not db.scalar(select(ShiftQuota).where(ShiftQuota.shift==shift)):
                db.add(ShiftQuota(shift=shift,closure_limit=limit,updated_at=time.time()))
        db.commit()
        counts={model.__tablename__:db.scalar(select(func.count()).select_from(model)) for model in [User,Dataset,Job,Report,Delivery,Audit,Roadway,ShiftQuota]}
        print(json.dumps(counts,ensure_ascii=False))
        return counts
if __name__=='__main__':seed()

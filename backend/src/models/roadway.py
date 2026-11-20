from sqlalchemy import String, JSON, Double, Integer, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base


class Roadway(Base):
    """巷道登记：各组的必经巷道，同巷道组在排班时同进同退。"""
    __tablename__ = 'roadways'
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    # 必经该巷道的试点小组，如 ["一组", "三组"]
    teams: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[float] = mapped_column(Double)


class ShiftQuota(Base):
    """每班封道上限：一个班次内最多封闭多少条巷道。"""
    __tablename__ = 'shift_quotas'
    id: Mapped[int] = mapped_column(primary_key=True)
    shift: Mapped[str] = mapped_column(String(40), unique=True)
    closure_limit: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[float] = mapped_column(Double)


class SchedulePlan(Base):
    """扩测排班单：草案不占封道额度，确认后整单占用，可中断恢复。"""
    __tablename__ = 'schedule_plans'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    shift_id: Mapped[int] = mapped_column(ForeignKey('shift_quotas.id'))
    threshold: Mapped[float] = mapped_column(Double)
    status: Mapped[str] = mapped_column(String(20), default='draft')  # draft / confirming / confirmed
    # 选包结果快照：入选组、落选组及依据、覆盖人数、占用额度
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[float] = mapped_column(Double)
    confirmed_at: Mapped[float | None] = mapped_column(Double, nullable=True)


class ScheduleClosure(Base):
    """确认后实际占用的封道额度：(班次, 巷道) 唯一，重试不会重复占用。"""
    __tablename__ = 'schedule_closures'
    __table_args__ = (UniqueConstraint('shift_id', 'roadway_id', name='uq_shift_roadway_closure'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey('schedule_plans.id'))
    shift_id: Mapped[int] = mapped_column(ForeignKey('shift_quotas.id'))
    roadway_id: Mapped[int] = mapped_column(ForeignKey('roadways.id'))
    team: Mapped[str] = mapped_column(String(40))
    job_id: Mapped[int | None] = mapped_column(ForeignKey('jobs.id'), nullable=True)
    operators: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[float] = mapped_column(Double)

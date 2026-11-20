from pydantic import BaseModel, Field


class RoadwayInput(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(default='', max_length=120)
    teams: list[str] = Field(min_length=1, max_length=20)


class QuotaInput(BaseModel):
    shift: str = Field(min_length=1, max_length=40)
    closure_limit: int = Field(ge=0, le=1000)


class PlanInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    shift_id: int
    threshold: float | None = Field(default=None, ge=0, le=10000)


class DraftInput(BaseModel):
    shift_id: int
    threshold: float | None = Field(default=None, ge=0, le=10000)

from pydantic import BaseModel, Field


class CheckInRequest(BaseModel):
    sleep_hours: float | None = Field(default=None, ge=0, le=16)
    energy: int = Field(ge=1, le=5)
    mood: int = Field(ge=1, le=5)
    stress: int = Field(ge=1, le=5)
    available_minutes: int = Field(default=45, ge=0, le=360)
    note: str | None = Field(default=None, max_length=500)


class WeeklyPlanRequest(BaseModel):
    focus_dimensions: list[str] = Field(default_factory=list, max_length=4)
    task_budget: int = Field(default=3, ge=1, le=4)
    note: str | None = Field(default=None, max_length=500)

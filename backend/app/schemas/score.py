from pydantic import BaseModel


class ScoreResponse(BaseModel):
    dimension: str
    score: float
    streak_days: int


class ScoreChangeResponse(BaseModel):
    dimension: str
    delta: float
    streak: int

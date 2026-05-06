from pydantic import BaseModel
from uuid import UUID


class UserResponse(BaseModel):
    id: UUID
    email: str
    nickname: str
    avatar_url: str | None

    class Config:
        from_attributes = True


class ProfileUpdate(BaseModel):
    height_cm: float | None = None
    weight_kg: float | None = None
    age: int | None = None
    gender: str | None = None


class ProfileResponse(BaseModel):
    height_cm: float | None
    weight_kg: float | None
    age: int | None
    gender: str | None
    front_photo_url: str | None
    side_photo_url: str | None

    class Config:
        from_attributes = True


class EvaluateRequest(BaseModel):
    height_cm: float
    weight_kg: float
    age: int
    gender: str

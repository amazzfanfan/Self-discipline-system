from typing import Literal

from pydantic import BaseModel, Field
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


class PreferenceUpdate(BaseModel):
    daily_task_budget: int | None = Field(default=None, ge=1, le=4)
    memory_enabled: bool | None = None
    notification_settings: dict[str, bool] | None = None


class DeleteAccountRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class ProfileResponse(BaseModel):
    height_cm: float | None
    weight_kg: float | None
    age: int | None
    gender: str | None
    avatar_url: str | None
    portrait_photo_url: str | None
    front_photo_url: str | None
    side_photo_url: str | None
    questionnaire: dict[str, str] | None
    skin_analysis: dict | None  # face++ 肤质分析结果
    daily_task_budget: int
    memory_enabled: int
    notification_settings: dict

    class Config:
        from_attributes = True


class EvaluateRequest(BaseModel):
    height_cm: float = Field(ge=100, le=250)
    weight_kg: float = Field(ge=30, le=300)
    age: int = Field(ge=13, le=100)
    gender: Literal["male", "female", "other"]
    questionnaire: dict[str, str] | None = None

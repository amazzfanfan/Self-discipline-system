from datetime import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    nickname: str
    avatar_url: str | None

class ProfileUpdate(BaseModel):
    height_cm: float | None = None
    weight_kg: float | None = Field(default=None, gt=20, lt=300)
    age: int | None = None
    gender: str | None = None
    skincare_constraints: "SkincareConstraints | None" = None
    task_constraints: "TaskConstraints | None" = None


class SkincareConstraints(BaseModel):
    sensitive_skin: bool = False
    pregnancy_or_breastfeeding: bool = False
    skin_barrier_damaged: bool = False
    prescription_treatment: bool = False
    allergies: list[str] = Field(default_factory=list, max_length=20)


class TaskConstraints(BaseModel):
    available_items: list[str] = Field(default_factory=list, max_length=30)
    unavailable_items: list[str] = Field(default_factory=list, max_length=30)
    preferred_locations: list[str] = Field(default_factory=list, max_length=10)
    avoid_activities: list[str] = Field(default_factory=list, max_length=20)
    max_task_minutes: int | None = Field(default=None, ge=5, le=240)
    notes: str = Field(default="", max_length=500)


class PreferenceUpdate(BaseModel):
    daily_task_budget: int | None = Field(default=None, ge=1, le=4)
    memory_enabled: bool | None = None
    notification_settings: dict[str, bool] | None = None
    notification_quiet_start: time | None = None
    notification_quiet_end: time | None = None


class DeleteAccountRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    skincare_constraints: dict
    task_constraints: dict
    daily_task_budget: int
    memory_enabled: int
    notification_settings: dict
    notification_quiet_start: time | None
    notification_quiet_end: time | None

class EvaluateRequest(BaseModel):
    height_cm: float = Field(ge=100, le=250)
    weight_kg: float = Field(ge=30, le=300)
    age: int = Field(ge=13, le=100)
    gender: Literal["male", "female", "other"]
    questionnaire: dict[str, str] | None = None

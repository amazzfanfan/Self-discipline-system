import os
import uuid

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User, UserProfile
from app.models.score import UserScore, DimensionEnum
from app.schemas.user import UserResponse, ProfileUpdate, ProfileResponse, EvaluateRequest
from app.services.ai_service import evaluate_initial_score, analyze_image, generate_appearance_analysis, generate_body_analysis
from app.services.scheduler_service import generate_tasks_for_user
from app.models.conversation import Conversation, RoleEnum

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return user


@router.get("/me/profile", response_model=ProfileResponse)
async def get_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user.profile:
        profile = UserProfile(user_id=user.id)
        db.add(profile)
        await db.flush()
        return profile
    return user.profile


@router.put("/me/profile", response_model=ProfileResponse)
async def update_profile(
    req: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = user.profile
    if not profile:
        profile = UserProfile(user_id=user.id)
        db.add(profile)
        await db.flush()

    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    return profile


@router.post("/me/photos")
async def upload_photo(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    os.makedirs("uploads", exist_ok=True)
    ext = os.path.splitext(file.filename or "photo.jpg")[1]
    filename = f"{user.id}_{uuid.uuid4().hex[:8]}{ext}"
    path = f"uploads/{filename}"
    with open(path, "wb") as f:
        f.write(await file.read())
    return {"url": f"/uploads/{filename}"}


@router.post("/me/photos/upload")
async def upload_onboarding_photos(
    front_photo: UploadFile = File(...),
    side_photo: UploadFile | None = File(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload photos during onboarding. Returns saved URLs."""
    os.makedirs("uploads", exist_ok=True)
    user_id = user.id

    # Save front photo
    ext = os.path.splitext(front_photo.filename or "photo.jpg")[1]
    front_name = f"{user_id}_front_{uuid.uuid4().hex[:8]}{ext}"
    with open(f"uploads/{front_name}", "wb") as f:
        f.write(await front_photo.read())
    front_url = f"/uploads/{front_name}"

    side_url = None
    if side_photo:
        ext = os.path.splitext(side_photo.filename or "photo.jpg")[1]
        side_name = f"{user_id}_side_{uuid.uuid4().hex[:8]}{ext}"
        with open(f"uploads/{side_name}", "wb") as f:
            f.write(await side_photo.read())
        side_url = f"/uploads/{side_name}"

    # Update profile with photo URLs
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if not profile:
        profile = UserProfile(user_id=user_id, front_photo_url=front_url, side_photo_url=side_url)
        db.add(profile)
    else:
        profile.front_photo_url = front_url
        profile.side_photo_url = side_url
    await db.flush()

    return {"front_photo_url": front_url, "side_photo_url": side_url}


@router.post("/me/evaluate")
async def evaluate(
    req: EvaluateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = user.id

    # Update profile (query separately to avoid lazy load in async)
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if not profile:
        profile = UserProfile(user_id=user_id, height_cm=req.height_cm, weight_kg=req.weight_kg, age=req.age, gender=req.gender)
        db.add(profile)
    else:
        profile.height_cm = req.height_cm
        profile.weight_kg = req.weight_kg
        profile.age = req.age
        profile.gender = req.gender

    # Exercise/diet/sleep default to 50 (hard to assess initially)
    scores = {"exercise": 50, "diet": 50, "sleep": 50, "appearance": 50}

    # Only AI-evaluate appearance if user has uploaded photos
    if profile.front_photo_url:
        try:
            appearance_score = await evaluate_initial_score(
                req.height_cm, req.weight_kg, req.age, req.gender,
                front_photo_url=profile.front_photo_url,
                side_photo_url=profile.side_photo_url,
            )
            scores["appearance"] = appearance_score
        except Exception:
            pass  # Keep default 50

    # Update user_scores (create if not exist)
    result = await db.execute(select(UserScore).where(UserScore.user_id == user_id))
    db_scores = {s.dimension: s for s in result.scalars().all()}
    for dim in DimensionEnum:
        if dim.value in db_scores:
            db_scores[dim.value].score = scores[dim.value]
        else:
            db.add(UserScore(user_id=user_id, dimension=dim, score=scores[dim.value]))

    await db.flush()

    # Generate first-login analysis message
    if profile.front_photo_url:
        try:
            analysis = await generate_appearance_analysis(
                user.nickname, float(req.height_cm), float(req.weight_kg), req.age, req.gender,
                front_photo_url=profile.front_photo_url,
                side_photo_url=profile.side_photo_url,
            )
            db.add(Conversation(user_id=user_id, role=RoleEnum.system, content=analysis))
            await db.flush()
        except Exception:
            pass
    else:
        try:
            analysis = await generate_body_analysis(
                user.nickname, float(req.height_cm), float(req.weight_kg), req.age, req.gender,
            )
            db.add(Conversation(user_id=user_id, role=RoleEnum.system, content=analysis))
            await db.flush()
        except Exception:
            pass

    # Generate first day tasks immediately after evaluation
    await generate_tasks_for_user(user_id, user.nickname, db)
    await db.flush()

    return {"message": "evaluation complete", "scores": scores}

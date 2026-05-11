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
from app.services.ai_service import evaluate_all_scores, generate_appearance_analysis, generate_body_analysis
from app.services.faceplus_service import analyze_skin, generate_skin_task
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


@router.post("/me/skin-analyze")
async def skin_analyze(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """聊天界面上传图片进行肤质分析"""
    os.makedirs("uploads", exist_ok=True)
    
    # 保存图片
    ext = os.path.splitext(file.filename or "photo.jpg")[1]
    filename = f"{user.id}_skin_{uuid.uuid4().hex[:8]}{ext}"
    path = f"uploads/{filename}"
    with open(path, "wb") as f:
        f.write(await file.read())
    
    # 分析肤质（带降级策略）
    skin_result = await analyze_skin(path)
    
    # 存储分析结果到用户档案
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == user.id))
    profile = result.scalar_one_or_none()
    if profile:
        profile.skin_analysis = {
            "source": skin_result.source,
            "skin_type": skin_result.skin_type,
            "skin_type_name": skin_result.skin_type_name,
            "skin_score": skin_result.skin_score,
            "issues": skin_result.issues,
            "suggestions": skin_result.suggestions,
        }
        await db.flush()
    
    # 生成分析报告消息
    from app.services.faceplus_service import get_source_display
    source_text = get_source_display(skin_result.source)
    
    report = f"【肤质分析报告】\n"
    report += f"分析方式: {source_text}\n"
    report += f"皮肤类型: {skin_result.skin_type_name}\n"
    report += f"肤质评分: {skin_result.skin_score:.0f}/100\n"
    
    if skin_result.issues:
        report += f"存在问题: {', '.join(skin_result.issues)}\n"
        report += f"\n【护理建议】\n"
        for i, suggestion in enumerate(skin_result.suggestions[:3], 1):
            report += f"{i}. {suggestion}\n"
    else:
        report += "皮肤状态良好，继续保持！\n"
    
    # 保存到对话记录
    db.add(Conversation(user_id=user.id, role=RoleEnum.system, content=report))
    await db.flush()
    
    return {
        "source": skin_result.source,
        "source_display": source_text,
        "skin_type": skin_result.skin_type_name,
        "skin_score": skin_result.skin_score,
        "issues": skin_result.issues,
        "suggestions": skin_result.suggestions,
        "report": report,
        "photo_url": f"/uploads/{filename}",
    }


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

    # Save questionnaire if provided
    if req.questionnaire:
        profile.questionnaire = req.questionnaire

    # AI-evaluate all four dimensions
    try:
        scores = await evaluate_all_scores(
            float(req.height_cm), float(req.weight_kg), req.age, req.gender,
            front_photo_url=profile.front_photo_url,
            side_photo_url=profile.side_photo_url,
            questionnaire=req.questionnaire,
        )
    except Exception as e:
        print(f"[评估] evaluate_all_scores 异常，使用默认分数: {e}")
        scores = {"exercise": 50, "diet": 50, "sleep": 50, "appearance": 50}

    # 肤质分析 (如果有正面照片) - 带降级策略
    skin_result = None
    skin_source = "none"
    if profile.front_photo_url:
        try:
            skin_result = await analyze_skin(profile.front_photo_url.lstrip('/'))
            skin_source = skin_result.source
            
            # 存储肤质分析结果
            profile.skin_analysis = {
                "source": skin_result.source,
                "skin_type": skin_result.skin_type,
                "skin_type_name": skin_result.skin_type_name,
                "skin_score": skin_result.skin_score,
                "issues": skin_result.issues,
                "suggestions": skin_result.suggestions,
                "dark_circle": skin_result.dark_circle,
                "eye_pouch": skin_result.eye_pouch,
                "acne": skin_result.acne,
                "blackhead": skin_result.blackhead,
                "skin_spot": skin_result.skin_spot,
            }
            
            from app.services.faceplus_service import get_source_display
            print(f"[评估] 肤质分析成功 ({get_source_display(skin_result.source)}): {skin_result.skin_type_name}, 评分: {skin_result.skin_score}")
            
            # 肤质分析结果影响外貌评分 (权重 20%)
            appearance_boost = (skin_result.skin_score - 50) * 0.2
            scores["appearance"] = max(0, min(100, scores["appearance"] + appearance_boost))
            print(f"[评估] 肤质调整后外貌评分: {scores['appearance']}")
        except Exception as e:
            print(f"[评估] 肤质分析异常: {e}")

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
            # 如果有肤质分析结果，追加肤质信息
            if skin_result and skin_result.issues:
                skin_msg = f"\n\n【肤质分析】\n皮肤类型: {skin_result.skin_type_name}\n肤质评分: {skin_result.skin_score:.0f}/100\n存在问题: {', '.join(skin_result.issues[:3])}"
                analysis += skin_msg
            
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

    return {
        "message": "evaluation complete",
        "scores": scores,
        "skin_analysis": profile.skin_analysis,
        "skin_source": skin_source,
    }

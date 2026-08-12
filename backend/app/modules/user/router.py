from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User, UserProfile
from app.models.score import UserScore, DimensionEnum
from app.models.assessment import AssessmentRun
from app.schemas.user import (
    DeleteAccountRequest,
    EvaluateRequest,
    PreferenceUpdate,
    ProfileResponse,
    ProfileUpdate,
    UserResponse,
)
from app.core.security import verify_password
from app.services.assessment_service import evaluate_profile
from app.services.cache_service import enqueue_background_job_once, invalidate_scores
from app.services.faceplus_service import (
    analyze_skin,
    generate_ai_suggestions,
    get_source_display,
)
from app.models.conversation import Conversation, RoleEnum
from app.services.assessment_generation_service import generation_payload
from app.services.upload_service import (
    UPLOAD_DIRECTORY,
    delete_saved_image,
    resolve_image_path,
    save_image_upload,
    sha256_file,
)
from app.services.privacy_service import delete_user_account, export_user_data
from app.models.memory import Memory
from sqlalchemy import delete

router = APIRouter(prefix="/api/users", tags=["users"])


def _assessment_payload(run: AssessmentRun, *, reused: bool | None = None) -> dict:
    return {
        "id": str(run.id),
        "input_hash": run.input_hash,
        "rubric_version": run.rubric_version,
        "mode": run.mode,
        "scores": run.scores,
        "evidence": run.evidence,
        "confidence": run.confidence,
        "overall_confidence": float(run.overall_confidence),
        "warnings": run.warnings,
        "skin_source": run.skin_source,
        "skin_input_hash": run.skin_input_hash,
        "reused": run.reused if reused is None else reused,
        "generation": generation_payload(run),
        "created_at": run.created_at.isoformat(),
    }


def _profile_report(nickname: str, assessment: dict, skin_analysis: dict | None) -> str:
    labels = {
        "exercise": "运动状态",
        "diet": "饮食习惯",
        "sleep": "睡眠状态",
        "appearance": "形象管理",
    }
    scores = assessment["scores"]
    score_lines = "\n".join(f"- {labels[key]}：{float(value):.1f}" for key, value in scores.items())
    focus = min(scores, key=lambda key: float(scores[key]))
    report = (
        f"{nickname}，你的初始状态画像已经建立。\n\n"
        f"【状态基线】\n{score_lines}\n\n"
        f"当前可以优先关注：{labels[focus]}。这些分数来自结构化问卷和固定规则，"
        "照片不会被用于推断运动、饮食或睡眠。完成每日任务后，系统会继续记录你的执行变化。"
    )
    if skin_analysis and skin_analysis.get("skin_score") is not None:
        issues = skin_analysis.get("issues") or []
        report += (
            f"\n\n【Face++ 肤质观察】\n皮肤类型：{skin_analysis.get('skin_type_name', '未知')}\n"
            f"肤质评分：{float(skin_analysis['skin_score']):.0f}/100"
        )
        if issues:
            report += f"\n观察项：{', '.join(issues[:3])}"
        report += "\n该结果只用于日常护理参考，不属于医学诊断，也不参与前三项行为评分。"
    return report


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    # Older onboarding records stored the avatar on UserProfile only. Keep the
    # public user payload compatible with those records while new uploads sync
    # both fields below.
    return {
        "id": user.id,
        "email": user.email,
        "nickname": user.nickname,
        "avatar_url": user.avatar_url or (user.profile.avatar_url if user.profile else None),
    }


@router.get("/me/profile", response_model=ProfileResponse)
async def get_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    if not user.profile:
        profile = UserProfile(user_id=user.id)
        db.add(profile)
        await db.flush()
        return profile
    return user.profile


@router.get("/me/assessment/latest")
async def get_latest_assessment(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    result = await db.execute(
        select(AssessmentRun)
        .where(AssessmentRun.user_id == user.id)
        .order_by(AssessmentRun.created_at.desc())
        .limit(1)
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "尚未完成状态评估")
    if run.generation_status in {"pending", "failed"}:
        await enqueue_background_job_once(
            "generate_assessment_extras",
            {"assessment_run_id": str(run.id), "user_id": str(user.id)},
            dedupe_key=f"assessment:{run.id}",
        )
    return _assessment_payload(run)


@router.get("/me/assessment/{assessment_id}/generation")
async def get_assessment_generation(
    assessment_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    run = await db.scalar(
        select(AssessmentRun).where(
            AssessmentRun.id == assessment_id,
            AssessmentRun.user_id == user.id,
        )
    )
    if run is None:
        raise HTTPException(404, "Assessment not found")
    if run.generation_status in {"pending", "failed"}:
        if run.generation_status == "failed":
            run.generation_status = "pending"
            run.generation_stage = "queued"
            run.generation_error = None
            await db.commit()
        await enqueue_background_job_once(
            "generate_assessment_extras",
            {"assessment_run_id": str(run.id), "user_id": str(user.id)},
            dedupe_key=f"assessment:{run.id}",
        )
    return generation_payload(run)


@router.put("/me/profile", response_model=ProfileResponse)
async def update_profile(
    req: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    profile = user.profile
    if not profile:
        profile = UserProfile(user_id=user.id)
        db.add(profile)
        await db.flush()

    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    return profile


@router.patch("/me/preferences")
async def update_preferences(
    req: PreferenceUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    profile = user.profile
    if not profile:
        profile = UserProfile(user_id=user.id)
        db.add(profile)
        await db.flush()
    updates = req.model_dump(exclude_unset=True)
    if "memory_enabled" in updates:
        updates["memory_enabled"] = int(bool(updates["memory_enabled"]))
    for key, value in updates.items():
        setattr(profile, key, value)
    return {
        "daily_task_budget": profile.daily_task_budget,
        "memory_enabled": bool(profile.memory_enabled),
        "notification_settings": profile.notification_settings or {},
        "notification_quiet_start": (
            profile.notification_quiet_start.strftime("%H:%M")
            if profile.notification_quiet_start else None
        ),
        "notification_quiet_end": (
            profile.notification_quiet_end.strftime("%H:%M")
            if profile.notification_quiet_end else None
        ),
    }


@router.get("/me/data-export")
async def export_my_data(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    return await export_user_data(db, user)


@router.delete("/me/memories")
async def clear_my_memories(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    result = await db.execute(delete(Memory).where(Memory.user_id == user.id))
    return {"deleted": result.rowcount or 0}


@router.delete("/me", status_code=204)
async def delete_my_account(
    req: DeleteAccountRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    if not verify_password(req.password, user.password_hash):
        raise HTTPException(403, "密码不正确")
    await delete_user_account(db, user)


@router.post("/me/photos")
async def upload_photo(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    saved = await save_image_upload(file, str(user.id))
    return {"url": saved.url, "quality": saved.quality}


@router.get("/me/photos/files/{filename}")
async def get_private_photo(
    filename: str,
    user: User = Depends(get_current_user),
):
    """Serve a generated upload only to its owning user."""
    if Path(filename).name != filename or not filename.startswith(f"{user.id}_"):
        raise HTTPException(404, "Photo not found")
    target = (UPLOAD_DIRECTORY / filename).resolve()
    if target.parent != UPLOAD_DIRECTORY or not target.is_file():
        raise HTTPException(404, "Photo not found")
    return FileResponse(target, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=300"})


@router.post("/me/photos/upload")
async def upload_photos(
    avatar: UploadFile | None = File(None),
    portrait_photo: UploadFile | None = File(None),
    front_photo: UploadFile | None = File(None),
    side_photo: UploadFile | None = File(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """Upload photos during onboarding. Returns saved URLs."""
    user_id = user.id
    
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if not profile:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
    
    uploaded = {}
    
    # 保存头像
    if avatar:
        previous = profile.avatar_url or user.avatar_url
        saved = await save_image_upload(avatar, f"{user_id}_avatar")
        profile.avatar_url = saved.url
        user.avatar_url = saved.url
        uploaded["avatar_url"] = profile.avatar_url
        uploaded["avatar_quality"] = saved.quality
        await delete_saved_image(previous)
    
    # 保存正面肖像图
    if portrait_photo:
        previous = profile.portrait_photo_url
        saved = await save_image_upload(portrait_photo, f"{user_id}_portrait")
        profile.portrait_photo_url = saved.url
        uploaded["portrait_photo_url"] = profile.portrait_photo_url
        uploaded["portrait_quality"] = saved.quality
        await delete_saved_image(previous)
    
    # 保存正面图
    if front_photo:
        previous = profile.front_photo_url
        saved = await save_image_upload(front_photo, f"{user_id}_front")
        profile.front_photo_url = saved.url
        uploaded["front_photo_url"] = profile.front_photo_url
        uploaded["front_quality"] = saved.quality
        await delete_saved_image(previous)
    
    # 保存侧面图
    if side_photo:
        previous = profile.side_photo_url
        saved = await save_image_upload(side_photo, f"{user_id}_side")
        profile.side_photo_url = saved.url
        uploaded["side_photo_url"] = profile.side_photo_url
        uploaded["side_quality"] = saved.quality
        await delete_saved_image(previous)
    
    await db.flush()
    return uploaded


@router.post("/me/skin-analyze")
async def skin_analyze(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """分析一次性聊天照片；只保留结构化结果，不保留原图。"""
    saved = await save_image_upload(file, f"{user.id}_skin")
    try:
        # 同一图片按内容哈希复用 Face++ 结果，不使用随机视觉模型兜底。
        skin_result = await analyze_skin(saved.path, saved.sha256)

        result = await db.execute(select(UserProfile).where(UserProfile.user_id == user.id))
        profile = result.scalar_one_or_none()
        constraints = profile.skincare_constraints if profile else None
        ai_suggestions = []
        if skin_result.source == "faceplusplus":
            ai_suggestions = await generate_ai_suggestions(
                skin_result.issues,
                skin_result.skin_type_name,
                constraints,
            )
        skin_result.suggestions = ai_suggestions

        if profile:
            profile.skin_analysis = asdict(skin_result)
            await db.flush()

        source_text = get_source_display(skin_result.source)
        report = "【肤质分析报告】\n"
        report += f"分析方式: {source_text}\n"
        if skin_result.skin_score is None:
            report += "本次未获得有效肤质结果，请稍后重试。\n"
        else:
            report += f"皮肤类型: {skin_result.skin_type_name}\n"
            report += f"肤质评分: {skin_result.skin_score:.0f}/100\n"

        if skin_result.skin_score is None:
            pass
        elif skin_result.issues:
            report += f"存在问题: {', '.join(skin_result.issues)}\n"
            report += "\n【护理建议】\n"
            for i, suggestion in enumerate(ai_suggestions[:3], 1):
                report += f"{i}. {suggestion}\n"
        else:
            report += "皮肤状态良好，继续保持！\n"

        db.add(Conversation(user_id=user.id, role=RoleEnum.system, content=report))
        await db.flush()
        return {
            "source": skin_result.source,
            "source_display": source_text,
            "skin_type": skin_result.skin_type_name,
            "skin_score": skin_result.skin_score,
            "issues": skin_result.issues,
            "suggestions": ai_suggestions,
            "report": report,
            "photo_url": None,
            "photo_retained": False,
            "photo_quality": saved.quality,
            "cached": skin_result.cached,
            "error": skin_result.error,
        }
    finally:
        await delete_saved_image(saved.path)


@router.post("/me/evaluate")
async def evaluate(
    req: EvaluateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    user_id = user.id
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if not profile:
        profile = UserProfile(user_id=user_id)
        db.add(profile)

    profile.height_cm = req.height_cm
    profile.weight_kg = req.weight_kg
    profile.age = req.age
    profile.gender = req.gender
    questionnaire = req.questionnaire or profile.questionnaire
    if not questionnaire:
        raise HTTPException(422, "请先完成状态问卷，再建立评分")
    profile.questionnaire = questionnaire

    # Face++ result is independent evidence. Reuse the same image result locally
    # and in Redis before making another external request.
    skin_analysis = profile.skin_analysis if isinstance(profile.skin_analysis, dict) else None
    skin_source = "none"
    photo_hash = None
    photo_for_skin = profile.portrait_photo_url or profile.front_photo_url
    if photo_for_skin:
        try:
            photo_path = resolve_image_path(photo_for_skin)
        except FileNotFoundError:
            photo_path = None
            skin_analysis = None
            skin_source = "unavailable"
        photo_hash = sha256_file(photo_path) if photo_path else None
        if (
            photo_path
            and
            skin_analysis
            and skin_analysis.get("image_hash") == photo_hash
            and skin_analysis.get("source") == "faceplusplus"
        ):
            skin_source = str(skin_analysis.get("source", "none"))
        else:
            skin_result = await analyze_skin(str(photo_path), photo_hash)
            skin_source = skin_result.source
            skin_analysis = asdict(skin_result)
            profile.skin_analysis = skin_analysis
    try:
        assessment = evaluate_profile(
            height_cm=float(req.height_cm),
            weight_kg=float(req.weight_kg),
            age=req.age,
            gender=req.gender,
            questionnaire=questionnaire,
            photo_hash=photo_hash,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    existing_result = await db.execute(
        select(AssessmentRun).where(
            AssessmentRun.user_id == user_id,
            AssessmentRun.input_hash == assessment.input_hash,
            AssessmentRun.rubric_version == assessment.rubric_version,
        )
    )
    assessment_run = existing_result.scalar_one_or_none()
    reused = assessment_run is not None
    if assessment_run is None:
        assessment_run = AssessmentRun(
            user_id=user_id,
            input_hash=assessment.input_hash,
            rubric_version=assessment.rubric_version,
            mode=assessment.mode,
            scores=assessment.scores,
            evidence=assessment.evidence,
            confidence=assessment.confidence,
            overall_confidence=assessment.overall_confidence,
            warnings=assessment.warnings,
            skin_source=skin_source,
            skin_input_hash=photo_hash,
            generation_status="pending",
            generation_stage="queued",
            care_suggestions=[],
        )
        db.add(assessment_run)
    else:
        assessment_run.reused = True
        if skin_source != "none":
            assessment_run.skin_source = skin_source
            assessment_run.skin_input_hash = photo_hash

    scores = {key: float(value) for key, value in assessment_run.scores.items()}
    result = await db.execute(select(UserScore).where(UserScore.user_id == user_id))
    db_scores = {s.dimension: s for s in result.scalars().all()}
    for dim in DimensionEnum:
        new_baseline = scores[dim.value]
        if dim.value in db_scores:
            record = db_scores[dim.value]
            previous_baseline = float(record.baseline_score or record.score)
            behavior_delta = float(record.score) - previous_baseline
            record.baseline_score = new_baseline
            record.score = max(0.0, min(100.0, new_baseline + behavior_delta))
        else:
            db.add(
                UserScore(
                    user_id=user_id,
                    dimension=dim,
                    score=new_baseline,
                    baseline_score=new_baseline,
                )
            )

    await db.flush()
    await invalidate_scores(str(user_id))

    if not reused:
        report_data = assessment.to_dict()
        analysis = _profile_report(user.nickname, report_data, skin_analysis)
        focus_dimension = min(scores, key=scores.get)
        profile_message = Conversation(
            user_id=user_id,
            role=RoleEnum.system,
            content=analysis,
            extra_metadata={
                "message_type": "profile_assessment",
                "assessment": {
                    "scores": scores,
                    "focus_dimension": focus_dimension,
                    "overall_confidence": float(assessment.overall_confidence),
                },
                "skin_analysis": {
                    "skin_type_name": skin_analysis.get("skin_type_name"),
                    "skin_score": skin_analysis.get("skin_score"),
                    "issues": list(skin_analysis.get("issues") or []),
                    "source": skin_analysis.get("source"),
                }
                if skin_analysis
                else None,
                "care_suggestions": [],
                "generation_status": "pending",
            },
        )
        db.add(profile_message)
        await db.flush()
        assessment_run.profile_message_id = profile_message.id

    await db.commit()
    should_enqueue = assessment_run.generation_status != "completed"
    queued = False
    if should_enqueue:
        queued = bool(
            await enqueue_background_job_once(
                "generate_assessment_extras",
                {
                    "assessment_run_id": str(assessment_run.id),
                    "user_id": str(user_id),
                },
                dedupe_key=f"assessment:{assessment_run.id}",
            )
        )

    return {
        "message": "evaluation saved; AI content generation queued",
        "scores": scores,
        "skin_analysis": skin_analysis,
        "skin_source": skin_source,
        "eval_mode": assessment_run.mode,
        "assessment": _assessment_payload(assessment_run, reused=reused),
        "generation_queued": queued,
    }

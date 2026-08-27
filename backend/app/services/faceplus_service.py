"""
Face++ 旷视肤质分析 API 服务
用于分析用户上传的照片，获取详细的肤质数据

Face++ 是唯一的图片分析来源。服务不可用时明确返回 unavailable，
不会再使用随机视觉模型或伪造默认分数。
"""

import httpx
import json
import logging
import time
from typing import Optional
from dataclasses import asdict, dataclass
from app.core.config import get_settings
from app.services.prompt_service import prompt_service
from app.services.skin_safety_service import (
    skincare_constraints_text,
    validate_skin_suggestions,
)
from app.services.task_constraint_service import task_constraints_text, validate_task_feasibility
from app.services.llm_service import chat_completion_with_fallback
from app.services.cache_service import get_cached_skin_analysis, set_cached_skin_analysis
from app.services.capacity_service import distributed_capacity
from app.services.metrics_service import increment_metric, observe_external_call
from app.services.upload_service import sha256_file

settings = get_settings()
logger = logging.getLogger(__name__)

PIPELINE_VERSION = "faceplusplus-skin-v2"
SCORE_ORIGIN = "system_rule_v2"
SCORE_LABEL = "日常肤质状态分（系统换算）"
SKIN_SUGGESTION_MAX_TOKENS = 600
SKIN_SUGGESTION_RETRY_MAX_TOKENS = 800


@dataclass
class SkinAnalysisResult:
    """肤质分析结果"""
    # 分析来源: faceplusplus / unavailable
    source: str
    
    # 皮肤类型: 0=油性, 1=干性, 2=中性, 3=混合性
    skin_type: int
    skin_type_name: str
    
    # 各项指标 (0=无问题, 1=有问题)
    dark_circle: int  # 黑眼圈
    eye_pouch: int  # 眼袋
    forehead_wrinkle: int  # 额头皱纹
    nasolabial_fold: int  # 法令纹
    crows_feet: int  # 鱼尾纹
    glabella_wrinkle: int  # 眉间皱纹
    eye_finelines: int  # 眼部细纹
    
    # 皮肤问题
    acne: int  # 痘痘
    blackhead: int  # 黑头
    skin_spot: int  # 皮肤斑点
    mole: int  # 痣
    
    # 毛孔状况 (0=细腻, 1=略粗)
    pores_forehead: int  # 额头毛孔
    pores_left_cheek: int  # 左脸颊毛孔
    pores_right_cheek: int  # 右脸颊毛孔
    pores_jaw: int  # 下巴毛孔
    left_eyelids: int  # 左眼皮
    right_eyelids: int  # 右眼皮
    
    # 综合评分 (0-100)
    skin_score: float | None
    
    # 问题列表
    issues: list[str]
    
    # 护理建议
    suggestions: list[str]
    image_hash: str | None = None
    cached: bool = False
    error: str | None = None
    score_origin: str | None = None
    score_label: str | None = None
    field_coverage: dict[str, object] | None = None
    suggestions_error: str | None = None


# 皮肤类型映射
SKIN_TYPE_MAP = {
    0: "油性",
    1: "干性",
    2: "中性",
    3: "混合性"
}

# 问题描述映射
ISSUE_MAP = {
    "dark_circle": "黑眼圈",
    "eye_pouch": "眼袋",
    "forehead_wrinkle": "额头皱纹",
    "nasolabial_fold": "法令纹",
    "crows_feet": "鱼尾纹",
    "glabella_wrinkle": "眉间皱纹",
    "eye_finelines": "眼部细纹",
    "acne": "痘痘",
    "blackhead": "黑头",
    "skin_spot": "皮肤斑点",
    "mole": "痣",
    "pores_forehead": "额头毛孔粗大",
    "pores_left_cheek": "左脸颊毛孔粗大",
    "pores_right_cheek": "右脸颊毛孔粗大",
    "pores_jaw": "下巴毛孔粗大",
}

SCORED_SIGNAL_FIELDS = (
    "forehead_wrinkle",
    "nasolabial_fold",
    "crows_feet",
    "glabella_wrinkle",
    "eye_finelines",
    "dark_circle",
    "eye_pouch",
    "acne",
    "blackhead",
    "skin_spot",
    "pores_forehead",
    "pores_left_cheek",
    "pores_right_cheek",
    "pores_jaw",
)


def _faceplus_field_coverage(result: dict) -> dict[str, object]:
    """Validate every provider field used by the local score.

    A non-empty Face++ result is not automatically a complete result. Treating
    omitted metrics as zero would turn schema drift or partial responses into a
    misleading perfect score.
    """
    missing: list[str] = []
    skin_type = result.get("skin_type")
    if not (
        isinstance(skin_type, dict)
        and skin_type.get("skin_type") in SKIN_TYPE_MAP
    ):
        missing.append("skin_type")
    for field in SCORED_SIGNAL_FIELDS:
        payload = result.get(field)
        if not isinstance(payload, dict) or payload.get("value") not in (0, 1):
            missing.append(field)
    expected = len(SCORED_SIGNAL_FIELDS) + 1
    return {
        "present": expected - len(missing),
        "expected": expected,
        "complete": not missing,
        "missing": missing,
    }

def _calculate_skin_score(result: dict) -> tuple[float, list[str]]:
    """计算肤质综合评分，返回 (评分, 问题列表)
    
    注意：建议由AI动态生成，不再在此处生成
    """
    score = 100.0
    issues = []
    
    # 皱纹类问题扣分
    wrinkle_fields = [
        "forehead_wrinkle", "nasolabial_fold", "crows_feet",
        "glabella_wrinkle", "eye_finelines"
    ]
    for field in wrinkle_fields:
        if result.get(field, {}).get("value", 0) == 1:
            score -= 5
            issues.append(ISSUE_MAP.get(field, field))
    
    # 黑眼圈/眼袋扣分
    if result.get("dark_circle", {}).get("value", 0) == 1:
        score -= 8
        issues.append("黑眼圈")
    
    if result.get("eye_pouch", {}).get("value", 0) == 1:
        score -= 5
        issues.append("眼袋")
    
    # 皮肤问题扣分
    if result.get("acne", {}).get("value", 0) == 1:
        score -= 10
        issues.append("痘痘")
    
    if result.get("blackhead", {}).get("value", 0) == 1:
        score -= 5
        issues.append("黑头")
    
    if result.get("skin_spot", {}).get("value", 0) == 1:
        score -= 5
        issues.append("皮肤斑点")
    
    # 毛孔问题扣分
    pore_fields = ["pores_forehead", "pores_left_cheek", "pores_right_cheek", "pores_jaw"]
    for field in pore_fields:
        if result.get(field, {}).get("value", 0) == 1:
            score -= 3
            issues.append(ISSUE_MAP.get(field, field))
    
    # 确保分数在 0-100 之间
    score = max(0, min(100, score))
    
    return score, issues


async def _call_faceplus_api(image_path: str, image_hash: str) -> Optional[SkinAnalysisResult]:
    """调用 face++ API 分析肤质"""
    try:
        with open(image_path, 'rb') as f:
            image_data = f.read()
        
        async with distributed_capacity("faceplus", settings.FACEPLUS_MAX_CONCURRENCY):
            async with httpx.AsyncClient(timeout=settings.FACEPLUSPLUS_TIMEOUT_SECONDS) as client:
                provider_started = time.perf_counter()
                response = await client.post(
                    settings.FACEPLUSPLUS_API_URL,
                    data={
                        "api_key": settings.FACEPLUSPLUS_API_KEY,
                        "api_secret": settings.FACEPLUSPLUS_API_SECRET,
                    },
                    files={
                        "image_file": ("photo.jpg", image_data, "image/jpeg")
                    }
                )
                await observe_external_call(
                    "faceplus",
                    str(response.status_code),
                    (time.perf_counter() - provider_started) * 1000,
                )
            
            response.raise_for_status()
            data = response.json()
            
            # 检查是否有错误
            if "error" in data:
                logger.warning("Face++ API returned an error: %s", data["error"].get("message", "unknown"))
                return None
            
            result = data.get("result", {})
            if not result:
                logger.warning("Face++ API returned an empty result")
                return None

            coverage = _faceplus_field_coverage(result)
            if not coverage["complete"]:
                await increment_metric("external:faceplus:incomplete")
                logger.warning(
                    "Face++ API returned an incomplete result: missing=%s",
                    coverage["missing"],
                )
                return _get_incomplete_result(result, image_hash, coverage)
            
            # 计算综合评分（建议由AI后续动态生成）
            skin_score, issues = _calculate_skin_score(result)
            
            # 提取皮肤类型
            skin_type = result.get("skin_type", {}).get("skin_type", 2)
            
            return SkinAnalysisResult(
                source="faceplusplus",
                skin_type=skin_type,
                skin_type_name=SKIN_TYPE_MAP.get(skin_type, "未知"),
                dark_circle=result.get("dark_circle", {}).get("value", 0),
                eye_pouch=result.get("eye_pouch", {}).get("value", 0),
                forehead_wrinkle=result.get("forehead_wrinkle", {}).get("value", 0),
                nasolabial_fold=result.get("nasolabial_fold", {}).get("value", 0),
                crows_feet=result.get("crows_feet", {}).get("value", 0),
                glabella_wrinkle=result.get("glabella_wrinkle", {}).get("value", 0),
                eye_finelines=result.get("eye_finelines", {}).get("value", 0),
                acne=result.get("acne", {}).get("value", 0),
                blackhead=result.get("blackhead", {}).get("value", 0),
                skin_spot=result.get("skin_spot", {}).get("value", 0),
                mole=result.get("mole", {}).get("value", 0),
                pores_forehead=result.get("pores_forehead", {}).get("value", 0),
                pores_left_cheek=result.get("pores_left_cheek", {}).get("value", 0),
                pores_right_cheek=result.get("pores_right_cheek", {}).get("value", 0),
                pores_jaw=result.get("pores_jaw", {}).get("value", 0),
                left_eyelids=result.get("left_eyelids", {}).get("value", 0),
                right_eyelids=result.get("right_eyelids", {}).get("value", 0),
                skin_score=skin_score,
                issues=issues,
                suggestions=[],  # 建议由AI后续动态生成
                image_hash=image_hash,
                score_origin=SCORE_ORIGIN,
                score_label=SCORE_LABEL,
                field_coverage=coverage,
            )
    except Exception as e:
        await increment_metric("external:faceplus:error")
        logger.warning("Face++ skin analysis failed: %s", e)
        return None


def _get_unavailable_result(image_hash: str, error: str) -> SkinAnalysisResult:
    """Represent missing evidence explicitly instead of inventing a score."""
    return SkinAnalysisResult(
        source="unavailable",
        skin_type=2,
        skin_type_name="暂未分析",
        dark_circle=0,
        eye_pouch=0,
        forehead_wrinkle=0,
        nasolabial_fold=0,
        crows_feet=0,
        glabella_wrinkle=0,
        eye_finelines=0,
        acne=0,
        blackhead=0,
        skin_spot=0,
        mole=0,
        pores_forehead=0,
        pores_left_cheek=0,
        pores_right_cheek=0,
        pores_jaw=0,
        left_eyelids=0,
        right_eyelids=0,
        skin_score=None,
        issues=[],
        suggestions=[],
        image_hash=image_hash,
        error=error,
    )


def _get_incomplete_result(
    raw_result: dict,
    image_hash: str,
    coverage: dict[str, object],
) -> SkinAnalysisResult:
    """Preserve provider provenance without inventing a score."""
    raw_skin_type = raw_result.get("skin_type")
    skin_type = (
        raw_skin_type.get("skin_type")
        if isinstance(raw_skin_type, dict)
        and raw_skin_type.get("skin_type") in SKIN_TYPE_MAP
        else 2
    )
    result = _get_unavailable_result(
        image_hash,
        "Face++ 返回字段不完整，本次未生成状态分",
    )
    result.source = "faceplusplus_incomplete"
    result.skin_type = skin_type
    result.skin_type_name = SKIN_TYPE_MAP.get(skin_type, "暂未确认")
    result.field_coverage = coverage
    result.score_label = SCORE_LABEL
    return result


async def analyze_skin(image_path: str, image_hash: str | None = None) -> SkinAnalysisResult:
    """
    分析图片中的肤质
    
    The exact image is cached by SHA-256 and pipeline version. Cache misses
    call Face++; failures are returned as unavailable without fake scores.
    """
    digest = image_hash or sha256_file(image_path)
    cached = await get_cached_skin_analysis(digest, PIPELINE_VERSION)
    if cached:
        cached["cached"] = True
        return SkinAnalysisResult(**cached)

    if not settings.FACEPLUSPLUS_API_KEY or not settings.FACEPLUSPLUS_API_SECRET:
        logger.warning("Face++ credentials are not configured")
        return _get_unavailable_result(digest, "Face++ 服务未配置")

    result = await _call_faceplus_api(image_path, digest)
    if result:
        if result.source == "faceplusplus":
            await set_cached_skin_analysis(digest, PIPELINE_VERSION, asdict(result))
        return result
    return _get_unavailable_result(digest, "Face++ 服务暂时不可用")


def get_source_display(source: str) -> str:
    """获取分析来源的显示文本"""
    source_map = {
        "faceplusplus": "外部API (face++)",
        "faceplusplus_incomplete": "Face++ 返回结果不完整",
        "unavailable": "暂未获得有效结果",
    }
    return source_map.get(source, source)


async def generate_ai_suggestions(
    issues: list[str],
    skin_type_name: str,
    constraints: dict | None = None,
    task_constraints: dict | None = None,
) -> list[str]:
    """根据肤质问题列表，调用AI生成个性化护理建议
    
    Args:
        issues: 检测到的皮肤问题列表，如 ["黑眼圈", "痘痘", "额头毛孔粗大"]
        skin_type_name: 皮肤类型名称，如 "油性"、"干性"
    
    Returns:
        AI生成的护理建议列表
    """
    issues_str = "、".join(issues) if issues else "未检测到明显问题"
    suggestion_limit = min(3, max(1, len(issues)))
    prompt = prompt_service.build_skin_suggestion_prompt(
        skin_type_name,
        issues_str,
        skincare_constraints_text(constraints),
        task_constraints_text(task_constraints),
        suggestion_limit,
    )

    content = await chat_completion_with_fallback(
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=SKIN_SUGGESTION_MAX_TOKENS,
        response_format={"type": "json_object"},
        enable_thinking=False,
        num_retries=0,
        timeout=20,
    )
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        await increment_metric("ai:skin_suggestions:json_retry")
        logger.warning(
            "AI skin suggestion JSON was incomplete; retrying once: %s",
            exc,
        )
        retry_prompt = (
            f"{prompt}\n\n"
            "上一次响应不是完整JSON。请重新生成更精简的完整JSON；"
            "不要重复说明，不要使用Markdown，并确保所有字符串、数组和对象正确闭合。"
        )
        content = await chat_completion_with_fallback(
            messages=[{"role": "user", "content": retry_prompt}],
            temperature=0,
            max_tokens=SKIN_SUGGESTION_RETRY_MAX_TOKENS,
            response_format={"type": "json_object"},
            enable_thinking=False,
            num_retries=0,
            timeout=20,
        )
        parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise RuntimeError("AI skin suggestion response is not a JSON object")
    cleaned = validate_skin_suggestions(parsed.get("suggestions"), constraints)
    cleaned = [item for item in cleaned if validate_task_feasibility(item, task_constraints)[0]]
    if not cleaned:
        raise RuntimeError("AI skin suggestions require unavailable user resources")
    logger.info("AI skin suggestions generated: count=%s", len(cleaned[:3]))
    return cleaned[:3]


async def generate_ai_suggestions_safely(
    issues: list[str],
    skin_type_name: str,
    constraints: dict | None = None,
    task_constraints: dict | None = None,
) -> tuple[list[str], str | None]:
    """Generate optional advice without invalidating Face++ evidence.

    No issue means there is nothing to advise on, so no model call is needed.
    Model, JSON, or safety-validation failures are reported separately while
    the provider analysis remains usable.
    """
    if not issues:
        return [], None
    try:
        suggestions = await generate_ai_suggestions(
            issues,
            skin_type_name,
            constraints,
            task_constraints,
        )
        return suggestions, None
    except Exception as exc:
        await increment_metric("ai:skin_suggestions:error")
        logger.warning("AI skin suggestions unavailable: %s", exc)
        return [], "AI 个性化护理建议暂时不可用，肤质观察结果仍然有效"


async def generate_skin_task_ai(
    issues: list[str],
    skin_type_name: str,
    constraints: dict | None = None,
    task_constraints: dict | None = None,
) -> str:
    """根据肤质分析结果，调用AI生成个性化护肤任务
    
    Args:
        issues: 检测到的皮肤问题列表
        skin_type_name: 皮肤类型名称
    
    Returns:
        AI生成的护肤任务描述
    """
    issues_str = "、".join(issues[:2]) if issues else "未检测到明显问题"
    prompt = prompt_service.build_skin_task_prompt(
        issues_str,
        skin_type_name,
        skincare_constraints_text(constraints),
        task_constraints_text(task_constraints),
    )

    content = await chat_completion_with_fallback(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=100,
        response_format={"type": "json_object"},
        enable_thinking=False,
        num_retries=0,
        timeout=20,
    )
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise RuntimeError("AI skin task response is not a JSON object")
    task = str(parsed.get("task", "")).strip()
    if not task or len(task) >= 100:
        raise RuntimeError("AI skin task response has no valid task")
    task = validate_skin_suggestions([task], constraints, limit=1)[0]
    feasible, reason = validate_task_feasibility(task, task_constraints)
    if not feasible:
        raise RuntimeError(f"AI skin task is infeasible: {reason}")
    logger.info("AI skin task generated")
    return task

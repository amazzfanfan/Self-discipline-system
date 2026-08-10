"""LLM helpers for tasks and chat intent plus deterministic assessment bridge."""

import json
import logging
import re

from app.services.assessment_service import evaluate_profile
from app.services.llm_service import chat_completion_with_fallback
from app.services.prompt_service import prompt_service

logger = logging.getLogger(__name__)


async def generate_task(
    nickname: str,
    dimension: str,
    score: float,
    difficulty: str,
    recent_tasks: list[str],
    goal_content: str | None = None,
) -> str:
    """Generate a daily task title with AI or raise an explicit error."""
    prompt = prompt_service.build_task_prompt(
        dimension=dimension,
        score=score,
        difficulty=difficulty,
        recent_tasks=recent_tasks,
        goal_content=goal_content,
    )
    content = await chat_completion_with_fallback(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=120,
        response_format={"type": "json_object"},
        enable_thinking=False,
        num_retries=0,
        timeout=20,
    )
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"AI task response for {dimension} is not a JSON object")
    task_title = _clean_task_title(parsed.get("task", ""))
    if not task_title:
        raise RuntimeError(f"AI task response for {dimension} has no valid task")
    logger.info("Task generation succeeded: %s -> %s", dimension, task_title)
    return task_title


def _clean_task_title(text: str) -> str:
    if not text:
        return ""
    text = text.strip().strip('"\'“”「」·•- ')
    text = re.sub(r"^\d+[.、]\s*", "", text)
    for prefix in ("任务：", "任务:", "标题：", "标题:", "今日任务：", "今日任务:"):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    thinking_keywords = (
        "首先",
        "用户要求",
        "维度",
        "生成",
        "系统",
        "难度：",
        "评分：",
        "意味着",
        "所以",
        "应该是",
        "当前评分",
        "最近做过的",
        "避免重复",
        "匹配难度",
    )
    if len(text) > 150 or any(keyword in text for keyword in thinking_keywords):
        return ""
    return text


async def evaluate_all_scores(
    height_cm: float,
    weight_kg: float,
    age: int,
    gender: str,
    portrait_photo_url: str | None = None,
    front_photo_url: str | None = None,
    side_photo_url: str | None = None,
    skin_analysis: dict | None = None,
    questionnaire: dict[str, str] | None = None,
) -> tuple[dict[str, float], str]:
    """Compatibility entry backed by the deterministic rubric engine.

    Photo parameters remain for old callers but never influence behavioral
    scores. Face++ results are stored and displayed separately.
    """
    del portrait_photo_url, front_photo_url, side_photo_url, skin_analysis
    assessment = evaluate_profile(
        height_cm=height_cm,
        weight_kg=weight_kg,
        age=age,
        gender=gender,
        questionnaire=questionnaire,
    )
    return assessment.scores, assessment.mode


def _detect_intent_rules(message: str, today_tasks: list[dict]) -> dict | None:
    msg = message.strip()
    weight_patterns = (
        r"体重\s*(\d+\.?\d*)",
        r"(\d+\.?\d*)\s*(?:公斤|kg|斤)",
        r"称了\s*(\d+\.?\d*)",
    )
    for pattern in weight_patterns:
        match = re.search(pattern, msg, re.IGNORECASE)
        if match:
            weight = float(match.group(1))
            if "斤" in msg:
                weight /= 2
            if 20 < weight < 300:
                return {"intent": "record_weight", "weight_kg": weight}

    complete_keywords = ("完成", "做了", "搞定了", "搞完", "已做", "已完成", "打卡", "搞定")
    skip_keywords = ("不想", "放弃", "跳过", "不做", "算了", "今天不")
    has_complete = any(keyword in msg for keyword in complete_keywords)
    has_skip = any(keyword in msg for keyword in skip_keywords)
    if not has_complete and not has_skip:
        return None

    dimension_keywords = {
        "exercise": ("运动", "快走", "跑步", "健身", "锻炼", "散步", "走路", "游泳", "俯卧撑", "深蹲", "有氧"),
        "diet": ("饮食", "三餐", "吃饭", "记录三餐", "餐食", "食物"),
        "sleep": ("睡眠", "放下手机", "睡觉", "早睡", "作息"),
        "appearance": ("护肤", "外貌", "皮肤", "面膜", "形象"),
    }
    for task in today_tasks:
        dimension = task["dimension"]
        title = task.get("title", "")
        if title and title in msg:
            return {"intent": "complete_task" if has_complete else "skip_task", "dimension": dimension}

    for dimension, keywords in dimension_keywords.items():
        if any(keyword in msg for keyword in keywords):
            return {"intent": "complete_task" if has_complete else "skip_task", "dimension": dimension}

    if has_complete:
        pending_dimensions = [
            task["dimension"]
            for task in today_tasks
            if task.get("status") == "pending"
        ]
        if len(set(pending_dimensions)) == 1:
            return {"intent": "complete_task", "dimension": pending_dimensions[0]}
    return None


RULES_ONLY = False


async def detect_intent(message: str, today_tasks: list[dict]) -> dict:
    if not RULES_ONLY:
        result = await _detect_intent_ai(message, today_tasks)
        if result:
            return result
    result = _detect_intent_rules(message, today_tasks)
    return result or {"intent": "chat"}


async def _detect_intent_ai(message: str, today_tasks: list[dict]) -> dict | None:
    tasks_str = "\n".join(
        f"- {task['dimension']}: {task['title']} ({task['status']})"
        for task in today_tasks
    ) if today_tasks else "无任务"
    prompt = prompt_service.build_intent_ai_prompt(message, tasks_str)
    try:
        content = await chat_completion_with_fallback(
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            enable_thinking=False,
            num_retries=0,
            timeout=15,
        )
        if content:
            parsed = json.loads(content)
            if parsed.get("intent") in ("complete_task", "skip_task", "record_weight", "chat"):
                return parsed
    except Exception as exc:
        logger.warning("AI intent detection failed: %s", exc)
    return None

import asyncio
import base64
import json
import re
import os
import logging
from datetime import datetime, timezone, timedelta
from app.core.config import get_settings
from app.services.llm_service import chat_completion_with_fallback
from app.services.prompt_service import prompt_service

logger = logging.getLogger(__name__)
BJT = timezone(timedelta(hours=8))

settings = get_settings()


# --- Task generation ---

TASK_DEFAULTS = {
    "exercise": "快走30分钟",
    "diet": "记录今日三餐",
    "sleep": "23:00前放下手机",
    "appearance": "认真护肤一次",
}


async def generate_task(nickname: str, dimension: str, score: float, difficulty: str, recent_tasks: list[str], goal_content: str = None) -> str:
    """AI generates a daily task title. Returns a short string.

    Uses llm_service for unified LLM access with retry/fallback.
    """
    prompt = prompt_service.build_task_prompt(
        dimension=dimension,
        score=score,
        difficulty=difficulty,
        recent_tasks=recent_tasks,
        goal_content=goal_content
    )

    try:
        content = await chat_completion_with_fallback(
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        if content:
            parsed = json.loads(content)
            task_title = parsed.get("task", "")
            task_title = _clean_task_title(task_title)
            if task_title:
                logger.info(f"[任务生成] AI成功: {dimension} -> {task_title}")
                return task_title
            else:
                logger.warning(f"[任务生成] AI返回无效标题: {parsed}")
        else:
            logger.warning("[任务生成] AI返回空内容")
    except Exception as e:
        logger.error(f"[任务生成] AI异常: {e}")

    logger.info(f"[任务生成] 使用默认标题: {dimension} -> {TASK_DEFAULTS.get(dimension, '完成一个今日任务')}")
    return TASK_DEFAULTS.get(dimension, "完成一个今日任务")


def _clean_task_title(text: str) -> str:
    """Clean up an AI-generated task title."""
    if not text:
        return ""
    # Remove quotes, bullets, numbering
    text = text.strip().strip('"\'\u201c\u201d\u300c\u300d\u00b7\u2022- ')
    text = re.sub(r'^\d+[.、]\s*', '', text)
    # Remove common prefixes the model might add
    for prefix in ["任务：", "任务:", "标题：", "标题:", "今日任务：", "今日任务:"]:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    # Reject if looks like thinking/reasoning (not a task description)
    thinking_keywords = [
        "首先", "用户要求", "维度", "生成", "系统",
        "难度：", "评分：", "意味着", "所以", "应该是",
        "当前评分", "最近做过的", "避免重复", "匹配难度",
    ]
    if len(text) > 150 or any(kw in text for kw in thinking_keywords):
        return ""
    return text


# --- Appearance analysis ---

async def generate_appearance_analysis(
    nickname: str, height_cm: float, weight_kg: float, age: int, gender: str,
    front_photo_url: str | None = None, side_photo_url: str | None = None,
) -> str:
    """Generate a detailed appearance analysis message for the user's chat."""
    bmi = weight_kg / (height_cm / 100) ** 2
    gender_cn = {"male": "男", "female": "女"}.get(gender, "其他")

    prompt = (
        '你是"系统"，一个AI成长助手。用户' + nickname + '完成了初始评估，请根据数据和照片给出外貌/体态分析。\n\n'
        '数据：身高' + str(height_cm) + 'cm，体重' + str(weight_kg) + 'kg，BMI ' + f'{bmi:.1f}' + '，' + str(age) + '岁，' + gender_cn + '\n\n'
        '请直接用"系统"的口吻写一段分析（严格但关怀），使用 markdown 格式，包含：\n'
        '1. **评估**：对当前外貌/体态的评估（看照片判断，不要只看BMI）\n'
        '2. **改善建议**：3条具体改善建议，用编号列表\n'
        '3. **鼓励**：一句鼓励\n\n'
        '不要写思考过程，不要用第三人称描述自己，直接输出给用户看的内容。200字以内。'
    )

    messages = [{"role": "user", "content": []}]
    if front_photo_url:
        b64_url = _image_path_to_base64(front_photo_url)
        if b64_url:
            messages[0]["content"].append({"type": "image_url", "image_url": {"url": b64_url}})
    if side_photo_url:
        b64_url = _image_path_to_base64(side_photo_url)
        if b64_url:
            messages[0]["content"].append({"type": "image_url", "image_url": {"url": b64_url}})
    messages[0]["content"].append({"type": "text", "text": prompt})

    try:
        result = await chat_completion_with_fallback(messages=messages, max_tokens=1000)
        # Validate: should not look like thinking
        if result and len(result) > 20 and not any(kw in result[:50] for kw in ["好的", "让我", "我需要", "用户要求"]):
            return result
    except Exception as e:
        logger.error(f"[外貌分析] 生成失败: {e}")
    return f"{nickname}，你的初始画像已建立。坚持完成每日任务，分数会稳步提升。"


async def generate_body_analysis(
    nickname: str, height_cm: float, weight_kg: float, age: int, gender: str,
) -> str:
    """Generate a body condition analysis message when user has no photos."""
    bmi = weight_kg / (height_cm / 100) ** 2
    gender_cn = {"male": "男", "female": "女"}.get(gender, "其他")

    if bmi < 18.5:
        bmi_label = "偏瘦"
    elif bmi < 24:
        bmi_label = "正常"
    elif bmi < 28:
        bmi_label = "偏胖"
    else:
        bmi_label = "肥胖"

    prompt = (
        f'你是"系统"，一个AI成长助手。用户{nickname}完成了初始评估（未上传照片），请根据身体数据给出综合评价。\n\n'
        f'数据：身高{height_cm}cm，体重{weight_kg}kg，BMI {bmi:.1f}（{bmi_label}），{age}岁，{gender_cn}\n\n'
        f'请直接用"系统"的口吻写一段详细评价（严格但关怀），使用 markdown 格式，包含：\n'
        f'1. **评估**：对当前身体状况的详细评估（结合BMI和年龄，分析可能的健康风险）\n'
        f'2. **改善建议**：3条具体改善建议（运动、饮食、作息各一条），每条建议要详细说明具体怎么做\n'
        f'3. **鼓励**：一句鼓励的话\n\n'
        f'不要写思考过程，不要用第三人称描述自己，直接输出给用户看的内容。300-400字。'
    )

    try:
        result = await chat_completion_with_fallback(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000
        )
        if result and len(result) > 50:
            return result
    except Exception as e:
        logger.error(f"[评估报告] 生成失败: {e}")

    return f"{nickname}，你的初始画像已建立。当前BMI为{bmi:.1f}（{bmi_label}），坚持完成每日任务，身体状况会逐步改善。"


async def _score_dimension_from_photo(
    dimension: str,
    image_messages: list[dict],
    height_cm: float, weight_kg: float, age: int, gender: str,
) -> float:
    """Score a single dimension from photo analysis. Returns 0-100."""
    bmi = weight_kg / (height_cm / 100) ** 2
    gender_cn = {"male": "男", "female": "女"}.get(gender, "其他")

    prompt = prompt_service.DIMENSION_PROMPTS[dimension].format(
        height=height_cm, weight=weight_kg, bmi=bmi, age=age, gender_cn=gender_cn
    )

    messages = [{"role": "user", "content": image_messages + [{"type": "text", "text": prompt}]}]

    try:
        content = await chat_completion_with_fallback(
            messages=messages,
            max_tokens=200,
            response_format={"type": "json_object"}
        )
        parsed = json.loads(content)
        score = float(parsed.get("score", 50))
        logger.info(f"[四维评分] {dimension} 照片评分: {score}")
        return min(100, max(0, score))
    except Exception as e:
        logger.error(f"[四维评分] {dimension} 照片评分失败: {e}")
        return 50.0


def _image_path_to_base64(photo_url: str) -> str | None:
    """Convert a local image path to base64 data URL."""
    if not photo_url:
        return None
    # Remove leading / and get the file path
    file_path = photo_url.lstrip('/')
    if not os.path.exists(file_path):
        logger.warning(f"[图片转换] 文件不存在: {file_path}")
        return None
    try:
        with open(file_path, 'rb') as f:
            image_data = f.read()
        # Determine MIME type
        ext = os.path.splitext(file_path)[1].lower()
        mime_map = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.gif': 'image/gif', '.webp': 'image/webp'}
        mime_type = mime_map.get(ext, 'image/jpeg')
        b64 = base64.b64encode(image_data).decode('utf-8')
        return f"data:{mime_type};base64,{b64}"
    except Exception as e:
        logger.error(f"[图片转换] 转换失败: {e}")
        return None


async def _evaluate_with_questionnaire(
    height_cm: float, weight_kg: float, age: int, gender: str,
    questionnaire: dict[str, str],
) -> dict[str, float]:
    """Evaluate all 4 dimensions using questionnaire + body data."""
    prompt = prompt_service.build_questionnaire_prompt(
        height=height_cm, weight=weight_kg, age=age, gender=gender,
        questionnaire=questionnaire
    )

    # 重试机制：最多重试 3 次（JSON 解析层面，LLM 层面重试由 llm_service 处理）
    max_retries = 3
    last_error = None

    for attempt in range(max_retries):
        try:
            if attempt > 0:
                wait_time = 5 * attempt
                logger.info(f"[四维评分] 问卷评分第 {attempt + 1} 次尝试，等待 {wait_time} 秒...")
                await asyncio.sleep(wait_time)

            content = await chat_completion_with_fallback(
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )

            # 如果内容为空，抛出异常
            if not content:
                raise Exception("AI 返回空内容")

            # 尝试清理和修复 JSON
            content = content.strip()
            # 如果 JSON 不完整，尝试修复
            if content and not content.endswith('}'):
                last_brace = content.rfind('}')
                if last_brace > 0:
                    content = content[:last_brace + 1]
                else:
                    content = content + '}'

            parsed = json.loads(content)
            result = {
                "exercise": min(100, max(0, float(parsed.get("exercise", 50)))),
                "diet": min(100, max(0, float(parsed.get("diet", 50)))),
                "sleep": min(100, max(0, float(parsed.get("sleep", 50)))),
                "appearance": min(100, max(0, float(parsed.get("appearance", 50)))),
            }
            logger.info(f"[四维评分] 问卷评分成功 (第 {attempt + 1} 次尝试): {result}")
            return result
        except Exception as e:
            last_error = e
            logger.error(f"[四维评分] 问卷评分第 {attempt + 1} 次尝试失败: {e}")
            if attempt < max_retries - 1:
                logger.info(f"[四维评分] 返回内容: {content[:200] if 'content' in locals() else 'N/A'}")

    # 所有重试都失败
    logger.error(f"[四维评分] 问卷评分失败 (已重试 {max_retries} 次): {last_error}")
    return {"exercise": 50, "diet": 50, "sleep": 50, "appearance": 50}


async def _evaluate_comprehensive(
    height_cm: float, weight_kg: float, age: int, gender: str,
    portrait_photo_url: str | None = None,
    front_photo_url: str | None = None,
    side_photo_url: str | None = None,
    skin_analysis: dict | None = None,
) -> dict[str, float]:
    """综合评分模式：图片 + 旷视结果 + 身体数据"""
    prompt = prompt_service.build_comprehensive_prompt(
        height=height_cm, weight=weight_kg, age=age, gender=gender,
        skin_analysis=skin_analysis
    )
    
    # 构建图片消息
    messages = [{"role": "user", "content": []}]
    
    # 添加肖像图（用于肤质参考）
    if portrait_photo_url:
        b64_url = _image_path_to_base64(portrait_photo_url)
        if b64_url:
            messages[0]["content"].append({"type": "image_url", "image_url": {"url": b64_url}})
            logger.info("[四维评分] 肖像图已转为base64")
    
    # 添加正面图（用于体态分析）
    if front_photo_url:
        b64_url = _image_path_to_base64(front_photo_url)
        if b64_url:
            messages[0]["content"].append({"type": "image_url", "image_url": {"url": b64_url}})
            logger.info("[四维评分] 正面图已转为base64")
    
    # 添加侧面图（用于体态分析）
    if side_photo_url:
        b64_url = _image_path_to_base64(side_photo_url)
        if b64_url:
            messages[0]["content"].append({"type": "image_url", "image_url": {"url": b64_url}})
            logger.info("[四维评分] 侧面图已转为base64")
    
    messages[0]["content"].append({"type": "text", "text": prompt})
    
    # 重试机制：最多重试 3 次
    max_retries = 3
    last_error = None
    
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                wait_time = 5 * attempt
                logger.info(f"[四维评分] 第 {attempt + 1} 次尝试，等待 {wait_time} 秒...")
                await asyncio.sleep(wait_time)

            content = await chat_completion_with_fallback(
                messages=messages,
                response_format={"type": "json_object"}
            )

            # 如果内容为空，抛出异常
            if not content:
                raise Exception("AI 返回空内容")

            # 尝试清理和修复 JSON
            content = content.strip()
            if content and not content.endswith('}'):
                last_brace = content.rfind('}')
                if last_brace > 0:
                    content = content[:last_brace + 1]
                else:
                    content = content + '}'

            parsed = json.loads(content)
            result = {
                "exercise": min(100, max(0, float(parsed.get("exercise", 50)))),
                "diet": min(100, max(0, float(parsed.get("diet", 50)))),
                "sleep": min(100, max(0, float(parsed.get("sleep", 50)))),
                "appearance": min(100, max(0, float(parsed.get("appearance", 50)))),
            }
            logger.info(f"[四维评分] 综合评分成功 (第 {attempt + 1} 次尝试): {result}")
            return result
        except Exception as e:
            last_error = e
            logger.error(f"[四维评分] 第 {attempt + 1} 次尝试失败: {e}")
            if attempt < max_retries - 1:
                logger.info(f"[四维评分] 返回内容: {content[:200] if 'content' in locals() else 'N/A'}")

    # 所有重试都失败
    logger.error(f"[四维评分] 综合评分失败 (已重试 {max_retries} 次): {last_error}")
    raise last_error


async def evaluate_all_scores(
    height_cm: float, weight_kg: float, age: int, gender: str,
    portrait_photo_url: str | None = None,
    front_photo_url: str | None = None,
    side_photo_url: str | None = None,
    skin_analysis: dict | None = None,
    questionnaire: dict[str, str] | None = None,
) -> tuple[dict[str, float], str]:
    """Main entry: evaluate all 4 dimension scores.
    
    Returns: (scores_dict, eval_mode)
    - eval_mode: "photo" or "questionnaire" or "default"
    """
    # 有评估图片（肖像图/正面图/侧面图）时使用综合评分模式
    has_eval_photo = portrait_photo_url or front_photo_url or side_photo_url
    
    if has_eval_photo:
        logger.info("[四维评分] 使用综合评分模式（图片+旷视+身体数据）")
        try:
            scores = await _evaluate_comprehensive(
                height_cm, weight_kg, age, gender,
                portrait_photo_url, front_photo_url, side_photo_url,
                skin_analysis
            )
            return scores, "photo"
        except Exception as e:
            logger.warning(f"[四维评分] 综合评分失败，尝试问卷模式: {e}")
    
    # 无图片或综合评分失败时使用问卷模式
    if questionnaire:
        logger.info("[四维评分] 使用问卷模式")
        scores = await _evaluate_with_questionnaire(height_cm, weight_kg, age, gender, questionnaire)
        return scores, "questionnaire"
    
    # 都没有时使用默认分数
    logger.info("[四维评分] 无图片无问卷，使用默认分数")
    return {"exercise": 50, "diet": 50, "sleep": 50, "appearance": 50}, "default"


# --- Intent detection ---


def _detect_intent_rules(message: str, today_tasks: list[dict]) -> dict | None:
    """Rule-based intent detection. Returns intent dict or None if no match."""
    msg = message.strip()

    # Check for weight recording: "体重XX" or "XX公斤" or "XXkg"
    weight_patterns = [
        r'体重\s*(\d+\.?\d*)',
        r'(\d+\.?\d*)\s*(?:公斤|kg|斤)',
        r'称了\s*(\d+\.?\d*)',
    ]
    for pattern in weight_patterns:
        m = re.search(pattern, msg, re.IGNORECASE)
        if m:
            weight = float(m.group(1))
            # If unit is 斤, convert to kg
            if '斤' in msg:
                weight = weight / 2
            if 20 < weight < 300:
                return {"intent": "record_weight", "weight_kg": weight}

    # Check for task completion/skip keywords
    complete_keywords = ['完成', '做了', '搞定了', '搞完', '已做', '已完成', '打卡', '搞定']
    skip_keywords = ['不想', '放弃', '跳过', '不做', '算了', '今天不']

    has_complete = any(kw in msg for kw in complete_keywords)
    has_skip = any(kw in msg for kw in skip_keywords)

    if not has_complete and not has_skip:
        return None

    # Match dimension from task titles or keywords
    dimension_keywords = {
        'exercise': ['运动', '快走', '跑步', '健身', '锻炼', '散步', '走路', '游泳', '俯卧撑', '深蹲', '有氧'],
        'diet': ['饮食', '三餐', '吃饭', '记录三餐', '餐食', '食物'],
        'sleep': ['睡眠', '放下手机', '睡觉', '早睡', '作息'],
        'appearance': ['护肤', '外貌', '皮肤', '面膜', '形象'],
    }

    # First try to match against task titles
    for task in today_tasks:
        dim = task['dimension']
        title = task.get('title', '')
        if title and title in msg:
            if has_complete:
                return {"intent": "complete_task", "dimension": dim}
            else:
                return {"intent": "skip_task", "dimension": dim}

    # Then try keyword matching
    for dim, keywords in dimension_keywords.items():
        for kw in keywords:
            if kw in msg:
                if has_complete:
                    return {"intent": "complete_task", "dimension": dim}
                else:
                    return {"intent": "skip_task", "dimension": dim}

    # If we have completion/skip keywords but no dimension match,
    # check if there's only one pending task in that dimension
    if has_complete:
        pending_dims = [t['dimension'] for t in today_tasks if t.get('status') == 'pending']
        if len(set(pending_dims)) == 1:
            return {"intent": "complete_task", "dimension": pending_dims[0]}

    return None


# 测试时设为 True，只用AI检测；设为 False 时关键词匹配作为兜底
RULES_ONLY = False


async def detect_intent(message: str, today_tasks: list[dict]) -> dict:
    """Detect user intent from chat message. Returns structured intent dict."""
    # 测试时跳过关键词匹配，直接用AI
    if not RULES_ONLY:
        result = await _detect_intent_ai(message, today_tasks)
        if result:
            logger.info(f"[意图检测] AI成功: {result}")
            return result
        else:
            logger.warning("[意图检测] AI失败，降级到关键词匹配")

    # 关键词匹配作为兜底
    result = _detect_intent_rules(message, today_tasks)
    if result:
        logger.info(f"[意图检测] 关键词匹配: {result}")
        return result
    logger.info("[意图检测] 未识别意图，返回chat")
    return {"intent": "chat"}


async def _detect_intent_ai(message: str, today_tasks: list[dict]) -> dict | None:
    """AI-based intent detection with JSON mode. Returns intent dict or None on failure.

    Uses llm_service for unified LLM access with retry/fallback.
    """
    tasks_str = "\n".join(
        f"- {t['dimension']}: {t['title']} ({t['status']})"
        for t in today_tasks
    ) if today_tasks else "无任务"

    prompt = prompt_service.build_intent_ai_prompt(message, tasks_str)

    try:
        content = await chat_completion_with_fallback(
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        if content:
            parsed = json.loads(content)
            if parsed.get("intent") in ("complete_task", "skip_task", "record_weight", "chat"):
                return parsed
            else:
                logger.warning(f"[意图检测] AI返回无效intent: {parsed}")
        else:
            logger.warning("[意图检测] AI返回空内容")
    except Exception as e:
        logger.error(f"[意图检测] AI异常: {e}")

    return None

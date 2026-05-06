import json
import re
import httpx
from collections.abc import AsyncGenerator
from app.core.config import get_settings

settings = get_settings()

SYSTEM_PROMPT = """你是一个名为"系统"的AI助手，灵感来源于小说中的成长系统。你的职责是帮助用户提升自己。
你不是朋友，不是医生，而是一个严格但关怀的引导者。你用数据说话，用鼓励驱动，偶尔带一点幽默。
你相信持续的小进步会带来大变化。

对话原则：
- 不批评，不说教，用数据和事实引导
- 承认人性，偶尔放松是正常的
- 关注趋势，单次失败不代表失败
- 主动关怀，检测到异常时主动询问
- 保持人设，始终以"系统"身份对话
- 绝对不要输出你的思考过程、推理步骤或内心独白，只输出面向用户的回复内容"""


def _extract_content(data: dict) -> str:
    """Extract content from AI response.

    Non-reasoning models: content is in choices[0].message.content.
    Reasoning models (fallback): content may be in reasoning_content.
    """
    msg = data["choices"][0]["message"]
    content = (msg.get("content") or "").strip()

    if content:
        return content

    # Fallback for reasoning models: take last 300 chars of reasoning_content
    reasoning = (msg.get("reasoning_content") or "").strip()
    if reasoning:
        # Take the last chunk — reasoning models typically end with the answer
        tail = reasoning[-300:]
        # Skip partial first line (may be cut mid-sentence)
        tail = tail.split('\n', 1)[-1] if '\n' in tail else tail
        return tail.strip()

    return ""


async def chat_completion(messages: list[dict], user_context: str = "") -> str:
    """Call AI model for chat completion."""
    system_msg = SYSTEM_PROMPT
    if user_context:
        system_msg += f"\n\n用户上下文：{user_context}"

    full_messages = [{"role": "system", "content": system_msg}] + messages

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{settings.AI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {settings.AI_API_KEY}", "Content-Type": "application/json"},
            json={"model": settings.chat_model, "messages": full_messages, "max_tokens": 1500},
        )
        data = response.json()
        return _extract_content(data)


async def chat_completion_stream(messages: list[dict], user_context: str = "") -> AsyncGenerator[str, None]:
    """Stream AI model chat completion, yielding content chunks."""
    system_msg = SYSTEM_PROMPT
    if user_context:
        system_msg += f"\n\n用户上下文：{user_context}"

    full_messages = [{"role": "system", "content": system_msg}] + messages

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST",
            f"{settings.AI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {settings.AI_API_KEY}", "Content-Type": "application/json"},
            json={"model": settings.chat_model, "messages": full_messages, "max_tokens": 1500, "stream": True},
        ) as response:
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content") or ""
                    if content:
                        yield content
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue


# --- Task generation ---

TASK_DEFAULTS = {
    "exercise": "快走30分钟",
    "diet": "记录今日三餐",
    "sleep": "23:00前放下手机",
    "appearance": "认真护肤一次",
}


async def generate_task(nickname: str, dimension: str, score: float, difficulty: str, recent_tasks: list[str]) -> str:
    """AI generates a daily task title. Returns a short string."""
    recent = "、".join(recent_tasks[-5:]) if recent_tasks else "无"
    diff_cn = {"easy": "简单", "medium": "中等", "hard": "困难"}.get(difficulty, "中等")

    # Single message, no system message - forces the model to answer directly
    prompt = (
        f"请为用户生成1个{dimension}维度的今日任务。\n"
        f"难度：{diff_cn}，当前评分：{score}分，最近做过的：{recent}（避免重复）。\n"
        f"要求：具体可执行，有明确完成标准。\n"
        f"只输出任务标题，不要任何解释，不要加引号，不要加序号。"
    )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{settings.AI_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {settings.AI_API_KEY}", "Content-Type": "application/json"},
                json={"model": settings.chat_model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 50},
            )
            data = response.json()
            result = _extract_content(data)
            result = _clean_task_title(result)
            if result:
                return result
    except Exception:
        pass

    return TASK_DEFAULTS.get(dimension, "完成一个今日任务")


def _clean_task_title(text: str) -> str:
    """Clean up an AI-generated task title."""
    if not text:
        return ""
    # Remove quotes, bullets, numbering
    text = text.strip().strip('"\'""「」·•- ')
    text = re.sub(r'^\d+[.、]\s*', '', text)
    # Remove common prefixes the model might add
    for prefix in ["任务：", "任务:", "标题：", "标题:", "今日任务：", "今日任务:"]:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
    # If still too long or looks like thinking, reject
    if len(text) > 100 or any(kw in text for kw in ["首先", "用户", "要求", "维度", "生成", "系统"]):
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
        '请直接用"系统"的口吻写一段分析（严格但关怀），包含：\n'
        '1. 对当前外貌/体态的评估（看照片判断，不要只看BMI）\n'
        '2. 3条具体改善建议\n'
        '3. 一句鼓励\n\n'
        '不要写思考过程，不要用第三人称描述自己，直接输出给用户看的内容。200字以内。'
    )

    messages = [{"role": "user", "content": []}]
    if front_photo_url:
        messages[0]["content"].append({"type": "image_url", "image_url": {"url": f"http://localhost:8000{front_photo_url}"}})
    if side_photo_url:
        messages[0]["content"].append({"type": "image_url", "image_url": {"url": f"http://localhost:8000{side_photo_url}"}})
    messages[0]["content"].append({"type": "text", "text": prompt})

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{settings.AI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {settings.AI_API_KEY}", "Content-Type": "application/json"},
            json={"model": settings.chat_model, "messages": messages, "max_tokens": 1000},
        )
        data = response.json()
        result = _extract_content(data)
        # Validate: should not look like thinking
        if result and len(result) > 20 and not any(kw in result[:50] for kw in ["好的", "让我", "我需要", "用户要求"]):
            return result
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
        f'请直接用"系统"的口吻写一段评价（严格但关怀），包含：\n'
        f'1. 对当前身体状况的评估（结合BMI和年龄）\n'
        f'2. 3条具体改善建议（运动、饮食、作息各一条）\n'
        f'3. 一句鼓励\n\n'
        f'不要写思考过程，不要用第三人称描述自己，直接输出给用户看的内容。200字以内。'
    )

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{settings.AI_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {settings.AI_API_KEY}", "Content-Type": "application/json"},
                json={"model": settings.chat_model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 500},
            )
            data = response.json()
            result = _extract_content(data)
            if result and len(result) > 20:
                return result
    except Exception:
        pass

    return f"{nickname}，你的初始画像已建立。当前BMI为{bmi:.1f}（{bmi_label}），坚持完成每日任务，身体状况会逐步改善。"


async def evaluate_initial_score(
    height_cm: float, weight_kg: float, age: int, gender: str,
    front_photo_url: str | None = None, side_photo_url: str | None = None,
) -> float:
    """AI evaluates appearance score based on user data and photos. Returns a score 0-100."""
    bmi = weight_kg / (height_cm / 100) ** 2
    gender_cn = {"male": "男", "female": "女"}.get(gender, "其他")

    prompt = (
        f"评估用户外貌/体态评分（0-100分）。\n"
        f"数据：身高{height_cm}cm，体重{weight_kg}kg，BMI {bmi:.1f}，{age}岁，{gender_cn}\n"
        f"评分标准：90-100出众，70-89良好，50-69普通，30-49需改善，0-29需较大改善\n"
        f"只返回JSON：{{\"score\": 数字}}"
    )

    messages = [{"role": "user", "content": []}]
    if front_photo_url:
        messages[0]["content"].append({"type": "image_url", "image_url": {"url": f"http://localhost:8000{front_photo_url}"}})
    if side_photo_url:
        messages[0]["content"].append({"type": "image_url", "image_url": {"url": f"http://localhost:8000{side_photo_url}"}})
    messages[0]["content"].append({"type": "text", "text": prompt})

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{settings.AI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {settings.AI_API_KEY}", "Content-Type": "application/json"},
            json={"model": settings.analysis_model, "messages": messages, "max_tokens": 2000},
        )
        data = response.json()
        content = _extract_content(data)
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        if "{" in content:
            json_str = content[content.index("{"):content.rindex("}") + 1]
            parsed = json.loads(json_str)
            score = parsed.get("score", 50)
            if isinstance(score, dict):
                score = score.get("score", 50)
            return min(100, max(0, float(score)))
        return 50.0


async def analyze_image(image_url: str, analysis_type: str) -> str:
    """AI analyzes user-uploaded images."""
    prompt_map = {
        "body": "请分析这张身材照片，评估体态、肌肉线条、整体外形。给出0-100的评分和简要分析。",
        "face": "请分析这张面部照片，评估皮肤状态、精神面貌。给出0-100的评分和简要分析。",
    }
    prompt = prompt_map.get(analysis_type, "请分析这张图片。")

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{settings.AI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {settings.AI_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": settings.analysis_model,
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ]}],
                "max_tokens": 300,
            },
        )
        data = response.json()
        return _extract_content(data)


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


async def detect_intent(message: str, today_tasks: list[dict]) -> dict:
    """Detect user intent from chat message. Returns structured intent dict."""
    result = _detect_intent_rules(message, today_tasks)
    if result:
        return result
    return {"intent": "chat"}

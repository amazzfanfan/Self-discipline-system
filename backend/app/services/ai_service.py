import asyncio
import base64
import json
import re
import httpx
import os
from datetime import datetime, timezone, timedelta
from collections.abc import AsyncGenerator
from app.core.config import get_settings

BJT = timezone(timedelta(hours=8))

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


def _build_system_prompt(user_context: str = "") -> str:
    """Build system prompt with current Beijing time injected."""
    now = datetime.now(BJT)
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    time_str = now.strftime(f"%Y年%m月%d日 %H:%M {weekdays[now.weekday()]}")
    system_msg = SYSTEM_PROMPT + f"\n\n当前时间（北京时间）：{time_str}"
    if user_context:
        system_msg += f"\n\n用户上下文：{user_context}"
    return system_msg


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
    system_msg = _build_system_prompt(user_context)
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
    system_msg = _build_system_prompt(user_context)
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


# --- Dimension scoring prompts (for photo-based evaluation) ---

DIMENSION_PROMPTS = {
    "exercise": (
        "评估用户的运动能力和体能水平（0-100分）。\n"
        "分析照片中的：体型、肌肉线条、体态、是否有运动痕迹。\n"
        "结合身体数据：身高{height}cm，体重{weight}kg，BMI {bmi:.1f}，{age}岁，{gender_cn}。\n"
        "评分标准：90-100运动员体格，70-89经常运动，50-69普通，30-49缺乏运动，0-29体能极差。\n"
        '只返回JSON：{{"score": 数字}}'
    ),
    "diet": (
        "评估用户的饮食健康程度（0-100分）。\n"
        "分析照片中的：体脂率、皮肤光泽、面色、是否有营养不良或过剩迹象。\n"
        "结合身体数据：身高{height}cm，体重{weight}kg，BMI {bmi:.1f}，{age}岁，{gender_cn}。\n"
        "评分标准：90-100非常健康，70-89良好，50-69普通，30-49不健康，0-29严重问题。\n"
        '只返回JSON：{{"score": 数字}}'
    ),
    "sleep": (
        "评估用户的睡眠质量（0-100分）。\n"
        "分析照片中的：黑眼圈、眼袋、肤质、精神状态、面色。\n"
        "结合身体数据：身高{height}cm，体重{weight}kg，BMI {bmi:.1f}，{age}岁，{gender_cn}。\n"
        "评分标准：90-100精神饱满，70-89状态良好，50-69一般，30-49明显疲惫，0-29严重睡眠不足。\n"
        '只返回JSON：{{"score": 数字}}'
    ),
    "appearance": (
        "评估用户的外在形象（0-100分）。\n"
        "分析照片中的：整体形象、穿着打扮、气质、面部状态。\n"
        "结合身体数据：身高{height}cm，体重{weight}kg，BMI {bmi:.1f}，{age}岁，{gender_cn}。\n"
        "评分标准：90-100形象出众，70-89良好，50-69普通，30-49需要打理，0-29需大幅改善。\n"
        '只返回JSON：{{"score": 数字}}'
    ),
}


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

    prompt = (
        f"请为用户生成1个{dimension}维度的今日任务。\n"
        f"难度：{diff_cn}，当前评分：{score}分，最近做过的：{recent}（避免重复）。\n"
        f"要求：具体可执行，有明确完成标准。\n\n"
        f'返回JSON格式：{{"task": "任务标题"}}'
    )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{settings.AI_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {settings.AI_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": settings.chat_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 100,
                    "response_format": {"type": "json_object"},
                },
            )
            data = response.json()
            content = (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
            if content:
                parsed = json.loads(content)
                task_title = parsed.get("task", "")
                task_title = _clean_task_title(task_title)
                if task_title:
                    print(f"[任务生成] AI成功: {dimension} -> {task_title}")
                    return task_title
                else:
                    print(f"[任务生成] AI返回无效标题: {parsed}")
            else:
                print("[任务生成] AI返回空内容")
    except Exception as e:
        print(f"[任务生成] AI异常: {e}")

    print(f"[任务生成] 使用默认标题: {dimension} -> {TASK_DEFAULTS.get(dimension, '完成一个今日任务')}")
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
        f'请直接用"系统"的口吻写一段评价（严格但关怀），使用 markdown 格式，包含：\n'
        f'1. **评估**：对当前身体状况的评估（结合BMI和年龄）\n'
        f'2. **改善建议**：3条具体改善建议（运动、饮食、作息各一条），用编号列表\n'
        f'3. **鼓励**：一句鼓励\n\n'
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


async def _score_dimension_from_photo(
    dimension: str,
    image_messages: list[dict],
    height_cm: float, weight_kg: float, age: int, gender: str,
) -> float:
    """Score a single dimension from photo analysis. Returns 0-100."""
    bmi = weight_kg / (height_cm / 100) ** 2
    gender_cn = {"male": "男", "female": "女"}.get(gender, "其他")

    prompt = DIMENSION_PROMPTS[dimension].format(
        height=height_cm, weight=weight_kg, bmi=bmi, age=age, gender_cn=gender_cn
    )

    messages = [{"role": "user", "content": image_messages + [{"type": "text", "text": prompt}]}]

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{settings.AI_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {settings.AI_API_KEY}", "Content-Type": "application/json"},
                json={"model": settings.chat_model, "messages": messages, "max_tokens": 200, "response_format": {"type": "json_object"}},
            )
            data = response.json()
            content = _extract_content(data)
            parsed = json.loads(content)
            score = float(parsed.get("score", 50))
            print(f"[四维评分] {dimension} 照片评分: {score}")
            return min(100, max(0, score))
    except Exception as e:
        print(f"[四维评分] {dimension} 照片评分失败: {e}")
        return 50.0


def _image_path_to_base64(photo_url: str) -> str | None:
    """Convert a local image path to base64 data URL."""
    if not photo_url:
        return None
    # Remove leading / and get the file path
    file_path = photo_url.lstrip('/')
    if not os.path.exists(file_path):
        print(f"[图片转换] 文件不存在: {file_path}")
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
        print(f"[图片转换] 转换失败: {e}")
        return None


async def _evaluate_with_photos(
    height_cm: float, weight_kg: float, age: int, gender: str,
    front_photo_url: str | None, side_photo_url: str | None,
) -> dict[str, float]:
    """Evaluate all 4 dimensions in parallel using photo analysis."""
    # Build image message parts using base64
    image_parts = []
    if front_photo_url:
        b64_url = _image_path_to_base64(front_photo_url)
        if b64_url:
            image_parts.append({"type": "image_url", "image_url": {"url": b64_url}})
            print(f"[四维评分] 正面照片已转为base64")
        else:
            print(f"[四维评分] 正面照片转换失败: {front_photo_url}")
    if side_photo_url:
        b64_url = _image_path_to_base64(side_photo_url)
        if b64_url:
            image_parts.append({"type": "image_url", "image_url": {"url": b64_url}})
            print(f"[四维评分] 侧面照片已转为base64")

    if not image_parts:
        print("[四维评分] 无有效图片，使用默认分数")
        return {"exercise": 50, "diet": 50, "sleep": 50, "appearance": 50}

    # Run 4 dimension evaluations in parallel
    results = await asyncio.gather(
        _score_dimension_from_photo("exercise", image_parts, height_cm, weight_kg, age, gender),
        _score_dimension_from_photo("diet", image_parts, height_cm, weight_kg, age, gender),
        _score_dimension_from_photo("sleep", image_parts, height_cm, weight_kg, age, gender),
        _score_dimension_from_photo("appearance", image_parts, height_cm, weight_kg, age, gender),
    )

    return {
        "exercise": results[0],
        "diet": results[1],
        "sleep": results[2],
        "appearance": results[3],
    }


QUESTIONNAIRE_PROMPT = """评估用户四个维度的初始评分（0-100分）。

身体数据：
- 身高：{height}cm
- 体重：{weight}kg
- BMI：{bmi:.1f}
- 年龄：{age}岁
- 性别：{gender_cn}

用户自述：
- 运动：{exercise_answer}
- 饮食：{diet_answer}
- 睡眠：{sleep_answer}
- 外貌：{appearance_answer}

评分标准：90-100优秀，70-89良好，50-69普通，30-49需改善，0-29需大幅改善。
请根据用户自述内容合理评估，不要全部给50分。回答越详细、习惯越好，分数越高。

只返回JSON：{{"exercise": 数字, "diet": 数字, "sleep": 数字, "appearance": 数字}}"""


async def _evaluate_with_questionnaire(
    height_cm: float, weight_kg: float, age: int, gender: str,
    questionnaire: dict[str, str],
) -> dict[str, float]:
    """Evaluate all 4 dimensions using questionnaire + body data."""
    bmi = weight_kg / (height_cm / 100) ** 2
    gender_cn = {"male": "男", "female": "女"}.get(gender, "其他")

    prompt = QUESTIONNAIRE_PROMPT.format(
        height=height_cm, weight=weight_kg, bmi=bmi, age=age, gender_cn=gender_cn,
        exercise_answer=questionnaire.get("exercise", "未回答"),
        diet_answer=questionnaire.get("diet", "未回答"),
        sleep_answer=questionnaire.get("sleep", "未回答"),
        appearance_answer=questionnaire.get("appearance", "未回答"),
    )

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{settings.AI_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {settings.AI_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": settings.chat_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 200,
                    "response_format": {"type": "json_object"},
                },
            )
            data = response.json()
            content = _extract_content(data)
            parsed = json.loads(content)
            result = {
                "exercise": min(100, max(0, float(parsed.get("exercise", 50)))),
                "diet": min(100, max(0, float(parsed.get("diet", 50)))),
                "sleep": min(100, max(0, float(parsed.get("sleep", 50)))),
                "appearance": min(100, max(0, float(parsed.get("appearance", 50)))),
            }
            print(f"[四维评分] 问卷评分成功: {result}")
            return result
    except Exception as e:
        print(f"[四维评分] 问卷评分失败: {e}")
        return {"exercise": 50, "diet": 50, "sleep": 50, "appearance": 50}


async def evaluate_all_scores(
    height_cm: float, weight_kg: float, age: int, gender: str,
    front_photo_url: str | None = None, side_photo_url: str | None = None,
    questionnaire: dict[str, str] | None = None,
) -> dict[str, float]:
    """Main entry: evaluate all 4 dimension scores.

    - With photos: 4 parallel AI calls, each analyzing the photo for its dimension.
    - Without photos: single AI call with questionnaire + body data.
    - Fallback: returns 50 for all dimensions.
    """
    if front_photo_url:
        print("[四维评分] 使用照片模式（4次并行调用）")
        return await _evaluate_with_photos(height_cm, weight_kg, age, gender, front_photo_url, side_photo_url)

    if questionnaire:
        print("[四维评分] 使用问卷模式（单次调用）")
        return await _evaluate_with_questionnaire(height_cm, weight_kg, age, gender, questionnaire)

    print("[四维评分] 无照片无问卷，使用默认分数")
    return {"exercise": 50, "diet": 50, "sleep": 50, "appearance": 50}


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
        b64_url = _image_path_to_base64(front_photo_url)
        if b64_url:
            messages[0]["content"].append({"type": "image_url", "image_url": {"url": b64_url}})
    if side_photo_url:
        b64_url = _image_path_to_base64(side_photo_url)
        if b64_url:
            messages[0]["content"].append({"type": "image_url", "image_url": {"url": b64_url}})
    messages[0]["content"].append({"type": "text", "text": prompt})

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{settings.AI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {settings.AI_API_KEY}", "Content-Type": "application/json"},
            json={"model": settings.chat_model, "messages": messages, "max_tokens": 2000},
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

    # Convert to base64 if it's a local path
    if image_url.startswith('/'):
        b64_url = _image_path_to_base64(image_url)
        if not b64_url:
            return "图片加载失败"
        image_url = b64_url

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{settings.AI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {settings.AI_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": settings.chat_model,
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


INTENT_PROMPT = """分析用户消息，判断意图。只返回JSON，不要其他内容。

意图类型：
- complete_task: 用户报告完成了某个任务（运动/饮食/睡眠/外貌）
- skip_task: 用户表示不想做或放弃某个任务
- record_weight: 用户报告体重数据
- chat: 普通对话、提问、闲聊

返回格式：
{{"intent": "complete_task", "dimension": "exercise"}}
{{"intent": "skip_task", "dimension": "diet"}}
{{"intent": "record_weight", "weight_kg": 72.5}}
{{"intent": "chat"}}

dimension 只能是: exercise, diet, sleep, appearance

今日任务：
{today_tasks}

用户消息：{message}"""


# 测试时设为 True，只用AI检测；设为 False 时关键词匹配作为兜底
RULES_ONLY = False


async def detect_intent(message: str, today_tasks: list[dict]) -> dict:
    """Detect user intent from chat message. Returns structured intent dict."""
    # 测试时跳过关键词匹配，直接用AI
    if not RULES_ONLY:
        result = await _detect_intent_ai(message, today_tasks)
        if result:
            print(f"[意图检测] AI成功: {result}")
            return result
        else:
            print("[意图检测] AI失败，降级到关键词匹配")

    # 关键词匹配作为兜底
    result = _detect_intent_rules(message, today_tasks)
    if result:
        print(f"[意图检测] 关键词匹配: {result}")
        return result
    print("[意图检测] 未识别意图，返回chat")
    return {"intent": "chat"}


async def _detect_intent_ai(message: str, today_tasks: list[dict]) -> dict | None:
    """AI-based intent detection with JSON mode. Returns intent dict or None on failure."""
    tasks_str = "\n".join(
        f"- {t['dimension']}: {t['title']} ({t['status']})"
        for t in today_tasks
    ) if today_tasks else "无任务"

    prompt = INTENT_PROMPT.format(today_tasks=tasks_str, message=message)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{settings.AI_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {settings.AI_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": settings.chat_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 100,
                    "response_format": {"type": "json_object"},
                },
            )
            data = response.json()
            content = (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
            if content:
                parsed = json.loads(content)
                if parsed.get("intent") in ("complete_task", "skip_task", "record_weight", "chat"):
                    return parsed
                else:
                    print(f"[意图检测] AI返回无效intent: {parsed}")
            else:
                print("[意图检测] AI返回空内容")
    except Exception as e:
        print(f"[意图检测] AI异常: {e}")

    return None

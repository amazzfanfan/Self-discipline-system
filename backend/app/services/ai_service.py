import httpx
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
- 保持人设，始终以"系统"身份对话"""


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
            json={"model": settings.AI_MODEL, "messages": full_messages, "max_tokens": 500},
        )
        data = response.json()
        return data["choices"][0]["message"]["content"]


async def generate_task(nickname: str, dimension: str, score: float, difficulty: str, recent_tasks: list[str]) -> str:
    """AI generates a daily task."""
    recent = "、".join(recent_tasks[-5:]) if recent_tasks else "无"
    prompt = f"用户{nickname}，{dimension}维度当前评分{score}分。请生成1个今日任务，难度{difficulty}，具体可执行，有明确完成标准。最近做过的任务：{recent}，请避免重复。只返回任务标题，不要其他内容。"

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{settings.AI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {settings.AI_API_KEY}", "Content-Type": "application/json"},
            json={"model": settings.AI_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 100},
        )
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()


async def evaluate_initial_score(height_cm: float, weight_kg: float, age: int, gender: str) -> dict:
    """AI evaluates initial scores based on user data."""
    prompt = f"""基于以下用户数据评估四个维度的得分（0-100）：
身高：{height_cm}cm，体重：{weight_kg}kg，年龄：{age}岁，性别：{gender}

请以JSON格式返回，包含四个维度：
- exercise: 运动/体态评分
- diet: 饮食/营养评分
- sleep: 睡眠/作息评分
- appearance: 外貌/皮肤评分

参考中国成年人健康标准，BMI正常范围18.5-24。只返回JSON，不要其他内容。"""

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{settings.AI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {settings.AI_API_KEY}", "Content-Type": "application/json"},
            json={"model": settings.AI_MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": 200},
        )
        data = response.json()
        import json
        return json.loads(data["choices"][0]["message"]["content"])


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
                "model": settings.AI_MODEL,
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ]}],
                "max_tokens": 300,
            },
        )
        data = response.json()
        return data["choices"][0]["message"]["content"]

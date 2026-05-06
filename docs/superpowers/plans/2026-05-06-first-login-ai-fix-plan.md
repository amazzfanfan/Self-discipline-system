# 首次登录消息与AI回复质量修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复两个问题：(1) 用户未上传照片时首次登录无欢迎消息；(2) AI 回复质量差（输出思考过程或乱码），通过切换非推理模型解决。

**Architecture:** 双模型架构 — 聊天/任务生成使用非推理模型（content 字段直接返回结果），评分/图片分析保留推理模型。修改集中在 `config.py`、`ai_service.py`、`user/router.py` 三个文件。

**Tech Stack:** Python, FastAPI, httpx, pydantic-settings

---

## 文件清单

| 文件 | 操作 | 职责 |
|------|------|------|
| `backend/app/core/config.py` | 修改 | 新增 `AI_CHAT_MODEL` 和 `AI_ANALYSIS_MODEL` 配置 |
| `backend/app/services/ai_service.py` | 修改 | 简化 `_extract_content`，新增 `generate_body_analysis`，各函数使用正确模型 |
| `backend/app/modules/user/router.py` | 修改 | `evaluate` 函数增加无照片时的分析消息分支 |
| `backend/.env.example` | 修改 | 新增两个模型配置项 |

---

### Task 1: 双模型配置

**Files:**
- Modify: `backend/app/core/config.py:22-24`
- Modify: `backend/.env.example`

- [ ] **Step 1: 在 Settings 类中新增两个模型配置**

在 `backend/app/core/config.py` 的 `AI_MODEL` 行之后添加：

```python
    AI_CHAT_MODEL: str = ""        # Non-reasoning model for chat/tasks (e.g. qwen-plus)
    AI_ANALYSIS_MODEL: str = ""    # Reasoning model for scoring/image analysis (e.g. mimo-v2.5-pro)
```

同时添加一个 property 方法，让 `AI_CHAT_MODEL` 和 `AI_ANALYSIS_MODEL` 在为空时回退到 `AI_MODEL`。在 `Settings` 类末尾添加：

```python
    @property
    def chat_model(self) -> str:
        return self.AI_CHAT_MODEL or self.AI_MODEL

    @property
    def analysis_model(self) -> str:
        return self.AI_ANALYSIS_MODEL or self.AI_MODEL
```

完整 `config.py` 如下：

```python
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    APP_NAME: str = "System Agent"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/system_agent"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # AI
    AI_API_KEY: str = ""
    AI_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    AI_MODEL: str = "qwen-vl-plus"
    AI_CHAT_MODEL: str = ""        # Non-reasoning model for chat/tasks (e.g. qwen-plus)
    AI_ANALYSIS_MODEL: str = ""    # Reasoning model for scoring/image analysis (e.g. mimo-v2.5-pro)

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    class Config:
        env_file = ".env"

    @property
    def chat_model(self) -> str:
        return self.AI_CHAT_MODEL or self.AI_MODEL

    @property
    def analysis_model(self) -> str:
        return self.AI_ANALYSIS_MODEL or self.AI_MODEL


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 2: 更新 .env.example**

在 `backend/.env.example` 中 `AI_MODEL` 行之后添加：

```
AI_CHAT_MODEL=qwen-plus
AI_ANALYSIS_MODEL=mimo-v2.5-pro
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/config.py backend/.env.example
git commit -m "feat: add dual-model config for chat and analysis"
```

---

### Task 2: 简化 _extract_content

**Files:**
- Modify: `backend/app/services/ai_service.py:22-67`

- [ ] **Step 1: 替换 _extract_content 函数**

将 `backend/app/services/ai_service.py` 中的 `_extract_content` 函数（第 22-67 行）替换为：

```python
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
        # Clean common thinking prefixes from the start of the tail
        tail = re.sub(r'^.*?(?=[\n]|$)', '', tail, count=1) if '\n' in tail else tail
        return tail.strip()

    return ""
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/ai_service.py
git commit -m "fix: simplify _extract_content for non-reasoning models"
```

---

### Task 3: 各函数使用正确的模型

**Files:**
- Modify: `backend/app/services/ai_service.py`

- [ ] **Step 1: 修改 chat_completion 使用 chat_model**

找到 `chat_completion` 函数（约第 70 行），将 `settings.AI_MODEL` 改为 `settings.chat_model`：

```python
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
```

- [ ] **Step 2: 修改 chat_completion_stream 使用 chat_model**

找到 `chat_completion_stream` 函数（约第 88 行），将 `settings.AI_MODEL` 改为 `settings.chat_model`：

```python
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
```

- [ ] **Step 3: 修改 generate_task 使用 chat_model**

找到 `generate_task` 函数（约第 129 行），将 `settings.AI_MODEL` 改为 `settings.chat_model`：

```python
async def generate_task(nickname: str, dimension: str, score: float, difficulty: str, recent_tasks: list[str]) -> str:
    """AI generates a daily task title. Returns a short string."""
    recent = "、".join(recent_tasks[-5:]) if recent_tasks else "无"
    diff_cn = {"easy": "简单", "medium": "中等", "hard": "困难"}.get(difficulty, "中等")

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
```

- [ ] **Step 4: 修改 generate_appearance_analysis 使用 chat_model**

找到 `generate_appearance_analysis` 函数（约第 179 行），将 `settings.AI_MODEL` 改为 `settings.chat_model`：

```python
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
        if result and len(result) > 20:
            return result
        return f"{nickname}，你的初始画像已建立。坚持完成每日任务，分数会稳步提升。"
```

- [ ] **Step 5: 修改 evaluate_initial_score 使用 analysis_model**

找到 `evaluate_initial_score` 函数（约第 218 行），将 `settings.AI_MODEL` 改为 `settings.analysis_model`：

```python
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
```

- [ ] **Step 6: 修改 analyze_image 使用 analysis_model**

找到 `analyze_image` 函数（约第 262 行），将 `settings.AI_MODEL` 改为 `settings.analysis_model`：

```python
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
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/ai_service.py
git commit -m "feat: route chat functions to chat_model, analysis functions to analysis_model"
```

---

### Task 4: 新增 generate_body_analysis 函数

**Files:**
- Modify: `backend/app/services/ai_service.py`

- [ ] **Step 1: 在 generate_appearance_analysis 函数之后添加 generate_body_analysis**

在 `backend/app/services/ai_service.py` 中，`generate_appearance_analysis` 函数结束后（`return f"{nickname}，你的初始画像已建立..."` 那行之后），添加：

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/ai_service.py
git commit -m "feat: add generate_body_analysis for users without photos"
```

---

### Task 5: 修复 evaluate 函数的首次登录消息逻辑

**Files:**
- Modify: `backend/app/modules/user/router.py:108-171`

- [ ] **Step 1: 修改 evaluate 函数**

将 `backend/app/modules/user/router.py` 中 `evaluate` 函数的导入行和分析消息逻辑修改如下。

首先更新导入，在现有导入中添加 `generate_body_analysis`：

```python
from app.services.ai_service import evaluate_initial_score, analyze_image, generate_appearance_analysis, generate_body_analysis
```

然后将 `evaluate` 函数中第 154-165 行的分析消息逻辑：

```python
    # Generate appearance analysis message if user uploaded photos
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
```

替换为：

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/modules/user/router.py
git commit -m "fix: send body analysis message when user has no photos"
```

---

### Task 6: 端到端验证

- [ ] **Step 1: 启动后端服务**

```bash
cd backend
python -m uvicorn app.main:app --reload --port 8000
```

- [ ] **Step 2: 测试有照片用户的首次登录流程**

使用 curl 或前端注册一个新用户，完成 Onboarding（上传照片），检查对话历史中是否包含外貌分析消息和任务消息：

```bash
# 注册
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test1@example.com","password":"test123456","nickname":"测试用户1"}'

# 登录
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test1@example.com","password":"test123456"}'

# 使用 token 完成评估（有照片场景需要通过前端上传照片）
# 检查对话历史
curl http://localhost:8000/api/chat/history \
  -H "Authorization: Bearer <token>"
```

期望结果：对话历史中包含系统发送的外貌分析消息 + 任务公告消息。

- [ ] **Step 3: 测试无照片用户的首次登录流程**

```bash
# 注册新用户
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test2@example.com","password":"test123456","nickname":"测试用户2"}'

# 登录
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test2@example.com","password":"test123456"}'

# 直接评估（不上传照片）
curl -X POST http://localhost:8000/api/users/me/evaluate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"height_cm":175,"weight_kg":70,"age":25,"gender":"male"}'

# 检查对话历史
curl http://localhost:8000/api/chat/history \
  -H "Authorization: Bearer <token>"
```

期望结果：对话历史中包含系统发送的身体综合评价消息（非外貌照片分析）+ 任务公告消息。

- [ ] **Step 4: 测试聊天回复质量**

```bash
# 发送一条聊天消息
curl -X POST "http://localhost:8000/api/chat/send?content=你好，我今天应该做什么" \
  -H "Authorization: Bearer <token>"
```

期望结果：回复是正常的面向用户的对话内容，不是思考过程或乱码。

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: complete first-login message and AI reply quality fix"
```

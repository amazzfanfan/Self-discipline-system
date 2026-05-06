# 聊天任务意图识别 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户在聊天中说"我完成了XX任务"时，系统自动识别意图、完成任务、更新评分，而非仅靠 AI 文字回复。

**Architecture:** 新增 `detect_intent` 函数用 AI 识别用户意图（complete_task/skip_task/record_weight/chat），在 chat router 中先执行意图对应操作，再让 AI 回复包含操作结果。任务完成和体重记录的核心逻辑提取为 service 函数复用。

**Tech Stack:** Python, FastAPI, SQLAlchemy, httpx

---

## 文件清单

| 文件 | 操作 | 职责 |
|------|------|------|
| `backend/app/services/ai_service.py` | 修改 | 新增 `detect_intent` 函数 |
| `backend/app/services/task_service.py` | 新建 | 提取任务完成/跳过的核心逻辑 |
| `backend/app/services/weight_service.py` | 新建 | 提取体重记录的核心逻辑 |
| `backend/app/modules/chat/router.py` | 修改 | send_message 和 stream_message 增加意图识别流程 |
| `backend/app/modules/task/router.py` | 修改 | 调用 task_service 复用逻辑 |
| `backend/app/modules/weight/router.py` | 修改 | 调用 weight_service 复用逻辑 |

---

### Task 1: 新增 detect_intent 函数

**Files:**
- Modify: `backend/app/services/ai_service.py`

- [ ] **Step 1: 在 ai_service.py 末尾添加 detect_intent 函数**

在 `backend/app/services/ai_service.py` 文件末尾（`analyze_image` 函数之后）添加：

```python
# --- Intent detection ---

INTENT_PROMPT = """分析用户消息，判断意图。只返回JSON，不要其他内容。

意图类型：
- complete_task: 用户报告完成了某个任务（运动/饮食/睡眠/外貌）
- skip_task: 用户表示不想做或放弃某个任务
- record_weight: 用户报告体重数据
- chat: 普通对话、提问、闲聊

返回格式：
{"intent": "complete_task", "dimension": "exercise"}
{"intent": "skip_task", "dimension": "diet"}
{"intent": "record_weight", "weight_kg": 72.5}
{"intent": "chat"}

dimension 只能是: exercise, diet, sleep, appearance

今日任务：
{today_tasks}

用户消息：{message}"""


async def detect_intent(message: str, today_tasks: list[dict]) -> dict:
    """Detect user intent from chat message. Returns structured intent dict."""
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
                json={"model": settings.chat_model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 100},
            )
            data = response.json()
            content = _extract_content(data)
            # Parse JSON from response
            if "{" in content:
                json_str = content[content.index("{"):content.rindex("}") + 1]
                result = json.loads(json_str)
                # Validate intent type
                if result.get("intent") in ("complete_task", "skip_task", "record_weight", "chat"):
                    return result
    except Exception:
        pass

    return {"intent": "chat"}
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/ai_service.py
git commit -m "feat: add detect_intent function for chat intent recognition"
```

---

### Task 2: 提取任务完成逻辑到 task_service

**Files:**
- Create: `backend/app/services/task_service.py`
- Modify: `backend/app/modules/task/router.py`

- [ ] **Step 1: 创建 task_service.py**

创建 `backend/app/services/task_service.py`：

```python
from datetime import date, datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.models.task import Task, TaskStatusEnum
from app.models.score import DimensionEnum
from app.services.score_service import record_task_completion, record_negative


async def complete_task_by_dimension(db: AsyncSession, user_id: str, dimension: str) -> dict:
    """Complete today's pending task for a dimension. Returns result dict."""
    dim_enum = DimensionEnum(dimension)
    result = await db.execute(
        select(Task).where(
            and_(
                Task.user_id == user_id,
                Task.scheduled_date == date.today(),
                Task.dimension == dim_enum,
                Task.status == TaskStatusEnum.pending,
            )
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        return {"success": False, "message": "该维度今日无待完成任务"}

    task.status = TaskStatusEnum.completed
    task.completed_at = datetime.now(timezone.utc)

    score_change = await record_task_completion(db, user_id, dim_enum)
    return {
        "success": True,
        "message": f"任务已完成：{task.title}",
        "task_title": task.title,
        "score_change": score_change,
    }


async def skip_task_by_dimension(db: AsyncSession, user_id: str, dimension: str) -> dict:
    """Mark today's pending task for a dimension as failed. Returns result dict."""
    dim_enum = DimensionEnum(dimension)
    result = await db.execute(
        select(Task).where(
            and_(
                Task.user_id == user_id,
                Task.scheduled_date == date.today(),
                Task.dimension == dim_enum,
                Task.status == TaskStatusEnum.pending,
            )
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        return {"success": False, "message": "该维度今日无待完成任务"}

    task.status = TaskStatusEnum.failed

    score_change = await record_negative(db, user_id, dim_enum, f"跳过任务：{task.title}")
    return {
        "success": True,
        "message": f"已跳过任务：{task.title}",
        "task_title": task.title,
        "score_change": score_change,
    }


async def get_today_tasks_dict(db: AsyncSession, user_id: str) -> list[dict]:
    """Get today's tasks as list of dicts for intent detection."""
    result = await db.execute(
        select(Task).where(
            and_(Task.user_id == user_id, Task.scheduled_date == date.today())
        )
    )
    return [
        {"dimension": t.dimension.value, "title": t.title, "status": t.status.value}
        for t in result.scalars().all()
    ]
```

- [ ] **Step 2: 修改 task/router.py 使用 task_service**

将 `backend/app/modules/task/router.py` 中的 `complete_task` 函数改为调用 `task_service`：

```python
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.task import Task, TaskStatusEnum
from app.models.score import DimensionEnum
from app.services.task_service import complete_task_by_dimension

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/today")
async def get_today_tasks(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Task).where(and_(Task.user_id == user.id, Task.scheduled_date == date.today()))
    )
    tasks = result.scalars().all()
    return [
        {
            "id": str(t.id), "dimension": t.dimension.value, "title": t.title,
            "description": t.description, "difficulty": t.difficulty.value,
            "status": t.status.value, "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        }
        for t in tasks
    ]


@router.post("/{task_id}/complete")
async def complete_task(task_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(and_(Task.id == task_id, Task.user_id == user.id)))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status == TaskStatusEnum.completed:
        raise HTTPException(400, "Already completed")

    from datetime import datetime, timezone
    task.status = TaskStatusEnum.completed
    task.completed_at = datetime.now(timezone.utc)

    from app.services.score_service import record_task_completion
    score_change = await record_task_completion(db, user.id, task.dimension)

    return {
        "message": "任务完成",
        "score_change": score_change,
    }


@router.get("")
async def list_tasks(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
                     dimension: str | None = None, status: str | None = None, limit: int = 20):
    query = select(Task).where(Task.user_id == user.id)
    if dimension:
        query = query.where(Task.dimension == dimension)
    if status:
        query = query.where(Task.status == status)
    query = query.order_by(Task.scheduled_date.desc()).limit(limit)

    result = await db.execute(query)
    return [
        {
            "id": str(t.id), "dimension": t.dimension.value, "title": t.title,
            "scheduled_date": t.scheduled_date.isoformat(), "status": t.status.value,
        }
        for t in result.scalars().all()
    ]
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/task_service.py backend/app/modules/task/router.py
git commit -m "feat: extract task completion logic to task_service"
```

---

### Task 3: 提取体重记录逻辑到 weight_service

**Files:**
- Create: `backend/app/services/weight_service.py`
- Modify: `backend/app/modules/weight/router.py`

- [ ] **Step 1: 创建 weight_service.py**

创建 `backend/app/services/weight_service.py`：

```python
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.weight import WeightRecord


async def record_weight(db: AsyncSession, user_id: str, weight_kg: float) -> dict:
    """Record user weight for today. Returns result dict."""
    record = WeightRecord(user_id=user_id, weight_kg=weight_kg, recorded_at=date.today())
    db.add(record)
    return {"message": f"体重已记录：{weight_kg}kg", "weight_kg": weight_kg}
```

- [ ] **Step 2: 修改 weight/router.py 使用 weight_service**

将 `backend/app/modules/weight/router.py` 改为：

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services.weight_service import record_weight as record_weight_service

router = APIRouter(prefix="/api/weight", tags=["weight"])

class WeightRequest(BaseModel):
    weight_kg: float

@router.post("")
async def record_weight(req: WeightRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await record_weight_service(db, str(user.id), req.weight_kg)

@router.get("/history")
async def get_weight_history(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db), limit: int = 30):
    from sqlalchemy import select
    from app.models.weight import WeightRecord
    result = await db.execute(
        select(WeightRecord).where(WeightRecord.user_id == user.id)
        .order_by(WeightRecord.recorded_at.desc()).limit(limit)
    )
    return [
        {"weight_kg": float(w.weight_kg), "recorded_at": w.recorded_at.isoformat()}
        for w in result.scalars().all()
    ]
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/weight_service.py backend/app/modules/weight/router.py
git commit -m "feat: extract weight recording logic to weight_service"
```

---

### Task 4: 修改 send_message 增加意图识别

**Files:**
- Modify: `backend/app/modules/chat/router.py`

- [ ] **Step 1: 替换 send_message 函数**

将 `backend/app/modules/chat/router.py` 中的 `send_message` 函数（第 15-40 行）替换为：

```python
@router.post("/send")
async def send_message(content: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.services.ai_service import detect_intent
    from app.services.task_service import complete_task_by_dimension, skip_task_by_dimension, get_today_tasks_dict
    from app.services.weight_service import record_weight as record_weight_service

    # Save user message
    user_msg = Conversation(user_id=user.id, role=RoleEnum.user, content=content)
    db.add(user_msg)

    # Detect intent
    today_tasks = await get_today_tasks_dict(db, str(user.id))
    intent = await detect_intent(content, today_tasks)

    # Execute intent
    action_context = ""
    if intent["intent"] == "complete_task":
        dim = intent.get("dimension", "")
        result = await complete_task_by_dimension(db, str(user.id), dim)
        if result["success"]:
            action_context = f"[系统操作] {result['message']}"
            if result.get("score_change"):
                action_context += f"，评分变动：{result['score_change']}"
        else:
            action_context = f"[系统提示] {result['message']}"
    elif intent["intent"] == "skip_task":
        dim = intent.get("dimension", "")
        result = await skip_task_by_dimension(db, str(user.id), dim)
        if result["success"]:
            action_context = f"[系统操作] {result['message']}"
        else:
            action_context = f"[系统提示] {result['message']}"
    elif intent["intent"] == "record_weight":
        weight_kg = intent.get("weight_kg")
        if weight_kg and isinstance(weight_kg, (int, float)) and 20 < weight_kg < 300:
            result = await record_weight_service(db, str(user.id), float(weight_kg))
            action_context = f"[系统操作] {result['message']}"
        else:
            action_context = "[系统提示] 未能识别有效的体重数据"

    # Get recent history for context (last 10 messages)
    result = await db.execute(
        select(Conversation).where(Conversation.user_id == user.id)
        .order_by(Conversation.created_at.desc()).limit(10)
    )
    history = list(reversed(result.scalars().all()))
    messages = [{"role": h.role.value, "content": h.content} for h in history]
    messages.append({"role": "user", "content": content})

    # Build user context with action result
    user_context = f"用户昵称：{user.nickname}"
    if action_context:
        user_context += f"\n{action_context}"

    # AI reply
    ai_reply = await chat_completion(messages, user_context)

    # Save AI reply
    sys_msg = Conversation(user_id=user.id, role=RoleEnum.system, content=ai_reply)
    db.add(sys_msg)

    return {"reply": ai_reply}
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/modules/chat/router.py
git commit -m "feat: add intent detection to chat send_message"
```

---

### Task 5: 修改 stream_message 增加意图识别

**Files:**
- Modify: `backend/app/modules/chat/router.py`

- [ ] **Step 1: 替换 stream_message 函数**

将 `backend/app/modules/chat/router.py` 中的 `stream_message` 函数（第 43-77 行）替换为：

```python
@router.post("/stream")
async def stream_message(content: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Stream AI reply via Server-Sent Events."""
    from app.services.ai_service import detect_intent
    from app.services.task_service import complete_task_by_dimension, skip_task_by_dimension, get_today_tasks_dict
    from app.services.weight_service import record_weight as record_weight_service

    user_id = str(user.id)
    nickname = user.nickname

    # Save user message first
    user_msg = Conversation(user_id=user.id, role=RoleEnum.user, content=content)
    db.add(user_msg)
    await db.flush()

    # Detect intent
    today_tasks = await get_today_tasks_dict(db, user_id)
    intent = await detect_intent(content, today_tasks)

    # Execute intent
    action_context = ""
    if intent["intent"] == "complete_task":
        dim = intent.get("dimension", "")
        result = await complete_task_by_dimension(db, user_id, dim)
        if result["success"]:
            action_context = f"[系统操作] {result['message']}"
            if result.get("score_change"):
                action_context += f"，评分变动：{result['score_change']}"
        else:
            action_context = f"[系统提示] {result['message']}"
    elif intent["intent"] == "skip_task":
        dim = intent.get("dimension", "")
        result = await skip_task_by_dimension(db, user_id, dim)
        if result["success"]:
            action_context = f"[系统操作] {result['message']}"
        else:
            action_context = f"[系统提示] {result['message']}"
    elif intent["intent"] == "record_weight":
        weight_kg = intent.get("weight_kg")
        if weight_kg and isinstance(weight_kg, (int, float)) and 20 < weight_kg < 300:
            result = await record_weight_service(db, user_id, float(weight_kg))
            action_context = f"[系统操作] {result['message']}"
        else:
            action_context = "[系统提示] 未能识别有效的体重数据"

    # Get recent history
    result = await db.execute(
        select(Conversation).where(Conversation.user_id == user.id)
        .order_by(Conversation.created_at.desc()).limit(10)
    )
    history = list(reversed(result.scalars().all()))
    messages = [{"role": h.role.value, "content": h.content} for h in history]
    messages.append({"role": "user", "content": content})

    user_context = f"用户昵称：{nickname}"
    if action_context:
        user_context += f"\n{action_context}"

    async def event_generator():
        full_reply = []
        async for chunk in chat_completion_stream(messages, user_context):
            full_reply.append(chunk)
            yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"

        # Save the complete AI reply in a fresh session
        async with async_session() as session:
            session.add(Conversation(user_id=user_id, role=RoleEnum.system, content="".join(full_reply)))
            await session.commit()

        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/modules/chat/router.py
git commit -m "feat: add intent detection to chat stream_message"
```

---

### Task 6: 语法检查与验证

- [ ] **Step 1: 语法检查所有修改的文件**

```bash
py -c "import py_compile; py_compile.compile('backend/app/services/ai_service.py', doraise=True); print('ai_service.py: OK')"
py -c "import py_compile; py_compile.compile('backend/app/services/task_service.py', doraise=True); print('task_service.py: OK')"
py -c "import py_compile; py_compile.compile('backend/app/services/weight_service.py', doraise=True); print('weight_service.py: OK')"
py -c "import py_compile; py_compile.compile('backend/app/modules/chat/router.py', doraise=True); print('chat/router.py: OK')"
py -c "import py_compile; py_compile.compile('backend/app/modules/task/router.py', doraise=True); print('task/router.py: OK')"
py -c "import py_compile; py_compile.compile('backend/app/modules/weight/router.py', doraise=True); print('weight/router.py: OK')"
```

- [ ] **Step 2: Final commit**

```bash
git add -A
git commit -m "feat: complete chat task intent detection feature"
```

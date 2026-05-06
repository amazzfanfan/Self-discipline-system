import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db, async_session
from app.core.deps import get_current_user
from app.models.user import User
from app.models.conversation import Conversation, RoleEnum
from app.services.ai_service import chat_completion, chat_completion_stream

router = APIRouter(prefix="/api/chat", tags=["chat"])


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
    valid_dims = {"exercise", "diet", "sleep", "appearance"}
    if intent["intent"] == "complete_task":
        dim = intent.get("dimension", "")
        if dim not in valid_dims:
            action_context = "[系统提示] 无法识别任务维度"
        else:
            try:
                result = await complete_task_by_dimension(db, str(user.id), dim)
                if result["success"]:
                    action_context = f"[系统操作] {result['message']}"
                    if result.get("score_change"):
                        action_context += f"，评分变动：{result['score_change']}"
                else:
                    action_context = f"[系统提示] {result['message']}"
            except Exception as e:
                action_context = f"[系统提示] 任务操作失败: {e}"
    elif intent["intent"] == "skip_task":
        dim = intent.get("dimension", "")
        if dim not in valid_dims:
            action_context = "[系统提示] 无法识别任务维度"
        else:
            try:
                result = await skip_task_by_dimension(db, str(user.id), dim)
                if result["success"]:
                    action_context = f"[系统操作] {result['message']}"
                else:
                    action_context = f"[系统提示] {result['message']}"
            except Exception as e:
                action_context = f"[系统提示] 任务操作失败: {e}"
    elif intent["intent"] == "record_weight":
        weight_kg = intent.get("weight_kg")
        if weight_kg and isinstance(weight_kg, (int, float)) and 20 < weight_kg < 300:
            result = await record_weight_service(db, str(user.id), float(weight_kg))
            action_context = f"[系统操作] {result['message']}"
        else:
            action_context = "[系统提示] 未能识别有效的体重数据"

    # Commit intent execution results to database
    if action_context:
        await db.commit()

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
    valid_dims = {"exercise", "diet", "sleep", "appearance"}
    if intent["intent"] == "complete_task":
        dim = intent.get("dimension", "")
        if dim not in valid_dims:
            action_context = "[系统提示] 无法识别任务维度"
        else:
            try:
                result = await complete_task_by_dimension(db, user_id, dim)
                if result["success"]:
                    action_context = f"[系统操作] {result['message']}"
                    if result.get("score_change"):
                        action_context += f"，评分变动：{result['score_change']}"
                else:
                    action_context = f"[系统提示] {result['message']}"
            except Exception as e:
                action_context = f"[系统提示] 任务操作失败: {e}"
    elif intent["intent"] == "skip_task":
        dim = intent.get("dimension", "")
        if dim not in valid_dims:
            action_context = "[系统提示] 无法识别任务维度"
        else:
            try:
                result = await skip_task_by_dimension(db, user_id, dim)
                if result["success"]:
                    action_context = f"[系统操作] {result['message']}"
                else:
                    action_context = f"[系统提示] {result['message']}"
            except Exception as e:
                action_context = f"[系统提示] 任务操作失败: {e}"
    elif intent["intent"] == "record_weight":
        weight_kg = intent.get("weight_kg")
        if weight_kg and isinstance(weight_kg, (int, float)) and 20 < weight_kg < 300:
            try:
                result = await record_weight_service(db, user_id, float(weight_kg))
                action_context = f"[系统操作] {result['message']}"
            except Exception as e:
                action_context = f"[系统提示] 体重记录失败: {e}"
        else:
            action_context = "[系统提示] 未能识别有效的体重数据"

    # Commit intent execution results to database
    if action_context:
        await db.commit()

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


@router.get("/history")
async def get_history(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db), limit: int = 50):
    result = await db.execute(
        select(Conversation).where(Conversation.user_id == user.id)
        .order_by(Conversation.created_at.desc()).limit(limit)
    )
    messages = list(reversed(result.scalars().all()))
    return [
        {"id": str(m.id), "role": m.role.value, "content": m.content, "created_at": m.created_at.isoformat()}
        for m in messages
    ]

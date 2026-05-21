"""
Chat Router - 聊天路由（完整版）
集成上下文构建器、记忆服务和用户画像服务
"""

import json
import logging
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db, async_session
from app.core.deps import get_current_user
from app.models.user import User
from app.models.conversation import Conversation, RoleEnum
from app.services.llm_service import chat_completion_with_fallback as ai_chat_completion, chat_completion_stream as ai_chat_completion_stream  # noqa: E501
from app.services.context_builder import ContextBuilder
from app.services.memory_service import MemoryService
from app.services.profile_service import ProfileService
from app.services.goal_service import goal_service

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = logging.getLogger(__name__)


@router.post("/send")
async def send_message(
    content: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """发送消息并获取 AI 回复"""
    from app.services.ai_service import detect_intent
    from app.services.task_service import complete_task_by_dimension, skip_task_by_dimension, get_today_tasks_dict
    from app.services.weight_service import record_weight as record_weight_service
    from app.services.cache_service import invalidate_tasks, invalidate_scores
    user_msg = Conversation(user_id=user.id, role=RoleEnum.user, content=content)
    db.add(user_msg)
    await db.flush()

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
                    await invalidate_tasks(str(user.id))
                    await invalidate_scores(str(user.id))
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
                    await invalidate_tasks(str(user.id))
                    await invalidate_scores(str(user.id))
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

    # 使用上下文构建器构建消息
    context_builder = ContextBuilder(db, user)
    messages = await context_builder.build_context_with_action(
        user_message=content,
        action_context=action_context,
        include_recent=True,
        include_relevant=True
    )

    # AI reply
    try:
        ai_reply = await ai_chat_completion(messages)
    except Exception as e:
        logger.error(f"AI 调用失败: {e}")
        ai_reply = "当前 AI 不可用，请稍后再试。"

    # 如果 AI 返回空内容，使用默认回复
    if not ai_reply or not ai_reply.strip():
        ai_reply = "当前 AI 不可用，请稍后再试。"

    # Save AI reply
    sys_msg = Conversation(user_id=user.id, role=RoleEnum.system, content=ai_reply)
    db.add(sys_msg)
    await db.commit()

    # 自动存储记忆
    memory_service = MemoryService(db)
    await memory_service.auto_store_conversation(
        user_id=str(user.id),
        content=content,
        role="user",
        source_id=str(user_msg.id)
    )
    await memory_service.auto_store_conversation(
        user_id=str(user.id),
        content=ai_reply,
        role="system",
        source_id=str(sys_msg.id)
    )

    # 更新用户画像
    profile_service = ProfileService(db)
    await profile_service.extract_and_update_profile(str(user.id), content)

    # 自动提取目标
    try:
        await goal_service.extract_goal_from_message(db, str(user.id), content)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[目标提取] 失败: {e}")

    return {"reply": ai_reply}


@router.post("/stream")
async def stream_message(
    content: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """流式获取 AI 回复"""
    from app.services.ai_service import detect_intent
    from app.services.task_service import complete_task_by_dimension, skip_task_by_dimension, get_today_tasks_dict
    from app.services.weight_service import record_weight as record_weight_service
    from app.services.cache_service import invalidate_tasks, invalidate_scores

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
                    await invalidate_tasks(user_id)
                    await invalidate_scores(user_id)
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
                    await invalidate_tasks(user_id)
                    await invalidate_scores(user_id)
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

    # 使用上下文构建器构建消息
    context_builder = ContextBuilder(db, user)
    messages = await context_builder.build_context_with_action(
        user_message=content,
        action_context=action_context,
        include_recent=True,
        include_relevant=True
    )

    async def event_generator():
        full_reply = []
        try:
            async for chunk in ai_chat_completion_stream(messages):
                full_reply.append(chunk)
                yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"AI 流式调用失败: {e}")
            if not full_reply:
                error_reply = "当前 AI 不可用，请稍后再试。"
                full_reply.append(error_reply)
                yield f"data: {json.dumps({'content': error_reply}, ensure_ascii=False)}\n\n"

        # 如果 AI 返回空内容，使用默认回复
        if not full_reply:
            default_reply = "当前 AI 不可用，请稍后再试。"
            full_reply.append(default_reply)
            yield f"data: {json.dumps({'content': default_reply}, ensure_ascii=False)}\n\n"

        # Save the complete AI reply in a fresh session
        try:
            async with async_session() as session:
                # 保存 AI 回复
                sys_msg = Conversation(user_id=user_id, role=RoleEnum.system, content="".join(full_reply))
                session.add(sys_msg)
                await session.commit()
                
                # 存储记忆
                memory_service = MemoryService(session)
                await memory_service.auto_store_conversation(
                    user_id=user_id,
                    content=content,
                    role="user",
                    source_id=str(user_msg.id)
                )
                await memory_service.auto_store_conversation(
                    user_id=user_id,
                    content="".join(full_reply),
                    role="system",
                    source_id=str(sys_msg.id)
                )
                
                # 更新用户画像
                profile_service = ProfileService(session)
                await profile_service.extract_and_update_profile(user_id, content)

                # 自动提取目标
                try:
                    await goal_service.extract_goal_from_message(session, user_id, content)
                except Exception as e:
                    print(f"[目标提取] 失败: {e}")
        except Exception as e:
            # 记录错误但不影响响应
            print(f"[聊天] 后处理错误: {e}")

        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/history")
async def get_history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50
):
    """获取聊天历史"""
    result = await db.execute(
        select(Conversation).where(Conversation.user_id == user.id)
        .order_by(Conversation.created_at.desc()).limit(limit)
    )
    messages = list(reversed(result.scalars().all()))
    return [
        {
            "id": str(m.id),
            "role": m.role.value,
            "content": m.content,
            "created_at": m.created_at.isoformat()
        }
        for m in messages
    ]


@router.get("/memories")
async def get_memories(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 20,
    memory_type: str = None
):
    """获取用户记忆"""
    memory_service = MemoryService(db)
    memories = await memory_service.get_recent_memories(
        user_id=str(user.id),
        limit=limit,
        memory_type=memory_type
    )
    return memories


@router.get("/memories/search")
async def search_memories(
    query: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    top_k: int = 5
):
    """搜索相关记忆"""
    memory_service = MemoryService(db)
    memories = await memory_service.search_similar_memories(
        user_id=str(user.id),
        query=query,
        top_k=top_k
    )
    return memories


@router.get("/memories/stats")
async def get_memory_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取记忆统计信息"""
    memory_service = MemoryService(db)
    stats = await memory_service.get_memory_stats(str(user.id))
    return stats


@router.get("/profile")
async def get_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取用户画像"""
    profile_service = ProfileService(db)
    summary = await profile_service.get_user_summary(str(user.id))
    return {"summary": summary}

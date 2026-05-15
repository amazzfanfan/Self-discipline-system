"""
Context Builder - 智能上下文构建器
负责组装发送给 LLM 的上下文，包括系统提示、用户画像、相关记忆、最近对话等
"""

from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.conversation import Conversation
from app.models.user import User
from app.services.memory_service import MemoryService
import logging

try:
    from app.services.goal_service import goal_service
except ImportError:
    goal_service = None

logger = logging.getLogger(__name__)

BJT = timezone(timedelta(hours=8))


class ContextBuilder:
    """智能上下文构建器"""
    
    def __init__(self, db: AsyncSession, user: User):
        self.db = db
        self.user = user
        self.memory_service = MemoryService(db)
    
    async def build_system_prompt(self) -> str:
        """
        构建系统提示
        
        Returns:
            系统提示文本
        """
        now = datetime.now(BJT)
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        time_str = now.strftime(f"%Y年%m月%d日 %H:%M {weekdays[now.weekday()]}")
        
        # 基础提示
        base_prompt = f"""你是一个名为"系统"的AI助手，灵感来源于小说中的成长系统。你的职责是帮助用户提升自己。

核心原则：
- 用数据说话，用鼓励驱动
- 关注趋势，单次失败不代表失败
- 主动关怀，检测到异常时主动询问
- 保持人设，始终以"系统"身份对话
- 绝对不要输出你的思考过程、推理步骤或内心独白，只输出面向用户的回复内容

当前时间（北京时间）：{time_str}
用户信息：{self.user.nickname}
"""
        
        # 添加用户画像（事实性记忆）
        user_facts = await self.memory_service.get_user_facts(str(self.user.id))
        if user_facts:
            base_prompt += f"\n用户偏好和习惯：\n"
            for fact in user_facts:
                base_prompt += f"- {fact}\n"
        
        return base_prompt
    
    async def build_context(
        self,
        user_message: str,
        include_recent: bool = True,
        include_relevant: bool = True,
        recent_limit: int = 5,
        relevant_limit: int = 3
    ) -> list[dict]:
        """
        构建完整的对话上下文
        
        Args:
            user_message: 用户当前消息
            include_recent: 是否包含最近对话
            include_relevant: 是否包含相关记忆
            recent_limit: 最近对话数量限制
            relevant_limit: 相关记忆数量限制
        
        Returns:
            消息列表，可直接发送给 LLM
        """
        context = []
        
        # 1. 系统提示（固定）
        system_prompt = await self.build_system_prompt()
        context.append({"role": "system", "content": system_prompt})
        logger.info(f"System prompt built")
        
        # 2. 相关历史（关键词搜索）
        if include_relevant:
            try:
                relevant_memories = await self.memory_service.search_similar_memories(
                    user_id=str(self.user.id),
                    query=user_message,
                    top_k=relevant_limit,
                    memory_type="conversation"
                )
                
                if relevant_memories:
                    relevant_text = "相关历史对话：\n"
                    for mem in relevant_memories:
                        relevant_text += f"- {mem['content']}\n"
                    
                    context.append({"role": "system", "content": relevant_text})
                    logger.info(f"Relevant memories: {len(relevant_memories)} items")
            except Exception as e:
                logger.warning(f"Failed to get relevant memories: {e}")
        
        # 3. 最近对话（按时间）
        if include_recent:
            try:
                recent_messages = await self._get_recent_messages(limit=recent_limit)
                context.extend(recent_messages)
                logger.info(f"Recent messages: {len(recent_messages)} items")
            except Exception as e:
                logger.warning(f"Failed to get recent messages: {e}")
        
        # 4. 当前用户输入
        context.append({"role": "user", "content": user_message})
        
        logger.info(f"Built context with {len(context)} messages")
        return context
    
    async def _get_recent_messages(self, limit: int = 5) -> list[dict]:
        """
        获取最近的对话消息
        
        Args:
            limit: 消息数量限制
        
        Returns:
            消息列表
        """
        result = await self.db.execute(
            select(Conversation)
            .where(Conversation.user_id == self.user.id)
            .order_by(Conversation.created_at.desc())
            .limit(limit)
        )
        messages = list(reversed(result.scalars().all()))
        
        return [
            {
                "role": msg.role.value,
                "content": msg.content
            }
            for msg in messages
        ]
    
    async def build_context_with_action(
        self,
        user_message: str,
        action_context: str = "",
        include_recent: bool = True,
        include_relevant: bool = True
    ) -> list[dict]:
        """
        构建带有动作上下文的对话上下文
        
        Args:
            user_message: 用户当前消息
            action_context: 动作上下文（如任务完成、体重记录等）
            include_recent: 是否包含最近对话
            include_relevant: 是否包含相关记忆
        
        Returns:
            消息列表
        """
        context = []
        
        # 1. 系统提示
        system_prompt = await self.build_system_prompt()
        if action_context:
            system_prompt += f"\n{action_context}"
        context.append({"role": "system", "content": system_prompt})
        
        # 2. 相关记忆
        if include_relevant:
            try:
                relevant_memories = await self.memory_service.search_similar_memories(
                    user_id=str(self.user.id),
                    query=user_message,
                    top_k=3
                )
                if relevant_memories:
                    relevant_text = "相关历史：\n"
                    for mem in relevant_memories:
                        relevant_text += f"- {mem['content']}\n"
                    context.append({"role": "system", "content": relevant_text})
            except Exception as e:
                logger.warning(f"Failed to get relevant memories: {e}")
        
        # 3. 相关目标
        if goal_service is not None:
            try:
                relevant_goals = await goal_service.search_goals(
                    user_id=str(self.user.id),
                    query=user_message,
                    top_k=3
                )
                if relevant_goals:
                    goals_text = "相关目标：\n"
                    for goal in relevant_goals:
                        goals_text += f"- {goal}\n"
                    context.append({"role": "system", "content": goals_text})
                    logger.info(f"Relevant goals: {len(relevant_goals)} items")
            except Exception as e:
                logger.warning(f"Failed to get relevant goals: {e}")
        
        # 4. 最近对话
        if include_recent:
            try:
                recent_messages = await self._get_recent_messages(limit=5)
                context.extend(recent_messages)
            except Exception as e:
                logger.warning(f"Failed to get recent messages: {e}")
        
        # 5. 当前用户输入
        context.append({"role": "user", "content": user_message})
        
        return context

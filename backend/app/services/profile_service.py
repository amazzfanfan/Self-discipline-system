"""
Profile Service - 用户画像服务
管理用户的偏好、习惯、目标等画像信息
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import User
from app.services.memory_service import MemoryService
from typing import Optional
import logging
import json

logger = logging.getLogger(__name__)


class ProfileService:
    """用户画像服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.memory_service = MemoryService(db)
    
    async def update_preferences(self, user_id: str, preferences: dict):
        """
        更新用户偏好
        
        Args:
            user_id: 用户 ID
            preferences: 偏好字典
        """
        user = await self.db.get(User, user_id)
        if user:
            current = user.preferences or {}
            current.update(preferences)
            user.preferences = current
            await self.db.commit()
            logger.info(f"Updated preferences for user {user_id}: {preferences}")
    
    async def get_preferences(self, user_id: str) -> dict:
        """
        获取用户偏好
        
        Args:
            user_id: 用户 ID
        
        Returns:
            偏好字典
        """
        user = await self.db.get(User, user_id)
        return user.preferences if user else {}
    
    async def add_habit(self, user_id: str, habit: str):
        """
        添加用户习惯
        
        Args:
            user_id: 用户 ID
            habit: 习惯描述
        """
        user = await self.db.get(User, user_id)
        if user:
            habits = user.habits or []
            if habit not in habits:
                habits.append(habit)
                user.habits = habits
                await self.db.commit()
                logger.info(f"Added habit for user {user_id}: {habit}")
    
    async def get_habits(self, user_id: str) -> list[str]:
        """
        获取用户习惯列表
        
        Args:
            user_id: 用户 ID
        
        Returns:
            习惯列表
        """
        user = await self.db.get(User, user_id)
        return user.habits if user else []
    
    async def add_goal(self, user_id: str, goal: str):
        """
        添加用户目标
        
        Args:
            user_id: 用户 ID
            goal: 目标描述
        """
        user = await self.db.get(User, user_id)
        if user:
            goals = user.goals or []
            if goal not in goals:
                goals.append(goal)
                user.goals = goals
                await self.db.commit()
                logger.info(f"Added goal for user {user_id}: {goal}")
    
    async def get_goals(self, user_id: str) -> list[str]:
        """
        获取用户目标列表
        
        Args:
            user_id: 用户 ID
        
        Returns:
            目标列表
        """
        user = await self.db.get(User, user_id)
        return user.goals if user else []
    
    async def extract_and_update_profile(self, user_id: str, message: str):
        """
        从对话中提取并更新用户画像
        
        Args:
            user_id: 用户 ID
            message: 对话内容
        """
        # 关键词分类
        categories = {
            "偏好": ["喜欢", "讨厌", "偏好", "最爱", "最讨厌"],
            "习惯": ["习惯", "经常", "每天", "总是", "从不"],
            "目标": ["目标", "计划", "打算", "想要", "希望"],
            "健康": ["体重", "睡眠", "运动", "饮食", "健康"],
            "情感": ["难过", "开心", "焦虑", "压力", "心情"],
        }
        
        for category, keywords in categories.items():
            if any(kw in message for kw in keywords):
                # 存储到记忆系统
                await self.memory_service.store_memory(
                    user_id=user_id,
                    content=message,
                    role="user",
                    memory_type="fact",
                    importance_score=0.8
                )
                logger.info(f"Extracted {category} from user {user_id}: {message[:50]}...")
                break
    
    async def get_user_summary(self, user_id: str) -> str:
        """
        获取用户画像摘要
        
        Args:
            user_id: 用户 ID
        
        Returns:
            用户画像摘要文本
        """
        user = await self.db.get(User, user_id)
        if not user:
            return "用户信息未知"
        
        summary_parts = []
        
        # 基本信息
        summary_parts.append(f"昵称：{user.nickname}")
        
        # 获取用户档案
        profile = user.profile
        if profile:
            if profile.age:
                summary_parts.append(f"年龄：{profile.age}岁")
            if profile.gender:
                summary_parts.append(f"性别：{'男' if profile.gender == 'male' else '女'}")
            if profile.height_cm:
                summary_parts.append(f"身高：{profile.height_cm}cm")
            if profile.weight_kg:
                summary_parts.append(f"体重：{profile.weight_kg}kg")
        
        # 事实性记忆
        facts = await self.memory_service.get_user_facts(user_id, limit=5)
        if facts:
            facts_str = "；".join(facts[:3])  # 最多显示 3 个
            summary_parts.append(f"历史记录：{facts_str}")
        
        return "\n".join(summary_parts)
    
    async def update_personality_traits(self, user_id: str, traits: dict):
        """
        更新用户性格特征
        
        Args:
            user_id: 用户 ID
            traits: 性格特征字典
        """
        user = await self.db.get(User, user_id)
        if user:
            current = user.personality_traits or {}
            current.update(traits)
            user.personality_traits = current
            await self.db.commit()
            logger.info(f"Updated personality traits for user {user_id}: {traits}")
    
    async def get_personality_traits(self, user_id: str) -> dict:
        """
        获取用户性格特征
        
        Args:
            user_id: 用户 ID
        
        Returns:
            性格特征字典
        """
        user = await self.db.get(User, user_id)
        return user.personality_traits if user else {}

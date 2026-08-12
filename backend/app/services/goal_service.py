"""
Goal Service - 目标管理服务
提供目标的创建、更新、删除、搜索功能
支持向量嵌入的语义搜索，关键词搜索作为降级方案
"""

from datetime import date, datetime, time, timezone
from sqlalchemy import select, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.goal import Goal, GoalStatus, GoalSource
from typing import Optional
import logging
import re
import traceback
from app.services.llm_service import get_embedding
from app.services.cache_service import enqueue_background_job
from app.core.config import get_settings
from app.services.goal_schedule_service import parse_goal_schedule

logger = logging.getLogger(__name__)
settings = get_settings()


class GoalService:
    """目标管理服务 - 支持向量语义搜索"""

    def __init__(self):
        pass

    async def create_goal(
        self,
        db: AsyncSession,
        user_id: str,
        content: str,
        goal_type: str = "exercise",
        structured_data: dict = None,
        target_metric: str | None = None,
        target_value: float | None = None,
        current_value: float | None = None,
        deadline: date | None = None,
        milestones: list[dict] | None = None,
        recurrence: str | None = None,
        days_of_week: list[int] | None = None,
        preferred_time: time | None = None,
        duration_minutes: int | None = None,
        start_date: date | None = None,
        reminder_enabled: bool | None = None,
        reminder_minutes_before: int = 30,
        source: str = "manual",
    ) -> Goal:
        """
        创建目标

        Args:
            db: 数据库会话
            user_id: 用户 ID
            content: 目标内容
            goal_type: 目标类型 (exercise/diet/sleep/appearance)
            structured_data: 结构化数据 (AI 解析后的结构化数据)
            source: 目标来源 (manual/chat)

        Returns:
            Goal 对象
        """
        try:
            parsed_schedule = parse_goal_schedule(content)
            resolved_time = preferred_time or parsed_schedule.get("preferred_time")
            goal = Goal(
                user_id=user_id,
                content=content,
                goal_type=goal_type,
                structured_data=structured_data,
                target_metric=target_metric,
                target_value=target_value,
                current_value=current_value,
                deadline=deadline,
                milestones=milestones or [],
                recurrence=(
                    recurrence or parsed_schedule.get("recurrence") or "flexible"
                ),
                days_of_week=(
                    days_of_week
                    if days_of_week is not None
                    else parsed_schedule.get("days_of_week", [])
                ),
                preferred_time=resolved_time,
                duration_minutes=(
                    duration_minutes or parsed_schedule.get("duration_minutes")
                ),
                start_date=start_date,
                reminder_enabled=(
                    bool(resolved_time) if reminder_enabled is None else reminder_enabled
                ),
                reminder_minutes_before=reminder_minutes_before,
                embedding=None,
                embedding_model=None,
                source=source,
                status=GoalStatus.active.value,
            )

            db.add(goal)
            await db.commit()

            await enqueue_background_job(
                "refresh_goal_tasks",
                {"goal_id": str(goal.id), "user_id": str(user_id)},
            )
            queued = await enqueue_background_job(
                "index_goal",
                {"goal_id": str(goal.id), "user_id": str(user_id)},
            )
            if not queued:
                logger.warning("Goal %s saved without deferred embedding; keyword search remains available", goal.id)

            logger.info(f"Created goal for user {user_id}: {content[:50]}...")
            return goal

        except Exception as e:
            logger.error(f"Failed to create goal: {e}")
            await db.rollback()
            raise

    async def update_goal(
        self,
        db: AsyncSession,
        goal_id: str,
        user_id: str,
        updates: dict,
    ) -> Optional[Goal]:
        """
        更新目标

        Args:
            db: 数据库会话
            goal_id: 目标 ID
            user_id: 用户 ID (用于权限验证)
            updates: 更新字段字典

        Returns:
            更新后的 Goal 对象，如果目标不存在则返回 None
        """
        try:
            result = await db.execute(
                select(Goal)
                .where(Goal.id == goal_id)
                .where(Goal.user_id == user_id)
            )
            goal = result.scalar_one_or_none()

            if not goal:
                logger.warning(f"Goal {goal_id} not found for user {user_id}")
                return None

            if updates.get("content") and updates["content"] != goal.content:
                parsed_schedule = parse_goal_schedule(updates["content"])
                for key, value in parsed_schedule.items():
                    updates.setdefault(key, value)
                if "preferred_time" in parsed_schedule:
                    updates.setdefault("reminder_enabled", True)

            # 更新字段
            content_changed = False
            planning_changed = bool(
                set(updates)
                & {
                    "content",
                    "goal_type",
                    "status",
                    "recurrence",
                    "days_of_week",
                    "preferred_time",
                    "duration_minutes",
                    "start_date",
                    "deadline",
                }
            )
            for key, value in updates.items():
                if hasattr(goal, key):
                    if key == "content" and value != goal.content:
                        content_changed = True
                    setattr(goal, key, value)

            # 内容变化时先完成业务写入，向量在本地 Redis worker 中异步更新，
            # 避免一次远程 embedding 调用阻塞用户对话。
            if content_changed and goal.content:
                goal.embedding = None
                goal.embedding_model = None

            goal.updated_at = datetime.now(timezone.utc)
            await db.commit()

            if planning_changed:
                await enqueue_background_job(
                    "refresh_goal_tasks",
                    {"goal_id": str(goal.id), "user_id": str(user_id)},
                )
            if content_changed:
                queued = await enqueue_background_job(
                    "index_goal",
                    {"goal_id": str(goal.id), "user_id": str(user_id)},
                )
                if not queued:
                    logger.warning("Updated goal %s remains available through keyword search", goal.id)

            logger.info(f"Updated goal {goal_id}")
            return goal

        except Exception as e:
            logger.error(f"Failed to update goal {goal_id}: {e}")
            await db.rollback()
            raise

    async def index_goal_embedding(
        self,
        db: AsyncSession,
        goal_id: str,
        user_id: str,
    ) -> bool:
        """Populate a goal vector from the remote embedding API in the background."""
        result = await db.execute(
            select(Goal)
            .where(Goal.id == goal_id)
            .where(Goal.user_id == user_id)
        )
        goal = result.scalar_one_or_none()
        if not goal:
            return False
        embedding = await get_embedding(goal.content)
        goal.embedding = embedding
        goal.embedding_model = settings.EMBEDDING_MODEL
        await db.commit()
        logger.info("Indexed goal embedding: %s", goal_id)
        return True

    async def delete_goal(
        self,
        db: AsyncSession,
        goal_id: str,
        user_id: str,
    ) -> bool:
        """
        删除目标

        Args:
            db: 数据库会话
            goal_id: 目标 ID
            user_id: 用户 ID (用于权限验证)

        Returns:
            是否删除成功
        """
        try:
            result = await db.execute(
                select(Goal)
                .where(Goal.id == goal_id)
                .where(Goal.user_id == user_id)
            )
            goal = result.scalar_one_or_none()

            if goal:
                await db.delete(goal)
                await db.commit()
                await enqueue_background_job(
                    "refresh_goal_tasks",
                    {"goal_id": str(goal_id), "user_id": str(user_id)},
                )
                logger.info(f"Deleted goal {goal_id}")
                return True

            logger.warning(f"Goal {goal_id} not found for user {user_id}")
            return False

        except Exception as e:
            logger.error(f"Failed to delete goal {goal_id}: {e}")
            await db.rollback()
            raise

    async def get_user_goals(
        self,
        db: AsyncSession,
        user_id: str,
        status: str = None,
        goal_type: str = None,
    ) -> list[dict]:
        """
        获取用户的目标列表

        Args:
            db: 数据库会话
            user_id: 用户 ID
            status: 目标状态过滤 (active/completed/paused, 可选)
            goal_type: 目标类型过滤 (exercise/diet/sleep/appearance, 可选)

        Returns:
            目标列表
        """
        try:
            stmt = (
                select(Goal)
                .where(Goal.user_id == user_id)
                .order_by(Goal.created_at.desc())
            )

            if status:
                stmt = stmt.where(Goal.status == status)

            if goal_type:
                stmt = stmt.where(Goal.goal_type == goal_type)

            result = await db.execute(stmt)
            goals = result.scalars().all()

            return [goal.to_dict() for goal in goals]

        except Exception as e:
            logger.error(f"Failed to get goals for user {user_id}: {e}")
            raise

    async def search_goals(
        self,
        db: AsyncSession,
        user_id: str,
        query: str,
        top_k: int = 5,
        status: str = None,
    ) -> list[dict]:
        """
        使用向量相似度搜索相关目标（降级为关键词搜索）

        Args:
            db: 数据库会话
            user_id: 用户 ID
            query: 查询文本
            top_k: 返回结果数量
            status: 目标状态过滤 (可选)

        Returns:
            相关目标列表
        """
        try:
            # 尝试向量相似度搜索
            try:
                query_embedding = await get_embedding(query)
                logger.info(f"Vector search with embedding: dim={len(query_embedding)}")

                # 使用 cosine_distance 排序（距离越小越相似）
                stmt = (
                    select(
                        Goal,
                        text("1 - (goal.embedding <=> :embedding)").label("similarity")
                    )
                    .where(Goal.user_id == user_id)
                    .where(Goal.embedding.isnot(None))
                    .where(Goal.embedding_model == settings.EMBEDDING_MODEL)
                    .params(embedding=query_embedding)
                )

                if status:
                    stmt = stmt.where(Goal.status == status)

                stmt = stmt.order_by(
                    text("goal.embedding <=> :embedding")
                ).params(embedding=query_embedding).limit(top_k)

                result = await db.execute(stmt)
                rows = result.all()

                goals = []
                for row in rows:
                    goal = row[0]
                    similarity = row[1]
                    goal_dict = goal.to_dict()
                    goal_dict["similarity"] = round(float(similarity), 4) if similarity is not None else 0.0
                    goals.append(goal_dict)

                if goals:
                    logger.info(f"Vector search found {len(goals)} goals")
                    return goals

                # 向量搜索无结果，降级为关键词搜索
                logger.info("Vector search returned no results, falling back to keyword search")

            except Exception as e:
                logger.warning(f"Vector search failed, falling back to keyword search: {e}")

            # 降级：关键词搜索
            return await self._keyword_search(db, user_id, query, top_k, status)

        except Exception as e:
            logger.error(f"Failed to search goals: {e}")
            raise

    def _extract_keywords(self, text: str) -> list[str]:
        """
        从文本中提取关键词

        Args:
            text: 输入文本

        Returns:
            关键词列表
        """
        # 移除标点符号和特殊字符
        text = re.sub(r'[^\w\s]', ' ', text)

        # 分词（简单的空格分词）
        words = text.split()

        # 过滤停用词和短词
        stop_words = {
            '的', '了', '是', '在', '我', '你', '他', '她', '它', '们',
            '这', '那', '有', '和', '与', '或', '但', '不', '也', '就',
            '都', '很', '会', '要', '能', '可以', '可能', '应该', '需要',
            '想', '说', '看', '做', '来', '去', '到', '从', '把', '被',
            '让', '给', '对', '向', '往', '以', '因', '为', '所', '如',
            '果', '虽', '然', '而', '且', '或', '者', '一', '二', '三',
            '四', '五', '六', '七', '八', '九', '十', '个', '些', '每',
            '各', '某', '这', '那', '哪', '什', '么', '怎', '样', '多',
            '少', '大', '小', '长', '短', '高', '低', '快', '慢', '好',
            '坏', '新', '旧', '美', '丑', '真', '假', '对', '错', '是', '非'
        }

        keywords = [word for word in words if len(word) >= 2 and word not in stop_words]

        return keywords[:10]  # 最多返回 10 个关键词

    async def _keyword_search(
        self,
        db: AsyncSession,
        user_id: str,
        query: str,
        top_k: int = 5,
        status: str = None,
    ) -> list[dict]:
        """
        关键词搜索（降级方案）

        Args:
            db: 数据库会话
            user_id: 用户 ID
            query: 查询文本
            top_k: 返回结果数量
            status: 目标状态过滤 (可选)

        Returns:
            相关目标列表
        """
        keywords = self._extract_keywords(query)

        if not keywords:
            return await self.get_user_goals(db, user_id, status=status)

        stmt = select(Goal).where(Goal.user_id == user_id)

        conditions = []
        for keyword in keywords[:5]:
            conditions.append(Goal.content.ilike(f"%{keyword}%"))

        if conditions:
            stmt = stmt.where(or_(*conditions))

        if status:
            stmt = stmt.where(Goal.status == status)

        stmt = stmt.order_by(
            Goal.created_at.desc()
        ).limit(top_k)

        result = await db.execute(stmt)
        goals = result.scalars().all()

        logger.info(f"Keyword search found {len(goals)} goals")
        return [goal.to_dict() for goal in goals]

    async def extract_goal_from_message(
        self,
        db: AsyncSession,
        user_id: str,
        message: str,
    ) -> Optional[Goal]:
        """
        从消息中提取目标

        Args:
            db: 数据库会话
            user_id: 用户 ID
            message: 用户消息

        Returns:
            如果检测到目标，返回 Goal 对象；否则返回 None
        """
        try:
            # 目标关键词映射
            goal_keywords = {
                "exercise": [
                    "运动", "锻炼", "健身", "跑步", "游泳", "走路", "散步",
                    "减重", "减肥", "增肌", "塑形", "瘦", "练", "体能",
                ],
                "diet": [
                    "饮食", "吃", "食物", "餐", "热量", "卡路里", "营养",
                    "少吃", "多吃", "控制饮食", "减肥餐", "食谱",
                ],
                "sleep": [
                    "睡眠", "睡觉", "作息", "早睡", "早起", "熬夜", "失眠",
                    "休息", "午睡", "睡眠质量",
                ],
                "appearance": [
                    "外貌", "颜值", "皮肤", "发型", "化妆", "护肤",
                    "美白", "防晒", "保养", "美容",
                ],
            }

            # 目标意图关键词
            intent_keywords = [
                "目标", "计划", "打算", "准备", "想要", "想要",
                "希望", "决心", "开始", "坚持", "养成", "习惯",
                "每天", "每周", "坚持", "一个月", "三个月", "半年",
            ]

            # 检测是否包含目标意图
            has_intent = any(kw in message for kw in intent_keywords)

            if not has_intent:
                logger.debug(f"No goal intent detected in message: {message[:50]}...")
                return None

            # 检测目标类型
            detected_type = None
            max_match_count = 0

            for goal_type, keywords in goal_keywords.items():
                match_count = sum(1 for kw in keywords if kw in message)
                if match_count > max_match_count:
                    max_match_count = match_count
                    detected_type = goal_type

            if not detected_type:
                # 默认使用 exercise 类型
                detected_type = "exercise"
                logger.info(f"No specific goal type detected, defaulting to {detected_type}")

            # 创建目标
            goal = await self.create_goal(
                db=db,
                user_id=user_id,
                content=message,
                goal_type=detected_type,
                source=GoalSource.chat.value,
            )

            logger.info(f"Extracted goal from message for user {user_id}: type={detected_type}")
            return goal

        except Exception as e:
            logger.error(f"Failed to extract goal from message: {e}")
            logger.error(traceback.format_exc())
            return None


# 全局实例，供其他模块导入使用
goal_service = GoalService()

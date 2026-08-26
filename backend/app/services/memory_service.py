"""
Memory Service - 记忆管理服务
提供记忆的存储、检索、管理功能
支持向量嵌入的语义搜索，关键词搜索作为降级方案
"""

from datetime import datetime, timezone
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.memory import Memory
from app.models.user import UserProfile
import logging
import re
from app.services.llm_service import get_embedding
from app.services.memory_judge import HybridMemoryJudge
from app.services.memory_scorer import MemoryImportanceScorer
from app.services.memory_decay import MemoryDecay
from app.services.cache_service import (
    get_cached_memory_search,
    invalidate_memory_search,
    set_cached_memory_search,
)
from app.core.config import get_settings
from app.services.llm_service import LLMChatAdapter

logger = logging.getLogger(__name__)
settings = get_settings()


class MemoryService:
    """记忆管理服务 - 支持向量语义搜索"""
    
    def __init__(self, db: AsyncSession, llm_client=None):
        self.db = db
        if llm_client is None and settings.AI_API_KEY:
            llm_client = LLMChatAdapter()
        self.importance_scorer = MemoryImportanceScorer()
        self.memory_decay = MemoryDecay()
        self.judge = HybridMemoryJudge(
            llm_client=llm_client,
            importance_scorer=self.importance_scorer,
            memory_decay=self.memory_decay)
    
    def _get_effective_importance(self, memory: Memory) -> float:
        """计算记忆经过衰减后的有效重要性评分
        
        衰减规则：
        - 距上次访问越久，重要性越低
        - 访问次数越多，衰减越慢
        - 最低不会低于 MIN_IMPORTANCE (0.01)
        
        Args:
            memory: Memory ORM 对象
            
        Returns:
            衰减后的重要性评分 (0.01 ~ 1.0)
        """
        return self.memory_decay.calculate_importance(
            original_importance=float(memory.importance_score),
            created_at=memory.created_at,
            last_accessed=memory.last_accessed,
            access_count=memory.access_count or 0,
        )
    
    async def store_memory(
        self,
        user_id: str,
        content: str,
        role: str,
        memory_type: str = "conversation",
        importance_score: float = 0.5,
        source_id: str = None
    ) -> Memory:
        """
        存储记忆
        
        Args:
            user_id: 用户 ID
            content: 记忆内容
            role: 角色（user/system）
            memory_type: 记忆类型（conversation/preference/fact）
            importance_score: 重要性评分（0-1）
            source_id: 来源 ID（如对话 ID）
        
        Returns:
            Memory 对象
        """
        try:
            # Exact duplicates add noise and retrieval bias. Merge them instead.
            existing_result = await self.db.execute(
                select(Memory).where(
                    Memory.user_id == user_id,
                    Memory.content == content,
                    Memory.role == role,
                ).limit(1)
            )
            existing = existing_result.scalar_one_or_none()
            if existing:
                existing.importance_score = max(
                    float(existing.importance_score or 0), importance_score
                )
                if (
                    existing.embedding is None
                    or existing.embedding_model != settings.EMBEDDING_MODEL
                ):
                    try:
                        existing.embedding = await get_embedding(content)
                        existing.embedding_model = settings.EMBEDDING_MODEL
                    except Exception as exc:
                        logger.warning("Failed to refresh memory embedding: %s", exc)
                existing.updated_at = datetime.now(timezone.utc)
                await self.db.commit()
                await invalidate_memory_search(user_id)
                return existing

            # 生成向量嵌入
            embedding = None
            try:
                embedding = await get_embedding(content)
                logger.info(f"Generated embedding for memory: dim={len(embedding)}")
            except Exception as e:
                logger.warning(f"Failed to generate embedding, storing without it: {e}")

            # 创建记忆记录
            memory = Memory(
                user_id=user_id,
                content=content,
                role=role,
                memory_type=memory_type,
                importance_score=importance_score,
                source_id=source_id,
                embedding=embedding,
                embedding_model=settings.EMBEDDING_MODEL if embedding else None,
            )
            
            self.db.add(memory)
            await self.db.commit()
            await invalidate_memory_search(user_id)
            
            logger.info(f"Stored memory for user {user_id}: {content[:50]}...")
            return memory
            
        except Exception as e:
            logger.error(f"Failed to store memory: {e}")
            await self.db.rollback()
            raise
    
    async def search_similar_memories(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
        memory_type: str = None,
        min_importance: float = 0.0
    ) -> list[dict]:
        """
        使用向量相似度搜索相关记忆（降级为关键词搜索）
        
        Args:
            user_id: 用户 ID
            query: 查询文本
            top_k: 返回结果数量
            memory_type: 记忆类型过滤（可选）
            min_importance: 最小重要性评分（可选）
        
        Returns:
            相关记忆列表
        """
        try:
            # 检查 Redis 缓存
            cached = await get_cached_memory_search(
                user_id, query, top_k, memory_type, min_importance
            )
            if cached is not None:
                logger.info(f"Memory search cache hit for user={user_id}")
                return cached
            # 尝试向量相似度搜索
            try:
                query_embedding = await get_embedding(query)
                logger.info(f"Vector search with embedding: dim={len(query_embedding)}")

                # Retrieve a wider candidate set, then rerank by semantic similarity
                # and time-decayed importance.
                candidate_limit = max(top_k * 3, top_k)
                distance = Memory.embedding.cosine_distance(query_embedding)
                similarity = (1 - distance).label("similarity")
                stmt = (
                    select(Memory, similarity)
                    .where(Memory.user_id == user_id)
                    .where(Memory.embedding.isnot(None))
                    .where(Memory.embedding_model == settings.EMBEDDING_MODEL)
                )

                if memory_type:
                    stmt = stmt.where(Memory.memory_type == memory_type)

                stmt = stmt.order_by(distance).limit(candidate_limit)

                result = await self.db.execute(stmt)
                rows = result.all()

                memories = []
                for row in rows:
                    memory = row[0]
                    similarity = float(row[1])
                    # 增加访问计数（用于衰减计算）
                    memory.access_count += 1
                    memory.last_accessed = datetime.now(timezone.utc)
                    # 计算衰减后的有效重要性
                    effective_imp = self._get_effective_importance(memory)
                    if effective_imp < min_importance:
                        continue
                    relevance_score = 0.75 * similarity + 0.25 * effective_imp
                    memories.append({
                        "id": str(memory.id),
                        "content": memory.content,
                        "role": memory.role,
                        "memory_type": memory.memory_type,
                        "importance_score": memory.importance_score,
                        "effective_importance": round(effective_imp, 4),
                        "created_at": memory.created_at.isoformat(),
                        "similarity": round(similarity, 4),
                        "relevance_score": round(relevance_score, 4),
                    })

                await self.db.commit()

                if memories:
                    memories.sort(key=lambda item: item["relevance_score"], reverse=True)
                    memories = memories[:top_k]
                    await set_cached_memory_search(
                        user_id,
                        query,
                        memories,
                        top_k,
                        memory_type,
                        min_importance,
                    )
                    logger.info(f"Vector search found {len(memories)} memories")
                    return memories

                # 向量搜索无结果，降级为关键词搜索
                logger.info("Vector search returned no results, falling back to keyword search")

            except Exception as e:
                logger.warning(f"Vector search failed, falling back to keyword search: {e}")

            # 降级：关键词搜索
            return await self._keyword_search(user_id, query, top_k, memory_type, min_importance)
            
        except Exception as e:
            logger.error(f"Failed to search memories: {e}")
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
        stop_words = {'的', '了', '是', '在', '我', '你', '他', '她', '它', '们', '这', '那', '有', '和', '与', '或', '但', '不', '也', '就', '都', '很', '会', '要', '能', '可以', '可能', '应该', '需要', '想', '说', '看', '做', '来', '去', '到', '从', '把', '被', '让', '给', '对', '向', '往', '以', '因', '为', '所', '如', '果', '虽', '然', '而', '且', '或', '者', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十', '个', '些', '每', '各', '某', '这', '那', '哪', '什', '么', '怎', '样', '多', '少', '大', '小', '长', '短', '高', '低', '快', '慢', '好', '坏', '新', '旧', '美', '丑', '真', '假', '对', '错', '是', '非'}
        
        keywords = [word for word in words if len(word) >= 2 and word not in stop_words]
        # Chinese text usually has no spaces. Character n-grams provide a useful
        # deterministic fallback when the remote embedding service is unavailable.
        compact = re.sub(r"[^\u4e00-\u9fff]", "", text)
        if compact and len(words) <= 1:
            for size in (4, 3, 2):
                for index in range(0, max(len(compact) - size + 1, 0), max(size - 1, 1)):
                    token = compact[index:index + size]
                    if token and token not in stop_words:
                        keywords.append(token)
        
        return keywords[:10]  # 最多返回 10 个关键词

    async def _keyword_search(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
        memory_type: str = None,
        min_importance: float = 0.0
    ) -> list[dict]:
        """
        关键词搜索（降级方案）

        Args:
            user_id: 用户 ID
            query: 查询文本
            top_k: 返回结果数量
            memory_type: 记忆类型过滤（可选）
            min_importance: 最小重要性评分（可选）

        Returns:
            相关记忆列表
        """
        keywords = self._extract_keywords(query)

        if not keywords:
            return await self.get_recent_memories(user_id, limit=top_k, memory_type=memory_type)

        stmt = select(Memory).where(Memory.user_id == user_id)

        conditions = []
        for keyword in keywords[:5]:
            conditions.append(Memory.content.ilike(f"%{keyword}%"))

        if conditions:
            stmt = stmt.where(or_(*conditions))

        if memory_type:
            stmt = stmt.where(Memory.memory_type == memory_type)

        stmt = stmt.order_by(
            Memory.importance_score.desc(),
            Memory.created_at.desc()
        ).limit(max(top_k * 3, top_k))

        result = await self.db.execute(stmt)
        memories = result.scalars().all()

        for memory in memories:
            memory.access_count += 1
            memory.last_accessed = datetime.now(timezone.utc)

        await self.db.commit()

        result_items = [
            {
                "id": str(m.id),
                "content": m.content,
                "role": m.role,
                "memory_type": m.memory_type,
                "importance_score": m.importance_score,
                "effective_importance": round(self._get_effective_importance(m), 4),
                "relevance_score": round(self._get_effective_importance(m), 4),
                "created_at": m.created_at.isoformat(),
            }
            for m in memories
            if self._get_effective_importance(m) >= min_importance
        ]
        result_items.sort(key=lambda item: item["relevance_score"], reverse=True)
        result_items = result_items[:top_k]
        await set_cached_memory_search(
            user_id,
            query,
            result_items,
            top_k,
            memory_type,
            min_importance,
        )
        logger.info(f"Keyword search found {len(result_items)} memories")
        return result_items
    
    async def get_user_facts(self, user_id: str, limit: int = 10) -> list[str]:
        """
        获取用户的事实性记忆（偏好、习惯等）
        
        按衰减后的重要性排序，确保老记忆不会一直占据前列。
        
        Args:
            user_id: 用户 ID
            limit: 返回数量限制
        
        Returns:
            事实性记忆内容列表
        """
        result = await self.db.execute(
            select(Memory)
            .where(Memory.user_id == user_id)
            .where(Memory.memory_type == "fact")
        )
        all_facts = result.scalars().all()
        # 按衰减后的重要性排序
        all_facts.sort(key=lambda m: self._get_effective_importance(m), reverse=True)
        return [m.content for m in all_facts[:limit]]
    
    async def get_recent_memories(
        self,
        user_id: str,
        limit: int = 10,
        memory_type: str = None
    ) -> list[dict]:
        """
        获取最近的记忆
        
        Args:
            user_id: 用户 ID
            limit: 返回数量限制
            memory_type: 记忆类型过滤（可选）
        
        Returns:
            最近记忆列表
        """
        stmt = (
            select(Memory)
            .where(Memory.user_id == user_id)
            .order_by(Memory.created_at.desc())
            .limit(limit)
        )
        
        if memory_type:
            stmt = stmt.where(Memory.memory_type == memory_type)
        
        result = await self.db.execute(stmt)
        memories = result.scalars().all()
        
        return [
            {
                "id": str(m.id),
                "content": m.content,
                "role": m.role,
                "memory_type": m.memory_type,
                "importance_score": m.importance_score,
                "effective_importance": round(self._get_effective_importance(m), 4),
                "created_at": m.created_at.isoformat(),
            }
            for m in memories
        ]
    

    async def auto_store_conversation(
        self,
        user_id: str,
        content: str,
        role: str,
        source_id: str = None
    ):
        """
        自动判断并存储对话记忆
        
        Args:
            user_id: 用户 ID
            content: 对话内容
            role: 角色（user/system）
            source_id: 来源 ID（可选）
        """
        setting_result = await self.db.execute(
            select(UserProfile.memory_enabled).where(UserProfile.user_id == user_id)
        )
        memory_enabled = setting_result.scalar_one_or_none()
        if memory_enabled == 0:
            return
        judgment = await self.judge.judge(content, role=role)

        if judgment["should_remember"]:
            await self.store_memory(
                user_id=user_id,
                content=content,
                role=role,
                memory_type=judgment["memory_type"],
                importance_score=judgment["importance"],
                source_id=source_id
            )
    
    async def delete_memory(self, memory_id: str, user_id: str) -> bool:
        """
        删除记忆
        
        Args:
            memory_id: 记忆 ID
            user_id: 用户 ID（用于权限验证）
        
        Returns:
            是否删除成功
        """
        result = await self.db.execute(
            select(Memory)
            .where(Memory.id == memory_id)
            .where(Memory.user_id == user_id)
        )
        memory = result.scalar_one_or_none()
        
        if memory:
            await self.db.delete(memory)
            await self.db.commit()
            await invalidate_memory_search(user_id)
            logger.info(f"Deleted memory {memory_id}")
            return True
        
        return False
    
    async def get_memory_stats(self, user_id: str) -> dict:
        """
        获取记忆统计信息
        
        Args:
            user_id: 用户 ID
        
        Returns:
            统计信息字典
        """
        # 总记忆数
        total_result = await self.db.execute(
            select(func.count(Memory.id))
            .where(Memory.user_id == user_id)
        )
        total = total_result.scalar()
        
        # 按类型统计
        type_result = await self.db.execute(
            select(Memory.memory_type, func.count(Memory.id))
            .where(Memory.user_id == user_id)
            .group_by(Memory.memory_type)
        )
        type_stats = {row[0]: row[1] for row in type_result.all()}
        
        return {
            "total": total,
            "by_type": type_stats,
        }

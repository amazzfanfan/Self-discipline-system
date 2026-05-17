# 目标管理系统与向量记忆升级实现计划

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 实现目标管理系统，集成阿里云 Embedding API，升级记忆系统支持语义搜索，智能任务生成参考用户目标

**Architecture:** 使用 PostgreSQL + pgvector 存储向量嵌入，阿里云 DashScope Embedding API 生成向量，新增 goals 表存储用户目标，升级 memory_service 和 context_builder 支持语义搜索

**Tech Stack:** PostgreSQL, pgvector, 阿里云 DashScope Embedding API, FastAPI, SQLAlchemy

---

## Phase 1: 集成 Embedding API

### Task 1.1: 配置阿里云 Embedding API

**Objective:** 在配置文件中添加阿里云 Embedding API 的配置

**Files:**
- Modify: `backend/app/core/config.py`

**Step 1: 添加配置项**

在 `Settings` 类中添加：
```python
# Embedding Configuration
EMBEDDING_API_KEY: str = ""
EMBEDDING_MODEL: str = "text-embedding-v2"
EMBEDDING_DIMENSION: int = 1536
```

**Step 2: 更新 .env 文件**

在 `.env` 文件中添加：
```bash
EMBEDDING_API_KEY=your-embedding-api-key
EMBEDDING_MODEL=text-embedding-v2
EMBEDDING_DIMENSION=1536
```

**Step 3: Commit**

```bash
git add backend/app/core/config.py backend/.env
git commit -m "feat: add embedding API configuration"
```

---

### Task 1.2: 创建 EmbeddingService

**Objective:** 创建 EmbeddingService 服务，封装阿里云 Embedding API 调用

**Files:**
- Create: `backend/app/services/embedding_service.py`

**Step 1: 创建 EmbeddingService**

```python
"""
Embedding Service - 向量嵌入服务
使用阿里云 DashScope Embedding API 生成文本的向量嵌入
"""

import httpx
from app.core.config import get_settings
import logging

logger = logging.getLogger(__name__)
settings = get_settings()


class EmbeddingService:
    """向量嵌入服务"""
    
    def __init__(self):
        self.api_key = settings.EMBEDDING_API_KEY
        self.model = settings.EMBEDDING_MODEL
        self.dimension = settings.EMBEDDING_DIMENSION
        self.base_url = "https://dashscope.aliyuncs.com/api/v1"
    
    async def get_embedding(self, text: str) -> list[float]:
        """
        获取文本的向量嵌入
        
        Args:
            text: 输入文本
        
        Returns:
            向量嵌入列表
        """
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.base_url}/services/embeddings/text-embedding/text-embedding",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "input": {
                            "texts": [text]
                        },
                        "parameters": {
                            "dimension": self.dimension
                        }
                    }
                )
                
                if response.status_code != 200:
                    logger.error(f"Embedding API error: {response.status_code} - {response.text}")
                    return []
                
                data = response.json()
                embeddings = data.get("output", {}).get("embeddings", [])
                
                if embeddings:
                    return embeddings[0].get("embedding", [])
                
                return []
                
        except Exception as e:
            logger.error(f"Failed to get embedding: {e}")
            return []
    
    async def batch_embed(self, texts: list[str]) -> list[list[float]]:
        """
        批量获取文本的向量嵌入
        
        Args:
            texts: 文本列表
        
        Returns:
            向量嵌入列表
        """
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    f"{self.base_url}/services/embeddings/text-embedding/text-embedding",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "input": {
                            "texts": texts
                        },
                        "parameters": {
                            "dimension": self.dimension
                        }
                    }
                )
                
                if response.status_code != 200:
                    logger.error(f"Embedding API error: {response.status_code} - {response.text}")
                    return []
                
                data = response.json()
                embeddings = data.get("output", {}).get("embeddings", [])
                
                return [e.get("embedding", []) for e in embeddings]
                
        except Exception as e:
            logger.error(f"Failed to batch embed: {e}")
            return []


# 全局实例
embedding_service = EmbeddingService()
```

**Step 2: Commit**

```bash
git add backend/app/services/embedding_service.py
git commit -m "feat: create EmbeddingService for vector embeddings"
```

---

## Phase 2: 升级记忆系统

### Task 2.1: 升级 MemoryService 支持向量嵌入

**Objective:** 修改 MemoryService，在存储记忆时生成向量嵌入，搜索时使用向量相似度

**Files:**
- Modify: `backend/app/services/memory_service.py`

**Step 1: 添加导入**

在文件顶部添加：
```python
from app.services.embedding_service import embedding_service
```

**Step 2: 修改 store_memory 方法**

```python
async def store_memory(
    self,
    user_id: str,
    content: str,
    role: str,
    memory_type: str = "conversation",
    importance_score: float = 0.5,
    source_id: str = None
) -> Memory:
    """存储记忆并生成向量嵌入"""
    try:
        # 生成向量嵌入
        embedding = await embedding_service.get_embedding(content)
        
        # 创建记忆记录
        memory = Memory(
            user_id=user_id,
            content=content,
            role=role,
            embedding=embedding if embedding else None,
            memory_type=memory_type,
            importance_score=importance_score,
            source_id=source_id,
        )
        
        self.db.add(memory)
        await self.db.commit()
        
        logger.info(f"Stored memory for user {user_id}: {content[:50]}...")
        return memory
        
    except Exception as e:
        logger.error(f"Failed to store memory: {e}")
        await self.db.rollback()
        raise
```

**Step 3: 修改 search_similar_memories 方法**

```python
async def search_similar_memories(
    self,
    user_id: str,
    query: str,
    top_k: int = 5,
    memory_type: str = None,
    min_importance: float = 0.0
) -> list[dict]:
    """使用向量相似度搜索相关记忆"""
    try:
        # 获取查询的向量嵌入
        query_embedding = await embedding_service.get_embedding(query)
        
        if not query_embedding:
            # 如果获取嵌入失败，降级到关键词搜索
            return await self._keyword_search(user_id, query, top_k, memory_type)
        
        # 构建向量相似度查询
        from pgvector.sqlalchemy import Vector
        from sqlalchemy import text
        
        # 使用余弦相似度搜索
        stmt = (
            select(
                Memory,
                (1 - Memory.embedding.cosine_distance(query_embedding)).label("similarity")
            )
            .where(Memory.user_id == user_id)
            .where(Memory.embedding.isnot(None))
            .order_by(text("similarity DESC"))
            .limit(top_k)
        )
        
        if memory_type:
            stmt = stmt.where(Memory.memory_type == memory_type)
        if min_importance > 0:
            stmt = stmt.where(Memory.importance_score >= min_importance)
        
        result = await self.db.execute(stmt)
        rows = result.all()
        
        # 更新访问统计
        for row in rows:
            memory = row[0]
            memory.access_count += 1
            memory.last_accessed = datetime.now(timezone.utc)
        
        await self.db.commit()
        
        return [
            {
                "id": str(row[0].id),
                "content": row[0].content,
                "role": row[0].role,
                "memory_type": row[0].memory_type,
                "importance_score": row[0].importance_score,
                "similarity": row[1],
                "created_at": row[0].created_at.isoformat(),
            }
            for row in rows
        ]
        
    except Exception as e:
        logger.error(f"Failed to search memories: {e}")
        # 降级到关键词搜索
        return await self._keyword_search(user_id, query, top_k, memory_type)
```

**Step 4: 添加关键词搜索降级方法**

```python
async def _keyword_search(
    self,
    user_id: str,
    query: str,
    top_k: int = 5,
    memory_type: str = None
) -> list[dict]:
    """关键词搜索（降级方案）"""
    try:
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
        ).limit(top_k)
        
        result = await self.db.execute(stmt)
        memories = result.scalars().all()
        
        return [
            {
                "id": str(m.id),
                "content": m.content,
                "role": m.role,
                "memory_type": m.memory_type,
                "importance_score": m.importance_score,
                "created_at": m.created_at.isoformat(),
            }
            for m in memories
        ]
        
    except Exception as e:
        logger.error(f"Failed to search memories: {e}")
        return []
```

**Step 5: Commit**

```bash
git add backend/app/services/memory_service.py
git commit -m "feat: upgrade MemoryService with vector embedding support"
```

---

### Task 2.2: 升级 ContextBuilder 使用语义搜索

**Objective:** 修改 ContextBuilder，使用语义搜索获取相关记忆和目标

**Files:**
- Modify: `backend/app/services/context_builder.py`

**Step 1: 添加导入**

在文件顶部添加：
```python
from app.services.goal_service import goal_service
```

**Step 2: 修改 build_context_with_action 方法**

```python
async def build_context_with_action(
    self,
    user_message: str,
    action_context: str = "",
    include_recent: bool = True,
    include_relevant: bool = True
) -> list[dict]:
    """构建带有动作上下文的对话上下文"""
    context = []
    
    # 1. 系统提示
    system_prompt = await self.build_system_prompt()
    if action_context:
        system_prompt += f"\n{action_context}"
    context.append({"role": "system", "content": system_prompt})
    
    # 2. 相关目标（语义搜索）
    if include_relevant:
        try:
            relevant_goals = await goal_service.search_goals(
                user_id=str(self.user.id),
                query=user_message,
                top_k=3
            )
            if relevant_goals:
                goals_text = "用户目标：\n"
                for goal in relevant_goals:
                    goals_text += f"- {goal['content']}\n"
                context.append({"role": "system", "content": goals_text})
                logger.info(f"Relevant goals: {len(relevant_goals)} items")
        except Exception as e:
            logger.warning(f"Failed to get relevant goals: {e}")
    
    # 3. 相关记忆（语义搜索）
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
```

**Step 3: Commit**

```bash
git add backend/app/services/context_builder.py
git commit -m "feat: upgrade ContextBuilder with semantic search"
```

---

## Phase 3: 创建目标管理系统

### Task 3.1: 创建 goals 表

**Objective:** 创建 goals 表的数据库模型

**Files:**
- Create: `backend/app/models/goal.py`
- Modify: `backend/app/models/__init__.py`

**Step 1: 创建 Goal 模型**

```python
"""
Goal Model - 用户目标模型
存储用户设定的目标，支持向量嵌入和语义搜索
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Float, JSON
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
from app.core.database import Base


class Goal(Base):
    """用户目标模型"""
    __tablename__ = "goals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    
    # 目标内容
    content = Column(Text, nullable=False)
    goal_type = Column(String(50), index=True)  # exercise/diet/sleep/appearance
    
    # 结构化数据
    structured_data = Column(JSON)  # 存储结构化目标参数
    
    # 向量嵌入
    embedding = Column(Vector(1536))
    
    # 元数据
    importance_score = Column(Float, default=0.8)
    status = Column(String(20), default="active", index=True)  # active/completed/paused
    source = Column(String(20), default="manual")  # manual/chat
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Goal {self.id}: {self.content[:50]}...>"

    def to_dict(self):
        """转换为字典"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "content": self.content,
            "goal_type": self.goal_type,
            "structured_data": self.structured_data,
            "importance_score": self.importance_score,
            "status": self.status,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
```

**Step 2: 更新 __init__.py**

在 `backend/app/models/__init__.py` 中添加：
```python
from app.models.goal import Goal

__all__ = [
    # ... 现有导出 ...
    "Goal",
]
```

**Step 3: 创建数据库迁移**

```bash
cd backend
alembic revision --autogenerate -m "add goals table"
alembic upgrade head
```

**Step 4: Commit**

```bash
git add backend/app/models/goal.py backend/app/models/__init__.py
git commit -m "feat: create Goal model for user goals"
```

---

### Task 3.2: 创建 GoalService

**Objective:** 创建 GoalService 服务，实现目标的 CRUD 和搜索功能

**Files:**
- Create: `backend/app/services/goal_service.py`

**Step 1: 创建 GoalService**

```python
"""
Goal Service - 目标管理服务
管理用户目标的 CRUD 和语义搜索
"""

from datetime import datetime, timezone
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.goal import Goal
from app.services.embedding_service import embedding_service
import logging
import re

logger = logging.getLogger(__name__)


class GoalService:
    """目标管理服务"""
    
    def __init__(self):
        pass
    
    async def create_goal(
        self,
        db: AsyncSession,
        user_id: str,
        content: str,
        goal_type: str = None,
        structured_data: dict = None,
        source: str = "manual"
    ) -> Goal:
        """
        创建目标
        
        Args:
            db: 数据库会话
            user_id: 用户 ID
            content: 目标内容
            goal_type: 目标类型
            structured_data: 结构化数据
            source: 来源（manual/chat）
        
        Returns:
            Goal 对象
        """
        try:
            # 生成向量嵌入
            embedding = await embedding_service.get_embedding(content)
            
            # 创建目标
            goal = Goal(
                user_id=user_id,
                content=content,
                goal_type=goal_type,
                structured_data=structured_data,
                embedding=embedding if embedding else None,
                source=source,
            )
            
            db.add(goal)
            await db.commit()
            
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
        updates: dict
    ) -> Goal:
        """
        更新目标
        
        Args:
            db: 数据库会话
            goal_id: 目标 ID
            user_id: 用户 ID
            updates: 更新内容
        
        Returns:
            Goal 对象
        """
        try:
            result = await db.execute(
                select(Goal)
                .where(Goal.id == goal_id)
                .where(Goal.user_id == user_id)
            )
            goal = result.scalar_one_or_none()
            
            if not goal:
                raise ValueError("Goal not found")
            
            # 更新字段
            for key, value in updates.items():
                if hasattr(goal, key):
                    setattr(goal, key, value)
            
            # 如果内容更新，重新生成嵌入
            if "content" in updates:
                embedding = await embedding_service.get_embedding(updates["content"])
                goal.embedding = embedding if embedding else None
            
            await db.commit()
            
            logger.info(f"Updated goal {goal_id}")
            return goal
            
        except Exception as e:
            logger.error(f"Failed to update goal: {e}")
            await db.rollback()
            raise
    
    async def delete_goal(
        self,
        db: AsyncSession,
        goal_id: str,
        user_id: str
    ) -> bool:
        """
        删除目标
        
        Args:
            db: 数据库会话
            goal_id: 目标 ID
            user_id: 用户 ID
        
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
            
            if not goal:
                return False
            
            await db.delete(goal)
            await db.commit()
            
            logger.info(f"Deleted goal {goal_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete goal: {e}")
            await db.rollback()
            return False
    
    async def get_user_goals(
        self,
        db: AsyncSession,
        user_id: str,
        status: str = "active",
        goal_type: str = None
    ) -> list[dict]:
        """
        获取用户目标
        
        Args:
            db: 数据库会话
            user_id: 用户 ID
            status: 目标状态
            goal_type: 目标类型
        
        Returns:
            目标列表
        """
        try:
            stmt = select(Goal).where(Goal.user_id == user_id)
            
            if status:
                stmt = stmt.where(Goal.status == status)
            if goal_type:
                stmt = stmt.where(Goal.goal_type == goal_type)
            
            stmt = stmt.order_by(Goal.created_at.desc())
            
            result = await db.execute(stmt)
            goals = result.scalars().all()
            
            return [goal.to_dict() for goal in goals]
            
        except Exception as e:
            logger.error(f"Failed to get user goals: {e}")
            return []
    
    async def search_goals(
        self,
        db: AsyncSession,
        user_id: str,
        query: str,
        top_k: int = 5,
        status: str = "active"
    ) -> list[dict]:
        """
        语义搜索目标
        
        Args:
            db: 数据库会话
            user_id: 用户 ID
            query: 查询文本
            top_k: 返回结果数量
            status: 目标状态
        
        Returns:
            相关目标列表
        """
        try:
            # 获取查询的向量嵌入
            query_embedding = await embedding_service.get_embedding(query)
            
            if not query_embedding:
                # 降级到关键词搜索
                return await self._keyword_search(db, user_id, query, top_k, status)
            
            # 向量相似度搜索
            from sqlalchemy import text
            
            stmt = (
                select(
                    Goal,
                    (1 - Goal.embedding.cosine_distance(query_embedding)).label("similarity")
                )
                .where(Goal.user_id == user_id)
                .where(Goal.embedding.isnot(None))
            )
            
            if status:
                stmt = stmt.where(Goal.status == status)
            
            stmt = stmt.order_by(text("similarity DESC")).limit(top_k)
            
            result = await db.execute(stmt)
            rows = result.all()
            
            return [
                {
                    **row[0].to_dict(),
                    "similarity": row[1]
                }
                for row in rows
            ]
            
        except Exception as e:
            logger.error(f"Failed to search goals: {e}")
            return await self._keyword_search(db, user_id, query, top_k, status)
    
    async def _keyword_search(
        self,
        db: AsyncSession,
        user_id: str,
        query: str,
        top_k: int = 5,
        status: str = "active"
    ) -> list[dict]:
        """关键词搜索（降级方案）"""
        try:
            stmt = select(Goal).where(Goal.user_id == user_id)
            
            if status:
                stmt = stmt.where(Goal.status == status)
            
            # 简单的关键词匹配
            keywords = query.split()
            conditions = []
            for keyword in keywords[:5]:
                conditions.append(Goal.content.ilike(f"%{keyword}%"))
            
            if conditions:
                from sqlalchemy import or_
                stmt = stmt.where(or_(*conditions))
            
            stmt = stmt.order_by(Goal.created_at.desc()).limit(top_k)
            
            result = await db.execute(stmt)
            goals = result.scalars().all()
            
            return [goal.to_dict() for goal in goals]
            
        except Exception as e:
            logger.error(f"Failed to keyword search goals: {e}")
            return []
    
    async def extract_goal_from_message(
        self,
        db: AsyncSession,
        user_id: str,
        message: str
    ) -> Goal | None:
        """
        从聊天消息中提取目标
        
        Args:
            db: 数据库会话
            user_id: 用户 ID
            message: 聊天消息
        
        Returns:
            Goal 对象或 None
        """
        # 检测是否包含目标相关关键词
        goal_keywords = ["目标", "计划", "打算", "想要", "希望", "每天", "每周"]
        
        if not any(kw in message for kw in goal_keywords):
            return None
        
        # 尝试提取目标类型
        goal_type = None
        type_keywords = {
            "exercise": ["运动", "跑步", "健身", "锻炼", "走路", "游泳"],
            "diet": ["饮食", "吃", "食物", "蔬菜", "水果", "喝水"],
            "sleep": ["睡眠", "睡觉", "早睡", "休息"],
            "appearance": ["护肤", "外貌", "形象", "打扮"],
        }
        
        for gtype, keywords in type_keywords.items():
            if any(kw in message for kw in keywords):
                goal_type = gtype
                break
        
        # 存储目标
        goal = await self.create_goal(
            db=db,
            user_id=user_id,
            content=message,
            goal_type=goal_type,
            source="chat"
        )
        
        return goal


# 全局实例
goal_service = GoalService()
```

**Step 2: Commit**

```bash
git add backend/app/services/goal_service.py
git commit -m "feat: create GoalService for goal management"
```

---

### Task 3.3: 创建目标管理 API

**Objective:** 创建目标管理的 API 端点

**Files:**
- Create: `backend/app/modules/goals/router.py`
- Modify: `backend/app/main.py`

**Step 1: 创建 goals router**

```python
"""
Goals Router - 目标管理路由
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services.goal_service import goal_service

router = APIRouter(prefix="/api/goals", tags=["goals"])


class GoalCreateRequest(BaseModel):
    content: str
    goal_type: Optional[str] = None
    structured_data: Optional[dict] = None


class GoalUpdateRequest(BaseModel):
    content: Optional[str] = None
    goal_type: Optional[str] = None
    structured_data: Optional[dict] = None
    status: Optional[str] = None


@router.post("", status_code=201)
async def create_goal(
    req: GoalCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """创建目标"""
    goal = await goal_service.create_goal(
        db=db,
        user_id=str(user.id),
        content=req.content,
        goal_type=req.goal_type,
        structured_data=req.structured_data,
        source="manual"
    )
    return goal.to_dict()


@router.get("")
async def get_goals(
    status: str = "active",
    goal_type: str = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取目标列表"""
    goals = await goal_service.get_user_goals(
        db=db,
        user_id=str(user.id),
        status=status,
        goal_type=goal_type
    )
    return goals


@router.put("/{goal_id}")
async def update_goal(
    goal_id: str,
    req: GoalUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """更新目标"""
    updates = {k: v for k, v in req.dict().items() if v is not None}
    
    try:
        goal = await goal_service.update_goal(
            db=db,
            goal_id=goal_id,
            user_id=str(user.id),
            updates=updates
        )
        return goal.to_dict()
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/{goal_id}")
async def delete_goal(
    goal_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """删除目标"""
    success = await goal_service.delete_goal(
        db=db,
        goal_id=goal_id,
        user_id=str(user.id)
    )
    if not success:
        raise HTTPException(404, "Goal not found")
    return {"message": "Goal deleted"}


@router.get("/search")
async def search_goals(
    query: str,
    top_k: int = 5,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """语义搜索目标"""
    goals = await goal_service.search_goals(
        db=db,
        user_id=str(user.id),
        query=query,
        top_k=top_k
    )
    return goals
```

**Step 2: 注册路由**

在 `backend/app/main.py` 中添加：
```python
from app.modules.goals.router import router as goals_router

app.include_router(goals_router)
```

**Step 3: Commit**

```bash
git add backend/app/modules/goals/router.py backend/app/main.py
git commit -m "feat: add goals API endpoints"
```

---

## Phase 4: 升级任务生成

### Task 4.1: 更新 scheduler_service.py

**Objective:** 修改任务生成逻辑，参考用户目标

**Files:**
- Modify: `backend/app/services/scheduler_service.py`

**Step 1: 添加导入**

在文件顶部添加：
```python
from app.services.goal_service import goal_service
```

**Step 2: 修改 generate_tasks_for_user 函数**

```python
async def generate_tasks_for_user(user_id, nickname: str, db=None):
    """Generate today's tasks for a single user. Pass db session or creates its own."""
    async def _generate(session):
        scores_result = await session.execute(select(UserScore).where(UserScore.user_id == user_id))
        scores = {s.dimension: s for s in scores_result.scalars().all()}

        # 获取用户的肤质分析结果
        profile_result = await session.execute(select(UserProfile).where(UserProfile.user_id == user_id))
        profile = profile_result.scalar_one_or_none()
        skin_analysis = profile.skin_analysis if profile else None

        # 获取用户目标
        goals = await goal_service.get_user_goals(session, user_id, status="active")
        
        # 按类型分组目标
        goals_by_type = {}
        for goal in goals:
            gtype = goal.get("goal_type")
            if gtype:
                if gtype not in goals_by_type:
                    goals_by_type[gtype] = []
                goals_by_type[gtype].append(goal)

        generated_tasks = []
        default_titles = {
            DimensionEnum.exercise: "运动30分钟",
            DimensionEnum.diet: "健康饮食一天",
            DimensionEnum.sleep: "23:00前入睡",
            DimensionEnum.appearance: "认真护肤一次",
        }

        for dim, count in TASKS_PER_DIMENSION.items():
            score_record = scores.get(dim)
            if not score_record:
                continue

            # 检查是否有相关目标
            dim_goals = goals_by_type.get(dim.value, [])
            
            # 生成任务
            if dim_goals:
                # 有目标时，参考目标生成任务
                goal_content = dim_goals[0]["content"]
                task_title = await generate_task(
                    nickname=nickname,
                    dimension=dim.value,
                    score=score_record.score,
                    difficulty="medium",
                    recent_tasks=[],
                    user_goal=goal_content
                )
            else:
                # 没有目标时，使用默认逻辑
                task_title = await generate_task(
                    nickname=nickname,
                    dimension=dim.value,
                    score=score_record.score,
                    difficulty="medium",
                    recent_tasks=[]
                )

            # 创建任务
            task = Task(
                user_id=user_id,
                dimension=dim,
                title=task_title,
                scheduled_date=date.today(),
                status=TaskStatusEnum.pending,
            )
            session.add(task)
            generated_tasks.append(task)

        await session.commit()
        return generated_tasks

    if db:
        return await _generate(db)
    else:
        async with async_session() as session:
            return await _generate(session)
```

**Step 3: Commit**

```bash
git add backend/app/services/scheduler_service.py
git commit -m "feat: update task generation to consider user goals"
```

---

## Phase 5: 升级聊天路由

### Task 5.1: 更新 chat/router.py 支持目标自动提取

**Objective:** 修改聊天路由，在用户消息中检测目标并自动存储

**Files:**
- Modify: `backend/app/modules/chat/router.py`

**Step 1: 添加导入**

在文件顶部添加：
```python
from app.services.goal_service import goal_service
```

**Step 2: 在 send_message 函数中添加目标提取**

在 `send_message` 函数的后处理部分添加：
```python
# 自动提取目标
await goal_service.extract_goal_from_message(
    db=db,
    user_id=str(user.id),
    content=content
)
```

**Step 3: 在 stream_message 函数中添加目标提取**

在 `stream_message` 函数的后处理部分添加：
```python
# 自动提取目标
await goal_service.extract_goal_from_message(
    db=session,
    user_id=user_id,
    content=content
)
```

**Step 4: Commit**

```bash
git add backend/app/modules/chat/router.py
git commit -m "feat: add automatic goal extraction from chat messages"
```

---

## Phase 6: 前端目标管理

### Task 6.1: 创建目标管理页面

**Objective:** 在"画像"页面增加目标管理板块

**Files:**
- Modify: `frontend/src/pages/Profile.tsx`

**Step 1: 添加目标管理组件**

在 Profile.tsx 中添加目标管理板块：
```tsx
// 目标管理板块
<div className="goals-section">
  <h3>我的目标</h3>
  <button onClick={handleAddGoal}>+ 添加目标</button>
  
  {goals.map(goal => (
    <div key={goal.id} className="goal-item">
      <span className="goal-icon">{getGoalIcon(goal.goal_type)}</span>
      <div className="goal-content">
        <p>{goal.content}</p>
        <span className="goal-type">{goal.goal_type}</span>
        <span className="goal-status">{goal.status}</span>
      </div>
      <div className="goal-actions">
        <button onClick={() => handleEditGoal(goal)}>编辑</button>
        <button onClick={() => handleDeleteGoal(goal.id)}>删除</button>
      </div>
    </div>
  ))}
</div>
```

**Step 2: 添加 API 调用**

```typescript
// 获取目标列表
const fetchGoals = async () => {
  const response = await api.get('/goals');
  setGoals(response.data);
};

// 创建目标
const handleAddGoal = async () => {
  const response = await api.post('/goals', {
    content: newGoal.content,
    goal_type: newGoal.type,
  });
  setGoals([...goals, response.data]);
};

// 删除目标
const handleDeleteGoal = async (goalId: string) => {
  await api.delete(`/goals/${goalId}`);
  setGoals(goals.filter(g => g.id !== goalId));
};
```

**Step 3: Commit**

```bash
git add frontend/src/pages/Profile.tsx
git commit -m "feat: add goal management UI to profile page"
```

---

## 执行顺序

1. **Phase 1:** 集成 Embedding API
2. **Phase 2:** 升级记忆系统
3. **Phase 3:** 创建目标管理系统
4. **Phase 4:** 升级任务生成
5. **Phase 5:** 升级聊天路由
6. **Phase 6:** 前端目标管理

每个 Phase 完成后运行测试，确保功能正常后再继续下一个。

# 系统升级实施计划

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 将系统升级为企业级应用，引入向量记忆、LiteLLM、智能上下文、用户画像等核心能力

**Architecture:** 分层架构，向量数据库负责语义检索，PostgreSQL 负责结构化存储，LiteLLM 提供统一 LLM 接口

**Tech Stack:** PostgreSQL + pgvector, LiteLLM, OpenAI SDK, Redis, SQLAlchemy

---

## Phase 1: 基础设施准备

### Task 1.1: 安装 pgvector 扩展

**Objective:** 在 PostgreSQL 中启用 pgvector 向量数据库支持

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/scripts/setup_pgvector.sql`

**Step 1: 检查 PostgreSQL 版本**
```bash
psql --version
# 需要 PostgreSQL 12+
```

**Step 2: 安装 pgvector 扩展**
```bash
# Ubuntu/Debian
sudo apt install postgresql-15-pgvector

# 或者从源码安装
cd /tmp
git clone https://github.com/pgvector/pgvector.git
cd pgvector
make
sudo make install
```

**Step 3: 在数据库中启用扩展**
```sql
-- scripts/setup_pgvector.sql
CREATE EXTENSION IF NOT EXISTS vector;

-- 验证安装
SELECT * FROM pg_extension WHERE extname = 'vector';
```

**Step 4: 运行设置脚本**
```bash
psql -U postgres -d system_agent -f backend/scripts/setup_pgvector.sql
```

**Step 5: Commit**
```bash
git add backend/scripts/setup_pgvector.sql
git commit -m "feat: add pgvector setup script"
```

---

### Task 1.2: 安装 Python 依赖

**Objective:** 安装 LiteLLM、pgvector Python 客户端等依赖

**Files:**
- Modify: `backend/requirements.txt`

**Step 1: 更新 requirements.txt**
```txt
# 添加以下依赖
litellm>=1.30.0
pgvector>=0.2.0
tiktoken>=0.5.0
tenacity>=8.2.0
```

**Step 2: 安装依赖**
```bash
cd backend
pip install -r requirements.txt
```

**Step 3: 验证安装**
```bash
python -c "import litellm; print(litellm.__version__)"
python -c "import pgvector; print('pgvector ok')"
```

**Step 4: Commit**
```bash
git add backend/requirements.txt
git commit -m "deps: add litellm, pgvector, tiktoken"
```

---

## Phase 2: 集成 LiteLLM

### Task 2.1: 创建 LiteLLM 服务

**Objective:** 创建统一的 LLM 调用服务，替代原来的 httpx 直接调用

**Files:**
- Create: `backend/app/services/llm_service.py`
- Modify: `backend/app/core/config.py`

**Step 1: 更新配置**
```python
# backend/app/core/config.py 添加
class Settings(BaseSettings):
    # ... 现有配置 ...
    
    # LLM 配置
    LLM_PROVIDER: str = "openai"  # openai, anthropic, etc.
    LLM_MODEL: str = "mimo-v2.5"
    LLM_MAX_RETRIES: int = 3
    LLM_TIMEOUT: int = 30
    LLM_FALLBACK_MODEL: str = "gpt-3.5-turbo"
```

**Step 2: 创建 LLM 服务**
```python
# backend/app/services/llm_service.py
import litellm
from litellm import acompletion
from app.core.config import get_settings
import logging

logger = logging.getLogger(__name__)
settings = get_settings()

# 配置 LiteLLM
litellm.num_retries = settings.LLM_MAX_RETRIES
litellm.request_timeout = settings.LLM_TIMEOUT
litellm.drop_params = True

async def chat_completion(
    messages: list[dict],
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = 1500,
    response_format: dict = None
) -> str:
    """统一的 LLM 调用接口"""
    model = model or settings.LLM_MODEL
    
    try:
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format
        
        response = await acompletion(**kwargs)
        return response.choices[0].message.content
        
    except litellm.RateLimitError as e:
        logger.warning(f"Rate limit hit: {e}")
        raise
    except litellm.APIError as e:
        logger.error(f"API error: {e}")
        raise
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        raise

async def chat_completion_stream(
    messages: list[dict],
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = 1500
):
    """流式 LLM 调用"""
    model = model or settings.LLM_MODEL
    
    try:
        response = await acompletion(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        
        async for chunk in response:
            content = chunk.choices[0].delta.content
            if content:
                yield content
                
    except Exception as e:
        logger.error(f"Stream LLM call failed: {e}")
        raise

async def get_embedding(text: str, model: str = None) -> list[float]:
    """获取文本的向量嵌入"""
    # 如果使用 OpenAI 兼容 API
    from openai import AsyncOpenAI
    
    client = AsyncOpenAI(
        api_key=settings.AI_API_KEY,
        base_url=settings.AI_BASE_URL,
    )
    
    response = await client.embeddings.create(
        model="text-embedding-ada-002",  # 或其他嵌入模型
        input=text,
    )
    
    return response.data[0].embedding
```

**Step 3: Commit**
```bash
git add backend/app/services/llm_service.py backend/app/core/config.py
git commit -m "feat: add LiteLLM service with retry and streaming"
```

---

### Task 2.2: 迁移现有调用到 LiteLLM

**Objective:** 将 ai_service.py 中的 httpx 调用迁移到 LiteLLM

**Files:**
- Modify: `backend/app/services/ai_service.py`

**Step 1: 更新导入**
```python
# backend/app/services/ai_service.py
from app.services.llm_service import chat_completion, chat_completion_stream
```

**Step 2: 更新 chat_completion 函数**
```python
async def chat_completion_old(messages: list[dict], user_context: str = "") -> str:
    """旧的实现（保留作为参考）"""
    # ... 旧代码 ...

async def chat_completion_new(messages: list[dict], user_context: str = "") -> str:
    """新的实现使用 LiteLLM"""
    system_msg = _build_system_prompt(user_context)
    full_messages = [{"role": "system", "content": system_msg}] + messages
    
    return await chat_completion(
        messages=full_messages,
        max_tokens=1500,
    )
```

**Step 3: 更新所有调用点**
```python
# 替换所有 httpx 调用为 LiteLLM 调用
# 例如 generate_task, generate_appearance_analysis 等
```

**Step 4: Commit**
```bash
git add backend/app/services/ai_service.py
git commit -m "refactor: migrate ai_service to use LiteLLM"
```

---

## Phase 3: 向量记忆系统

### Task 3.1: 创建向量记忆模型

**Objective:** 创建存储向量嵌入的数据库模型

**Files:**
- Create: `backend/app/models/memory.py`
- Modify: `backend/app/models/__init__.py`

**Step 1: 创建 Memory 模型**
```python
# backend/app/models/memory.py
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Float, Integer
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
from app.core.database import Base

class Memory(Base):
    """向量记忆模型"""
    __tablename__ = "memories"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    
    # 原始内容
    content = Column(Text, nullable=False)
    role = Column(String(20), nullable=False)  # user, system
    
    # 向量嵌入
    embedding = Column(Vector(1536))  # OpenAI ada-002 维度
    
    # 元数据
    memory_type = Column(String(50), default="conversation")  # conversation, preference, fact
    importance_score = Column(Float, default=0.5)  # 0-1 重要性评分
    
    # 访问统计
    access_count = Column(Integer, default=0)
    last_accessed = Column(DateTime(timezone=True))
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    def __repr__(self):
        return f"<Memory {self.id}: {self.content[:50]}...>"
```

**Step 2: 更新模型导入**
```python
# backend/app/models/__init__.py
from app.models.memory import Memory
```

**Step 3: 创建数据库迁移**
```bash
cd backend
alembic revision --autogenerate -m "add memories table with vector"
alembic upgrade head
```

**Step 4: Commit**
```bash
git add backend/app/models/memory.py backend/app/models/__init__.py
git commit -m "feat: add Memory model with pgvector support"
```

---

### Task 3.2: 创建记忆服务

**Objective:** 实现记忆的存储、检索、管理功能

**Files:**
- Create: `backend/app/services/memory_service.py`

**Step 1: 创建记忆服务**
```python
# backend/app/services/memory_service.py
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.memory import Memory
from app.services.llm_service import get_embedding
import logging

logger = logging.getLogger(__name__)

class MemoryService:
    """记忆管理服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def store_memory(
        self,
        user_id: str,
        content: str,
        role: str,
        memory_type: str = "conversation",
        importance_score: float = 0.5
    ) -> Memory:
        """存储记忆并生成向量嵌入"""
        try:
            # 生成向量嵌入
            embedding = await get_embedding(content)
            
            # 创建记忆记录
            memory = Memory(
                user_id=user_id,
                content=content,
                role=role,
                embedding=embedding,
                memory_type=memory_type,
                importance_score=importance_score,
            )
            
            self.db.add(memory)
            await self.db.commit()
            
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
        memory_type: str = None
    ) -> list[dict]:
        """语义检索相关记忆"""
        try:
            # 获取查询的向量嵌入
            query_embedding = await get_embedding(query)
            
            # 构建查询
            stmt = (
                select(
                    Memory,
                    Memory.embedding.cosine_distance(query_embedding).label("distance")
                )
                .where(Memory.user_id == user_id)
                .order_by("distance")
                .limit(top_k)
            )
            
            if memory_type:
                stmt = stmt.where(Memory.memory_type == memory_type)
            
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
                    "content": row[0].content,
                    "role": row[0].role,
                    "memory_type": row[0].memory_type,
                    "importance_score": row[0].importance_score,
                    "distance": row[1],
                }
                for row in rows
            ]
            
        except Exception as e:
            logger.error(f"Failed to search memories: {e}")
            raise
    
    async def get_user_facts(self, user_id: str) -> list[str]:
        """获取用户的事实性记忆（偏好、习惯等）"""
        result = await self.db.execute(
            select(Memory)
            .where(Memory.user_id == user_id)
            .where(Memory.memory_type == "fact")
            .order_by(Memory.importance_score.desc())
            .limit(10)
        )
        return [m.content for m in result.scalars()]
    
    async def should_remember(self, content: str) -> bool:
        """判断内容是否值得记住"""
        keywords = [
            "目标", "计划", "打算", "准备",  # 目标/计划
            "喜欢", "讨厌", "习惯", "偏好",  # 偏好
            "体重", "睡眠", "运动", "饮食",  # 健康数据
            "难过", "开心", "焦虑", "压力",  # 情感
        ]
        return any(kw in content for kw in keywords)
    
    async def auto_store_conversation(
        self,
        user_id: str,
        content: str,
        role: str
    ):
        """自动判断并存储对话记忆"""
        if await self.should_remember(content):
            importance = 0.8 if role == "user" else 0.6
            await self.store_memory(
                user_id=user_id,
                content=content,
                role=role,
                memory_type="conversation",
                importance_score=importance
            )
```

**Step 2: Commit**
```bash
git add backend/app/services/memory_service.py
git commit -m "feat: add memory service with semantic search"
```

---

## Phase 4: 智能上下文构建

### Task 4.1: 创建上下文构建器

**Objective:** 实现智能的上下文组装逻辑

**Files:**
- Create: `backend/app/services/context_builder.py`

**Step 1: 创建上下文构建器**
```python
# backend/app/services/context_builder.py
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.conversation import Conversation
from app.models.user import User
from app.services.memory_service import MemoryService
import tiktoken
import logging

logger = logging.getLogger(__name__)

BJT = timezone(timedelta(hours=8))

class ContextBuilder:
    """智能上下文构建器"""
    
    def __init__(self, db: AsyncSession, user: User):
        self.db = db
        self.user = user
        self.memory_service = MemoryService(db)
        self.token_budget = 3000  # 留给上下文的 token 预算
    
    def count_tokens(self, text: str) -> int:
        """计算 token 数量"""
        try:
            encoding = tiktoken.encoding_for_model("gpt-4")
            return len(encoding.encode(text))
        except:
            # 简单估算：中文约 1.5 token/字
            return len(text) * 2
    
    async def build_system_prompt(self) -> str:
        """构建系统提示"""
        now = datetime.now(BJT)
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        time_str = now.strftime(f"%Y年%m月%d日 %H:%M {weekdays[now.weekday()]}")
        
        base_prompt = f"""你是一个名为"系统"的AI助手，灵感来源于小说中的成长系统。你的职责是帮助用户提升自己。

核心原则：
- 用数据说话，用鼓励驱动
- 关注趋势，单次失败不代表失败
- 主动关怀，检测到异常时主动询问
- 保持人设，始终以"系统"身份对话

当前时间（北京时间）：{time_str}
用户信息：{self.user.nickname}，{self.user.age}岁，性别{"男" if self.user.gender == "male" else "女"}
"""
        
        # 添加用户画像
        user_facts = await self.memory_service.get_user_facts(str(self.user.id))
        if user_facts:
            base_prompt += f"\n用户偏好和习惯：\n" + "\n".join(f"- {fact}" for fact in user_facts)
        
        return base_prompt
    
    async def build_context(
        self,
        user_message: str,
        include_recent: bool = True,
        include_relevant: bool = True
    ) -> list[dict]:
        """构建完整的对话上下文"""
        context = []
        used_tokens = 0
        
        # 1. 系统提示（固定）
        system_prompt = await self.build_system_prompt()
        system_tokens = self.count_tokens(system_prompt)
        context.append({"role": "system", "content": system_prompt})
        used_tokens += system_tokens
        
        # 2. 相关历史（语义检索）
        if include_relevant and used_tokens < self.token_budget:
            relevant_memories = await self.memory_service.search_similar_memories(
                user_id=str(self.user.id),
                query=user_message,
                top_k=3,
                memory_type="conversation"
            )
            
            if relevant_memories:
                relevant_text = "相关历史对话：\n"
                for mem in relevant_memories:
                    relevant_text += f"- {mem['content']}\n"
                
                relevant_tokens = self.count_tokens(relevant_text)
                if used_tokens + relevant_tokens < self.token_budget:
                    context.append({"role": "system", "content": relevant_text})
                    used_tokens += relevant_tokens
        
        # 3. 最近对话（按时间）
        if include_recent and used_tokens < self.token_budget:
            recent_messages = await self._get_recent_messages(
                limit=5,
                max_tokens=self.token_budget - used_tokens
            )
            context.extend(recent_messages)
        
        # 4. 当前用户输入
        context.append({"role": "user", "content": user_message})
        
        logger.info(f"Built context with {used_tokens} tokens, {len(context)} messages")
        return context
    
    async def _get_recent_messages(
        self,
        limit: int = 5,
        max_tokens: int = 1000
    ) -> list[dict]:
        """获取最近的对话消息"""
        result = await self.db.execute(
            select(Conversation)
            .where(Conversation.user_id == self.user.id)
            .order_by(Conversation.created_at.desc())
            .limit(limit)
        )
        messages = list(reversed(result.scalars().all()))
        
        # 按 token 预算过滤
        filtered = []
        used_tokens = 0
        
        for msg in messages:
            msg_text = f"{msg.role.value}: {msg.content}"
            msg_tokens = self.count_tokens(msg_text)
            
            if used_tokens + msg_tokens <= max_tokens:
                filtered.append({
                    "role": msg.role.value,
                    "content": msg.content
                })
                used_tokens += msg_tokens
        
        return filtered
```

**Step 2: Commit**
```bash
git add backend/app/services/context_builder.py
git commit -m "feat: add intelligent context builder with token budget"
```

---

## Phase 5: 用户画像系统

### Task 5.1: 创建用户画像模型

**Objective:** 扩展用户模型，支持更丰富的画像数据

**Files:**
- Modify: `backend/app/models/user.py`
- Create: `backend/app/services/profile_service.py`

**Step 1: 扩展用户模型**
```python
# backend/app/models/user.py 添加字段
class User(Base):
    # ... 现有字段 ...
    
    # 画像字段
    preferences = Column(JSON, default={})  # 用户偏好
    habits = Column(JSON, default=[])  # 习惯列表
    goals = Column(JSON, default=[])  # 目标列表
    personality_traits = Column(JSON, default={})  # 性格特征
```

**Step 2: 创建画像服务**
```python
# backend/app/services/profile_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.services.memory_service import MemoryService
import json

class ProfileService:
    """用户画像服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.memory_service = MemoryService(db)
    
    async def update_preferences(self, user_id: str, preferences: dict):
        """更新用户偏好"""
        user = await self.db.get(User, user_id)
        if user:
            current = user.preferences or {}
            current.update(preferences)
            user.preferences = current
            await self.db.commit()
    
    async def add_habit(self, user_id: str, habit: str):
        """添加用户习惯"""
        user = await self.db.get(User, user_id)
        if user:
            habits = user.habits or []
            if habit not in habits:
                habits.append(habit)
                user.habits = habits
                await self.db.commit()
    
    async def add_goal(self, user_id: str, goal: str):
        """添加用户目标"""
        user = await self.db.get(User, user_id)
        if user:
            goals = user.goals or []
            if goal not in goals:
                goals.append(goal)
                user.goals = goals
                await self.db.commit()
    
    async def extract_and_update_profile(self, user_id: str, message: str):
        """从对话中提取并更新用户画像"""
        # 简单的关键词提取（实际可以用 LLM 提取）
        keywords = {
            "偏好": ["喜欢", "讨厌", "偏好", "最爱"],
            "习惯": ["习惯", "经常", "每天", "总是"],
            "目标": ["目标", "计划", "打算", "想要"],
        }
        
        for category, words in keywords.items():
            if any(word in message for word in words):
                # 存储到记忆系统
                await self.memory_service.store_memory(
                    user_id=user_id,
                    content=message,
                    role="user",
                    memory_type="fact",
                    importance_score=0.8
                )
                break
```

**Step 3: Commit**
```bash
git add backend/app/models/user.py backend/app/services/profile_service.py
git commit -m "feat: add user profile system"
```

---

## Phase 6: 集成和测试

### Task 6.1: 更新 Chat Router

**Objective:** 将所有新功能集成到聊天路由中

**Files:**
- Modify: `backend/app/modules/chat/router.py`

**Step 1: 更新 chat router**
```python
# backend/app/modules/chat/router.py
from app.services.context_builder import ContextBuilder
from app.services.memory_service import MemoryService
from app.services.profile_service import ProfileService
from app.services.llm_service import chat_completion, chat_completion_stream

@router.post("/send")
async def send_message(
    content: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # 1. 保存用户消息
    user_msg = Conversation(user_id=user.id, role=RoleEnum.user, content=content)
    db.add(user_msg)
    await db.flush()
    
    # 2. 意图识别和任务执行
    # ... 保持原有逻辑 ...
    
    # 3. 智能上下文构建
    context_builder = ContextBuilder(db, user)
    messages = await context_builder.build_context(content)
    
    # 4. AI 回复
    ai_reply = await chat_completion(messages)
    
    # 5. 保存 AI 回复
    sys_msg = Conversation(user_id=user.id, role=RoleEnum.system, content=ai_reply)
    db.add(sys_msg)
    await db.commit()
    
    # 6. 自动存储记忆
    memory_service = MemoryService(db)
    await memory_service.auto_store_conversation(str(user.id), content, "user")
    await memory_service.auto_store_conversation(str(user.id), ai_reply, "system")
    
    # 7. 更新用户画像
    profile_service = ProfileService(db)
    await profile_service.extract_and_update_profile(str(user.id), content)
    
    return {"reply": ai_reply}
```

**Step 2: Commit**
```bash
git add backend/app/modules/chat/router.py
git commit -m "feat: integrate context builder and memory into chat"
```

---

### Task 6.2: 测试验证

**Objective:** 测试所有新功能

**Files:**
- Create: `backend/tests/test_memory.py`
- Create: `backend/tests/test_context.py`

**Step 1: 运行现有测试**
```bash
cd backend
pytest tests/ -v
```

**Step 2: 测试记忆存储**
```bash
# 手动测试
curl -X POST http://localhost:8000/api/chat/send \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d "content=我的目标是每天跑步30分钟"
```

**Step 3: 测试语义检索**
```bash
# 查询相关记忆
curl -X GET "http://localhost:8000/api/memories/search?query=跑步目标" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Step 4: 验证上下文构建**
```bash
# 检查日志输出
tail -f backend/logs/app.log | grep "Built context"
```

**Step 5: Commit**
```bash
git add backend/tests/
git commit -m "test: add tests for memory and context builder"
```

---

## 执行顺序

1. **Phase 1** - 基础设施（pgvector、依赖）
2. **Phase 2** - LiteLLM 集成
3. **Phase 3** - 向量记忆系统
4. **Phase 4** - 智能上下文构建
5. **Phase 5** - 用户画像系统
6. **Phase 6** - 集成和测试

每个 Phase 完成后运行测试，确保功能正常后再继续下一个。

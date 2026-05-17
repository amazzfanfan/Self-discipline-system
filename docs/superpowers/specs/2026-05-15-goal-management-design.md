# 目标管理系统与向量记忆升级设计文档

> **日期：** 2026-05-15
> **状态：** 设计中
> **作者：** zengfan

---

## 1. 背景与目标

### 1.1 背景

当前系统已实现基础的记忆功能，但存在以下问题：

1. **记忆搜索质量差** - 使用关键词匹配，无法理解语义
2. **缺乏目标管理** - 用户在聊天中提到的目标没有被专门管理
3. **任务生成不智能** - 每日任务没有参考用户设定的目标

### 1.2 目标

1. 集成阿里云 Embedding API，实现语义搜索
2. 创建目标管理系统，支持聊天自动提取和手动管理
3. 升级任务生成逻辑，智能参考用户目标

---

## 2. 技术方案

### 2.1 向量数据库

**方案：** PostgreSQL + pgvector 扩展

| 组件 | 说明 |
|------|------|
| PostgreSQL | 主数据库 |
| pgvector | 向量数据库扩展 |
| memories 表 | 存储对话记忆和向量嵌入 |
| goals 表 | 存储用户目标和向量嵌入 |

**理由：**
- 已经安装 pgvector
- 不需要额外部署向量数据库
- 与现有数据库集成

### 2.2 Embedding API

**方案：** 阿里云 DashScope Embedding API

| 项目 | 说明 |
|------|------|
| API | 阿里云 DashScope |
| 模型 | text-embedding-v2 |
| 维度 | 1536 |
| 费用 | 有免费额度 |

**理由：**
- 已经在使用阿里云 DashScope
- 国内访问快
- 有免费额度

---

## 3. 数据模型设计

### 3.1 新增 goals 表

```sql
CREATE TABLE goals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    content TEXT NOT NULL,                    -- 目标内容
    goal_type VARCHAR(50),                    -- 目标类型：exercise/diet/sleep/appearance
    structured_data JSONB,                    -- 结构化数据（可选）
    embedding VECTOR(1536),                   -- 向量嵌入
    importance_score FLOAT DEFAULT 0.8,       -- 重要性评分
    status VARCHAR(20) DEFAULT 'active',      -- active/completed/paused
    source VARCHAR(20) DEFAULT 'manual',      -- manual/chat
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 索引
CREATE INDEX idx_goals_user_id ON goals(user_id);
CREATE INDEX idx_goals_status ON goals(status);
CREATE INDEX idx_goals_embedding ON goals USING ivfflat (embedding vector_cosine_ops);
```

### 3.2 结构化数据示例

```json
{
  "exercise": {
    "type": "跑步",
    "duration": 30,
    "frequency": "每天",
    "time": "09:30"
  }
}
```

### 3.3 升级 memories 表

```sql
-- 添加向量嵌入索引
CREATE INDEX idx_memories_embedding ON memories USING ivfflat (embedding vector_cosine_ops);
```

---

## 4. 功能模块设计

### 4.1 EmbeddingService

**职责：** 调用阿里云 Embedding API，获取文本的向量嵌入

```python
class EmbeddingService:
    async def get_embedding(text: str) -> list[float]
    async def batch_embed(texts: list[str]) -> list[list[float]]
```

**配置：**
```python
EMBEDDING_API_KEY = "your-api-key"
EMBEDDING_MODEL = "text-embedding-v2"
EMBEDDING_DIMENSION = 1536
```

### 4.2 GoalService

**职责：** 管理用户目标的 CRUD 和搜索

```python
class GoalService:
    async def create_goal(user_id, content, goal_type, structured_data, source)
    async def update_goal(goal_id, user_id, updates)
    async def delete_goal(goal_id, user_id)
    async def get_user_goals(user_id, status='active')
    async def search_goals(user_id, query, top_k=5)
    async def extract_goal_from_message(user_id, message)
```

### 4.3 升级 MemoryService

**变更：**
- `store_memory()` - 存储时生成向量嵌入
- `search_similar_memories()` - 使用向量相似度搜索

```python
class MemoryService:
    async def store_memory(user_id, content, role, memory_type, importance_score, source_id):
        # 1. 生成向量嵌入
        embedding = await embedding_service.get_embedding(content)
        
        # 2. 存储到数据库
        memory = Memory(user_id=user_id, content=content, embedding=embedding, ...)
        db.add(memory)
    
    async def search_similar_memories(user_id, query, top_k=5):
        # 1. 获取查询向量
        query_embedding = await embedding_service.get_embedding(query)
        
        # 2. 向量相似度搜索
        results = await db.execute(
            select(Memory)
            .where(Memory.user_id == user_id)
            .order_by(Memory.embedding.cosine_distance(query_embedding))
            .limit(top_k)
        )
```

### 4.4 升级 ContextBuilder

**变更：**
- 搜索相关记忆（语义搜索）
- 搜索相关目标（语义搜索）
- 组装上下文

```python
class ContextBuilder:
    async def build_context(user_message, user):
        # 1. 系统提示
        system_prompt = await self.build_system_prompt()
        
        # 2. 相关目标（语义搜索）
        relevant_goals = await goal_service.search_goals(user_id, user_message, top_k=3)
        
        # 3. 相关记忆（语义搜索）
        relevant_memories = await memory_service.search_similar_memories(user_id, user_message, top_k=3)
        
        # 4. 最近对话
        recent_messages = await self.get_recent_messages(user_id, limit=5)
        
        # 5. 组装上下文
        return [system_prompt, relevant_goals, relevant_memories, recent_messages, user_message]
```

### 4.5 升级任务生成

**变更：**
- 获取用户目标
- AI 综合目标、评分、历史生成任务

```python
async def generate_tasks_for_user(user_id, nickname, db):
    # 1. 获取用户目标
    goals = await goal_service.get_user_goals(user_id)
    
    # 2. 获取用户评分
    scores = await get_user_scores(user_id)
    
    # 3. 获取历史完成情况
    history = await get_completion_history(user_id)
    
    # 4. AI 综合生成任务
    prompt = f"""
    用户目标：{goals}
    用户评分：{scores}
    历史完成：{history}
    
    请生成今日任务...
    """
    task = await ai_generate_task(prompt)
```

---

## 5. API 设计

### 5.1 目标管理 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/goals | 创建目标 |
| GET | /api/goals | 获取目标列表 |
| PUT | /api/goals/{id} | 更新目标 |
| DELETE | /api/goals/{id} | 删除目标 |
| GET | /api/goals/search?query=xxx | 语义搜索目标 |

### 5.2 请求/响应示例

**创建目标：**
```json
POST /api/goals
{
  "content": "每天跑步30分钟",
  "goal_type": "exercise",
  "structured_data": {
    "type": "跑步",
    "duration": 30,
    "frequency": "每天",
    "time": "09:30"
  }
}

Response:
{
  "id": "xxx",
  "content": "每天跑步30分钟",
  "goal_type": "exercise",
  "status": "active",
  "created_at": "2026-05-15T12:00:00"
}
```

**搜索目标：**
```json
GET /api/goals/search?query=跑步

Response:
[
  {
    "id": "xxx",
    "content": "每天跑步30分钟",
    "goal_type": "exercise",
    "similarity": 0.95
  }
]
```

---

## 6. 前端设计

### 6.1 目标管理页面

在"画像"页面增加"我的目标"板块：

```
┌─────────────────────────────────────────┐
│ 我的目标                                │
├─────────────────────────────────────────┤
│ [+] 添加目标                            │
├─────────────────────────────────────────┤
│ 🏃 每天跑步30分钟                        │
│    类型：运动 | 状态：进行中             │
│    [编辑] [删除]                        │
├─────────────────────────────────────────┤
│ 🥗 每天吃5种蔬菜                        │
│    类型：饮食 | 状态：进行中             │
│    [编辑] [删除]                        │
└─────────────────────────────────────────┘
```

---

## 7. 实现阶段

### Phase 1：集成 Embedding API
- 创建 EmbeddingService
- 配置阿里云 API

### Phase 2：升级记忆系统
- 升级 MemoryService，支持向量嵌入
- 升级 ContextBuilder，使用语义搜索

### Phase 3：创建目标管理系统
- 创建 goals 表
- 创建 GoalService
- 实现目标管理 API

### Phase 4：升级任务生成
- 更新 scheduler_service.py
- AI 综合目标生成任务

### Phase 5：前端目标管理
- 在"画像"页面增加目标板块
- 实现目标 CRUD 界面

### Phase 6：聊天自动提取
- 在 chat/router.py 中增加目标提取逻辑
- 自动存储到 goals 表

---

## 8. 测试计划

### 8.1 单元测试
- EmbeddingService 测试
- GoalService 测试
- MemoryService 测试

### 8.2 集成测试
- 语义搜索测试
- 目标管理 API 测试
- 任务生成测试

### 8.3 E2E 测试
- 聊天自动提取目标
- 目标影响任务生成
- 前端目标管理

---

## 9. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 阿里云 API 调用失败 | 无法生成向量 | 降级到关键词搜索 |
| 向量搜索性能差 | 响应慢 | 添加索引，优化查询 |
| 目标提取不准确 | 存储错误目标 | 人工审核机制 |

---

## 10. 成功指标

| 指标 | 目标 |
|------|------|
| 语义搜索准确率 | > 80% |
| 目标提取准确率 | > 70% |
| API 响应时间 | < 500ms |
| 用户满意度 | > 4.0/5.0 |

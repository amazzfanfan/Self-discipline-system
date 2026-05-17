# LiteLLM 集成设计文档

> **日期：** 2026-05-16
> **状态：** 设计中
> **作者：** zengfan

---

## 1. 背景与目标

### 1.1 背景

当前系统使用 httpx 直接调用 AI API，存在以下问题：

- ❌ **无重试机制** - API 调用失败后直接返回错误
- ❌ **无统一接口** - 每个调用点都需要手动构建请求
- ❌ **错误处理不完善** - 429 限流、超时等错误处理不统一
- ❌ **代码重复** - 多个地方重复相同的调用代码

### 1.2 目标

- 使用 litellm 统一 LLM 调用接口
- 支持多模型配置（主模型 + 备用模型）
- 实现自动重试机制（最多 3 次）
- 统一错误处理和降级策略
- 独立系统提示词管理

---

## 2. 架构设计

### 2.1 整体架构

```
用户消息
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Chat Router                                                │
│  - 接收用户消息                                               │
│  - 调用意图识别                                               │
│  - 调用聊天功能                                               │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Prompt Service (新增)                                       │
│  - 系统提示词构建                                             │
│  - 任务提示词构建                                             │
│  - 评估提示词构建                                             │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  LLM Service (修改)                                         │
│  - 统一 LLM 调用接口                                         │
│  - 多模型支持（主模型、备用模型）                             │
│  - 自动重试机制                                               │
│  - 错误处理和降级                                             │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  AI Service (修改)                                          │
│  - 移除 LLM 调用代码                                         │
│  - 只保留业务逻辑                                             │
│  - 调用 llm_service                                          │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 文件结构

```
backend/app/services/
├── llm_service.py          # 修改：添加多模型支持
├── prompt_service.py       # 新增：系统提示词
├── ai_service.py           # 修改：移除 LLM 调用
├── memory_service.py       # 保持不变
├── context_builder.py      # 保持不变
└── ...
```

---

## 3. 详细设计

### 3.1 Prompt Service（新增）

#### 3.1.1 职责

- 构建系统提示词
- 构建任务生成提示词
- 构建评估提示词
- 构建意图识别提示词

#### 3.1.2 代码结构

```python
# prompt_service.py

class PromptService:
    """提示词服务"""
    
    def build_system_prompt(self, user_context: str = "") -> str:
        """构建系统提示词"""
        pass
    
    def build_task_prompt(self, dimension: str, score: float, difficulty: str, ...) -> str:
        """构建任务生成提示词"""
        pass
    
    def build_evaluation_prompt(self, height: float, weight: float, ...) -> str:
        """构建评估提示词"""
        pass
    
    def build_intent_prompt(self, content: str) -> str:
        """构建意图识别提示词"""
        pass
```

### 3.2 LLM Service（修改）

#### 3.2.1 职责

- 统一 LLM 调用接口
- 多模型支持（主模型、备用模型）
- 自动重试机制
- 错误处理和降级

#### 3.2.2 多模型配置

```python
# .env 文件
LLM_PRIMARY_MODEL=mimo-v2.5
LLM_FALLBACK_MODEL=gpt-3.5-turbo
LLM_MAX_RETRIES=3
LLM_TIMEOUT=30
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=1500
```

#### 3.2.3 代码结构

```python
# llm_service.py

class LLMService:
    """统一的 LLM 调用服务"""
    
    def __init__(self):
        self.primary_model = settings.LLM_PRIMARY_MODEL
        self.fallback_model = settings.LLM_FALLBACK_MODEL
        self.max_retries = settings.LLM_MAX_RETRIES
        self.timeout = settings.LLM_TIMEOUT
    
    async def chat_completion(self, messages: list[dict], **kwargs) -> str:
        """非流式调用"""
        pass
    
    async def chat_completion_stream(self, messages: list[dict], **kwargs) -> AsyncGenerator[str, None]:
        """流式调用"""
        pass
    
    async def get_embedding(self, text: str) -> list[float]:
        """获取向量嵌入"""
        pass
    
    async def _retry_with_fallback(self, func, *args, **kwargs):
        """重试机制 + 降级策略"""
        pass
```

### 3.3 AI Service（修改）

#### 3.3.1 职责

- 移除 LLM 调用代码
- 只保留业务逻辑
- 调用 llm_service

#### 3.3.2 修改内容

```python
# ai_service.py（修改后）

from app.services.llm_service import llm_service
from app.services.prompt_service import prompt_service

async def detect_intent(content: str) -> dict:
    """意图识别"""
    prompt = prompt_service.build_intent_prompt(content)
    response = await llm_service.chat_completion(
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    return json.loads(response)

async def generate_task(nickname: str, dimension: str, ...) -> str:
    """任务生成"""
    prompt = prompt_service.build_task_prompt(...)
    response = await llm_service.chat_completion(
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    return json.loads(response).get("task", "")
```

---

## 4. 错误处理

### 4.1 重试机制

```
LLM 调用
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  第 1 次尝试（主模型）                                        │
│  - 成功 → 返回结果                                           │
│  - 失败 → 等待 2 秒，重试                                    │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  第 2 次尝试（主模型）                                        │
│  - 成功 → 返回结果                                           │
│  - 失败 → 等待 4 秒，重试                                    │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  第 3 次尝试（主模型）                                        │
│  - 成功 → 返回结果                                           │
│  - 失败 → 切换备用模型                                        │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  备用模型尝试                                                 │
│  - 成功 → 返回结果                                           │
│  - 失败 → 返回降级回复                                        │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 降级回复

```python
DEFAULT_RESPONSES = {
    "chat": "当前 AI 不可用，请稍后再试。",
    "intent": {"intent": "chat"},
    "task": "完成今日任务",
    "evaluation": {"exercise": 50, "diet": 50, "sleep": 50, "appearance": 50},
}
```

---

## 5. 集成点

### 5.1 需要修改的文件

| 文件 | 修改内容 |
|------|----------|
| `ai_service.py` | 移除 LLM 调用代码，调用 llm_service |
| `llm_service.py` | 添加多模型支持、重试机制 |
| `chat/router.py` | 使用新的 llm_service |
| `user/router.py` | 使用新的 llm_service |
| `scheduler_service.py` | 使用新的 llm_service |

### 5.2 不需要修改的文件

| 文件 | 说明 |
|------|------|
| `memory_service.py` | 已经使用 llm_service |
| `context_builder.py` | 不直接调用 LLM |
| `memory_judge.py` | 已经使用 HybridMemoryJudge |

---

## 6. 测试策略

### 6.1 单元测试

```python
# test_llm_service.py

async def test_chat_completion():
    """测试非流式调用"""
    pass

async def test_chat_completion_stream():
    """测试流式调用"""
    pass

async def test_retry_mechanism():
    """测试重试机制"""
    pass

async def test_fallback_model():
    """测试备用模型"""
    pass
```

### 6.2 集成测试

```bash
# 测试聊天功能
curl -X POST "http://localhost:8000/api/chat/send?content=你好" \
  -H "Authorization: Bearer $TOKEN"

# 测试意图识别
curl -X POST "http://localhost:8000/api/chat/send?content=完成今天的运动任务" \
  -H "Authorization: Bearer $TOKEN"

# 测试任务生成
curl -X POST "http://localhost:8000/api/tasks/generate" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 7. 实施计划

### 7.1 阶段划分

| 阶段 | 任务 | 时间 |
|------|------|------|
| Phase 1 | 创建 PromptService | 1 小时 |
| Phase 2 | 修改 LLMService | 2 小时 |
| Phase 3 | 修改 AI Service | 2 小时 |
| Phase 4 | 修改 Chat Router | 1 小时 |
| Phase 5 | 测试和验证 | 2 小时 |

### 7.2 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/services/prompt_service.py` | 新增 | 系统提示词服务 |
| `backend/app/services/llm_service.py` | 修改 | 添加多模型支持 |
| `backend/app/services/ai_service.py` | 修改 | 移除 LLM 调用 |
| `backend/app/modules/chat/router.py` | 修改 | 使用新的 llm_service |
| `backend/app/core/config.py` | 修改 | 添加多模型配置 |

---

## 8. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| litellm 兼容性问题 | 无法调用 API | 测试 API 兼容性 |
| 多模型配置错误 | 无法切换模型 | 验证配置正确性 |
| 重试机制失效 | 无法自动重试 | 测试重试逻辑 |
| 性能问题 | 响应变慢 | 监控性能指标 |

---

## 9. 总结

本设计方案将完全替换现有的 httpx 直接调用，使用 litellm 统一 LLM 调用接口。通过多模型支持、自动重试机制和统一错误处理，提升系统的可靠性和可维护性。

**核心优势：**
- ✅ 统一接口 - 所有 LLM 调用使用同一套代码
- ✅ 自动重试 - 最多重试 3 次，支持备用模型
- ✅ 错误处理 - 统一的降级策略
- ✅ 易于维护 - 代码结构清晰，职责明确

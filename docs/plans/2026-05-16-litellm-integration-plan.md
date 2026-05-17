# LiteLLM 集成实现计划

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 集成 LiteLLM 到系统中，统一 LLM 调用接口，支持多模型、自动重试和错误处理

**Architecture:** 使用 LiteLLM 统一接口，支持主模型和备用模型，实现自动重试和降级策略

**Tech Stack:** Python, FastAPI, LiteLLM, httpx

---

## Phase 1: 创建 PromptService

### Task 1.1: 创建 prompt_service.py

**Objective:** 创建系统提示词服务，将提示词逻辑从 ai_service.py 中独立出来

**Files:**
- Create: `backend/app/services/prompt_service.py`

**Step 1: 创建 prompt_service.py 文件**

```python
"""
Prompt Service - 提示词服务
负责构建各种提示词，包括系统提示、任务提示、评估提示等
"""

from datetime import datetime, timezone, timedelta
from app.core.config import get_settings
import logging

logger = logging.getLogger(__name__)
settings = get_settings()

BJT = timezone(timedelta(hours=8))


class PromptService:
    """提示词服务"""
    
    # 系统提示词
    SYSTEM_PROMPT = """你是一个名为"系统"的AI助手，灵感来源于小说中的成长系统。你的职责是帮助用户提升自己。
你不是朋友，不是医生，而是一个严格但关怀的引导者。你用数据说话，用鼓励驱动，偶尔带一点幽默。
你相信持续的小进步会带来大变化。

对话原则：
- 不批评，不说教，用数据和事实引导
- 承认人性，偶尔放松是正常的
- 关注趋势，单次失败不代表失败
- 主动关怀，检测到异常时主动询问
- 保持人设，始终以"系统"身份对话
- 绝对不要输出你的思考过程、推理步骤或内心独白，只输出面向用户的回复内容"""
    
    # 意图识别提示词
    INTENT_PROMPT = """分析用户消息意图，返回JSON格式：
{
  "intent": "complete_task|skip_task|record_weight|chat",
  "task_keyword": "关键词（如果是完成任务）",
  "weight": 数字（如果是记录体重）
}

用户消息：{content}

请只返回 JSON，不要有其他内容。"""
    
    # 任务生成提示词
    TASK_PROMPT = """请为用户生成1个{dimension}维度的今日任务。
难度：{difficulty}，当前评分：{score}分，最近做过的：{recent}（避免重复）。
要求：具体可执行，有明确完成标准。

重要：{dim_guide}
用户目标：{goal_content}
请生成与该目标相关的任务，帮助用户逐步实现目标。

返回JSON格式：{{"task": "任务标题"}}"""
    
    # 评估提示词
    EVALUATION_PROMPT = """根据用户的身体数据和问卷回答，评估四个维度的分数（0-100）：
- exercise: 运动维度
- diet: 饮食维度
- sleep: 睡眠维度
- appearance: 外貌维度

身体数据：身高{height}cm，体重{weight}kg，BMI {bmi}，{age}岁，{gender_cn}

问卷回答：
- 运动：{exercise_answer}
- 饮食：{diet_answer}
- 睡眠：{sleep_answer}
- 外貌：{appearance_answer}

返回JSON格式：{{"exercise": 分数, "diet": 分数, "sleep": 分数, "appearance": 分数}}"""
    
    def build_system_prompt(self, user_context: str = "") -> str:
        """
        构建系统提示词
        
        Args:
            user_context: 用户上下文信息
            
        Returns:
            完整的系统提示词
        """
        now = datetime.now(BJT)
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        time_str = now.strftime(f"%Y年%m月%d日 %H:%M {weekdays[now.weekday()]}")
        
        system_msg = self.SYSTEM_PROMPT + f"\n\n当前时间（北京时间）：{time_str}"
        if user_context:
            system_msg += f"\n\n用户上下文：{user_context}"
        
        return system_msg
    
    def build_intent_prompt(self, content: str) -> str:
        """
        构建意图识别提示词
        
        Args:
            content: 用户消息内容
            
        Returns:
            意图识别提示词
        """
        return self.INTENT_PROMPT.format(content=content)
    
    def build_task_prompt(
        self,
        dimension: str,
        score: float,
        difficulty: str,
        recent_tasks: list[str],
        goal_content: str = None
    ) -> str:
        """
        构建任务生成提示词
        
        Args:
            dimension: 维度名称
            score: 当前评分
            difficulty: 难度级别
            recent_tasks: 最近的任务列表
            goal_content: 用户目标内容
            
        Returns:
            任务生成提示词
        """
        recent = "、".join(recent_tasks[-5:]) if recent_tasks else "无"
        diff_cn = {"easy": "简单", "medium": "中等", "hard": "困难"}.get(difficulty, "中等")
        
        # 维度指南
        dim_guides = {
            "exercise": "运动类任务：体育锻炼、健身、跑步、跳绳、俯卧撑、深蹲、瑜伽、拉伸、散步、骑车、游泳等身体活动。",
            "diet": "饮食类任务：健康饮食、喝水、记录饮食、少吃零食、多吃蔬菜、控制热量、少油少盐等饮食相关。",
            "sleep": "睡眠类任务：早睡、放下手机、冥想、深呼吸、睡前放松、避免熬夜等睡眠相关。",
            "appearance": "外貌类任务：护肤、防晒、清洁面部、使用眼霜、敷面膜、整理仪容等外貌护理相关。",
        }
        dim_guide = dim_guides.get(dimension, "")
        
        # 目标上下文
        goal_context = ""
        if goal_content:
            goal_context = f"\n用户目标：{goal_content}\n请生成与该目标相关的任务，帮助用户逐步实现目标。\n"
        
        return self.TASK_PROMPT.format(
            dimension=dimension,
            difficulty=diff_cn,
            score=score,
            recent=recent,
            dim_guide=dim_guide,
            goal_content=goal_context
        )
    
    def build_evaluation_prompt(
        self,
        height: float,
        weight: float,
        age: int,
        gender: str,
        questionnaire: dict
    ) -> str:
        """
        构建评估提示词
        
        Args:
            height: 身高
            weight: 体重
            age: 年龄
            gender: 性别
            questionnaire: 问卷答案
            
        Returns:
            评估提示词
        """
        bmi = weight / (height / 100) ** 2
        gender_cn = {"male": "男", "female": "女"}.get(gender, "其他")
        
        return self.EVALUATION_PROMPT.format(
            height=height,
            weight=weight,
            bmi=f"{bmi:.1f}",
            age=age,
            gender_cn=gender_cn,
            exercise_answer=questionnaire.get("exercise", "未回答"),
            diet_answer=questionnaire.get("diet", "未回答"),
            sleep_answer=questionnaire.get("sleep", "未回答"),
            appearance_answer=questionnaire.get("appearance", "未回答")
        )


# 全局实例
prompt_service = PromptService()
```

**Step 2: 验证代码语法**

Run: `cd /mnt/d/zf/agent/系统/backend && python -m py_compile app/services/prompt_service.py`
Expected: 无输出（语法正确）

**Step 3: Commit**

```bash
cd /mnt/d/zf/agent/系统/backend
git add app/services/prompt_service.py
git commit -m "feat: add PromptService for centralized prompt management"
```

---

## Phase 2: 修改 LLMService

### Task 2.1: 添加多模型支持

**Objective:** 修改 llm_service.py，添加多模型支持和重试机制

**Files:**
- Modify: `backend/app/services/llm_service.py`
- Modify: `backend/app/core/config.py`

**Step 1: 更新 config.py 添加多模型配置**

在 `config.py` 中添加：

```python
# LLM 配置
LLM_PRIMARY_MODEL: str = "mimo-v2.5"
LLM_FALLBACK_MODEL: str = "gpt-3.5-turbo"
LLM_MAX_RETRIES: int = 3
LLM_TIMEOUT: int = 30
LLM_TEMPERATURE: float = 0.7
LLM_MAX_TOKENS: int = 1500
```

**Step 2: 修改 llm_service.py**

```python
"""
LLM Service - 统一的 LLM 调用接口
使用 LiteLLM 提供统一的 API，支持重试、流式输出、多模型等功能
"""

import litellm
from litellm import acompletion
from app.core.config import get_settings
from typing import AsyncGenerator, Optional
import logging
import asyncio

logger = logging.getLogger(__name__)
settings = get_settings()

# 配置 LiteLLM
litellm.num_retries = settings.LLM_MAX_RETRIES
litellm.request_timeout = settings.LLM_TIMEOUT
litellm.drop_params = True  # 忽略不支持的参数

# 默认降级回复
DEFAULT_RESPONSES = {
    "chat": "当前 AI 不可用，请稍后再试。",
    "intent": {"intent": "chat"},
    "task": "完成今日任务",
    "evaluation": {"exercise": 50, "diet": 50, "sleep": 50, "appearance": 50},
}


class LLMService:
    """统一的 LLM 调用服务"""
    
    def __init__(self):
        self.primary_model = settings.LLM_PRIMARY_MODEL
        self.fallback_model = settings.LLM_FALLBACK_MODEL
        self.max_retries = settings.LLM_MAX_RETRIES
        self.timeout = settings.LLM_TIMEOUT
        self.temperature = settings.LLM_TEMPERATURE
        self.max_tokens = settings.LLM_MAX_TOKENS
    
    async def chat_completion(
        self,
        messages: list[dict],
        model: str = None,
        temperature: float = None,
        max_tokens: int = None,
        response_format: dict = None
    ) -> str:
        """
        非流式 LLM 调用
        
        Args:
            messages: 消息列表
            model: 模型名称（可选，默认使用主模型）
            temperature: 温度参数（可选）
            max_tokens: 最大 token 数（可选）
            response_format: 响应格式（可选，如 JSON）
        
        Returns:
            AI 回复内容
        """
        model = model or self.primary_model
        temperature = temperature or self.temperature
        max_tokens = max_tokens or self.max_tokens
        
        try:
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if response_format:
                kwargs["response_format"] = response_format
            
            logger.info(f"Calling LLM: model={model}, messages={len(messages)}")
            response = await acompletion(**kwargs)
            
            content = response.choices[0].message.content
            logger.info(f"LLM response received: {len(content)} chars")
            
            return content
            
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
        self,
        messages: list[dict],
        model: str = None,
        temperature: float = None,
        max_tokens: int = None
    ) -> AsyncGenerator[str, None]:
        """
        流式 LLM 调用
        
        Args:
            messages: 消息列表
            model: 模型名称（可选）
            temperature: 温度参数（可选）
            max_tokens: 最大 token 数（可选）
        
        Yields:
            AI 回复的内容块
        """
        model = model or self.primary_model
        temperature = temperature or self.temperature
        max_tokens = max_tokens or self.max_tokens
        
        try:
            logger.info(f"Calling LLM (stream): model={model}")
            
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
    
    async def chat_completion_with_fallback(
        self,
        messages: list[dict],
        response_format: dict = None
    ) -> str:
        """
        带降级的 LLM 调用
        
        Args:
            messages: 消息列表
            response_format: 响应格式（可选）
        
        Returns:
            AI 回复内容
        """
        # 尝试主模型
        try:
            return await self.chat_completion(
                messages=messages,
                model=self.primary_model,
                response_format=response_format
            )
        except Exception as e:
            logger.warning(f"Primary model failed: {e}")
        
        # 尝试备用模型
        try:
            logger.info(f"Trying fallback model: {self.fallback_model}")
            return await self.chat_completion(
                messages=messages,
                model=self.fallback_model,
                response_format=response_format
            )
        except Exception as e:
            logger.error(f"Fallback model failed: {e}")
        
        # 所有模型都失败，返回降级回复
        logger.error("All models failed, returning default response")
        return DEFAULT_RESPONSES.get("chat", "当前 AI 不可用，请稍后再试。")
    
    async def get_embedding(
        self,
        text: str,
        model: str = None
    ) -> list[float]:
        """
        获取文本的向量嵌入
        
        Args:
            text: 输入文本
            model: 嵌入模型名称（可选）
        
        Returns:
            向量嵌入列表
        """
        model = model or settings.EMBEDDING_MODEL
        
        try:
            from openai import AsyncOpenAI
            
            client = AsyncOpenAI(
                api_key=settings.EMBEDDING_API_KEY,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            )
            
            logger.info(f"Getting embedding for text: {len(text)} chars")
            
            response = await client.embeddings.create(
                model=model,
                input=text,
            )
            
            embedding = response.data[0].embedding
            logger.info(f"Embedding received: dimension={len(embedding)}")
            
            return embedding
            
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            raise


# 全局实例
llm_service = LLMService()
```

**Step 3: 验证代码语法**

Run: `cd /mnt/d/zf/agent/系统/backend && python -m py_compile app/services/llm_service.py`
Expected: 无输出（语法正确）

**Step 4: Commit**

```bash
cd /mnt/d/zf/agent/系统/backend
git add app/services/llm_service.py app/core/config.py
git commit -m "feat: add multi-model support and fallback to LLMService"
```

---

## Phase 3: 修改 AI Service

### Task 3.1: 移除 LLM 调用代码

**Objective:** 修改 ai_service.py，移除 LLM 调用代码，只保留业务逻辑

**Files:**
- Modify: `backend/app/services/ai_service.py`

**Step 1: 修改 ai_service.py**

```python
"""
AI Service - 业务逻辑服务
只保留业务逻辑，LLM 调用使用 llm_service
"""

import json
import logging
from app.services.llm_service import llm_service
from app.services.prompt_service import prompt_service
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def detect_intent(content: str) -> dict:
    """
    意图识别
    
    Args:
        content: 用户消息内容
        
    Returns:
        意图识别结果
    """
    try:
        prompt = prompt_service.build_intent_prompt(content)
        response = await llm_service.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return json.loads(response)
    except Exception as e:
        logger.error(f"Intent detection failed: {e}")
        return {"intent": "chat"}


async def generate_task(
    nickname: str,
    dimension: str,
    score: float,
    difficulty: str,
    recent_tasks: list[str],
    goal_content: str = None
) -> str:
    """
    任务生成
    
    Args:
        nickname: 用户昵称
        dimension: 维度名称
        score: 当前评分
        difficulty: 难度级别
        recent_tasks: 最近的任务列表
        goal_content: 用户目标内容
        
    Returns:
        任务标题
    """
    try:
        prompt = prompt_service.build_task_prompt(
            dimension=dimension,
            score=score,
            difficulty=difficulty,
            recent_tasks=recent_tasks,
            goal_content=goal_content
        )
        
        response = await llm_service.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response)
        task_title = result.get("task", "")
        
        # 清理任务标题
        task_title = _clean_task_title(task_title)
        
        return task_title if task_title else "完成今日任务"
        
    except Exception as e:
        logger.error(f"Task generation failed: {e}")
        return "完成今日任务"


async def evaluate_scores(
    height: float,
    weight: float,
    age: int,
    gender: str,
    questionnaire: dict
) -> dict:
    """
    评估分数
    
    Args:
        height: 身高
        weight: 体重
        age: 年龄
        gender: 性别
        questionnaire: 问卷答案
        
    Returns:
        四维评分
    """
    try:
        prompt = prompt_service.build_evaluation_prompt(
            height=height,
            weight=weight,
            age=age,
            gender=gender,
            questionnaire=questionnaire
        )
        
        response = await llm_service.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response)
        return {
            "exercise": min(100, max(0, float(result.get("exercise", 50)))),
            "diet": min(100, max(0, float(result.get("diet", 50)))),
            "sleep": min(100, max(0, float(result.get("sleep", 50)))),
            "appearance": min(100, max(0, float(result.get("appearance", 50)))),
        }
        
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        return {"exercise": 50, "diet": 50, "sleep": 50, "appearance": 50}


def _clean_task_title(task_title: str) -> str:
    """
    清理任务标题
    
    Args:
        task_title: 原始任务标题
        
    Returns:
        清理后的任务标题
    """
    if not task_title:
        return ""
    
    # 移除引号
    task_title = task_title.strip('"\'')
    
    # 移除多余空格
    task_title = " ".join(task_title.split())
    
    # 截断过长的标题
    if len(task_title) > 200:
        task_title = task_title[:200] + "..."
    
    return task_title
```

**Step 2: 验证代码语法**

Run: `cd /mnt/d/zf/agent/系统/backend && python -m py_compile app/services/ai_service.py`
Expected: 无输出（语法正确）

**Step 3: Commit**

```bash
cd /mnt/d/zf/agent/系统/backend
git add app/services/ai_service.py
git commit -m "refactor: remove LLM calls from ai_service, use llm_service"
```

---

## Phase 4: 修改 Chat Router

### Task 4.1: 更新 Chat Router

**Objective:** 修改 chat/router.py，使用新的 llm_service

**Files:**
- Modify: `backend/app/modules/chat/router.py`

**Step 1: 修改 chat/router.py**

```python
"""
Chat Router - 聊天路由
使用新的 llm_service 进行 LLM 调用
"""

from app.services.llm_service import llm_service
from app.services.prompt_service import prompt_service
from app.services.ai_service import detect_intent


async def send_message(
    content: str,
    user: User,
    db: AsyncSession
) -> dict:
    """
    发送消息
    
    Args:
        content: 消息内容
        user: 用户对象
        db: 数据库会话
        
    Returns:
        AI 回复
    """
    # 1. 意图识别
    intent_result = await detect_intent(content)
    
    # 2. 构建上下文
    context_builder = ContextBuilder(db, user)
    messages = await context_builder.build_context_with_action(
        user_message=content,
        action_context="",
        include_recent=True,
        include_relevant=True
    )
    
    # 3. 调用 LLM（带降级）
    ai_reply = await llm_service.chat_completion_with_fallback(messages)
    
    # 4. 保存对话
    # ... 保存逻辑 ...
    
    return {"reply": ai_reply}
```

**Step 2: 验证代码语法**

Run: `cd /mnt/d/zf/agent/系统/backend && python -m py_compile app/modules/chat/router.py`
Expected: 无输出（语法正确）

**Step 3: Commit**

```bash
cd /mnt/d/zf/agent/系统/backend
git add app/modules/chat/router.py
git commit -m "refactor: update chat router to use llm_service"
```

---

## Phase 5: 测试和验证

### Task 5.1: 测试所有功能

**Objective:** 测试所有功能是否正常工作

**Files:**
- 测试文件：`backend/tests/test_llm_service.py`

**Step 1: 创建测试文件**

```python
"""
测试 LLM Service
"""

import pytest
from app.services.llm_service import llm_service
from app.services.prompt_service import prompt_service


@pytest.mark.asyncio
async def test_chat_completion():
    """测试非流式调用"""
    messages = [{"role": "user", "content": "你好"}]
    response = await llm_service.chat_completion(messages)
    assert response is not None
    assert len(response) > 0


@pytest.mark.asyncio
async def test_chat_completion_stream():
    """测试流式调用"""
    messages = [{"role": "user", "content": "你好"}]
    chunks = []
    async for chunk in llm_service.chat_completion_stream(messages):
        chunks.append(chunk)
    assert len(chunks) > 0


@pytest.mark.asyncio
async def test_chat_completion_with_fallback():
    """测试带降级的调用"""
    messages = [{"role": "user", "content": "你好"}]
    response = await llm_service.chat_completion_with_fallback(messages)
    assert response is not None
    assert len(response) > 0


def test_build_system_prompt():
    """测试系统提示词构建"""
    prompt = prompt_service.build_system_prompt()
    assert "系统" in prompt
    assert "北京时间" in prompt


def test_build_intent_prompt():
    """测试意图识别提示词构建"""
    prompt = prompt_service.build_intent_prompt("完成今天的运动任务")
    assert "完成今天的运动任务" in prompt


def test_build_task_prompt():
    """测试任务生成提示词构建"""
    prompt = prompt_service.build_task_prompt(
        dimension="exercise",
        score=50,
        difficulty="medium",
        recent_tasks=["跑步30分钟"]
    )
    assert "exercise" in prompt
    assert "中等" in prompt
```

**Step 2: 运行测试**

Run: `cd /mnt/d/zf/agent/系统/backend && python -m pytest tests/test_llm_service.py -v`
Expected: 所有测试通过

**Step 3: 测试 API**

```bash
# 启动后端服务
cd /mnt/d/zf/agent/系统/backend
uvicorn app.main:app --reload --port 8000

# 测试聊天功能
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "test123456"}' | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)

curl -s -X POST "http://localhost:8000/api/chat/send?content=你好" \
  -H "Authorization: Bearer $TOKEN"
```

**Step 4: Commit**

```bash
cd /mnt/d/zf/agent/系统/backend
git add tests/test_llm_service.py
git commit -m "test: add tests for LLMService and PromptService"
```

---

## 执行顺序

1. **Phase 1:** 创建 PromptService（Task 1.1）
2. **Phase 2:** 修改 LLMService（Task 2.1）
3. **Phase 3:** 修改 AI Service（Task 3.1）
4. **Phase 4:** 修改 Chat Router（Task 4.1）
5. **Phase 5:** 测试和验证（Task 5.1）

---

## 验证命令

```bash
# 验证所有文件语法
cd /mnt/d/zf/agent/系统/backend
python -m py_compile app/services/prompt_service.py
python -m py_compile app/services/llm_service.py
python -m py_compile app/services/ai_service.py
python -m py_compile app/modules/chat/router.py

# 运行测试
python -m pytest tests/test_llm_service.py -v

# 启动服务测试
uvicorn app.main:app --reload --port 8000
```

# 记忆判断优化实现计划

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 优化记忆判断系统，从简单的关键词匹配升级为混合判断策略（规则过滤 + LLM 判断），并添加记忆重要性评分和衰减机制

**Architecture:** 采用分层架构，第一层快速规则过滤（< 1ms），第二层 LLM 深度判断（100-500ms），配合重要性评分和衰减机制

**Tech Stack:** Python, FastAPI, SQLAlchemy, httpx (LLM API)

---

## Phase 1: 创建规则过滤器

### Task 1.1: 创建 RuleBasedFilter 类

**Objective:** 实现快速规则过滤器，支持 20 条高优先级规则和 13 条低优先级规则

**Files:**
- Create: `backend/app/services/memory_judge.py`

**Step 1: 创建 memory_judge.py 文件**

```python
"""
Memory Judge - 记忆判断系统
采用混合判断策略：快速规则过滤 + LLM 深度判断
"""

import re
import json
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class RuleBasedFilter:
    """
    快速规则过滤器（严格策略）
    执行时间：< 1ms
    """
    
    # 明确要记住的模式（高优先级）
    HIGH_PRIORITY_PATTERNS = [
        # 用户目标
        (r"我的目标是", "goal", 0.95),
        (r"我计划", "goal", 0.9),
        (r"我打算", "goal", 0.9),
        (r"我想要", "goal", 0.85),
        (r"我准备", "goal", 0.85),
        
        # 用户偏好
        (r"我喜欢", "preference", 0.9),
        (r"我讨厌", "preference", 0.9),
        (r"我习惯", "preference", 0.9),
        (r"我偏好", "preference", 0.9),
        (r"我最爱", "preference", 0.9),
        
        # 个人信息
        (r"我养了", "personal", 0.95),
        (r"我住在", "personal", 0.95),
        (r"我工作", "personal", 0.9),
        (r"我生日", "personal", 0.95),
        (r"我年龄", "personal", 0.9),
        (r"我家庭", "personal", 0.9),
        
        # 健康数据
        (r"我体重", "health", 0.9),
        (r"我身高", "health", 0.9),
        (r"我血压", "health", 0.9),
        (r"我血糖", "health", 0.9),
    ]
    
    # 明确不记住的模式（低优先级）
    LOW_PRIORITY_PATTERNS = [
        # 询问 AI 能力
        (r"^你[有能会]", 0.1),
        (r"^你是", 0.1),
        
        # 临时请求
        (r"^帮我", 0.2),
        (r"^请帮", 0.2),
        (r"^麻烦", 0.2),
        
        # 通用问题
        (r"^什么是", 0.1),
        (r"^怎么", 0.15),
        (r"^为什么", 0.15),
        (r"^如何", 0.15),
        
        # 临时确认
        (r"^好的$", 0.05),
        (r"^嗯$", 0.05),
        (r"^谢谢", 0.1),
        (r"^感谢", 0.1),
    ]
    
    def filter(self, content: str) -> Optional[Tuple[bool, float, str]]:
        """
        快速规则过滤
        
        Args:
            content: 用户消息内容
            
        Returns:
            - None: 不确定，交给 LLM 判断
            - (should_remember, importance, memory_type): 明确结果
        """
        # 检查高优先级模式
        for pattern, memory_type, importance in self.HIGH_PRIORITY_PATTERNS:
            if re.search(pattern, content):
                logger.info(f"Rule matched (high): {pattern} -> {memory_type}")
                return (True, importance, memory_type)
        
        # 检查低优先级模式
        for pattern, importance in self.LOW_PRIORITY_PATTERNS:
            if re.search(pattern, content):
                logger.info(f"Rule matched (low): {pattern} -> {importance}")
                return (False, importance, None)
        
        # 不确定，交给 LLM
        return None
```

**Step 2: 验证代码语法**

Run: `cd /mnt/d/zf/agent/系统/backend && python -m py_compile app/services/memory_judge.py`
Expected: 无输出（语法正确）

**Step 3: Commit**

```bash
cd /mnt/d/zf/agent/系统/backend
git add app/services/memory_judge.py
git commit -m "feat: add RuleBasedFilter for fast memory judgment"
```

---

## Phase 2: 创建 LLM 判断器

### Task 2.1: 实现 LLMBasedJudge 类

**Objective:** 实现 LLM 深度判断器，处理规则过滤器无法确定的消息

**Files:**
- Modify: `backend/app/services/memory_judge.py`

**Step 1: 添加 LLMBasedJudge 类**

在 `memory_judge.py` 文件末尾添加：

```python
class LLMBasedJudge:
    """
    LLM 深度判断器
    执行时间：100-500ms
    """
    
    JUDGE_PROMPT = """
你是一个记忆管理专家。判断以下对话内容是否值得长期记住。

值得记住的信息：
- 用户的偏好和习惯（我喜欢、我讨厌、我习惯）
- 用户的目标和计划（我的目标是、我计划、我打算）
- 用户的个人信息（我养了、我住在、我工作、我生日）
- 用户的健康数据（我体重、我身高、我血压）
- 重要的事实和数据

不值得记住的信息：
- 临时性的问题（帮我查、帮我算）
- 已经过时的信息
- 重复的内容
- 无关紧要的细节
- 询问 AI 能力的问题

用户消息：{content}

返回 JSON 格式：
{{
    "remember": true/false,
    "importance": 0.0-1.0,
    "memory_type": "preference/fact/goal/personal/health/other",
    "reason": "判断理由"
}}
"""
    
    def __init__(self, llm_client):
        """
        初始化 LLM 判断器
        
        Args:
            llm_client: LLM 客户端（需要有 complete 方法）
        """
        self.llm = llm_client
    
    async def judge(self, content: str) -> Tuple[bool, float, str]:
        """
        使用 LLM 判断是否值得记住
        
        Args:
            content: 用户消息内容
            
        Returns:
            (should_remember, importance, memory_type)
        """
        try:
            prompt = self.JUDGE_PROMPT.format(content=content)
            response = await self.llm.complete(prompt)
            
            # 解析 JSON 响应
            result = json.loads(response)
            
            return (
                result.get("remember", False),
                result.get("importance", 0.5),
                result.get("memory_type", "other")
            )
        except Exception as e:
            logger.error(f"LLM judge failed: {e}")
            # 降级：默认不记住
            return (False, 0.3, "other")
```

**Step 2: 验证代码语法**

Run: `cd /mnt/d/zf/agent/系统/backend && python -m py_compile app/services/memory_judge.py`
Expected: 无输出（语法正确）

**Step 3: Commit**

```bash
cd /mnt/d/zf/agent/系统/backend
git add app/services/memory_judge.py
git commit -m "feat: add LLMBasedJudge for semantic memory judgment"
```

---

## Phase 3: 创建重要性评分器

### Task 3.1: 实现 MemoryImportanceScorer 类

**Objective:** 实现记忆重要性评分系统，综合规则分、语义分和行为分

**Files:**
- Create: `backend/app/services/memory_scorer.py`

**Step 1: 创建 memory_scorer.py 文件**

```python
"""
Memory Scorer - 记忆重要性评分系统
综合评分 = 规则分(0.3) + 语义分(0.5) + 行为分(0.2)
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class MemoryImportanceScorer:
    """
    记忆重要性评分系统
    """
    
    # 高优先级关键词
    HIGH_PRIORITY_KEYWORDS = [
        "目标", "计划", "喜欢", "讨厌", "习惯", "生日", "养了",
        "住在", "工作", "家庭", "体重", "身高", "血压", "血糖"
    ]
    
    # 中优先级关键词
    MEDIUM_PRIORITY_KEYWORDS = [
        "想要", "准备", "打算", "偏好", "最爱"
    ]
    
    def score(self, content: str, context: Dict[str, Any] = None) -> float:
        """
        计算记忆重要性评分
        
        Args:
            content: 记忆内容
            context: 上下文信息（可选）
            
        Returns:
            重要性评分（0.0-1.0）
        """
        if context is None:
            context = {}
        
        # 1. 规则分（0-1）
        rule_score = self._rule_score(content)
        
        # 2. 语义分（0-1，来自 LLM 判断）
        semantic_score = context.get("semantic_score", 0.5)
        
        # 3. 行为分（0-1）
        behavior_score = self._behavior_score(context)
        
        # 综合评分
        final_score = (
            rule_score * 0.3 +
            semantic_score * 0.5 +
            behavior_score * 0.2
        )
        
        return min(1.0, max(0.0, final_score))
    
    def _rule_score(self, content: str) -> float:
        """
        基于规则的评分
        
        Args:
            content: 记忆内容
            
        Returns:
            规则分（0-1）
        """
        # 检查高优先级关键词
        if any(kw in content for kw in self.HIGH_PRIORITY_KEYWORDS):
            return 1.0
        
        # 检查中优先级关键词
        if any(kw in content for kw in self.MEDIUM_PRIORITY_KEYWORDS):
            return 0.6
        
        # 默认分数
        return 0.3
    
    def _behavior_score(self, context: Dict[str, Any]) -> float:
        """
        基于用户行为的评分
        
        Args:
            context: 上下文信息
            
        Returns:
            行为分（0-1）
        """
        # 用户是否重复提及
        if context.get("repeat_count", 0) > 1:
            return 0.9
        
        # 用户是否强调
        if context.get("emphasized", False):
            return 0.8
        
        # 默认分数
        return 0.5
```

**Step 2: 验证代码语法**

Run: `cd /mnt/d/zf/agent/系统/backend && python -m py_compile app/services/memory_scorer.py`
Expected: 无输出（语法正确）

**Step 3: Commit**

```bash
cd /mnt/d/zf/agent/系统/backend
git add app/services/memory_scorer.py
git commit -m "feat: add MemoryImportanceScorer for importance scoring"
```

---

## Phase 4: 创建记忆衰减器

### Task 4.1: 实现 MemoryDecay 类

**Objective:** 实现记忆衰减机制，支持时间衰减、访问衰减和访问频率加成

**Files:**
- Create: `backend/app/services/memory_decay.py`

**Step 1: 创建 memory_decay.py 文件**

```python
"""
Memory Decay - 记忆衰减机制
支持时间衰减、访问衰减和访问频率加成
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class MemoryDecay:
    """
    记忆衰减机制
    
    衰减公式：
    最终重要性 = 原始重要性 × 时间衰减 × 访问衰减 × (1 + 访问频率加成)
    
    其中：
    - 时间衰减 = 1 / (1 + 天数 × 0.01)
    - 访问衰减 = 1 / (1 + 距离上次访问天数 × 0.005)
    - 访问频率加成 = min(1.0, 访问次数 × 0.1)
    """
    
    def calculate_importance(
        self,
        original_importance: float,
        created_at: datetime,
        last_accessed: datetime,
        access_count: int
    ) -> float:
        """
        计算衰减后的重要性评分
        
        Args:
            original_importance: 原始重要性评分（0-1）
            created_at: 创建时间
            last_accessed: 最后访问时间
            access_count: 访问次数
            
        Returns:
            衰减后的重要性评分（0-1）
        """
        now = datetime.now(timezone.utc)
        
        # 1. 时间衰减（天数）
        days_old = (now - created_at).days
        time_decay = 1.0 / (1.0 + days_old * 0.01)
        
        # 2. 访问衰减
        days_since_access = (now - last_accessed).days
        access_decay = 1.0 / (1.0 + days_since_access * 0.005)
        
        # 3. 访问频率加成
        frequency_bonus = min(1.0, access_count * 0.1)
        
        # 综合评分
        final_importance = (
            original_importance * 
            time_decay * 
            access_decay * 
            (1.0 + frequency_bonus)
        )
        
        result = min(1.0, max(0.0, final_importance))
        
        logger.debug(
            f"Memory decay: original={original_importance:.2f}, "
            f"days_old={days_old}, days_since_access={days_since_access}, "
            f"access_count={access_count}, final={result:.2f}"
        )
        
        return result
```

**Step 2: 验证代码语法**

Run: `cd /mnt/d/zf/agent/系统/backend && python -m py_compile app/services/memory_decay.py`
Expected: 无输出（语法正确）

**Step 3: Commit**

```bash
cd /mnt/d/zf/agent/系统/backend
git add app/services/memory_decay.py
git commit -m "feat: add MemoryDecay for memory importance decay"
```

---

## Phase 5: 创建混合判断器

### Task 5.1: 实现 HybridMemoryJudge 类

**Objective:** 实现混合记忆判断器，整合规则过滤、LLM 判断、重要性评分和衰减机制

**Files:**
- Modify: `backend/app/services/memory_judge.py`

**Step 1: 添加 HybridMemoryJudge 类**

在 `memory_judge.py` 文件末尾添加：

```python
from app.services.memory_scorer import MemoryImportanceScorer
from app.services.memory_decay import MemoryDecay


class HybridMemoryJudge:
    """
    混合记忆判断器
    
    判断流程：
    1. 快速规则过滤（< 1ms）
    2. LLM 深度判断（100-500ms，仅处理不确定的内容）
    3. 综合重要性评分
    4. 记忆衰减计算
    """
    
    def __init__(self, llm_client=None):
        """
        初始化混合判断器
        
        Args:
            llm_client: LLM 客户端（可选，如果不提供则只使用规则判断）
        """
        self.rule_filter = RuleBasedFilter()
        self.llm_judge = LLMBasedJudge(llm_client) if llm_client else None
        self.importance_scorer = MemoryImportanceScorer()
        self.memory_decay = MemoryDecay()
    
    async def should_remember(
        self, 
        content: str, 
        context: Dict[str, Any] = None
    ) -> Tuple[bool, float, str]:
        """
        判断是否值得记住
        
        Args:
            content: 用户消息内容
            context: 上下文信息（可选）
            
        Returns:
            (should_remember, importance, memory_type)
        """
        if context is None:
            context = {}
        
        # 第一层：快速规则过滤
        rule_result = self.rule_filter.filter(content)
        if rule_result is not None:
            logger.info(f"Rule filter result: {rule_result}")
            return rule_result
        
        # 第二层：LLM 深度判断（如果可用）
        if self.llm_judge:
            llm_result = await self.llm_judge.judge(content)
            
            # 计算综合重要性评分
            if llm_result[0]:  # 如果值得记住
                importance = self.importance_scorer.score(content, {
                    "semantic_score": llm_result[1],
                    **context
                })
                return (llm_result[0], importance, llm_result[2])
            
            return llm_result
        
        # 如果没有 LLM，使用默认判断
        logger.warning("No LLM available, using default judgment")
        return (False, 0.3, "other")
    
    def calculate_decayed_importance(
        self,
        original_importance: float,
        created_at: datetime,
        last_accessed: datetime,
        access_count: int
    ) -> float:
        """
        计算衰减后的重要性评分
        
        Args:
            original_importance: 原始重要性评分
            created_at: 创建时间
            last_accessed: 最后访问时间
            access_count: 访问次数
            
        Returns:
            衰减后的重要性评分
        """
        return self.memory_decay.calculate_importance(
            original_importance,
            created_at,
            last_accessed,
            access_count
        )
```

**Step 2: 验证代码语法**

Run: `cd /mnt/d/zf/agent/系统/backend && python -m py_compile app/services/memory_judge.py`
Expected: 无输出（语法正确）

**Step 3: Commit**

```bash
cd /mnt/d/zf/agent/系统/backend
git add app/services/memory_judge.py
git commit -m "feat: add HybridMemoryJudge for hybrid memory judgment"
```

---

## Phase 6: 集成到 MemoryService

### Task 6.1: 修改 MemoryService 使用新的判断系统

**Objective:** 将 HybridMemoryJudge 集成到现有的 MemoryService 中

**Files:**
- Modify: `backend/app/services/memory_service.py`

**Step 1: 添加导入**

在 `memory_service.py` 文件顶部添加：

```python
from app.services.memory_judge import HybridMemoryJudge
```

**Step 2: 修改 __init__ 方法**

在 `MemoryService.__init__` 方法中添加：

```python
def __init__(self, db: AsyncSession, llm_client=None):
    self.db = db
    self.judge = HybridMemoryJudge(llm_client)
```

**Step 3: 替换 should_remember 方法**

将现有的 `should_remember` 方法替换为：

```python
async def should_remember(self, content: str, context: dict = None) -> Tuple[bool, float, str]:
    """
    判断内容是否值得记住
    
    Args:
        content: 对话内容
        context: 上下文信息（可选）
        
    Returns:
        (should_remember, importance, memory_type)
    """
    return await self.judge.should_remember(content, context)
```

**Step 4: 修改 auto_store_conversation 方法**

将现有的 `auto_store_conversation` 方法替换为：

```python
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
    # 使用混合判断器
    should_remember, importance, memory_type = await self.judge.should_remember(content)
    
    if should_remember:
        await self.store_memory(
            user_id=user_id,
            content=content,
            role=role,
            memory_type=memory_type or "conversation",
            importance_score=importance,
            source_id=source_id
        )
        logger.info(f"Auto-stored memory: {content[:50]}... (importance={importance:.2f})")
    else:
        logger.debug(f"Skipped memory: {content[:50]}...")
```

**Step 5: 验证代码语法**

Run: `cd /mnt/d/zf/agent/系统/backend && python -m py_compile app/services/memory_service.py`
Expected: 无输出（语法正确）

**Step 6: Commit**

```bash
cd /mnt/d/zf/agent/系统/backend
git add app/services/memory_service.py
git commit -m "feat: integrate HybridMemoryJudge into MemoryService"
```

---

## Phase 7: 更新 ContextBuilder

### Task 7.1: 修改 ContextBuilder 使用新的记忆判断

**Objective:** 更新 ContextBuilder 以使用新的记忆判断系统

**Files:**
- Modify: `backend/app/services/context_builder.py`

**Step 1: 添加导入**

在 `context_builder.py` 文件顶部添加：

```python
from app.services.memory_judge import HybridMemoryJudge
```

**Step 2: 修改 __init__ 方法**

在 `ContextBuilder.__init__` 方法中添加：

```python
def __init__(self, db: AsyncSession, user: User, llm_client=None):
    self.db = db
    self.user = user
    self.memory_service = MemoryService(db, llm_client)
```

**Step 3: 验证代码语法**

Run: `cd /mnt/d/zf/agent/系统/backend && python -m py_compile app/services/context_builder.py`
Expected: 无输出（语法正确）

**Step 4: Commit**

```bash
cd /mnt/d/zf/agent/系统/backend
git add app/services/context_builder.py
git commit -m "feat: update ContextBuilder to use new memory judgment"
```

---

## Phase 8: 测试和验证

### Task 8.1: 创建测试文件

**Objective:** 创建测试文件验证所有组件的功能

**Files:**
- Create: `backend/tests/test_memory_judge.py`

**Step 1: 创建测试文件**

```python
"""
测试记忆判断系统
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta

from app.services.memory_judge import RuleBasedFilter, HybridMemoryJudge
from app.services.memory_scorer import MemoryImportanceScorer
from app.services.memory_decay import MemoryDecay


class TestRuleBasedFilter:
    """测试规则过滤器"""
    
    def setup_method(self):
        self.filter = RuleBasedFilter()
    
    def test_high_priority_goal(self):
        """测试高优先级目标模式"""
        result = self.filter.filter("我的目标是每天跑步30分钟")
        assert result is not None
        assert result[0] is True  # should_remember
        assert result[1] >= 0.9   # importance
        assert result[2] == "goal"  # memory_type
    
    def test_high_priority_preference(self):
        """测试高优先级偏好模式"""
        result = self.filter.filter("我喜欢早起")
        assert result is not None
        assert result[0] is True
        assert result[1] >= 0.9
        assert result[2] == "preference"
    
    def test_high_priority_personal(self):
        """测试高优先级个人信息模式"""
        result = self.filter.filter("我养了一只猫叫小米")
        assert result is not None
        assert result[0] is True
        assert result[1] >= 0.9
        assert result[2] == "personal"
    
    def test_low_priority_ai_question(self):
        """测试低优先级 AI 问题模式"""
        result = self.filter.filter("你有什么功能？")
        assert result is not None
        assert result[0] is False  # should_remember
        assert result[1] <= 0.2    # importance
    
    def test_low_priority_request(self):
        """测试低优先级请求模式"""
        result = self.filter.filter("帮我查一下天气")
        assert result is not None
        assert result[0] is False
        assert result[1] <= 0.3
    
    def test_uncertain_content(self):
        """测试不确定内容"""
        result = self.filter.filter("今天天气真好")
        assert result is None  # 交给 LLM 判断


class TestMemoryImportanceScorer:
    """测试记忆重要性评分器"""
    
    def setup_method(self):
        self.scorer = MemoryImportanceScorer()
    
    def test_high_priority_content(self):
        """测试高优先级内容评分"""
        score = self.scorer.score("我的目标是每天跑步30分钟")
        assert score >= 0.7
    
    def test_medium_priority_content(self):
        """测试中优先级内容评分"""
        score = self.scorer.score("我想要减肥")
        assert score >= 0.5
    
    def test_low_priority_content(self):
        """测试低优先级内容评分"""
        score = self.scorer.score("今天天气真好")
        assert score <= 0.5


class TestMemoryDecay:
    """测试记忆衰减机制"""
    
    def setup_method(self):
        self.decay = MemoryDecay()
    
    def test_recent_memory(self):
        """测试近期记忆衰减"""
        now = datetime.now(timezone.utc)
        importance = self.decay.calculate_importance(
            original_importance=1.0,
            created_at=now,
            last_accessed=now,
            access_count=1
        )
        assert importance >= 0.9  # 近期记忆衰减很小
    
    def test_old_memory(self):
        """测试老旧记忆衰减"""
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=30)
        importance = self.decay.calculate_importance(
            original_importance=1.0,
            created_at=old_time,
            last_accessed=old_time,
            access_count=1
        )
        assert importance <= 0.8  # 30天前的记忆衰减明显
    
    def test_frequently_accessed(self):
        """测试频繁访问的记忆"""
        now = datetime.now(timezone.utc)
        importance = self.decay.calculate_importance(
            original_importance=1.0,
            created_at=now,
            last_accessed=now,
            access_count=10
        )
        assert importance >= 0.95  # 频繁访问的记忆衰减很小


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

**Step 2: 运行测试**

Run: `cd /mnt/d/zf/agent/系统/backend && python -m pytest tests/test_memory_judge.py -v`
Expected: 所有测试通过

**Step 3: Commit**

```bash
cd /mnt/d/zf/agent/系统/backend
git add tests/test_memory_judge.py
git commit -m "test: add tests for memory judgment system"
```

---

## 执行顺序

1. **Phase 1:** 创建 RuleBasedFilter（Task 1.1）
2. **Phase 2:** 创建 LLMBasedJudge（Task 2.1）
3. **Phase 3:** 创建 MemoryImportanceScorer（Task 3.1）
4. **Phase 4:** 创建 MemoryDecay（Task 4.1）
5. **Phase 5:** 创建 HybridMemoryJudge（Task 5.1）
6. **Phase 6:** 集成到 MemoryService（Task 6.1）
7. **Phase 7:** 更新 ContextBuilder（Task 7.1）
8. **Phase 8:** 测试和验证（Task 8.1）

---

## 验证命令

```bash
# 验证所有文件语法
cd /mnt/d/zf/agent/系统/backend
python -m py_compile app/services/memory_judge.py
python -m py_compile app/services/memory_scorer.py
python -m py_compile app/services/memory_decay.py
python -m py_compile app/services/memory_service.py
python -m py_compile app/services/context_builder.py

# 运行测试
python -m pytest tests/test_memory_judge.py -v

# 启动服务测试
uvicorn app.main:app --reload --port 8000
```

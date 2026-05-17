# 记忆判断优化设计文档

> **日期：** 2026-05-15
> **状态：** 设计中
> **作者：** zengfan

---

## 1. 背景与目标

### 1.1 背景

当前系统的 `should_remember()` 方法使用简单的关键词匹配来判断对话内容是否值得记住：

```python
# 当前实现（memory_service.py 第 319-341 行）
async def should_remember(self, content: str) -> bool:
    keywords = [
        "目标", "计划", "打算", "准备", "想要",
        "喜欢", "讨厌", "习惯", "偏好", "最爱",
        "体重", "睡眠", "运动", "饮食", "健康",
        "难过", "开心", "焦虑", "压力", "心情",
        "生日", "年龄", "工作", "学校", "家庭",
    ]
    return any(kw in content for kw in keywords)
```

**当前问题：**
- ❌ **漏判**："我养了一只猫叫小米" 不包含任何关键词，不会被记住
- ❌ **误判**："你有什么目标吗？" 包含"目标"，会被记住（但这是 AI 的问题，不是用户信息）
- ❌ **不够智能**：无法理解语义，只能匹配字面

### 1.2 目标

- 提高记忆判断的准确率（从当前约 60% 提升到 90%+）
- 降低误判率（从当前约 20% 降低到 5% 以下）
- 控制 API 成本（只有不确定的内容才调用 LLM）
- 支持记忆重要性评分和衰减机制

---

## 2. 架构设计

### 2.1 整体架构

```
用户消息
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  HybridMemoryJudge（混合记忆判断器）                          │
├─────────────────────────────────────────────────────────────┤
│  第一层：RuleBasedFilter（快速规则过滤）                       │
│  - 执行时间：< 1ms                                           │
│  - 覆盖率：约 60-70% 的消息                                  │
│  - 策略：严格，宁可漏判也不误判                               │
└─────────────────────────────────────────────────────────────┘
    │
    ▼ (不确定的消息，约 30-40%)
┌─────────────────────────────────────────────────────────────┐
│  第二层：LLMBasedJudge（LLM 深度判断）                        │
│  - 执行时间：100-500ms                                       │
│  - 准确率：> 90%                                             │
│  - 返回：是否记住 + 重要性评分 + 记忆类型                     │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  MemoryImportanceScorer（记忆重要性评分）                     │
│  - 综合评分：规则分(0.3) + 语义分(0.5) + 行为分(0.2)          │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  MemoryDecay（记忆衰减）                                     │
│  - 时间衰减：越久远越不重要                                   │
│  - 访问衰减：越少访问越不重要                                 │
│  - 重要性保持：高重要性记忆衰减慢                             │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  存储到 memories 表                                          │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 组件职责

| 组件 | 职责 | 执行时间 |
|------|------|----------|
| **RuleBasedFilter** | 快速规则过滤 | < 1ms |
| **LLMBasedJudge** | LLM 深度判断 | 100-500ms |
| **MemoryImportanceScorer** | 记忆重要性评分 | < 1ms |
| **MemoryDecay** | 记忆衰减计算 | < 1ms |

---

## 3. 详细设计

### 3.1 RuleBasedFilter（快速规则过滤器）

#### 3.1.1 设计原则

- **严格策略**：宁可漏判也不误判
- **快速执行**：< 1ms
- **覆盖明确场景**：只处理明确要记住/不记住的内容

#### 3.1.2 规则设计

**明确要记住的模式（高优先级）：**

| 模式 | 记忆类型 | 重要性 | 示例 |
|------|----------|--------|------|
| `我的目标是` | goal | 0.95 | "我的目标是每天跑步30分钟" |
| `我计划` | goal | 0.9 | "我计划下周开始健身" |
| `我打算` | goal | 0.9 | "我打算学习 Python" |
| `我想要` | goal | 0.85 | "我想要减肥" |
| `我准备` | goal | 0.85 | "我准备早起" |
| `我喜欢` | preference | 0.9 | "我喜欢跑步" |
| `我讨厌` | preference | 0.9 | "我讨厌吃蔬菜" |
| `我习惯` | preference | 0.9 | "我习惯早起" |
| `我偏好` | preference | 0.9 | "我偏好清淡饮食" |
| `我最爱` | preference | 0.9 | "我最爱吃火锅" |
| `我养了` | personal | 0.95 | "我养了一只猫叫小米" |
| `我住在` | personal | 0.95 | "我住在北京" |
| `我工作` | personal | 0.9 | "我在互联网公司工作" |
| `我生日` | personal | 0.95 | "我生日是 1 月 1 日" |
| `我年龄` | personal | 0.9 | "我今年 25 岁" |
| `我家庭` | personal | 0.9 | "我家有三口人" |
| `我体重` | health | 0.9 | "我体重 70 公斤" |
| `我身高` | health | 0.9 | "我身高 175 厘米" |
| `我血压` | health | 0.9 | "我血压有点高" |
| `我血糖` | health | 0.9 | "我血糖正常" |

**明确不记住的模式（低优先级）：**

| 模式 | 重要性 | 示例 |
|------|--------|------|
| `^你[有能会]` | 0.1 | "你有什么功能？" |
| `^你是` | 0.1 | "你是什么？" |
| `^帮我` | 0.2 | "帮我查一下天气" |
| `^请帮` | 0.2 | "请帮我写个代码" |
| `^麻烦` | 0.2 | "麻烦帮我看看" |
| `^什么是` | 0.1 | "什么是机器学习？" |
| `^怎么` | 0.15 | "怎么做红烧肉？" |
| `^为什么` | 0.15 | "为什么天空是蓝的？" |
| `^如何` | 0.15 | "如何学习编程？" |
| `^好的$` | 0.05 | "好的" |
| `^嗯$` | 0.05 | "嗯" |
| `^谢谢` | 0.1 | "谢谢" |
| `^感谢` | 0.1 | "感谢" |

#### 3.1.3 代码实现

```python
class RuleBasedFilter:
    """
    快速规则过滤器（严格策略）
    执行时间：< 1ms
    """
    
    HIGH_PRIORITY_PATTERNS = [
        (r"我的目标是", "goal", 0.95),
        (r"我计划", "goal", 0.9),
        (r"我打算", "goal", 0.9),
        (r"我想要", "goal", 0.85),
        (r"我准备", "goal", 0.85),
        (r"我喜欢", "preference", 0.9),
        (r"我讨厌", "preference", 0.9),
        (r"我习惯", "preference", 0.9),
        (r"我偏好", "preference", 0.9),
        (r"我最爱", "preference", 0.9),
        (r"我养了", "personal", 0.95),
        (r"我住在", "personal", 0.95),
        (r"我工作", "personal", 0.9),
        (r"我生日", "personal", 0.95),
        (r"我年龄", "personal", 0.9),
        (r"我家庭", "personal", 0.9),
        (r"我体重", "health", 0.9),
        (r"我身高", "health", 0.9),
        (r"我血压", "health", 0.9),
        (r"我血糖", "health", 0.9),
    ]
    
    LOW_PRIORITY_PATTERNS = [
        (r"^你[有能会]", 0.1),
        (r"^你是", 0.1),
        (r"^帮我", 0.2),
        (r"^请帮", 0.2),
        (r"^麻烦", 0.2),
        (r"^什么是", 0.1),
        (r"^怎么", 0.15),
        (r"^为什么", 0.15),
        (r"^如何", 0.15),
        (r"^好的$", 0.05),
        (r"^嗯$", 0.05),
        (r"^谢谢", 0.1),
        (r"^感谢", 0.1),
    ]
    
    def filter(self, content: str) -> tuple[bool, float, str] | None:
        """
        返回：
        - None: 不确定，交给 LLM 判断
        - (should_remember, importance, memory_type): 明确结果
        """
        # 检查高优先级模式
        for pattern, memory_type, importance in self.HIGH_PRIORITY_PATTERNS:
            if re.search(pattern, content):
                return (True, importance, memory_type)
        
        # 检查低优先级模式
        for pattern, importance in self.LOW_PRIORITY_PATTERNS:
            if re.search(pattern, content):
                return (False, importance, None)
        
        # 不确定，交给 LLM
        return None
```

### 3.2 LLMBasedJudge（LLM 深度判断器）

#### 3.2.1 设计原则

- **理解语义**：准确判断内容是否值得记住
- **返回结构化数据**：是否记住 + 重要性评分 + 记忆类型
- **错误处理**：API 失败时降级为规则判断

#### 3.2.2 Prompt 设计

```python
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
```

#### 3.2.3 代码实现

```python
class LLMBasedJudge:
    """
    LLM 深度判断器
    执行时间：100-500ms
    """
    
    def __init__(self, llm_client):
        self.llm = llm_client
    
    async def judge(self, content: str) -> tuple[bool, float, str]:
        """
        返回：(should_remember, importance, memory_type)
        """
        try:
            prompt = JUDGE_PROMPT.format(content=content)
            response = await self.llm.complete(prompt)
            result = json.loads(response)
            
            return (
                result["remember"],
                result["importance"],
                result["memory_type"]
            )
        except Exception as e:
            logger.error(f"LLM judge failed: {e}")
            # 降级：默认不记住
            return (False, 0.3, "other")
```

### 3.3 MemoryImportanceScorer（记忆重要性评分）

#### 3.3.1 评分公式

```
综合评分 = 规则分 × 0.3 + 语义分 × 0.5 + 行为分 × 0.2
```

#### 3.3.2 代码实现

```python
class MemoryImportanceScorer:
    """
    记忆重要性评分系统
    """
    
    def score(self, content: str, context: dict) -> float:
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
        """基于规则的评分"""
        high_priority = ["目标", "计划", "喜欢", "讨厌", "习惯", "生日", "养了"]
        medium_priority = ["想要", "准备", "打算", "偏好"]
        
        if any(kw in content for kw in high_priority):
            return 1.0
        if any(kw in content for kw in medium_priority):
            return 0.6
        return 0.3
    
    def _behavior_score(self, context: dict) -> float:
        """基于用户行为的评分"""
        # 用户是否重复提及
        if context.get("repeat_count", 0) > 1:
            return 0.9
        
        # 用户是否强调
        if context.get("emphasized", False):
            return 0.8
        
        return 0.5
```

### 3.4 MemoryDecay（记忆衰减）

#### 3.4.1 衰减公式

```
最终重要性 = 原始重要性 × 时间衰减 × 访问衰减 × (1 + 访问频率加成)

其中：
- 时间衰减 = 1 / (1 + 天数 × 0.01)
- 访问衰减 = 1 / (1 + 距离上次访问天数 × 0.005)
- 访问频率加成 = min(1.0, 访问次数 × 0.1)
```

#### 3.4.2 代码实现

```python
class MemoryDecay:
    """
    记忆衰减机制
    """
    
    def calculate_importance(
        self,
        original_importance: float,
        created_at: datetime,
        last_accessed: datetime,
        access_count: int
    ) -> float:
        now = datetime.now()
        
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
        
        return min(1.0, max(0.0, final_importance))
```

---

## 4. 集成设计

### 4.1 HybridMemoryJudge（混合记忆判断器）

```python
class HybridMemoryJudge:
    """
    混合记忆判断器
    """
    
    def __init__(self, llm_client):
        self.rule_filter = RuleBasedFilter()
        self.llm_judge = LLMBasedJudge(llm_client)
        self.importance_scorer = MemoryImportanceScorer()
        self.memory_decay = MemoryDecay()
    
    async def should_remember(self, content: str, context: dict = None) -> tuple[bool, float, str]:
        """
        判断是否值得记住
        
        返回：(should_remember, importance, memory_type)
        """
        # 第一层：快速规则过滤
        rule_result = self.rule_filter.filter(content)
        if rule_result is not None:
            return rule_result
        
        # 第二层：LLM 深度判断
        llm_result = await self.llm_judge.judge(content)
        
        # 计算综合重要性评分
        if llm_result[0]:  # 如果值得记住
            importance = self.importance_scorer.score(content, {
                "semantic_score": llm_result[1],
                **(context or {})
            })
            return (llm_result[0], importance, llm_result[2])
        
        return llm_result
```

### 4.2 MemoryService 集成

```python
class MemoryService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.judge = HybridMemoryJudge(llm_client)
    
    async def auto_store_conversation(
        self,
        user_id: str,
        content: str,
        role: str,
        source_id: str = None
    ):
        """自动判断并存储对话记忆"""
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
```

---

## 5. 测试策略

### 5.1 测试用例

| 输入 | 预期输出 | 说明 |
|------|----------|------|
| "我的目标是每天跑步30分钟" | (True, 0.95, "goal") | 规则匹配 |
| "我养了一只猫叫小米" | (True, 0.95, "personal") | 规则匹配 |
| "我喜欢早起" | (True, 0.9, "preference") | 规则匹配 |
| "你有什么功能？" | (False, 0.1, None) | 规则匹配 |
| "帮我查一下天气" | (False, 0.2, None) | 规则匹配 |
| "今天天气真好" | LLM 判断 | 交给 LLM |
| "小米今天很乖" | LLM 判断 | 交给 LLM |

### 5.2 性能测试

| 指标 | 目标 | 测试方法 |
|------|------|----------|
| 规则过滤时间 | < 1ms | 批量测试 1000 条消息 |
| LLM 判断时间 | < 500ms | 测试 100 条消息 |
| 准确率 | > 90% | 人工标注 100 条测试数据 |

---

## 6. 实施计划

### 6.1 阶段划分

| 阶段 | 任务 | 时间 |
|------|------|------|
| Phase 1 | 实现 RuleBasedFilter | 1 小时 |
| Phase 2 | 实现 LLMBasedJudge | 2 小时 |
| Phase 3 | 实现 MemoryImportanceScorer | 1 小时 |
| Phase 4 | 实现 MemoryDecay | 1 小时 |
| Phase 5 | 集成 HybridMemoryJudge | 2 小时 |
| Phase 6 | 测试和优化 | 2 小时 |

### 6.2 文件结构

```
backend/app/services/
├── memory_service.py          # 记忆服务（已有）
├── memory_judge.py            # 混合记忆判断器（新增）
├── memory_scorer.py           # 记忆重要性评分（新增）
├── memory_decay.py            # 记忆衰减（新增）
└── embedding_service.py       # 向量嵌入服务（已有）
```

---

## 7. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| LLM API 调用失败 | 无法判断不确定内容 | 降级为规则判断 |
| LLM API 响应慢 | 用户体验下降 | 添加超时机制 |
| 规则覆盖不全 | 漏判率上升 | 持续优化规则列表 |

---

## 8. 总结

本设计方案采用**混合判断策略**，结合快速规则过滤和 LLM 深度判断，在保证准确率的同时控制 API 成本。通过记忆重要性评分和衰减机制，实现智能化的记忆管理。

**核心优势：**
- ✅ 准确率高（> 90%）
- ✅ 成本可控（只有 30-40% 的消息调用 LLM）
- ✅ 速度快（规则过滤 < 1ms）
- ✅ 可扩展（规则列表可动态更新）

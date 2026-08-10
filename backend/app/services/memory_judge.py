"""
Memory Judge - 记忆判断模块

第一层: RuleBasedFilter - 基于规则的快速过滤器（低延迟）
第二层: LLMBasedJudge - 基于 LLM 的语义判断器（高精度）
第三层: HybridMemoryJudge - 混合记忆判断器（整合规则、LLM、评分、衰减）
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional
from app.services.prompt_service import prompt_service

logger = logging.getLogger(__name__)


class RuleBasedFilter:
    """基于规则的记忆判断过滤器

    返回值:
        None          - 不确定，需要 LLM 进一步判断
        (bool, float, str) - (should_remember, importance, memory_type)
    """

    # ── 高优先级模式：应该记住的内容 ──────────────────────────────
    HIGH_PRIORITY_PATTERNS: list[tuple[str, float, str]] = [
        # 目标 / 计划
        (r"(?:我的|我有)?目标是",                          0.9, "goal"),
        (r"计划(?:要|去|做)",                              0.85, "goal"),
        (r"打算(?:要|去|做)",                              0.85, "goal"),
        (r"准备(?:要|去|做|开始)",                         0.85, "goal"),
        (r"想要(?:学|做|成为|达到)",                       0.8,  "goal"),

        # 偏好 / 喜好
        (r"我喜欢",                                       0.8,  "preference"),
        (r"我(?:最)?(?:喜欢|爱|偏好|偏好)",               0.8,  "preference"),
        (r"我(?:讨厌|不喜欢|不想要)",                      0.8,  "preference"),
        (r"我的(?:习惯|偏好|口味)",                        0.8,  "preference"),

        # 个人信息
        (r"我(?:的)?(?:生日|出生)",                        0.95, "fact"),
        (r"我(?:今年)?(?:几岁|多大|年龄)",                 0.9,  "fact"),
        (r"我(?:的)?(?:名字|姓名)是",                      0.95, "fact"),
        (r"我在?(?:工作|上班|就职)于",                     0.9,  "fact"),
        (r"我的(?:职业|工作)是",                           0.9,  "fact"),
        (r"我(?:家)?住(?:在)?",                            0.9,  "fact"),
        (r"我(?:的)?(?:家|家庭)",                          0.85, "fact"),
        (r"我(?:养了|养了只|养了只猫|养了只狗)",           0.95, "personal"),
        (r"我(?:的)?(?:猫|狗|宠物)(?:叫|名字是)",          0.95, "personal"),

        # 健康数据
        (r"(?:我的)?(?:体重|身高)(?:是|到了?)",            0.9,  "health"),
        (r"(?:我)?(?:每天|每周)?(?:运动|锻炼)",            0.8,  "health"),
        (r"(?:我的)?(?:血压|血糖|心率)",                   0.9,  "health"),
        (r"(?:我)?(?:最近)?(?:失眠|睡不着|睡眠不好)",      0.85, "health"),

        # 情感 / 心情
        (r"我(?:最近|现在)?(?:很|特别)?(?:难过|伤心|焦虑|压力大|抑郁|开心|高兴|兴奋)",
                                                          0.8,  "emotion"),
    ]

    # ── 低优先级模式：不需要记住的内容 ─────────────────────────────
    LOW_PRIORITY_PATTERNS: list[tuple[str, float, str]] = [
        # AI 相关问题
        (r"(?:你|AI|人工智能)(?:能|会|可以)(?:做|帮|干)",  0.1, "conversation"),
        (r"(?:你是谁|你叫什么|你的名字)",                   0.1, "conversation"),
        (r"(?:你(?:能|会|可以).*(?:吗|么)\??$)",            0.1, "conversation"),

        # 简单请求
        (r"^(?:帮|请|帮忙)",                               0.2, "conversation"),
        (r"(?:翻译|解释|说明|介绍)一下",                    0.2, "conversation"),

        # 一般性问答
        (r"(?:什么是|什么叫|怎么|如何|为什么|请问)",       0.15, "conversation"),
        (r"(?:什么|哪个|哪款|哪些).+(?:好|推荐|比较好)",    0.1,  "conversation"),
        (r"(?:推荐|建议)(?:一下|一个|个)?",                 0.15, "conversation"),
        (r"(?:吗|呢|吧|呀|啊|哦|嘛)\?{0,1}$",             0.1,  "conversation"),

        # 寒暄
        (r"^(?:你好|嗨|hi|hello|hey|谢谢|感谢|拜拜|再见)", 0.05, "conversation"),

        # 测试 / 占位
        (r"^(?:测试|test|123|aaa)",                        0.05, "conversation"),
        (r"^(?:嗯|哦|好的?|行|好吧|知道了|ok)$",           0.05, "conversation"),

        # 很短的输入（少于 4 个字）
        (r"^.{0,3}$",                                      0.1,  "conversation"),
    ]

    def filter(
        self, text: str, role: str = "user"
    ) -> Optional[tuple[bool, float, str]]:
        """快速判断文本是否值得记忆

        Args:
            text: 待判断的文本内容
            role: 消息来源角色 ("user" | "system")

        Returns:
            None                    - 规则无法判定，交由 LLM 判断
            (should_remember, importance, memory_type) - 明确的判断结果
        """
        if not text or not text.strip():
            return (False, 0.0, "conversation")

        text = text.strip()

        # 先检查低优先级模式（如果命中，直接决定不记住）
        for pattern, importance, mem_type in self.LOW_PRIORITY_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                # 低优先级模式命中 → 跳过，但不是直接丢弃
                # 用户角色的消息仍然可能有价值，给一个低分
                if role == "user" and importance >= 0.15:
                    return (False, importance, mem_type)
                return (False, importance, mem_type)

        # 再检查高优先级模式
        for pattern, importance, mem_type in self.HIGH_PRIORITY_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return (True, importance, mem_type)

        # 规则未命中 → 返回 None，交给 LLM 进一步判断
        return None


class LLMBasedJudge:
    """基于 LLM 的语义记忆判断器

    当规则过滤器无法判定时，使用 LLM 进行更精确的语义分析。
    """

    def __init__(self, llm_client):
        """初始化 LLM 记忆判断器

        Args:
            llm_client: LLM 客户端实例，需要有 chat 方法
        """
        self.llm_client = llm_client

    async def judge(self, content: str) -> tuple[bool, float, str]:
        """使用 LLM 判断内容是否值得记忆

        Args:
            content: 待判断的文本内容

        Returns:
            (should_remember, importance, memory_type) 元组
        """
        import json

        try:
            prompt = prompt_service.build_judge_prompt(content)
            response = await self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}]
            )

            # 解析 JSON 响应
            result = json.loads(response)
            should_remember = result.get("should_remember", False)
            importance = float(result.get("importance", 0.5))
            memory_type = result.get("memory_type", "conversation")

            # 确保 importance 在有效范围内
            importance = max(0.0, min(1.0, importance))

            # 确保 memory_type 是有效类型
            valid_types = {"fact", "goal", "preference", "emotion", "health", "conversation"}
            if memory_type not in valid_types:
                memory_type = "conversation"

            return (should_remember, importance, memory_type)

        except Exception as e:
            # 解析失败时返回默认值
            logger.warning(f"LLM memory judgment failed: {e}")
            return (False, 0.5, "conversation")


class HybridMemoryJudge:
    """混合记忆判断器

    整合以下组件，提供统一的记忆判断接口：
    - RuleBasedFilter: 基于规则的快速过滤（第一层）
    - LLMBasedJudge: 基于 LLM 的语义判断（第二层，仅在规则层不确定时调用）
    - MemoryImportanceScorer: 综合重要性评分
    - MemoryDecay: 记忆重要性时间衰减

    典型用法:
        from app.services.memory_judge import HybridMemoryJudge
        from app.services.memory_scorer import MemoryImportanceScorer
        from app.services.memory_decay import MemoryDecay

        judge = HybridMemoryJudge(
            llm_client=my_llm_client,          # 可选，不传则跳过 LLM 层
            importance_scorer=MemoryImportanceScorer(),
            memory_decay=MemoryDecay(),
        )
        result = await judge.judge("我的目标是学会弹钢琴")
    """

    # 权重：规则分 vs LLM 分 vs 评分器分 的融合比例
    RULE_WEIGHT = 0.5
    LLM_WEIGHT = 0.2
    SCORER_WEIGHT = 0.3

    def __init__(
        self,
        llm_client: Any = None,
        importance_scorer: Any = None,
        memory_decay: Any = None,
    ):
        """初始化混合记忆判断器

        Args:
            llm_client: LLM 客户端实例（可选），需有 async chat 方法
            importance_scorer: MemoryImportanceScorer 实例（可选）
            memory_decay: MemoryDecay 实例（可选）
        """
        self.rule_filter = RuleBasedFilter()
        self.llm_judge = LLMBasedJudge(llm_client) if llm_client else None
        self.importance_scorer = importance_scorer
        self.memory_decay = memory_decay

    async def judge(
        self,
        text: str,
        role: str = "user",
        context: Optional[dict] = None,
    ) -> dict[str, Any]:
        """判断文本是否值得记忆

        三层判断流程：
        1. RuleBasedFilter 快速过滤（确定性结果直接返回）
        2. LLMBasedJudge 语义判断（规则不确定时调用）
        3. MemoryImportanceScorer 综合评分 + 融合各层分数

        Args:
            text: 待判断的文本内容
            role: 消息来源角色 ("user" | "system")
            context: 上下文信息，传递给 ImportanceScorer

        Returns:
            dict: {
                "should_remember": bool,     # 是否值得记忆
                "importance": float,         # 最终重要性分数 (0-1)
                "memory_type": str,          # 记忆类型
                "source": str,               # 判断来源 ("rule" | "llm" | "hybrid")
                "rule_result": tuple | None, # 规则层原始结果
                "llm_result": tuple | None,  # LLM 层原始结果
                "scorer_score": float,       # 评分器分数
            }
        """
        result: dict[str, Any] = {
            "should_remember": False,
            "importance": 0.0,
            "memory_type": "conversation",
            "source": "rule",
            "rule_result": None,
            "llm_result": None,
            "scorer_score": 0.0,
        }

        if not text or not text.strip():
            return result

        # ── 第一层: 规则过滤 ──────────────────────────────────────
        rule_result = self.rule_filter.filter(text, role)
        result["rule_result"] = rule_result

        if rule_result is not None:
            should_remember, importance, memory_type = rule_result
            result["should_remember"] = should_remember
            result["importance"] = importance
            result["memory_type"] = memory_type
            result["source"] = "rule"

            # 如果规则层有明确结论且不需要 LLM 参与，仍然计算评分器分数用于融合
            if self.importance_scorer:
                scorer_score = self.importance_scorer.score(text, context)
                result["scorer_score"] = scorer_score
                # 融合：规则分权重更高
                final_importance = (
                    self.RULE_WEIGHT * importance
                    + self.SCORER_WEIGHT * scorer_score
                )
                # 规则层判定不需要记忆时，LLM 权重为 0
                result["importance"] = max(0.0, min(1.0, final_importance))
                # 重新判断 should_remember：融合后分数 >= 0.5 才记住
                if should_remember and result["importance"] < 0.5:
                    result["should_remember"] = False

            return result

        # ── 第二层: LLM 判断（规则不确定时） ─────────────────────
        llm_result: Optional[tuple[bool, float, str]] = None
        if self.llm_judge:
            try:
                llm_result = await self.llm_judge.judge(text)
                result["llm_result"] = llm_result
            except Exception as e:
                logger.warning("LLM judge failed: %s", e)
                llm_result = None

        # ── 第三层: 综合评分 ─────────────────────────────────────
        scorer_score = 0.5  # 默认中性分
        if self.importance_scorer:
            scorer_score = self.importance_scorer.score(text, context)
        result["scorer_score"] = scorer_score

        if llm_result is not None:
            llm_should, llm_importance, llm_type = llm_result
            result["memory_type"] = llm_type

            # 融合三层分数
            final_importance = (
                self.LLM_WEIGHT * llm_importance
                + self.SCORER_WEIGHT * scorer_score
            )
            result["importance"] = max(0.0, min(1.0, final_importance))

            # conversation 类型（闲聊/问答）需要更高阈值才记住
            threshold = 0.7 if llm_type == "conversation" else 0.5
            result["should_remember"] = llm_should and result["importance"] >= threshold
            result["source"] = "llm"
        else:
            # LLM 不可用时，仅依赖评分器
            result["importance"] = scorer_score
            result["should_remember"] = scorer_score >= 0.5
            result["source"] = "hybrid"

        return result

    def apply_decay(
        self,
        original_importance: float,
        created_at: datetime,
        last_accessed: Optional[datetime] = None,
        access_count: int = 0,
    ) -> float:
        """对记忆重要性施加时间衰减

        如果未配置 MemoryDecay，则直接返回原始分数。

        Args:
            original_importance: 原始重要性分数 (0-1)
            created_at: 记忆创建时间
            last_accessed: 最后访问时间（None 表示从未访问）
            access_count: 累计访问次数

        Returns:
            float: 衰减后的重要性分数
        """
        if not self.memory_decay:
            return original_importance

        return self.memory_decay.calculate_importance(
            original_importance=original_importance,
            created_at=created_at,
            last_accessed=last_accessed,
            access_count=access_count,
        )

    async def judge_with_decay(
        self,
        text: str,
        role: str = "user",
        context: Optional[dict] = None,
        created_at: Optional[datetime] = None,
        last_accessed: Optional[datetime] = None,
        access_count: int = 0,
    ) -> dict[str, Any]:
        """判断 + 衰减的完整流程

        等价于先调用 judge() 再调用 apply_decay()，方便一步到位。

        Args:
            text: 待判断的文本内容
            role: 消息来源角色
            context: 上下文信息
            created_at: 记忆创建时间（用于衰减计算，默认为当前时间）
            last_accessed: 最后访问时间
            access_count: 累计访问次数

        Returns:
            dict: 与 judge() 返回格式相同，importance 为衰减后的值
        """
        result = await self.judge(text, role, context)

        if self.memory_decay and result["should_remember"]:
            if created_at is None:
                created_at = datetime.now(timezone.utc)
            result["importance"] = self.apply_decay(
                original_importance=result["importance"],
                created_at=created_at,
                last_accessed=last_accessed,
                access_count=access_count,
            )

        return result

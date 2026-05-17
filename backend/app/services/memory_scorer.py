"""
Memory Importance Scorer - 记忆重要性评分器

为记忆内容计算综合重要性分数，结合：
1. 基于规则的内容评分（_rule_score）
2. 基于用户行为的行为评分（_behavior_score）

返回 0.0 ~ 1.0 之间的浮点数，分数越高越重要。
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class MemoryImportanceScorer:
    """记忆重要性综合评分器

    综合考虑内容特征和用户行为，为记忆内容产出一个 0-1 的重要性分数。

    典型用法:
        scorer = MemoryImportanceScorer()
        score = scorer.score("我的目标是明年学会弹钢琴", context={"role": "user"})
    """

    # ── 高重要性关键词模式 ──────────────────────────────────────────
    HIGH_IMPORTANCE_PATTERNS: list[tuple[str, float]] = [
        # 目标 / 计划
        (r"(?:我的|我有)?目标是",                     0.90),
        (r"计划(?:要|去|做)",                          0.85),
        (r"打算(?:要|去|做)",                          0.85),
        (r"准备(?:要|去|做|开始)",                     0.85),
        (r"想要(?:学|做|成为|达到)",                   0.80),

        # 个人信息
        (r"我(?:的)?(?:生日|出生)",                    0.95),
        (r"我(?:的)?(?:名字|姓名)是",                  0.95),
        (r"我(?:今年)?(?:几岁|多大|年龄)",             0.90),
        (r"我在?(?:工作|上班|就职)于",                 0.90),
        (r"我的(?:职业|工作)是",                       0.90),
        (r"我(?:家)?住(?:在)?",                        0.90),
        (r"我的(?:家|家庭)",                           0.85),

        # 偏好 / 喜好
        (r"我(?:最)?(?:喜欢|爱|偏好)",                 0.80),
        (r"我(?:讨厌|不喜欢|不想要)",                  0.80),
        (r"我的(?:习惯|偏好|口味)",                    0.80),

        # 健康数据
        (r"(?:我的)?(?:体重|身高)(?:是|到了?)",        0.90),
        (r"(?:我)?(?:每天|每周)?(?:运动|锻炼)",        0.80),
        (r"(?:我的)?(?:血压|血糖|心率)",               0.90),
        (r"(?:我)?(?:最近)?(?:失眠|睡不着|睡眠不好)",  0.85),

        # 情感 / 心情
        (r"我(?:最近|现在)?(?:很|特别)?(?:难过|伤心|焦虑|压力大|抑郁|开心|高兴|兴奋)",
                                                      0.80),
    ]

    # ── 低重要性关键词模式 ──────────────────────────────────────────
    LOW_IMPORTANCE_PATTERNS: list[tuple[str, float]] = [
        # AI 相关问题
        (r"(?:你|AI|人工智能)(?:能|会|可以)(?:做|帮|干)",  0.10),
        (r"(?:你是谁|你叫什么|你的名字)",                   0.10),

        # 简单请求
        (r"^(?:帮|请|帮忙)",                               0.20),
        (r"(?:翻译|解释|说明|介绍)一下",                    0.20),

        # 一般性问答
        (r"(?:什么是|什么叫|怎么|如何|为什么|请问)",       0.15),

        # 天气相关（闲聊）
        (r"(?:今天|明天|昨天)(?:天气|气温|下雨|下雪|晴天|阴天)", 0.15),
        (r"(?:好热|好冷|好凉快|好暖和)",                   0.15),

        # 时间相关（临时信息）
        (r"(?:现在几点|今天星期几|今天几号)",               0.15),

        # 寒暄
        (r"^(?:你好|嗨|hi|hello|hey|谢谢|感谢|拜拜|再见)", 0.05),

        # 测试 / 占位
        (r"^(?:测试|test|123|aaa)",                        0.05),
        (r"^(?:嗯|哦|好的?|行|好吧|知道了|ok)$",           0.05),
    ]

    # 特殊处理：question mark pattern 无法直接用 tuple，单独列出
    _QUESTION_PATTERN = (r"(?:吗|呢|吧)\?{0,1}$", 0.10)

    # 权重
    RULE_WEIGHT = 0.7      # 规则评分权重
    BEHAVIOR_WEIGHT = 0.3  # 行为评分权重

    # 默认中性分数
    DEFAULT_SCORE = 0.5

    # ─────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────

    def score(self, content: str, context: Optional[dict] = None) -> float:
        """综合评分

        将规则评分和行为评分按权重加权求和，截断到 [0, 1]。

        Args:
            content: 待评分的文本内容
            context: 上下文信息字典，可包含：
                - role (str): 消息角色 "user" | "system"
                - access_count (int): 历史访问次数
                - message_length (int): 原始消息长度（字符数）
                - conversation_turn (int): 当前对话轮次
                - has_question (bool): 是否为提问

        Returns:
            float: 0.0 ~ 1.0 的重要性分数
        """
        if not content or not content.strip():
            return 0.0

        context = context or {}

        rule_score = self._rule_score(content)
        behavior_score = self._behavior_score(context)

        combined = (
            self.RULE_WEIGHT * rule_score
            + self.BEHAVIOR_WEIGHT * behavior_score
        )

        return max(0.0, min(1.0, round(combined, 4)))

    # ─────────────────────────────────────────────────────────────────
    # Internal scoring helpers
    # ─────────────────────────────────────────────────────────────────

    def _rule_score(self, content: str) -> float:
        """基于规则的内容评分

        扫描 HIGH / LOW 重要性关键词模式，命中高重要性模式取最高分，
        命中低重要性模式取最低分，均未命中返回默认中性分数。

        Args:
            content: 待评分的文本内容

        Returns:
            float: 0.0 ~ 1.0 的规则分数
        """
        if not content or not content.strip():
            return 0.0

        text = content.strip()

        # 先检查低重要性模式（优先级更高，命中即决定）
        for pattern, score in self.LOW_IMPORTANCE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return score

        # 检查 question mark 特殊模式
        if re.search(self._QUESTION_PATTERN[0], text, re.IGNORECASE):
            return self._QUESTION_PATTERN[1]

        # 检查高重要性模式（取最高匹配分）
        max_high_score = 0.0
        for pattern, score in self.HIGH_IMPORTANCE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                max_high_score = max(max_high_score, score)

        if max_high_score > 0.0:
            return max_high_score

        # 文本长度启发：很短的内容通常不太重要
        if len(text) <= 3:
            return 0.1

        # 未命中任何模式，返回默认中性分数
        return self.DEFAULT_SCORE

    def _behavior_score(self, context: dict) -> float:
        """基于用户行为的评分

        根据上下文中的行为信号调整分数：
        - role: 用户消息 > 系统消息
        - access_count: 被多次访问的记忆通常更重要
        - message_length: 较长的消息通常包含更多信息
        - conversation_turn: 靠前的轮次（首次提及）略重要
        - has_question: 提问通常指示用户需求

        Args:
            context: 上下文信息字典

        Returns:
            float: 0.0 ~ 1.0 的行为分数
        """
        score = 0.5  # 基准分

        # ── 角色信号 ──────────────────────────────────────────────
        role = context.get("role", "user")
        if role == "user":
            score += 0.1  # 用户主动提供的信息更重要
        elif role == "system":
            score -= 0.1

        # ── 访问频率信号 ─────────────────────────────────────────
        access_count = context.get("access_count", 0)
        if access_count >= 5:
            score += 0.15  # 高频访问 → 高重要性
        elif access_count >= 2:
            score += 0.05

        # ── 消息长度信号 ─────────────────────────────────────────
        message_length = context.get("message_length", 0)
        if message_length >= 100:
            score += 0.1   # 长消息通常包含更多有价值信息
        elif message_length >= 30:
            score += 0.05
        elif message_length > 0 and message_length < 10:
            score -= 0.1   # 过短消息重要性偏低

        # ── 对话轮次信号 ─────────────────────────────────────────
        turn = context.get("conversation_turn", 0)
        if 0 < turn <= 3:
            score += 0.05  # 对话初期的信息略重要（用户正在建立上下文）

        # ── 提问信号 ─────────────────────────────────────────────
        if context.get("has_question", False):
            score += 0.05

        return max(0.0, min(1.0, round(score, 4)))

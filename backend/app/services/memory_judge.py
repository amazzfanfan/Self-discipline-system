"""
Memory Judge - 记忆判断模块

第一层: RuleBasedFilter - 基于规则的快速过滤器（低延迟）
第二层: LLMBasedJudge - 基于 LLM 的语义判断器（高精度）
"""

import re
from typing import Optional


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
        (r"(?:吗|呢|吧)\?{0,1}$",                         0.1,  "conversation"),

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

    JUDGE_PROMPT = """你是一个记忆判断助手。请分析以下对话内容，判断是否值得长期记忆。

判断标准：
1. 包含用户个人信息（姓名、生日、职业、地址等）→ 值得记住
2. 包含用户偏好或喜好（喜欢什么、讨厌什么）→ 值得记住
3. 包含用户目标或计划（想做什么、计划做什么）→ 值得记住
4. 包含重要事实（健康数据、重要事件）→ 值得记住
5. 包含情感表达（心情、感受）→ 适度记住
6. 一般性问题、寒暄、请求帮助、闲聊 → 不需要记住

请以 JSON 格式返回分析结果：
{
    "should_remember": true/false,
    "importance": 0.0-1.0 之间的浮点数,
    "memory_type": "fact/goal/preference/emotion/health/conversation" 中的一个,
    "reason": "简短的判断理由"
}

待判断内容：
{text}

请只返回 JSON，不要有其他内容。"""

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
            prompt = self.JUDGE_PROMPT.format(text=content)
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

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            # 解析失败时返回默认值
            return (False, 0.5, "conversation")

"""
Prompt Service - 提示词服务
负责构建各种提示词，包括系统提示、任务提示、评估提示等
集中管理所有 prompt，避免散落在各业务文件中
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
    
    # 意图识别提示词（简单的，用于 build_intent_prompt）
    INTENT_PROMPT = """分析用户消息意图，返回JSON格式：
{{
  "intent": "complete_task|skip_task|record_weight|chat",
  "task_keyword": "关键词（如果是完成任务）",
  "weight": 数字（如果是记录体重）
}}

用户消息：{content}

请只返回 JSON，不要有其他内容。"""
    
    # 意图识别提示词（AI版，带 today_tasks，用于 build_intent_ai_prompt）
    INTENT_PROMPT_AI = """分析用户消息，判断意图。只返回JSON，不要其他内容。

意图类型：
- complete_task: 用户报告完成了某个任务（运动/饮食/睡眠/外貌）
- skip_task: 用户表示不想做或放弃某个任务
- record_weight: 用户报告体重数据
- chat: 普通对话、提问、闲聊

返回格式：
{{"intent": "complete_task", "dimension": "exercise"}}
{{"intent": "skip_task", "dimension": "diet"}}
{{"intent": "record_weight", "weight_kg": 72.5}}
{{"intent": "chat"}}

dimension 只能是: exercise, diet, sleep, appearance

今日任务：
{today_tasks}

用户消息：{message}"""

    # 任务生成提示词
    TASK_PROMPT = """请为用户生成1个{dimension}维度的今日任务。
难度：{difficulty}，当前评分：{score}分，最近做过的：{recent}（避免重复）。
要求：具体可执行，有明确完成标准。
{adaptation_context}
用户可执行条件：{constraint_context}
不得生成依赖“不可用物品/器材”、命中“避免活动”或超过最长时长的任务。

重要：{dim_guide}
{goal_context}
返回JSON格式：{{"task": "任务标题"}}"""
    
    # 维度指南
    DIMENSION_GUIDES = {
        "exercise": "运动类任务：体育锻炼、健身、跑步、跳绳、俯卧撑、深蹲、瑜伽、拉伸、散步、骑车、游泳等身体活动。不要包含学习、写作、阅读等非身体活动。",
        "diet": "饮食类任务：健康饮食、喝水、记录饮食、少吃零食、多吃蔬菜、控制热量、少油少盐等饮食相关。",
        "sleep": "睡眠类任务：早睡、放下手机、冥想、深呼吸、睡前放松、避免熬夜等睡眠相关。",
        "appearance": "形象管理类任务：护肤、防晒、清洁面部、整理仪容等自我护理事项，不评价长相或气质。",
    }

    # 记忆判断提示词（从 memory_judge.py 迁移）
    JUDGE_PROMPT = """你是一个记忆判断助手。请分析以下对话内容，判断是否值得长期记忆。

判断标准（满足以下任一才记住）：
1. 包含用户个人信息（姓名、生日、职业、地址、宠物等）→ 值得记住
2. 包含用户偏好或喜好（喜欢什么、讨厌什么）→ 值得记住
3. 包含用户目标或计划（想做什么、计划做什么）→ 值得记住
4. 包含重要事实（健康数据、重要事件）→ 值得记住
5. 包含情感表达（心情、感受）→ 适度记住

以下内容一律不记住（即使看起来有用）：
- 闲聊问答："什么手机好"、"推荐一下"、"哪个比较好" → 不记住
- 通用问题："什么是"、"怎么"、"为什么"、"介绍一下" → 不记住
- 寒暄问候："你好"、"谢谢"、"好的"、"嗯" → 不记住
- 临时请求："帮我查"、"帮我算"、"翻译一下" → 不记住
- 时间/天气："现在几点"、"今天天气" → 不记住
- AI 相关："你能做什么"、"你是谁" → 不记住
- 系统回复：AI 给出的分析、建议、推荐 → 不记住

重要：只有用户主动透露的个人信息、偏好、目标、情感才值得记住。
AI 的回复、分析、推荐一律不记住。问题和请求一律不记住。

请以 JSON 格式返回分析结果：
{{
    "should_remember": true/false,
    "importance": 0.0-1.0 之间的浮点数,
    "memory_type": "fact/goal/preference/emotion/health/conversation" 中的一个,
    "reason": "简短的判断理由"
}}

待判断内容：
{text}

请只返回 JSON，不要有其他内容。"""

    # 肤质护理建议提示词（从 faceplus_service.py 迁移）
    SKIN_SUGGESTION_PROMPT = (
        "用户肤质分析结果：皮肤类型为{skin_type_name}，检测到以下问题：{issues_str}。\n\n"
        "用户安全限制：{constraints_text}。\n\n"
        "用户可执行条件：{feasibility_text}。不得推荐用户明确没有的产品。\n\n"
        "请针对问题给出具体、可操作的日常护理建议，返回JSON格式：\n"
        '{{"suggestions": [{{"text": "建议1", "risk_level": "low", "cautions": ["注意事项"]}}]}}\n\n'
        "要求：\n"
        "1. 每条建议要具体，包含产品类型或操作方法，text 不超过80个汉字\n"
        "2. 建议要结合用户的皮肤类型\n"
        "3. 最多返回{suggestion_limit}条最重要的建议，每条最多1个简短注意事项，risk_level 只能是 low 或 moderate\n"
        "4. 不得进行医疗诊断、承诺治疗效果或推荐处方药、口服药、注射和针刺\n"
        "5. 必须遵守用户安全限制；无法安全建议时返回空数组\n"
        "6. 只返回JSON，不要其他内容"
    )

    # 肤质任务提示词（从 faceplus_service.py 迁移）
    SKIN_TASK_PROMPT = (
        "用户肤质问题：{issues_str}，皮肤类型：{skin_type_name}。\n\n"
        "用户安全限制：{constraints_text}。\n\n"
        "用户可执行条件：{feasibility_text}。不得依赖用户明确没有的产品或工具。\n\n"
        "请生成1个今日护肤任务，要求：\n"
        "1. 具体可执行，有明确的完成标准\n"
        "2. 针对用户的具体问题\n"
        "3. 20字以内\n"
        "4. 遵守安全限制，不进行医疗诊断或推荐处方、口服、注射、针刺\n\n"
        '返回JSON格式：{{"task": "任务描述"}}'
    )

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

    def build_intent_ai_prompt(self, message: str, today_tasks: str) -> str:
        """
        构建AI意图识别提示词（带今日任务上下文）
        
        Args:
            message: 用户消息内容
            today_tasks: 今日任务字符串（已格式化）
            
        Returns:
            AI意图识别提示词
        """
        return self.INTENT_PROMPT_AI.format(today_tasks=today_tasks, message=message)

    def build_judge_prompt(self, content: str) -> str:
        """
        构建记忆判断提示词
        
        Args:
            content: 待判断的文本内容
            
        Returns:
            记忆判断提示词
        """
        return self.JUDGE_PROMPT.format(text=content)

    def build_skin_suggestion_prompt(
        self,
        skin_type_name: str,
        issues_str: str,
        constraints_text: str = "未提供特殊限制",
        feasibility_text: str = "未提供特殊可执行条件",
        suggestion_limit: int = 3,
    ) -> str:
        """
        构建肤质护理建议提示词
        
        Args:
            skin_type_name: 皮肤类型名称
            issues_str: 皮肤问题描述字符串
            
        Returns:
            肤质护理建议提示词
        """
        return self.SKIN_SUGGESTION_PROMPT.format(
            skin_type_name=skin_type_name,
            issues_str=issues_str,
            constraints_text=constraints_text,
            feasibility_text=feasibility_text,
            suggestion_limit=max(1, min(3, suggestion_limit)),
        )

    def build_skin_task_prompt(
        self,
        issues_str: str,
        skin_type_name: str,
        constraints_text: str = "未提供特殊限制",
        feasibility_text: str = "未提供特殊可执行条件",
    ) -> str:
        """
        构建肤质任务提示词
        
        Args:
            issues_str: 皮肤问题描述字符串
            skin_type_name: 皮肤类型名称
            
        Returns:
            肤质任务提示词
        """
        return self.SKIN_TASK_PROMPT.format(
            issues_str=issues_str,
            skin_type_name=skin_type_name,
            constraints_text=constraints_text,
            feasibility_text=feasibility_text,
        )
    
    def build_task_prompt(
        self,
        dimension: str,
        score: float,
        difficulty: str,
        recent_tasks: list[str],
        goal_content: str = None,
        adaptation_context: str | None = None,
        constraint_context: str | None = None,
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
        dim_guide = self.DIMENSION_GUIDES.get(dimension, "")
        
        # 目标上下文
        goal_context = ""
        if goal_content:
            goal_context = (
                f"用户目标：{goal_content}\n"
                "请生成与该目标直接一致的任务；若目标中包含执行时间、时长或具体活动，"
                "必须保留这些约束，不得擅自换成通用任务。\n"
            )
        
        return self.TASK_PROMPT.format(
            dimension=dimension,
            difficulty=diff_cn,
            score=score,
            recent=recent,
            dim_guide=dim_guide,
            goal_context=goal_context,
            adaptation_context=adaptation_context or "",
            constraint_context=constraint_context or "未提供特殊可执行条件",
        )
    
# 全局实例
prompt_service = PromptService()

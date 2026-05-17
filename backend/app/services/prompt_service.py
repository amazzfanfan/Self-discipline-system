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
{{
  "intent": "complete_task|skip_task|record_weight|chat",
  "task_keyword": "关键词（如果是完成任务）",
  "weight": 数字（如果是记录体重）
}}

用户消息：{content}

请只返回 JSON，不要有其他内容。"""
    
    # 任务生成提示词
    TASK_PROMPT = """请为用户生成1个{dimension}维度的今日任务。
难度：{difficulty}，当前评分：{score}分，最近做过的：{recent}（避免重复）。
要求：具体可执行，有明确完成标准。

重要：{dim_guide}
{goal_context}
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
    
    # 维度指南
    DIMENSION_GUIDES = {
        "exercise": "运动类任务：体育锻炼、健身、跑步、跳绳、俯卧撑、深蹲、瑜伽、拉伸、散步、骑车、游泳等身体活动。不要包含学习、写作、阅读等非身体活动。",
        "diet": "饮食类任务：健康饮食、喝水、记录饮食、少吃零食、多吃蔬菜、控制热量、少油少盐等饮食相关。",
        "sleep": "睡眠类任务：早睡、放下手机、冥想、深呼吸、睡前放松、避免熬夜等睡眠相关。",
        "appearance": "外貌类任务：护肤、防晒、清洁面部、使用眼霜、敷面膜、整理仪容等外貌护理相关。",
    }
    
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
        dim_guide = self.DIMENSION_GUIDES.get(dimension, "")
        
        # 目标上下文
        goal_context = ""
        if goal_content:
            goal_context = f"用户目标：{goal_content}\n请生成与该目标相关的任务，帮助用户逐步实现目标。\n"
        
        return self.TASK_PROMPT.format(
            dimension=dimension,
            difficulty=diff_cn,
            score=score,
            recent=recent,
            dim_guide=dim_guide,
            goal_context=goal_context
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

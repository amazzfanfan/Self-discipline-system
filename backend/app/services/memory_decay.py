"""
MemoryDecay - 记忆重要性衰减服务
根据时间衰减和访问频率动态调整记忆的重要性评分
"""

import math
from datetime import datetime, timezone


class MemoryDecay:
    """记忆重要性衰减计算器

    使用指数衰减模型，结合访问频率进行加权：
    - 时间越久远，重要性衰减越大
    - 访问次数越多，衰减越慢（记忆被"刷新"）
    """

    # 衰减速率常数（越大衰减越快）
    DECAY_RATE = 0.01  # 每天衰减系数

    # 访问频率对衰减的缓解系数
    ACCESS_BOOST_FACTOR = 0.15

    # 最低重要性下限
    MIN_IMPORTANCE = 0.01

    def calculate_importance(
        self,
        original_importance: float,
        created_at: datetime,
        last_accessed: datetime | None,
        access_count: int,
    ) -> float:
        """计算经过衰减后的记忆重要性评分

        Args:
            original_importance: 原始重要性评分 (0-1)
            created_at: 记忆创建时间
            last_accessed: 最后访问时间（None 表示从未访问）
            access_count: 累计访问次数

        Returns:
            衰减后的重要性评分 (MIN_IMPORTANCE ~ 1.0)
        """
        now = datetime.now(timezone.utc)

        # 确保 created_at 是 aware datetime
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        # 计算距创建的天数
        days_since_creation = (now - created_at).total_seconds() / 86400.0
        if days_since_creation < 0:
            days_since_creation = 0.0

        # 计算距最后访问的天数（从未访问则用创建时间）
        reference_time = last_accessed if last_accessed else created_at
        if reference_time.tzinfo is None:
            reference_time = reference_time.replace(tzinfo=timezone.utc)
        days_since_access = (now - reference_time).total_seconds() / 86400.0
        if days_since_access < 0:
            days_since_access = 0.0

        # 基础衰减：基于距上次访问的时间（越近衰减越小）
        time_decay = math.exp(-self.DECAY_RATE * days_since_access)

        # 访问频率加权：访问次数越多，衰减越慢
        access_boost = math.exp(-self.ACCESS_BOOST_FACTOR / max(access_count, 1))
        # access_count=0 -> boost ≈ 0.86, access_count=5 -> boost ≈ 0.97, access_count=20 -> boost ≈ 0.993
        # 转换为 0~1 的衰减缓解因子（访问越多越接近 1，即不衰减）
        access_factor = 1.0 - (1.0 - access_boost) * 0.5

        # 综合衰减
        decay_multiplier = time_decay * access_factor

        # 计算最终重要性
        decayed = original_importance * decay_multiplier

        return max(decayed, self.MIN_IMPORTANCE)

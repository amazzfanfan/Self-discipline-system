from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.weight import WeightRecord


async def record_weight(db: AsyncSession, user_id: str, weight_kg: float) -> dict:
    """Record user weight for today. Returns result dict."""
    record = WeightRecord(user_id=user_id, weight_kg=weight_kg, recorded_at=date.today())
    db.add(record)
    return {"message": f"体重已记录：{weight_kg}kg", "weight_kg": weight_kg}

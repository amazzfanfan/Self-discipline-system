from datetime import date
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.weight import WeightRecord

router = APIRouter(prefix="/api/weight", tags=["weight"])

class WeightRequest(BaseModel):
    weight_kg: float

@router.post("")
async def record_weight(req: WeightRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    record = WeightRecord(user_id=user.id, weight_kg=req.weight_kg, recorded_at=date.today())
    db.add(record)
    return {"message": "体重已记录", "weight_kg": req.weight_kg}

@router.get("/history")
async def get_weight_history(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db), limit: int = 30):
    result = await db.execute(
        select(WeightRecord).where(WeightRecord.user_id == user.id)
        .order_by(WeightRecord.recorded_at.desc()).limit(limit)
    )
    return [
        {"weight_kg": float(w.weight_kg), "recorded_at": w.recorded_at.isoformat()}
        for w in result.scalars().all()
    ]

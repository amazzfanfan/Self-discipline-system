from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services.weight_service import record_weight as record_weight_service

router = APIRouter(prefix="/api/weight", tags=["weight"])

class WeightRequest(BaseModel):
    weight_kg: float

@router.post("")
async def record_weight(req: WeightRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await record_weight_service(db, str(user.id), req.weight_kg)

@router.get("/history")
async def get_weight_history(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db), limit: int = 30):
    from sqlalchemy import select
    from app.models.weight import WeightRecord
    result = await db.execute(
        select(WeightRecord).where(WeightRecord.user_id == user.id)
        .order_by(WeightRecord.recorded_at.desc()).limit(limit)
    )
    return [
        {"weight_kg": float(w.weight_kg), "recorded_at": w.recorded_at.isoformat()}
        for w in result.scalars().all()
    ]

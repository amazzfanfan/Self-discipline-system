from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services.weight_service import get_weight_history_payload, record_weight as record_weight_service

router = APIRouter(prefix="/api/weight", tags=["weight"])

class WeightRequest(BaseModel):
    weight_kg: float = Field(gt=20, lt=300)

@router.post("")
async def record_weight(req: WeightRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db, scope="function")):
    return await record_weight_service(db, str(user.id), req.weight_kg, source="manual_api")

@router.get("/history")
async def get_weight_history(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db, scope="function"), limit: int = 30):
    return await get_weight_history_payload(db, str(user.id), limit=limit)

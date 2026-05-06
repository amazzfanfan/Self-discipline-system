from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.score import UserScore, ScoreHistory


router = APIRouter(prefix="/api/scores", tags=["scores"])


@router.get("")
async def get_scores(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserScore).where(UserScore.user_id == user.id))
    scores = result.scalars().all()
    return [
        {"dimension": s.dimension.value, "score": float(s.score), "streak_days": s.streak_days}
        for s in scores
    ]


@router.get("/history")
async def get_score_history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
):
    result = await db.execute(
        select(ScoreHistory)
        .where(ScoreHistory.user_id == user.id)
        .order_by(ScoreHistory.created_at.desc())
        .limit(limit)
    )
    return [
        {
            "dimension": h.dimension.value,
            "delta": float(h.delta),
            "reason": h.reason,
            "created_at": h.created_at.isoformat(),
        }
        for h in result.scalars().all()
    ]


@router.get("/trends")
async def get_trends(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ScoreHistory)
        .where(ScoreHistory.user_id == user.id)
        .order_by(ScoreHistory.created_at)
    )
    history = result.scalars().all()

    trends = {}
    for h in history:
        dim = h.dimension.value
        if dim not in trends:
            trends[dim] = []
        trends[dim].append({"delta": float(h.delta), "date": h.created_at.isoformat()})

    return trends

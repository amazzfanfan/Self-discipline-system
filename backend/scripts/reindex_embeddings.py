"""Regenerate memory and goal vectors through the configured remote API."""

import asyncio

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import async_session
from app.models.goal import Goal
from app.models.memory import Memory
from app.services.llm_service import get_embedding


async def reindex() -> None:
    settings = get_settings()
    updated = 0
    async with async_session() as session:
        for model_class in (Memory, Goal):
            result = await session.execute(select(model_class).order_by(model_class.created_at))
            records = result.scalars().all()
            for record in records:
                record.embedding = await get_embedding(record.content)
                record.embedding_model = settings.EMBEDDING_MODEL
                updated += 1
                if updated % 20 == 0:
                    await session.commit()
                    print(f"已重建 {updated} 条向量")
        await session.commit()
    print(
        f"完成：{updated} 条记录已使用 {settings.EMBEDDING_MODEL} / "
        f"{settings.EMBEDDING_DIMENSION} 维重建"
    )


if __name__ == "__main__":
    asyncio.run(reindex())

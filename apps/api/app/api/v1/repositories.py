from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.db.models import Repository

router = APIRouter()


@router.get("/")
async def list_repositories(db: AsyncSession = Depends(get_db)) -> list[dict]:
    result = await db.execute(select(Repository).order_by(Repository.created_at.desc()))
    repos = result.scalars().all()
    return [
        {
            "id": r.id,
            "full_name": r.full_name,
            "owner": r.owner,
            "name": r.name,
            "created_at": r.created_at.isoformat(),
        }
        for r in repos
    ]

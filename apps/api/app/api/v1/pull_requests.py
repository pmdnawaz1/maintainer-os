from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.db.models import PullRequest

router = APIRouter()


@router.get("/")
async def list_pull_requests(
    repository_id: int | None = None,
    q: str | None = None,
    search_type: str = "hybrid",
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    if q:
        from app.core.memory import hybrid_search_pull_requests
        return await hybrid_search_pull_requests(db, q, limit=50, search_type=search_type)

    query = select(PullRequest).order_by(PullRequest.created_at.desc())
    if repository_id is not None:
        query = query.where(PullRequest.repository_id == repository_id)
    result = await db.execute(query)
    prs = result.scalars().all()
    return [
        {
            "id": pr.id,
            "github_number": pr.github_number,
            "title": pr.title,
            "status": pr.status,
            "created_at": pr.created_at.isoformat(),
        }
        for pr in prs
    ]


@router.get("/{pr_id}")
async def get_pull_request(pr_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(select(PullRequest).where(PullRequest.id == pr_id))
    pr = result.scalar_one_or_none()
    if not pr:
        raise HTTPException(status_code=404, detail="Pull request not found")
    return {
        "id": pr.id,
        "github_number": pr.github_number,
        "title": pr.title,
        "body": pr.body,
        "status": pr.status,
        "review_feedback": pr.review_feedback,
        "created_at": pr.created_at.isoformat(),
    }

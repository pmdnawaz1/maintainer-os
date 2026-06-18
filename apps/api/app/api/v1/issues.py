from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.db.models import Issue

router = APIRouter()


@router.get("/")
async def list_issues(
    repository_id: int | None = None,
    q: str | None = None,
    search_type: str = "hybrid",
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    if q:
        from app.core.memory import hybrid_search_issues
        return await hybrid_search_issues(db, q, limit=50, search_type=search_type)

    query = select(Issue).order_by(Issue.created_at.desc())
    if repository_id is not None:
        query = query.where(Issue.repository_id == repository_id)
    result = await db.execute(query)
    issues = result.scalars().all()
    return [
        {
            "id": i.id,
            "github_number": i.github_number,
            "title": i.title,
            "status": i.status,
            "triage_label": i.triage_label,
            "created_at": i.created_at.isoformat(),
        }
        for i in issues
    ]


@router.get("/{issue_id}")
async def get_issue(issue_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(select(Issue).where(Issue.id == issue_id))
    issue = result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    return {
        "id": issue.id,
        "github_number": issue.github_number,
        "title": issue.title,
        "body": issue.body,
        "status": issue.status,
        "triage_label": issue.triage_label,
        "ai_response": issue.ai_response,
        "created_at": issue.created_at.isoformat(),
    }

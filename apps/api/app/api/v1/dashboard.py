"""Dashboard summary endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.db.models import Issue, IssueStatus, PRStatus, PullRequest, Repository

router = APIRouter()


@router.get("/stats")
async def dashboard_stats(db: AsyncSession = Depends(get_db)) -> dict:
    open_issues = await db.scalar(
        select(func.count()).select_from(Issue).where(Issue.status == IssueStatus.open)
    ) or 0
    triaged_issues = await db.scalar(
        select(func.count()).select_from(Issue).where(Issue.status == IssueStatus.triaged)
    ) or 0
    open_prs = await db.scalar(
        select(func.count()).select_from(PullRequest).where(PullRequest.status == PRStatus.open)
    ) or 0
    repositories = await db.scalar(
        select(func.count()).select_from(Repository)
    ) or 0

    return {
        "open_issues": open_issues,
        "triaged_issues": triaged_issues,
        "open_prs": open_prs,
        "repositories": repositories,
    }


@router.get("/activity")
async def dashboard_activity(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    issues_result = await db.execute(
        select(Issue, Repository.full_name)
        .join(Repository, Issue.repository_id == Repository.id)
        .order_by(Issue.updated_at.desc())
        .limit(limit // 2)
    )
    pr_result = await db.execute(
        select(PullRequest, Repository.full_name)
        .join(Repository, PullRequest.repository_id == Repository.id)
        .order_by(PullRequest.updated_at.desc())
        .limit(limit // 2)
    )

    activity = []
    for issue, repo_name in issues_result:
        activity.append({
            "id": issue.id,
            "type": "issue",
            "title": issue.title,
            "repo": repo_name,
            "status": issue.status,
            "created_at": issue.updated_at.isoformat(),
        })
    for pr, repo_name in pr_result:
        activity.append({
            "id": pr.id,
            "type": "pull_request",
            "title": pr.title,
            "repo": repo_name,
            "status": pr.status,
            "created_at": pr.updated_at.isoformat(),
        })

    activity.sort(key=lambda x: x["created_at"], reverse=True)
    return activity[:limit]

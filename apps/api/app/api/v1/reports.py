"""Weekly health report endpoints."""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.db.models import Repository, WeeklyReport

router = APIRouter()


@router.post("/weekly")
async def trigger_weekly_report(
    repo: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Trigger weekly health report generation for a repository.

    The report is queued as a Celery task and generated asynchronously.
    Retrieve the result via GET /reports/weekly?repo={repo}.
    """
    repo_result = await db.execute(select(Repository).where(Repository.full_name == repo))
    repository = repo_result.scalar_one_or_none()
    if not repository:
        raise HTTPException(status_code=404, detail=f"Repository '{repo}' not found")

    from app.tasks.reports import generate_weekly_report

    generate_weekly_report.delay(repository.id)

    return {"status": "queued", "repo": repo}


@router.get("/weekly")
async def list_weekly_reports(
    repo: str | None = None,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Retrieve stored weekly health reports.

    Optionally filter by repository full name (e.g. ``owner/repo``).
    Results are ordered newest-first by week_start.
    """
    stmt = (
        select(WeeklyReport, Repository.full_name)
        .join(Repository, WeeklyReport.repository_id == Repository.id)
        .order_by(WeeklyReport.week_start.desc())
        .limit(limit)
    )
    if repo:
        stmt = stmt.where(Repository.full_name == repo)

    result = await db.execute(stmt)
    reports = []
    for record, full_name in result:
        reports.append({
            "id": record.id,
            "repository": full_name,
            "week_start": record.week_start.isoformat(),
            "week_end": record.week_end.isoformat(),
            "report": json.loads(record.report_json),
            "markdown": record.report_markdown,
            "created_at": record.created_at.isoformat(),
        })
    return reports

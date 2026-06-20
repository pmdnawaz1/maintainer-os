"""Weekly project health report generation."""

import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.models import Issue, IssueStatus, PRStatus, PullRequest, Repository, WeeklyReport
from app.services.github_auth import get_installation_token
from app.tasks.celery_app import celery_app

log = structlog.get_logger()

GITHUB_API = "https://api.github.com"


def _week_bounds() -> tuple[datetime, datetime]:
    """Return (week_start, week_end) for the previous calendar week (Mon–Sun, UTC)."""
    today = datetime.now(tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    # Go back to the Monday that started the current week
    days_since_monday = today.weekday()
    week_end = today - timedelta(days=days_since_monday)
    week_start = week_end - timedelta(days=7)
    return week_start.replace(tzinfo=None), week_end.replace(tzinfo=None)


async def _fetch_github_stats(installation_id: int, full_name: str) -> dict:
    """Fetch live GitHub repo stats (stars, forks, contributors) via installation token."""
    try:
        token = await get_installation_token(installation_id)
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        async with httpx.AsyncClient(timeout=15) as client:
            repo_resp = await client.get(f"{GITHUB_API}/repos/{full_name}", headers=headers)
            if repo_resp.status_code != 200:
                log.warning("github_repo_fetch_failed", repo=full_name, status=repo_resp.status_code)
                return {}
            repo_data = repo_resp.json()

            top_contributors: list[dict] = []
            contribs_resp = await client.get(
                f"{GITHUB_API}/repos/{full_name}/contributors",
                headers=headers,
                params={"per_page": 5},
            )
            if contribs_resp.status_code == 200:
                for c in contribs_resp.json()[:5]:
                    top_contributors.append({"login": c["login"], "contributions": c["contributions"]})

        return {
            "stars": repo_data.get("stargazers_count", 0),
            "forks": repo_data.get("forks_count", 0),
            "watchers": repo_data.get("watchers_count", 0),
            "open_issues_github": repo_data.get("open_issues_count", 0),
            "top_contributors": top_contributors,
        }
    except Exception:
        log.exception("github_stats_fetch_error", repo=full_name)
        return {}


async def _build_report_data(
    db: AsyncSession,
    repo: Repository,
    week_start: datetime,
    week_end: datetime,
) -> dict:
    """Aggregate DB metrics and GitHub stats into a structured report dict."""
    # --- Issues ---
    total_open_issues = await db.scalar(
        select(func.count()).select_from(Issue).where(
            Issue.repository_id == repo.id,
            Issue.status == IssueStatus.open,
        )
    ) or 0

    triaged_issues = await db.scalar(
        select(func.count()).select_from(Issue).where(
            Issue.repository_id == repo.id,
            Issue.status == IssueStatus.triaged,
        )
    ) or 0

    new_issues_this_week = await db.scalar(
        select(func.count()).select_from(Issue).where(
            Issue.repository_id == repo.id,
            Issue.created_at >= week_start,
            Issue.created_at < week_end,
        )
    ) or 0

    closed_issues_this_week = await db.scalar(
        select(func.count()).select_from(Issue).where(
            Issue.repository_id == repo.id,
            Issue.status.in_([IssueStatus.closed, IssueStatus.resolved]),
            Issue.updated_at >= week_start,
            Issue.updated_at < week_end,
        )
    ) or 0

    # --- Pull Requests ---
    total_open_prs = await db.scalar(
        select(func.count()).select_from(PullRequest).where(
            PullRequest.repository_id == repo.id,
            PullRequest.status == PRStatus.open,
        )
    ) or 0

    new_prs_this_week = await db.scalar(
        select(func.count()).select_from(PullRequest).where(
            PullRequest.repository_id == repo.id,
            PullRequest.created_at >= week_start,
            PullRequest.created_at < week_end,
        )
    ) or 0

    merged_prs_this_week = await db.scalar(
        select(func.count()).select_from(PullRequest).where(
            PullRequest.repository_id == repo.id,
            PullRequest.status == PRStatus.merged,
            PullRequest.updated_at >= week_start,
            PullRequest.updated_at < week_end,
        )
    ) or 0

    reviewed_prs_this_week = await db.scalar(
        select(func.count()).select_from(PullRequest).where(
            PullRequest.repository_id == repo.id,
            PullRequest.status == PRStatus.reviewed,
            PullRequest.updated_at >= week_start,
            PullRequest.updated_at < week_end,
        )
    ) or 0

    # --- GitHub live stats (optional — requires installation) ---
    github_stats: dict = {}
    if repo.installation_id:
        github_stats = await _fetch_github_stats(repo.installation_id, repo.full_name)

    return {
        "repository": repo.full_name,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "issues": {
            "total_open": total_open_issues,
            "triaged": triaged_issues,
            "new_this_week": new_issues_this_week,
            "closed_this_week": closed_issues_this_week,
        },
        "pull_requests": {
            "total_open": total_open_prs,
            "new_this_week": new_prs_this_week,
            "merged_this_week": merged_prs_this_week,
            "reviewed_this_week": reviewed_prs_this_week,
        },
        "github": github_stats,
    }


def _render_markdown(report: dict) -> str:
    """Render the report dict as a human-readable Markdown summary."""
    issues = report["issues"]
    prs = report["pull_requests"]
    gh = report.get("github", {})

    week_start = report["week_start"][:10]
    week_end = report["week_end"][:10]
    repo = report["repository"]

    md = f"# Weekly Health Report: {repo}\n\n"
    md += f"**Period**: {week_start} → {week_end}\n\n"

    md += "## Issues\n\n"
    md += "| Metric | Count |\n|--------|-------|\n"
    md += f"| Open | {issues['total_open']} |\n"
    md += f"| Triaged | {issues['triaged']} |\n"
    md += f"| New this week | {issues['new_this_week']} |\n"
    md += f"| Closed this week | {issues['closed_this_week']} |\n\n"

    md += "## Pull Requests\n\n"
    md += "| Metric | Count |\n|--------|-------|\n"
    md += f"| Open | {prs['total_open']} |\n"
    md += f"| New this week | {prs['new_this_week']} |\n"
    md += f"| Merged this week | {prs['merged_this_week']} |\n"
    md += f"| Reviewed this week | {prs['reviewed_this_week']} |\n\n"

    if gh:
        md += "## Repository Stats\n\n"
        md += f"- Stars: {gh.get('stars', 'N/A')}\n"
        md += f"- Forks: {gh.get('forks', 'N/A')}\n"
        md += f"- Watchers: {gh.get('watchers', 'N/A')}\n\n"

        contributors = gh.get("top_contributors", [])
        if contributors:
            md += "## Top Contributors\n\n"
            for c in contributors:
                md += f"- @{c['login']} ({c['contributions']} contributions)\n"
            md += "\n"

    return md


async def _async_generate_weekly_report(repo_id: int) -> dict:
    """Core async logic: build, render, and persist a weekly health report."""
    week_start, week_end = _week_bounds()
    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session() as db:
            repo_result = await db.execute(select(Repository).where(Repository.id == repo_id))
            repo = repo_result.scalar_one_or_none()
            if not repo:
                log.warning("weekly_report_repo_not_found", repo_id=repo_id)
                return {"status": "skipped", "reason": "repository not found"}

            report_data = await _build_report_data(db, repo, week_start, week_end)
            report_markdown = _render_markdown(report_data)

            record = WeeklyReport(
                repository_id=repo.id,
                week_start=week_start,
                week_end=week_end,
                report_json=json.dumps(report_data),
                report_markdown=report_markdown,
            )
            db.add(record)
            await db.commit()
            await db.refresh(record)

            log.info("weekly_report_saved", repo=repo.full_name, report_id=record.id)
            return {"status": "ok", "report_id": record.id, "repo": repo.full_name}
    finally:
        await engine.dispose()


async def _async_schedule_all_repos() -> dict:
    """Queue weekly report generation for every tracked repository."""
    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session() as db:
            result = await db.execute(select(Repository.id))
            repo_ids = [row[0] for row in result.fetchall()]
        for repo_id in repo_ids:
            generate_weekly_report.delay(repo_id)
        log.info("weekly_reports_queued", count=len(repo_ids))
        return {"status": "ok", "queued": len(repo_ids)}
    finally:
        await engine.dispose()


@celery_app.task(
    name="app.tasks.reports.generate_weekly_report",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def generate_weekly_report(self, repo_id: int) -> dict:
    """Celery task — generate and persist a weekly health report for a single repository."""
    try:
        result = asyncio.run(_async_generate_weekly_report(repo_id))
        log.info("weekly_report_task_done", repo_id=repo_id, result=result)
        return result
    except Exception as exc:
        log.error("weekly_report_task_failed", repo_id=repo_id, error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task(name="app.tasks.reports.generate_weekly_reports_for_all_repos")
def generate_weekly_reports_for_all_repos() -> dict:
    """Scheduled Celery beat task — queues weekly reports for all tracked repositories."""
    try:
        result = asyncio.run(_async_schedule_all_repos())
        return result
    except Exception:
        log.exception("weekly_reports_schedule_failed")
        return {"status": "error"}

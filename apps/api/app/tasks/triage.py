import asyncio
import structlog
from app.tasks.celery_app import celery_app

log = structlog.get_logger()


@celery_app.task(
    name="app.tasks.triage.run_triage",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def run_triage(self, installation_id: int, repo_full_name: str, issue_number: int) -> dict:
    """Celery task — runs the LangGraph triage agent for a GitHub issue."""
    try:
        from app.services.triage_service import triage_issue
        asyncio.run(triage_issue(installation_id, repo_full_name, issue_number))
        log.info("triage_task_done", repo=repo_full_name, issue=issue_number)
        return {"status": "ok", "issue": issue_number}
    except Exception as exc:
        log.error("triage_task_failed", repo=repo_full_name, issue=issue_number, error=str(exc))
        raise self.retry(exc=exc)

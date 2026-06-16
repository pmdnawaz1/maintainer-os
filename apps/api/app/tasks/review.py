import asyncio
import structlog
from app.tasks.celery_app import celery_app

log = structlog.get_logger()


@celery_app.task(
    name="app.tasks.review.run_review",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
)
def run_review(self, installation_id: int, repo_full_name: str, pr_number: int) -> dict:
    """Celery task — runs the LangGraph reviewer agent for a GitHub PR."""
    try:
        from app.services.review_service import review_pull_request
        asyncio.run(review_pull_request(installation_id, repo_full_name, pr_number))
        log.info("review_task_done", repo=repo_full_name, pr=pr_number)
        return {"status": "ok", "pr": pr_number}
    except Exception as exc:
        log.error("review_task_failed", repo=repo_full_name, pr=pr_number, error=str(exc))
        raise self.retry(exc=exc)

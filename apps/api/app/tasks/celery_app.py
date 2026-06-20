from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "maintainer_os",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.triage",
        "app.tasks.review",
        "app.tasks.reports",
        "app.tasks.release_task",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.tasks.triage.*": {"queue": "triage"},
        "app.tasks.review.*": {"queue": "review"},
        "app.tasks.reports.*": {"queue": "reports"},
        "app.tasks.release_task.*": {"queue": "releases"},
        "app.tasks.celery_app.*": {"queue": "embeddings"},
    },
    beat_schedule={
        # Every Monday at 09:00 UTC — generate health reports for all repos
        "weekly-health-reports": {
            "task": "app.tasks.reports.generate_weekly_reports_for_all_repos",
            "schedule": crontab(day_of_week="monday", hour=9, minute=0),
        },
    },
)


@celery_app.task(
    name="app.tasks.celery_app.generate_embedding_for_item",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def generate_embedding_for_item(self, item_id: int, item_type: str) -> None:
    """Generate and store a 1536-dim embedding for an Issue or PullRequest."""
    import asyncio
    try:
        asyncio.run(_async_generate_embedding(item_id, item_type))
    except Exception as exc:
        raise self.retry(exc=exc)


async def _async_generate_embedding(item_id: int, item_type: str) -> None:
    import openai
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.models import Issue, PullRequest

    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    try:
        async with async_session() as db:
            if item_type == "issue":
                result = await db.execute(select(Issue).where(Issue.id == item_id))
                item = result.scalar_one_or_none()
            elif item_type == "pull_request":
                result = await db.execute(select(PullRequest).where(PullRequest.id == item_id))
                item = result.scalar_one_or_none()
            else:
                return

            if not item:
                return

            text = f"{item.title}\n{item.body or ''}"
            response = await client.embeddings.create(
                model="text-embedding-3-small",
                input=text,
            )
            item.embedding = response.data[0].embedding
            await db.commit()
    finally:
        await engine.dispose()

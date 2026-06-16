from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "maintainer_os",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.triage",
        "app.tasks.review",
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
    },
)

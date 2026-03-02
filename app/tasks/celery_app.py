"""Celery application instance + beat schedule."""
from celery import Celery
from celery.schedules import crontab

from app.settings import settings

celery_app = Celery(
    "faceless",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.task_definitions"],
)

# ── Serialization ─────────────────────────────────────────────────────────────
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Reliability
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Result expiry
    result_expires=86400 * 7,  # 7 days
    # Queues
    task_default_queue="default",
    task_queues={
        "default": {},
        "asset_gen": {},
    },
    # Routing
    task_routes={
        "app.tasks.task_definitions.generate_asset_task": {"queue": "asset_gen"},
    },
)

# ── Beat schedule ─────────────────────────────────────────────────────────────
hour, minute = (int(x) for x in settings.POST_TIME.split(":"))

celery_app.conf.beat_schedule = {
    "daily-pipeline": {
        "task": "app.tasks.task_definitions.run_daily_pipeline_task",
        "schedule": crontab(hour=hour, minute=minute),
        "args": [],
    }
}

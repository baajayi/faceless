"""Celery task definitions for the faceless pipeline.

Task graph:
  run_daily_pipeline_task(run_id)
    └─ chain(
         trend_research_task,
         topic_selection_task,
         scriptwriter_task,
         storyboard_task,
         group(generate_asset_task(shot_0), ...) | video_assembly_task,
         metadata_task,
         qa_moderation_task,
         publish_task,
         finalize_run_task
       )
"""
from __future__ import annotations

import traceback
from datetime import date

from celery import chain, chord, group

from app.tasks.celery_app import celery_app
from app.utils.logging import get_logger, set_run_id

log = get_logger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _record_and_fail(run_id: str, stage: str, exc: Exception) -> None:
    from app.db.models import Error, Run, RunStatus
    from app.db.session import get_db
    from app.utils.notifications import notify_failure

    tb = traceback.format_exc()
    with get_db() as db:
        err = Error(run_id=run_id, stage=stage, message=str(exc)[:2000], traceback=tb[:5000])
        db.add(err)
        run = db.get(Run, run_id)
        if run:
            run.status = RunStatus.FAILED

    notify_failure(run_id=run_id, stage=stage, message=str(exc))


# ── Entry point ───────────────────────────────────────────────────────────────

@celery_app.task(bind=True, max_retries=0)
def run_daily_pipeline_task(self, run_id: str | None = None) -> str:
    """Top-level task: triggers the daily pipeline for today or the given run_id."""
    from app.pipelines.daily_pipeline import get_or_create_run
    from app.db.session import get_db

    if run_id is None:
        run_date_str = str(date.today())
        with get_db() as db:
            run = get_or_create_run(db, run_date_str)
            run_id = run.id

    set_run_id(run_id)
    log.info("task.run_daily_pipeline", run_id=run_id)

    # Build and execute the chain
    pipeline = chain(
        trend_research_task.si(run_id),
        topic_selection_task.si(run_id),
        scriptwriter_task.si(run_id),
        storyboard_task.si(run_id),
        # asset generation and assembly handled as a single task that
        # internally handles shots (simpler than dynamic chord)
        asset_generation_task.si(run_id),
        video_assembly_task.si(run_id),
        metadata_task.si(run_id),
        qa_moderation_task.si(run_id),
        publish_task.si(run_id),
        finalize_run_task.si(run_id),
    )

    pipeline.delay()
    return run_id


# ── Individual stage tasks ────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
    reject_on_worker_lost=True,
)
def trend_research_task(self, run_id: str) -> str:
    set_run_id(run_id)
    try:
        from app.agents.trend_research import run_trend_research
        from app.settings import settings
        run_trend_research(run_id, region=settings.REGION)
        return run_id
    except Exception as exc:
        try:
            raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            _record_and_fail(run_id, "trend_research", exc)
            raise


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
    reject_on_worker_lost=True,
)
def topic_selection_task(self, run_id: str) -> str:
    set_run_id(run_id)
    try:
        from app.agents.topic_selection import run_topic_selection
        run_topic_selection(run_id)
        return run_id
    except Exception as exc:
        try:
            raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            _record_and_fail(run_id, "topic_selection", exc)
            raise


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
    reject_on_worker_lost=True,
)
def scriptwriter_task(self, run_id: str, revision_feedback: str = "") -> str:
    set_run_id(run_id)
    try:
        from app.agents.scriptwriter import run_scriptwriter
        run_scriptwriter(run_id, revision_feedback=revision_feedback)
        return run_id
    except Exception as exc:
        try:
            raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            _record_and_fail(run_id, "scriptwriter", exc)
            raise


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
    reject_on_worker_lost=True,
)
def storyboard_task(self, run_id: str) -> str:
    set_run_id(run_id)
    try:
        from app.agents.storyboard import run_storyboard
        run_storyboard(run_id)
        return run_id
    except Exception as exc:
        try:
            raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            _record_and_fail(run_id, "storyboard", exc)
            raise


@celery_app.task(
    bind=True,
    max_retries=4,
    default_retry_delay=60,
    acks_late=True,
    reject_on_worker_lost=True,
    queue="asset_gen",
)
def generate_asset_task(self, run_id: str, shot_index: int) -> str:
    """Generate assets for a single shot (used for parallel execution)."""
    set_run_id(run_id)
    try:
        from app.agents.asset_generator import run_asset_generation
        run_asset_generation(run_id, shot_index=shot_index)
        return run_id
    except Exception as exc:
        try:
            raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            _record_and_fail(run_id, f"asset_gen_shot_{shot_index}", exc)
            raise


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
    reject_on_worker_lost=True,
    queue="asset_gen",
)
def asset_generation_task(self, run_id: str) -> str:
    """Generate all assets (sequential mode for direct chain)."""
    set_run_id(run_id)
    try:
        from app.agents.asset_generator import run_asset_generation
        run_asset_generation(run_id)
        return run_id
    except Exception as exc:
        try:
            raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            _record_and_fail(run_id, "asset_generation", exc)
            raise


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
    reject_on_worker_lost=True,
)
def video_assembly_task(self, run_id: str) -> str:
    set_run_id(run_id)
    try:
        from app.agents.video_assembler import run_video_assembly
        run_video_assembly(run_id)
        return run_id
    except Exception as exc:
        try:
            raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            _record_and_fail(run_id, "video_assembly", exc)
            raise


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
    reject_on_worker_lost=True,
)
def metadata_task(self, run_id: str) -> str:
    set_run_id(run_id)
    try:
        from app.agents.metadata_agent import run_metadata_agent
        run_metadata_agent(run_id)
        return run_id
    except Exception as exc:
        try:
            raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            _record_and_fail(run_id, "metadata", exc)
            raise


@celery_app.task(
    bind=True,
    max_retries=1,
    default_retry_delay=60,
    acks_late=True,
    reject_on_worker_lost=True,
)
def qa_moderation_task(self, run_id: str) -> str:
    set_run_id(run_id)
    try:
        from app.pipelines.daily_pipeline import _qa_with_retry
        _qa_with_retry(run_id)
        return run_id
    except Exception as exc:
        try:
            raise self.retry(exc=exc, countdown=60)
        except self.MaxRetriesExceededError:
            _record_and_fail(run_id, "qa_moderation", exc)
            raise


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
    reject_on_worker_lost=True,
)
def publish_task(self, run_id: str) -> str:
    set_run_id(run_id)
    try:
        from app.agents.publisher import run_publisher
        run_publisher(run_id)
        return run_id
    except Exception as exc:
        try:
            raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            _record_and_fail(run_id, "publisher", exc)
            raise


@celery_app.task(bind=True, max_retries=3)
def finalize_run_task(self, run_id: str) -> str:
    """Final bookkeeping — log completion metrics."""
    set_run_id(run_id)
    from app.db.models import Run
    from app.db.session import get_db

    with get_db() as db:
        run = db.get(Run, run_id)
        if run:
            log.info(
                "task.finalized",
                run_id=run_id,
                status=run.status,
                cost_usd=float(run.cost_usd),
            )
    return run_id

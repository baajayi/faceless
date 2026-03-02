"""Dead-letter / retry pipeline handler.

Handles runs that ended in FAILED status by re-queueing them
from the last successful stage.
"""
from __future__ import annotations

from app.db.models import Error, Run, RunStatus
from app.db.session import get_db
from app.utils.logging import get_logger

log = get_logger(__name__)

# Stage order for resumption
STAGE_ORDER = [
    "trend_research",
    "topic_selection",
    "scriptwriter",
    "storyboard",
    "asset_generation",
    "video_assembly",
    "metadata",
    "qa_moderation",
    "publisher",
]


def retry_failed_run(run_id: str) -> str:
    """Attempt to resume a FAILED run from its last failed stage.

    Returns: 'queued' | 'skipped'
    """
    with get_db() as db:
        run = db.get(Run, run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")

        if run.status not in (RunStatus.FAILED, RunStatus.NEEDS_REVIEW):
            log.info("retry.not_failed", run_id=run_id, status=run.status)
            return "skipped"

        # Find last error stage
        last_error = (
            db.query(Error)
            .filter(Error.run_id == run_id, Error.retryable == True)
            .order_by(Error.created_at.desc())
            .first()
        )
        failed_stage = last_error.stage if last_error else "trend_research"

    log.info("retry.attempt", run_id=run_id, failed_stage=failed_stage)

    # Re-trigger from that stage via Celery
    from app.tasks.task_definitions import run_daily_pipeline_task
    task = run_daily_pipeline_task.delay(run_id)

    with get_db() as db:
        run = db.get(Run, run_id)
        run.status = RunStatus.PENDING
        run.celery_task_id = task.id
        db.flush()

    log.info("retry.queued", run_id=run_id, task_id=task.id)
    return "queued"


def get_failed_runs() -> list[str]:
    """Return list of run_ids that are in FAILED or NEEDS_REVIEW status."""
    with get_db() as db:
        runs = (
            db.query(Run)
            .filter(Run.status.in_([RunStatus.FAILED, RunStatus.NEEDS_REVIEW]))
            .all()
        )
        return [r.id for r in runs]

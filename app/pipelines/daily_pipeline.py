"""Daily pipeline orchestrator.

get_or_create_run — idempotent run record management.
trigger_run — orchestrates the full agent chain synchronously (no Celery).
"""
from __future__ import annotations

import traceback
from datetime import date

from app.agents.asset_generator import run_asset_generation
from app.agents.metadata_agent import run_metadata_agent
from app.agents.publisher import run_publisher
from app.agents.qa_moderator import run_qa_moderation
from app.agents.scriptwriter import run_scriptwriter
from app.agents.storyboard import run_storyboard
from app.agents.topic_selection import run_topic_selection
from app.agents.trend_research import run_trend_research
from app.agents.video_assembler import run_video_assembly
from app.db.models import Error, Run, RunStatus
from app.db.session import get_db
from app.settings import settings
from app.utils.cost_tracker import CostTracker
from app.utils.logging import get_logger, set_run_id
from app.utils.notifications import notify_failure

log = get_logger(__name__)


def get_or_create_run(db, run_date_str: str, force: bool = False) -> Run:
    """Get existing run or create new one. force=True resets status to PENDING."""
    run_date = date.fromisoformat(run_date_str)
    run = db.query(Run).filter(Run.run_date == run_date).first()

    if run:
        if force:
            run.status = RunStatus.PENDING
            run.cost_usd = 0
            db.flush()
            log.info("pipeline.run_reset", run_id=run.id)
        return run

    run = Run(run_date=run_date, status=RunStatus.PENDING)
    db.add(run)
    db.flush()
    log.info("pipeline.run_created", run_id=run.id, run_date=run_date_str)
    return run


def trigger_run(run_date_str: str, force: bool = False) -> str:
    """Execute the full pipeline synchronously.

    Returns run_id.
    """
    with get_db() as db:
        run = get_or_create_run(db, run_date_str, force=force)
        run_id = run.id

        if run.status == RunStatus.DONE and not force:
            log.info("pipeline.already_done", run_id=run_id, run_date=run_date_str)
            return run_id

    set_run_id(run_id)
    log.info("pipeline.start", run_id=run_id, run_date=run_date_str)

    stages = [
        ("trend_research", lambda: run_trend_research(run_id, region=settings.REGION)),
        ("topic_selection", lambda: run_topic_selection(run_id)),
        ("scriptwriter", lambda: run_scriptwriter(run_id)),
        ("storyboard", lambda: run_storyboard(run_id)),
        ("asset_generation", lambda: run_asset_generation(run_id)),
        ("video_assembly", lambda: run_video_assembly(run_id)),
        ("metadata", lambda: run_metadata_agent(run_id)),
        ("qa_moderation", lambda: _qa_with_retry(run_id)),
        ("publisher", lambda: run_publisher(run_id)),
    ]

    for stage_name, stage_fn in stages:
        try:
            log.info(f"pipeline.stage.start", stage=stage_name, run_id=run_id)
            result = stage_fn()
            log.info(f"pipeline.stage.done", stage=stage_name, run_id=run_id, result=str(result)[:100])
        except Exception as exc:
            tb = traceback.format_exc()
            log.error("pipeline.stage.failed", stage=stage_name, run_id=run_id, error=str(exc))
            _record_error(run_id, stage_name, str(exc), tb)
            _mark_failed(run_id, stage_name)
            notify_failure(run_id=run_id, stage=stage_name, message=str(exc), run_date=run_date_str)
            raise

    log.info("pipeline.complete", run_id=run_id, run_date=run_date_str)
    return run_id


def _qa_with_retry(run_id: str) -> dict:
    """Run QA; if it fails and retry_count < 1, re-run scriptwriter → downstream agents."""
    qa_report = run_qa_moderation(run_id)

    if not qa_report["passed"]:
        failures_text = "; ".join(f["detail"] for f in qa_report["failures"])
        log.warning("pipeline.qa_failed", run_id=run_id, failures=failures_text)

        # Check retry count from errors table
        with get_db() as db:
            error_count = (
                db.query(Error)
                .filter(Error.run_id == run_id, Error.stage == "qa_retry")
                .count()
            )

        if error_count < 1:
            log.info("pipeline.qa_retry", run_id=run_id)
            _record_error(run_id, "qa_retry", failures_text, "", retryable=False)

            # Re-run from scriptwriter
            run_scriptwriter(run_id, revision_feedback=f"REVISION NEEDED: {failures_text}")
            run_storyboard(run_id)
            run_asset_generation(run_id)
            run_video_assembly(run_id)

            # Second QA attempt
            qa_report = run_qa_moderation(run_id)
            if not qa_report["passed"]:
                _mark_needs_review(run_id)
                raise ValueError(f"QA failed after retry: {failures_text}")
        else:
            _mark_needs_review(run_id)
            raise ValueError(f"QA failed (no more retries): {failures_text}")

    return qa_report


def _record_error(
    run_id: str,
    stage: str,
    message: str,
    tb: str,
    retryable: bool = True,
) -> None:
    with get_db() as db:
        err = Error(
            run_id=run_id,
            stage=stage,
            message=message[:2000],
            traceback=tb[:5000],
            retryable=retryable,
        )
        db.add(err)


def _mark_failed(run_id: str, stage: str) -> None:
    with get_db() as db:
        run = db.get(Run, run_id)
        if run:
            run.status = RunStatus.FAILED


def _mark_needs_review(run_id: str) -> None:
    with get_db() as db:
        run = db.get(Run, run_id)
        if run:
            run.status = RunStatus.NEEDS_REVIEW

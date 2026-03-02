"""Run management API routes."""
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.db.models import Run, RunStatus
from app.db.session import get_db

router = APIRouter(prefix="/runs", tags=["runs"])


class RunResponse(BaseModel):
    id: str
    run_date: str
    status: str
    cost_usd: float
    celery_task_id: Optional[str]
    created_at: str
    updated_at: str


class TriggerRequest(BaseModel):
    run_date: Optional[str] = None  # YYYY-MM-DD, defaults to today
    force: bool = False


@router.get("", response_model=list[RunResponse])
def list_runs(
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0),
):
    """List recent pipeline runs."""
    with get_db() as db:
        runs = (
            db.query(Run)
            .order_by(Run.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return [
            RunResponse(
                id=r.id,
                run_date=str(r.run_date),
                status=r.status,
                cost_usd=float(r.cost_usd),
                celery_task_id=r.celery_task_id,
                created_at=r.created_at.isoformat(),
                updated_at=r.updated_at.isoformat(),
            )
            for r in runs
        ]


@router.get("/{run_id}", response_model=RunResponse)
def get_run(run_id: str):
    """Get a specific run by ID."""
    with get_db() as db:
        run = db.get(Run, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        return RunResponse(
            id=run.id,
            run_date=str(run.run_date),
            status=run.status,
            cost_usd=float(run.cost_usd),
            celery_task_id=run.celery_task_id,
            created_at=run.created_at.isoformat(),
            updated_at=run.updated_at.isoformat(),
        )


@router.post("/trigger")
def trigger_run(body: TriggerRequest):
    """Trigger a pipeline run via Celery."""
    from app.tasks.task_definitions import run_daily_pipeline_task
    from app.pipelines.daily_pipeline import get_or_create_run

    run_date_str = body.run_date or str(date.today())

    with get_db() as db:
        run = get_or_create_run(db, run_date_str, force=body.force)
        if run.status == RunStatus.DONE and not body.force:
            return {"message": "Run already DONE for this date", "run_id": run.id}

        task = run_daily_pipeline_task.delay(run.id)
        run.celery_task_id = task.id
        db.flush()

    return {"run_id": run.id, "celery_task_id": task.id, "status": "queued"}

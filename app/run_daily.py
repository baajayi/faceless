"""CLI entry point: python -m app.run_daily [--date YYYY-MM-DD] [--force]

Runs the pipeline synchronously (no Celery required) for local dev/testing.
Inside Docker with Celery running, use the /runs/trigger API or Celery beat instead.
"""
import sys
from datetime import date

import click

from app.utils.logging import configure_logging, get_logger

configure_logging()
log = get_logger(__name__)


@click.command()
@click.option(
    "--date",
    "run_date",
    default=None,
    help="Run date in YYYY-MM-DD format. Defaults to today.",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Re-run even if a DONE run exists for this date.",
)
def main(run_date: str | None, force: bool) -> None:
    """Run the daily faceless TikTok video pipeline."""
    if run_date is None:
        run_date = str(date.today())

    try:
        date.fromisoformat(run_date)
    except ValueError:
        click.echo(f"ERROR: Invalid date format '{run_date}'. Use YYYY-MM-DD.", err=True)
        sys.exit(1)

    click.echo(f"Starting pipeline for {run_date} (force={force})")
    log.info("run_daily.start", run_date=run_date, force=force)

    from app.pipelines.daily_pipeline import trigger_run

    try:
        run_id = trigger_run(run_date, force=force)
        click.echo(f"Pipeline complete. Run ID: {run_id}")
        click.echo(f"Output: output/{run_date}/")
    except Exception as exc:
        click.echo(f"Pipeline FAILED: {exc}", err=True)
        log.error("run_daily.failed", error=str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()

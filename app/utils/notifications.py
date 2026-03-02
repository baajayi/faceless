"""Slack webhook notifications on failure."""
import httpx

from app.settings import settings
from app.utils.logging import get_logger

log = get_logger(__name__)


def notify_failure(
    run_id: str,
    stage: str,
    message: str,
    run_date: str = "",
) -> None:
    """Send a Slack webhook message on pipeline failure."""
    if not settings.SLACK_WEBHOOK_URL:
        return

    text = (
        f":x: *Faceless Pipeline Failure*\n"
        f"• Run ID: `{run_id}`\n"
        f"• Date: `{run_date}`\n"
        f"• Stage: `{stage}`\n"
        f"• Error: {message}"
    )

    try:
        response = httpx.post(
            settings.SLACK_WEBHOOK_URL,
            json={"text": text},
            timeout=10,
        )
        response.raise_for_status()
        log.info("notification.sent", run_id=run_id, stage=stage)
    except Exception as exc:
        log.warning("notification.failed", error=str(exc))


def notify_success(run_id: str, run_date: str, export_path: str) -> None:
    """Send a Slack webhook message on pipeline success."""
    if not settings.SLACK_WEBHOOK_URL:
        return

    text = (
        f":white_check_mark: *Faceless Pipeline Complete*\n"
        f"• Run ID: `{run_id}`\n"
        f"• Date: `{run_date}`\n"
        f"• Export: `{export_path}`"
    )

    try:
        response = httpx.post(
            settings.SLACK_WEBHOOK_URL,
            json={"text": text},
            timeout=10,
        )
        response.raise_for_status()
    except Exception as exc:
        log.warning("notification.success_failed", error=str(exc))

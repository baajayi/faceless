"""Agent I — Publisher.

MODE_C: Creates final export package in output/{run_date}/
Sets publish_job.status = READY_TO_POST and run.status = DONE.
"""
from __future__ import annotations

from app.db.models import PublishJob, PublishStatus, Run, RunStatus
from app.db.session import get_db
from app.services.tiktok_publish.mode_c import export_package
from app.services.youtube_publish.youtube_uploader import upload_video
from app.settings import settings
from app.utils.logging import get_logger
from app.utils.notifications import notify_success

log = get_logger(__name__)


def run_publisher(run_id: str) -> str:
    """Execute publishing for the given run.

    Returns export path string.
    """
    log.info("agent_i.start", run_id=run_id, mode=settings.PUBLISH_MODE)

    with get_db() as db:
        run = db.get(Run, run_id)
        run_date = str(run.run_date)
        run.status = RunStatus.PUBLISHING
        db.flush()

        pub_job = db.query(PublishJob).filter(PublishJob.run_id == run_id).first()
        if not pub_job:
            raise ValueError(f"No publish job for run {run_id}")

        caption = pub_job.caption or ""
        hashtags = pub_job.hashtags or []
        metadata = pub_job.metadata_json or {}

    if settings.PUBLISH_MODE == "C":
        export_path = _mode_c_export(run_date, caption, hashtags, metadata)
    elif settings.PUBLISH_MODE == "A":
        from app.services.tiktok_publish.mode_a import post_video
        from app.storage.artifact_paths import final_video_path
        post_video(final_video_path(run_date), caption, hashtags)
        export_path = str(final_video_path(run_date))
    elif settings.PUBLISH_MODE == "Y":
        export_path = _mode_y_publish(run_date, caption, hashtags, metadata)
    else:
        raise ValueError(f"Unsupported PUBLISH_MODE: {settings.PUBLISH_MODE}")

    # Update DB
    with get_db() as db:
        run = db.get(Run, run_id)
        pub_job = db.query(PublishJob).filter(PublishJob.run_id == run_id).first()

        pub_job.status = PublishStatus.READY_TO_POST
        pub_job.export_path = export_path
        run.status = RunStatus.DONE
        db.flush()

    notify_success(run_id=run_id, run_date=run_date, export_path=export_path)
    log.info("agent_i.complete", run_id=run_id, export_path=export_path)
    return export_path


def _mode_c_export(
    run_date: str,
    caption: str,
    hashtags: list[str],
    metadata: dict,
) -> str:
    return export_package(
        run_date=run_date,
        caption=caption,
        hashtags=hashtags,
        metadata=metadata,
    )


def _mode_y_publish(
    run_date: str,
    caption: str,
    hashtags: list[str],
    metadata: dict,
) -> str:
    from app.storage.artifact_paths import final_video_path, thumbnail_path

    title = metadata.get("title") or caption[:95]
    description = caption
    if hashtags:
        description = f"{caption}\n\n" + " ".join(f"#{h.lstrip('#')}" for h in hashtags)

    result = upload_video(
        video_path=final_video_path(run_date),
        title=title,
        description=description,
        tags=[h.lstrip("#") for h in hashtags],
        thumbnail_path=thumbnail_path(run_date),
    )
    return result.get("id", "")

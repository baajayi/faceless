"""MODE_C Publisher — exports a ready-to-post package to the output directory."""
import json
import shutil
from pathlib import Path
from typing import Any

from app.storage.artifact_paths import (
    caption_path,
    final_video_path,
    hashtags_path,
    metadata_json_path,
    run_dir,
    thumbnail_path,
)
from app.utils.logging import get_logger

log = get_logger(__name__)


def export_package(
    run_date: str,
    caption: str,
    hashtags: list[str],
    metadata: dict[str, Any],
) -> str:
    """Export the final video + metadata as a publish-ready package.

    Creates / populates:
      output/{run_date}/final.mp4
      output/{run_date}/thumbnail.jpg
      output/{run_date}/caption.txt
      output/{run_date}/hashtags.txt
      output/{run_date}/metadata.json

    Returns the export directory path as a string.
    """
    export_dir = run_dir(run_date)
    export_dir.mkdir(parents=True, exist_ok=True)

    # final.mp4 and thumbnail.jpg should already exist (produced by Agent F)
    video_src = final_video_path(run_date)
    thumb_src = thumbnail_path(run_date)

    if not video_src.exists():
        raise FileNotFoundError(f"Final video not found: {video_src}")

    # caption.txt
    cap_dest = caption_path(run_date)
    cap_dest.write_text(caption.strip(), encoding="utf-8")
    log.info("mode_c.caption_written", path=str(cap_dest))

    # hashtags.txt
    ht_dest = hashtags_path(run_date)
    ht_dest.write_text("\n".join(f"#{h.lstrip('#')}" for h in hashtags), encoding="utf-8")
    log.info("mode_c.hashtags_written", path=str(ht_dest))

    # metadata.json
    meta_dest = metadata_json_path(run_date)
    meta_dest.write_text(
        json.dumps(metadata, indent=2, default=str),
        encoding="utf-8",
    )
    log.info("mode_c.metadata_written", path=str(meta_dest))

    log.info(
        "mode_c.export_complete",
        run_date=run_date,
        export_dir=str(export_dir),
    )
    return str(export_dir)

"""Canonical artifact paths per run_id / run_date."""
import os
from pathlib import Path

from app.settings import settings


def run_dir(run_date: str) -> Path:
    """Root directory for all artifacts of a daily run."""
    return Path(settings.ARTIFACTS_DIR) / run_date


def shot_image_path(run_date: str, shot_index: int) -> Path:
    return run_dir(run_date) / "images" / f"shot_{shot_index:02d}.png"


def shot_audio_path(run_date: str, shot_index: int) -> Path:
    return run_dir(run_date) / "audio" / f"shot_{shot_index:02d}.mp3"


def shot_video_path(run_date: str, shot_index: int) -> Path:
    return run_dir(run_date) / "clips" / f"shot_{shot_index:02d}.mp4"


def music_path(run_date: str) -> Path:
    return run_dir(run_date) / "audio" / "background_music.mp3"


def final_video_path(run_date: str) -> Path:
    return run_dir(run_date) / "final.mp4"


def thumbnail_path(run_date: str) -> Path:
    return run_dir(run_date) / "thumbnail.jpg"


def caption_path(run_date: str) -> Path:
    return run_dir(run_date) / "caption.txt"


def hashtags_path(run_date: str) -> Path:
    return run_dir(run_date) / "hashtags.txt"


def metadata_json_path(run_date: str) -> Path:
    return run_dir(run_date) / "metadata.json"


def ensure_dirs(run_date: str) -> None:
    """Create all subdirectories for a run."""
    base = run_dir(run_date)
    for sub in ("images", "audio", "clips"):
        (base / sub).mkdir(parents=True, exist_ok=True)

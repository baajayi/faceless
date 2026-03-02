"""MODE_A Publisher — TikTok Content Posting API (stub).

To activate MODE_A:
  1. Register a TikTok developer app at https://developers.tiktok.com/
  2. Get approved for the Content Posting API
  3. Set env vars: TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_ACCESS_TOKEN
  4. Set PUBLISH_MODE=A in your .env

Current status: NOT IMPLEMENTED — raises NotImplementedError.
"""
from pathlib import Path

from app.settings import settings
from app.utils.logging import get_logger

log = get_logger(__name__)


def post_video(
    video_path: Path,
    caption: str,
    hashtags: list[str],
) -> dict:
    """Upload and publish a video via TikTok Content Posting API.

    Raises:
        NotImplementedError: Always — MODE_A not yet implemented.
        ValueError: If required TikTok credentials are missing.
    """
    if not settings.TIKTOK_ACCESS_TOKEN:
        raise ValueError(
            "TIKTOK_ACCESS_TOKEN not set. "
            "Configure TikTok credentials to use MODE_A."
        )

    raise NotImplementedError(
        "TikTok Content Posting API (MODE_A) is not yet implemented. "
        "Use PUBLISH_MODE=C (manual export) instead. "
        "See app/services/tiktok_publish/mode_a.py for implementation guidance."
    )

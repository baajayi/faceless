"""Background music service.

Default: MUSIC_MODE=none (no music).
Stub for royalty_free mode (Pixabay/FreeSound API placeholder).
"""
from pathlib import Path
from typing import Optional

from app.settings import settings
from app.utils.logging import get_logger

log = get_logger(__name__)


def get_background_music(
    duration_s: float,
    output_path: Optional[Path] = None,
) -> Optional[Path]:
    """Fetch or generate background music for the given duration.

    Returns path to music file, or None if MUSIC_MODE=none.
    """
    if settings.MUSIC_MODE == "none":
        log.info("music.disabled", mode="none")
        return None

    if settings.MUSIC_MODE == "royalty_free":
        return _fetch_royalty_free(duration_s, output_path)

    if settings.MUSIC_MODE == "generated":
        log.warning("music.generated_not_implemented")
        return None

    return None


def _fetch_royalty_free(
    duration_s: float,
    output_path: Optional[Path] = None,
) -> Optional[Path]:
    """Placeholder for royalty-free music fetch (Pixabay / FreeSound API).

    To implement: sign up for Pixabay API, search for kid-friendly music,
    download a clip that covers duration_s, save to output_path.
    """
    log.warning(
        "music.royalty_free_stub",
        message="Royalty-free music fetch not yet implemented. "
                "Add Pixabay/FreeSound API key to .env and implement this method.",
    )
    # TODO: implement actual API call
    # Example Pixabay endpoint:
    # GET https://pixabay.com/api/videos/music/?key=API_KEY&q=kids+educational&duration=30
    return None

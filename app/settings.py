from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Core infrastructure ───────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql://faceless:faceless@postgres:5432/faceless"
    REDIS_URL: str = "redis://redis:6379/0"
    OPENAI_API_KEY: str = ""
    YOUTUBE_API_KEY: str = ""

    # ── Pipeline config ───────────────────────────────────────────────────────
    REGION: str = "US"
    POST_TIME: str = "06:00"  # HH:MM UTC for Celery beat schedule
    AGE_BAND: str = "4-10"
    VISUAL_STYLE: Literal["cartoon", "paper-cut", "3d-toy", "whiteboard"] = "cartoon"

    # ── TTS / Voice ───────────────────────────────────────────────────────────
    VOICE_PROVIDER: str = "openai"
    VOICE_ID: str = "nova"  # child-friendly OpenAI TTS voice

    # ── Music ─────────────────────────────────────────────────────────────────
    MUSIC_MODE: Literal["none", "royalty_free", "generated"] = "none"

    # ── Publishing ────────────────────────────────────────────────────────────
    PUBLISH_MODE: Literal["A", "B", "C", "Y"] = "C"

    # ── YouTube Publishing (MODE_Y) ──────────────────────────────────────────
    YOUTUBE_CLIENT_ID: Optional[str] = None
    YOUTUBE_CLIENT_SECRET: Optional[str] = None
    YOUTUBE_REFRESH_TOKEN: Optional[str] = None
    YOUTUBE_PRIVACY_STATUS: Literal["public", "unlisted", "private"] = "public"
    YOUTUBE_UPLOAD_THUMBNAIL: bool = True

    # ── Text / OCR / Spellcheck ───────────────────────────────────────────────
    IMAGE_TEXT_ENFORCEMENT: bool = True
    IMAGE_TEXT_MAX_ATTEMPTS: int = 6
    IMAGE_TEXT_OCR_MODEL: str = "gpt-4o"
    IMAGE_TEXT_FALLBACK: Literal["no_text_regen"] = "no_text_regen"
    SPELLCHECK_ENABLED: bool = True
    SPELLCHECK_ALLOWLIST_PATH: str = "configs/spellcheck_allowlist.txt"

    # ── Safety ────────────────────────────────────────────────────────────────
    SAFETY_STRICTNESS: Literal["low", "med", "high"] = "high"

    # ── Cost guard ────────────────────────────────────────────────────────────
    COST_LIMIT_PER_DAY: float = 5.0  # USD hard cap

    # ── Observability ─────────────────────────────────────────────────────────
    SLACK_WEBHOOK_URL: Optional[str] = None
    LOG_LEVEL: str = "INFO"

    # ── Storage ───────────────────────────────────────────────────────────────
    ARTIFACTS_DIR: str = "/app/output"

    # ── TikTok API (MODE_A only) ──────────────────────────────────────────────
    TIKTOK_CLIENT_KEY: Optional[str] = None
    TIKTOK_CLIENT_SECRET: Optional[str] = None
    TIKTOK_ACCESS_TOKEN: Optional[str] = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


# Singleton instance imported by all modules
settings = Settings()

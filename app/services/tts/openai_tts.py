"""OpenAI TTS service — generates child-friendly narration audio."""
from decimal import Decimal
from pathlib import Path
from typing import Optional

import openai

from app.settings import settings
from app.utils.logging import get_logger

log = get_logger(__name__)

# OpenAI TTS-1 cost: $0.015 per 1000 characters
TTS_COST_PER_CHAR = Decimal("0.000015")


def generate_speech(
    text: str,
    output_path: Optional[Path] = None,
    voice: Optional[str] = None,
    speed: float = 1.0,
) -> tuple[bytes, Decimal]:
    """Generate speech audio from text using OpenAI TTS.

    Returns (audio_bytes_mp3, cost_usd).
    Saves to output_path if provided.
    """
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    voice_id = voice or settings.VOICE_ID

    log.info("tts.generate", chars=len(text), voice=voice_id)

    response = client.audio.speech.create(
        model="tts-1",
        voice=voice_id,
        input=text,
        speed=max(0.25, min(4.0, speed)),  # clamp to valid range
    )

    audio_bytes = response.content
    cost = TTS_COST_PER_CHAR * len(text)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(audio_bytes)
        log.info("tts.saved", path=str(output_path), size=len(audio_bytes))

    return audio_bytes, cost

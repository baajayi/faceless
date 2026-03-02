"""DALL-E 3 image generation service."""
from decimal import Decimal
from pathlib import Path
from typing import Optional

import openai

from app.settings import settings
from app.utils.logging import get_logger

log = get_logger(__name__)

# DALL-E 3 cost: $0.040 per standard 1024x1792 image
DALLE3_COST_USD = Decimal("0.040")

# 1024x1792 is the closest DALL-E 3 size to 9:16 (1080x1920)
IMAGE_SIZE = "1024x1792"


def generate_image(
    prompt: str,
    style_prefix: str = "",
    output_path: Optional[Path] = None,
) -> tuple[bytes, Decimal]:
    """Generate a single image with DALL-E 3.

    Returns (image_bytes, cost_usd).
    Saves to output_path if provided.
    """
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

    full_prompt = f"{style_prefix}{prompt}" if style_prefix else prompt

    # Safety: always prepend "NO human faces" instruction
    if "NO human faces" not in full_prompt:
        full_prompt = f"NO human faces visible, age-appropriate for children: {full_prompt}"

    # Truncate to DALL-E's 4000 char limit
    full_prompt = full_prompt[:4000]

    log.info("dalle.generate", prompt_len=len(full_prompt))

    response = client.images.generate(
        model="dall-e-3",
        prompt=full_prompt,
        size=IMAGE_SIZE,
        quality="standard",
        n=1,
        response_format="b64_json",
    )

    import base64
    image_data = base64.b64decode(response.data[0].b64_json)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(image_data)
        log.info("dalle.saved", path=str(output_path), size=len(image_data))

    return image_data, DALLE3_COST_USD

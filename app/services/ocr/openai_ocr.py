"""OCR via OpenAI vision models."""
from __future__ import annotations

import base64

import openai

from app.settings import settings
from app.utils.logging import get_logger

log = get_logger(__name__)


def extract_text(image_bytes: bytes, model: str | None = None) -> str:
    """Extract visible text from an image using OpenAI vision."""
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    model = model or settings.IMAGE_TEXT_OCR_MODEL

    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:image/png;base64,{b64}"

    prompt = "Extract all visible text verbatim. Return plain text only. If none, return empty."

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        temperature=0.0,
    )

    text = response.choices[0].message.content or ""
    return text.strip()

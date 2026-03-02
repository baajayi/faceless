"""Image generation with text verification and fallback behavior."""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Optional

from app.services.image_gen.dalle_service import generate_image
from app.services.ocr.openai_ocr import extract_text
from app.settings import settings
from app.utils.logging import get_logger
from app.utils.text_match import is_text_match

log = get_logger(__name__)


def _text_prompt_suffix(text: str) -> str:
    return f' Include exact text: "{text}". Use clear block letters. No other words.'


def _no_text_suffix() -> str:
    return " No text anywhere in the image."


def _strip_text_instruction(prompt: str) -> str:
    prompt = re.sub(r'Include exact text:\\s*\".*?\"\\.?', "", prompt, flags=re.IGNORECASE)
    prompt = re.sub(r"No other words\\.?", "", prompt, flags=re.IGNORECASE)
    return prompt.strip()


def generate_image_with_text_guard(
    prompt: str,
    style_prefix: str,
    text_overlay: Optional[str],
    output_path,
    enforce: bool | None = None,
    max_attempts: Optional[int] = None,
    ocr_model: Optional[str] = None,
    fallback: Optional[str] = None,
) -> tuple[bytes, Decimal, dict]:
    """Generate image, verify text via OCR, and fallback to no-text if needed.

    Returns (image_bytes, total_cost, metadata).
    """
    enforce = settings.IMAGE_TEXT_ENFORCEMENT if enforce is None else enforce
    max_attempts = settings.IMAGE_TEXT_MAX_ATTEMPTS if max_attempts is None else max_attempts
    ocr_model = settings.IMAGE_TEXT_OCR_MODEL if ocr_model is None else ocr_model
    fallback = settings.IMAGE_TEXT_FALLBACK if fallback is None else fallback

    total_cost = Decimal("0")
    meta: dict = {"attempts": 0, "fallback_used": False, "ocr_text": None}

    prompt_with_text = prompt
    if text_overlay and "include exact text" not in prompt.lower():
        prompt_with_text = f"{prompt} {_text_prompt_suffix(text_overlay)}"

    if not enforce or not text_overlay:
        image_bytes, cost = generate_image(
            prompt=prompt_with_text,
            style_prefix=style_prefix,
            output_path=output_path,
        )
        total_cost += cost
        return image_bytes, total_cost, meta

    for attempt in range(1, max_attempts + 1):
        image_bytes, cost = generate_image(
            prompt=prompt_with_text,
            style_prefix=style_prefix,
            output_path=output_path,
        )
        total_cost += cost
        meta["attempts"] = attempt

        ocr_text = extract_text(image_bytes, model=ocr_model)
        meta["ocr_text"] = ocr_text
        if is_text_match(text_overlay, ocr_text):
            return image_bytes, total_cost, meta

        log.warning(
            "image_text.mismatch",
            attempt=attempt,
            expected=text_overlay,
            observed=ocr_text,
        )

    if fallback == "no_text_regen":
        meta["fallback_used"] = True
        no_text_prompt = _strip_text_instruction(prompt)
        no_text_prompt = f"{no_text_prompt} {_no_text_suffix()}".strip()
        image_bytes, cost = generate_image(
            prompt=no_text_prompt,
            style_prefix=style_prefix,
            output_path=output_path,
        )
        total_cost += cost
        return image_bytes, total_cost, meta

    return image_bytes, total_cost, meta

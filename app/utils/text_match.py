"""Text normalization and matching for OCR verification."""
from __future__ import annotations

import re


def normalize_for_match(text: str) -> str:
    t = text.lower().strip()
    t = re.sub(r"[^a-z0-9\\s]", "", t)
    t = re.sub(r"\\s+", " ", t)
    return t


def is_text_match(expected: str, observed: str) -> bool:
    return normalize_for_match(expected) == normalize_for_match(observed)

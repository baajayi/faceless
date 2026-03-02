"""Spellcheck utilities for on-screen text."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from spellchecker import SpellChecker

from app.settings import settings
from app.utils.logging import get_logger

log = get_logger(__name__)

WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")


def _load_allowlist(path: str) -> set[str]:
    p = Path(path)
    if not p.exists():
        return set()
    lines = [l.strip() for l in p.read_text(encoding="utf-8").splitlines()]
    return {l.lower() for l in lines if l and not l.startswith("#")}


def _should_skip_token(token: str) -> bool:
    if len(token) < 2:
        return True
    if token.isupper():
        return True
    if any(ch.isdigit() for ch in token):
        return True
    if token.startswith("#") or token.startswith("@"):
        return True
    if "http" in token.lower():
        return True
    return False


def _preserve_case(original: str, corrected: str) -> str:
    if original.istitle():
        return corrected.capitalize()
    if original.isupper():
        return original
    return corrected


def spellcheck_text(text: str, allowlist: Iterable[str]) -> tuple[str, list[tuple[str, str]]]:
    """Return corrected text and list of (from, to) replacements."""
    allow = {a.lower() for a in allowlist}
    spell = SpellChecker()

    corrections: list[tuple[str, str]] = []
    result = text
    offset = 0

    for match in WORD_RE.finditer(text):
        word = match.group(0)
        if _should_skip_token(word):
            continue
        if word.lower() in allow:
            continue
        corrected = spell.correction(word.lower()) or word.lower()
        if corrected != word.lower():
            fixed = _preserve_case(word, corrected)
            start, end = match.start() + offset, match.end() + offset
            result = result[:start] + fixed + result[end:]
            offset += len(fixed) - len(word)
            corrections.append((word, fixed))

    return result, corrections


def spellcheck_enabled() -> bool:
    return bool(settings.SPELLCHECK_ENABLED)


def apply_spellcheck(text: str) -> tuple[str, list[tuple[str, str]]]:
    allow = _load_allowlist(settings.SPELLCHECK_ALLOWLIST_PATH)
    corrected, corrections = spellcheck_text(text, allow)
    if corrections:
        log.info("spellcheck.corrected", original=text, corrected=corrected, changes=corrections)
    return corrected, corrections

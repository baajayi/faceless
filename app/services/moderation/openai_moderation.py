"""OpenAI Moderation API wrapper."""
from typing import Optional

import openai

from app.settings import settings
from app.utils.logging import get_logger

log = get_logger(__name__)


def moderate_text(text: str) -> dict:
    """Run OpenAI moderation on text.

    Returns dict with:
      - flagged: bool
      - risk_score: float (0–1, max of all category scores)
      - categories: dict of category -> score
      - raw: full API response
    """
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

    try:
        response = client.moderations.create(
            input=text,
            model="omni-moderation-latest",
        )
    except Exception as exc:
        log.error("moderation.api_error", error=str(exc))
        # Fail open with max risk on API error (conservative)
        return {
            "flagged": True,
            "risk_score": 1.0,
            "categories": {},
            "error": str(exc),
            "raw": None,
        }

    result = response.results[0]
    scores = result.category_scores.model_dump() if result.category_scores else {}
    risk_score = max(scores.values()) if scores else 0.0

    # Apply strictness adjustment
    threshold = _get_threshold()
    flagged = result.flagged or risk_score >= threshold

    log.info(
        "moderation.result",
        flagged=flagged,
        risk_score=round(risk_score, 4),
        threshold=threshold,
    )

    return {
        "flagged": flagged,
        "risk_score": round(risk_score, 4),
        "categories": {k: round(v, 4) for k, v in scores.items()},
        "raw": response.model_dump(),
    }


def _get_threshold() -> float:
    """Return risk score threshold based on SAFETY_STRICTNESS setting."""
    thresholds = {
        "low": 0.8,
        "med": 0.5,
        "high": 0.2,
    }
    return thresholds.get(settings.SAFETY_STRICTNESS, 0.2)

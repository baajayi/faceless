"""Agent A — Trend Research.

Fetches trending children's topics from Google Trends and YouTube,
merges/deduplicates, and stores candidates in the DB.
"""
from __future__ import annotations

import re
from datetime import date
from difflib import SequenceMatcher
from typing import Optional

from app.db.models import Run, RunStatus, Topic
from app.db.session import get_db
from app.services.trends.google_trends import fetch_google_trends
from app.services.trends.youtube_trends import fetch_youtube_trends
from app.utils.logging import get_logger

log = get_logger(__name__)


def run_trend_research(run_id: str, region: str = "US") -> list[str]:
    """Execute trend research for a run.

    Returns list of topic IDs saved to DB.
    """
    log.info("agent_a.start", run_id=run_id)

    with get_db() as db:
        run = db.get(Run, run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")
        run.status = RunStatus.TREND_RESEARCH
        db.flush()

    # 1. Fetch from both sources
    google_topics = fetch_google_trends(region=region)
    youtube_topics = fetch_youtube_trends(region=region)

    all_raw = google_topics + youtube_topics
    log.info("agent_a.raw_fetched", google=len(google_topics), youtube=len(youtube_topics))

    # 2. Deduplicate by title similarity
    deduplicated = _deduplicate(all_raw)
    log.info("agent_a.after_dedup", count=len(deduplicated))

    # 3. Score each candidate
    scored = [_score_topic(t) for t in deduplicated]

    # 4. Save to DB
    topic_ids = []
    with get_db() as db:
        for t in scored:
            topic = Topic(
                run_id=run_id,
                title=t["title"],
                category=t.get("category"),
                trend_score=t["trend_score"],
                kid_score=t["kid_score"],
                educational_score=t["educational_score"],
                novelty_score=t["novelty_score"],
                risk_score=0.0,  # will be set by Agent B
                composite_score=0.0,
                raw_sources=t.get("raw_sources", {}),
            )
            db.add(topic)
            db.flush()
            topic_ids.append(topic.id)

    log.info("agent_a.complete", run_id=run_id, topics_saved=len(topic_ids))
    return topic_ids


def _deduplicate(topics: list[dict]) -> list[dict]:
    """Remove near-duplicate titles (similarity > 0.7)."""
    unique: list[dict] = []
    for candidate in topics:
        title = candidate["title"].lower()
        is_dup = False
        for existing in unique:
            ratio = SequenceMatcher(None, title, existing["title"].lower()).ratio()
            if ratio > 0.7:
                # Keep the one with higher trend_score
                if candidate.get("trend_score", 0) > existing.get("trend_score", 0):
                    unique.remove(existing)
                    unique.append(candidate)
                is_dup = True
                break
        if not is_dup:
            unique.append(candidate)
    return unique


def _score_topic(topic: dict) -> dict:
    """Compute kid_score and educational_score via keyword heuristics."""
    title_lower = topic["title"].lower()

    # kid_score: child-relevant keywords
    kid_keywords = [
        "animal", "dinosaur", "space", "planet", "ocean", "color", "number",
        "letter", "shape", "baby", "kid", "children", "fun", "learn", "magic",
        "cartoon", "fairy", "cute", "tiny", "big", "little",
    ]
    kid_score = min(sum(1 for k in kid_keywords if k in title_lower) / 3.0, 1.0)

    # educational_score: learning keywords
    edu_keywords = [
        "fact", "why", "how", "what", "where", "who", "science", "math",
        "history", "learn", "education", "discover", "explore", "teach",
        "know", "understand", "explain",
    ]
    edu_score = min(sum(1 for k in edu_keywords if k in title_lower) / 3.0, 1.0)

    return {
        **topic,
        "kid_score": round(kid_score, 4),
        "educational_score": round(edu_score, 4),
        "novelty_score": 1.0,  # will be updated by Agent B using DB lookback
        "raw_sources": {
            "title": topic["title"],
            "source": topic.get("source", "unknown"),
            "trend_score": topic.get("trend_score", 0),
        },
    }

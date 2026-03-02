"""Agent B — Topic Selection + Safety Filter."""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import yaml

from app.db.models import Run, RunStatus, Topic
from app.db.session import get_db
from app.services.moderation.openai_moderation import moderate_text
from app.utils.logging import get_logger

log = get_logger(__name__)

_BLOCKLIST_PATH = Path(__file__).parent.parent.parent / "configs" / "safety_blocklist.yaml"
_CATEGORIES_PATH = Path(__file__).parent.parent.parent / "configs" / "topic_categories.yaml"

# Composite score weights
W_TREND = 0.25
W_KID = 0.30
W_EDU = 0.25
W_NOVELTY = 0.15
W_RISK = -0.50  # penalty


def run_topic_selection(run_id: str) -> str:
    """Select the best topic for this run.

    Returns selected topic_id.
    """
    log.info("agent_b.start", run_id=run_id)

    blocklist = _load_blocklist()
    categories_cfg = _load_categories()

    with get_db() as db:
        # Load all candidates for this run
        candidates = db.query(Topic).filter(Topic.run_id == run_id).all()
        if not candidates:
            raise ValueError(f"No topic candidates found for run {run_id}")

        # Load last 7 days' selected topics for diversity check
        run = db.get(Run, run_id)
        cutoff = run.run_date - timedelta(days=7)
        recent_selected = (
            db.query(Topic)
            .join(Run)
            .filter(
                Topic.is_selected == True,
                Run.run_date >= cutoff,
                Run.id != run_id,
            )
            .all()
        )
        recent_categories = [t.category for t in recent_selected if t.category]

        scores = []
        for topic in candidates:
            # Hard filter: blocklist
            if _is_blocked(topic.title, blocklist):
                log.info("agent_b.blocked", title=topic.title)
                continue

            # Safety moderation
            moderation = moderate_text(topic.title)
            risk_score = moderation["risk_score"]
            topic.risk_score = risk_score

            if moderation["flagged"] and risk_score > 0.7:
                log.info("agent_b.flagged", title=topic.title, risk=risk_score)
                continue

            # Novelty: penalize if same title appeared recently
            topic.novelty_score = _compute_novelty(topic.title, recent_selected)

            # Category detection
            category = _detect_category(topic.title, categories_cfg)
            topic.category = category

            # Diversity: reject if category appeared >= 2 times in last 7 days
            if category and recent_categories.count(category) >= 2:
                log.info("agent_b.diversity_reject", title=topic.title, category=category)
                continue

            # Composite score
            composite = (
                W_TREND * topic.trend_score
                + W_KID * topic.kid_score
                + W_EDU * topic.educational_score
                + W_NOVELTY * topic.novelty_score
                + W_RISK * topic.risk_score
            )
            topic.composite_score = round(composite, 6)
            topic.safety_report = moderation

            scores.append((topic, composite))
            db.flush()

        if not scores:
            raise ValueError("No safe topics found after filtering")

        # Select topic with highest composite score
        scores.sort(key=lambda x: x[1], reverse=True)
        selected_topic, best_score = scores[0]
        selected_topic.is_selected = True
        db.flush()

        # Update run status
        run.status = RunStatus.TOPIC_SELECTED
        db.flush()

        log.info(
            "agent_b.selected",
            run_id=run_id,
            topic=selected_topic.title,
            score=best_score,
            category=selected_topic.category,
        )
        return selected_topic.id


def _load_blocklist() -> dict:
    with open(_BLOCKLIST_PATH) as f:
        return yaml.safe_load(f)


def _load_categories() -> dict:
    with open(_CATEGORIES_PATH) as f:
        return yaml.safe_load(f)


def _is_blocked(title: str, blocklist: dict) -> bool:
    """Check if a title matches any blocked keyword."""
    title_lower = title.lower()
    blocked_keywords = blocklist.get("blocked_keywords", [])
    blocked_brands = blocklist.get("blocked_brands", [])
    all_blocked = [k.lower() for k in blocked_keywords + blocked_brands]
    return any(kw in title_lower for kw in all_blocked)


def _compute_novelty(title: str, recent_topics: list[Topic]) -> float:
    """1.0 if title hasn't appeared in last 7 days, 0.0 if exact match."""
    title_lower = title.lower()
    recent_titles = [t.title.lower() for t in recent_topics]
    if title_lower in recent_titles:
        return 0.0
    # Partial match penalty
    for rt in recent_titles:
        if title_lower in rt or rt in title_lower:
            return 0.5
    return 1.0


def _detect_category(title: str, categories_cfg: dict) -> Optional[str]:
    """Detect topic category from title using keyword matching."""
    title_lower = title.lower()
    best_cat = None
    best_count = 0

    for cat_key, cat_data in categories_cfg.get("categories", {}).items():
        keywords = cat_data.get("keywords", [])
        count = sum(1 for kw in keywords if kw.lower() in title_lower)
        if count > best_count:
            best_count = count
            best_cat = cat_key

    return best_cat

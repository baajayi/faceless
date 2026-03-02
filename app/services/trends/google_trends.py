"""Google Trends wrapper using pytrends."""
import time
from typing import Optional

from app.utils.logging import get_logger

log = get_logger(__name__)

# Child-safe seed keywords — batched 5 at a time (pytrends limit)
SEED_KEYWORDS = [
    ["animals for kids", "space facts kids", "dinosaur facts", "ocean animals", "rainforest animals"],
    ["science experiments kids", "math tricks children", "history facts kids", "geography kids", "fun facts children"],
]


def fetch_google_trends(region: str = "US") -> list[dict]:
    """Fetch trending topics related to children's content.

    Returns list of dicts: {title, trend_score, source}
    """
    results: list[dict] = []

    try:
        from pytrends.request import TrendReq
    except ImportError:
        log.warning("pytrends not installed; skipping Google Trends")
        return _fallback_topics()

    try:
        pt = TrendReq(hl="en-US", tz=0, timeout=(10, 25))

        for batch in SEED_KEYWORDS:
            try:
                pt.build_payload(batch, cat=0, timeframe="now 7-d", geo=region)
                related = pt.related_queries()

                for keyword in batch:
                    data = related.get(keyword, {})
                    top_df = data.get("top")
                    if top_df is not None and not top_df.empty:
                        for _, row in top_df.iterrows():
                            score = min(float(row.get("value", 0)) / 100.0, 1.0)
                            results.append({
                                "title": str(row["query"]).title(),
                                "trend_score": score,
                                "source": "google_trends",
                                "seed_keyword": keyword,
                            })

                # Respect pytrends rate limit
                time.sleep(1.5)

            except Exception as exc:
                log.warning("google_trends.batch_error", batch=batch, error=str(exc))
                time.sleep(2)

    except Exception as exc:
        log.error("google_trends.error", error=str(exc))
        return _fallback_topics()

    if not results:
        log.warning("google_trends.empty_result", region=region)
        return _fallback_topics()

    log.info("google_trends.fetched", count=len(results))
    return results


def _fallback_topics() -> list[dict]:
    """Static fallback when Google Trends is unavailable."""
    return [
        {"title": "How Do Butterflies Fly", "trend_score": 0.8, "source": "fallback"},
        {"title": "Why Is The Sky Blue", "trend_score": 0.75, "source": "fallback"},
        {"title": "How Do Volcanoes Erupt", "trend_score": 0.7, "source": "fallback"},
        {"title": "What Do Sharks Eat", "trend_score": 0.65, "source": "fallback"},
        {"title": "How Do Bees Make Honey", "trend_score": 0.6, "source": "fallback"},
        {"title": "Why Do Leaves Change Color", "trend_score": 0.55, "source": "fallback"},
        {"title": "How Big Is The Universe", "trend_score": 0.5, "source": "fallback"},
        {"title": "What Is Inside A Black Hole", "trend_score": 0.45, "source": "fallback"},
    ]

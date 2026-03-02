"""YouTube Data API v3 wrapper for trending children's content."""
import math
from typing import Optional

from app.settings import settings
from app.utils.logging import get_logger

log = get_logger(__name__)

# YouTube category ID 25 = Education; also check kids content category
EDUCATION_CATEGORY_ID = "25"
KIDS_CATEGORY_ID = "20"  # Gaming — often has kid-safe content


def fetch_youtube_trends(region: str = "US", max_results: int = 25) -> list[dict]:
    """Fetch trending educational YouTube videos and normalize to topic candidates.

    Returns list of dicts: {title, trend_score, source, video_id, view_count}
    """
    if not settings.YOUTUBE_API_KEY:
        log.warning("youtube_trends.no_api_key")
        return []

    try:
        from googleapiclient.discovery import build
        youtube = build("youtube", "v3", developerKey=settings.YOUTUBE_API_KEY)
    except Exception as exc:
        log.error("youtube_trends.build_error", error=str(exc))
        return []

    results: list[dict] = []
    view_counts: list[int] = []

    try:
        # Fetch most popular education videos
        request = youtube.videos().list(
            part="snippet,statistics",
            chart="mostPopular",
            regionCode=region,
            videoCategoryId=EDUCATION_CATEGORY_ID,
            safeSearch="strict",
            maxResults=max_results,
            videoDuration="short",  # prefer short-form content
        )
        response = request.execute()

        raw_items = []
        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})

            title = snippet.get("title", "")
            views = int(stats.get("viewCount", 0))
            video_id = item.get("id", "")

            # Filter: must be safe for kids / education
            if not _is_kid_safe_title(title):
                continue

            raw_items.append({
                "title": _clean_title(title),
                "view_count": views,
                "video_id": video_id,
                "source": "youtube_trends",
            })
            view_counts.append(views)

        # Log-normalize view counts to [0, 1]
        if view_counts:
            log_max = math.log1p(max(view_counts)) if max(view_counts) > 0 else 1.0
            for item_data in raw_items:
                normalized = math.log1p(item_data["view_count"]) / log_max if log_max else 0.0
                item_data["trend_score"] = round(normalized, 4)
                results.append(item_data)

    except Exception as exc:
        log.error("youtube_trends.fetch_error", error=str(exc))

    log.info("youtube_trends.fetched", count=len(results))
    return results


def _clean_title(title: str) -> str:
    """Strip common YouTube title noise."""
    noise = [
        "| Kids Learning", "for Kids", "for Children", "- Educational",
        "| Educational", "(Official)", "HD", "4K",
    ]
    for n in noise:
        title = title.replace(n, "").strip()
    return title.strip(" -|")


def _is_kid_safe_title(title: str) -> bool:
    """Basic heuristic — reject obviously non-kid-safe titles."""
    bad_words = ["horror", "scary", "violence", "war", "killing", "murder", "adult", "18+"]
    title_lower = title.lower()
    return not any(w in title_lower for w in bad_words)

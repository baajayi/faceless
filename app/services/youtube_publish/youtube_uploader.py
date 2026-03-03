"""YouTube upload service using OAuth refresh token."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import httpx

from app.settings import settings
from app.utils.logging import get_logger

log = get_logger(__name__)


def _get_access_token() -> str:
    if not settings.YOUTUBE_CLIENT_ID or not settings.YOUTUBE_CLIENT_SECRET:
        raise ValueError("YouTube client credentials missing.")
    if not settings.YOUTUBE_REFRESH_TOKEN:
        raise ValueError("YOUTUBE_REFRESH_TOKEN missing.")

    resp = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": settings.YOUTUBE_CLIENT_ID,
            "client_secret": settings.YOUTUBE_CLIENT_SECRET,
            "refresh_token": settings.YOUTUBE_REFRESH_TOKEN,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _resumable_upload_init(access_token: str, metadata: dict) -> str:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Type": "video/*",
    }
    params = {"uploadType": "resumable", "part": "snippet,status"}
    resp = httpx.post(
        "https://www.googleapis.com/upload/youtube/v3/videos",
        params=params,
        headers=headers,
        content=json.dumps(metadata),
        timeout=30,
    )
    resp.raise_for_status()
    upload_url = resp.headers.get("Location")
    if not upload_url:
        raise RuntimeError("Missing resumable upload URL from YouTube.")
    return upload_url


def _resumable_upload_video(upload_url: str, video_path: Path) -> dict:
    with video_path.open("rb") as f:
        resp = httpx.put(
            upload_url,
            content=f,
            headers={"Content-Type": "video/*"},
            timeout=None,
        )
    resp.raise_for_status()
    return resp.json()


def _upload_thumbnail(access_token: str, video_id: str, thumbnail_path: Path) -> None:
    if not thumbnail_path.exists():
        return
    params = {"videoId": video_id, "uploadType": "media"}
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "image/jpeg"}
    with thumbnail_path.open("rb") as f:
        resp = httpx.post(
            "https://www.googleapis.com/upload/youtube/v3/thumbnails/set",
            params=params,
            headers=headers,
            content=f,
            timeout=30,
        )
    resp.raise_for_status()


def upload_video(
    video_path: Path,
    title: str,
    description: str,
    tags: Optional[list[str]] = None,
    privacy_status: str | None = None,
    thumbnail_path: Optional[Path] = None,
) -> dict:
    """Upload video to YouTube and optionally set thumbnail."""
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    access_token = _get_access_token()
    privacy_status = privacy_status or settings.YOUTUBE_PRIVACY_STATUS
    metadata = {
        "snippet": {
            "title": title[:95],
            "description": description[:5000],
            "tags": tags or [],
        },
        "status": {"privacyStatus": privacy_status},
    }

    upload_url = _resumable_upload_init(access_token, metadata)
    result = _resumable_upload_video(upload_url, video_path)
    video_id = result.get("id")
    log.info("youtube.uploaded", video_id=video_id)

    if settings.YOUTUBE_UPLOAD_THUMBNAIL and thumbnail_path and video_id:
        _upload_thumbnail(access_token, video_id, thumbnail_path)
        log.info("youtube.thumbnail_set", video_id=video_id)

    return result

"""Agent G — Metadata Generator.

Generates caption and hashtags for the video.
"""
from __future__ import annotations

import json

import openai

from app.db.models import PublishJob, PublishStatus, Run, Script, Video
from app.db.session import get_db
from app.settings import settings
from app.utils.cost_tracker import CostTracker
from app.utils.logging import get_logger

log = get_logger(__name__)

METADATA_SYSTEM = """You are a social media manager for a children's educational TikTok channel.
Generate:
1. A caption (≤150 chars, fun, 1-2 emojis maximum, no spam)
2. 3-6 kid-safe hashtags (no #fyp spam)

Output ONLY this JSON:
{
  "caption": "...",
  "hashtags": ["hashtag1", "hashtag2", "hashtag3"]
}

Rules:
- Caption must be family-friendly and educational
- Hashtags should include 2-3 broad (#kidslearning, #kidseducation) and 1-2 specific ones
- No hashtags promoting dangerous content or brands
- Hashtags without # prefix in the array"""


def run_metadata_agent(run_id: str) -> str:
    """Generate caption and hashtags, create publish job record.

    Returns publish_job_id.
    """
    log.info("agent_g.start", run_id=run_id)

    with get_db() as db:
        run = db.get(Run, run_id)
        run_date = str(run.run_date)

        script = (
            db.query(Script)
            .filter(Script.run_id == run_id)
            .order_by(Script.revision.desc())
            .first()
        )
        video = db.query(Video).filter(Video.run_id == run_id).first()

        if not script:
            raise ValueError(f"No script for run {run_id}")

        title = script.raw_json.get("title", "Educational Video")
        narration = script.raw_json.get("narration", [])
        topic = script.raw_json.get("topic", "")

    cost_tracker = CostTracker(run_id)
    caption, hashtags = _generate_metadata(
        title=title,
        topic=topic,
        narration_preview=" ".join(n["text"] for n in narration[:3]),
        cost_tracker=cost_tracker,
    )

    # Build full metadata dict
    metadata = {
        "run_id": run_id,
        "run_date": run_date,
        "title": title,
        "topic": topic,
        "caption": caption,
        "hashtags": hashtags,
        "video_path": video.file_path if video else None,
        "thumbnail_path": video.thumbnail_path if video else None,
        "duration_s": video.duration_s if video else None,
    }

    with get_db() as db:
        pub_job = PublishJob(
            run_id=run_id,
            mode=settings.PUBLISH_MODE,
            status=PublishStatus.PENDING,
            caption=caption,
            hashtags=hashtags,
            metadata_json=metadata,
        )
        db.add(pub_job)
        db.flush()
        cost_tracker.flush_to_db(db, run_id)
        pub_job_id = pub_job.id

    log.info("agent_g.complete", run_id=run_id, caption_len=len(caption), hashtags=len(hashtags))
    return pub_job_id


def _generate_metadata(
    title: str,
    topic: str,
    narration_preview: str,
    cost_tracker: CostTracker,
) -> tuple[str, list[str]]:
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

    user_msg = f"Title: {title}\nTopic: {topic}\nScript preview: {narration_preview[:300]}"

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": METADATA_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
    )

    cost_tracker.add_gpt4o(response.usage.prompt_tokens, response.usage.completion_tokens)

    data = json.loads(response.choices[0].message.content)
    caption = data.get("caption", title)[:150]
    hashtags = [h.lstrip("#") for h in data.get("hashtags", ["kidslearning", "educational"])]

    return caption, hashtags

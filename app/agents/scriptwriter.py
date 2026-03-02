"""Agent C — Scriptwriter.

Generates a validated script JSON via GPT-4o with Pydantic validation.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal, Optional

import openai
from pydantic import BaseModel, Field, field_validator, model_validator

from app.db.models import Run, RunStatus, Script, Topic
from app.db.session import get_db
from app.settings import settings
from app.utils.cost_tracker import CostTracker
from app.utils.logging import get_logger
from app.utils.spellcheck import apply_spellcheck, spellcheck_enabled

log = get_logger(__name__)

# ── Pydantic Script Schema ────────────────────────────────────────────────────

class NarrationSegment(BaseModel):
    t: float = Field(ge=0.0, description="Start time in seconds")
    text: str = Field(min_length=1, max_length=200)

class OnScreenText(BaseModel):
    t: float = Field(ge=0.0)
    text: str = Field(min_length=1, max_length=100)

class SoundEffect(BaseModel):
    t: float = Field(ge=0.0)
    type: Literal["pop", "ding", "whoosh"]

class StyleLock(BaseModel):
    palette: str
    character_style: str
    background_style: str

class ScriptSchema(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    age_band: str = Field(default="4-10")
    topic: str = Field(min_length=3)
    narration: list[NarrationSegment] = Field(min_length=2)
    on_screen_text: list[OnScreenText] = Field(default_factory=list)
    sound_effects: list[SoundEffect] = Field(default_factory=list)
    visual_style: Literal["cartoon", "paper-cut", "3d-toy", "whiteboard"] = "cartoon"
    style_lock: StyleLock
    cta: str = Field(max_length=150)
    pronunciation_hints: dict[str, str] = Field(default_factory=dict)
    estimated_duration_s: float = Field(default=30.0, ge=15.0, le=60.0)

    @field_validator("narration")
    @classmethod
    def sentences_short_enough(cls, v: list[NarrationSegment]) -> list[NarrationSegment]:
        for seg in v:
            words = seg.text.split()
            if len(words) > 15:
                raise ValueError(
                    f"Narration segment has {len(words)} words (max 15): '{seg.text[:60]}...'"
                )
        return v

    @model_validator(mode="after")
    def duration_matches_narration(self) -> "ScriptSchema":
        if self.narration:
            last = max(s.t for s in self.narration)
            if abs(self.estimated_duration_s - last) > 5.0:
                # Auto-correct rather than fail
                self.estimated_duration_s = last + 3.0
        return self


# ── Agent Logic ───────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a children's educational video scriptwriter.
Rules:
- Target age: {age_band}
- Max 12 words per narration sentence
- Tone: warm, playful, encouraging
- No human faces in visuals (use animals, objects, cartoons)
- Script must be 25-40 seconds total
- Use "Can you guess...?" style engagement
- Visual style: {visual_style}
- Always include a style_lock object for visual consistency

Output ONLY valid JSON matching this schema exactly:
{{
  "title": "...",
  "age_band": "{age_band}",
  "topic": "...",
  "narration": [{{"t": 0.0, "text": "..."}}],
  "on_screen_text": [{{"t": 0.0, "text": "..."}}],
  "sound_effects": [{{"t": 0.0, "type": "pop|ding|whoosh"}}],
  "visual_style": "{visual_style}",
  "style_lock": {{
    "palette": "describe colors",
    "character_style": "describe character style, NO human faces",
    "background_style": "describe backgrounds"
  }},
  "cta": "Call to action text (max 150 chars)",
  "pronunciation_hints": {{}},
  "estimated_duration_s": 30.0
}}"""


def run_scriptwriter(run_id: str, revision_feedback: str = "") -> str:
    """Generate and validate script for the selected topic.

    Returns script_id.
    """
    log.info("agent_c.start", run_id=run_id)

    with get_db() as db:
        run = db.get(Run, run_id)
        topic = (
            db.query(Topic).filter(Topic.run_id == run_id, Topic.is_selected == True).first()
        )
        if not topic:
            raise ValueError(f"No selected topic for run {run_id}")

        run_date_str = str(run.run_date)

    cost_tracker = CostTracker(run_id)
    script_data, prompt_tokens, completion_tokens = _generate_script(
        topic_title=topic.title,
        age_band=settings.AGE_BAND,
        visual_style=settings.VISUAL_STYLE,
        run_date_str=run_date_str,
        revision_feedback=revision_feedback,
        cost_tracker=cost_tracker,
    )

    with get_db() as db:
        run = db.get(Run, run_id)
        script = Script(
            run_id=run_id,
            topic_id=topic.id,
            raw_json=script_data,
            estimated_duration_s=script_data.get("estimated_duration_s", 30.0),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            revision=1 if revision_feedback else 0,
        )
        db.add(script)
        run.status = RunStatus.SCRIPTED
        db.flush()
        cost_tracker.flush_to_db(db, run_id)

        log.info("agent_c.complete", run_id=run_id, script_id=script.id)
        return script.id


def _generate_script(
    topic_title: str,
    age_band: str,
    visual_style: str,
    run_date_str: str,
    revision_feedback: str = "",
    cost_tracker: Optional[CostTracker] = None,
    max_rounds: int = 2,
) -> tuple[dict, int, int]:
    """Call GPT-4o to generate a validated script. Retries on validation failure."""
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    seed = int(hashlib.md5(run_date_str.encode()).hexdigest(), 16) % (2**31)

    system = SYSTEM_PROMPT.format(age_band=age_band, visual_style=visual_style)
    user_msg = f"Create an educational children's video script about: {topic_title}"
    if revision_feedback:
        user_msg += f"\n\nREVISION NEEDED: {revision_feedback}"

    total_prompt_tokens = 0
    total_completion_tokens = 0
    last_error = ""

    for attempt in range(max_rounds):
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ]
        if last_error and attempt > 0:
            messages.append({
                "role": "user",
                "content": f"Fix these validation errors: {last_error}",
            })

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.8,
            seed=seed,
        )

        total_prompt_tokens += response.usage.prompt_tokens
        total_completion_tokens += response.usage.completion_tokens

        if cost_tracker:
            cost_tracker.add_gpt4o(response.usage.prompt_tokens, response.usage.completion_tokens)

        raw_text = response.choices[0].message.content
        try:
            raw_data = json.loads(raw_text)
            validated = ScriptSchema.model_validate(raw_data)
            data = validated.model_dump()
            if spellcheck_enabled():
                title, _ = apply_spellcheck(data.get("title", ""))
                data["title"] = title
                for item in data.get("on_screen_text", []):
                    if "text" in item:
                        item["text"], _ = apply_spellcheck(item["text"])
            return data, total_prompt_tokens, total_completion_tokens
        except Exception as exc:
            last_error = str(exc)
            log.warning("agent_c.validation_failed", attempt=attempt, error=last_error)

    raise ValueError(f"Script validation failed after {max_rounds} attempts: {last_error}")

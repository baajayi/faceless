"""Agent D — Storyboard / Shot List Generator."""
from __future__ import annotations

import json
from typing import Any, Literal, Optional

import openai
from pydantic import BaseModel, Field, field_validator, model_validator

from app.db.models import Run, RunStatus, Script, Storyboard
from app.db.session import get_db
from app.settings import settings
from app.utils.cost_tracker import CostTracker
from app.utils.logging import get_logger
from app.utils.spellcheck import apply_spellcheck, spellcheck_enabled

log = get_logger(__name__)


# ── Pydantic Storyboard Schema ─────────────────────────────────────────────

class CameraMotion(BaseModel):
    type: Literal["zoom_in", "zoom_out", "pan_left", "pan_right", "static"]
    magnitude: float = Field(default=0.05, ge=0.0, le=0.3)

class Shot(BaseModel):
    index: int = Field(ge=0)
    duration_s: float = Field(ge=1.0, le=15.0)
    narration_indices: list[int] = Field(default_factory=list)
    background: str = Field(min_length=5)
    foreground_elements: list[str] = Field(default_factory=list)
    camera_motion: CameraMotion
    text_overlay: Optional[str] = None
    dalle_prompt: str = Field(
        min_length=20,
        description="Complete, self-contained DALL-E 3 prompt for this shot",
    )
    sfx_type: Optional[Literal["pop", "ding", "whoosh"]] = None

    @field_validator("sfx_type", mode="before")
    @classmethod
    def coerce_none_string(cls, v):
        if isinstance(v, str) and v.lower() in ("none", "null", ""):
            return None
        return v

class StyleLock(BaseModel):
    palette: str
    character_style: str
    background_style: str

class StoryboardSchema(BaseModel):
    topic: str
    visual_style: str
    style_lock: StyleLock
    shots: list[Shot] = Field(min_length=3, max_length=10)
    total_duration_s: float

    @model_validator(mode="after")
    def validate_total_duration(self) -> "StoryboardSchema":
        computed = sum(s.duration_s for s in self.shots)
        if abs(computed - self.total_duration_s) > 3.0:
            self.total_duration_s = computed
        return self


# ── Agent Logic ───────────────────────────────────────────────────────────

STORYBOARD_SYSTEM = """You are a children's educational video director.
Given a script JSON, create a shot list (storyboard) with DALL-E 3 image prompts.

Rules:
- Every shot must use FACELESS visuals: animals, objects, cartoons, text graphics, NO human faces
- Each shot's dalle_prompt must be complete and self-contained (include style info)
- All shots must use the same style_lock (consistent visual identity)
- Camera motion should be simple: zoom_in, zoom_out, pan_left, pan_right, or static
- Total duration must match script's estimated_duration_s within ±3 seconds
- If text_overlay is present, dalle_prompt MUST include: Include exact text: "..."
- If text_overlay is present, NO other words should appear anywhere in the image
- Keep text_overlay short (≤ 4 words)

Output ONLY valid JSON matching this schema:
{
  "topic": "...",
  "visual_style": "...",
  "style_lock": {"palette": "...", "character_style": "...", "background_style": "..."},
  "shots": [
    {
      "index": 0,
      "duration_s": 4.0,
      "narration_indices": [0, 1],
      "background": "describe background scene",
      "foreground_elements": ["element1", "element2"],
      "camera_motion": {"type": "zoom_in", "magnitude": 0.05},
      "text_overlay": "optional text",
      "dalle_prompt": "Complete DALL-E 3 prompt, NO human faces...",
      "sfx_type": "pop"
    }
  ],
  "total_duration_s": 32.0
}"""


def run_storyboard(run_id: str) -> str:
    """Generate storyboard from the current run's script.

    Returns storyboard_id.
    """
    log.info("agent_d.start", run_id=run_id)

    with get_db() as db:
        run = db.get(Run, run_id)
        script = (
            db.query(Script)
            .filter(Script.run_id == run_id)
            .order_by(Script.revision.desc())
            .first()
        )
        if not script:
            raise ValueError(f"No script found for run {run_id}")
        script_data = script.raw_json
        script_id = script.id

    cost_tracker = CostTracker(run_id)
    board_data, prompt_tokens, completion_tokens = _generate_storyboard(
        script_data=script_data,
        cost_tracker=cost_tracker,
    )

    with get_db() as db:
        run = db.get(Run, run_id)
        storyboard = Storyboard(
            run_id=run_id,
            script_id=script_id,
            raw_json=board_data,
            shot_count=len(board_data.get("shots", [])),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        db.add(storyboard)
        run.status = RunStatus.STORYBOARDED
        db.flush()
        cost_tracker.flush_to_db(db, run_id)

        log.info("agent_d.complete", run_id=run_id, shots=storyboard.shot_count)
        return storyboard.id


def _generate_storyboard(
    script_data: dict,
    cost_tracker: Optional[CostTracker] = None,
) -> tuple[dict, int, int]:
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": STORYBOARD_SYSTEM},
            {"role": "user", "content": f"Create storyboard for this script:\n{json.dumps(script_data, indent=2)}"},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
    )

    if cost_tracker:
        cost_tracker.add_gpt4o(response.usage.prompt_tokens, response.usage.completion_tokens)

    raw_data = json.loads(response.choices[0].message.content)
    validated = StoryboardSchema.model_validate(raw_data)
    data = validated.model_dump()
    for shot in data.get("shots", []):
        if shot.get("text_overlay"):
            if spellcheck_enabled():
                shot["text_overlay"], _ = apply_spellcheck(shot["text_overlay"])
            if "include exact text" not in shot.get("dalle_prompt", "").lower():
                shot["dalle_prompt"] = (
                    f'{shot["dalle_prompt"]} Include exact text: "{shot["text_overlay"]}". '
                    "Use clear block letters. No other words."
                )

    return (
        data,
        response.usage.prompt_tokens,
        response.usage.completion_tokens,
    )

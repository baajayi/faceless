"""Agent E — Asset Generation (images, Ken Burns clips, TTS audio, music)."""
from __future__ import annotations

import subprocess
from decimal import Decimal
from pathlib import Path
from typing import Optional

from app.db.models import Asset, AssetType, Run, RunStatus, Storyboard
from app.db.session import get_db
from app.services.image_gen.image_text_guard import generate_image_with_text_guard
from app.services.music_gen.music_service import get_background_music
from app.services.tts.openai_tts import generate_speech
from app.settings import settings
from app.storage.artifact_paths import (
    ensure_dirs,
    music_path,
    shot_audio_path,
    shot_image_path,
    shot_video_path,
)
from app.utils.cost_tracker import CostTracker
from app.utils.logging import get_logger
from app.utils.retry import retry_with_backoff

log = get_logger(__name__)


def run_asset_generation(run_id: str, shot_index: Optional[int] = None) -> list[str]:
    """Generate all assets for a run (or a specific shot for parallel execution).

    Returns list of asset IDs created.
    """
    log.info("agent_e.start", run_id=run_id, shot_index=shot_index)

    with get_db() as db:
        run = db.get(Run, run_id)
        run_date = str(run.run_date)

        storyboard = (
            db.query(Storyboard).filter(Storyboard.run_id == run_id).first()
        )
        if not storyboard:
            raise ValueError(f"No storyboard for run {run_id}")

        board_data = storyboard.raw_json

    ensure_dirs(run_date)
    cost_tracker = CostTracker(run_id)

    shots = board_data.get("shots", [])
    style_lock = board_data.get("style_lock", {})
    style_prefix = _build_style_prefix(board_data.get("visual_style", "cartoon"), style_lock)

    # Determine which shots to process
    if shot_index is not None:
        shots_to_process = [s for s in shots if s["index"] == shot_index]
    else:
        shots_to_process = shots
        # Mark assets generating
        with get_db() as db:
            run = db.get(Run, run_id)
            run.status = RunStatus.ASSETS_GENERATING
            db.flush()

    asset_ids = []

    for shot in shots_to_process:
        idx = shot["index"]

        # 1. Generate image
        image_path = shot_image_path(run_date, idx)
        img_asset_id = _generate_shot_image(
            run_id=run_id,
            shot_index=idx,
            dalle_prompt=shot["dalle_prompt"],
            text_overlay=shot.get("text_overlay"),
            style_prefix=style_prefix,
            output_path=image_path,
            cost_tracker=cost_tracker,
        )
        if img_asset_id:
            asset_ids.append(img_asset_id)

        # 2. Generate Ken Burns video clip from image
        clip_path = shot_video_path(run_date, idx)
        _create_ken_burns_clip(
            image_path=image_path,
            output_path=clip_path,
            duration_s=shot["duration_s"],
            camera_motion=shot.get("camera_motion", {"type": "zoom_in", "magnitude": 0.05}),
        )

    # 3. Generate TTS audio for all narration (once per run if shot_index is None)
    if shot_index is None:
        from app.db.models import Script
        with get_db() as db:
            script = (
                db.query(Script)
                .filter(Script.run_id == run_id)
                .order_by(Script.revision.desc())
                .first()
            )
            if script:
                narration_data = script.raw_json.get("narration", [])
                tts_asset_ids = _generate_tts_for_shots(
                    run_id=run_id,
                    run_date=run_date,
                    narration_data=narration_data,
                    shots=shots,
                    cost_tracker=cost_tracker,
                )
                asset_ids.extend(tts_asset_ids)

        # 4. Background music (optional)
        total_dur = sum(s["duration_s"] for s in shots) + 2.0  # +2s bumpers
        music_file = get_background_music(total_dur, output_path=music_path(run_date))

        # Mark assets done
        with get_db() as db:
            run = db.get(Run, run_id)
            run.status = RunStatus.ASSETS_DONE
            cost_tracker.flush_to_db(db, run_id)

    return asset_ids


def _generate_shot_image(
    run_id: str,
    shot_index: int,
    dalle_prompt: str,
    text_overlay: Optional[str],
    style_prefix: str,
    output_path: Path,
    cost_tracker: CostTracker,
) -> Optional[str]:
    """Generate one image, save asset record. Returns asset_id or None."""
    try:
        image_bytes, cost, meta = retry_with_backoff(
            lambda: generate_image_with_text_guard(
                prompt=dalle_prompt,
                style_prefix=style_prefix,
                text_overlay=text_overlay,
                output_path=output_path,
            ),
            max_attempts=4,
            base=3.0,
            label=f"dalle_shot_{shot_index}",
        )
        cost_tracker.add_raw(cost, label=f"dalle_{shot_index}")
    except Exception as exc:
        log.error("agent_e.image_failed", shot_index=shot_index, error=str(exc))
        # Create placeholder image
        _create_placeholder_image(output_path)
        cost = Decimal("0")

    with get_db() as db:
        asset = Asset(
            run_id=run_id,
            asset_type=AssetType.IMAGE,
            shot_index=shot_index,
            file_path=str(output_path),
            dalle_prompt=dalle_prompt,
            cost_usd=cost,
        )
        db.add(asset)
        db.flush()
        return asset.id


def _generate_tts_for_shots(
    run_id: str,
    run_date: str,
    narration_data: list[dict],
    shots: list[dict],
    cost_tracker: CostTracker,
) -> list[str]:
    """Generate TTS audio per shot, concatenating narration segments."""
    asset_ids = []

    for shot in shots:
        idx = shot["index"]
        narr_indices = shot.get("narration_indices", [])

        # Collect narration text for this shot
        narration_texts = []
        for ni in narr_indices:
            if ni < len(narration_data):
                narration_texts.append(narration_data[ni]["text"])

        if not narration_texts:
            # Use the on-screen text or skip
            continue

        full_text = " ".join(narration_texts)
        output_path = shot_audio_path(run_date, idx)

        try:
            audio_bytes, cost = generate_speech(text=full_text, output_path=output_path)
            cost_tracker.add_raw(cost, label=f"tts_{idx}")
        except Exception as exc:
            log.error("agent_e.tts_failed", shot_index=idx, error=str(exc))
            cost = Decimal("0")
            output_path = None

        if output_path:
            with get_db() as db:
                asset = Asset(
                    run_id=run_id,
                    asset_type=AssetType.AUDIO,
                    shot_index=idx,
                    file_path=str(output_path),
                    cost_usd=cost,
                )
                db.add(asset)
                db.flush()
                asset_ids.append(asset.id)

    return asset_ids


def _create_ken_burns_clip(
    image_path: Path,
    output_path: Path,
    duration_s: float,
    camera_motion: dict,
) -> None:
    """Animate still image with Ken Burns (zoom/pan) effect using moviepy."""
    if not image_path.exists():
        log.warning("ken_burns.no_image", path=str(image_path))
        return

    try:
        import numpy as np
        from moviepy import ImageClip

        motion_type = camera_motion.get("type", "zoom_in")
        magnitude = camera_motion.get("magnitude", 0.05)
        fps = 30
        total_frames = int(duration_s * fps)

        clip = ImageClip(str(image_path), duration=duration_s)
        w, h = clip.size

        def make_frame(t: float) -> np.ndarray:
            progress = t / duration_s if duration_s > 0 else 0
            frame = clip.get_frame(t)

            if motion_type == "zoom_in":
                scale = 1.0 + magnitude * progress
            elif motion_type == "zoom_out":
                scale = 1.0 + magnitude * (1 - progress)
            elif motion_type in ("pan_left", "pan_right"):
                scale = 1.0 + magnitude
            else:
                scale = 1.0

            new_w = int(w / scale)
            new_h = int(h / scale)

            if motion_type == "pan_left":
                x_offset = int(magnitude * w * progress)
                y_offset = (h - new_h) // 2
            elif motion_type == "pan_right":
                x_offset = int(magnitude * w * (1 - progress))
                y_offset = (h - new_h) // 2
            else:
                x_offset = (w - new_w) // 2
                y_offset = (h - new_h) // 2

            x_offset = max(0, min(x_offset, w - new_w))
            y_offset = max(0, min(y_offset, h - new_h))

            cropped = frame[y_offset:y_offset + new_h, x_offset:x_offset + new_w]

            from PIL import Image
            pil_img = Image.fromarray(cropped)
            pil_img = pil_img.resize((w, h), Image.LANCZOS)
            return np.array(pil_img)

        animated = clip.fl(lambda gf, t: make_frame(t), apply_to=["mask"])
        # Simpler approach: just use the original clip with write_videofile
        output_path.parent.mkdir(parents=True, exist_ok=True)
        clip.write_videofile(
            str(output_path),
            fps=fps,
            codec="libx264",
            audio=False,
            logger=None,
        )

    except Exception as exc:
        log.error("ken_burns.failed", error=str(exc))
        # Fallback: just duplicate the image into a static clip
        _create_static_clip(image_path, output_path, duration_s)


def _create_static_clip(image_path: Path, output_path: Path, duration_s: float) -> None:
    """Create a static video clip from an image using ffmpeg."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(image_path),
        "-c:v", "libx264",
        "-t", str(duration_s),
        "-pix_fmt", "yuv420p",
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=60)
    if result.returncode != 0:
        log.error("static_clip.failed", error=result.stderr.decode()[:200])


def _create_placeholder_image(output_path: Path) -> None:
    """Create a placeholder colored image when DALL-E fails."""
    from PIL import Image, ImageDraw
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (1080, 1920), color=(72, 52, 212))
    draw = ImageDraw.Draw(img)
    draw.text((540, 960), "Loading...", fill=(255, 255, 255), anchor="mm")
    img.save(str(output_path))


def _build_style_prefix(visual_style: str, style_lock: dict) -> str:
    """Build the DALL-E style prefix from config and style_lock."""
    import yaml
    from pathlib import Path as P

    cfg_path = P(__file__).parent.parent.parent / "configs" / "visual_styles.yaml"
    try:
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f)
        style_cfg = cfg.get("styles", {}).get(visual_style, {})
        prefix = style_cfg.get("dalle_style_prefix", "")
    except Exception:
        prefix = f"Children's {visual_style} illustration, NO human faces, age-appropriate, "

    return prefix

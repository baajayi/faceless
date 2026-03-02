"""Agent F — Video Assembler.

Composes the final 1080x1920 30fps MP4 using moviepy:
  intro_bumper → shot clips (with captions + audio) → outro_bumper
Generates thumbnail.jpg from first content shot.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from app.db.models import Asset, AssetType, Run, RunStatus, Script, Storyboard, Video
from app.db.session import get_db
from app.settings import settings
from app.storage.artifact_paths import (
    final_video_path,
    music_path,
    run_dir,
    shot_audio_path,
    shot_video_path,
    thumbnail_path,
)
from app.utils.logging import get_logger

log = get_logger(__name__)

FONT_PATH = "/app/assets/fonts/Nunito-Bold.ttf"
INTRO_BUMPER = "/app/assets/bumpers/intro_bumper.png"
OUTRO_BUMPER = "/app/assets/bumpers/outro_bumper.png"

VIDEO_W = 1080
VIDEO_H = 1920
FPS = 30


def run_video_assembly(run_id: str) -> str:
    """Assemble the final video and thumbnail.

    Returns video_id.
    """
    log.info("agent_f.start", run_id=run_id)

    with get_db() as db:
        run = db.get(Run, run_id)
        run_date = str(run.run_date)
        run.status = RunStatus.ASSEMBLING
        db.flush()

        storyboard = db.query(Storyboard).filter(Storyboard.run_id == run_id).first()
        if not storyboard:
            raise ValueError(f"No storyboard for run {run_id}")

        script = (
            db.query(Script)
            .filter(Script.run_id == run_id)
            .order_by(Script.revision.desc())
            .first()
        )
        board_data = storyboard.raw_json
        script_data = script.raw_json if script else {}

    shots = board_data.get("shots", [])
    out_video = final_video_path(run_date)
    out_thumb = thumbnail_path(run_date)

    try:
        _assemble_with_moviepy(
            run_date=run_date,
            shots=shots,
            script_data=script_data,
            out_video=out_video,
            out_thumb=out_thumb,
        )
    except Exception as exc:
        log.error("agent_f.assembly_failed", error=str(exc))
        raise

    # Get duration
    duration_s = _get_video_duration(out_video)

    with get_db() as db:
        run = db.get(Run, run_id)
        video = Video(
            run_id=run_id,
            file_path=str(out_video),
            thumbnail_path=str(out_thumb),
            duration_s=duration_s,
        )
        db.add(video)
        db.flush()
        video_id = video.id

    log.info("agent_f.complete", run_id=run_id, duration_s=duration_s)
    return video_id


def _assemble_with_moviepy(
    run_date: str,
    shots: list[dict],
    script_data: dict,
    out_video: Path,
    out_thumb: Path,
) -> None:
    """Build final video using moviepy."""
    from moviepy import (
        AudioFileClip,
        CompositeAudioClip,
        CompositeVideoClip,
        ImageClip,
        TextClip,
        VideoFileClip,
        concatenate_videoclips,
    )

    clips = []
    audio_clips = []

    # ── Intro bumper ──────────────────────────────────────────────────────
    if Path(INTRO_BUMPER).exists():
        intro = ImageClip(INTRO_BUMPER, duration=1.0).resized((VIDEO_W, VIDEO_H))
        clips.append(intro)

    # ── Shot clips with captions ──────────────────────────────────────────
    current_t = 1.0  # offset after intro

    sound_effects = script_data.get("sound_effects", [])

    for shot in shots:
        idx = shot["index"]
        duration = shot["duration_s"]

        clip_path = shot_video_path(run_date, idx)
        audio_path = shot_audio_path(run_date, idx)

        if clip_path.exists():
            try:
                vid_clip = VideoFileClip(str(clip_path))
                if vid_clip.size != (VIDEO_W, VIDEO_H):
                    vid_clip = vid_clip.resized((VIDEO_W, VIDEO_H))
                vid_clip = vid_clip.with_duration(duration)
            except Exception:
                vid_clip = _fallback_color_clip(duration)
        else:
            vid_clip = _fallback_color_clip(duration)

        # Add text overlay
        text = shot.get("text_overlay") or ""
        if text:
            font = FONT_PATH if Path(FONT_PATH).exists() else None
            try:
                txt_clip = (
                    TextClip(
                        font=font,
                        text=text,
                        font_size=72,
                        color="white",
                        stroke_color="black",
                        stroke_width=3,
                        method="caption",
                        size=(VIDEO_W - 80, None),
                        duration=duration,
                    )
                    .with_position(("center", VIDEO_H - 250))
                )
                vid_clip = CompositeVideoClip([vid_clip, txt_clip])
            except Exception as exc:
                log.warning("agent_f.text_overlay_failed", error=str(exc))

        clips.append(vid_clip)

        # Add audio for this shot
        if audio_path.exists():
            try:
                narr = AudioFileClip(str(audio_path)).with_start(current_t)
                audio_clips.append(narr)
            except Exception as exc:
                log.warning("agent_f.audio_load_failed", shot=idx, error=str(exc))

        current_t += duration

    # ── Outro bumper ──────────────────────────────────────────────────────
    if Path(OUTRO_BUMPER).exists():
        outro = ImageClip(OUTRO_BUMPER, duration=1.0).resized((VIDEO_W, VIDEO_H))
        clips.append(outro)

    if not clips:
        raise ValueError("No clips to assemble")

    # ── Concatenate ────────────────────────────────────────────────────────
    final = concatenate_videoclips(clips, method="compose")

    # ── Mix audio ─────────────────────────────────────────────────────────
    music_file = music_path(run_date)
    if music_file.exists():
        try:
            bg_music = (
                AudioFileClip(str(music_file))
                .with_volume_scaled(0.15)  # -20dB approx
                .with_duration(final.duration)
            )
            audio_clips.append(bg_music)
        except Exception as exc:
            log.warning("agent_f.music_failed", error=str(exc))

    if audio_clips:
        final_audio = CompositeAudioClip(audio_clips)
        final = final.with_audio(final_audio)

    # ── Write final video ─────────────────────────────────────────────────
    out_video.parent.mkdir(parents=True, exist_ok=True)
    final.write_videofile(
        str(out_video),
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        bitrate="4000k",
        threads=4,
        logger=None,
    )

    # ── Thumbnail: first content frame (after intro) ──────────────────────
    _generate_thumbnail(
        out_video=out_video,
        out_thumb=out_thumb,
        title=script_data.get("title", ""),
    )


def _fallback_color_clip(duration: float):
    """Create a solid-color clip as fallback when image/clip is missing."""
    from moviepy import ColorClip
    return ColorClip(size=(VIDEO_W, VIDEO_H), color=(72, 52, 212), duration=duration)


def _generate_thumbnail(out_video: Path, out_thumb: Path, title: str) -> None:
    """Extract frame at ~1.5s (after intro) and add text overlay."""
    out_thumb.parent.mkdir(parents=True, exist_ok=True)

    # Extract frame with ffmpeg
    cmd = [
        "ffmpeg", "-y",
        "-ss", "1.5",
        "-i", str(out_video),
        "-frames:v", "1",
        "-q:v", "2",
        str(out_thumb),
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=30)

    if result.returncode != 0 or not out_thumb.exists():
        # Fallback: use intro bumper as thumbnail
        import shutil
        if Path(INTRO_BUMPER).exists():
            shutil.copy(INTRO_BUMPER, out_thumb)
        return

    # Add text overlay to thumbnail
    if title:
        try:
            from PIL import Image, ImageDraw, ImageFont
            img = Image.open(str(out_thumb))

            try:
                font = ImageFont.truetype(FONT_PATH, size=72)
            except Exception:
                font = ImageFont.load_default()

            draw = ImageDraw.Draw(img)
            # Text background box
            margin = 40
            text_y = VIDEO_H // 3
            draw.rectangle(
                [margin, text_y - 20, VIDEO_W - margin, text_y + 120],
                fill=(0, 0, 0, 180),
            )
            draw.text(
                (VIDEO_W // 2, text_y + 50),
                title[:50],
                font=font,
                fill=(255, 255, 255),
                anchor="mm",
            )
            img.save(str(out_thumb), quality=95)
        except Exception as exc:
            log.warning("thumbnail.text_overlay_failed", error=str(exc))


def _get_video_duration(video_path: Path) -> float:
    """Get video duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return float(result.stdout.strip())
    except Exception:
        return 0.0

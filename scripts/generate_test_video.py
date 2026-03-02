#!/usr/bin/env python3
"""
generate_test_video.py — Run the full pipeline locally without real API keys.

Creates a real MP4 with:
  - PIL-generated shot images (colorful placeholders)
  - Numpy-synthesized sine-wave narration audio (no TTS API needed)
  - Actual moviepy video assembly (Ken Burns effect, captions, bumpers)
  - Real output package: final.mp4, thumbnail.jpg, caption.txt, hashtags.txt, metadata.json

Usage:
    python scripts/generate_test_video.py [--date YYYY-MM-DD] [--output-dir /path/to/output]
"""
from __future__ import annotations

import json
import math
import os
import struct
import sys
import wave
from datetime import date
from pathlib import Path

import click
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ── Constants ─────────────────────────────────────────────────────────────────

W, H = 1080, 1920
FPS = 30
FONT_PATH = str(Path(__file__).parent.parent / "assets" / "fonts" / "Nunito-Bold.ttf")
INTRO_BUMPER = str(Path(__file__).parent.parent / "assets" / "bumpers" / "intro_bumper.png")
OUTRO_BUMPER = str(Path(__file__).parent.parent / "assets" / "bumpers" / "outro_bumper.png")

# Shot color palette — each shot has a distinct background
SHOT_PALETTES = [
    {"bg": (255, 200, 80),  "fg": (220, 60,  30),  "text": (20,  20,  80)},   # warm yellow
    {"bg": (80,  180, 255), "fg": (20,  100, 200), "text": (255, 255, 255)},   # sky blue
    {"bg": (100, 220, 120), "fg": (30,  140, 60),  "text": (255, 255, 255)},   # grass green
    {"bg": (220, 100, 255), "fg": (140, 20,  180), "text": (255, 255, 255)},   # purple
    {"bg": (255, 140, 80),  "fg": (200, 60,  20),  "text": (255, 255, 255)},   # orange
]

# ── Test Pipeline Data ────────────────────────────────────────────────────────

TOPIC = "Why Do Butterflies Have Wings?"

SCRIPT = {
    "title": "Why Do Butterflies Have Wings?",
    "age_band": "4-10",
    "topic": "butterfly wings",
    "narration": [
        {"t": 0.0,  "text": "Have you ever watched a butterfly flutter by?"},
        {"t": 4.0,  "text": "Butterflies have beautiful wings for a reason!"},
        {"t": 8.5,  "text": "Their wings help them fly and find flowers."},
        {"t": 13.0, "text": "Colors keep them safe from hungry birds."},
        {"t": 18.0, "text": "Can you guess what else butterfly wings do?"},
        {"t": 22.0, "text": "They warm up in the sun — pretty cool!"},
    ],
    "on_screen_text": [
        {"t": 0.0,  "text": "🦋 Butterfly Wings!"},
        {"t": 8.5,  "text": "Flying + Finding Food"},
        {"t": 13.0, "text": "Camouflage!"},
        {"t": 18.0, "text": "Can you guess?"},
        {"t": 22.0, "text": "Solar Power!"},
    ],
    "visual_style": "cartoon",
    "cta": "Follow for more fun facts!",
    "estimated_duration_s": 27.0,
}

STORYBOARD = {
    "shots": [
        {
            "index": 0, "duration_s": 4.5,
            "text_overlay": "Butterfly Wings!",
            "narration_text": "Have you ever watched a butterfly flutter by?",
            "camera_motion": {"type": "zoom_in", "magnitude": 0.06},
            "emoji": "🦋",
            "label": "Intro",
        },
        {
            "index": 1, "duration_s": 5.0,
            "text_overlay": "Flying + Finding Food",
            "narration_text": "Butterflies have beautiful wings for a reason! Their wings help them fly and find flowers.",
            "camera_motion": {"type": "pan_right", "magnitude": 0.05},
            "emoji": "🌸",
            "label": "Wings = Flight",
        },
        {
            "index": 2, "duration_s": 5.5,
            "text_overlay": "Camouflage!",
            "narration_text": "Colors keep them safe from hungry birds.",
            "camera_motion": {"type": "zoom_out", "magnitude": 0.05},
            "emoji": "🍃",
            "label": "Hide & Survive",
        },
        {
            "index": 3, "duration_s": 5.0,
            "text_overlay": "Can you guess?",
            "narration_text": "Can you guess what else butterfly wings do?",
            "camera_motion": {"type": "pan_left", "magnitude": 0.05},
            "emoji": "🤔",
            "label": "Quiz Time!",
        },
        {
            "index": 4, "duration_s": 6.0,
            "text_overlay": "Solar Power!",
            "narration_text": "They warm up in the sun — pretty cool!",
            "camera_motion": {"type": "zoom_in", "magnitude": 0.04},
            "emoji": "☀️",
            "label": "Sun Warmth",
        },
    ],
    "total_duration_s": 26.0,
}


# ── Image Generation ──────────────────────────────────────────────────────────

def create_shot_image(
    shot: dict,
    palette: dict,
    output_path: Path,
) -> None:
    """Create a colorful placeholder shot image with PIL."""
    img = Image.new("RGB", (W, H), palette["bg"])
    draw = ImageDraw.Draw(img)

    # Background gradient bands
    band_h = H // 6
    for i in range(7):
        alpha = 0.15 * (i % 2)
        color = tuple(min(255, int(c * (1 - alpha))) for c in palette["bg"])
        draw.rectangle([0, i * band_h, W, (i + 1) * band_h], fill=color)

    # Large decorative circle (represents subject)
    cx, cy = W // 2, int(H * 0.40)
    r = 280
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=palette["fg"])

    # Inner circle
    draw.ellipse([cx - r//2, cy - r//2, cx + r//2, cy + r//2],
                 fill=tuple(min(255, c + 40) for c in palette["fg"]))

    # Emoji / label text in center
    emoji_text = shot.get("emoji", "📚")
    label_text = shot.get("label", "")

    try:
        font_large = ImageFont.truetype(FONT_PATH, size=120)
        font_medium = ImageFont.truetype(FONT_PATH, size=64)
        font_small = ImageFont.truetype(FONT_PATH, size=48)
    except Exception:
        font_large = font_medium = font_small = ImageFont.load_default()

    # Center label
    draw.text((cx, cy), emoji_text, font=font_large, fill=palette["text"], anchor="mm")
    draw.text((cx, cy + 160), label_text, font=font_medium, fill=palette["text"], anchor="mm")

    # Shot number badge (top-left)
    draw.rounded_rectangle([30, 40, 150, 120], radius=20, fill=palette["fg"])
    draw.text((90, 80), f"#{shot['index'] + 1}", font=font_small, fill="white", anchor="mm")

    # Bottom caption bar
    bar_y = H - 300
    draw.rectangle([0, bar_y, W, H], fill=(0, 0, 0))

    # Caption text
    caption = shot.get("text_overlay", "")
    if caption:
        # Wrap long captions
        words = caption.split()
        lines = []
        current = []
        for word in words:
            test = " ".join(current + [word])
            bbox = draw.textbbox((0, 0), test, font=font_medium)
            if bbox[2] - bbox[0] > W - 100 and current:
                lines.append(" ".join(current))
                current = [word]
            else:
                current.append(word)
        if current:
            lines.append(" ".join(current))

        y_start = bar_y + 60
        for line in lines[:3]:
            draw.text((W // 2, y_start), line, font=font_medium,
                      fill="white", anchor="mm")
            y_start += 90

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), quality=95)
    print(f"  [image] Shot {shot['index']} → {output_path.name}")


def create_bumper(path: Path, text: str, bg_color: tuple, text_color: tuple = (255, 255, 255)) -> None:
    """Create a simple branded bumper PNG."""
    if Path(path).exists():
        return  # Use existing

    img = Image.new("RGB", (W, H), bg_color)
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype(FONT_PATH, size=96)
        font_sub = ImageFont.truetype(FONT_PATH, size=52)
    except Exception:
        font = font_sub = ImageFont.load_default()

    # Decorative circles
    draw.ellipse([W//2 - 250, H//2 - 350, W//2 + 250, H//2 + 250],
                 fill=tuple(min(255, c + 30) for c in bg_color))
    draw.ellipse([W//2 - 150, H//2 - 250, W//2 + 150, H//2 + 150],
                 fill=tuple(min(255, c + 60) for c in bg_color))

    # Text
    draw.text((W // 2, H // 2 - 80), "KidsFacts", font=font, fill=text_color, anchor="mm")
    draw.text((W // 2, H // 2 + 60), text, font=font_sub, fill=text_color, anchor="mm")

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    img.save(str(path))


# ── Audio Generation ──────────────────────────────────────────────────────────

def create_tone_audio(
    text: str,
    output_path: Path,
    duration_s: float | None = None,
    base_freq: float = 220.0,
) -> None:
    """Create a sine-wave audio file that approximates speech timing.

    Uses ~3 chars/second reading rate to estimate duration if not given.
    Frequency varies by character to simulate speech rhythm.
    """
    sample_rate = 44100
    chars_per_sec = 14.0  # approximate reading speed
    est_dur = len(text) / chars_per_sec if not duration_s else duration_s
    est_dur = max(1.0, min(est_dur, 8.0))

    n_samples = int(sample_rate * est_dur)
    t = np.linspace(0, est_dur, n_samples, endpoint=False)

    # Build a signal that varies in pitch to simulate speech prosody
    words = text.split()
    n_words = max(len(words), 1)
    audio = np.zeros(n_samples)

    for i, word in enumerate(words):
        start = int(i / n_words * n_samples)
        end = int((i + 1) / n_words * n_samples)
        # Different frequency per word (vowel-based heuristic)
        vowels = sum(1 for c in word.lower() if c in "aeiou")
        freq = base_freq * (1.0 + 0.3 * vowels / max(len(word), 1))
        seg_t = t[start:end]
        envelope = np.hanning(end - start)
        audio[start:end] = 0.4 * np.sin(2 * np.pi * freq * seg_t) * envelope

    # Add slight white noise for naturalness
    audio += 0.02 * np.random.randn(n_samples)
    audio = np.clip(audio, -1.0, 1.0)

    # Convert to 16-bit PCM
    pcm = (audio * 32767).astype(np.int16)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())

    print(f"  [audio] {output_path.name} ({est_dur:.1f}s)")


# ── Video Assembly ────────────────────────────────────────────────────────────

def assemble_video(
    run_date: str,
    shots: list[dict],
    script: dict,
    output_dir: Path,
) -> Path:
    """Assemble the final video using moviepy."""
    from moviepy import (
        AudioFileClip,
        ColorClip,
        CompositeAudioClip,
        CompositeVideoClip,
        ImageClip,
        TextClip,
        concatenate_videoclips,
    )
    import subprocess

    print("\n[assemble] Building video clips...")
    clips = []
    audio_clips = []
    current_t = 0.0

    # Intro bumper (1s)
    if Path(INTRO_BUMPER).exists():
        intro = ImageClip(INTRO_BUMPER, duration=1.0).resized((W, H))
        clips.append(intro)
        current_t += 1.0
        print("  [clip] intro bumper (1.0s)")

    # Shot clips
    for shot in shots:
        idx = shot["index"]
        duration = shot["duration_s"]
        img_path = output_dir / "images" / f"shot_{idx:02d}.png"
        audio_path = output_dir / "audio" / f"shot_{idx:02d}.wav"

        # Load or fall back to color clip
        if img_path.exists():
            clip = ImageClip(str(img_path), duration=duration).resized((W, H))
        else:
            palette = SHOT_PALETTES[idx % len(SHOT_PALETTES)]
            clip = ColorClip((W, H), color=palette["bg"], duration=duration)

        # Apply Ken Burns effect (simple zoom)
        motion = shot.get("camera_motion", {"type": "zoom_in", "magnitude": 0.05})
        clip = _apply_ken_burns(clip, duration, motion)

        # Text overlay at bottom
        caption = shot.get("text_overlay", "")
        if caption:
            try:
                txt = (
                    TextClip(
                        text=caption,
                        font_size=72,
                        color="white",
                        font=FONT_PATH if Path(FONT_PATH).exists() else None,
                        stroke_color="black",
                        stroke_width=3,
                        method="caption",
                        size=(W - 80, None),
                    )
                    .with_position(("center", H - 260))
                    .with_duration(duration)
                )
                clip = CompositeVideoClip([clip, txt], size=(W, H))
            except Exception as e:
                print(f"  [warn] text overlay failed for shot {idx}: {e}")

        clips.append(clip)

        # Add narration audio
        if audio_path.exists():
            try:
                narr = AudioFileClip(str(audio_path)).with_start(current_t)
                audio_clips.append(narr)
            except Exception as e:
                print(f"  [warn] audio load failed for shot {idx}: {e}")

        print(f"  [clip] shot {idx} ({duration}s)")
        current_t += duration

    # Outro bumper (1s)
    if Path(OUTRO_BUMPER).exists():
        outro = ImageClip(OUTRO_BUMPER, duration=1.0).resized((W, H))
        clips.append(outro)
        print("  [clip] outro bumper (1.0s)")

    print("\n[assemble] Concatenating clips...")
    final = concatenate_videoclips(clips, method="compose")

    # Mix audio
    if audio_clips:
        final_audio = CompositeAudioClip(audio_clips)
        final = final.with_audio(final_audio)

    out_path = output_dir / "final.mp4"
    print(f"\n[assemble] Writing {out_path} ({final.duration:.1f}s)...")
    final.write_videofile(
        str(out_path),
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        threads=4,
        logger="bar",
    )

    return out_path


def _apply_ken_burns(clip, duration: float, motion: dict):
    """Apply a simple zoom/pan effect to an ImageClip."""
    motion_type = motion.get("type", "zoom_in")
    magnitude = motion.get("magnitude", 0.05)

    # For simplicity, just use a static resize — full Ken Burns requires
    # per-frame manipulation which is very slow without GPU
    if motion_type in ("zoom_in", "zoom_out"):
        scale = 1.0 + magnitude
        w2, h2 = int(W * scale), int(H * scale)
        # Crop back to original size from center
        clip = clip.resized((w2, h2)).cropped(
            x_center=w2 // 2,
            y_center=h2 // 2,
            width=W,
            height=H,
        )
    return clip


def create_thumbnail(video_path: Path, output_path: Path, title: str) -> None:
    """Extract frame and add title text."""
    import subprocess

    # Extract frame at 1.5s
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-ss", "1.5",
        "-i", str(video_path),
        "-frames:v", "1", "-q:v", "2",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=30)

    if not output_path.exists():
        # Fallback to intro bumper
        if Path(INTRO_BUMPER).exists():
            import shutil
            shutil.copy(INTRO_BUMPER, output_path)
        return

    # Add title overlay
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.open(str(output_path)).convert("RGB")
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype(FONT_PATH, size=72)
        except Exception:
            font = ImageFont.load_default()

        # Title banner
        margin = 50
        draw.rectangle([0, 0, W, 140], fill=(0, 0, 0, 200))
        draw.text((W // 2, 70), title[:55], font=font, fill=(255, 220, 50), anchor="mm")
        img.save(str(output_path), quality=95)
    except Exception as e:
        print(f"  [warn] thumbnail text overlay failed: {e}")

    print(f"  [thumb] {output_path.name}")


# ── Main Entry Point ──────────────────────────────────────────────────────────

@click.command()
@click.option("--date", "run_date", default=None,
              help="Run date YYYY-MM-DD (default: today)")
@click.option("--output-dir", default=None,
              help="Output root directory (default: output/)")
def main(run_date: str | None, output_dir: str | None) -> None:
    """Generate a test video without any API calls."""

    run_date = run_date or str(date.today())
    base_dir = Path(output_dir) if output_dir else Path(__file__).parent.parent / "output"
    out_dir = base_dir / run_date
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  Faceless TikTok Pipeline — Test Video Generator")
    print(f"  Date: {run_date}")
    print(f"  Output: {out_dir}")
    print(f"{'='*60}\n")

    shots = STORYBOARD["shots"]

    # ── Step 1: Generate shot images ──────────────────────────────────────
    print("[1/5] Generating shot images...")
    for i, shot in enumerate(shots):
        palette = SHOT_PALETTES[i % len(SHOT_PALETTES)]
        img_path = out_dir / "images" / f"shot_{shot['index']:02d}.png"
        create_shot_image(shot, palette, img_path)

    # ── Step 2: Ensure bumpers exist ──────────────────────────────────────
    print("\n[2/5] Checking bumpers...")
    create_bumper(INTRO_BUMPER, "Daily Fun Facts", bg_color=(72, 52, 212))
    create_bumper(OUTRO_BUMPER, "Subscribe for more!", bg_color=(52, 172, 100))
    print(f"  intro: {Path(INTRO_BUMPER).name}")
    print(f"  outro: {Path(OUTRO_BUMPER).name}")

    # ── Step 3: Generate narration audio ─────────────────────────────────
    print("\n[3/5] Synthesizing narration audio...")
    for shot in shots:
        audio_path = out_dir / "audio" / f"shot_{shot['index']:02d}.wav"
        text = shot.get("narration_text", "Fun fact!")
        create_tone_audio(text, audio_path, duration_s=shot["duration_s"] * 0.85)

    # ── Step 4: Assemble video ────────────────────────────────────────────
    print("\n[4/5] Assembling video...")
    video_path = assemble_video(run_date, shots, SCRIPT, out_dir)

    # ── Step 5: Generate thumbnail + write metadata ───────────────────────
    print("\n[5/5] Generating thumbnail and metadata package...")
    thumb_path = out_dir / "thumbnail.jpg"
    create_thumbnail(video_path, thumb_path, SCRIPT["title"])

    caption = (
        f"Did you know butterflies use their wings for more than flying? "
        f"Watch to find out! 🦋"
    )
    hashtags = ["kidslearning", "butterflies", "science", "didyouknow", "funfacts"]

    (out_dir / "caption.txt").write_text(caption)
    (out_dir / "hashtags.txt").write_text("\n".join(f"#{h}" for h in hashtags))
    (out_dir / "metadata.json").write_text(json.dumps({
        "run_date": run_date,
        "title": SCRIPT["title"],
        "topic": SCRIPT["topic"],
        "age_band": SCRIPT["age_band"],
        "visual_style": SCRIPT["visual_style"],
        "caption": caption,
        "hashtags": hashtags,
        "video_path": str(video_path),
        "thumbnail_path": str(thumb_path),
        "shots": len(shots),
        "mode": "test_no_api",
        "note": "Generated without API calls — placeholder images and synthetic audio",
    }, indent=2))

    # ── Summary ───────────────────────────────────────────────────────────
    import subprocess
    dur_result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True
    )
    duration = float(dur_result.stdout.strip()) if dur_result.returncode == 0 else 0.0

    print(f"\n{'='*60}")
    print(f"  Video complete!")
    print(f"{'='*60}")
    print(f"  final.mp4      {video_path}  ({duration:.1f}s)")
    print(f"  thumbnail.jpg  {thumb_path}")
    print(f"  caption.txt    {out_dir / 'caption.txt'}")
    print(f"  hashtags.txt   {out_dir / 'hashtags.txt'}")
    print(f"  metadata.json  {out_dir / 'metadata.json'}")
    print(f"\n  Resolution:  {W}x{H}  ({W/H:.3f} ≈ 9:16)")
    print(f"  Shots:       {len(shots)}")
    print(f"  Duration:    {duration:.1f}s")
    print(f"\n  To view:  ffplay {video_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()

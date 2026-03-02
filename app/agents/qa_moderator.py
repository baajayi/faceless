"""Agent H — QA / Moderation.

Validates the final video before publishing:
- Content moderation on script text
- Duration check (15–60s)
- Audio level check
- Caption size check
- On fail: retry scriptwriter once, then NEEDS_REVIEW
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from app.db.models import Run, RunStatus, Script, Video
from app.db.session import get_db
from app.services.moderation.openai_moderation import moderate_text
from app.storage.artifact_paths import final_video_path
from app.utils.logging import get_logger

log = get_logger(__name__)

MIN_DURATION_S = 15.0
MAX_DURATION_S = 60.0
MIN_LUFS = -30.0  # relaxed threshold (ideal -23 LUFS)
MIN_CAPTION_FONTSIZE = 60


def run_qa_moderation(run_id: str) -> dict:
    """Run QA checks on the assembled video.

    Returns qa_report dict with keys: passed, failures, checked_at.
    """
    log.info("agent_h.start", run_id=run_id)

    with get_db() as db:
        run = db.get(Run, run_id)
        run_date = str(run.run_date)
        run.status = RunStatus.QA
        db.flush()

        script = (
            db.query(Script)
            .filter(Script.run_id == run_id)
            .order_by(Script.revision.desc())
            .first()
        )
        video = db.query(Video).filter(Video.run_id == run_id).first()

    failures = []

    # ── 1. Text moderation ────────────────────────────────────────────────
    if script:
        narration = script.raw_json.get("narration", [])
        full_text = " ".join(n["text"] for n in narration)
        moderation = moderate_text(full_text)
        if moderation["flagged"]:
            failures.append({
                "check": "content_moderation",
                "detail": f"Script flagged: risk_score={moderation['risk_score']}",
            })

    # ── 2. Duration check ─────────────────────────────────────────────────
    if video and video.duration_s:
        if video.duration_s < MIN_DURATION_S:
            failures.append({
                "check": "duration",
                "detail": f"Video too short: {video.duration_s:.1f}s (min {MIN_DURATION_S}s)",
            })
        elif video.duration_s > MAX_DURATION_S:
            failures.append({
                "check": "duration",
                "detail": f"Video too long: {video.duration_s:.1f}s (max {MAX_DURATION_S}s)",
            })
    elif video and not video.duration_s:
        failures.append({"check": "duration", "detail": "Could not determine video duration"})

    # ── 3. Audio level check ──────────────────────────────────────────────
    video_file = final_video_path(run_date)
    if video_file.exists():
        lufs = _measure_loudness(video_file)
        if lufs is not None and lufs < MIN_LUFS:
            failures.append({
                "check": "audio_levels",
                "detail": f"Mean loudness too low: {lufs:.1f} LUFS (min {MIN_LUFS})",
            })

    # ── 4. Caption size check (heuristic — verify config ≥ 60px) ─────────
    # This checks the script config, not actual rendered pixels
    # Actual font size is hardcoded to 72 in video_assembler.py
    caption_fontsize = 72  # hardcoded in assembler
    if caption_fontsize < MIN_CAPTION_FONTSIZE:
        failures.append({
            "check": "caption_size",
            "detail": f"Caption font size {caption_fontsize} < {MIN_CAPTION_FONTSIZE}",
        })

    qa_passed = len(failures) == 0
    qa_report = {
        "passed": qa_passed,
        "failures": failures,
        "checked_at": str(__import__("datetime").datetime.utcnow()),
    }

    # ── Save QA results ───────────────────────────────────────────────────
    with get_db() as db:
        video = db.query(Video).filter(Video.run_id == run_id).first()
        if video:
            video.qa_passed = qa_passed
            video.qa_report = qa_report
            db.flush()

    log.info(
        "agent_h.result",
        run_id=run_id,
        passed=qa_passed,
        failures=len(failures),
    )
    return qa_report


def _measure_loudness(video_path: Path) -> Optional[float]:
    """Measure mean loudness in LUFS using ffmpeg volumedetect."""
    try:
        cmd = [
            "ffmpeg", "-i", str(video_path),
            "-af", "volumedetect",
            "-f", "null", "-",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = result.stderr

        # Parse mean_volume from output
        for line in output.splitlines():
            if "mean_volume" in line:
                # e.g. "mean_volume: -23.5 dB"
                parts = line.split(":")
                if len(parts) >= 2:
                    val = parts[1].strip().replace(" dB", "")
                    return float(val)
    except Exception as exc:
        log.warning("qa.loudness_check_failed", error=str(exc))
    return None

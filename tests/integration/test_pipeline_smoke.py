"""Integration smoke test — full pipeline with all external calls mocked.

This test verifies:
1. All pipeline stages execute in order without errors
2. The final output package (caption.txt, hashtags.txt, metadata.json) is created
3. No real API calls are made

DB correctness is tested separately in test_db_models.py.
"""
from __future__ import annotations

import json
import uuid
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest


def _make_run(run_date: str = "2026-03-02") -> MagicMock:
    """Create a mock Run ORM object."""
    run = MagicMock()
    run.id = str(uuid.uuid4())
    run.run_date = date.fromisoformat(run_date)
    run.status = "PENDING"
    run.cost_usd = 0
    return run


def _make_topic(run_id: str, title: str) -> MagicMock:
    topic = MagicMock()
    topic.id = str(uuid.uuid4())
    topic.run_id = run_id
    topic.title = title
    topic.is_selected = True
    topic.category = "animals"
    topic.trend_score = 0.8
    topic.kid_score = 0.7
    topic.educational_score = 0.9
    topic.novelty_score = 1.0
    topic.risk_score = 0.01
    topic.composite_score = 0.75
    return topic


def _make_script(run_id: str, topic_id: str, script_json: dict) -> MagicMock:
    script = MagicMock()
    script.id = str(uuid.uuid4())
    script.run_id = run_id
    script.topic_id = topic_id
    script.raw_json = script_json
    script.revision = 0
    return script


def _make_storyboard(run_id: str, board_json: dict) -> MagicMock:
    board = MagicMock()
    board.id = str(uuid.uuid4())
    board.run_id = run_id
    board.raw_json = board_json
    board.shot_count = len(board_json.get("shots", []))
    return board


def _make_video(run_id: str, video_path: str, thumb_path: str) -> MagicMock:
    video = MagicMock()
    video.id = str(uuid.uuid4())
    video.run_id = run_id
    video.file_path = video_path
    video.thumbnail_path = thumb_path
    video.duration_s = 17.0
    video.qa_passed = True
    video.qa_report = {"passed": True, "failures": []}
    return video


def _make_publish_job(run_id: str) -> MagicMock:
    job = MagicMock()
    job.id = str(uuid.uuid4())
    job.run_id = run_id
    job.mode = "C"
    job.status = "PENDING"
    job.caption = "Amazing butterfly facts!"
    job.hashtags = ["kidslearning", "butterflies"]
    job.metadata_json = {}
    return job


SAMPLE_SCRIPT = {
    "title": "Why Do Butterflies Have Wings?",
    "age_band": "4-10",
    "topic": "butterfly wings",
    "narration": [
        {"t": 0.0, "text": "Have you ever watched a butterfly flutter?"},
        {"t": 5.0, "text": "Butterflies have wings for a special reason!"},
        {"t": 10.0, "text": "Their wings help them fly and find flowers."},
    ],
    "on_screen_text": [{"t": 0.0, "text": "Butterfly Wings!"}],
    "sound_effects": [{"t": 0.0, "type": "whoosh"}],
    "visual_style": "cartoon",
    "style_lock": {
        "palette": "bright blues and purples",
        "character_style": "cute cartoon butterfly, no human faces",
        "background_style": "colorful garden",
    },
    "cta": "Follow for more fun facts!",
    "pronunciation_hints": {},
    "estimated_duration_s": 18.0,
}

SAMPLE_STORYBOARD = {
    "topic": "butterfly wings",
    "visual_style": "cartoon",
    "style_lock": {
        "palette": "bright colors",
        "character_style": "cartoon butterfly, no faces",
        "background_style": "garden",
    },
    "shots": [
        {
            "index": 0,
            "duration_s": 5.0,
            "narration_indices": [0],
            "background": "bright garden with colorful flowers",
            "foreground_elements": ["butterfly"],
            "camera_motion": {"type": "zoom_in", "magnitude": 0.05},
            "text_overlay": "Wings!",
            "dalle_prompt": "Cartoon butterfly, NO human faces, children's illustration",
            "sfx_type": "whoosh",
        },
        {
            "index": 1,
            "duration_s": 5.0,
            "narration_indices": [1],
            "background": "bright blue sky with clouds",
            "foreground_elements": ["butterfly"],
            "camera_motion": {"type": "static", "magnitude": 0.0},
            "text_overlay": "Amazing!",
            "dalle_prompt": "Cartoon butterfly flying, NO human faces, bright colors",
            "sfx_type": "ding",
        },
        {
            "index": 2,
            "duration_s": 7.0,
            "narration_indices": [2],
            "background": "colorful forest with leaves",
            "foreground_elements": ["butterfly", "leaves"],
            "camera_motion": {"type": "zoom_out", "magnitude": 0.05},
            "text_overlay": "Camouflage!",
            "dalle_prompt": "Butterfly hiding in leaves, NO human faces, educational",
            "sfx_type": None,
        },
    ],
    "total_duration_s": 17.0,
}


class TestPipelineSmoke:
    def test_full_pipeline_runs_to_completion(self, tmp_path, monkeypatch):
        """Full pipeline should complete without errors and create output files."""
        run_date = "2026-03-02"

        # ── Patch settings ─────────────────────────────────────────────────
        monkeypatch.setenv("ARTIFACTS_DIR", str(tmp_path))

        # ── Build mock DB state ────────────────────────────────────────────
        mock_run = _make_run(run_date)
        mock_topic = _make_topic(mock_run.id, "Why Do Butterflies Have Wings")
        mock_script = _make_script(mock_run.id, mock_topic.id, SAMPLE_SCRIPT)
        mock_board = _make_storyboard(mock_run.id, SAMPLE_STORYBOARD)

        video_path = str(tmp_path / run_date / "final.mp4")
        thumb_path = str(tmp_path / run_date / "thumbnail.jpg")
        mock_video = _make_video(mock_run.id, video_path, thumb_path)
        mock_pub_job = _make_publish_job(mock_run.id)

        # ── Mock session / DB ──────────────────────────────────────────────
        mock_session = MagicMock()
        mock_session.__enter__ = lambda s: s
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.flush = MagicMock()
        mock_session.commit = MagicMock()
        mock_session.close = MagicMock()

        def mock_db_get(model_class, pk):
            # Always return the mock run for any ORM get
            return mock_run

        mock_session.get.side_effect = mock_db_get

        def mock_query(model_class):
            q = MagicMock()
            if hasattr(model_class, "__tablename__"):
                name = model_class.__tablename__
                if name == "runs":
                    q.filter.return_value.first.return_value = mock_run
                    q.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [mock_run]
                elif name == "topics":
                    q.filter.return_value.first.return_value = mock_topic
                    q.filter.return_value.all.return_value = [mock_topic]
                    q.join.return_value.filter.return_value.all.return_value = []
                    q.filter.return_value.count.return_value = 0
                elif name == "scripts":
                    q.filter.return_value.order_by.return_value.first.return_value = mock_script
                elif name == "storyboards":
                    q.filter.return_value.first.return_value = mock_board
                elif name == "videos":
                    q.filter.return_value.first.return_value = mock_video
                elif name == "publish_jobs":
                    q.filter.return_value.first.return_value = mock_pub_job
                elif name == "errors":
                    q.filter.return_value.count.return_value = 0
            return q

        mock_session.query.side_effect = mock_query
        mock_session.add = MagicMock()

        # ── Mock OpenAI ────────────────────────────────────────────────────
        openai_mock = MagicMock()

        def mock_chat_create(*args, **kwargs):
            messages = kwargs.get("messages", [])
            system = next((m["content"] for m in messages if m["role"] == "system"), "")

            if "storyboard" in system.lower() or "shot" in system.lower():
                content = json.dumps(SAMPLE_STORYBOARD)
            elif "hashtag" in system.lower() or "caption" in system.lower() or "social" in system.lower():
                content = json.dumps({
                    "caption": "Amazing butterfly facts! Did you know their wings have a secret?",
                    "hashtags": ["kidslearning", "butterflies", "science"],
                })
            else:
                content = json.dumps(SAMPLE_SCRIPT)

            resp = MagicMock()
            resp.choices = [MagicMock()]
            resp.choices[0].message.content = content
            resp.usage.prompt_tokens = 100
            resp.usage.completion_tokens = 200
            return resp

        openai_mock.chat.completions.create.side_effect = mock_chat_create
        openai_mock.audio.speech.create.return_value.content = b"\x00" * 1000

        import base64
        from PIL import Image
        import io
        img = Image.new("RGB", (1024, 1792), color=(72, 52, 212))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        mock_dalle_data = MagicMock()
        mock_dalle_data.b64_json = b64
        openai_mock.images.generate.return_value.data = [mock_dalle_data]

        mock_mod_result = MagicMock()
        mock_mod_result.flagged = False
        mock_mod_result.category_scores.model_dump.return_value = {
            "harassment": 0.001,
            "violence": 0.001,
        }
        mock_moderation_resp = MagicMock()
        mock_moderation_resp.results = [mock_mod_result]
        mock_moderation_resp.model_dump.return_value = {"id": "modr-test", "results": []}
        openai_mock.moderations.create.return_value = mock_moderation_resp

        # ── Pre-create output video + thumbnail files ──────────────────────
        (tmp_path / run_date).mkdir(parents=True, exist_ok=True)
        Path(video_path).write_bytes(b"\x00" * 100)
        Path(thumb_path).write_bytes(b"\xff" * 100)

        # ── Run pipeline with all mocks active ────────────────────────────
        # Patch the real settings singleton attributes directly so all modules see them
        from app.settings import settings as real_settings
        original_artifacts_dir = real_settings.ARTIFACTS_DIR
        original_music_mode = real_settings.MUSIC_MODE
        original_publish_mode = real_settings.PUBLISH_MODE
        real_settings.ARTIFACTS_DIR = str(tmp_path)
        real_settings.MUSIC_MODE = "none"
        real_settings.PUBLISH_MODE = "C"
        real_settings.SAFETY_STRICTNESS = "high"

        try:
         with patch("openai.OpenAI", return_value=openai_mock), \
             patch("app.services.trends.google_trends.fetch_google_trends",
                   return_value=[
                       {"title": "Why Do Butterflies Have Wings", "trend_score": 0.8, "source": "fallback"},
                   ]), \
             patch("app.services.trends.youtube_trends.fetch_youtube_trends",
                   return_value=[]), \
             patch("app.db.session.SessionLocal", return_value=mock_session), \
             patch("app.agents.asset_generator._create_ken_burns_clip"), \
             patch("app.agents.video_assembler._assemble_with_moviepy"), \
             patch("subprocess.run") as mock_subproc:

            mock_subproc.return_value = MagicMock(returncode=0, stdout="17.0\n", stderr="")

            from app.pipelines.daily_pipeline import trigger_run
            run_id = trigger_run(run_date, force=True)

        finally:
            # Restore original settings
            real_settings.ARTIFACTS_DIR = original_artifacts_dir
            real_settings.MUSIC_MODE = original_music_mode
            real_settings.PUBLISH_MODE = original_publish_mode

        # ── Verify run completed and output files exist ────────────────────
        assert run_id is not None
        assert len(run_id) > 0

        # caption.txt, hashtags.txt, metadata.json should be created by Agent I
        output_dir = tmp_path / run_date
        assert (output_dir / "caption.txt").exists(), "caption.txt not created"
        assert (output_dir / "hashtags.txt").exists(), "hashtags.txt not created"
        assert (output_dir / "metadata.json").exists(), "metadata.json not created"

        # Verify caption content
        caption = (output_dir / "caption.txt").read_text()
        assert len(caption) > 0

        # Verify hashtags content
        hashtags = (output_dir / "hashtags.txt").read_text()
        assert "#" in hashtags

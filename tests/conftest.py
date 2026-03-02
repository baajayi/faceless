"""Shared test fixtures."""
from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base


# ── In-memory SQLite DB ───────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def sqlite_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    # SQLite doesn't support ARRAY or JSONB natively — use JSON text instead
    # We use the same models but with SQLite dialect
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(sqlite_engine):
    """Provides a transactional DB session that rolls back after each test."""
    connection = sqlite_engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


# ── Mock OpenAI ───────────────────────────────────────────────────────────────

@pytest.fixture
def mock_openai_chat():
    """Mock openai.OpenAI().chat.completions.create."""
    with patch("openai.OpenAI") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "{}"
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 200
        mock_client.chat.completions.create.return_value = mock_response

        yield mock_client


@pytest.fixture
def mock_openai_moderation():
    """Mock OpenAI moderation API — returns safe result."""
    with patch("app.services.moderation.openai_moderation.openai.OpenAI") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        mock_result = MagicMock()
        mock_result.flagged = False
        mock_result.category_scores.model_dump.return_value = {
            "harassment": 0.001,
            "hate": 0.001,
            "sexual": 0.001,
            "violence": 0.001,
        }

        mock_response = MagicMock()
        mock_response.results = [mock_result]
        mock_client.moderations.create.return_value = mock_response

        yield mock_client


@pytest.fixture
def mock_dalle():
    """Mock DALL-E image generation."""
    with patch("app.services.image_gen.dalle_service.openai.OpenAI") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        # Return a valid 1x1 PNG
        import base64
        from PIL import Image
        import io
        img = Image.new("RGB", (1024, 1792), color=(72, 52, 212))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()

        mock_img_data = MagicMock()
        mock_img_data.b64_json = b64
        mock_response = MagicMock()
        mock_response.data = [mock_img_data]
        mock_client.images.generate.return_value = mock_response

        yield mock_client


@pytest.fixture
def mock_tts():
    """Mock OpenAI TTS."""
    with patch("app.services.tts.openai_tts.openai.OpenAI") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.audio.speech.create.return_value.content = b"\x00" * 1000
        yield mock_client


# ── Sample data ───────────────────────────────────────────────────────────────

@pytest.fixture
def sample_run_id():
    return str(uuid.uuid4())


@pytest.fixture
def sample_run_date():
    return "2026-03-02"


@pytest.fixture
def sample_script_json():
    return {
        "title": "Why Do Butterflies Have Wings?",
        "age_band": "4-10",
        "topic": "butterfly wings",
        "narration": [
            {"t": 0.0, "text": "Have you ever watched a butterfly flutter by?"},
            {"t": 4.0, "text": "Butterflies have beautiful wings for a special reason!"},
            {"t": 8.0, "text": "Their wings help them fly and find flowers."},
            {"t": 12.0, "text": "The colors help them hide from animals that might eat them."},
            {"t": 16.0, "text": "Isn't that amazing? Can you guess what else wings do?"},
        ],
        "on_screen_text": [
            {"t": 0.0, "text": "Butterfly Wings!"},
            {"t": 8.0, "text": "Flying + Finding Food"},
        ],
        "sound_effects": [
            {"t": 0.0, "type": "whoosh"},
            {"t": 12.0, "type": "ding"},
        ],
        "visual_style": "cartoon",
        "style_lock": {
            "palette": "bright blues, purples, greens",
            "character_style": "cute cartoon butterfly, no human faces, round shapes",
            "background_style": "colorful garden with flowers",
        },
        "cta": "Follow for more fun facts!",
        "pronunciation_hints": {"butterflies": "BUH-ter-flize"},
        "estimated_duration_s": 22.0,
    }


@pytest.fixture
def sample_storyboard_json(sample_script_json):
    return {
        "topic": sample_script_json["topic"],
        "visual_style": "cartoon",
        "style_lock": sample_script_json["style_lock"],
        "shots": [
            {
                "index": 0,
                "duration_s": 4.0,
                "narration_indices": [0],
                "background": "bright garden with colorful flowers",
                "foreground_elements": ["cartoon butterfly", "flowers"],
                "camera_motion": {"type": "zoom_in", "magnitude": 0.05},
                "text_overlay": "Butterfly Wings!",
                "dalle_prompt": "Cute cartoon butterfly with colorful wings flying over flowers, bright garden background, NO human faces, children's illustration",
                "sfx_type": "whoosh",
            },
            {
                "index": 1,
                "duration_s": 5.0,
                "narration_indices": [1, 2],
                "background": "blue sky with clouds",
                "foreground_elements": ["cartoon butterfly flying"],
                "camera_motion": {"type": "pan_right", "magnitude": 0.05},
                "text_overlay": "Flying + Finding Food",
                "dalle_prompt": "Cartoon butterfly soaring through blue sky with fluffy clouds, NO human faces, children's educational illustration",
                "sfx_type": None,
            },
            {
                "index": 2,
                "duration_s": 8.0,
                "narration_indices": [3, 4],
                "background": "colorful forest",
                "foreground_elements": ["butterfly", "leaves", "predator animal"],
                "camera_motion": {"type": "zoom_out", "magnitude": 0.05},
                "text_overlay": "Camouflage!",
                "dalle_prompt": "Colorful cartoon butterfly camouflaged among leaves, showing wing patterns, NO human faces, bright children's illustration",
                "sfx_type": "ding",
            },
        ],
        "total_duration_s": 17.0,
    }

"""Unit tests for OpenAI moderation service."""
from unittest.mock import MagicMock, patch

import pytest

from app.services.moderation.openai_moderation import _get_threshold, moderate_text


class TestModerationService:
    def test_safe_content_not_flagged(self):
        """Safe content should return flagged=False."""
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

            result = moderate_text("Butterflies have beautiful wings!")

        assert result["flagged"] is False
        assert result["risk_score"] < 0.2

    def test_unsafe_content_flagged(self):
        """Content with high scores should be flagged."""
        with patch("app.services.moderation.openai_moderation.openai.OpenAI") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client

            mock_result = MagicMock()
            mock_result.flagged = True
            mock_result.category_scores.model_dump.return_value = {
                "harassment": 0.9,
                "violence": 0.85,
                "sexual": 0.1,
            }

            mock_response = MagicMock()
            mock_response.results = [mock_result]
            mock_client.moderations.create.return_value = mock_response

            result = moderate_text("violent content text")

        assert result["flagged"] is True
        assert result["risk_score"] == 0.9

    def test_api_error_returns_max_risk(self):
        """On API error, should fail safe with max risk."""
        with patch("app.services.moderation.openai_moderation.openai.OpenAI") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.moderations.create.side_effect = Exception("API error")

            result = moderate_text("some text")

        assert result["flagged"] is True
        assert result["risk_score"] == 1.0

    def test_risk_score_is_max_of_categories(self):
        """risk_score should be the max of all category scores."""
        with patch("app.services.moderation.openai_moderation.openai.OpenAI") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client

            mock_result = MagicMock()
            mock_result.flagged = False
            mock_result.category_scores.model_dump.return_value = {
                "cat1": 0.1,
                "cat2": 0.3,
                "cat3": 0.05,
            }

            mock_response = MagicMock()
            mock_response.results = [mock_result]
            mock_client.moderations.create.return_value = mock_response

            result = moderate_text("test text")

        assert result["risk_score"] == 0.3


class TestThresholds:
    def test_high_strictness_low_threshold(self):
        with patch("app.services.moderation.openai_moderation.settings") as mock_settings:
            mock_settings.SAFETY_STRICTNESS = "high"
            threshold = _get_threshold()
        assert threshold == 0.2

    def test_med_strictness_threshold(self):
        with patch("app.services.moderation.openai_moderation.settings") as mock_settings:
            mock_settings.SAFETY_STRICTNESS = "med"
            threshold = _get_threshold()
        assert threshold == 0.5

    def test_low_strictness_high_threshold(self):
        with patch("app.services.moderation.openai_moderation.settings") as mock_settings:
            mock_settings.SAFETY_STRICTNESS = "low"
            threshold = _get_threshold()
        assert threshold == 0.8

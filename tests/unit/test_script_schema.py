"""Unit tests for ScriptSchema Pydantic validation."""
import pytest
from pydantic import ValidationError

from app.agents.scriptwriter import ScriptSchema


@pytest.fixture
def valid_script():
    return {
        "title": "Why Do Butterflies Have Wings?",
        "age_band": "4-10",
        "topic": "butterfly wings",
        "narration": [
            {"t": 0.0, "text": "Have you ever watched a butterfly flutter?"},
            {"t": 4.0, "text": "Butterflies have wings for a special reason!"},
            {"t": 8.0, "text": "Wings help them fly and find flowers."},
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
        "estimated_duration_s": 25.0,
    }


class TestScriptSchemaValidation:
    def test_valid_script_passes(self, valid_script):
        script = ScriptSchema.model_validate(valid_script)
        assert script.title == "Why Do Butterflies Have Wings?"
        assert len(script.narration) == 3

    def test_missing_title_fails(self, valid_script):
        valid_script.pop("title")
        with pytest.raises(ValidationError):
            ScriptSchema.model_validate(valid_script)

    def test_empty_narration_fails(self, valid_script):
        valid_script["narration"] = [{"t": 0.0, "text": "Only one item"}]
        with pytest.raises(ValidationError):
            ScriptSchema.model_validate(valid_script)

    def test_narration_too_many_words(self, valid_script):
        valid_script["narration"][0]["text"] = " ".join(["word"] * 16)
        with pytest.raises(ValidationError):
            ScriptSchema.model_validate(valid_script)

    def test_narration_max_words_ok(self, valid_script):
        valid_script["narration"][0]["text"] = " ".join(["word"] * 12)
        script = ScriptSchema.model_validate(valid_script)
        assert script is not None

    def test_invalid_visual_style(self, valid_script):
        valid_script["visual_style"] = "photorealistic"
        with pytest.raises(ValidationError):
            ScriptSchema.model_validate(valid_script)

    def test_invalid_sfx_type(self, valid_script):
        valid_script["sound_effects"] = [{"t": 0.0, "type": "bang"}]
        with pytest.raises(ValidationError):
            ScriptSchema.model_validate(valid_script)

    def test_valid_sfx_types(self, valid_script):
        for sfx_type in ["pop", "ding", "whoosh"]:
            valid_script["sound_effects"] = [{"t": 0.0, "type": sfx_type}]
            script = ScriptSchema.model_validate(valid_script)
            assert script.sound_effects[0].type == sfx_type

    def test_duration_autocorrect(self, valid_script):
        """Duration auto-corrects if it doesn't match narration timing by >5s."""
        # Last narration t=8.0, so expected auto-corrected = 8+3 = 11.0
        # Use 55.0: valid per field constraints (15–60) but >5s off from computed 11.0
        valid_script["estimated_duration_s"] = 55.0
        script = ScriptSchema.model_validate(valid_script)
        # Should auto-correct to last narration time + 3 = 11.0
        assert script.estimated_duration_s < 20.0

    def test_cta_max_length(self, valid_script):
        valid_script["cta"] = "x" * 151
        with pytest.raises(ValidationError):
            ScriptSchema.model_validate(valid_script)

    def test_duration_too_short(self, valid_script):
        valid_script["estimated_duration_s"] = 10.0
        with pytest.raises(ValidationError):
            ScriptSchema.model_validate(valid_script)

    def test_duration_too_long(self, valid_script):
        valid_script["estimated_duration_s"] = 65.0
        with pytest.raises(ValidationError):
            ScriptSchema.model_validate(valid_script)

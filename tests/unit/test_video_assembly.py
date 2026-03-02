"""Unit tests for video assembly utilities."""
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestVideoAssembly:
    def test_fallback_color_clip_returns_clip(self):
        """_fallback_color_clip should return a moviepy clip."""
        pytest.importorskip("moviepy")
        from app.agents.video_assembler import _fallback_color_clip

        clip = _fallback_color_clip(5.0)
        assert clip is not None
        assert abs(clip.duration - 5.0) < 0.1

    def test_get_video_duration_returns_float(self):
        """_get_video_duration should return 0.0 for non-existent file."""
        from app.agents.video_assembler import _get_video_duration

        result = _get_video_duration(Path("/nonexistent/video.mp4"))
        assert isinstance(result, float)
        assert result == 0.0

    def test_placeholder_image_created(self):
        """_create_placeholder_image should create a valid PNG."""
        from app.agents.asset_generator import _create_placeholder_image

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_placeholder.png"
            _create_placeholder_image(output_path)

            assert output_path.exists()
            # Verify it's a valid image
            from PIL import Image
            img = Image.open(output_path)
            assert img.size == (1080, 1920)

    def test_style_prefix_built_from_config(self):
        """_build_style_prefix should return a non-empty string for known styles."""
        from app.agents.asset_generator import _build_style_prefix

        prefix = _build_style_prefix("cartoon", {})
        assert isinstance(prefix, str)
        assert len(prefix) > 0

    def test_style_prefix_unknown_style_fallback(self):
        """Unknown visual style should fall back gracefully."""
        from app.agents.asset_generator import _build_style_prefix

        prefix = _build_style_prefix("unknown_style", {})
        assert isinstance(prefix, str)

    @patch("subprocess.run")
    def test_static_clip_calls_ffmpeg(self, mock_run):
        """_create_static_clip should invoke ffmpeg."""
        from app.agents.asset_generator import _create_static_clip

        mock_run.return_value = MagicMock(returncode=0)

        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "test.png"
            # Create placeholder image
            from PIL import Image
            Image.new("RGB", (1080, 1920), (72, 52, 212)).save(image_path)

            output_path = Path(tmpdir) / "out.mp4"
            _create_static_clip(image_path, output_path, 3.0)

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "ffmpeg" in args

    def test_thumbnail_generation_missing_video(self):
        """Thumbnail generation should handle missing video gracefully."""
        from app.agents.video_assembler import _generate_thumbnail

        with tempfile.TemporaryDirectory() as tmpdir:
            non_existent_video = Path(tmpdir) / "missing.mp4"
            out_thumb = Path(tmpdir) / "thumb.jpg"

            # Should not raise, should fall back to bumper
            _generate_thumbnail(non_existent_video, out_thumb, "Test Title")
            # If no bumper exists either, thumbnail just won't exist — that's OK

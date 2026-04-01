"""Tests for Replicate MusicGen music generation — mock API."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.tools.music_gen import generate_music


class TestInputValidation:
    @pytest.mark.asyncio
    async def test_empty_prompt_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            await generate_music("", Path("/tmp"))

    @pytest.mark.asyncio
    async def test_long_prompt_raises(self):
        with pytest.raises(ValueError, match="too long"):
            await generate_music("x" * 1001, Path("/tmp"))

    @pytest.mark.asyncio
    async def test_duration_too_low_raises(self):
        with pytest.raises(ValueError, match="Duration must be"):
            await generate_music("test", Path("/tmp"), duration=0)

    @pytest.mark.asyncio
    async def test_duration_too_high_raises(self):
        with pytest.raises(ValueError, match="Duration must be"):
            await generate_music("test", Path("/tmp"), duration=31)

    @pytest.mark.asyncio
    async def test_valid_duration_range(self):
        """Duration 1-30 should not raise."""
        for d in [1, 15, 30]:
            with patch("app.tools.music_gen.replicate.async_run", new_callable=AsyncMock, return_value=None):
                result = await generate_music("test", Path("/tmp"), duration=d)
                assert result is None  # None because mock returns None


class TestMusicDownload:
    @pytest.mark.asyncio
    async def test_downloads_and_saves_audio(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            fake_audio = b"RIFF" + b"\x00" * 100  # fake wav header

            with patch("app.tools.music_gen.replicate.async_run", new_callable=AsyncMock, return_value="https://example.com/music.wav"):
                mock_response = httpx.Response(
                    status_code=200,
                    content=fake_audio,
                    headers={"content-type": "audio/wav"},
                    request=httpx.Request("GET", "https://example.com/music.wav"),
                )
                with patch("app.tools.music_gen.httpx.AsyncClient") as mock_client_cls:
                    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_cls.return_value)
                    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
                    mock_client_cls.return_value.get = AsyncMock(return_value=mock_response)

                    result = await generate_music("ambient electronic", output_dir, duration=8)

            assert result is not None
            assert result.exists()
            assert result.read_bytes() == fake_audio

    @pytest.mark.asyncio
    async def test_rejects_non_audio_content_type(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            with patch("app.tools.music_gen.replicate.async_run", new_callable=AsyncMock, return_value="https://example.com/file.html"):
                mock_response = httpx.Response(
                    status_code=200,
                    content=b"<html>not audio</html>",
                    headers={"content-type": "text/html"},
                    request=httpx.Request("GET", "https://example.com/file.html"),
                )
                with patch("app.tools.music_gen.httpx.AsyncClient") as mock_client_cls:
                    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_cls.return_value)
                    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
                    mock_client_cls.return_value.get = AsyncMock(return_value=mock_response)

                    result = await generate_music("test", output_dir)

            assert result is None


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_replicate_failure_returns_none(self):
        with patch("app.tools.music_gen.replicate.async_run", new_callable=AsyncMock, side_effect=Exception("API error")):
            result = await generate_music("test", Path("/tmp"))
        assert result is None

    @pytest.mark.asyncio
    async def test_no_url_in_response(self):
        with patch("app.tools.music_gen.replicate.async_run", new_callable=AsyncMock, return_value=None):
            result = await generate_music("test", Path("/tmp"))
        assert result is None

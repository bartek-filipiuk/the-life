"""Tests for Replicate Flux image generation — mock API."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.tools.image_gen import generate_image


class TestInputValidation:
    @pytest.mark.asyncio
    async def test_empty_prompt_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            await generate_image("", Path("/tmp"))

    @pytest.mark.asyncio
    async def test_whitespace_prompt_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            await generate_image("   ", Path("/tmp"))

    @pytest.mark.asyncio
    async def test_long_prompt_raises(self):
        with pytest.raises(ValueError, match="too long"):
            await generate_image("x" * 1001, Path("/tmp"))

    @pytest.mark.asyncio
    async def test_max_length_prompt_ok(self):
        """Prompt of exactly 1000 chars should not raise."""
        prompt = "x" * 1000
        with patch("app.tools.image_gen.replicate.async_run", new_callable=AsyncMock, return_value=None):
            result = await generate_image(prompt, Path("/tmp"))
            assert result is None  # None because mock returns None


class TestImageDownload:
    @pytest.mark.asyncio
    async def test_downloads_and_saves_image(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            fake_image = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

            with patch("app.tools.image_gen.replicate.async_run", new_callable=AsyncMock, return_value=["https://example.com/image.png"]):
                mock_response = httpx.Response(
                    status_code=200,
                    content=fake_image,
                    headers={"content-type": "image/png"},
                    request=httpx.Request("GET", "https://example.com/image.png"),
                )
                with patch("app.tools.image_gen.httpx.AsyncClient") as mock_client_cls:
                    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_cls.return_value)
                    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
                    mock_client_cls.return_value.get = AsyncMock(return_value=mock_response)

                    result = await generate_image("a beautiful sunset", output_dir)

            assert result is not None
            assert result.exists()
            assert result.read_bytes() == fake_image

    @pytest.mark.asyncio
    async def test_rejects_non_image_content_type(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            with patch("app.tools.image_gen.replicate.async_run", new_callable=AsyncMock, return_value=["https://example.com/file.txt"]):
                mock_response = httpx.Response(
                    status_code=200,
                    content=b"not an image",
                    headers={"content-type": "text/plain"},
                    request=httpx.Request("GET", "https://example.com/file.txt"),
                )
                with patch("app.tools.image_gen.httpx.AsyncClient") as mock_client_cls:
                    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_cls.return_value)
                    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
                    mock_client_cls.return_value.get = AsyncMock(return_value=mock_response)

                    result = await generate_image("test", output_dir)

            assert result is None


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_replicate_failure_returns_none(self):
        with patch("app.tools.image_gen.replicate.async_run", new_callable=AsyncMock, side_effect=Exception("API error")):
            result = await generate_image("test", Path("/tmp"))
        assert result is None

    @pytest.mark.asyncio
    async def test_no_url_in_response(self):
        with patch("app.tools.image_gen.replicate.async_run", new_callable=AsyncMock, return_value=[]):
            result = await generate_image("test", Path("/tmp"))
        assert result is None

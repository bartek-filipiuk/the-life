"""Replicate MusicGen music generation wrapper.

Security: prompt and duration validated, downloads to controlled directory,
content-type verified as audio.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx
import replicate

logger = logging.getLogger(__name__)

MAX_PROMPT_LENGTH = 1000
MAX_DURATION = 30  # seconds
DOWNLOAD_TIMEOUT = 60.0
ALLOWED_CONTENT_TYPES = {"audio/mpeg", "audio/wav", "audio/ogg", "audio/flac", "application/octet-stream"}
# MusicGen model on Replicate
MUSICGEN_MODEL = "meta/musicgen:671ac645ce5e552cc63a54a2bbff63fcf798043ac7f315f3f0f32d2fc4b76dcc"


async def generate_music(
    prompt: str,
    output_dir: Path,
    duration: int = 8,
    filename: str = "music.wav",
    timeout: float = DOWNLOAD_TIMEOUT,
) -> Path | None:
    """Generate music using MusicGen on Replicate.

    Args:
        prompt: Music description (max 1000 chars).
        output_dir: Directory to save the audio.
        duration: Duration in seconds (1-30).
        filename: Output filename.
        timeout: Download timeout in seconds.

    Returns:
        Path to saved audio, or None on failure.

    Raises:
        ValueError: If prompt is empty/too long or duration out of range.
    """
    prompt = prompt.strip()
    if not prompt:
        raise ValueError("Music prompt cannot be empty")
    if len(prompt) > MAX_PROMPT_LENGTH:
        raise ValueError(f"Music prompt too long ({len(prompt)} > {MAX_PROMPT_LENGTH})")
    if not 1 <= duration <= MAX_DURATION:
        raise ValueError(f"Duration must be 1-{MAX_DURATION} seconds, got {duration}")

    try:
        output = await replicate.async_run(
            MUSICGEN_MODEL,
            input={
                "prompt": prompt,
                "duration": duration,
                "model_version": "stereo-melody-large",
            },
        )

        audio_url = _extract_url(output)
        if not audio_url:
            logger.error("No audio URL in Replicate response")
            return None

        return await _download_audio(audio_url, output_dir, filename, timeout)

    except Exception:
        logger.exception("Music generation failed")
        return None


def _extract_url(output: Any) -> str | None:
    """Extract URL from Replicate output."""
    if isinstance(output, str):
        return output
    if hasattr(output, "url"):
        return str(output.url)
    if hasattr(output, "read"):
        return str(output)
    return None


async def _download_audio(
    url: str,
    output_dir: Path,
    filename: str,
    timeout: float,
) -> Path | None:
    """Download audio from URL, verify content-type, save to disk."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / filename

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "").split(";")[0].strip()
        if content_type not in ALLOWED_CONTENT_TYPES:
            logger.error("Unexpected content-type: %s (expected audio)", content_type)
            return None

        output_path.write_bytes(response.content)
        logger.info("Audio saved: %s (%d bytes)", output_path, len(response.content))
        return output_path

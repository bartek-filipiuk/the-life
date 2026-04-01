"""Replicate Flux image generation wrapper.

Security: prompt length validated, downloads to controlled directory,
content-type verified as image.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx
import replicate

logger = logging.getLogger(__name__)

MAX_PROMPT_LENGTH = 1000
DOWNLOAD_TIMEOUT = 30.0
ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}
# Flux model on Replicate
FLUX_MODEL = "black-forest-labs/flux-schnell"


async def generate_image(
    prompt: str,
    output_dir: Path,
    filename: str = "image.webp",
    timeout: float = DOWNLOAD_TIMEOUT,
) -> Path | None:
    """Generate an image using Flux on Replicate.

    Args:
        prompt: Image description (max 1000 chars).
        output_dir: Directory to save the image.
        filename: Output filename.
        timeout: Download timeout in seconds.

    Returns:
        Path to saved image, or None on failure.

    Raises:
        ValueError: If prompt is empty or too long.
    """
    prompt = prompt.strip()
    if not prompt:
        raise ValueError("Image prompt cannot be empty")
    if len(prompt) > MAX_PROMPT_LENGTH:
        raise ValueError(f"Image prompt too long ({len(prompt)} > {MAX_PROMPT_LENGTH})")

    try:
        output = await replicate.async_run(
            FLUX_MODEL,
            input={"prompt": prompt, "num_outputs": 1},
        )

        # Replicate returns a list of FileOutput or URLs
        image_url = _extract_url(output)
        if not image_url:
            logger.error("No image URL in Replicate response")
            return None

        return await _download_image(image_url, output_dir, filename, timeout)

    except Exception:
        logger.exception("Image generation failed")
        return None


def _extract_url(output: Any) -> str | None:
    """Extract URL from Replicate output (handles various formats)."""
    if isinstance(output, list) and output:
        item = output[0]
        if isinstance(item, str):
            return item
        if hasattr(item, "url"):
            return str(item.url)
        if hasattr(item, "read"):
            # FileOutput — get URL
            return str(item)
    if isinstance(output, str):
        return output
    return None


async def _download_image(
    url: str,
    output_dir: Path,
    filename: str,
    timeout: float,
) -> Path | None:
    """Download image from URL, verify content-type, save to disk."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / filename

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "").split(";")[0].strip()
        if content_type not in ALLOWED_CONTENT_TYPES:
            logger.error("Unexpected content-type: %s (expected image)", content_type)
            return None

        output_path.write_bytes(response.content)
        logger.info("Image saved: %s (%d bytes)", output_path, len(response.content))
        return output_path

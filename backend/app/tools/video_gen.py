"""Video generation via Replicate.

Security: validates prompt length, downloads to controlled directory,
verifies content-type is video.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
import replicate

logger = logging.getLogger(__name__)

ALLOWED_CONTENT_TYPES = {"video/mp4", "video/webm", "video/quicktime", "application/octet-stream"}
MAX_PROMPT_LENGTH = 1000
DOWNLOAD_TIMEOUT = 120.0  # videos can be large


async def generate_video(
    prompt: str,
    output_dir: Path,
    model: str = "",
    duration: int = 5,
) -> Path | None:
    """Generate a short video clip via Replicate.

    Returns the local file path on success, None on failure.
    """
    if not prompt or len(prompt) > MAX_PROMPT_LENGTH:
        logger.warning("Video prompt invalid (empty or >%d chars)", MAX_PROMPT_LENGTH)
        return None

    if not model:
        logger.warning("No video model configured, skipping generation")
        return None

    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        output = await replicate.async_run(
            model,
            input={
                "prompt": prompt[:MAX_PROMPT_LENGTH],
                "duration": min(max(duration, 1), 10),
            },
        )

        # Replicate returns URL or list of URLs
        video_url = output if isinstance(output, str) else (output[0] if output else None)
        if not video_url:
            logger.error("No video URL returned from Replicate")
            return None

        # Download
        async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT) as client:
            resp = await client.get(video_url)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "").split(";")[0].strip()
            if content_type not in ALLOWED_CONTENT_TYPES:
                logger.error("Unexpected content-type for video: %s", content_type)
                return None

            ext = "mp4"
            if "webm" in content_type:
                ext = "webm"

            file_path = output_dir / f"video.{ext}"
            file_path.write_bytes(resp.content)
            logger.info("Video saved: %s (%d bytes)", file_path, len(resp.content))
            return file_path

    except Exception:
        logger.exception("Video generation failed")
        return None

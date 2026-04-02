"""Generic HTTP wrapper for custom API endpoints.

Allows admin to register arbitrary APIs (e.g., YouTube-to-article, custom search)
that the AI can call as tools during cycles.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TIMEOUT = 30.0


@dataclass
class CustomAPIResult:
    """Result from a custom API call."""

    success: bool
    data: Any = None
    error: str | None = None


async def call_custom_api(
    endpoint_url: str,
    input_data: str,
    method: str = "POST",
    headers: dict[str, str] | None = None,
) -> CustomAPIResult:
    """Call a custom HTTP API endpoint.

    Args:
        endpoint_url: Full URL to call.
        input_data: Input string to send (as JSON body or query param).
        method: HTTP method (GET or POST).
        headers: Optional extra headers.
    """
    if not endpoint_url:
        return CustomAPIResult(success=False, error="No endpoint URL configured")

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            if method.upper() == "GET":
                resp = await client.get(
                    endpoint_url,
                    params={"input": input_data},
                    headers=headers or {},
                )
            else:
                resp = await client.post(
                    endpoint_url,
                    json={"input": input_data},
                    headers={"Content-Type": "application/json", **(headers or {})},
                )

            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "json" in content_type:
                data = resp.json()
            else:
                data = resp.text

            return CustomAPIResult(success=True, data=data)

    except httpx.HTTPStatusError as e:
        logger.error("Custom API returned %d: %s", e.response.status_code, endpoint_url)
        return CustomAPIResult(success=False, error=f"HTTP {e.response.status_code}")
    except Exception as e:
        logger.exception("Custom API call failed: %s", endpoint_url)
        return CustomAPIResult(success=False, error=str(e))

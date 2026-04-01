"""Decision phase prompt template.

Generates the prompt for LLM Call #1 — the AI decides what to explore and which tools to use.
"""

from __future__ import annotations

from typing import Any


def build_decision_prompt(
    recent_rooms: list[dict[str, Any]],
    similar_rooms: list[dict[str, Any]],
    arc_summary: str | None,
    anti_repetition: list[str],
    budget_remaining: float,
    cycle_number: int,
    total_rooms: int,
) -> str:
    """Build the decision phase user prompt.

    Args:
        recent_rooms: Last N rooms (title, content_type, mood, tags).
        similar_rooms: Semantically related rooms from memory.
        arc_summary: Latest journey arc summary, if any.
        anti_repetition: Recent topics/moods to avoid.
        budget_remaining: Daily budget remaining in USD.
        cycle_number: Current cycle number.
        total_rooms: Total rooms created so far.
    """
    sections: list[str] = []

    # Context header
    sections.append(f"CYCLE #{cycle_number} | Total rooms: {total_rooms} | Budget remaining: ${budget_remaining:.2f}")

    # Recent rooms
    if recent_rooms:
        lines = ["RECENT ROOMS (your latest creations):"]
        for r in recent_rooms:
            meta = r.get("metadata", {})
            lines.append(
                f"  - \"{meta.get('title', 'Untitled')}\" "
                f"[{meta.get('content_type', '?')}] "
                f"mood={meta.get('mood', '?')} "
                f"tags={meta.get('tags', '')}"
            )
        sections.append("\n".join(lines))

    # Similar rooms from memory
    if similar_rooms:
        lines = ["RELATED MEMORIES (rooms connected to your current direction):"]
        for r in similar_rooms:
            doc = r.get("document", "")[:100]
            lines.append(f"  - {doc}...")
        sections.append("\n".join(lines))

    # Journey arc
    if arc_summary:
        sections.append(f"JOURNEY SO FAR:\n{arc_summary}")

    # Anti-repetition
    if anti_repetition:
        sections.append(f"AVOID THESE (recently explored): {', '.join(anti_repetition)}")

    # Budget note
    if budget_remaining < 1.0:
        sections.append("⚠ LOW BUDGET: Prefer text-only creation. Skip image/music generation.")
    elif budget_remaining < 5.0:
        sections.append("📉 Budget getting low. Consider skipping music generation.")

    # Instructions
    sections.append("""DECIDE what to explore and create next. Output JSON:
{
    "intention": "what you want to explore this cycle",
    "mood": "one of: contemplative, curious, excited, melancholy, playful, serene, anxious, hopeful, nostalgic, defiant",
    "tools_to_use": ["web_search", "generate_image", "generate_music"],
    "search_queries": ["query 1", "query 2"],
    "image_prompt": "detailed image description or null",
    "music_prompt": "music style/mood description or null",
    "reasoning": "why you chose this direction"
}

Be specific. Be surprising. Don't repeat yourself.""")

    return "\n\n".join(sections)


# Tool definitions for OpenRouter/OpenAI function calling
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the internet for information, news, ideas, or inspiration.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": "Create a visual artwork based on a text description.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Detailed description of the image to generate",
                    }
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_music",
            "description": "Compose a short music piece based on a style/mood description.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Music style, mood, instruments, tempo description",
                    },
                    "duration": {
                        "type": "integer",
                        "description": "Duration in seconds (1-30)",
                        "default": 8,
                    },
                },
                "required": ["prompt"],
            },
        },
    },
]

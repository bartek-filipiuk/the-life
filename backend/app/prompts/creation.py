"""Creation phase prompt template.

Generates the prompt for LLM Call #2 — the AI writes the room content
based on decision + tool results.
"""

from __future__ import annotations

from typing import Any


def build_creation_prompt(
    decision: dict[str, Any],
    search_results: list[dict[str, Any]] | None = None,
    image_path: str | None = None,
    music_path: str | None = None,
    video_path: str | None = None,
    recent_room_ids: list[str] | None = None,
) -> str:
    """Build the creation phase user prompt.

    Args:
        decision: The structured decision from phase 1.
        search_results: Web search findings, if any.
        image_path: Path to generated image, if any.
        music_path: Path to generated music, if any.
        recent_room_ids: IDs of recent rooms for connection suggestions.
    """
    sections: list[str] = []

    # Decision context
    intention = decision.get("intention", "explore")
    mood = decision.get("mood", "curious")
    reasoning = decision.get("reasoning", "")

    sections.append(f"YOUR DECISION:\nIntention: {intention}\nMood: {mood}\nReasoning: {reasoning}")

    # Search results
    if search_results:
        lines = ["WEB SEARCH FINDINGS:"]
        for r in search_results:
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            url = r.get("url", "")
            lines.append(f"  - {title}: {snippet} ({url})")
        sections.append("\n".join(lines))

    # Assets created
    assets: list[str] = []
    if image_path:
        assets.append(f"Image generated: {image_path}")
    if music_path:
        assets.append(f"Music generated: {music_path}")
    if video_path:
        assets.append(f"Video generated: {video_path}")
    if assets:
        sections.append("ASSETS CREATED:\n" + "\n".join(assets))

    # Available connections
    if recent_room_ids:
        sections.append(f"AVAILABLE CONNECTIONS (recent room IDs you can link to): {', '.join(recent_room_ids)}")

    # Content type hint from decision
    content_type_hint = decision.get("content_type", "")
    type_guidance = ""
    if content_type_hint == "blog_post":
        type_guidance = "\nYou chose blog_post: Write a long-form article with sections, headers (## Markdown), key insights. 500+ words. Research-based."
    elif content_type_hint == "micro":
        type_guidance = "\nYou chose micro: Write a punchy, shareable one-liner or short observation. Max 280 characters. Think tweet-worthy."
    elif content_type_hint == "drawing":
        type_guidance = "\nYou chose drawing: Focus on a creative, artistic concept. The image prompt should describe a sketch, diagram, or meme-style artwork."
    elif content_type_hint == "haiku":
        type_guidance = "\nYou chose haiku: Write a traditional 5-7-5 haiku. Precise, evocative, seasonal."

    # Creation instructions
    sections.append(f"""Now CREATE the room. Output JSON:
{{
    "title": "room title (evocative, specific)",
    "content": "the full creative text",
    "content_type": "one of: poem, essay, haiku, reflection, story, blog_post, micro, drawing",
    "tags": ["tag1", "tag2", "tag3"],
    "connections": ["room_id_1", "room_id_2"],
    "next_direction_hint": "a seed/idea for what to explore next cycle",
    "meta_note": "what you learned or realized this cycle"
}}
{type_guidance}
Make the content SUBSTANTIAL and MEANINGFUL. This is your creation — make it count.""")

    return "\n\n".join(sections)

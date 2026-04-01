"""Search provider factory.

Creates the correct search provider based on configuration.
Supports: 'brave', 'tavily'. Extensible for future providers.
"""

from __future__ import annotations

from app.tools.search_provider import SearchProvider, SearchProviderError


def create_search_provider(
    provider_name: str,
    api_key: str,
    **kwargs,
) -> SearchProvider:
    """Create a search provider by name.

    Args:
        provider_name: One of 'brave', 'tavily'.
        api_key: API key for the provider.
        **kwargs: Provider-specific options (e.g., search_depth for Tavily).

    Returns:
        A SearchProvider instance.

    Raises:
        SearchProviderError: If provider_name is unknown.
        ValueError: If api_key is missing.
    """
    name = provider_name.lower().strip()

    if name == "brave":
        from app.tools.brave_search import BraveSearchProvider
        return BraveSearchProvider(api_key=api_key)

    if name == "tavily":
        from app.tools.tavily_search import TavilySearchProvider
        return TavilySearchProvider(
            api_key=api_key,
            search_depth=kwargs.get("search_depth", "basic"),
            include_answer=kwargs.get("include_answer", False),
        )

    raise SearchProviderError(
        f"Unknown search provider: '{name}'. Supported: brave, tavily. "
        f"See docs/adding-tools.md for how to add new providers."
    )

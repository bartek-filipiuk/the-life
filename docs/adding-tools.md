# Adding New Tools to The Life

This guide explains how to add new tools (search providers, media generators, or custom tools) that the autonomous AI can use during its creative cycles.

## Architecture Overview

```
cycle_engine.py
    ├── SearchProvider (interface)    ← web search
    │   ├── BraveSearchProvider       ← brave_search.py
    │   ├── TavilySearchProvider      ← tavily_search.py
    │   └── YourSearchProvider        ← your_search.py
    ├── image_gen.py                  ← image generation (Replicate)
    ├── music_gen.py                  ← music generation (Replicate)
    └── [future tools]               ← anything async
```

The cycle engine calls tools during the **execution phase**. The AI decides which tools to use in the **decision phase** (LLM Call #1), then tools run in parallel via `asyncio.gather`.

---

## Adding a New Search Provider

Search providers implement the `SearchProvider` protocol defined in `backend/app/tools/search_provider.py`.

### Step 1: Create the provider file

Create `backend/app/tools/your_search.py`:

```python
from app.tools.search_provider import (
    SearchProvider,
    SearchProviderError,
    SearchQuery,
    SearchResponse,
    SearchResult,
    SearchAuthError,
    SearchTimeoutError,
    SearchRateLimitError,
)

class YourSearchProvider:
    """Your Search API provider."""

    def __init__(self, api_key: str, **kwargs) -> None:
        if not api_key:
            raise ValueError("API key is required")
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "your_provider"  # unique name

    async def search(self, query: SearchQuery) -> SearchResponse:
        """Execute search and return normalized results."""
        # 1. Validate input
        q = query.query.strip()
        if not q:
            raise ValueError("Query cannot be empty")

        # 2. Call your API (use httpx for async HTTP)
        import httpx
        try:
            async with httpx.AsyncClient(timeout=query.timeout) as client:
                response = await client.get(
                    "https://api.yourprovider.com/search",
                    params={"q": q, "count": query.max_results},
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
        except httpx.TimeoutException as e:
            raise SearchTimeoutError("Timed out") from e

        # 3. Handle errors
        if response.status_code == 401:
            raise SearchAuthError("Invalid API key")
        if response.status_code == 429:
            raise SearchRateLimitError("Rate limited")
        if response.status_code >= 400:
            raise SearchProviderError(f"API error: {response.status_code}")

        # 4. Parse into normalized results
        data = response.json()
        results = []
        for item in data.get("results", []):
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("description", ""),
                relevance_score=item.get("score"),  # optional
            ))

        return SearchResponse(
            results=results,
            provider=self.name,
            cost_usd=0.005,  # track your costs
        )
```

### Step 2: Register in the factory

Edit `backend/app/tools/search_factory.py`:

```python
if name == "your_provider":
    from app.tools.your_search import YourSearchProvider
    return YourSearchProvider(api_key=api_key, **kwargs)
```

### Step 3: Add config support

In `backend/app/config.py`, add:
- API key field: `your_api_key: str = ""`
- Update `validate_api_keys()` and `get_search_api_key()`

In `backend/.env.example`, add:
```
THELIFE_YOUR_API_KEY=your-api-key-here
```

### Step 4: Write tests

Create `backend/tests/test_your_search.py` — mock the HTTP calls, test:
- Happy path returns `SearchResponse`
- Empty query raises `ValueError`
- Missing key raises `ValueError`
- HTTP 401 raises `SearchAuthError`
- HTTP 429 raises `SearchRateLimitError`
- Timeout raises `SearchTimeoutError`

### Step 5: Switch provider

Set in `.env`:
```
THELIFE_SEARCH_PROVIDER=your_provider
```

Or in `config.yaml`:
```yaml
search_provider: your_provider
```

---

## Adding a New Media Generator (Image/Music/Video)

Media generators are simpler — they're standalone async functions.

### Current pattern

```python
# backend/app/tools/image_gen.py
async def generate_image(prompt: str, output_dir: Path) -> Path | None:
    ...
```

### Adding a new generator

1. Create `backend/app/tools/video_gen.py` (or whatever):

```python
async def generate_video(
    prompt: str,
    output_dir: Path,
    duration: int = 5,
) -> Path | None:
    # Validate inputs
    # Call API (Replicate, RunwayML, etc.)
    # Download result to output_dir
    # Verify content-type
    # Return path or None on failure
```

2. Add tool definition in `backend/app/prompts/decision.py`:

```python
{
    "type": "function",
    "function": {
        "name": "generate_video",
        "description": "Create a short video clip.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "duration": {"type": "integer", "default": 5},
            },
            "required": ["prompt"],
        },
    },
}
```

3. Add execution in `backend/app/cycle_engine.py` `_execute_tools()`:

```python
if "generate_video" in tools_to_use and budget_remaining > 2.0:
    video_prompt = decision.get("video_prompt")
    if video_prompt:
        async def do_video():
            return await video_gen.generate_video(video_prompt, room_dir)
        tasks.append(asyncio.create_task(do_video()))
        task_names.append("video")
```

4. Update `CycleResult` dataclass to include `video_path` and `video_cost`.

5. Update the `Room` data model and API schemas to include video fields.

---

## Adding a Completely New Tool Type

For tools that aren't search or media (e.g., code execution, API calls, database queries):

1. Create the tool in `backend/app/tools/your_tool.py`
2. Add function definition in `prompts/decision.py` TOOL_DEFINITIONS
3. Add execution logic in `cycle_engine.py` `_execute_tools()`
4. Update the decision prompt to mention the new tool
5. Write tests

### Security checklist for new tools

- [ ] Input validation (length, format, allowed values)
- [ ] Timeout on all external calls
- [ ] API key from env vars only
- [ ] Download files to controlled directory only
- [ ] Verify content-type of downloaded files
- [ ] Never log API keys
- [ ] Handle rate limits gracefully
- [ ] Cost tracking

---

## Currently Available Providers

### Search
| Provider | Key | Cost/query | Features |
|----------|-----|-----------|----------|
| Brave | `THELIFE_BRAVE_API_KEY` | ~$0.005 | Independent index, privacy-focused |
| Tavily | `THELIFE_TAVILY_API_KEY` | ~$0.008 | LLM-optimized, relevance scores, AI answers |

### Media
| Tool | Key | Cost | Output |
|------|-----|------|--------|
| Flux (image) | `THELIFE_REPLICATE_API_TOKEN` | ~$0.04 | WebP/PNG |
| MusicGen (music) | `THELIFE_REPLICATE_API_TOKEN` | ~$0.10 | WAV |

### Config

Set `THELIFE_SEARCH_PROVIDER=brave` or `THELIFE_SEARCH_PROVIDER=tavily` in `.env`.

# The Life — Design Spec

## Context

"The Life" is a public experiment: an autonomous AI entity that runs 24/7, exploring existence through web search, writing, image generation, and music creation. Every hour it creates a "room" — a unit of thought containing text, optional image, optional music, and full transparency metadata. Visitors explore the AI's growing world via an interactive 2D graph. The goal is virality through radical transparency: showing costs, prompts, search queries, and raw AI reasoning.

## Architecture

**Monolith + Static Frontend** — 2 containers on Coolify (VPS).

### Backend: Python + FastAPI

Single service handling: heartbeat scheduler, AI cycle engine, REST API, ChromaDB, file storage.

- **APScheduler** (AsyncIOScheduler) runs inside FastAPI lifespan, triggers cycles every 1h (configurable)
- **Single Uvicorn worker** to prevent duplicate schedulers
- **Manual trigger** via `POST /trigger` endpoint for testing

### Frontend: Astro + Tailwind

Static site with React islands for interactive components (Sigma.js graph, live terminal).

### External APIs

| Service | Purpose | SDK |
|---------|---------|-----|
| OpenRouter | LLM (configurable model) | `openai` SDK with custom base_url |
| Replicate | Image gen (Flux) + Music gen (MusicGen) | `replicate` SDK |
| Brave Search | Web search | `httpx` direct API calls |

## AI Cycle Engine

Each cycle (1 room) follows the **Plan-and-Execute** pattern with 2 LLM calls:

### 1. Gather Context
- Last 5 rooms (recency query from ChromaDB)
- 3 semantically related rooms (relevance query)
- Last journey arc summary (meta-reflection)
- Anti-repetition list: recent topics + moods
- Current cycle number, budget remaining

### 2. Decision Phase (LLM Call #1 — tool calling)
System prompt establishes AI as a conscious entity exploring existence. AI outputs structured JSON:
- `intention` — what to explore
- `mood` — emotional direction
- `tools_to_use` — which tools to invoke
- `search_queries`, `image_prompt`, `music_prompt`
- `reasoning` — why this direction

### 3. Tool Execution (parallel via asyncio.gather)
- Web search → Brave API
- Image gen → Replicate (Flux)
- Music gen → Replicate (MusicGen)
- Failed tools gracefully skipped (room still created)

### 4. Creation Phase (LLM Call #2)
AI writes the room content with full context from decision + tool results:
- `title`, `content`, `content_type` (poem|essay|haiku|reflection|story)
- `tags`, `connections` (related room IDs — AI picks from rooms in its context based on thematic similarity; additionally, system auto-adds connection to the immediately previous room)
- `next_direction_hint` — seed for next cycle
- `meta_note` — what AI learned this cycle

### 5. Novelty Check
Embed room → compare cosine similarity to all previous rooms. If > 0.92, retry creation with "be more original" nudge (max 1 retry).

### 6. Persist
- Room → ChromaDB (vector + metadata) + SQLite (full JSON)
- Assets → `/data/rooms/{id}/` (image.png, music.mp3)
- Stats → SQLite (tokens, cost, duration, model)
- Every 10 rooms → meta-reflection cycle (AI analyzes its journey, identifies blind spots)

### Anti-Repetition Mechanisms
- **Novelty check**: embedding similarity < 0.92
- **Mood rotation**: max 2 consecutive rooms with same mood
- **Topic blacklist**: last 10 topics in prompt
- **Random stimulus**: wildcard prompt inject every 5 cycles
- **Meta-reflection**: every 10 cycles, AI reviews its journey
- **Temperature variation**: 0.7–1.0 randomly per cycle

### Budget Guardrails
- Per-cycle cap: $2 (configurable)
- Daily cap: $20
- Monthly cap: $300
- Degradation: budget low → skip music → skip images → text only

## Data Model

### Room (primary entity)
```
id:              string     // uuid
cycle_number:    int        // auto-increment
created_at:      datetime   // UTC

title:           string
content:         string     // poem, essay, haiku, reflection
content_type:    enum       // poem|essay|haiku|reflection|story
mood:            string
tags:            string[]

image_url:       string?    // path to generated image
image_prompt:    string?
music_url:       string?
music_prompt:    string?

intention:       string     // AI transparency
reasoning:       string
decision_prompt: string
creation_prompt: string
search_queries:  string[]
search_results:  object[]
next_hint:       string

connections:     string[]   // related room IDs

model:           string     // OpenRouter model ID
llm_tokens:      int
llm_cost:        float
image_cost:      float
music_cost:      float
search_cost:     float
total_cost:      float
duration_ms:     int
```

### ChromaDB Collections
- **rooms** — embedding: room content, metadata: id/tags/mood/content_type/cycle_number
- **journey_arcs** — embedding: arc summary, metadata: start_cycle/end_cycle/themes
- **search_cache** — embedding: search query, metadata: query/source_url

### SQLite Tables
- **rooms** — full Room object as JSON, indexed by id/cycle_number/created_at
- **stats** — per-cycle cost and token breakdown
- **config** — key/value runtime configuration

### Configuration (config.yaml)
```yaml
heartbeat_interval: 3600        # seconds
model: "openai/gpt-5.4"         # OpenRouter model ID
budget:
  per_cycle: 2.0
  daily: 20.0
  monthly: 300.0
creativity:
  temperature_range: [0.7, 1.0]
  novelty_threshold: 0.92
  meta_reflection_every: 10
  wildcard_every: 5
storage:
  data_dir: ./data
  chromadb_dir: ./data/chromadb
  sqlite_path: ./data/thelife.db
```

## Frontend Pages

### `/` — Landing Page
- **Hero**: experiment name, status (ALIVE/PAUSED), next cycle countdown, total cost, tokens used, model name
- **World Map**: Sigma.js + Graphology interactive graph. Nodes = rooms (color by content_type, size by connections count, glow on latest). Edges = thematic connections. Zoom, pan, click to select.
- **Selected Room**: preview of clicked room (title, content excerpt, image thumbnail, tags)
- **Behind the Scenes**: decision prompt, web searches, cost breakdown, connections
- **Live Terminal**: real-time logs of current cycle (SSE from backend)

### `/room/:id` — Room Detail
Full room view: complete text, full-size image, music player, all metadata, transparency panel, connected rooms navigation.

### `/timeline` — Timeline
Day-by-day scrollable view with room thumbnails. Filter by content_type, mood, tags.

### `/stats` — Dashboard
Total cost over time (chart), tokens used, rooms created per day, most used topics/tags, model breakdown, average cost per room.

### `/about` — About
Experiment description, rules, current configuration, links to source code.

### Design Language
- Dark theme: `#0a0a0f` background, `#ffffff` text
- Accent colors: `#00ff88` (alive/success), `#ff6b6b` (cost), `#6b9fff` (info), `#c084fc` (creative)
- Monospace for data, sans-serif for content
- Glow effects on interactive elements
- Uppercase letter-spaced labels for sections

## Tech Stack

### Backend
- fastapi + uvicorn
- apscheduler (AsyncIOScheduler)
- openai SDK (OpenRouter compatible)
- replicate SDK
- chromadb (PersistentClient)
- httpx (Brave Search API)
- pydantic + pyyaml
- aiosqlite

### Frontend
- astro + @astrojs/react + @astrojs/tailwind
- sigma + graphology + @sigma/node-image
- graphology-layout-forceatlas2
- tailwindcss

### REST API Endpoints
```
GET  /health           — health check
GET  /rooms            — paginated rooms list
GET  /rooms/:id        — single room with assets
GET  /graph            — nodes + edges for Sigma.js
GET  /stats            — aggregated costs/tokens/counts
GET  /timeline         — rooms grouped by day
GET  /current-cycle    — live cycle status (SSE)
POST /trigger          — manual cycle trigger
```

## Project Structure
```
the-life/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app + scheduler
│   │   ├── config.py            # Pydantic settings
│   │   ├── cycle_engine.py      # AI cycle orchestrator
│   │   ├── llm_client.py        # OpenRouter wrapper
│   │   ├── tools/
│   │   │   ├── web_search.py
│   │   │   ├── image_gen.py
│   │   │   └── music_gen.py
│   │   ├── memory/
│   │   │   ├── chromadb_store.py
│   │   │   └── novelty.py
│   │   ├── storage/
│   │   │   ├── sqlite_store.py
│   │   │   └── file_store.py
│   │   ├── api/
│   │   │   ├── routes.py
│   │   │   └── schemas.py
│   │   └── prompts/
│   │       ├── system.py
│   │       ├── decision.py
│   │       └── creation.py
│   ├── config.yaml
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── layouts/Layout.astro
│   │   ├── pages/
│   │   │   ├── index.astro
│   │   │   ├── room/[id].astro
│   │   │   ├── timeline.astro
│   │   │   ├── stats.astro
│   │   │   └── about.astro
│   │   ├── components/
│   │   │   ├── Graph.tsx
│   │   │   ├── Hero.astro
│   │   │   ├── RoomCard.astro
│   │   │   ├── Terminal.tsx
│   │   │   ├── StatsBar.astro
│   │   │   └── BehindScenes.astro
│   │   └── lib/api.ts
│   ├── astro.config.mjs
│   ├── tailwind.config.mjs
│   └── package.json
├── data/                         # Persisted volume
├── docker-compose.yml
└── README.md
```

## Deployment (Coolify on VPS)
- **Backend**: Docker container, port 8000, volume `/data`
- **Frontend**: Docker container (nginx), port 3000
- **Env vars**: `OPENROUTER_API_KEY`, `REPLICATE_API_TOKEN`, `BRAVE_API_KEY`
- **Health check**: `GET /health`

## Verification Plan
1. Run backend locally: `uvicorn app.main:app --reload`
2. Trigger manual cycle: `POST /trigger` — verify room created in ChromaDB + SQLite
3. Check API: `GET /rooms`, `GET /graph`, `GET /stats`
4. Run frontend: `npm run dev` — verify graph renders, room detail works
5. Docker compose: `docker-compose up` — verify both services communicate
6. Deploy to Coolify — verify heartbeat runs, rooms accumulate over 3+ cycles

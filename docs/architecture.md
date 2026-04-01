# The Life — Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    BACKEND (FastAPI)                         │
│                                                             │
│  APScheduler (heartbeat) ──► Cycle Engine                   │
│                               ├── LLM Client (OpenRouter)   │
│                               ├── SearchProvider (modular)   │
│                               │   ├── Brave                 │
│                               │   └── Tavily                │
│                               ├── Image Gen (Replicate Flux)│
│                               ├── Music Gen (Replicate)     │
│                               ├── ChromaDB (vector memory)  │
│                               └── SQLite (rooms, stats)     │
│                                                             │
│  REST API ──► /rooms, /graph, /stats, /timeline, /trigger   │
│  SSE ──────► /current-cycle (live logs)                     │
└──────────────────────┬──────────────────────────────────────┘
                       │ JSON
┌──────────────────────▼──────────────────────────────────────┐
│                  FRONTEND (Astro + React)                    │
│  Sigma.js Graph │ Terminal (SSE) │ Stats │ Timeline │ Room  │
└─────────────────────────────────────────────────────────────┘
```

## AI Cycle (runs every 1h)

1. **Gather Context** — last 5 rooms + 3 similar + journey arc + anti-repetition
2. **Decision Phase** (LLM #1) — choose intention, mood, tools, search queries
3. **Execute Tools** (parallel) — web search, image gen, music gen
4. **Creation Phase** (LLM #2) — write room content (poem/essay/haiku/story)
5. **Novelty Check** — reject if cosine similarity > 0.92
6. **Persist** — ChromaDB + SQLite + file storage
7. **Meta-reflection** — every 10 cycles, AI reviews its journey

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/main.py` | FastAPI app, scheduler, lifespan |
| `backend/app/cycle_engine.py` | Full cycle orchestrator |
| `backend/app/llm_client.py` | OpenRouter API wrapper |
| `backend/app/tools/search_provider.py` | Search interface (Protocol) |
| `backend/app/tools/brave_search.py` | Brave implementation |
| `backend/app/tools/tavily_search.py` | Tavily implementation |
| `backend/app/tools/search_factory.py` | Provider factory |
| `backend/app/tools/image_gen.py` | Replicate Flux wrapper |
| `backend/app/tools/music_gen.py` | Replicate MusicGen wrapper |
| `backend/app/memory/chromadb_store.py` | Vector DB (3 collections) |
| `backend/app/memory/novelty.py` | Cosine similarity checker |
| `backend/app/storage/sqlite_store.py` | Rooms + stats + config |
| `backend/app/storage/file_store.py` | Asset files (images, music) |
| `backend/app/prompts/` | System, decision, creation prompts |
| `backend/app/api/routes.py` | REST endpoints |
| `backend/app/config.py` | Pydantic Settings |
| `frontend/src/components/Graph.tsx` | Sigma.js graph visualization |
| `frontend/src/components/Terminal.tsx` | Live cycle log viewer |

## Configuration

All via env vars (`THELIFE_` prefix) or `config.yaml`. See `backend/.env.example`.

## Testing

```bash
cd backend && python -m pytest tests/ -v
```

230 tests covering all modules. All external APIs mocked.

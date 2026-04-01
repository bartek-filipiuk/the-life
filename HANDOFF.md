# The Life — Build Handoff

> Automated build by Claude Code scheduler. Each task is atomic — implement, test, commit, push.
> Spec: `docs/superpowers/specs/2026-03-31-the-life-design.md`

---

## Stage 1: Backend Scaffolding & Config

- [x] **1.1** Create `backend/pyproject.toml` with all dependencies (fastapi, uvicorn, apscheduler, openai, replicate, chromadb, httpx, pydantic, pyyaml, aiosqlite, pytest, pytest-asyncio, httpx[test])
- [x] **1.2** Create `backend/app/__init__.py` and `backend/app/config.py` — Pydantic Settings loading from `config.yaml` + env vars. **Security: API keys MUST come from env vars only, never from config.yaml. Validate all config values have sane defaults and bounds.**
- [x] **1.3** Create `backend/config.yaml` with default values (heartbeat_interval, model, budget caps, creativity params, storage paths). **Security: no secrets in this file, add comment warning.**
- [x] **1.4** Create `backend/.env.example` with all required env vars (OPENROUTER_API_KEY, REPLICATE_API_TOKEN, BRAVE_API_KEY) — placeholder values only.
- [x] **1.5** **TEST:** Write `backend/tests/test_config.py` — test config loading, env var override, missing required keys raise error, budget bounds validation.

## Stage 2: Storage Layer

- [x] **2.1** Create `backend/app/storage/__init__.py` and `backend/app/storage/sqlite_store.py` — async SQLite wrapper: create tables (rooms, stats, config), CRUD for rooms (insert, get_by_id, list_paginated, list_by_day), stats aggregation (total_cost, total_tokens, cost_per_day). **Security: use parameterized queries only, never string formatting for SQL.**
- [x] **2.2** Create `backend/app/storage/file_store.py` — save/serve assets (images, music) to `data/rooms/{room_id}/`. **Security: validate room_id is valid UUID before path construction to prevent path traversal. Sanitize filenames.**
- [x] **2.3** Create `backend/app/memory/__init__.py` and `backend/app/memory/chromadb_store.py` — ChromaDB PersistentClient wrapper: 3 collections (rooms, journey_arcs, search_cache). Methods: add_room, query_recent(n), query_similar(text, n), add_arc, add_search_result.
- [x] **2.4** Create `backend/app/memory/novelty.py` — embed text via ChromaDB, compare cosine similarity to existing rooms. Return bool (is_novel) + closest match distance.
- [ ] **2.5** **TEST:** Write `backend/tests/test_sqlite_store.py` — test all CRUD operations, pagination, stats aggregation, parameterized queries safety.
- [ ] **2.6** **TEST:** Write `backend/tests/test_chromadb_store.py` — test add/query rooms, similarity search, collection management.
- [ ] **2.7** **TEST:** Write `backend/tests/test_novelty.py` — test novelty check with similar/different texts, threshold behavior.
- [ ] **2.8** **TEST:** Write `backend/tests/test_file_store.py` — test save/load assets, path traversal prevention, invalid UUID rejection.

## Stage 3: External API Clients (Tools)

- [ ] **3.1** Create `backend/app/llm_client.py` — OpenRouter wrapper using openai SDK (base_url="https://openrouter.ai/api/v1"). Methods: decision_call(messages, tools) → structured JSON, creation_call(messages) → room content. Track tokens and cost from response. **Security: validate API key exists before call, handle rate limits with exponential backoff, timeout after 60s.**
- [ ] **3.2** Create `backend/app/tools/__init__.py` and `backend/app/tools/web_search.py` — Brave Search API wrapper. Input: query string. Output: list of {title, url, snippet}. Max 5 results. **Security: sanitize query input, validate response structure, timeout 10s.**
- [ ] **3.3** Create `backend/app/tools/image_gen.py` — Replicate Flux wrapper. Input: prompt string. Output: image URL or local path after download. **Security: validate prompt length < 1000 chars, download to controlled directory only, verify content-type is image.**
- [ ] **3.4** Create `backend/app/tools/music_gen.py` — Replicate MusicGen wrapper. Input: prompt + duration. Output: audio URL or local path. **Security: same as image_gen — validate inputs, controlled download dir, verify content-type.**
- [ ] **3.5** **TEST:** Write `backend/tests/test_llm_client.py` — mock OpenRouter responses, test structured output parsing, cost tracking, error handling (timeout, rate limit, invalid response).
- [ ] **3.6** **TEST:** Write `backend/tests/test_web_search.py` — mock Brave API, test result parsing, empty results, timeout handling.
- [ ] **3.7** **TEST:** Write `backend/tests/test_image_gen.py` — mock Replicate API, test image download, invalid prompt rejection, content-type validation.
- [ ] **3.8** **TEST:** Write `backend/tests/test_music_gen.py` — mock Replicate API, test audio download, duration validation, error handling.

## Stage 4: AI Cycle Engine

- [ ] **4.1** Create `backend/app/prompts/__init__.py`, `backend/app/prompts/system.py` — system prompt establishing AI entity identity. Configurable personality seed.
- [ ] **4.2** Create `backend/app/prompts/decision.py` — decision phase prompt template. Takes: recent rooms, similar rooms, arc summary, anti-repetition list, budget remaining. Returns: structured tool-calling prompt.
- [ ] **4.3** Create `backend/app/prompts/creation.py` — creation phase prompt template. Takes: decision output, tool results, search findings. Returns: room content generation prompt.
- [ ] **4.4** Create `backend/app/cycle_engine.py` — main orchestrator. Full cycle: gather_context → decision_phase → execute_tools (asyncio.gather) → creation_phase → novelty_check → persist. Budget checking before each cycle. Graceful degradation on tool failures. Comprehensive logging per step. **Security: never log full API keys, sanitize any user-influenced data in logs.**
- [ ] **4.5** **TEST:** Write `backend/tests/test_cycle_engine.py` — mock all dependencies, test full cycle happy path, test tool failure graceful degradation, test budget exceeded behavior, test novelty retry, test meta-reflection trigger (every 10 cycles).
- [ ] **4.6** **TEST:** Write `backend/tests/test_prompts.py` — test prompt templates render correctly with various inputs, no injection possible through room content in prompts.

## Stage 5: FastAPI App & API

- [ ] **5.1** Create `backend/app/api/__init__.py`, `backend/app/api/schemas.py` — Pydantic response models (RoomResponse, GraphResponse, StatsResponse, TimelineResponse).
- [ ] **5.2** Create `backend/app/api/routes.py` — REST endpoints: GET /health, GET /rooms, GET /rooms/{id}, GET /graph, GET /stats, GET /timeline, GET /current-cycle (SSE), POST /trigger. **Security: rate limit POST /trigger (1 req/min), validate room_id as UUID, paginate all list endpoints (max 100 per page).**
- [ ] **5.3** Create `backend/app/main.py` — FastAPI app with lifespan (APScheduler setup, ChromaDB init, SQLite init). CORS middleware for frontend origin. Static files serving for assets. **Security: restrict CORS to specific origins, add security headers (X-Content-Type-Options, X-Frame-Options).**
- [ ] **5.4** **TEST:** Write `backend/tests/test_api.py` — test all endpoints with FastAPI TestClient, test pagination, test invalid IDs, test rate limiting on trigger, test CORS headers, test SSE streaming.
- [ ] **5.5** **TEST:** Write `backend/tests/conftest.py` — shared fixtures: test config, temp directories, mock API clients, test database.

## Stage 6: Frontend (Astro + Tailwind + Sigma.js)

- [ ] **6.1** Initialize Astro project in `frontend/` with React and Tailwind integrations. Configure dark theme in `tailwind.config.mjs` with custom colors (#0a0a0f, #00ff88, #ff6b6b, #6b9fff, #c084fc).
- [ ] **6.2** Create `frontend/src/layouts/Layout.astro` — base dark layout with meta tags, navigation (Home, Timeline, Stats, About), footer.
- [ ] **6.3** Create `frontend/src/lib/api.ts` — typed API client for backend (fetch wrapper with error handling, base URL from env).
- [ ] **6.4** Create `frontend/src/components/Hero.astro` + `StatsBar.astro` — hero section with experiment title, status indicator (ALIVE pulse animation), next cycle countdown, live stats (total cost, tokens, rooms, model).
- [ ] **6.5** Create `frontend/src/components/Graph.tsx` — Sigma.js + Graphology React island. Fetch /graph, render force-directed layout. Nodes colored by content_type, sized by connection count, glow on latest. Click → select room. Zoom/pan controls.
- [ ] **6.6** Create `frontend/src/components/RoomCard.astro` + `BehindScenes.astro` — room preview (title, excerpt, image thumb, tags) + transparency panel (prompt, searches, costs, connections).
- [ ] **6.7** Create `frontend/src/components/Terminal.tsx` — React island consuming SSE /current-cycle endpoint. Styled as terminal with timestamps and colored log levels.
- [ ] **6.8** Create `frontend/src/pages/index.astro` — landing page assembling: Hero, StatsBar, Graph, selected RoomCard + BehindScenes, Terminal.
- [ ] **6.9** Create `frontend/src/pages/room/[id].astro` — full room detail: complete text, full image, audio player, all metadata, transparency, connected rooms navigation.
- [ ] **6.10** Create `frontend/src/pages/timeline.astro` — day-by-day scrollable timeline with room thumbnails. Filter by content_type/mood/tags.
- [ ] **6.11** Create `frontend/src/pages/stats.astro` — dashboard: cost chart over time, tokens chart, rooms/day, top tags, model breakdown, avg cost/room.
- [ ] **6.12** Create `frontend/src/pages/about.astro` — experiment description, rules, current config, source code link.

## Stage 7: Docker & Deployment

- [ ] **7.1** Create `backend/Dockerfile` — Python 3.12, install deps, copy app, run uvicorn. **Security: non-root user, no dev deps in production, multi-stage build.**
- [ ] **7.2** Create `frontend/Dockerfile` — Node build stage → nginx serve stage. **Security: non-root nginx, minimal base image.**
- [ ] **7.3** Create `docker-compose.yml` — backend (port 8000) + frontend (port 3000) + shared volume for /data. Environment variables from .env file.
- [ ] **7.4** **INTEGRATION TEST:** docker-compose up, POST /trigger, verify room appears in GET /rooms and GET /graph, verify frontend renders at localhost:3000.

---

## Security Checklist (verify across all stages)
- [ ] All API keys from env vars only, never committed
- [ ] All SQL queries parameterized
- [ ] All file paths validated (no path traversal)
- [ ] All external API calls have timeouts
- [ ] Rate limiting on write endpoints
- [ ] CORS restricted to known origins
- [ ] No secrets in logs
- [ ] Docker runs as non-root
- [ ] Input validation on all public endpoints

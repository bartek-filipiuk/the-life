# The Life — Project Instructions

## Overview
Autonomous AI experiment. Spec: `docs/superpowers/specs/2026-03-31-the-life-design.md`
Build handoff: `HANDOFF.md`

## Tech Stack
- **Backend**: Python 3.12, FastAPI, APScheduler, ChromaDB, SQLite, OpenRouter, Replicate, Brave Search
- **Frontend**: Astro, React (islands), Tailwind CSS, Sigma.js + Graphology
- **Deploy**: Docker Compose, Coolify on VPS

## Code Style
- Python: type hints everywhere, async/await for I/O, pydantic models for data
- TypeScript: strict mode, typed API responses
- Tests: pytest + pytest-asyncio, mock external APIs, no real API calls in tests
- Commits: conventional commits, descriptive messages

## Security Rules
- API keys from env vars ONLY (never config files)
- SQL: parameterized queries only
- File paths: validate UUIDs, prevent path traversal
- External APIs: timeouts on all calls
- Logs: never log secrets
- Docker: non-root user

## Auto-Build Instructions

When running as a scheduled agent, follow this protocol:

1. Read `HANDOFF.md`
2. Find the FIRST unchecked task (`- [ ]`)
3. Read the spec for context: `docs/superpowers/specs/2026-03-31-the-life-design.md`
4. Implement the task following security rules above
5. If the task is a TEST task, run `cd backend && python -m pytest tests/ -v` after writing tests
6. If the task creates code, ensure all existing tests still pass
7. Stage only the files you created/modified (never `git add .`)
8. Commit with descriptive message: `feat(stage-N): description`
9. Mark the task as done in HANDOFF.md: change `- [ ]` to `- [x]`
10. Commit the HANDOFF.md change: `chore: mark task N.M as complete`
11. Push to main: `git push origin main`
12. If tests fail, fix the issue before moving on. Do NOT skip failing tests.
13. If a task depends on previous uncompleted tasks, stop and report.
14. Maximum 2 tasks per session to keep changes reviewable.

## Directory Structure
```
backend/          Python FastAPI backend
  app/            Application code
    api/          REST API routes and schemas
    memory/       ChromaDB and novelty checking
    prompts/      LLM prompt templates
    storage/      SQLite and file storage
    tools/        External API wrappers (search, image, music)
  tests/          pytest tests
frontend/         Astro frontend
  src/
    components/   Astro and React components
    layouts/      Base layouts
    lib/           API client
    pages/        Route pages
data/             Runtime data (ChromaDB, SQLite, assets) — gitignored
```

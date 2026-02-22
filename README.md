# ClawChat Server

Standalone Python FastAPI backend for [ClawChat](../clawchat/) — a privacy-first, self-hosted AI personal assistant.

## Features

- **AI Chat** with SSE streaming and intent classification (16 intents)
- **Dual LLM support** — Ollama native (`/api/chat`) + any OpenAI-compatible API
- **Full CRUD** for todos, calendar events, and memos
- **Today dashboard** — tasks, overdue items, events, inbox count
- **JWT auth** with PIN login and token refresh
- **Admin dashboard API** — server stats, AI config, DB management, activity logs, session control
- **Async throughout** — FastAPI + SQLAlchemy async + aiosqlite

## Quick Start

```bash
cd server
python -m venv venv
source venv/Scripts/activate  # Windows
# source venv/bin/activate    # Linux/Mac
pip install -r requirements.txt
cp .env.example .env          # Edit PIN and AI settings
uvicorn main:app --reload --port 8000
```

API docs at `http://localhost:8000/docs`

## API Endpoints

| Group | Endpoints |
|-------|-----------|
| Auth | `POST /api/auth/login`, `/refresh`, `/logout` |
| Chat | `POST /api/chat/stream` (SSE), `/send` (WS), conversations + message CRUD |
| Todos | `GET/POST /api/todos`, `GET/PATCH/DELETE /api/todos/:id` |
| Events | `GET/POST /api/events`, `GET/PATCH/DELETE /api/events/:id` |
| Memos | `GET/POST /api/memos`, `GET/PATCH/DELETE /api/memos/:id` |
| Search | `GET /api/search?q=...` (FTS5 full-text) |
| Tags | `GET /api/tags` |
| Today | `GET /api/today` |
| Admin | `GET /api/admin/overview`, `/ai`, `/activity`, `/sessions`, `/config`, `/data`; `POST /api/admin/ai/test`, `/db/reindex`, `/db/backup`, `/db/purge`, `/sessions/:id/disconnect` |
| Health | `GET /api/health` |

## Configuration

All settings via environment variables in `.env`. See [docs/devplan.md](docs/devplan.md) for the full reference.

Key settings: `AI_PROVIDER` (`ollama`/`openai`), `AI_BASE_URL`, `AI_MODEL`, `PIN`, `JWT_SECRET`.

## Requirements

- Python >= 3.11
- Ollama running locally (default) or an OpenAI-compatible API endpoint

# ClawChat Server — Development Plan

## Project Overview

ClawChat is a privacy-first, self-hosted AI personal assistant. This repository (`clawchat_server`) is the **standalone Python FastAPI backend**. The frontend lives in a separate `clawchat` repository (Vite + React + TypeScript + Electron).

All data stays on the user's server. The AI layer uses Ollama (local) or any OpenAI-compatible API (OpenAI, Claude via proxy).

---

## Architecture

```
┌─ ClawChat Desktop / Web App (separate repo) ─────────┐
│  Vite + React 18 + TypeScript + Electron               │
│  State: Zustand stores                                  │
│  Comms: REST (axios) + SSE streaming                    │
└────────────────────┬────────────────────────────────────┘
                     │ HTTPS + SSE + WebSocket
┌────────────────────┼────────────────────────────────────┐
│  Self-Hosted Server │  (this repo)                       │
│                                                          │
│  FastAPI Backend (async)                                 │
│  ├── Auth (JWT + PIN)                                    │
│  ├── Routers (chat, todo, calendar, memo, search, today) │
│  ├── Services (ai, orchestrator, intent_classifier,      │
│  │     todo, calendar, memo, search, agent_task,         │
│  │     briefing, reminder, scheduler)                    │
│  ├── SSE Streaming (POST /api/chat/stream)               │
│  ├── WebSocket (WS /ws — orchestrator notifications)     │
│  └── Models & Schemas (SQLAlchemy + Pydantic)            │
│                                                          │
│  SQLite Database (async via aiosqlite)                   │
│  └── conversations, messages, todos, events, memos,      │
│      agent_tasks + FTS5 virtual tables                   │
│                                                          │
│  LLM Provider                                            │
│  ├── Ollama (local — native /api/chat streaming)         │
│  └── OpenAI-compatible API (/v1/chat/completions)        │
└──────────────────────────────────────────────────────────┘
```

---

## Current State (v0.4.0) — Phase A + B + Admin Dashboard Complete

### Server Infrastructure
- FastAPI app with CORS, async lifespan, Pydantic Settings
- Async SQLAlchemy engine with aiosqlite, prefixed UUID IDs
- Custom exception hierarchy (`AppError`, `NotFoundError`, `AIUnavailableError`, `ValidationError`)

### Authentication
- PIN-based login → JWT access + refresh tokens
- `get_current_user` dependency on all endpoints
- WebSocket auth via `?token=` query param

### Chat & Messaging
- Conversation CRUD (create, list paginated, get with messages, archive)
- `POST /api/chat/send` — async AI processing via WebSocket
- `POST /api/chat/stream` — SSE streaming endpoint
- Message CRUD (list, edit, delete)
- Auto-generated conversation titles via LLM

### AI Service
- Dual provider: Ollama native + OpenAI-compatible
- SSE streaming for both providers
- Function calling for intent classification (16 intents)
- Health check per provider

### Orchestrator (all 16 intents wired)
- `general_chat` → LLM streaming with conversation context
- `create_todo`, `query_todos`, `complete_todo`, `update_todo`, `delete_todo` → todo_service
- `create_event`, `query_events`, `update_event`, `delete_event` → calendar_service
- `create_memo`, `query_memos`, `update_memo`, `delete_memo` → memo_service
- `search` → FTS5 full-text search
- `delegate_task` → background agent task execution
- `daily_briefing` → LLM-powered daily summary
- Title-based lookup for update/delete/complete (case-insensitive substring match)

### Search (Phase A)
- SQLite FTS5 virtual tables (messages, todos, events, memos)
- `GET /api/search?q=...&types=...` with BM25 relevance scoring
- Automatic FTS indexing via triggers on INSERT/UPDATE/DELETE

### Agent Tasks & Scheduling (Phase B)
- Agent task execution pipeline (queue → run → complete/fail → WS notify)
- Daily briefing generation (events + todos + overdue → LLM summary)
- Reminder system (event reminders, todo deadlines, overdue alerts, dedup)
- Background scheduler (reminder loop, briefing loop, midnight reset)

### Admin Dashboard
- Admin schemas (`schemas/admin.py`) — 14 Pydantic response/request models
- Admin service (`services/admin_service.py`) — table counts, storage stats, uptime, activity feed, agent task history, module data overview, purge old data, FTS reindex, DB backup
- Admin router (`routers/admin.py`) — 11 endpoints under `/api/admin/*`
- Overview: server stats, table counts, storage stats
- AI config: provider info, available models list, connectivity test
- Activity: recent items feed, agent task history
- Sessions: active WebSocket connections, force disconnect
- Database: FTS5 reindex, timestamped backup, data purge with validation
- Server config: read-only view of all `.env` settings
- Data management: per-module counts with date ranges

### REST Endpoints
- `GET/POST /api/todos`, `GET/PATCH/DELETE /api/todos/:id`
- `GET/POST /api/events`, `GET/PATCH/DELETE /api/events/:id`
- `GET/POST /api/memos`, `GET/PATCH/DELETE /api/memos/:id`
- `GET /api/today` — consolidated dashboard
- `GET /api/search` — FTS5 search
- `GET /api/health` — status + AI connectivity
- `POST /api/notifications/register-token` — push token registration
- `GET /api/admin/overview` — server stats, table counts, storage
- `GET /api/admin/ai` — AI config + available models
- `POST /api/admin/ai/test` — test AI connectivity
- `GET /api/admin/activity` — recent activity + agent task history
- `GET /api/admin/sessions` — active WebSocket connections
- `POST /api/admin/sessions/:id/disconnect` — force disconnect
- `GET /api/admin/config` — read-only server config
- `GET /api/admin/data` — per-module data overview
- `POST /api/admin/db/reindex` — rebuild FTS5 indexes
- `POST /api/admin/db/backup` — create timestamped DB backup
- `POST /api/admin/db/purge` — purge old data

### File Tree (51 source files)

```
clawchat_server/
├── .gitignore
├── README.md
├── docs/
│   └── devplan.md
└── server/
    ├── main.py                    # FastAPI app, lifespan, scheduler startup
    ├── config.py                  # Pydantic Settings from .env
    ├── database.py                # Async SQLAlchemy engine + FTS5 setup
    ├── utils.py                   # Utilities: make_id, serialize/deserialize_tags, apply_model_updates, strip_markdown_fences
    ├── constants.py               # Shared constants (SYSTEM_PROMPT)
    ├── exceptions.py              # AppError hierarchy + error handler
    ├── requirements.txt
    ├── .env.example
    ├── auth/
    │   ├── __init__.py
    │   ├── jwt.py                 # JWT create/verify
    │   └── dependencies.py        # get_current_user dependency
    ├── models/
    │   ├── __init__.py
    │   ├── conversation.py
    │   ├── message.py
    │   ├── todo.py
    │   ├── event.py
    │   ├── memo.py
    │   └── agent_task.py
    ├── schemas/
    │   ├── __init__.py
    │   ├── common.py              # PaginatedResponse
    │   ├── auth.py
    │   ├── chat.py                # SendMessageRequest, MessageEditRequest, conversation/message responses
    │   ├── todo.py
    │   ├── calendar.py
    │   ├── memo.py
    │   ├── search.py
    │   ├── today.py
    │   └── admin.py               # Admin dashboard response/request models
    ├── services/
    │   ├── __init__.py
    │   ├── ai_service.py          # Dual provider (OpenAI + Ollama)
    │   ├── intent_classifier.py   # 16-intent function-calling classifier
    │   ├── orchestrator.py        # Intent routing → service calls
    │   ├── todo_service.py
    │   ├── calendar_service.py
    │   ├── memo_service.py
    │   ├── search_service.py      # FTS5 full-text search
    │   ├── agent_task_service.py  # Background task execution
    │   ├── briefing_service.py    # Daily briefing generation
    │   ├── reminder_service.py    # Event/todo reminder checks
    │   ├── scheduler.py           # Background loops (reminders, briefing)
    │   └── admin_service.py      # Admin: counts, storage, activity, purge, reindex, backup
    ├── ws/
    │   ├── __init__.py
    │   ├── manager.py             # WebSocket ConnectionManager
    │   └── handler.py             # WebSocket message router
    ├── routers/
    │   ├── __init__.py
    │   ├── auth.py
    │   ├── chat.py                # SSE /stream, message CRUD, conversations
    │   ├── todo.py
    │   ├── calendar.py
    │   ├── memo.py
    │   ├── search.py              # FTS5 search endpoint
    │   ├── today.py               # Dashboard aggregation
    │   ├── notifications.py       # Push token registration
    │   └── admin.py              # Admin dashboard (11 endpoints)
    └── data/
        └── clawchat.db            # SQLite database (auto-created)
```

---

## What's Next

### Phase C — Database Migrations & Hardening

- [ ] Add Alembic for migration management
- [ ] Initial migration from current `create_all()` state
- [ ] Token blacklist for proper logout (currently stateless)
- [ ] Rate limiting on auth endpoints
- [ ] Input validation hardening (content length limits, sanitization)
- [ ] Request logging middleware
- [ ] Tests (pytest + httpx AsyncClient for API, pytest-asyncio for services)

### Phase D — Deployment & Polish

- [ ] Docker Compose (server + Ollama)
- [ ] HTTPS setup guide (Tailscale / Caddy reverse proxy)
- [ ] One-command setup script
- [x] Backup/restore tooling for SQLite database *(implemented in admin dashboard — `POST /api/admin/db/backup`)*
- [ ] Production logging configuration

---

## Key Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Architecture | Separate repos | Client and server independently deployable |
| Framework | FastAPI (async) | Async-native, OpenAPI docs, SSE + WS support |
| Database | SQLite + aiosqlite | Single-file, zero-config, sufficient for single-user |
| Search | SQLite FTS5 | No external dependency, BM25 ranking, triggers for auto-indexing |
| ORM | SQLAlchemy 2.0 async | Type-safe, migration-ready |
| Auth | JWT (python-jose) | Stateless, works with web + mobile + WebSocket |
| AI streaming | SSE (primary) + WS (orchestrator) | SSE for client; WS for push notifications |
| AI providers | Ollama native + OpenAI-compatible | Native Ollama avoids proxy; OpenAI compat covers cloud LLMs |
| Intent classification | OpenAI tools/function-calling | Structured output, works with both providers |
| Background tasks | asyncio loops in lifespan | Simple, no external queue for single-user |
| ID format | Prefixed UUIDs | Human-readable (`conv_`, `msg_`, `todo_`, `evt_`, `memo_`, `task_`) |
| Migrations | `create_all()` for now | Alembic deferred to Phase C |

---

## How to Run

```bash
cd server
python -m venv venv
source venv/Scripts/activate  # Windows
# source venv/bin/activate    # Linux/Mac
pip install -r requirements.txt
cp .env.example .env          # Edit PIN, AI settings
uvicorn main:app --reload --port 8000
```

API docs: `http://localhost:8000/docs`

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/clawchat.db` | Async SQLite connection string |
| `JWT_SECRET` | `change-this-...` | Secret key for JWT signing |
| `JWT_EXPIRY_HOURS` | `24` | JWT access token lifetime |
| `PIN` | `123456` | Login PIN |
| `AI_PROVIDER` | `ollama` | `"ollama"` or `"openai"` |
| `AI_BASE_URL` | `http://localhost:11434` | LLM API base URL |
| `AI_API_KEY` | (empty) | API key (required for OpenAI/Claude) |
| `AI_MODEL` | `llama3.2` | Model name |
| `ENABLE_SCHEDULER` | `false` | Enable background scheduler |
| `BRIEFING_TIME` | `08:00` | Daily briefing time (HH:MM) |
| `REMINDER_CHECK_INTERVAL` | `5` | Minutes between reminder checks |
| `DEBUG` | `false` | Enable debug logging |

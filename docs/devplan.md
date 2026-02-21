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
                     │ HTTPS + SSE
┌────────────────────┼────────────────────────────────────┐
│  Self-Hosted Server │  (this repo)                       │
│                                                          │
│  FastAPI Backend (async)                                 │
│  ├── Auth (JWT + PIN)                                    │
│  ├── Routers (chat, todo, calendar, memo, search, today) │
│  ├── Services (ai_service, intent_classifier,            │
│  │            orchestrator, todo, calendar, memo)         │
│  ├── SSE Streaming (POST /api/chat/stream)               │
│  ├── WebSocket (WS /ws — orchestrator notifications)     │
│  └── Models & Schemas (SQLAlchemy + Pydantic)            │
│                                                          │
│  SQLite Database (async via aiosqlite)                   │
│  └── conversations, messages, todos, events, memos,      │
│      agent_tasks                                         │
│                                                          │
│  LLM Provider                                            │
│  ├── Ollama (local — native /api/chat streaming)         │
│  └── OpenAI-compatible API (/v1/chat/completions)        │
└──────────────────────────────────────────────────────────┘
```

---

## Current State (v0.2.0)

### What's Done

#### Server Infrastructure
- [x] FastAPI app with CORS, async lifespan context manager
- [x] Pydantic Settings config from `.env`
- [x] Async SQLAlchemy engine with aiosqlite
- [x] DB tables: conversations, messages, todos, events, memos, agent_tasks
- [x] Prefixed UUID generation (`conv_`, `msg_`, `todo_`, `evt_`, `memo_`, `task_`)
- [x] Custom exception hierarchy (`AppError`, `NotFoundError`, `AIUnavailableError`, `ValidationError`)
- [x] `.gitignore` covering venv, .env, DB, __pycache__
- [x] Scheduler config settings (`enable_scheduler`, `briefing_time`, `reminder_check_interval`, `debug`)

#### Authentication
- [x] PIN-based login → JWT access + refresh tokens
- [x] Token refresh endpoint
- [x] `get_current_user` dependency protecting all endpoints
- [x] WebSocket auth via `?token=` query param

#### Chat & Messaging
- [x] Conversation CRUD (create, list paginated, get with messages, archive)
- [x] `POST /api/chat/send` — send message → 202 accepted, AI processing via BackgroundTasks + WebSocket
- [x] `POST /api/chat/stream` — **SSE streaming endpoint** (saves user msg, streams AI tokens, saves assistant msg)
- [x] `GET /api/chat/conversations/:id/messages` — paginated message listing
- [x] `DELETE /api/chat/conversations/:id/messages/:id` — delete individual message
- [x] `PUT /api/chat/conversations/:id/messages/:id` — edit message content
- [x] Last message preview on conversation list

#### SSE Streaming Protocol
- [x] Client POSTs to `/api/chat/stream` with `{conversation_id, content}`
- [x] Server returns `text/event-stream` with three event types:
  - Meta event: `data: {"conversation_id": "...", "message_id": "..."}`
  - Token events: `data: {"token": "..."}`
  - Done event: `data: [DONE]`
- [x] Assistant message persisted after stream completes (fresh DB session)
- [x] Graceful error handling (error text streamed as token on failure)

#### WebSocket
- [x] `ConnectionManager` with connect/disconnect/send_json
- [x] `stream_to_user()` — sends stream_start → stream_chunk → stream_end
- [x] JWT authentication on connection
- [x] Used by orchestrator for background task results (module actions, intent routing)

#### AI Service
- [x] **Dual provider support**: routes based on `provider` config
  - OpenAI-compatible: `/v1/chat/completions` SSE streaming
  - Ollama native: `/api/chat` NDJSON streaming
- [x] Function calling for intent classification (OpenAI-compatible `/v1/chat/completions` for both providers)
- [x] Health check: Ollama → `/api/tags`, OpenAI → `/v1/models`
- [x] Graceful error handling (ConnectError, Timeout → `AIUnavailableError`)

#### Intent Classification
- [x] 17 intents defined with OpenAI tools/function-calling schema
- [x] Parameter extraction (title, due_date, priority, start_time, location, etc.)
- [x] Falls back to `general_chat` on classification failure

#### Orchestrator
- [x] Routes `general_chat` → LLM streaming with conversation context (last 20 messages)
- [x] Routes module intents → **real service calls** (todo, calendar, memo CRUD)
- [x] Routes `search`, `delegate_task`, `daily_briefing` → stub messages
- [x] Saves all assistant messages to DB with classified intent
- [x] AI unavailable → graceful error message via WS
- [x] Owns its own DB session (not request-scoped)

#### Module Services (Async)
- [x] `todo_service.py` — Full async CRUD, auto-sets `completed_at` on status change
- [x] `calendar_service.py` — Full async CRUD, supports `is_all_day`, `reminder_minutes`, `tags`
- [x] `memo_service.py` — Full async CRUD with title + content + tags

#### Full CRUD Routers
- [x] `GET/POST /api/todos`, `GET/PATCH/DELETE /api/todos/:id` — filterable by status, priority, due_before
- [x] `GET/POST /api/events`, `GET/PATCH/DELETE /api/events/:id` — filterable by date range
- [x] `GET/POST /api/memos`, `GET/PATCH/DELETE /api/memos/:id` — paginated, sorted by updated_at
- [x] `GET /api/today` — consolidated dashboard (today tasks, overdue, events, inbox count, greeting)
- [x] `GET /api/search` — stub (returns empty)
- [x] `POST /api/notifications/register-token` — push token registration

#### Health
- [x] `GET /api/health` — returns status, version, ai_provider, ai_model, ai_connected
- [x] Shows `"degraded"` when AI provider is unreachable

### File Tree (47 source files)

```
clawchat_server/
├── .gitignore
├── README.md
├── docs/
│   └── devplan.md              ← you are here
└── server/
    ├── main.py                 # FastAPI app, lifespan, router wiring
    ├── config.py               # Pydantic Settings from .env
    ├── database.py             # Async SQLAlchemy engine + session factory
    ├── utils.py                # make_id() prefixed UUID helper
    ├── exceptions.py           # AppError hierarchy + error handler
    ├── requirements.txt
    ├── .env.example
    ├── auth/
    │   ├── __init__.py
    │   ├── jwt.py              # JWT create/verify
    │   └── dependencies.py     # get_current_user FastAPI dependency
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
    │   ├── common.py           # PaginatedResponse, ErrorResponse
    │   ├── auth.py
    │   ├── chat.py             # StreamSendRequest, MessageEditRequest, etc.
    │   ├── todo.py
    │   ├── calendar.py
    │   ├── memo.py
    │   └── today.py
    ├── services/
    │   ├── __init__.py
    │   ├── ai_service.py       # Dual provider (OpenAI + Ollama native)
    │   ├── intent_classifier.py
    │   ├── orchestrator.py     # Intent routing → real service calls
    │   ├── todo_service.py     # Async todo CRUD
    │   ├── calendar_service.py # Async event CRUD
    │   └── memo_service.py     # Async memo CRUD
    ├── ws/
    │   ├── __init__.py
    │   ├── manager.py          # WebSocket ConnectionManager
    │   └── handler.py          # WebSocket message router
    ├── routers/
    │   ├── __init__.py
    │   ├── auth.py
    │   ├── chat.py             # SSE /stream, message CRUD, conversations
    │   ├── todo.py             # Full CRUD
    │   ├── calendar.py         # Full CRUD
    │   ├── memo.py             # Full CRUD
    │   ├── search.py           # Stub
    │   ├── today.py            # Dashboard aggregation
    │   └── notifications.py    # Push token registration
    └── data/
        └── clawchat.db         # SQLite database (auto-created)
```

---

## What's Next

### Phase A — Search & Conversation Titles

- [ ] Full-text search via SQLite FTS5 (messages, todos, events, memos)
- [ ] `GET /api/search?q=...&types=...` with relevance scoring
- [ ] Auto-generate conversation titles from first user message (LLM summarization)
- [ ] Wire `search` intent in orchestrator to real FTS queries

### Phase B — Agent Tasks & Scheduling

- [ ] Agent task execution pipeline (queue → run → complete/fail → notify)
- [ ] Daily briefing generation (summarize today's events + pending todos via LLM)
- [ ] Reminder system (check upcoming events/todo deadlines, push notification via WS)
- [ ] Wire `delegate_task` and `daily_briefing` intents to real implementations
- [ ] Background scheduler (APScheduler or asyncio-based)

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
- [ ] Backup/restore tooling for SQLite database
- [ ] Production logging configuration

---

## Key Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Architecture | Separate repos | Client (Electron/web) and server are independently deployable |
| Framework | FastAPI (async) | Async-native, fast, built-in OpenAPI docs, SSE + WebSocket support |
| Database | SQLite + aiosqlite | Single-file, zero-config, sufficient for single-user |
| ORM | SQLAlchemy 2.0 async | Industry standard, type-safe, migration-ready |
| Auth | JWT (python-jose) | Stateless, works with web + mobile + WebSocket |
| AI streaming | SSE (primary) + WebSocket (orchestrator) | SSE is simpler for client consumption; WS kept for push notifications |
| AI providers | Ollama native + OpenAI-compatible | Native Ollama avoids proxy overhead; OpenAI compat covers cloud LLMs |
| Intent classification | OpenAI tools/function-calling | Structured output, works with both Ollama and OpenAI |
| Background processing | FastAPI BackgroundTasks | Simple, no external queue needed for single-user |
| ID format | Prefixed UUIDs | Human-readable, debuggable (`conv_`, `msg_`, `todo_`, `evt_`, `memo_`) |
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

# ClawChat Server — Development Plan

## Project Overview

ClawChat is a privacy-first, self-hosted AI personal assistant with a standalone Python FastAPI backend and a React Native mobile app. All data stays on the user's server. The AI layer uses any OpenAI-compatible API (Ollama for local, OpenAI/Claude for cloud).

---

## Architecture

```
┌─ React Native Mobile App ─────────────────────────────┐
│  Screens: Chat / Assistant / Settings                  │
│  State: Zustand stores                                 │
│  Comms: REST (axios) + WebSocket                       │
└────────────────────┬──────────────────────────────────┘
                     │ HTTPS + WSS
┌────────────────────┼──────────────────────────────────┐
│  Self-Hosted Server │                                  │
│                                                        │
│  FastAPI Backend                                       │
│  ├── Auth (JWT + PIN)                                  │
│  ├── Routers (chat, todo, calendar, memo, search)      │
│  ├── Services (ai_service, intent_classifier,          │
│  │            orchestrator)                             │
│  ├── WebSocket (streaming + real-time)                 │
│  └── Models & Schemas (SQLAlchemy + Pydantic)          │
│                                                        │
│  SQLite Database (async via aiosqlite)                 │
│  └── conversations, messages, todos, events,           │
│      memos, agent_tasks                                │
│                                                        │
│  LLM Provider                                          │
│  └── Ollama (local) or OpenAI-compatible API           │
└────────────────────────────────────────────────────────┘
```

---

## Current State (v0.1.0) — MVP Complete

### What's Done

#### Server Infrastructure
- [x] FastAPI app with CORS, lifespan context manager
- [x] Pydantic Settings config from `.env`
- [x] Async SQLAlchemy engine with aiosqlite
- [x] All 6 database tables with indexes (conversations, messages, todos, events, memos, agent_tasks)
- [x] Prefixed UUID generation (`conv_`, `msg_`, `todo_`, `evt_`, `memo_`, `task_`)
- [x] Custom exception hierarchy with consistent error response format
- [x] `.gitignore` covering venv, .env, DB, __pycache__

#### Authentication
- [x] PIN-based login → JWT access + refresh tokens
- [x] Token refresh endpoint
- [x] `get_current_user` dependency protecting all endpoints
- [x] WebSocket auth via `?token=` query param

#### Chat & Messaging
- [x] Conversation CRUD (create, list paginated, get with messages, archive)
- [x] Send message → 202 accepted, AI processing via BackgroundTasks
- [x] Paginated message listing per conversation
- [x] Last message preview on conversation list

#### WebSocket
- [x] `ConnectionManager` with connect/disconnect/send_json
- [x] `stream_to_user()` — sends stream_start → stream_chunk (per token) → stream_end
- [x] Graceful error handling (sends stream_end on failure so clients don't hang)
- [x] JWT authentication on connection

#### AI Service
- [x] OpenAI-compatible streaming completions via httpx SSE parsing
- [x] Function calling for intent classification
- [x] Health check endpoint (pings `/v1/models`)
- [x] Handles both Ollama and OpenAI API
- [x] Graceful error handling (ConnectError, Timeout → AIUnavailableError)

#### Intent Classification
- [x] 17 intents defined with OpenAI tools/function-calling schema
- [x] Parameter extraction (title, due_date, priority, start_time, location, etc.)
- [x] Falls back to `general_chat` on classification failure

#### Orchestrator
- [x] Routes `general_chat` → LLM streaming with conversation context (last 20 messages)
- [x] Routes module intents → friendly stub responses acknowledging intent + params
- [x] Routes `search`, `delegate_task`, `daily_briefing` → stub messages
- [x] Saves all assistant messages to DB with classified intent
- [x] AI unavailable → graceful error message via WS (no crash)
- [x] Owns its own DB session (not request-scoped)

#### Stub Routers (return empty lists / 501)
- [x] `GET /api/todos`
- [x] `GET /api/events`
- [x] `GET /api/memos`
- [x] `GET /api/search`

#### Health
- [x] `GET /api/health` — returns status, version, ai_provider, ai_model, ai_connected
- [x] Shows `"degraded"` when AI provider is unreachable

### File Tree (39 source files)

```
clawchat_server/
├── .gitignore
├── docs/
│   └── devplan.md
└── server/
    ├── main.py
    ├── config.py
    ├── database.py
    ├── utils.py
    ├── exceptions.py
    ├── requirements.txt
    ├── .env.example
    ├── auth/
    │   ├── __init__.py
    │   ├── jwt.py
    │   └── dependencies.py
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
    │   ├── common.py
    │   ├── auth.py
    │   ├── chat.py
    │   ├── todo.py
    │   ├── calendar.py
    │   └── memo.py
    ├── services/
    │   ├── __init__.py
    │   ├── ai_service.py
    │   ├── intent_classifier.py
    │   └── orchestrator.py
    ├── ws/
    │   ├── __init__.py
    │   ├── manager.py
    │   └── handler.py
    └── routers/
        ├── __init__.py
        ├── auth.py
        ├── chat.py
        ├── todo.py
        ├── calendar.py
        ├── memo.py
        └── search.py
```

---

## What's Next

### Phase A — Module Services (Todo / Calendar / Memo)

Replace stub routers with full CRUD implementations.

#### Todo Service
- [ ] `POST /api/todos` — create todo (with tags as JSON)
- [ ] `GET /api/todos/:id` — get single todo
- [ ] `PATCH /api/todos/:id` — update fields (status, title, priority, due_date)
- [ ] `DELETE /api/todos/:id` — delete todo
- [ ] `GET /api/todos` — filter by status, priority, due_date range, pagination
- [ ] Wire `create_todo` / `query_todos` / `update_todo` / `delete_todo` / `complete_todo` intents in orchestrator to actually create/query DB records
- [ ] Return action cards via WebSocket after creating/completing todos

#### Calendar Service
- [ ] `POST /api/events` — create event
- [ ] `GET /api/events/:id` — get single event
- [ ] `PATCH /api/events/:id` — update event
- [ ] `DELETE /api/events/:id` — delete event
- [ ] `GET /api/events` — filter by date range, pagination
- [ ] Wire `create_event` / `query_events` / `update_event` / `delete_event` intents in orchestrator
- [ ] Return action cards via WebSocket

#### Memo Service
- [ ] `POST /api/memos` — create memo
- [ ] `GET /api/memos/:id` — get single memo
- [ ] `PATCH /api/memos/:id` — update memo
- [ ] `DELETE /api/memos/:id` — delete memo
- [ ] `GET /api/memos` — paginated list sorted by updated_at
- [ ] Wire `create_memo` / `query_memos` / `update_memo` / `delete_memo` intents in orchestrator

### Phase B — Search & Conversation Titles

- [ ] Full-text search using SQLite FTS5 across messages, todos, events, memos
- [ ] `GET /api/search?q=...&types=...` with relevance scoring
- [ ] Auto-generate conversation titles from first user message (LLM summarization or first N words)
- [ ] Wire `search` intent in orchestrator to return actual results

### Phase C — Agent Tasks & Scheduling

- [ ] Agent task execution pipeline (queue → run → complete/fail → notify)
- [ ] Daily briefing generation (summarize today's events + pending todos via LLM)
- [ ] Reminder system (check upcoming events/todo deadlines, push notification via WS)
- [ ] Wire `delegate_task` and `daily_briefing` intents to real implementations
- [ ] Background scheduler (APScheduler or similar)

### Phase D — Database Migrations & Hardening

- [ ] Add Alembic for migration management
- [ ] Initial migration from current `create_all()` state
- [ ] Token blacklist for proper logout (currently stateless)
- [ ] Rate limiting on auth endpoints
- [ ] Input validation hardening (content length limits, sanitization)
- [ ] Request logging middleware
- [ ] Tests (pytest + httpx AsyncClient for API, pytest-asyncio for services)

### Phase E — Mobile App

- [ ] React Native (Expo) project setup
- [ ] Auth flow (server URL + PIN → token storage)
- [ ] Chat screen with streaming text rendering
- [ ] Action card components (todo created, event created, etc.)
- [ ] Todo / Calendar / Memo screens (CRUD via REST API)
- [ ] WebSocket connection manager with auto-reconnect
- [ ] Zustand stores for state management
- [ ] Push notifications for reminders and agent task completion

### Phase F — Deployment & Polish

- [ ] Docker Compose (server + Ollama)
- [ ] HTTPS setup guide (Tailscale / reverse proxy)
- [ ] One-command setup script
- [ ] Home screen widgets (Android + iOS)
- [ ] Voice input support
- [ ] Google Calendar sync (optional)
- [ ] Backup/restore tooling

---

## Key Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Framework | FastAPI | Async, fast, built-in OpenAPI docs, WebSocket support |
| Database | SQLite + aiosqlite | Single-file, zero-config, sufficient for single-user |
| ORM | SQLAlchemy 2.0 async | Industry standard, type-safe, migration support |
| Auth | JWT (python-jose) | Stateless, works well with mobile + WebSocket |
| AI client | httpx async | SSE streaming support, connection pooling |
| Intent classification | OpenAI tools/function-calling | Structured output, works with Ollama |
| Background processing | FastAPI BackgroundTasks | Simple, no external queue needed for MVP |
| ID format | Prefixed UUIDs | Human-readable, debuggable (conv_, msg_, etc.) |
| Migrations | create_all() for now | Alembic deferred to Phase D |

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

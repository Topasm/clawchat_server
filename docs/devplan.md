# AI Secretary — Development Plan

## Strategy: Build on OpenClaw, Not From Scratch

After reviewing OpenClaw's architecture, the smartest approach is **not** to build a standalone server from zero. OpenClaw already provides:

- AI agent runtime with LLM orchestration
- Gateway (WebSocket control plane) for real-time communication
- Skills system (SKILL.md + scripts) for extending capabilities
- Tool system (exec, write, read, browser, etc.)
- Cron jobs and scheduled tasks
- Memory and conversation history
- Multi-channel support (WebChat, Telegram, etc.)

**Our job is to build the missing pieces as OpenClaw skills + a React Native app that talks to the Gateway.**

---

## Revised Architecture

```
┌─ React Native App ─────────────────────────────────┐
│                                                      │
│  Widgets: Todo / Calendar / Memo / Quick AI Input    │
│  Screens: Chat / Todo / Calendar / Memo / Settings   │
│                                                      │
└──────────────────────┬───────────────────────────────┘
                       │
                       │ WebSocket + REST
                       │
┌──────────────────────┼───────────────────────────────┐
│  User's Local Server │                                │
│                      │                                │
│  ┌───────────────────┴──────────────────────────┐    │
│  │            OpenClaw Gateway                   │    │
│  │  (Node.js runtime, agent, tools, memory)      │    │
│  └───────────┬───────────────────────────────────┘    │
│              │                                         │
│  ┌───────────┴───────────────────────────────────┐    │
│  │         Custom Skills (our code)               │    │
│  │                                                │    │
│  │  📋 secretary-todo/     SKILL.md + scripts/    │    │
│  │  📅 secretary-calendar/ SKILL.md + scripts/    │    │
│  │  📝 secretary-memo/     SKILL.md + scripts/    │    │
│  │  🤖 secretary-agent/    SKILL.md + scripts/    │    │
│  │  📊 secretary-api/      SKILL.md + scripts/    │    │
│  └───────────┬───────────────────────────────────┘    │
│              │                                         │
│  ┌───────────┴───────────────────────────────────┐    │
│  │         SQLite (local data store)              │    │
│  │  todos / events / memos / agent_tasks          │    │
│  └────────────────────────────────────────────────┘    │
└────────────────────────────────────────────────────────┘
```

---

## What We Build vs What OpenClaw Provides

| Concern | OpenClaw (already done) | We Build |
|---------|------------------------|----------|
| LLM orchestration | ✅ Agent runtime, model routing, failover | — |
| Conversation | ✅ Memory, session history, context | — |
| Scheduling | ✅ Cron jobs, webhooks | Cron configs for briefing/reminders |
| Real-time comms | ✅ Gateway WebSocket | App ↔ Gateway bridge |
| Todo management | — | Skill + SQLite + scripts |
| Calendar | — (CalDAV skill exists but limited) | Skill + SQLite + Google Cal sync |
| Notes/Memos | — | Skill + SQLite + scripts |
| Auto agent tasks | — | Skill for delegated AI tasks |
| Mobile app | — (WebChat exists, no native app) | React Native app + widgets |
| REST API for app | — | Lightweight API skill/sidecar |

---

## Repository Structure

```
ai-secretary/
├── README.md
├── docs/
│   ├── VISION.md              # Project vision (already written)
│   └── PLAN.md                # This file
│
├── skills/                    # OpenClaw skills (drop into ~/.openclaw/skills/)
│   ├── secretary-todo/
│   │   ├── SKILL.md
│   │   ├── scripts/
│   │   │   ├── todo_service.py    # CRUD operations
│   │   │   └── setup_db.py       # Initialize SQLite tables
│   │   └── references/
│   │       └── schema.md
│   │
│   ├── secretary-calendar/
│   │   ├── SKILL.md
│   │   ├── scripts/
│   │   │   ├── calendar_service.py
│   │   │   └── google_sync.py     # Optional Google Calendar sync
│   │   └── references/
│   │       └── schema.md
│   │
│   ├── secretary-memo/
│   │   ├── SKILL.md
│   │   ├── scripts/
│   │   │   └── memo_service.py
│   │   └── references/
│   │       └── schema.md
│   │
│   ├── secretary-agent/
│   │   ├── SKILL.md               # Auto-task execution skill
│   │   ├── scripts/
│   │   │   ├── task_runner.py
│   │   │   └── briefing.py        # Daily briefing generator
│   │   └── references/
│   │       └── task_types.md
│   │
│   └── secretary-api/
│       ├── SKILL.md
│       └── scripts/
│           └── api_server.py      # Lightweight REST API for mobile app
│
├── app/                       # React Native mobile app
│   ├── package.json
│   ├── src/
│   │   ├── screens/
│   │   ├── components/
│   │   ├── widgets/
│   │   ├── api/
│   │   ├── store/
│   │   └── hooks/
│   ├── android/
│   └── ios/
│
└── docker/                    # Optional Docker setup
    ├── docker-compose.yml     # OpenClaw + skills + DB
    └── Dockerfile
```

**Note**: Skills repo and App repo may be split later if needed. Starting as monorepo for simplicity during development.

---

## Phase 1 — Foundation (Weeks 1–2)

**Goal**: OpenClaw running with basic todo/calendar/memo skills, accessible via WebChat.

### 1.1 OpenClaw Setup
- [ ] Install OpenClaw on local server
- [ ] Configure LLM provider (Ollama local or Claude API)
- [ ] Verify Gateway is running and WebChat works
- [ ] Understand skill loading, tool permissions, and session flow

### 1.2 SQLite Data Layer
- [ ] Design unified schema (todos, events, memos, agent_tasks)
- [ ] Write `setup_db.py` — idempotent table creation
- [ ] Store DB at `~/.openclaw/secretary/secretary.db`
- [ ] Test CRUD operations standalone

### 1.3 Core Skills — SKILL.md + Scripts
- [ ] `secretary-todo`: Create, list, update, complete, delete todos
- [ ] `secretary-calendar`: Create, list, update, delete events
- [ ] `secretary-memo`: Create, list, search, delete memos
- [ ] Each skill: SKILL.md with clear triggers + Python scripts for DB ops
- [ ] Test via OpenClaw WebChat: "add a todo", "what's on my calendar tomorrow"

### 1.4 Intent Routing (via SKILL.md descriptions)
- [ ] Write precise `description` fields so OpenClaw correctly routes to skills
- [ ] Test ambiguous inputs ("remind me about the meeting" → calendar or todo?)
- [ ] Add `references/` docs for edge cases

**Milestone**: Can manage todos, events, and memos entirely through OpenClaw chat.

---

## Phase 2 — Mobile App Shell (Weeks 3–4)

**Goal**: React Native app connected to OpenClaw, displaying data from skills.

### 2.1 REST API Bridge
- [ ] `secretary-api` skill: lightweight FastAPI/Flask sidecar
  - Runs as a background process managed by OpenClaw
  - Endpoints: `/todos`, `/events`, `/memos`, `/chat`, `/health`
  - Reads/writes same SQLite DB as skills
- [ ] Authentication: simple token-based (API key in app settings)
- [ ] HTTPS via Tailscale or reverse proxy

### 2.2 React Native App — Screens
- [ ] **SetupScreen**: Enter server URL + API token
- [ ] **ChatScreen**: Connect to OpenClaw Gateway WebSocket, send/receive messages
- [ ] **TodoScreen**: List, add, complete, delete (via REST API)
- [ ] **CalendarScreen**: Month/week/day views (via REST API)
- [ ] **MemoScreen**: List, create, edit (via REST API)
- [ ] **SettingsScreen**: Server connection, LLM config, sync options
- [ ] Tab navigation between screens

### 2.3 State Management
- [ ] Zustand stores for each module
- [ ] Offline cache with sync-on-reconnect
- [ ] WebSocket hook for real-time updates

**Milestone**: Functional app that shows todos/events/memos and can chat with AI.

---

## Phase 3 — Smart Features (Weeks 5–6)

**Goal**: Proactive AI behavior — briefings, reminders, auto-tasks.

### 3.1 Daily Briefing
- [ ] OpenClaw cron job: every morning at configured time
- [ ] `secretary-agent/briefing.py`: query today's events + pending todos
- [ ] Generate natural language summary via LLM
- [ ] Push to app via notification

### 3.2 Reminders
- [ ] Cron job: check events/todos approaching deadline every 15 min
- [ ] Send push notification to app
- [ ] Notification options: FCM, or WebSocket-based in-app alert

### 3.3 Auto Agent Tasks
- [ ] Task types: `search`, `summarize`, `draft`, `remind`
- [ ] User says "research latest VLA papers" → creates agent_task
- [ ] `task_runner.py` executes via OpenClaw tools (web search, file write)
- [ ] Result saved to DB + notification sent

### 3.4 Google Calendar Sync (Optional)
- [ ] OAuth flow via app settings
- [ ] Bidirectional sync: local events ↔ Google Calendar
- [ ] Conflict resolution: last-write-wins with user prompt

**Milestone**: App proactively sends briefings and executes delegated tasks.

---

## Phase 4 — Widgets & Polish (Weeks 7–8)

**Goal**: Home screen widgets, UX polish, deployment packaging.

### 4.1 Home Screen Widgets
- [ ] **Android**: Native widgets via react-native-android-widget
  - Todo widget: today's tasks with checkboxes
  - Calendar widget: next 3 upcoming events
  - Quick input widget: text field → sends to AI
- [ ] **iOS**: WidgetKit extension
  - Similar widgets adapted for iOS design language
- [ ] Widget ↔ app data sync via shared storage / background fetch

### 4.2 Chat UX Improvements
- [ ] Streaming responses (token-by-token display)
- [ ] Action cards in chat (visual confirmation of created items)
- [ ] Voice input support
- [ ] Chat history with search

### 4.3 Deployment Package
- [ ] Docker Compose: OpenClaw + skills + API sidecar
- [ ] One-command setup script
- [ ] Documentation: install guide, first-run walkthrough
- [ ] Backup/restore tooling for SQLite DB

### 4.4 Security Hardening
- [ ] HTTPS enforcement (Tailscale Serve or Let's Encrypt)
- [ ] API token rotation
- [ ] Rate limiting on API endpoints
- [ ] Input sanitization in all skills

**Milestone**: Complete, deployable product with widgets and proactive AI.

---

## Key Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| AI backbone | OpenClaw | Don't reinvent agent runtime, memory, scheduling |
| Skill language | Python (scripts) | Richer DB/API ecosystem than bash |
| Local DB | SQLite | Single-file, no config, sufficient for single-user |
| App ↔ Server | REST + WebSocket | REST for CRUD, WS for chat streaming + notifications |
| App framework | React Native | Cross-platform + native widget support |
| State mgmt | Zustand | Minimal boilerplate, fast |
| Deployment | Docker Compose | Reproducible, includes OpenClaw + Ollama |

---

## Open Questions (To Resolve After Reading OpenClaw Code)

1. **Gateway API access**: Can the React Native app connect directly to OpenClaw's WebSocket Gateway, or do we need a custom bridge?
2. **Skill ↔ Skill communication**: Can `secretary-agent` skill call `secretary-todo` skill internally, or must it go through the DB?
3. **Background processes**: Can a skill run a persistent API server (FastAPI sidecar), or should we use OpenClaw's webhook system for the app to query data?
4. **Push notifications**: Does OpenClaw have a built-in mechanism for mobile push, or do we need FCM/APNs integration in the API sidecar?
5. **Skill data persistence**: Is `~/.openclaw/` the right place for the SQLite DB, or should it live in a dedicated data directory?
6. **WebChat customization**: Could we skip the React Native app initially and build a custom WebChat frontend that includes todo/calendar/memo panels?

These will be answered by reviewing the OpenClaw source code (especially Gateway WS protocol, skill execution model, and tool sandboxing).

---

## Next Steps

1. **Read OpenClaw source** — Focus on: Gateway WS protocol, skill loading, tool execution, cron system
2. **Prototype one skill** — `secretary-todo` with SKILL.md + Python CRUD scripts + SQLite
3. **Test via WebChat** — Verify natural language → skill trigger → DB write → response
4. **Then decide** — Build React Native app from scratch, or start with custom WebChat panel
"""Admin dashboard schemas."""

from pydantic import BaseModel


# --- Server Overview ---


class ServerOverview(BaseModel):
    uptime_seconds: float
    version: str
    ai_backend: str
    ai_model: str
    ai_base_url: str
    ai_connected: bool
    active_ws_connections: int
    scheduler_enabled: bool
    scheduler_running: bool


class TableCounts(BaseModel):
    conversations: int
    messages: int
    todos: int
    events: int
    memos: int
    agent_tasks: int
    attachments: int
    task_relationships: int


class StorageStats(BaseModel):
    db_size_bytes: int
    upload_dir_size_bytes: int
    attachment_count: int
    attachment_total_bytes: int


class AdminOverviewResponse(BaseModel):
    server: ServerOverview
    counts: TableCounts
    storage: StorageStats


# --- AI Configuration ---


class AIConfigResponse(BaseModel):
    backend: str
    model: str
    base_url: str
    connected: bool
    available_models: list[str]


class AITestResponse(BaseModel):
    connected: bool
    latency_ms: float | None = None
    error: str | None = None


# --- Activity ---


class RecentActivity(BaseModel):
    type: str
    id: str
    summary: str
    created_at: str


class AgentTaskSummary(BaseModel):
    id: str
    task_type: str
    agent_type: str
    status: str
    instruction: str
    result: str | None = None
    error: str | None = None
    created_at: str
    completed_at: str | None = None


class ActivityResponse(BaseModel):
    recent: list[RecentActivity]
    agent_tasks: list[AgentTaskSummary]


# --- Sessions ---


class ActiveSession(BaseModel):
    user_id: str
    connected: bool


class SessionsResponse(BaseModel):
    active_connections: list[ActiveSession]
    total_connections: int


# --- Server Config (read-only view) ---


class ServerConfigResponse(BaseModel):
    host: str
    port: int
    database_url: str
    jwt_expiry_hours: int
    ai_backend: str
    ai_base_url: str
    ai_model: str
    upload_dir: str
    max_upload_size_mb: int
    allowed_extensions: str
    enable_scheduler: bool
    briefing_time: str
    reminder_check_interval: int
    debug: bool


# --- Data Management ---


class ModuleDataOverview(BaseModel):
    name: str
    count: int
    oldest: str | None = None
    newest: str | None = None


class DataOverviewResponse(BaseModel):
    modules: list[ModuleDataOverview]


# --- Purge / Cleanup ---


class PurgeRequest(BaseModel):
    target: str
    older_than_days: int


class PurgeResponse(BaseModel):
    deleted_count: int
    target: str


# --- FTS Reindex ---


class ReindexResponse(BaseModel):
    status: str
    tables_reindexed: list[str]


# --- DB Backup ---


class BackupResponse(BaseModel):
    filename: str
    size_bytes: int

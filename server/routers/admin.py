"""Admin dashboard endpoints."""

import time
import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from config import settings
from database import get_db
from exceptions import ValidationError
from schemas.admin import (
    AdminOverviewResponse,
    ServerOverview,
    TableCounts,
    StorageStats,
    AIConfigResponse,
    AITestResponse,
    ActivityResponse,
    RecentActivity,
    AgentTaskSummary,
    SessionsResponse,
    ActiveSession,
    ServerConfigResponse,
    DataOverviewResponse,
    ModuleDataOverview,
    PurgeRequest,
    PurgeResponse,
    ReindexResponse,
    BackupResponse,
)
from services import admin_service
from ws.manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Overview ---


@router.get("/overview", response_model=AdminOverviewResponse)
async def get_overview(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    counts_dict = await admin_service.get_table_counts(db)
    storage_dict = await admin_service.get_storage_stats(db)

    scheduler = getattr(request.app.state, "scheduler", None)

    server = ServerOverview(
        uptime_seconds=admin_service.get_uptime_seconds(),
        version="0.1.0",
        ai_backend="openclaw",
        ai_model=settings.ai_model,
        ai_base_url=settings.ai_base_url,
        ai_connected=getattr(request.app.state, "ai_connected", False),
        active_ws_connections=len(ws_manager.active_connections),
        scheduler_enabled=settings.enable_scheduler,
        scheduler_running=scheduler is not None,
    )

    return AdminOverviewResponse(
        server=server,
        counts=TableCounts(**counts_dict),
        storage=StorageStats(**storage_dict),
    )


# --- AI Configuration ---


@router.get("/ai", response_model=AIConfigResponse)
async def get_ai_config(
    request: Request,
    _user: str = Depends(get_current_user),
):
    ai_service = request.app.state.ai_service
    connected = await ai_service.health_check()
    request.app.state.ai_connected = connected

    models: list[str] = []
    if connected:
        try:
            resp = await ai_service.client.get(
                f"{ai_service.base_url}/v1/models", timeout=5.0
            )
            if resp.status_code == 200:
                data = resp.json()
                models = [m["id"] for m in data.get("data", [])]
        except Exception:
            pass

    return AIConfigResponse(
        backend="openclaw",
        model=settings.ai_model,
        base_url=settings.ai_base_url,
        connected=connected,
        available_models=models,
    )


@router.post("/ai/test", response_model=AITestResponse)
async def test_ai_connection(
    request: Request,
    _user: str = Depends(get_current_user),
):
    ai_service = request.app.state.ai_service
    start = time.time()
    try:
        connected = await ai_service.health_check()
        latency = (time.time() - start) * 1000
        request.app.state.ai_connected = connected
        return AITestResponse(
            connected=connected,
            latency_ms=round(latency, 1) if connected else None,
            error=None if connected else "Health check returned false",
        )
    except Exception as exc:
        latency = (time.time() - start) * 1000
        return AITestResponse(connected=False, latency_ms=round(latency, 1), error=str(exc))


# --- Activity & Logs ---


@router.get("/activity", response_model=ActivityResponse)
async def get_activity(
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    recent = await admin_service.get_recent_activity(db, limit=50)
    agent_tasks = await admin_service.get_agent_task_history(db, limit=50)
    return ActivityResponse(
        recent=[RecentActivity(**r) for r in recent],
        agent_tasks=[AgentTaskSummary(**t) for t in agent_tasks],
    )


# --- Sessions ---


@router.get("/sessions", response_model=SessionsResponse)
async def get_sessions(
    _user: str = Depends(get_current_user),
):
    connections = [
        ActiveSession(user_id=uid, connected=True)
        for uid in ws_manager.active_connections
    ]
    return SessionsResponse(
        active_connections=connections,
        total_connections=len(connections),
    )


@router.post("/sessions/{user_id}/disconnect")
async def disconnect_session(
    user_id: str,
    _user: str = Depends(get_current_user),
):
    ws = ws_manager.active_connections.get(user_id)
    if ws:
        await ws.close()
        ws_manager.disconnect(user_id)
        return {"status": "disconnected", "user_id": user_id}
    return {"status": "not_found", "user_id": user_id}


# --- Server Config ---


@router.get("/config", response_model=ServerConfigResponse)
async def get_server_config(
    _user: str = Depends(get_current_user),
):
    db_display = settings.database_url.split("///")[-1] if "///" in settings.database_url else "***"
    return ServerConfigResponse(
        host=settings.host,
        port=settings.port,
        database_url=db_display,
        jwt_expiry_hours=settings.jwt_expiry_hours,
        ai_backend="openclaw",
        ai_base_url=settings.ai_base_url,
        ai_model=settings.ai_model,
        upload_dir=settings.upload_dir,
        max_upload_size_mb=settings.max_upload_size_mb,
        allowed_extensions=settings.allowed_extensions,
        enable_scheduler=settings.enable_scheduler,
        briefing_time=settings.briefing_time,
        reminder_check_interval=settings.reminder_check_interval,
        debug=settings.debug,
    )


# --- Data Management ---


@router.get("/data", response_model=DataOverviewResponse)
async def get_data_overview(
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    modules = await admin_service.get_module_data_overview(db)
    return DataOverviewResponse(
        modules=[ModuleDataOverview(**m) for m in modules]
    )


# --- Database Operations ---


@router.post("/db/reindex", response_model=ReindexResponse)
async def reindex_database(
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    tables = await admin_service.reindex_fts(db)
    return ReindexResponse(status="completed", tables_reindexed=tables)


@router.post("/db/backup", response_model=BackupResponse)
async def backup_database(
    _user: str = Depends(get_current_user),
):
    filename, size = await admin_service.backup_database()
    return BackupResponse(filename=filename, size_bytes=size)


@router.post("/db/purge", response_model=PurgeResponse)
async def purge_data(
    body: PurgeRequest,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    if body.target not in ("conversations", "messages", "todos"):
        raise ValidationError(f"Invalid purge target: {body.target}")
    if body.older_than_days < 1:
        raise ValidationError("older_than_days must be >= 1")

    count = await admin_service.purge_old_data(db, body.target, body.older_than_days)
    return PurgeResponse(deleted_count=count, target=body.target)

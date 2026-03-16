"""Obsidian vault sync endpoints."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from config import settings
from database import get_db
from models.todo import Todo
from services.obsidian_sync_service import (
    get_last_sync_time,
    scan_vault,
    set_last_sync_time,
    sync_obsidian_todos,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/sync")
async def trigger_sync(
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """Trigger a full bidirectional sync with the Obsidian vault."""
    vault_path = settings.obsidian_vault_path
    if not vault_path:
        return {"error": "Obsidian vault path not configured", "synced": 0, "created": 0, "updated": 0, "written_back": 0}

    result = await sync_obsidian_todos(db, vault_path)
    set_last_sync_time(datetime.now(timezone.utc))

    return {
        "synced": result.synced,
        "created": result.created,
        "updated": result.updated,
        "written_back": result.written_back,
    }


@router.get("/status")
async def get_status(
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """Return current Obsidian sync status."""
    vault_path = settings.obsidian_vault_path
    enabled = bool(vault_path)

    file_count = 0
    task_count = 0

    if enabled:
        # Count files and tasks from a quick vault scan
        try:
            tasks = scan_vault(vault_path)
            task_count = len(tasks)
            file_count = len({t.file_path for t in tasks})
        except Exception as e:
            logger.warning("Failed to scan vault for status: %s", e)

    # Count DB todos with source=obsidian
    stmt = select(func.count(Todo.id)).where(Todo.source == "obsidian")
    db_task_count = (await db.execute(stmt)).scalar() or 0

    last_sync = get_last_sync_time()

    return {
        "enabled": enabled,
        "vault_path": vault_path,
        "last_sync": last_sync.isoformat() if last_sync else None,
        "file_count": file_count,
        "task_count": task_count,
        "db_task_count": db_task_count,
    }

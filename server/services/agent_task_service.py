"""Async service layer for agent task lifecycle."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.agent_task import AgentTask
from services.ai_service import AIService
from utils import make_id
from ws.manager import ConnectionManager

logger = logging.getLogger(__name__)


async def create_task(
    db: AsyncSession,
    *,
    task_type: str,
    instruction: str,
    conversation_id: str | None = None,
    message_id: str | None = None,
) -> AgentTask:
    task = AgentTask(
        id=make_id("task_"),
        task_type=task_type,
        instruction=instruction,
        status="queued",
        conversation_id=conversation_id,
        message_id=message_id,
    )
    db.add(task)
    await db.flush()
    return task


async def get_queued_tasks(db: AsyncSession) -> list[AgentTask]:
    q = (
        select(AgentTask)
        .where(AgentTask.status == "queued")
        .order_by(AgentTask.created_at.asc())
    )
    return list((await db.execute(q)).scalars().all())


async def mark_running(db: AsyncSession, task: AgentTask) -> None:
    task.status = "running"
    task.started_at = datetime.now(timezone.utc)
    await db.flush()


async def mark_completed(db: AsyncSession, task: AgentTask, result: str) -> None:
    task.status = "completed"
    task.result = result
    task.completed_at = datetime.now(timezone.utc)
    await db.flush()


async def mark_failed(db: AsyncSession, task: AgentTask, error: str) -> None:
    task.status = "failed"
    task.error = error
    task.completed_at = datetime.now(timezone.utc)
    await db.flush()


async def execute_task(
    db: AsyncSession,
    task: AgentTask,
    ai_service: AIService,
    ws_manager: ConnectionManager,
    user_id: str,
) -> None:
    """Full pipeline: mark running → call LLM → mark completed/failed → WS notify."""
    await mark_running(db, task)
    await db.commit()

    try:
        result = await ai_service.generate_completion(
            system_prompt=(
                "You are a helpful assistant executing a background task. "
                "Complete the following task and provide a clear, concise result."
            ),
            user_message=task.instruction,
        )
        await mark_completed(db, task, result)
        await db.commit()

        await ws_manager.send_json(user_id, {
            "type": "task_completed",
            "data": {
                "task_id": task.id,
                "task_type": task.task_type,
                "result": result,
                "conversation_id": task.conversation_id,
            },
        })
    except Exception as exc:
        logger.exception("Agent task %s failed", task.id)
        error_msg = str(exc)
        await mark_failed(db, task, error_msg)
        await db.commit()

        await ws_manager.send_json(user_id, {
            "type": "task_failed",
            "data": {
                "task_id": task.id,
                "task_type": task.task_type,
                "error": error_msg,
                "conversation_id": task.conversation_id,
            },
        })

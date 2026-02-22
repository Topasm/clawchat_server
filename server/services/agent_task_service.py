"""Async service layer for agent task lifecycle with multi-agent coordination."""

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.agent_task import AgentTask
from services.ai_service import AIService
from utils import make_id, strip_markdown_fences
from ws.manager import ConnectionManager

logger = logging.getLogger(__name__)

# Specialized agent system prompts
AGENT_PROMPTS: dict[str, str] = {
    "general": (
        "You are a helpful assistant executing a background task. "
        "Complete the following task and provide a clear, concise result."
    ),
    "research": (
        "You are a research assistant. Analyze the topic thoroughly, "
        "gather key insights, and present your findings in a well-structured format."
    ),
    "scheduling": (
        "You are a scheduling assistant. Help optimize time management, "
        "suggest meeting times, and resolve calendar conflicts."
    ),
    "drafting": (
        "You are a writing assistant. Draft clear, professional content "
        "based on the given instructions. Focus on clarity and structure."
    ),
    "analysis": (
        "You are a data analysis assistant. Analyze the given information, "
        "identify patterns, and provide actionable insights."
    ),
    "coordinator": (
        "You are a task coordinator. Break down complex tasks into smaller, "
        "manageable sub-tasks. Return a JSON array of sub-tasks.\n\n"
        "Each sub-task should have:\n"
        '- "instruction": what to do\n'
        '- "agent_type": one of "research", "drafting", "analysis", "general"\n\n'
        "Return ONLY a JSON array, no other text. Example:\n"
        '[{"instruction": "Research X", "agent_type": "research"}, '
        '{"instruction": "Draft report on Y", "agent_type": "drafting"}]'
    ),
}

# Keywords that indicate a task should use coordinator pattern
COMPLEXITY_KEYWORDS = [
    "research and", "analyze and", "draft and", "create a report",
    "investigate and", "summarize and", "compare and", "evaluate and",
    "step by step", "multi-step", "comprehensive",
]


def detect_agent_type(instruction: str) -> str:
    """Detect whether a task needs multi-agent coordination."""
    lower = instruction.lower()
    word_count = len(lower.split())

    # Long instructions or multi-step keywords suggest coordinator
    if word_count > 30 or any(kw in lower for kw in COMPLEXITY_KEYWORDS):
        return "coordinator"

    # Simple heuristics for specialist types
    if any(w in lower for w in ["research", "find out", "look up", "investigate"]):
        return "research"
    if any(w in lower for w in ["write", "draft", "compose", "email"]):
        return "drafting"
    if any(w in lower for w in ["analyze", "compare", "evaluate", "assess"]):
        return "analysis"

    return "general"


async def create_task(
    db: AsyncSession,
    *,
    task_type: str,
    instruction: str,
    conversation_id: str | None = None,
    message_id: str | None = None,
    parent_task_id: str | None = None,
    agent_type: str = "general",
) -> AgentTask:
    task = AgentTask(
        id=make_id("task_"),
        task_type=task_type,
        instruction=instruction,
        status="queued",
        conversation_id=conversation_id,
        message_id=message_id,
        parent_task_id=parent_task_id,
        agent_type=agent_type,
    )
    db.add(task)
    await db.flush()
    return task


async def get_sub_tasks(db: AsyncSession, parent_id: str) -> list[AgentTask]:
    q = (
        select(AgentTask)
        .where(AgentTask.parent_task_id == parent_id)
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
    task.progress = 100
    task.completed_at = datetime.now(timezone.utc)
    await db.flush()


async def mark_failed(db: AsyncSession, task: AgentTask, error: str) -> None:
    task.status = "failed"
    task.error = error
    task.completed_at = datetime.now(timezone.utc)
    await db.flush()


async def update_progress(
    db: AsyncSession,
    task: AgentTask,
    progress: int,
    message: str,
    ws_manager: ConnectionManager,
    user_id: str,
) -> None:
    task.progress = progress
    task.progress_message = message
    await db.flush()

    await ws_manager.send_json(user_id, {
        "type": "task_progress",
        "data": {
            "task_id": task.id,
            "progress": progress,
            "message": message,
            "status": task.status,
            "parent_task_id": task.parent_task_id,
        },
    })


async def execute_task(
    db: AsyncSession,
    task: AgentTask,
    ai_service: AIService,
    ws_manager: ConnectionManager,
    user_id: str,
    session_factory=None,
) -> None:
    """Full pipeline: mark running -> execute -> mark completed/failed -> WS notify."""
    if task.agent_type == "coordinator":
        await _execute_coordinator(db, task, ai_service, ws_manager, user_id, session_factory)
        return

    await mark_running(db, task)
    await db.commit()

    system_prompt = AGENT_PROMPTS.get(task.agent_type, AGENT_PROMPTS["general"])

    try:
        # Send initial progress
        await update_progress(db, task, 10, "Starting task...", ws_manager, user_id)
        await db.commit()

        result = await ai_service.generate_completion(
            system_prompt=system_prompt,
            user_message=task.instruction,
        )

        await update_progress(db, task, 90, "Finalizing...", ws_manager, user_id)
        await mark_completed(db, task, result)
        await db.commit()

        # Check if this is a sub-task and update parent
        if task.parent_task_id:
            await _check_parent_completion(db, task.parent_task_id, ai_service, ws_manager, user_id)

        await ws_manager.send_json(user_id, {
            "type": "task_completed",
            "data": {
                "task_id": task.id,
                "task_type": task.task_type,
                "result": result,
                "conversation_id": task.conversation_id,
                "parent_task_id": task.parent_task_id,
            },
        })
    except Exception as exc:
        logger.exception("Agent task %s failed", task.id)
        error_msg = str(exc)
        await mark_failed(db, task, error_msg)
        await db.commit()

        if task.parent_task_id:
            await _check_parent_completion(db, task.parent_task_id, ai_service, ws_manager, user_id)

        await ws_manager.send_json(user_id, {
            "type": "task_failed",
            "data": {
                "task_id": task.id,
                "task_type": task.task_type,
                "error": error_msg,
                "conversation_id": task.conversation_id,
                "parent_task_id": task.parent_task_id,
            },
        })


async def _execute_coordinator(
    db: AsyncSession,
    task: AgentTask,
    ai_service: AIService,
    ws_manager: ConnectionManager,
    user_id: str,
    session_factory=None,
) -> None:
    """Coordinator agent: decompose into sub-tasks, fire them, aggregate results."""
    await mark_running(db, task)
    await update_progress(db, task, 5, "Analyzing task and creating sub-tasks...", ws_manager, user_id)
    await db.commit()

    try:
        # Use AI to decompose the task
        response = await ai_service.generate_completion(
            system_prompt=AGENT_PROMPTS["coordinator"],
            user_message=task.instruction,
        )

        # Parse sub-task definitions
        cleaned = strip_markdown_fences(response)

        sub_task_defs = json.loads(cleaned)
        if not isinstance(sub_task_defs, list) or not sub_task_defs:
            # Fallback: run as single general task
            sub_task_defs = [{"instruction": task.instruction, "agent_type": "general"}]

        task.sub_task_count = len(sub_task_defs)
        task.completed_sub_tasks = 0
        await update_progress(db, task, 10, f"Created {len(sub_task_defs)} sub-tasks", ws_manager, user_id)
        await db.commit()

        # Create sub-tasks
        sub_tasks = []
        for sub_def in sub_task_defs:
            sub = await create_task(
                db,
                task_type=sub_def.get("agent_type", "general"),
                instruction=sub_def["instruction"],
                conversation_id=task.conversation_id,
                message_id=task.message_id,
                parent_task_id=task.id,
                agent_type=sub_def.get("agent_type", "general"),
            )
            sub_tasks.append(sub)
        await db.commit()

        # Fire sub-tasks concurrently
        if session_factory:
            async def _run_sub(sub_id: str):
                async with session_factory() as sub_db:
                    sub = await sub_db.get(AgentTask, sub_id)
                    if sub:
                        await execute_task(sub_db, sub, ai_service, ws_manager, user_id)

            tasks = [asyncio.create_task(_run_sub(s.id)) for s in sub_tasks]
            await asyncio.gather(*tasks, return_exceptions=True)
        else:
            # Sequential fallback if no session_factory
            for sub in sub_tasks:
                sub_task = await db.get(AgentTask, sub.id)
                if sub_task:
                    await execute_task(db, sub_task, ai_service, ws_manager, user_id)

    except Exception as exc:
        logger.exception("Coordinator task %s failed", task.id)
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


async def _check_parent_completion(
    db: AsyncSession,
    parent_id: str,
    ai_service: AIService,
    ws_manager: ConnectionManager,
    user_id: str,
) -> None:
    """Check if all sub-tasks of a parent are done and synthesize results."""
    parent = await db.get(AgentTask, parent_id)
    if not parent or parent.status in ("completed", "failed"):
        return

    subs = await get_sub_tasks(db, parent_id)
    completed = [s for s in subs if s.status == "completed"]
    failed = [s for s in subs if s.status == "failed"]
    total = len(subs)

    parent.completed_sub_tasks = len(completed) + len(failed)
    progress = int((parent.completed_sub_tasks / max(total, 1)) * 90) + 10
    await update_progress(db, parent, progress, f"{len(completed)}/{total} sub-tasks completed", ws_manager, user_id)
    await db.commit()

    # Check if all sub-tasks are done
    if parent.completed_sub_tasks < total:
        return

    # All done — synthesize results
    if completed:
        results_text = "\n\n---\n\n".join(
            f"**Sub-task ({s.agent_type}):** {s.instruction}\n**Result:** {s.result}"
            for s in completed
        )

        try:
            synthesis = await ai_service.generate_completion(
                system_prompt="Synthesize the following sub-task results into a cohesive final response. Be comprehensive but concise.",
                user_message=f"Original task: {parent.instruction}\n\nSub-task results:\n{results_text}",
            )
            await mark_completed(db, parent, synthesis)
        except Exception:
            # Fallback: concatenate results
            await mark_completed(db, parent, results_text)
    else:
        error_msgs = "; ".join(s.error or "Unknown error" for s in failed)
        await mark_failed(db, parent, f"All sub-tasks failed: {error_msgs}")

    await db.commit()

    status = "task_completed" if parent.status == "completed" else "task_failed"
    await ws_manager.send_json(user_id, {
        "type": status,
        "data": {
            "task_id": parent.id,
            "task_type": parent.task_type,
            "result": parent.result if parent.status == "completed" else None,
            "error": parent.error if parent.status == "failed" else None,
            "conversation_id": parent.conversation_id,
        },
    })

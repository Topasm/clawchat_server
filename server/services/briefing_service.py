"""Async service for generating daily briefings."""

import logging
from datetime import date, datetime, time, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions import AIUnavailableError
from models.agent_task import AgentTask
from models.event import Event
from models.todo import Todo
from services.ai_service import AIService

logger = logging.getLogger(__name__)


async def gather_briefing_data(db: AsyncSession) -> dict:
    today = date.today()
    today_start = datetime.combine(today, time.min, tzinfo=timezone.utc)
    today_end = datetime.combine(today, time.max, tzinfo=timezone.utc)

    # Today's events
    events_q = (
        select(Event)
        .where(Event.start_time >= today_start, Event.start_time <= today_end)
        .order_by(Event.start_time.asc())
    )
    events = list((await db.execute(events_q)).scalars().all())

    # Pending todos due today
    pending_q = (
        select(Todo)
        .where(
            Todo.due_date >= today_start,
            Todo.due_date <= today_end,
            Todo.status.notin_(["completed", "cancelled"]),
        )
        .order_by(Todo.created_at.asc())
    )
    pending_todos = list((await db.execute(pending_q)).scalars().all())

    # Overdue todos
    overdue_q = (
        select(Todo)
        .where(
            Todo.due_date < today_start,
            Todo.status.in_(["pending", "in_progress"]),
        )
        .order_by(Todo.due_date.asc())
    )
    overdue_todos = list((await db.execute(overdue_q)).scalars().all())

    # In-progress tasks (not due today)
    in_progress_q = select(Todo).where(
        Todo.status == "in_progress",
        or_(
            Todo.due_date == None,  # noqa: E711
            Todo.due_date < today_start,
            Todo.due_date > today_end,
        ),
    )
    in_progress = list((await db.execute(in_progress_q)).scalars().all())

    # Inbox count (no due date, pending)
    inbox_q = select(func.count(Todo.id)).where(
        Todo.due_date == None,  # noqa: E711
        Todo.status == "pending",
    )
    inbox_count = (await db.execute(inbox_q)).scalar() or 0

    # Running agent tasks
    agent_q = select(AgentTask).where(AgentTask.status.in_(["queued", "running"]))
    agent_tasks = list((await db.execute(agent_q)).scalars().all())

    return {
        "events": events,
        "pending_todos": pending_todos,
        "overdue_todos": overdue_todos,
        "in_progress": in_progress,
        "inbox_count": inbox_count,
        "agent_tasks": agent_tasks,
        "date": today,
    }


def _format_briefing_prompt(data: dict) -> str:
    lines = [f"Today is {data['date'].strftime('%A, %B %d, %Y')}."]
    lines.append("")

    if data["events"]:
        lines.append("## Today's Events")
        for e in data["events"]:
            t = e.start_time.strftime("%H:%M") if e.start_time else "all day"
            lines.append(f"- {t}: {e.title}" + (f" @ {e.location}" if e.location else ""))
        lines.append("")

    if data["pending_todos"]:
        lines.append("## Tasks Due Today")
        for t in data["pending_todos"]:
            lines.append(f"- [{t.priority}] {t.title}")
        lines.append("")

    if data["overdue_todos"]:
        lines.append("## Overdue Tasks")
        for t in data["overdue_todos"]:
            due = t.due_date.strftime("%b %d") if t.due_date else "unknown"
            lines.append(f"- {t.title} (was due {due})")
        lines.append("")

    if data["in_progress"]:
        lines.append("## In Progress")
        for t in data["in_progress"]:
            lines.append(f"- {t.title}")
        lines.append("")

    if data["inbox_count"] > 0:
        lines.append(f"Inbox: {data['inbox_count']} unsorted task(s).")
        lines.append("")

    if data["agent_tasks"]:
        lines.append(f"Background tasks: {len(data['agent_tasks'])} queued/running.")
        lines.append("")

    return "\n".join(lines)


async def generate_briefing(db: AsyncSession, ai_service: AIService) -> str:
    data = await gather_briefing_data(db)

    # Nothing to brief
    has_items = (
        data["events"]
        or data["pending_todos"]
        or data["overdue_todos"]
        or data["in_progress"]
        or data["inbox_count"] > 0
        or data["agent_tasks"]
    )
    if not has_items:
        return "Your schedule is clear today. No tasks, events, or pending items."

    prompt_text = _format_briefing_prompt(data)

    try:
        return await ai_service.generate_completion(
            system_prompt=(
                "You are a personal assistant generating a daily briefing. "
                "Summarize the user's day in a friendly, concise way. "
                "Highlight urgent items. Use bullet points for clarity."
            ),
            user_message=prompt_text,
        )
    except AIUnavailableError:
        logger.warning("LLM unavailable for briefing, using plain text fallback")
        return _format_briefing_prompt(data)

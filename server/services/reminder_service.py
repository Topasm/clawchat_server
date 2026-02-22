"""Reminder service — checks for upcoming events and overdue todos, sends WS notifications."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.event import Event
from models.todo import Todo
from services.recurrence_service import generate_occurrences
from ws.manager import ConnectionManager

logger = logging.getLogger(__name__)

# In-memory dedup: set of (reminder_type, item_id, dedup_key)
_sent_reminders: set[tuple[str, str, str]] = set()


async def check_event_reminders(
    db: AsyncSession, ws_manager: ConnectionManager, user_id: str
) -> int:
    """Find events starting within 60 min that have reminder_minutes set. Returns count sent."""
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(minutes=60)

    q = (
        select(Event)
        .where(
            Event.start_time >= now,
            Event.start_time <= window_end,
            Event.reminder_minutes != None,  # noqa: E711
        )
    )
    events = (await db.execute(q)).scalars().all()
    sent = 0

    for event in events:
        remind_at = event.start_time - timedelta(minutes=event.reminder_minutes)
        if remind_at > now:
            continue  # Not yet time to remind

        dedup_key = event.start_time.isoformat()
        key = ("event", event.id, dedup_key)
        if key in _sent_reminders:
            continue

        minutes_until = max(0, int((event.start_time - now).total_seconds() / 60))
        await ws_manager.send_json(user_id, {
            "type": "reminder",
            "data": {
                "reminder_type": "event",
                "item_id": event.id,
                "title": event.title,
                "message": f"'{event.title}' starts in {minutes_until} minute(s).",
                "minutes_until": minutes_until,
            },
        })
        _sent_reminders.add(key)
        sent += 1

    # Check recurring event occurrences within the reminder window
    recurring_q = (
        select(Event)
        .where(
            Event.recurrence_rule != None,  # noqa: E711
            Event.reminder_minutes != None,  # noqa: E711
        )
    )
    recurring_events = (await db.execute(recurring_q)).scalars().all()

    for event in recurring_events:
        occurrences = generate_occurrences(event, now, window_end)
        for occ in occurrences:
            occ_start = occ["start_time"]
            if isinstance(occ_start, str):
                occ_start = datetime.fromisoformat(occ_start)

            remind_at = occ_start - timedelta(minutes=event.reminder_minutes)
            if remind_at > now:
                continue

            occ_dedup_key = occ["occurrence_date"]
            key = ("event", event.id, occ_dedup_key)
            if key in _sent_reminders:
                continue

            minutes_until = max(0, int((occ_start - now).total_seconds() / 60))
            await ws_manager.send_json(user_id, {
                "type": "reminder",
                "data": {
                    "reminder_type": "event",
                    "item_id": event.id,
                    "title": event.title,
                    "message": f"'{event.title}' starts in {minutes_until} minute(s).",
                    "minutes_until": minutes_until,
                    "occurrence_date": occ_dedup_key,
                },
            })
            _sent_reminders.add(key)
            sent += 1

    return sent


async def check_todo_reminders(
    db: AsyncSession, ws_manager: ConnectionManager, user_id: str
) -> int:
    """Find non-completed todos due within 60 min. Returns count sent."""
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(minutes=60)

    q = (
        select(Todo)
        .where(
            Todo.due_date >= now,
            Todo.due_date <= window_end,
            Todo.status.notin_(["completed", "cancelled"]),
        )
    )
    todos = (await db.execute(q)).scalars().all()
    sent = 0

    for todo in todos:
        dedup_key = todo.due_date.isoformat()
        key = ("todo", todo.id, dedup_key)
        if key in _sent_reminders:
            continue

        minutes_until = max(0, int((todo.due_date - now).total_seconds() / 60))
        await ws_manager.send_json(user_id, {
            "type": "reminder",
            "data": {
                "reminder_type": "todo",
                "item_id": todo.id,
                "title": todo.title,
                "message": f"'{todo.title}' is due in {minutes_until} minute(s).",
                "minutes_until": minutes_until,
            },
        })
        _sent_reminders.add(key)
        sent += 1

    return sent


async def check_overdue_todos(
    db: AsyncSession, ws_manager: ConnectionManager, user_id: str
) -> int:
    """Find overdue pending/in-progress todos, one-time notification each. Returns count sent."""
    now = datetime.now(timezone.utc)

    q = (
        select(Todo)
        .where(
            Todo.due_date < now,
            Todo.status.in_(["pending", "in_progress"]),
        )
    )
    todos = (await db.execute(q)).scalars().all()
    sent = 0

    for todo in todos:
        key = ("todo_overdue", todo.id, "overdue")
        if key in _sent_reminders:
            continue

        await ws_manager.send_json(user_id, {
            "type": "reminder",
            "data": {
                "reminder_type": "todo_overdue",
                "item_id": todo.id,
                "title": todo.title,
                "message": f"'{todo.title}' is overdue.",
                "minutes_until": 0,
            },
        })
        _sent_reminders.add(key)
        sent += 1

    return sent


async def run_all_checks(
    db: AsyncSession, ws_manager: ConnectionManager, user_id: str
) -> int:
    total = 0
    total += await check_event_reminders(db, ws_manager, user_id)
    total += await check_todo_reminders(db, ws_manager, user_id)
    total += await check_overdue_todos(db, ws_manager, user_id)
    return total


def clear_sent_reminders() -> None:
    """Reset the dedup set — called at midnight."""
    _sent_reminders.clear()

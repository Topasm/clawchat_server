"""Async service layer for calendar event CRUD operations."""

import json
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions import NotFoundError
from models.event import Event
from services.recurrence_service import generate_occurrences
from utils import apply_model_updates, make_id, serialize_tags


async def get_events(
    db: AsyncSession,
    *,
    start_after: datetime | None = None,
    start_before: datetime | None = None,
    page: int = 1,
    limit: int = 50,
) -> tuple[list[Event | dict], int]:
    conditions = []
    if start_after is not None:
        conditions.append(Event.start_time >= start_after)
    if start_before is not None:
        conditions.append(Event.start_time <= start_before)

    # Fetch regular (non-recurring) events
    count_q = select(func.count(Event.id)).where(*conditions)
    total = (await db.execute(count_q)).scalar() or 0

    q = (
        select(Event)
        .where(*conditions)
        .order_by(Event.start_time.asc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    rows = (await db.execute(q)).scalars().all()
    results: list[Event | dict] = list(rows)

    # Expand recurring events into virtual occurrences
    if start_after and start_before:
        recurring_q = (
            select(Event)
            .where(Event.recurrence_rule != None)  # noqa: E711
        )
        recurring_events = (await db.execute(recurring_q)).scalars().all()
        for rev in recurring_events:
            occurrences = generate_occurrences(rev, start_after, start_before)
            results.extend(occurrences)

    # Sort combined results by start_time
    def sort_key(item):
        if isinstance(item, dict):
            st = item["start_time"]
            return st if isinstance(st, datetime) else datetime.fromisoformat(st)
        return item.start_time

    results.sort(key=sort_key)
    return results, total + len([r for r in results if isinstance(r, dict)])


async def get_event(db: AsyncSession, event_id: str) -> Event:
    event = await db.get(Event, event_id)
    if not event:
        raise NotFoundError(f"Event {event_id} not found")
    return event


async def create_event(
    db: AsyncSession,
    *,
    title: str,
    description: str | None = None,
    start_time: datetime,
    end_time: datetime | None = None,
    location: str | None = None,
    is_all_day: bool = False,
    reminder_minutes: int | None = None,
    recurrence_rule: str | None = None,
    recurrence_end: datetime | None = None,
    tags: list[str] | None = None,
) -> Event:
    event = Event(
        id=make_id("evt_"),
        title=title,
        description=description,
        start_time=start_time,
        end_time=end_time,
        location=location,
        is_all_day=is_all_day,
        reminder_minutes=reminder_minutes,
        recurrence_rule=recurrence_rule,
        recurrence_end=recurrence_end,
        tags=serialize_tags(tags),
    )
    db.add(event)
    await db.flush()
    return event


async def update_event(db: AsyncSession, event_id: str, **updates) -> Event:
    event = await get_event(db, event_id)
    apply_model_updates(event, updates)
    await db.flush()
    return event


async def delete_event(db: AsyncSession, event_id: str) -> None:
    event = await get_event(db, event_id)
    await db.delete(event)
    await db.flush()


async def delete_event_occurrence(
    db: AsyncSession, event_id: str, occurrence_date: str, mode: str
) -> None:
    """Delete a recurring event occurrence.

    mode: 'this_only' — adds to exceptions list
          'this_and_future' — sets recurrence_end to this date
          'all' — deletes entire series
    """
    event = await get_event(db, event_id)

    if mode == "all":
        await db.delete(event)
        await db.flush()
        return

    if mode == "this_and_future":
        occ_dt = datetime.fromisoformat(occurrence_date)
        event.recurrence_end = occ_dt.replace(tzinfo=timezone.utc)
        event.updated_at = datetime.now(timezone.utc)
        await db.flush()
        return

    # mode == "this_only" — add to exceptions
    exceptions: list[str] = []
    if event.recurrence_exceptions:
        try:
            exceptions = json.loads(event.recurrence_exceptions)
        except (json.JSONDecodeError, TypeError):
            exceptions = []
    if occurrence_date not in exceptions:
        exceptions.append(occurrence_date)
    event.recurrence_exceptions = json.dumps(exceptions)
    event.updated_at = datetime.now(timezone.utc)
    await db.flush()

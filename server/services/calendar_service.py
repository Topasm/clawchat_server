"""Async service layer for calendar event CRUD operations."""

import json
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions import NotFoundError
from models.event import Event
from utils import make_id


async def get_events(
    db: AsyncSession,
    *,
    start_after: datetime | None = None,
    start_before: datetime | None = None,
    page: int = 1,
    limit: int = 50,
) -> tuple[list[Event], int]:
    conditions = []
    if start_after is not None:
        conditions.append(Event.start_time >= start_after)
    if start_before is not None:
        conditions.append(Event.start_time <= start_before)

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
    return list(rows), total


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
        tags=json.dumps(tags) if tags else None,
    )
    db.add(event)
    await db.flush()
    return event


async def update_event(db: AsyncSession, event_id: str, **updates) -> Event:
    event = await get_event(db, event_id)
    for key, value in updates.items():
        if key == "tags":
            setattr(event, key, json.dumps(value) if value else None)
        else:
            setattr(event, key, value)

    event.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return event


async def delete_event(db: AsyncSession, event_id: str) -> None:
    event = await get_event(db, event_id)
    await db.delete(event)
    await db.flush()

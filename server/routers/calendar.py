import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from database import get_db
from exceptions import NotFoundError
from models.event import Event
from schemas.calendar import EventCreate, EventResponse, EventUpdate
from schemas.common import PaginatedResponse
from utils import make_id

router = APIRouter()


@router.get("", response_model=PaginatedResponse[EventResponse])
async def list_events(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    start_after: datetime | None = None,
    start_before: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    offset = (page - 1) * limit
    conditions = []
    if start_after:
        conditions.append(Event.start_time >= start_after)
    if start_before:
        conditions.append(Event.start_time <= start_before)

    count_q = select(func.count(Event.id)).where(*conditions)
    total = (await db.execute(count_q)).scalar() or 0

    q = (
        select(Event)
        .where(*conditions)
        .order_by(Event.start_time.asc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await db.execute(q)).scalars().all()

    items = []
    for row in rows:
        resp = EventResponse.model_validate(row)
        if row.tags:
            resp.tags = json.loads(row.tags)
        items.append(resp)

    return PaginatedResponse(items=items, total=total, page=page, limit=limit)


@router.post("", response_model=EventResponse, status_code=201)
async def create_event(
    body: EventCreate,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    event = Event(
        id=make_id("evt_"),
        title=body.title,
        description=body.description,
        start_time=body.start_time,
        end_time=body.end_time,
        location=body.location,
        is_all_day=body.is_all_day,
        reminder_minutes=body.reminder_minutes,
        tags=json.dumps(body.tags) if body.tags else None,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    resp = EventResponse.model_validate(event)
    if event.tags:
        resp.tags = json.loads(event.tags)
    return resp


@router.get("/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    event = await db.get(Event, event_id)
    if not event:
        raise NotFoundError("Event not found")
    resp = EventResponse.model_validate(event)
    if event.tags:
        resp.tags = json.loads(event.tags)
    return resp


@router.patch("/{event_id}", response_model=EventResponse)
async def update_event(
    event_id: str,
    body: EventUpdate,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    event = await db.get(Event, event_id)
    if not event:
        raise NotFoundError("Event not found")

    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        if key == "tags":
            setattr(event, key, json.dumps(value) if value else None)
        else:
            setattr(event, key, value)

    event.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(event)

    resp = EventResponse.model_validate(event)
    if event.tags:
        resp.tags = json.loads(event.tags)
    return resp


@router.delete("/{event_id}", status_code=204)
async def delete_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    event = await db.get(Event, event_id)
    if not event:
        raise NotFoundError("Event not found")
    await db.delete(event)
    await db.commit()

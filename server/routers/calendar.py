from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from database import get_db
from exceptions import NotFoundError
from models.event import Event
from schemas.calendar import EventCreate, EventResponse, EventUpdate
from schemas.common import PaginatedResponse
from services import calendar_service
from utils import apply_model_updates, deserialize_tags, make_id, serialize_tags

router = APIRouter()


def _event_to_response(row) -> EventResponse:
    """Convert an Event ORM object or virtual occurrence dict to EventResponse."""
    if isinstance(row, dict):
        # Virtual occurrence from recurrence expansion
        tags = row.get("tags")
        if isinstance(tags, str):
            tags = deserialize_tags(tags)
        return EventResponse(
            id=row["id"],
            title=row["title"],
            description=row.get("description"),
            start_time=row["start_time"],
            end_time=row.get("end_time"),
            location=row.get("location"),
            is_all_day=row.get("is_all_day", False),
            reminder_minutes=row.get("reminder_minutes"),
            recurrence_rule=row.get("recurrence_rule"),
            recurrence_end=row.get("recurrence_end"),
            is_occurrence=row.get("is_occurrence", False),
            occurrence_date=row.get("occurrence_date"),
            recurring_event_id=row.get("recurring_event_id"),
            tags=tags if isinstance(tags, list) else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
    resp = EventResponse.model_validate(row)
    if row.tags:
        resp.tags = deserialize_tags(row.tags)
    return resp


@router.get("", response_model=PaginatedResponse[EventResponse])
async def list_events(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    start_after: datetime | None = None,
    start_before: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    rows, total = await calendar_service.get_events(
        db, start_after=start_after, start_before=start_before, page=page, limit=limit,
    )

    items = [_event_to_response(row) for row in rows]

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
        recurrence_rule=body.recurrence_rule,
        recurrence_end=body.recurrence_end,
        tags=serialize_tags(body.tags),
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    resp = EventResponse.model_validate(event)
    if event.tags:
        resp.tags = deserialize_tags(event.tags)
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
        resp.tags = deserialize_tags(event.tags)
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
    apply_model_updates(event, data)
    await db.commit()
    await db.refresh(event)

    resp = EventResponse.model_validate(event)
    if event.tags:
        resp.tags = deserialize_tags(event.tags)
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


@router.delete("/{event_id}/occurrences/{date}", status_code=204)
async def delete_event_occurrence(
    event_id: str,
    date: str,
    mode: str = Query("this_only", pattern="^(this_only|this_and_future|all)$"),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    """Delete a specific occurrence of a recurring event.

    mode: this_only — exclude just this date
          this_and_future — end recurrence before this date
          all — delete entire series
    """
    await calendar_service.delete_event_occurrence(db, event_id, date, mode)
    await db.commit()

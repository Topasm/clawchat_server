from datetime import datetime

from pydantic import BaseModel


class EventCreate(BaseModel):
    title: str
    description: str | None = None
    start_time: datetime
    end_time: datetime | None = None
    location: str | None = None
    is_all_day: bool = False
    reminder_minutes: int | None = None
    recurrence_rule: str | None = None
    recurrence_end: datetime | None = None
    tags: list[str] | None = None


class EventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    location: str | None = None
    is_all_day: bool | None = None
    reminder_minutes: int | None = None
    recurrence_rule: str | None = None
    recurrence_end: datetime | None = None
    tags: list[str] | None = None


class EventResponse(BaseModel):
    id: str
    title: str
    description: str | None = None
    start_time: datetime
    end_time: datetime | None = None
    location: str | None = None
    is_all_day: bool
    reminder_minutes: int | None = None
    recurrence_rule: str | None = None
    recurrence_end: datetime | None = None
    is_occurrence: bool = False
    occurrence_date: str | None = None
    recurring_event_id: str | None = None
    tags: list[str] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

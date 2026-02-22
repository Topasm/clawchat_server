"""Recurrence service — RRULE parsing and occurrence expansion."""

import json
from datetime import datetime, timedelta, timezone

from dateutil.rrule import rrulestr


def parse_rrule(rule_string: str, dtstart: datetime, range_start: datetime, range_end: datetime) -> list[datetime]:
    """Parse an RRULE string and return occurrence datetimes within the given range."""
    try:
        rule = rrulestr(rule_string, dtstart=dtstart)
        return list(rule.between(range_start, range_end, inc=True))
    except (ValueError, TypeError):
        return []


def generate_occurrences(event, range_start: datetime, range_end: datetime) -> list[dict]:
    """Expand a recurring event into virtual occurrence dicts within the range.

    Each returned dict has the same shape as EventResponse fields plus
    `is_occurrence=True` and `occurrence_date` (ISO date string).
    """
    if not event.recurrence_rule:
        return []

    # Parse exception dates
    exceptions: set[str] = set()
    if event.recurrence_exceptions:
        try:
            exceptions = set(json.loads(event.recurrence_exceptions))
        except (json.JSONDecodeError, TypeError):
            pass

    # Determine effective end of recurrence
    effective_end = range_end
    if event.recurrence_end and event.recurrence_end < effective_end:
        effective_end = event.recurrence_end

    dates = parse_rrule(event.recurrence_rule, event.start_time, range_start, effective_end)

    # Compute event duration for end_time calculation
    duration = timedelta(0)
    if event.end_time:
        duration = event.end_time - event.start_time

    occurrences = []
    for dt in dates:
        date_key = dt.date().isoformat()
        if date_key in exceptions:
            continue

        # Skip the original event date — it's already returned as the base event
        if dt == event.start_time:
            continue

        occ = {
            "id": event.id,
            "title": event.title,
            "description": event.description,
            "start_time": dt,
            "end_time": dt + duration if duration else None,
            "location": event.location,
            "is_all_day": event.is_all_day,
            "reminder_minutes": event.reminder_minutes,
            "recurrence_rule": event.recurrence_rule,
            "recurrence_end": event.recurrence_end,
            "is_occurrence": True,
            "occurrence_date": date_key,
            "recurring_event_id": event.id,
            "tags": event.tags,
            "created_at": event.created_at,
            "updated_at": event.updated_at,
        }
        occurrences.append(occ)

    return occurrences

"""Smart scheduling service — conflict detection, free slot finder, AI suggestions."""

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.event import Event
from services.ai_service import AIService
from services.recurrence_service import generate_occurrences
from utils import strip_markdown_fences

logger = logging.getLogger(__name__)

# Default working hours
DEFAULT_WORK_START = 9  # 9 AM
DEFAULT_WORK_END = 17  # 5 PM


async def find_conflicts(
    db: AsyncSession, start_time: datetime, end_time: datetime
) -> list[dict]:
    """Find events that overlap with the given time range, including recurring occurrences."""
    # Query events where event.start < end_time AND (event.end > start_time OR event has no end)
    q = select(Event).where(
        Event.start_time < end_time,
    )
    events = (await db.execute(q)).scalars().all()

    conflicts = []
    for event in events:
        evt_end = event.end_time or (event.start_time + timedelta(minutes=30))
        if evt_end > start_time:
            conflicts.append({
                "id": event.id,
                "title": event.title,
                "start_time": event.start_time.isoformat(),
                "end_time": evt_end.isoformat(),
            })

    # Check recurring event occurrences
    recurring_q = select(Event).where(Event.recurrence_rule != None)  # noqa: E711
    recurring_events = (await db.execute(recurring_q)).scalars().all()

    for event in recurring_events:
        occurrences = generate_occurrences(event, start_time - timedelta(days=1), end_time + timedelta(days=1))
        for occ in occurrences:
            occ_start = occ["start_time"]
            occ_end = occ["end_time"] or (occ_start + timedelta(minutes=30))
            if occ_start < end_time and occ_end > start_time:
                conflicts.append({
                    "id": event.id,
                    "title": event.title,
                    "start_time": occ_start.isoformat() if isinstance(occ_start, datetime) else occ_start,
                    "end_time": occ_end.isoformat() if isinstance(occ_end, datetime) else occ_end,
                    "is_occurrence": True,
                    "occurrence_date": occ.get("occurrence_date"),
                })

    return conflicts


async def find_free_slots(
    db: AsyncSession,
    range_start: datetime,
    range_end: datetime,
    duration_minutes: int = 60,
    working_hours: tuple[int, int] = (DEFAULT_WORK_START, DEFAULT_WORK_END),
) -> list[dict]:
    """Find free time slots of at least `duration_minutes` within working hours."""
    # Gather all busy intervals
    q = select(Event).where(
        Event.start_time >= range_start,
        Event.start_time <= range_end,
    )
    events = (await db.execute(q)).scalars().all()

    busy: list[tuple[datetime, datetime]] = []
    for event in events:
        evt_end = event.end_time or (event.start_time + timedelta(minutes=30))
        busy.append((event.start_time, evt_end))

    # Also check recurring events
    recurring_q = select(Event).where(Event.recurrence_rule != None)  # noqa: E711
    recurring_events = (await db.execute(recurring_q)).scalars().all()
    for event in recurring_events:
        occurrences = generate_occurrences(event, range_start, range_end)
        for occ in occurrences:
            occ_start = occ["start_time"]
            occ_end = occ["end_time"] or (occ_start + timedelta(minutes=30))
            busy.append((occ_start, occ_end))

    # Sort by start time
    busy.sort(key=lambda x: x[0])

    # Walk through each day in the range during working hours
    free_slots: list[dict] = []
    work_start_h, work_end_h = working_hours
    duration = timedelta(minutes=duration_minutes)

    current_day = range_start.date()
    end_day = range_end.date()

    while current_day <= end_day:
        day_start = datetime(current_day.year, current_day.month, current_day.day, work_start_h, 0, tzinfo=timezone.utc)
        day_end = datetime(current_day.year, current_day.month, current_day.day, work_end_h, 0, tzinfo=timezone.utc)

        # Skip weekends
        if current_day.weekday() >= 5:
            current_day += timedelta(days=1)
            continue

        # Get busy intervals for this day
        day_busy = [
            (max(b[0], day_start), min(b[1], day_end))
            for b in busy
            if b[0] < day_end and b[1] > day_start
        ]
        day_busy.sort(key=lambda x: x[0])

        # Find gaps
        cursor = day_start
        for b_start, b_end in day_busy:
            if b_start - cursor >= duration:
                free_slots.append({
                    "start": cursor.isoformat(),
                    "end": b_start.isoformat(),
                    "duration_minutes": int((b_start - cursor).total_seconds() / 60),
                })
            cursor = max(cursor, b_end)

        # Check remaining time after last busy block
        if day_end - cursor >= duration:
            free_slots.append({
                "start": cursor.isoformat(),
                "end": day_end.isoformat(),
                "duration_minutes": int((day_end - cursor).total_seconds() / 60),
            })

        current_day += timedelta(days=1)

    return free_slots


async def suggest_best_time(
    db: AsyncSession,
    ai_service: AIService,
    title: str,
    duration_minutes: int = 60,
    preferred_date: datetime | None = None,
    constraints: str | None = None,
) -> list[dict]:
    """Find free slots and use AI to rank the top 3 with reasoning."""
    # Default range: next 5 working days
    now = datetime.now(timezone.utc)
    range_start = preferred_date or now
    range_end = range_start + timedelta(days=7)

    free_slots = await find_free_slots(db, range_start, range_end, duration_minutes)

    if not free_slots:
        return []

    # Limit to first 10 slots for AI context
    slot_text = "\n".join(
        f"- Slot {i+1}: {s['start']} to {s['end']} ({s['duration_minutes']} min available)"
        for i, s in enumerate(free_slots[:10])
    )

    prompt = f"""I need to schedule "{title}" ({duration_minutes} minutes).
Here are my available time slots:

{slot_text}

{f"Additional constraints: {constraints}" if constraints else ""}

Pick the best 3 time slots and explain why each is good. Return your answer as a JSON array:
[{{"start": "ISO datetime", "end": "ISO datetime", "reason": "brief explanation"}}]

Return ONLY the JSON array, no other text."""

    try:
        response = await ai_service.generate_completion(
            system_prompt="You are a scheduling assistant. Analyze calendar availability and suggest optimal meeting times. Always return valid JSON.",
            user_message=prompt,
        )

        # Parse the JSON from AI response
        cleaned = strip_markdown_fences(response)

        suggestions = json.loads(cleaned)
        return suggestions[:3] if isinstance(suggestions, list) else []
    except Exception:
        logger.exception("AI scheduling suggestion failed")
        # Fallback: return first 3 free slots with generic reasoning
        return [
            {
                "start": s["start"],
                "end": (datetime.fromisoformat(s["start"]) + timedelta(minutes=duration_minutes)).isoformat(),
                "reason": "Available time slot",
            }
            for s in free_slots[:3]
        ]

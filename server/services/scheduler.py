"""Background asyncio scheduler for reminders, briefings, and maintenance."""

import asyncio
import logging
from datetime import datetime, time, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config import settings
from services import briefing_service, reminder_service
from services.ai_service import AIService
from ws.manager import ConnectionManager

logger = logging.getLogger(__name__)

# Default user ID for single-user app
DEFAULT_USER_ID = "default"


class Scheduler:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        ai_service: AIService,
        ws_manager: ConnectionManager,
    ):
        self.session_factory = session_factory
        self.ai_service = ai_service
        self.ws_manager = ws_manager
        self._tasks: list[asyncio.Task] = []

    def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self._reminder_loop(), name="scheduler-reminders"),
            asyncio.create_task(self._briefing_loop(), name="scheduler-briefing"),
            asyncio.create_task(self._midnight_reset_loop(), name="scheduler-midnight"),
        ]
        logger.info("Scheduler started with %d background tasks", len(self._tasks))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("Scheduler stopped")

    async def _reminder_loop(self) -> None:
        interval = settings.reminder_check_interval * 60  # minutes → seconds
        logger.info("Reminder loop started (interval: %ds)", interval)
        try:
            while True:
                try:
                    async with self.session_factory() as db:
                        sent = await reminder_service.run_all_checks(
                            db, self.ws_manager, DEFAULT_USER_ID
                        )
                        if sent:
                            logger.info("Sent %d reminder(s)", sent)
                except Exception:
                    logger.exception("Error in reminder loop")
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.debug("Reminder loop cancelled")

    async def _briefing_loop(self) -> None:
        logger.info("Briefing loop started (target: %s UTC)", settings.briefing_time)
        try:
            while True:
                now = datetime.now(timezone.utc)
                # Parse briefing_time setting (HH:MM)
                parts = settings.briefing_time.split(":")
                target_time = time(int(parts[0]), int(parts[1]), tzinfo=timezone.utc)
                target = datetime.combine(now.date(), target_time)

                if target <= now:
                    # Already past today's briefing time, schedule for tomorrow
                    target = datetime.combine(
                        now.date() + timedelta(days=1), target_time
                    )

                sleep_seconds = (target - now).total_seconds()
                logger.debug("Briefing scheduled in %.0fs", sleep_seconds)
                await asyncio.sleep(sleep_seconds)

                try:
                    async with self.session_factory() as db:
                        content = await briefing_service.generate_briefing(
                            db, self.ai_service
                        )
                        await self.ws_manager.send_json(DEFAULT_USER_ID, {
                            "type": "daily_briefing",
                            "data": {
                                "content": content,
                                "generated_at": datetime.now(timezone.utc).isoformat(),
                            },
                        })
                        logger.info("Daily briefing sent")
                except Exception:
                    logger.exception("Error generating daily briefing")
        except asyncio.CancelledError:
            logger.debug("Briefing loop cancelled")

    async def _midnight_reset_loop(self) -> None:
        logger.info("Midnight reset loop started")
        try:
            while True:
                now = datetime.now(timezone.utc)
                tomorrow = datetime.combine(
                    now.date() + timedelta(days=1),
                    time.min,
                    tzinfo=timezone.utc,
                )
                sleep_seconds = (tomorrow - now).total_seconds()
                await asyncio.sleep(sleep_seconds)

                reminder_service.clear_sent_reminders()
                logger.info("Midnight: cleared reminder dedup set")
        except asyncio.CancelledError:
            logger.debug("Midnight reset loop cancelled")

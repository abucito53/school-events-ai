"""Platform-independent mini scheduler (replaces launchd/cron). Runs
forever in the foreground - whether started natively or as the Docker
container's main process."""
from __future__ import annotations

import logging
import time
from datetime import datetime

from school_events.app import Application
from school_events.config import SchedulerConfig

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, app: Application):
        self._app = app
        self._config: SchedulerConfig = app.config.scheduler
        self._last_fetch: datetime | None = None
        self._last_weekly_date = None

    def run_forever(self) -> None:
        logger.info(
            "Scheduler started. Fetching every %d min, weekly email on weekday %d at %02d:%02d.",
            self._config.fetch_interval_minutes,
            self._config.weekly_weekday,
            self._config.weekly_hour,
            self._config.weekly_minute,
        )
        self._run_pipeline_safely()
        self._last_fetch = datetime.now()

        while True:
            now = datetime.now()

            if self._due_for_fetch(now):
                self._run_pipeline_safely()
                self._last_fetch = now

            if self._due_for_weekly(now):
                self._run_weekly_safely()
                self._last_weekly_date = now.date()

            time.sleep(60)

    def _due_for_fetch(self, now: datetime) -> bool:
        if self._last_fetch is None:
            return True
        elapsed = (now - self._last_fetch).total_seconds()
        return elapsed >= self._config.fetch_interval_minutes * 60

    def _due_for_weekly(self, now: datetime) -> bool:
        return (
            now.weekday() == self._config.weekly_weekday
            and now.hour == self._config.weekly_hour
            and now.minute >= self._config.weekly_minute
            and self._last_weekly_date != now.date()
        )

    def _run_pipeline_safely(self) -> None:
        try:
            fetched = self._app.gmail_fetcher().fetch_new()
            if fetched:
                logger.info("Fetched %d new email(s)", len(fetched))
            new_events = self._app.inbox_processor().run()
            logger.info("Detected %d new/updated event(s)", new_events)
        except Exception:
            logger.error("Error during fetch/process run", exc_info=True)

    def _run_weekly_safely(self) -> None:
        try:
            events = self._app.event_store.all()
            body = self._app.summary_builder().build(events)
            subject = f"Schultermine nächste Woche ({datetime.now().strftime('%d.%m.%Y')})"
            self._app.gmail_mailer().send(subject, body)
            logger.info("Sent weekly summary email")
        except Exception:
            logger.error("Error sending weekly summary", exc_info=True)

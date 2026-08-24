"""Plattformunabhängiger Mini-Scheduler (ersetzt launchd/cron). Läuft
dauerhaft im Vordergrund - egal ob nativ oder als Docker-Hauptprozess."""
from __future__ import annotations

import time
from datetime import datetime

from schultermine.app import Application
from schultermine.config import SchedulerConfig


class Scheduler:
    def __init__(self, app: Application):
        self._app = app
        self._config: SchedulerConfig = app.config.scheduler
        self._last_fetch: datetime | None = None
        self._last_weekly_date = None

    def run_forever(self) -> None:
        print(
            f"[Scheduler] Gestartet. Abholen alle "
            f"{self._config.fetch_interval_minutes} Min., Wochenmail an Tag "
            f"{self._config.weekly_weekday} um "
            f"{self._config.weekly_hour:02d}:{self._config.weekly_minute:02d}."
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
                print(f"[Scheduler] {len(fetched)} neue Mail(s) abgeholt.")
            new_events = self._app.inbox_processor().run()
            print(f"[Scheduler] {new_events} neue/aktualisierte Termine erkannt.")
        except Exception as e:
            print(f"[Scheduler] Fehler im Abhol-/Verarbeitungslauf: {e}")

    def _run_weekly_safely(self) -> None:
        try:
            events = self._app.event_store.all()
            body = self._app.summary_builder().build(events)
            subject = f"Schultermine nächste Woche ({datetime.now().strftime('%d.%m.%Y')})"
            self._app.gmail_mailer().send(subject, body)
            print("[Scheduler] Wöchentliche Zusammenfassung verschickt.")
        except Exception as e:
            print(f"[Scheduler] Fehler bei der Wochenzusammenfassung: {e}")

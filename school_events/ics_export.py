"""Writes a local .ics file as an offline backup (in addition to the Google Calendar)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

from icalendar import Calendar, Event, vText

from school_events.models import SchoolEvent

logger = logging.getLogger(__name__)


class IcsExporter:
    def __init__(self, calendar_dir: Path, calendar_name: str):
        # Filename changed from the old "schultermine.ics" as part of the
        # project rename. This file is only a local backup copy (the Google
        # Calendar sync is the primary path), so a one-time stale leftover
        # file under the old name is harmless - it just stops being updated.
        self._output_path = calendar_dir / "school-events.ics"
        self._calendar_name = calendar_name

    def write(self, events: list[SchoolEvent]) -> Path:
        cal = Calendar()
        cal.add("prodid", "-//school-events-ai//local//DE")
        cal.add("version", "2.0")
        cal.add("x-wr-calname", vText(self._calendar_name))

        for event in events:
            cal.add_component(self._to_vevent(event))

        self._output_path.write_bytes(cal.to_ical())
        logger.debug("Wrote local .ics backup with %d event(s) to %s", len(events), self._output_path)
        return self._output_path

    @staticmethod
    def _to_vevent(event: SchoolEvent) -> Event:
        vevent = Event()
        vevent.add("uid", f"{event.id}@school-events-ai.local")
        # User-facing text stays German, see calendar_sync.py for the same rule.
        title = f"⚠️ Frist: {event.title}" if event.is_deadline else event.title
        vevent.add("summary", title)

        if event.event_time:
            start_dt = datetime.combine(event.event_date, event.event_time)
            vevent.add("dtstart", start_dt)
            vevent.add("dtend", start_dt + timedelta(hours=1))
        else:
            vevent.add("dtstart", event.event_date)
            vevent.add("dtend", event.end_date + timedelta(days=1))

        if event.location:
            vevent.add("location", event.location)

        description_parts = [
            part for part in [
                event.description,
                f"Zuständig: {event.responsible_person}" if event.responsible_person else None,
                f"Kategorie: {event.category}" if event.category else None,
                f"Quelle: {event.source_path}" if event.source_path else None,
            ] if part
        ]
        vevent.add("description", "\n".join(description_parts))

        if event.source_path and Path(event.source_path).exists():
            vevent.add("attach", f"file://{event.source_path}")

        return vevent

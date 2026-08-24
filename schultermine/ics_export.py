"""Schreibt eine lokale .ics-Datei als Offline-Backup (zusätzlich zum Google Kalender)."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from icalendar import Calendar, Event, vText

from schultermine.models import SchoolEvent


class IcsExporter:
    def __init__(self, calendar_dir: Path, calendar_name: str):
        self._output_path = calendar_dir / "schultermine.ics"
        self._calendar_name = calendar_name

    def write(self, events: list[SchoolEvent]) -> Path:
        cal = Calendar()
        cal.add("prodid", "-//Schultermine-KI//lokal//DE")
        cal.add("version", "2.0")
        cal.add("x-wr-calname", vText(self._calendar_name))

        for event in events:
            cal.add_component(self._to_vevent(event))

        self._output_path.write_bytes(cal.to_ical())
        return self._output_path

    @staticmethod
    def _to_vevent(event: SchoolEvent) -> Event:
        vevent = Event()
        vevent.add("uid", f"{event.id}@schultermine-ki.local")
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

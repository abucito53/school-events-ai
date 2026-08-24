"""Baut den Text der wöchentlichen Zusammenfassungs-Mail."""
from __future__ import annotations

from datetime import datetime, timedelta

from schultermine.models import SchoolEvent


class WeeklySummaryBuilder:
    def __init__(self, calendar_name: str, horizon_days: int = 7):
        self._calendar_name = calendar_name
        self._horizon_days = horizon_days

    def build(self, events: list[SchoolEvent]) -> str:
        today = datetime.now().date()
        horizon = today + timedelta(days=self._horizon_days)
        upcoming = sorted(
            (e for e in events if e.event_date and today <= e.event_date <= horizon),
            key=lambda e: e.event_date,
        )

        if not upcoming:
            body = "Für die kommende Woche wurden keine neuen Schultermine gefunden.\n\n"
        else:
            lines = ["Schultermine der kommenden Woche:\n"]
            for event in upcoming:
                lines.append(self._format_event(event))
            body = "\n".join(lines) + "\n\n"

        body += (
            "-----\n"
            f"Die Termine sind bereits im Google Kalender '{self._calendar_name}' "
            "aktuell und werden automatisch in Proton Calendar synchronisiert "
            "(per Abo, siehe README).\n"
        )
        return body

    @staticmethod
    def _format_event(event: SchoolEvent) -> str:
        tag = event.event_date.strftime("%A, %d.%m.%Y")
        zeit = f" um {event.event_time.strftime('%H:%M')}" if event.event_time else ""
        marker = "⚠️ FRIST: " if event.is_deadline else ""
        lines = [f"\n{marker}{tag}{zeit} – {event.title}"]
        if event.location:
            lines.append(f"  Ort: {event.location}")
        if event.responsible_person:
            lines.append(f"  Zuständig: {event.responsible_person}")
        if event.description:
            lines.append(f"  {event.description}")
        if event.source_path:
            lines.append(f"  Quelle: {event.source_path}")
        return "\n".join(lines)

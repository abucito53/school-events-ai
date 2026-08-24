"""Synchronisiert erkannte Termine in einen dedizierten Google Kalender.

Proton Calendar abonniert anschliessend die von Google automatisch erzeugte
"geheime iCal-Adresse" dieses Kalenders (siehe README). Jeder Termin wird
über eine stabile ID (extendedProperties.private) wiedererkannt: existiert
er schon, wird er aktualisiert statt dupliziert.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from schultermine.google_auth import GoogleAuthenticator
from schultermine.models import SchoolEvent

_PROPERTY_KEY = "schultermine_id"


class GoogleCalendarSync:
    def __init__(self, auth: GoogleAuthenticator, calendar_name: str):
        self._auth = auth
        self._calendar_name = calendar_name

    def sync(self, events: list[SchoolEvent]) -> int:
        service = self._auth.calendar_service()
        calendar_id = self._get_or_create_calendar(service)

        synced = 0
        for event in events:
            body = self._to_event_body(event)
            existing_id = self._find_existing_event_id(service, calendar_id, event.id)
            if existing_id:
                service.events().update(calendarId=calendar_id, eventId=existing_id, body=body).execute()
            else:
                service.events().insert(calendarId=calendar_id, body=body).execute()
            synced += 1
        return synced

    def _get_or_create_calendar(self, service) -> str:
        calendars = service.calendarList().list().execute().get("items", [])
        for cal in calendars:
            if cal.get("summary") == self._calendar_name:
                return cal["id"]
        created = service.calendars().insert(
            body={"summary": self._calendar_name, "timeZone": "Europe/Zurich"}
        ).execute()
        return created["id"]

    @staticmethod
    def _find_existing_event_id(service, calendar_id: str, schultermine_id: str) -> str | None:
        resp = service.events().list(
            calendarId=calendar_id,
            privateExtendedProperty=f"{_PROPERTY_KEY}={schultermine_id}",
            showDeleted=False,
        ).execute()
        items = resp.get("items", [])
        return items[0]["id"] if items else None

    @staticmethod
    def _to_event_body(event: SchoolEvent) -> dict:
        if event.event_time:
            start_dt = datetime.combine(event.event_date, event.event_time)
            end_dt = start_dt + timedelta(hours=1)
            start = {"dateTime": start_dt.isoformat(), "timeZone": "Europe/Zurich"}
            end = {"dateTime": end_dt.isoformat(), "timeZone": "Europe/Zurich"}
        else:
            end_date = event.end_date + timedelta(days=1)
            start = {"date": event.event_date.isoformat()}
            end = {"date": end_date.isoformat()}

        description_parts = [
            part for part in [
                event.description,
                f"Zuständig: {event.responsible_person}" if event.responsible_person else None,
                f"Kategorie: {event.category}" if event.category else None,
                f"Quelle (lokal): {event.source_path}" if event.source_path else None,
            ] if part
        ]

        title = event.title
        if event.is_deadline:
            title = f"⚠️ Frist: {title}"

        return {
            "summary": title,
            "location": event.location or "",
            "description": "\n".join(description_parts),
            "start": start,
            "end": end,
            "extendedProperties": {"private": {_PROPERTY_KEY: event.id}},
        }

"""Syncs detected events into a dedicated Google Calendar.

Proton Calendar then subscribes to the "secret iCal address" Google
generates automatically for this calendar (see README). Each event is
recognized via a stable ID (extendedProperties.private): if it already
exists, it gets updated instead of duplicated.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from school_events.google_auth import GoogleAuthenticator
from school_events.models import SchoolEvent

logger = logging.getLogger(__name__)

# Value stays as-is even after the project rename: it's already stored in
# extendedProperties.private on every event synced so far. Changing it would
# make sync stop recognizing existing calendar events as "already synced"
# and start duplicating them.
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

        logger.info("Synced %d event(s) to Google Calendar '%s'", synced, self._calendar_name)
        return synced

    def _get_or_create_calendar(self, service) -> str:
        calendars = service.calendarList().list().execute().get("items", [])
        for cal in calendars:
            if cal.get("summary") == self._calendar_name:
                return cal["id"]
        logger.info("Calendar '%s' does not exist yet, creating it", self._calendar_name)
        created = service.calendars().insert(
            body={"summary": self._calendar_name, "timeZone": "Europe/Zurich"}
        ).execute()
        return created["id"]

    @staticmethod
    def _find_existing_event_id(service, calendar_id: str, event_id: str) -> str | None:
        resp = service.events().list(
            calendarId=calendar_id,
            privateExtendedProperty=f"{_PROPERTY_KEY}={event_id}",
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

        # These labels are user-facing (they end up in the calendar entry
        # description the family reads), so they stay German on purpose,
        # unlike the rest of this file.
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

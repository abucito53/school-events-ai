"""Domänenmodell: ein einzelner erkannter Schultermin."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time as dt_time
from typing import Optional


@dataclass
class SchoolEvent:
    id: str
    title: str
    event_date: date
    end_date: date
    event_time: Optional[dt_time] = None
    location: Optional[str] = None
    responsible_person: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    is_deadline: bool = False
    source_path: Optional[str] = None
    extracted_at: datetime = field(default_factory=datetime.now)

    @classmethod
    def from_llm_dict(cls, raw: dict, event_id: str, source_path: str) -> Optional["SchoolEvent"]:
        """Baut ein SchoolEvent aus dem vom LLM gelieferten JSON-Objekt.
        Gibt None zurück, falls kein gültiges Datum enthalten ist."""
        date_str = raw.get("date")
        if not date_str:
            return None
        try:
            event_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None

        end_date_str = raw.get("end_date") or date_str
        try:
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            end_date = event_date

        event_time = None
        time_str = raw.get("time")
        if time_str:
            try:
                event_time = datetime.strptime(time_str, "%H:%M").time()
            except ValueError:
                event_time = None

        return cls(
            id=event_id,
            title=(raw.get("title") or "Schultermin").strip(),
            event_date=event_date,
            end_date=end_date,
            event_time=event_time,
            location=raw.get("location") or None,
            responsible_person=raw.get("responsible_person") or None,
            category=raw.get("category") or None,
            description=raw.get("description") or None,
            is_deadline=bool(raw.get("is_deadline", False)),
            source_path=source_path,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "date": self.event_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "time": self.event_time.strftime("%H:%M") if self.event_time else None,
            "location": self.location,
            "responsible_person": self.responsible_person,
            "category": self.category,
            "description": self.description,
            "is_deadline": self.is_deadline,
            "source_path": self.source_path,
            "extracted_at": self.extracted_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SchoolEvent":
        return cls(
            id=data["id"],
            title=data["title"],
            event_date=date.fromisoformat(data["date"]),
            end_date=date.fromisoformat(data.get("end_date") or data["date"]),
            event_time=dt_time.fromisoformat(data["time"]) if data.get("time") else None,
            location=data.get("location"),
            responsible_person=data.get("responsible_person"),
            category=data.get("category"),
            description=data.get("description"),
            is_deadline=bool(data.get("is_deadline", False)),
            source_path=data.get("source_path"),
            extracted_at=datetime.fromisoformat(data["extracted_at"]) if data.get("extracted_at") else datetime.now(),
        )

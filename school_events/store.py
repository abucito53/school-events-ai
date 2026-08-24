"""Persistence: detected events + dedup state as JSON files."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from school_events.models import SchoolEvent


class JsonSet:
    """A set of IDs/hashes mirrored to disk (e.g. already-processed files)."""

    def __init__(self, path: Path):
        self._path = path
        self._items: set[str] = set(self._read())

    def _read(self) -> list[str]:
        if self._path.exists():
            with open(self._path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def __contains__(self, item: str) -> bool:
        return item in self._items

    def add(self, item: str) -> None:
        self._items.add(item)

    def save(self) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(sorted(self._items), f, ensure_ascii=False, indent=2)


class EventRepository:
    """Manages events.json - all events detected so far.

    Plain state storage, overwritten on every save - NOT an event-sourcing
    store despite the similar-sounding name. See the README for why this
    distinction matters.
    """

    def __init__(self, path: Path):
        self._path = path
        self._events: dict[str, SchoolEvent] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            with open(self._path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            for item in raw:
                ev = SchoolEvent.from_dict(item)
                self._events[ev.id] = ev

    def upsert(self, event: SchoolEvent) -> None:
        self._events[event.id] = event

    def all(self) -> list[SchoolEvent]:
        return sorted(self._events.values(), key=lambda e: e.event_date)

    def save(self) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump([e.to_dict() for e in self._events.values()], f, ensure_ascii=False, indent=2)


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:24]


def stable_event_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]

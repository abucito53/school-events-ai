"""Orchestriert die Verarbeitung des Eingangsordners: Text extrahieren, ans
LLM schicken, Datei archivieren, Event-Store + Kalender aktualisieren."""
from __future__ import annotations

from pathlib import Path

from schultermine.calendar_sync import GoogleCalendarSync
from schultermine.config import AppConfig
from schultermine.content import ContentExtractor
from schultermine.ics_export import IcsExporter
from schultermine.ollama_client import OllamaEventExtractor
from schultermine.store import EventStore, JsonSet, content_hash


class InboxProcessor:
    def __init__(
        self,
        config: AppConfig,
        content_extractor: ContentExtractor,
        llm_extractor: OllamaEventExtractor,
        event_store: EventStore,
        ics_exporter: IcsExporter,
        calendar_sync: GoogleCalendarSync | None,
    ):
        self._config = config
        self._content_extractor = content_extractor
        self._llm_extractor = llm_extractor
        self._event_store = event_store
        self._ics_exporter = ics_exporter
        self._calendar_sync = calendar_sync
        self._processed = JsonSet(config.paths.data / "processed_hashes.json")

    def run(self) -> int:
        """Verarbeitet alle neuen Dateien im Eingangsordner. Gibt die Anzahl
        neu erkannter/aktualisierter Termine zurück."""
        candidates = sorted(
            p for p in self._config.paths.inbox.iterdir()
            if p.is_file() and p.suffix.lower() in (".pdf", ".eml")
        )
        if not candidates:
            return 0

        new_event_count = 0
        for path in candidates:
            new_event_count += self._process_one(path)

        self._event_store.save()
        self._ics_exporter.write(self._event_store.all())

        if self._calendar_sync:
            self._calendar_sync.sync(self._event_store.all())

        return new_event_count

    def _process_one(self, path: Path) -> int:
        file_hash = content_hash(path.read_bytes())
        if file_hash in self._processed:
            return 0

        try:
            extracted = self._content_extractor.extract(path)
        except Exception as e:
            print(f"  {path.name}: konnte nicht gelesen werden ({e}), übersprungen.")
            self._processed.add(file_hash)
            self._processed.save()
            return 0

        if not extracted.text.strip():
            self._processed.add(file_hash)
            self._processed.save()
            return 0

        archive_path = self._archive(path)
        source_path = extracted.primary_source or archive_path

        events = self._llm_extractor.extract(extracted.text, file_hash, source_path)
        for event in events:
            self._event_store.upsert(event)

        self._processed.add(file_hash)
        self._processed.save()
        return len(events)

    def _archive(self, path: Path) -> Path:
        archive_path = self._config.paths.originals / path.name
        counter = 1
        while archive_path.exists():
            archive_path = self._config.paths.originals / f"{path.stem}_{counter}{path.suffix}"
            counter += 1
        path.rename(archive_path)
        return archive_path

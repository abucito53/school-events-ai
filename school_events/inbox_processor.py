"""Orchestrates processing of the inbox folder: extract text, send to the
LLM, archive the file, update the event repository + calendar."""
from __future__ import annotations

import logging
from pathlib import Path

from school_events.calendar_sync import GoogleCalendarSync
from school_events.config import AppConfig
from school_events.content import ContentExtractor
from school_events.ics_export import IcsExporter
from school_events.ollama_client import OllamaEventExtractor
from school_events.store import EventRepository, JsonSet, content_hash

logger = logging.getLogger(__name__)


class InboxProcessor:
    def __init__(
        self,
        config: AppConfig,
        content_extractor: ContentExtractor,
        llm_extractor: OllamaEventExtractor,
        event_store: EventRepository,
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
        """Processes all new files in the inbox folder. Returns the number
        of newly detected/updated events."""
        candidates = sorted(
            p for p in self._config.paths.inbox.iterdir()
            if p.is_file() and p.suffix.lower() in (".pdf", ".eml")
        )
        if not candidates:
            logger.debug("Nothing to process in %s", self._config.paths.inbox)
            return 0

        logger.info("Found %d file(s) to process in %s", len(candidates), self._config.paths.inbox)

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
            logger.debug("%s already processed (hash=%s), skipping", path.name, file_hash)
            return 0

        logger.info("Processing %s", path.name)
        try:
            extracted = self._content_extractor.extract(path)
        except Exception:
            logger.warning("Could not read %s, skipping", path.name, exc_info=True)
            self._processed.add(file_hash)
            self._processed.save()
            return 0

        if not extracted.text.strip():
            logger.info("%s contains no usable text, skipping", path.name)
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
        logger.debug("Archived %s -> %s", path.name, archive_path)
        return archive_path

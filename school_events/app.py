"""Wires up all classes based on the config (simple manual dependency
injection, no framework needed for a project this size)."""
from __future__ import annotations

from school_events.calendar_sync import GoogleCalendarSync
from school_events.config import AppConfig
from school_events.content import ContentExtractor
from school_events.gmail_fetcher import GmailFetcher
from school_events.gmail_mailer import GmailMailer
from school_events.google_auth import GoogleAuthenticator
from school_events.ics_export import IcsExporter
from school_events.inbox_processor import InboxProcessor
from school_events.ollama_client import OllamaEventExtractor
from school_events.store import EventRepository
from school_events.summary import WeeklySummaryBuilder


class Application:
    """Central entry point: creates and wires up all components."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.auth = GoogleAuthenticator(config.gmail)
        self.event_store = EventRepository(config.paths.data / "events.json")

    def gmail_fetcher(self) -> GmailFetcher:
        return GmailFetcher(self.auth, self.config.gmail, self.config.paths)

    def gmail_mailer(self) -> GmailMailer:
        return GmailMailer(self.auth, self.config.gmail.send_to)

    def inbox_processor(self) -> InboxProcessor:
        calendar_sync = (
            GoogleCalendarSync(self.auth, self.config.calendar_name)
            if self.config.gmail.sync_calendar else None
        )
        return InboxProcessor(
            config=self.config,
            content_extractor=ContentExtractor(self.config.paths.originals),
            llm_extractor=OllamaEventExtractor(self.config.ollama),
            event_store=self.event_store,
            ics_exporter=IcsExporter(self.config.paths.calendar, self.config.calendar_name),
            calendar_sync=calendar_sync,
        )

    def summary_builder(self) -> WeeklySummaryBuilder:
        return WeeklySummaryBuilder(self.config.calendar_name)

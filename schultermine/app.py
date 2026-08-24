"""Baut alle Klassen anhand der Config zusammen (einfache manuelle
Dependency-Injection, kein Framework nötig für dieses Projekt)."""
from __future__ import annotations

from schultermine.calendar_sync import GoogleCalendarSync
from schultermine.config import AppConfig
from schultermine.content import ContentExtractor
from schultermine.gmail_fetcher import GmailFetcher
from schultermine.gmail_mailer import GmailMailer
from schultermine.google_auth import GoogleAuthenticator
from schultermine.ics_export import IcsExporter
from schultermine.inbox_processor import InboxProcessor
from schultermine.llm import OllamaEventExtractor
from schultermine.store import EventStore
from schultermine.summary import WeeklySummaryBuilder


class Application:
    """Zentraler Einstiegspunkt: erzeugt und verdrahtet alle Komponenten."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.auth = GoogleAuthenticator(config.gmail)
        self.event_store = EventStore(config.paths.data / "events.json")

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

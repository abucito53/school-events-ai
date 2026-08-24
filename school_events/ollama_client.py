"""Client for the local Ollama model used for event extraction.

Deliberately named "ollama_client", not "llm": there is no provider
abstraction here, this module talks to one concrete thing (the Ollama HTTP
API), so the name should say that plainly.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

import requests

from school_events.config import OllamaConfig
from school_events.models import SchoolEvent
from school_events.store import stable_event_id

logger = logging.getLogger(__name__)

# The prompt is deliberately in German: the source material (German school
# letters) is German, and we want the extracted field values (title,
# category, description, ...) in German too, since they end up directly in
# the user's calendar and summary email.
EXTRACTION_PROMPT = """Du bekommst den Inhalt einer Schul-Mitteilung (E-Mail-Text \
und/oder PDF-Text, z.B. Elternbrief, Stundenplan-Änderung, Ausflug, \
Elterngespräch, Ferienplan, Anmeldeschluss). Extrahiere ALLE konkreten \
Termine/Fristen daraus als JSON-Array. Wenn kein konkreter Termin (Datum) \
enthalten ist, gib ein leeres Array [] zurück.

Für jeden Termin gib folgende Felder zurück:
- "title": kurzer, klarer Titel (max. 8 Wörter)
- "date": Datum im Format YYYY-MM-DD (das Jahr ggf. sinnvoll ergänzen)
- "end_date": Enddatum falls mehrtägig, sonst gleich wie "date"
- "time": Uhrzeit im Format HH:MM, oder null falls keine genannt wird
- "location": Ort, oder null
- "responsible_person": zuständige Person/Absender, oder null
- "category": eine kurze Kategorie, z.B. "Elternabend", "Ausflug", "Ferien", \
"Anmeldeschluss", "Sonstiges"
- "description": 1-2 Sätze Zusammenfassung der relevanten Details
- "is_deadline": true/false, ob es sich um eine Frist/Anmeldeschluss statt \
einen Termin handelt

Gib AUSSCHLIESSLICH das JSON-Array zurück, keinen weiteren Text.

INHALT:
---
{content}
---
"""

MAX_CONTENT_CHARS = 12_000


class OllamaEventExtractor:
    """Sends text to the local Ollama model and returns detected SchoolEvents.

    This is a plain single-shot extractor, not an agent: one fixed prompt
    in, one JSON response out. No loop, no tool calls, no decisions about
    what to do next.
    """

    def __init__(self, config: OllamaConfig):
        self._config = config

    def extract(self, content: str, content_hash: str, source_path: Path) -> list[SchoolEvent]:
        truncated = content[:MAX_CONTENT_CHARS]
        if len(content) > MAX_CONTENT_CHARS:
            logger.debug(
                "Content for %s truncated from %d to %d chars before sending to Ollama",
                source_path, len(content), MAX_CONTENT_CHARS,
            )

        raw_response = self._call_ollama(truncated, content_hash)
        raw_events = self._parse_json_array(raw_response, content_hash)

        events = []
        for raw in raw_events:
            event_id = stable_event_id(content_hash, raw.get("title", ""), raw.get("date", ""))
            event = SchoolEvent.from_llm_dict(raw, event_id=event_id, source_path=str(source_path))
            if event:
                events.append(event)
            else:
                logger.debug(
                    "Skipped LLM item without a usable date (hash=%s): %r",
                    content_hash, raw,
                )

        logger.info(
            "Extracted %d event(s) from %s (hash=%s)",
            len(events), source_path.name, content_hash,
        )
        return events

    def _call_ollama(self, content: str, content_hash: str) -> str:
        url = self._config.url.rstrip("/") + "/api/generate"
        logger.debug(
            "Calling Ollama model=%s at %s with %d chars of content (hash=%s)",
            self._config.model, url, len(content), content_hash,
        )

        start = time.monotonic()
        try:
            response = requests.post(
                url,
                json={
                    "model": self._config.model,
                    "prompt": EXTRACTION_PROMPT.format(content=content),
                    "stream": False,
                    "options": {"temperature": 0.1},
                },
                timeout=300,
            )
            response.raise_for_status()
        except requests.RequestException:
            elapsed = time.monotonic() - start
            logger.error(
                "Ollama request failed after %.1fs (model=%s, hash=%s)",
                elapsed, self._config.model, content_hash, exc_info=True,
            )
            raise

        elapsed = time.monotonic() - start
        raw_text = response.json().get("response", "")
        logger.debug(
            "Ollama responded in %.1fs with %d chars (hash=%s)",
            elapsed, len(raw_text), content_hash,
        )
        return raw_text

    @staticmethod
    def _parse_json_array(raw: str, content_hash: str) -> list[dict]:
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            logger.warning(
                "No JSON array found in Ollama's response (hash=%s); raw response: %.500s",
                content_hash, raw,
            )
            return []
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            logger.warning(
                "Could not parse JSON array from Ollama's response (hash=%s); matched text: %.500s",
                content_hash, match.group(0), exc_info=True,
            )
            return []

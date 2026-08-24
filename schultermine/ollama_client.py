"""Anbindung ans lokale Ollama-Modell zur Terminextraktion."""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests

from schultermine.config import OllamaConfig
from schultermine.models import SchoolEvent
from schultermine.store import stable_event_id

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
    """Schickt Text ans lokale Ollama-Modell und liefert erkannte SchoolEvents."""

    def __init__(self, config: OllamaConfig):
        self._config = config

    def extract(self, content: str, content_hash: str, source_path: Path) -> list[SchoolEvent]:
        raw_response = self._call_ollama(content[:MAX_CONTENT_CHARS])
        raw_events = self._parse_json_array(raw_response)

        events = []
        for raw in raw_events:
            event_id = stable_event_id(content_hash, raw.get("title", ""), raw.get("date", ""))
            event = SchoolEvent.from_llm_dict(raw, event_id=event_id, source_path=str(source_path))
            if event:
                events.append(event)
        return events

    def _call_ollama(self, content: str) -> str:
        url = self._config.url.rstrip("/") + "/api/generate"
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
        return response.json().get("response", "")

    @staticmethod
    def _parse_json_array(raw: str) -> list[dict]:
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            return []
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return []

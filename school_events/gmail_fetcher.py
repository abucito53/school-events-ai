"""Fetches emails from the configured Gmail label via the API (read-only)
and drops them as .eml files into the inbox folder."""
from __future__ import annotations

import base64
import logging
from pathlib import Path

from school_events.config import GmailOAuthConfig, Paths
from school_events.google_auth import GoogleAuthenticator
from school_events.store import JsonSet

logger = logging.getLogger(__name__)


class GmailFetcher:
    def __init__(self, auth: GoogleAuthenticator, gmail_config: GmailOAuthConfig, paths: Paths):
        self._auth = auth
        self._gmail_config = gmail_config
        self._paths = paths
        self._fetched = JsonSet(paths.data / "gmail_fetched_ids.json")

    def fetch_new(self) -> list[Path]:
        service = self._auth.gmail_service()
        label_id = self._resolve_label_id(service, self._gmail_config.label_name)
        message_ids = self._list_message_ids(service, label_id)

        new_ids = [m for m in message_ids if m not in self._fetched]
        logger.debug(
            "Label '%s': %d message(s) total, %d new",
            self._gmail_config.label_name, len(message_ids), len(new_ids),
        )
        if not new_ids:
            return []

        written: list[Path] = []
        for msg_id in new_ids:
            raw_bytes = self._get_raw_message(service, msg_id)
            out_path = self._paths.inbox / f"gmail_{msg_id}.eml"
            out_path.write_bytes(raw_bytes)
            written.append(out_path)
            self._fetched.add(msg_id)
            logger.debug("Fetched message %s -> %s", msg_id, out_path.name)

        self._fetched.save()
        logger.info("Fetched %d new message(s) from label '%s'", len(written), self._gmail_config.label_name)
        return written

    @staticmethod
    def _resolve_label_id(service, label_name: str) -> str:
        labels = service.users().labels().list(userId="me").execute().get("labels", [])
        for label in labels:
            if label["name"].lower() == label_name.lower():
                return label["id"]
        raise ValueError(
            f"Label '{label_name}' does not exist in this Gmail account. "
            "Create it first (see README)."
        )

    @staticmethod
    def _list_message_ids(service, label_id: str) -> list[str]:
        ids: list[str] = []
        page_token = None
        while True:
            resp = service.users().messages().list(
                userId="me", labelIds=[label_id], pageToken=page_token
            ).execute()
            ids.extend(m["id"] for m in resp.get("messages", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return ids

    @staticmethod
    def _get_raw_message(service, message_id: str) -> bytes:
        msg = service.users().messages().get(userId="me", id=message_id, format="raw").execute()
        return base64.urlsafe_b64decode(msg["raw"])

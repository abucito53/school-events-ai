"""Sends the weekly summary via the Gmail API (no SMTP/password)."""
from __future__ import annotations

import base64
import logging
from email.mime.text import MIMEText

from school_events.google_auth import GoogleAuthenticator

logger = logging.getLogger(__name__)


class GmailMailer:
    def __init__(self, auth: GoogleAuthenticator, send_to: str):
        self._auth = auth
        self._send_to = send_to

    def send(self, subject: str, body: str) -> None:
        service = self._auth.gmail_service()
        message = MIMEText(body, "plain", "utf-8")
        message["to"] = self._send_to
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        logger.info("Sent email %r to %s", subject, self._send_to)

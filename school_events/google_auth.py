"""OAuth2 authentication for the dedicated Gmail account (Gmail API + Calendar API).

No password is ever stored - only a token limited to three scopes, revocable
at any time at myaccount.google.com/permissions: read mail, send mail,
manage calendar.
"""
from __future__ import annotations

import logging

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build

from school_events.config import GmailOAuthConfig

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
]


class GoogleAuthenticator:
    """Manages credentials and builds authenticated API clients (Resource objects)."""

    def __init__(self, config: GmailOAuthConfig):
        self._config = config
        self._credentials: Credentials | None = None

    def credentials(self) -> Credentials:
        if self._credentials and self._credentials.valid:
            return self._credentials

        creds = self._load_cached_credentials()

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("OAuth2 token expired, refreshing")
                creds.refresh(Request())
            else:
                logger.info("No valid token found, starting OAuth2 consent flow (a browser will open)")
                creds = self._run_consent_flow()
            self._config.token_path.write_text(creds.to_json())
            logger.info("Credentials saved to %s", self._config.token_path)

        self._credentials = creds
        return creds

    def _load_cached_credentials(self) -> Credentials | None:
        if self._config.token_path.exists():
            return Credentials.from_authorized_user_file(str(self._config.token_path), SCOPES)
        return None

    def _run_consent_flow(self) -> Credentials:
        if not self._config.credentials_path.exists():
            raise FileNotFoundError(
                f"{self._config.credentials_path} not found. See the README, "
                "section 'OAuth2 mit Gmail einrichten'."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(self._config.credentials_path), SCOPES)
        # Opens a browser once (only needed the first time, or once the
        # refresh token has become invalid). Requires a real desktop - see
        # the README for the note on why this doesn't work inside Docker.
        return flow.run_local_server(port=0)

    def gmail_service(self) -> Resource:
        return build("gmail", "v1", credentials=self.credentials(), cache_discovery=False)

    def calendar_service(self) -> Resource:
        return build("calendar", "v3", credentials=self.credentials(), cache_discovery=False)

"""OAuth2-Authentifizierung fürs dedizierte Gmail-Konto (Gmail-API + Calendar-API).

Kein Passwort wird je gespeichert - nur ein auf drei Rechte beschränktes,
jederzeit unter myaccount.google.com/permissions widerrufbares Token:
Mails lesen, Mails senden, Kalender verwalten.
"""
from __future__ import annotations

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build

from schultermine.config import GmailOAuthConfig

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
]


class GoogleAuthenticator:
    """Verwaltet Credentials und baut authentifizierte API-Clients (Resource-Objekte)."""

    def __init__(self, config: GmailOAuthConfig):
        self._config = config
        self._credentials: Credentials | None = None

    def credentials(self) -> Credentials:
        if self._credentials and self._credentials.valid:
            return self._credentials

        creds = self._load_cached_credentials()

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                creds = self._run_consent_flow()
            self._config.token_path.write_text(creds.to_json())

        self._credentials = creds
        return creds

    def _load_cached_credentials(self) -> Credentials | None:
        if self._config.token_path.exists():
            return Credentials.from_authorized_user_file(str(self._config.token_path), SCOPES)
        return None

    def _run_consent_flow(self) -> Credentials:
        if not self._config.credentials_path.exists():
            raise FileNotFoundError(
                f"{self._config.credentials_path} nicht gefunden. Siehe README, "
                "Abschnitt 'OAuth2 mit Gmail einrichten'."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(self._config.credentials_path), SCOPES)
        # Öffnet einmalig einen Browser (nur nötig beim ersten Mal bzw. falls
        # der Refresh-Token ungültig geworden ist). Funktioniert nur mit
        # echtem Desktop - siehe README für den Docker-Hinweis dazu.
        return flow.run_local_server(port=0)

    def gmail_service(self) -> Resource:
        return build("gmail", "v1", credentials=self.credentials(), cache_discovery=False)

    def calendar_service(self) -> Resource:
        return build("calendar", "v3", credentials=self.credentials(), cache_discovery=False)

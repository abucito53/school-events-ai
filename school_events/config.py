"""Loads and validates config.yaml into a typed AppConfig."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Paths:
    base_dir: Path
    inbox: Path
    originals: Path
    data: Path
    calendar: Path

    @classmethod
    def from_base(cls, base_dir: Path) -> "Paths":
        base_dir = base_dir.expanduser()
        paths = cls(
            base_dir=base_dir,
            # Folder name stays German ("eingang") even in this
            # English-language code: it's a user-facing path the user
            # already drops files into (see README) - renaming it would
            # silently break an existing installation.
            inbox=base_dir / "eingang",
            originals=base_dir / "originals",
            data=base_dir / "data",
            calendar=base_dir / "calendar",
        )
        for d in (paths.base_dir, paths.inbox, paths.originals, paths.data, paths.calendar):
            d.mkdir(parents=True, exist_ok=True)
        return paths


@dataclass(frozen=True)
class GmailOAuthConfig:
    credentials_path: Path
    token_path: Path
    label_name: str
    send_to: str
    sync_calendar: bool


@dataclass(frozen=True)
class OllamaConfig:
    model: str
    url: str


@dataclass(frozen=True)
class SchedulerConfig:
    fetch_interval_minutes: int = 60
    weekly_weekday: int = 6  # 0=Monday ... 6=Sunday
    weekly_hour: int = 18
    weekly_minute: int = 30


@dataclass(frozen=True)
class AppConfig:
    paths: Paths
    gmail: GmailOAuthConfig
    ollama: OllamaConfig
    calendar_name: str
    scheduler: SchedulerConfig

    @classmethod
    def load(cls, config_path: str | Path = "config.yaml") -> "AppConfig":
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(
                f"{path} not found. Copy config.example.yaml to config.yaml "
                "and fill in your values."
            )
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        paths = Paths.from_base(Path(raw["paths"]["base_dir"]))

        gmail_raw = raw["gmail_oauth"]
        gmail = GmailOAuthConfig(
            credentials_path=Path(gmail_raw["credentials_path"]).expanduser(),
            token_path=Path(gmail_raw["token_path"]).expanduser(),
            label_name=gmail_raw["label_name"],
            send_to=gmail_raw["send_to"],
            sync_calendar=bool(gmail_raw.get("sync_calendar", True)),
        )

        ollama = OllamaConfig(
            model=raw["ollama"]["model"],
            url=raw["ollama"]["url"],
        )

        scheduler_raw = raw.get("scheduler", {})
        scheduler = SchedulerConfig(
            fetch_interval_minutes=int(scheduler_raw.get("fetch_interval_minutes", 60)),
            weekly_weekday=int(scheduler_raw.get("weekly_weekday", 6)),
            weekly_hour=int(scheduler_raw.get("weekly_hour", 18)),
            weekly_minute=int(scheduler_raw.get("weekly_minute", 30)),
        )

        return cls(
            paths=paths,
            gmail=gmail,
            ollama=ollama,
            calendar_name=raw["calendar"]["calendar_name"],
            scheduler=scheduler,
        )

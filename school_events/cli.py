"""Command line interface: python3 -m school_events <command>"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime

from school_events.app import Application
from school_events.config import AppConfig
from school_events.logging_config import configure_logging
from school_events.scheduler import Scheduler

logger = logging.getLogger(__name__)


def cmd_login(app: Application) -> None:
    """Runs only the OAuth2 login (opens a browser if no valid token is
    present) and creates token.json. Does nothing else - no email fetch,
    no processing."""
    app.auth.credentials()
    logger.info("Login successful. Token saved to: %s", app.config.gmail.token_path)


def cmd_fetch(app: Application) -> None:
    fetched = app.gmail_fetcher().fetch_new()
    if fetched:
        logger.info("Fetched %d new email(s): %s", len(fetched), [p.name for p in fetched])
    else:
        logger.info("No new emails in the configured label.")


def cmd_process(app: Application) -> None:
    new_events = app.inbox_processor().run()
    logger.info("Done. Detected %d new/updated event(s).", new_events)


def cmd_weekly(app: Application) -> None:
    events = app.event_store.all()
    body = app.summary_builder().build(events)
    subject = f"Schultermine nächste Woche ({datetime.now().strftime('%d.%m.%Y')})"
    app.gmail_mailer().send(subject, body)
    logger.info("Weekly summary sent.\n%s", body)


def cmd_scheduler(app: Application) -> None:
    Scheduler(app).run_forever()


COMMANDS = {
    "login": cmd_login,
    "fetch": cmd_fetch,
    "process": cmd_process,
    "weekly": cmd_weekly,
    "scheduler": cmd_scheduler,
}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="school-events")
    parser.add_argument("command", choices=COMMANDS.keys())
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Use DEBUG to see full detail on every Ollama request/response.",
    )
    args = parser.parse_args(argv)

    configure_logging(level=getattr(logging, args.log_level))

    try:
        config = AppConfig.load(args.config)
        app = Application(config)
        COMMANDS[args.command](app)
    except Exception:
        logger.error("Fatal error", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

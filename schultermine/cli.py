"""Kommandozeilen-Schnittstelle: python3 -m schultermine <befehl>"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime

from schultermine.app import Application
from schultermine.config import AppConfig
from schultermine.scheduler import Scheduler


def cmd_login(app: Application) -> None:
    """Führt ausschliesslich den OAuth2-Login durch (öffnet einen Browser,
    falls noch kein gültiges Token vorliegt) und legt token.json an. Macht
    sonst nichts - kein Mail-Abruf, keine Verarbeitung."""
    app.auth.credentials()
    print(f"Login successful. Token saved under: {app.config.gmail.token_path}")


def cmd_fetch(app: Application) -> None:
    fetched = app.gmail_fetcher().fetch_new()
    if fetched:
        print(f"{len(fetched)} new mail(s) fetched: {[p.name for p in fetched]}")
    else:
        print("No new mails found in this mailbox.")


def cmd_process(app: Application) -> None:
    new_events = app.inbox_processor().run()
    print(f"Done. {new_events} new/updated events found.")


def cmd_weekly(app: Application) -> None:
    events = app.event_store.all()
    body = app.summary_builder().build(events)
    subject = f"School events next week ({datetime.now().strftime('%d.%m.%Y')})"
    app.gmail_mailer().send(subject, body)
    print(f"Weekly summary sent to {app.config.gmail.send_to} ")
    print(body)


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
    parser = argparse.ArgumentParser(prog="schultermine")
    parser.add_argument("command", choices=COMMANDS.keys())
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args(argv)

    try:
        config = AppConfig.load(args.config)
        app = Application(config)
        COMMANDS[args.command](app)
    except Exception as e:
        print(f"FEHLER: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

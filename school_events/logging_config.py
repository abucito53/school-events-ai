"""Central logging configuration for the school_events package."""
from __future__ import annotations

import logging
import sys


def configure_logging(level: int = logging.INFO) -> None:
    """Configures logging once for the whole application.

    Writes to stdout (not stderr) so log lines show up immediately in
    `docker compose logs` / Docker Desktop's Logs tab - see PYTHONUNBUFFERED
    in the Dockerfile, which is the other half of making this work.
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )

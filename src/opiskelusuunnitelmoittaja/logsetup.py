"""Lokitus: konsoliin lyhyesti, tiedostoon yksityiskohtaisesti."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_MAX_BYTES = 2_000_000  # lokitiedosto kiertää ~2 MB:n kohdalla
LOG_BACKUPS = 3  # app.log.1 … app.log.3 säilytetään


def setup_logging(
    log_file: Path, level: str = "INFO", *, verbose: bool = False, debug: bool = False
) -> logging.Logger:
    """Konsoliin vain varoitukset (``verbose`` → INFO, ``debug`` → DEBUG); tiedostoon kaikki.

    Tiedostoloki kiertää (``LOG_MAX_BYTES``, ``LOG_BACKUPS``), jotta se ei kasva rajatta.
    """
    root = logging.getLogger("suunnitelmoittaja")
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    console = logging.StreamHandler()
    if debug:
        console_level = logging.DEBUG
    elif verbose:
        console_level = getattr(logging, level, logging.INFO)
    else:
        console_level = logging.WARNING
    console.setLevel(console_level)
    console.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    root.addHandler(console)

    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
        )
        root.addHandler(file_handler)
    except OSError as exc:
        root.warning("Lokitiedostoa %s ei voitu avata: %s", log_file, exc)

    return root

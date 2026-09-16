"""Lokitus: konsoliin lyhyesti, tiedostoon yksityiskohtaisesti."""

from __future__ import annotations

import logging
from pathlib import Path


def setup_logging(
    log_file: Path, level: str = "INFO", *, verbose: bool = False, debug: bool = False
) -> logging.Logger:
    """Konsoliin vain varoitukset (``verbose`` → INFO, ``debug`` → DEBUG); tiedostoon kaikki."""
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
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
        )
        root.addHandler(file_handler)
    except OSError as exc:
        root.warning("Lokitiedostoa %s ei voitu avata: %s", log_file, exc)

    return root

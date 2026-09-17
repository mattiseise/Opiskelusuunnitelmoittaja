"""Taustasäie lomakkeen täytölle sekä lokin välitys Qt-signaaleina."""

from __future__ import annotations

import contextlib
import logging
import threading
import traceback

from PySide6.QtCore import QObject, QThread, Signal

from ..browser import BrowserError, connect, find_form_page
from ..config import Config
from ..excel import Sheet
from ..filler import FormFiller, Summary


class QtLogHandler(logging.Handler, QObject):
    """Logging-käsittelijä, joka lähettää rivit signaalina käyttöliittymään."""

    record = Signal(str, str)  # (taso, viesti)

    def __init__(self) -> None:
        logging.Handler.__init__(self)
        QObject.__init__(self)
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:  # type: ignore[override]
        # Excelin lukurivit tulevat joka esikatselusta; ne ovat lokitiedostossa, ei ikkunassa.
        if record.name == "suunnitelmoittaja.excel" and record.levelno < logging.WARNING:
            return
        with contextlib.suppress(RuntimeError):  # ikkuna suljettu
            self.record.emit(record.levelname, self.format(record))


class FillWorker(QThread):
    """Kytkeytyy Chromeen ja täyttää valitut välilehdet erillisessä säikeessä."""

    progress = Signal(int, int, str)  # tehty, yhteensä, viesti
    finished_ok = Signal(object)  # Summary
    failed = Signal(str)

    def __init__(self, config: Config, sheets: list[Sheet], *, dry_run: bool = False) -> None:
        super().__init__()
        self.config = config
        self.sheets = sheets
        self.dry_run = dry_run
        self._stop = threading.Event()
        self._done = 0
        self._total = sum(len(s.rows) for s in sheets)

    def request_stop(self) -> None:
        self._stop.set()

    def _on_progress(self, message: str) -> None:
        self._done += 1
        self.progress.emit(self._done, self._total, message.strip())

    def run(self) -> None:
        try:
            if self.dry_run:
                summary = FormFiller(
                    None,
                    self.config,
                    dry_run=True,
                    progress=self._on_progress,
                    stop_requested=self._stop.is_set,
                ).process_sheets(self.sheets)
                self.finished_ok.emit(summary)
                return
            with connect(self.config.browser) as browser:
                page = find_form_page(
                    browser, self.config.browser, self.config.selectors.table_body
                )
                self.progress.emit(0, self._total, f"Lomakesivu: {page.title() or page.url}")
                filler = FormFiller(
                    page,
                    self.config,
                    progress=self._on_progress,
                    stop_requested=self._stop.is_set,
                )
                summary: Summary = filler.process_sheets(self.sheets)
            self.finished_ok.emit(summary)
        except BrowserError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            logging.getLogger("suunnitelmoittaja.gui").debug(traceback.format_exc())
            self.failed.emit(f"Odottamaton virhe: {exc}")

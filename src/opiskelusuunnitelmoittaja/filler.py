"""Lomakkeen täyttö Playwright-sivulla."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from playwright.sync_api import Locator, Page

from .config import Config
from .excel import PlanRow, Sheet

log = logging.getLogger("suunnitelmoittaja.filler")


@dataclass(slots=True)
class SheetResult:
    sheet_name: str
    total_rows: int
    successful_rows: int = 0
    failed_rows: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        return self.successful_rows / self.total_rows * 100 if self.total_rows else 0.0


@dataclass(slots=True)
class Summary:
    sheets: list[SheetResult]

    @property
    def total_rows(self) -> int:
        return sum(s.total_rows for s in self.sheets)

    @property
    def successful_rows(self) -> int:
        return sum(s.successful_rows for s in self.sheets)

    @property
    def failed_rows(self) -> int:
        return sum(s.failed_rows for s in self.sheets)

    @property
    def total_errors(self) -> int:
        return sum(len(s.errors) for s in self.sheets)

    @property
    def success_rate(self) -> float:
        return self.successful_rows / self.total_rows * 100 if self.total_rows else 0.0


class FormFiller:
    """Lisää lomaketaulukkoon rivejä ja täyttää ne Excel-datasta.

    Toimintaperiaate per datarivi: paina "lisää rivi" → odota että rivimäärä kasvaa →
    täytä uusimman rivin solut. Näin täyttö ei nojaa absoluuttisiin rivinumeroihin.
    """

    def __init__(
        self,
        page: Page,
        config: Config,
        *,
        dry_run: bool = False,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        self.page = page
        self.config = config
        self.dry_run = dry_run
        self._progress = progress or (lambda _msg: None)
        self.selectors = config.selectors
        self.page.set_default_timeout(config.browser.timeout_ms)

    # --- julkinen rajapinta -------------------------------------------------

    def process_sheets(self, sheets: list[Sheet]) -> Summary:
        results: list[SheetResult] = []
        for i, sheet in enumerate(sheets):
            results.append(self.process_sheet(sheet))
            if self.config.separator_row_between_sheets and i < len(sheets) - 1:
                self._add_separator_row(sheet.name)
        return Summary(results)

    def process_sheet(self, sheet: Sheet) -> SheetResult:
        result = SheetResult(sheet.name, len(sheet.rows))
        log.info("Aloitetaan välilehti '%s' (%d riviä)", sheet.name, len(sheet.rows))
        for n, row in enumerate(sheet.rows, start=1):
            self._progress(f"  {sheet.name}: rivi {n}/{len(sheet.rows)}")
            try:
                self.fill_new_row(row)
                result.successful_rows += 1
            except Exception as exc:
                result.failed_rows += 1
                msg = f"{sheet.name} rivi {n}: {exc}"
                result.errors.append(msg)
                log.error(msg)
        log.info(
            "Välilehti '%s' valmis: %d/%d onnistui",
            sheet.name,
            result.successful_rows,
            result.total_rows,
        )
        return result

    def fill_new_row(self, row: PlanRow) -> None:
        """Lisää uusi rivi ja täytä se. Nostaa poikkeuksen, jos jokin kenttä ei täyty."""
        if self.dry_run:
            log.info("[kuiva-ajo] uusi rivi: %s", row.values)
            return
        table_row = self.add_table_row()
        failures: list[str] = []
        for field_name in self.config.field_names:
            value = row.values.get(field_name, "")
            try:
                self._fill_cell(table_row, field_name, value)
            except Exception as exc:
                failures.append(f"{field_name}: {exc}")
        if failures:
            raise RuntimeError("; ".join(failures))

    def add_table_row(self) -> Locator:
        """Paina lisäysnappia ja palauta lisätty (viimeinen) rivi."""
        rows = self._rows()
        before = rows.count()
        button = self.page.locator(self.selectors.add_row_button).first
        self._retry(
            lambda: (button.scroll_into_view_if_needed(), button.click()),
            what="rivin lisäys",
        )
        self.page.wait_for_function(
            "([sel, n]) => document.querySelectorAll(sel + ' > tr').length > n",
            arg=[_css_or_raise(self.selectors.table_body), before],
        )
        return rows.nth(rows.count() - 1)

    # --- sisäiset apurit ----------------------------------------------------

    def _rows(self) -> Locator:
        return self.page.locator(self.selectors.table_body).locator(":scope > tr")

    def _fill_cell(self, table_row: Locator, field_name: str, value: str) -> None:
        cell_selector = self.selectors.field_cells.get(field_name)
        if not cell_selector:
            raise RuntimeError(f"kentälle '{field_name}' ei ole solulokaattoria asetuksissa")
        control = table_row.locator(cell_selector).locator(self.selectors.input_in_cell).first
        text = value.strip() or self.config.empty_value

        def do_fill() -> None:
            tag = control.evaluate("el => el.tagName.toLowerCase()")
            if tag == "select":
                control.select_option(label=text)
            else:
                control.fill(text)
            actual = control.input_value()
            if actual != text and tag != "select":
                raise RuntimeError(f"arvo ei tarttunut (odotettu {text!r}, saatiin {actual!r})")

        self._retry(do_fill, what=f"kentän '{field_name}' täyttö")
        log.debug("%s ← %r", field_name, text)

    def _add_separator_row(self, after_sheet: str) -> None:
        if self.dry_run:
            log.info("[kuiva-ajo] välirivi välilehden '%s' jälkeen", after_sheet)
            return
        try:
            self.add_table_row()
            log.info("Lisätty tyhjä välirivi välilehden '%s' jälkeen", after_sheet)
        except Exception as exc:
            log.warning("Väliriviä ei voitu lisätä: %s", exc)

    def _retry(self, action: Callable[[], object], *, what: str) -> None:
        delay = self.config.retry_delay_s
        last: Exception | None = None
        for attempt in range(1, self.config.max_attempts + 1):
            try:
                action()
                return
            except Exception as exc:
                last = exc
                log.warning(
                    "%s epäonnistui (yritys %d/%d): %s",
                    what,
                    attempt,
                    self.config.max_attempts,
                    exc,
                )
                if attempt < self.config.max_attempts:
                    time.sleep(delay)
                    delay *= 2
        raise RuntimeError(
            f"{what} epäonnistui {self.config.max_attempts} yrityksen jälkeen: {last}"
        )


def _css_or_raise(selector: str) -> str:
    """Rivilaskuri käyttää querySelectorAllia, joten taulukon lokaattorin pitää olla CSS."""
    if selector.startswith(("xpath=", "//", "text=")):
        raise RuntimeError(
            "selectors.table_body pitää antaa CSS-valitsimena (esim. 'form table tbody'), "
            f"ei XPathina: {selector!r}"
        )
    return selector

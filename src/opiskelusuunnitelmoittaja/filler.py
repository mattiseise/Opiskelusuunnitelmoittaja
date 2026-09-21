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
        page: Page | None,
        config: Config,
        *,
        dry_run: bool = False,
        progress: Callable[[str], None] | None = None,
        stop_requested: Callable[[], bool] | None = None,
    ) -> None:
        if page is None and not dry_run:
            raise ValueError("page vaaditaan, kun dry_run=False")
        self.page: Page = page  # type: ignore[assignment]  # None vain kuiva-ajossa
        self.config = config
        self.dry_run = dry_run
        self._progress = progress or (lambda _msg: None)
        self._stop_requested = stop_requested or (lambda: False)
        self.selectors = config.selectors
        self._first_row_done = False
        self._warned_multiple = False
        if page is not None:
            page.set_default_timeout(config.browser.timeout_ms)

    # --- julkinen rajapinta -------------------------------------------------

    def process_sheets(self, sheets: list[Sheet]) -> Summary:
        results: list[SheetResult] = []
        for i, sheet in enumerate(sheets):
            if self._stop_requested():
                break
            results.append(self.process_sheet(sheet))
            if self.config.separator_row_between_sheets and i < len(sheets) - 1:
                self._add_separator_row(sheet.name)
        return Summary(results)

    def read_rows(self) -> list[PlanRow]:
        """Lue lomakkeen nykyiset rivit (kentät config.field_names-järjestyksessä).

        Tyhjät rivit ohitetaan. Käytetään, kun opiskelijan olemassa oleva suunnitelma
        halutaan esikatseluun muokattavaksi.
        """
        rows: list[PlanRow] = []
        table_rows = self._rows()
        for i in range(table_rows.count()):
            tr = table_rows.nth(i)
            values: dict[str, str] = {}
            for field_name in self.config.field_names:
                cell_selector = self.selectors.field_cells.get(field_name)
                if not cell_selector:
                    values[field_name] = ""
                    continue
                control = tr.locator(cell_selector).locator(self.selectors.input_in_cell).first
                values[field_name] = control.input_value().strip() if control.count() > 0 else ""
            row = PlanRow(values)
            if not row.is_empty():
                rows.append(row)
        log.info("Luettiin lomakkeelta %d riviä", len(rows))
        return rows

    def clear_rows(self) -> int:
        """Poista lomakkeen kaikki rivit poistonapilla; palauttaa poistettujen määrän.

        Viimeistä riviä ei voi Wilmassa poistaa (siinä ei ole poistonappia), joten sen
        kentät tyhjennetään ja se käytetään ensimmäiselle uudelle riville.
        """
        if self.dry_run:
            log.info("[kuiva-ajo] rivien poisto")
            return 0
        removed = 0
        for _ in range(500):  # turvaraja
            rows = self._rows()
            count = rows.count()
            button = None
            for i in range(count - 1, -1, -1):
                candidate = rows.nth(i).locator(self.selectors.remove_row_button)
                if candidate.count() > 0:
                    button = candidate.first
                    break
            if button is None:
                break
            button.click()
            self.page.wait_for_function(
                "([el, n]) => el.querySelectorAll(':scope > tr').length < n",
                arg=[self._tbody().element_handle(), count],
            )
            removed += 1
        # jäljelle jääneet rivit tyhjennetään
        rows = self._rows()
        for i in range(rows.count()):
            for field_name in self.config.field_names:
                cell_selector = self.selectors.field_cells.get(field_name)
                if not cell_selector:
                    continue
                control = (
                    rows.nth(i).locator(cell_selector).locator(self.selectors.input_in_cell).first
                )
                if control.count() > 0:
                    control.fill("")
        self._first_row_done = False
        log.info("Poistettiin %d riviä, %d tyhjennettiin", removed, rows.count())
        return removed

    def process_sheet(self, sheet: Sheet) -> SheetResult:
        result = SheetResult(sheet.name, len(sheet.rows))
        log.info("Aloitetaan välilehti '%s' (%d riviä)", sheet.name, len(sheet.rows))
        for n, row in enumerate(sheet.rows, start=1):
            if self._stop_requested():
                msg = f"{sheet.name}: keskeytetty rivillä {n}"
                result.errors.append(msg)
                result.failed_rows += len(sheet.rows) - n + 1
                log.warning(msg)
                break
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
        """Täytä seuraava rivi. Nostaa poikkeuksen, jos jokin kenttä ei täyty.

        Ensimmäisellä kerralla käytetään taulukossa valmiina olevaa tyhjää riviä, jos
        sellainen on; muuten painetaan lisäysnappia.
        """
        if self.dry_run:
            log.info("[kuiva-ajo] uusi rivi: %s", row.values)
            return
        table_row = self._reuse_trailing_empty_row() or self.add_table_row()
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
        tbody = self._tbody()
        rows = self._rows()
        before = rows.count()
        button = self._add_button()
        self._retry(
            lambda: (button.scroll_into_view_if_needed(), button.click()),
            what="rivin lisäys",
        )
        self.page.wait_for_function(
            "([el, n]) => el.querySelectorAll(':scope > tr').length > n",
            arg=[tbody.element_handle(), before],
        )
        return rows.nth(rows.count() - 1)

    # --- sisäiset apurit ----------------------------------------------------

    def _tbody(self) -> Locator:
        """Kohdetaulukon tbody. Jos valitsin osuu useaan taulukkoon, käytetään ensimmäistä."""
        tbody = self.page.locator(self.selectors.table_body)
        n = tbody.count()
        if n == 0:
            raise RuntimeError(f"taulukkoa ei löydy valitsimella {self.selectors.table_body!r}")
        if n > 1 and not self._warned_multiple:
            self._warned_multiple = True
            log.warning(
                "Valitsin %r osuu %d taulukkoon; käytetään ensimmäistä. Tarkenna "
                "selectors.table_body, jos väärä taulukko täyttyy.",
                self.selectors.table_body,
                n,
            )
        return tbody.first

    def _rows(self) -> Locator:
        return self._tbody().locator(":scope > tr")

    def _add_button(self) -> Locator:
        """Lisäysnappi mahdollisimman läheltä kohdetaulukkoa: taulukon sisältä,
        sen vanhemmasta tai isovanhemmasta; viimeisenä koko sivulta."""
        sel = self.selectors.add_row_button
        table = self._tbody().locator("xpath=ancestor::table[1]")
        for scope in (table, table.locator("xpath=.."), table.locator("xpath=../..")):
            candidate = scope.locator(sel)
            if candidate.count() > 0:
                return candidate.first
        return self.page.locator(sel).first

    def _reuse_trailing_empty_row(self) -> Locator | None:
        """Palauta taulukon viimeinen rivi, jos sitä ei ole vielä käytetty ja se on tyhjä."""
        if self._first_row_done:
            return None
        self._first_row_done = True
        rows = self._rows()
        if rows.count() == 0:
            return None
        last = rows.nth(rows.count() - 1)
        controls = last.locator(self.selectors.input_in_cell)
        if controls.count() < len(self.config.field_names):
            return None
        values = controls.evaluate_all("els => els.map(e => (e.value || '').trim())")
        if all(v == "" for v in values):
            log.info("Käytetään taulukossa valmiina olevaa tyhjää riviä")
            return last
        return None

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

"""Lomakkeen täyttö Playwright-sivulla."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from playwright.sync_api import Locator, Page

from .config import Config
from .excel import PlanRow, Sheet
from .fillmode import FillMode

log = logging.getLogger("suunnitelmoittaja.filler")


@dataclass(slots=True)
class SheetResult:
    sheet_name: str
    total_rows: int
    successful_rows: int = 0
    failed_rows: int = 0
    skipped_rows: int = 0  # täydennystilassa: rivi oli jo lomakkeella
    errors: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # ohitettujen rivien avaintekstit

    @property
    def success_rate(self) -> float:
        return self.successful_rows / self.total_rows * 100 if self.total_rows else 0.0


@dataclass(slots=True)
class Summary:
    sheets: list[SheetResult]
    mode: FillMode = FillMode.APPEND
    removed_rows: int = 0  # korvaustilassa poistetut ylimääräiset rivit
    cleared_rows: int = 0  # korvaustilassa tyhjennetyt ylimääräiset rivit (ei poistonappia)

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
    def skipped_rows(self) -> int:
        return sum(s.skipped_rows for s in self.sheets)

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

    Täyttötapa (``mode``) määrää, miten lomakkeella jo oleviin riveihin suhtaudutaan:

    * APPEND – nykyisiin riveihin ei kosketa, uudet tulevat perään (valmis tyhjä rivi käytetään).
    * REPLACE – nykyiset rivit kirjoitetaan yli järjestyksessä; ylimääräiset poistetaan
      (``selectors.remove_row_button``) tai tyhjennetään.
    * COMPLETE – vain rivit, joiden avainkenttää (``key_field``) ei vielä ole lomakkeella,
      lisätään perään.
    """

    def __init__(
        self,
        page: Page | None,
        config: Config,
        *,
        dry_run: bool = False,
        mode: FillMode | None = None,
        progress: Callable[[str], None] | None = None,
        stop_requested: Callable[[], bool] | None = None,
    ) -> None:
        if page is None and not dry_run:
            raise ValueError("page vaaditaan, kun dry_run=False")
        self.page: Page = page  # type: ignore[assignment]  # None vain kuiva-ajossa
        self.config = config
        self.dry_run = dry_run
        self.mode = mode if mode is not None else config.fill_mode
        self._progress = progress or (lambda _msg: None)
        self._stop_requested = stop_requested or (lambda: False)
        self.selectors = config.selectors
        self._first_row_done = False
        self._warned_multiple = False
        # korvaustila: montako riviä lomakkeella oli alussa ja mihin asti ne on kirjoitettu yli
        self._existing_total: int | None = None
        self._next_existing = 0
        if page is not None:
            page.set_default_timeout(config.browser.timeout_ms)

    # --- julkinen rajapinta -------------------------------------------------

    def process_sheets(self, sheets: list[Sheet]) -> Summary:
        results: list[SheetResult] = []
        log.info("Täyttötapa: %s", self.mode.label)
        if self.mode is FillMode.COMPLETE:
            sheets, results = self._drop_existing_rows(sheets)
        if self.mode is FillMode.REPLACE:
            self._begin_replace()

        to_fill = [s for s in sheets if s.rows]
        for i, sheet in enumerate(to_fill):
            if self._stop_requested():
                break
            result = self.process_sheet(sheet)
            # täydennystilassa ohitetut rivit on jo kirjattu samannimiseen tulokseen
            existing = next((r for r in results if r.sheet_name == sheet.name), None)
            if existing is not None:
                existing.total_rows += result.total_rows
                existing.successful_rows += result.successful_rows
                existing.failed_rows += result.failed_rows
                existing.errors.extend(result.errors)
            else:
                results.append(result)
            if self.config.separator_row_between_sheets and i < len(to_fill) - 1:
                self._add_separator_row(sheet.name)

        summary = Summary(results, mode=self.mode)
        if self.mode is FillMode.REPLACE and not self._stop_requested():
            summary.removed_rows, summary.cleared_rows = self._finish_replace()
        return summary

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

        Lisäys- ja täydennystilassa ensimmäisellä kerralla käytetään taulukossa valmiina
        olevaa tyhjää riviä, jos sellainen on; muuten painetaan lisäysnappia.
        Korvaustilassa kirjoitetaan olemassa olevat rivit yli järjestyksessä.
        """
        if self.dry_run:
            log.info("[kuiva-ajo] uusi rivi: %s", row.values)
            return
        table_row, _reused = self._target_row()
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

    def existing_rows(self) -> list[dict[str, str]]:
        """Lomakkeella nyt olevien rivien arvot kentittäin (kuiva-ajossa tyhjä lista)."""
        if self.dry_run:
            return []
        rows = self._rows()
        return [self._row_values(rows.nth(i)) for i in range(rows.count())]

    # --- täyttötavat --------------------------------------------------------

    def _target_row(self) -> tuple[Locator, bool]:
        """Seuraava täytettävä rivi ja tieto siitä, oliko se lomakkeella valmiina."""
        if self.mode is FillMode.REPLACE:
            if self._existing_total is None:
                self._begin_replace()
            assert self._existing_total is not None
            if self._next_existing < self._existing_total:
                row = self._rows().nth(self._next_existing)
                self._next_existing += 1
                return row, True
            return self.add_table_row(), False
        reused = self._reuse_trailing_empty_row()
        if reused is not None:
            return reused, True
        return self.add_table_row(), False

    def _begin_replace(self) -> None:
        if self.dry_run:
            self._existing_total = 0
            log.info("[kuiva-ajo] korvaustila: lomakkeen rivejä ei lueta")
            return
        self._existing_total = self._rows().count()
        self._next_existing = 0
        log.info(
            "Korvataan olemassa oleva opintosuunnitelma: lomakkeella %d riviä",
            self._existing_total,
        )

    def _finish_replace(self) -> tuple[int, int]:
        """Poista tai tyhjennä rivit, joita ei kirjoitettu yli → (poistettu, tyhjennetty)."""
        if self.dry_run or self._existing_total is None:
            return 0, 0
        leftover = self._existing_total - self._next_existing
        if leftover <= 0:
            return 0, 0
        remove_sel = self.selectors.remove_row_button.strip()
        removed = cleared = 0
        # Viimeisestä alkaen, jotta poisto ei siirrä vielä käsittelemättömien rivien indeksejä.
        for i in range(self._existing_total - 1, self._next_existing - 1, -1):
            try:
                if remove_sel and self._remove_row(i, remove_sel):
                    removed += 1
                else:
                    self._clear_row(self._rows().nth(i))
                    cleared += 1
            except Exception as exc:
                log.error("Ylimääräisen rivin %d käsittely epäonnistui: %s", i + 1, exc)
        if removed:
            log.info("Poistettu %d ylimääräistä riviä", removed)
        if cleared:
            log.warning(
                "Tyhjennettiin %d ylimääräistä riviä, joilla ei ole poistonappia "
                "(Wilmassa tallennetut rivit). Poista ne Wilmassa käsin.",
                cleared,
            )
        return removed, cleared

    def _remove_row(self, index: int, selector: str) -> bool:
        """Paina rivin poistonappia. Palauttaa False, jos rivillä ei ole nappia."""
        tbody = self._tbody()
        rows = self._rows()
        before = rows.count()
        button = rows.nth(index).locator(selector).first
        if button.count() == 0:
            return False
        self._retry(
            lambda: (button.scroll_into_view_if_needed(), button.click()),
            what=f"rivin {index + 1} poisto",
        )
        self.page.wait_for_function(
            "([el, n]) => el.querySelectorAll(':scope > tr').length < n",
            arg=[tbody.element_handle(), before],
        )
        return True

    def _drop_existing_rows(self, sheets: list[Sheet]) -> tuple[list[Sheet], list[SheetResult]]:
        """Täydennystila: poista Excel-riveistä ne, joiden avainkenttä on jo lomakkeella."""
        key = self.config.resolved_key_field
        existing = [values.get(key, "") for values in self.existing_rows()]
        existing = [v for v in existing if _norm(v)]
        log.info(
            "Täydennetään puuttuvat: lomakkeella on %d riviä, joilla on %s", len(existing), key
        )
        kept: list[Sheet] = []
        results: list[SheetResult] = []
        for sheet in sheets:
            rows: list[PlanRow] = []
            skipped: list[str] = []
            for row in sheet.rows:
                value = row.values.get(key, "")
                match = _find_match(value, existing) if _norm(value) else None
                if match is not None:
                    skipped.append(value.strip())
                    log.info("On jo lomakkeella: %r ≈ %r", value.strip(), match.strip())
                    self._progress(f"  {sheet.name}: on jo lomakkeella – {value.strip()}")
                else:
                    rows.append(row)
                    existing.append(value)  # sama rivi kahdesti Excelissä → vain kerran
            if skipped:
                log.info(
                    "Välilehti '%s': ohitetaan %d riviä, jotka ovat jo lomakkeella: %s",
                    sheet.name,
                    len(skipped),
                    "; ".join(skipped),
                )
                results.append(
                    SheetResult(sheet.name, 0, skipped_rows=len(skipped), skipped=skipped)
                )
            kept.append(Sheet(sheet.name, rows))
        return kept, results

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

    def _row_values(self, table_row: Locator) -> dict[str, str]:
        values: dict[str, str] = {}
        for field_name in self.config.field_names:
            cell_selector = self.selectors.field_cells.get(field_name)
            if not cell_selector:
                continue
            control = table_row.locator(cell_selector).locator(self.selectors.input_in_cell)
            values[field_name] = control.first.input_value() if control.count() else ""
        return values

    def _control(self, table_row: Locator, field_name: str) -> Locator:
        cell_selector = self.selectors.field_cells.get(field_name)
        if not cell_selector:
            raise RuntimeError(f"kentälle '{field_name}' ei ole solulokaattoria asetuksissa")
        return table_row.locator(cell_selector).locator(self.selectors.input_in_cell).first

    def _fill_cell(self, table_row: Locator, field_name: str, value: str) -> None:
        control = self._control(table_row, field_name)
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

    def _clear_row(self, table_row: Locator) -> None:
        """Tyhjennä rivin kentät kokonaan (välirivi tai ylimääräinen rivi korvaustilassa)."""
        for field_name in self.config.field_names:
            control = self._control(table_row, field_name)
            if control.count() == 0:
                continue
            tag = control.evaluate("el => el.tagName.toLowerCase()")
            if tag == "select":
                control.select_option(index=0)
            else:
                control.fill("")

    def _add_separator_row(self, after_sheet: str) -> None:
        if self.dry_run:
            log.info("[kuiva-ajo] välirivi välilehden '%s' jälkeen", after_sheet)
            return
        try:
            row, reused = self._target_row()
            if reused:
                self._clear_row(row)
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


_OSP_SUFFIX = re.compile(r"[\s,(]*\d+(?:[.,]\d+)?\s*osp\)?\s*$", re.IGNORECASE)
_MIN_PARTIAL = 8  # sisältyvyysvertailu vain, kun lyhyempi teksti on vähintään näin pitkä


def _norm(text: str) -> str:
    """Vertailumuoto avainkentälle.

    Kirjainkoko pois, välilyönnit yhdeksi, päättävät välimerkit ja laajuusmerkintä pois
    ("Taide ja luova ilmaisu 1osp" → "taide ja luova ilmaisu"), koska Wilmaan on usein
    kirjoitettu laajuus osaamistavoitteen perään, Excelissä se on omassa sarakkeessaan.
    """
    text = " ".join(text.split()).casefold().strip(" .:;,-–—")
    text = _OSP_SUFFIX.sub("", text)
    return text.strip(" .:;,-–—")


def _find_match(value: str, existing: list[str]) -> str | None:
    """Lomakkeen rivi, jota Excel-rivin avainteksti vastaa; None jos ei mitään.

    Ensin täsmällinen vastaavuus normalisoituna. Sitten sisältyvyys molempiin suuntiin,
    kunhan lyhyempi teksti on tarpeeksi pitkä ("ohjelmoinnin perusteet" vastaa riviä
    "Ohjelmoinnin perusteet, verkkokurssi"), jotta "Fysiikka" ei osu "Fysiikka 2":een.
    """
    wanted = _norm(value)
    for item in existing:
        if _norm(item) == wanted:
            return item
    if len(wanted) >= _MIN_PARTIAL:
        for item in existing:
            other = _norm(item)
            shorter, longer = sorted((wanted, other), key=len)
            if len(shorter) >= _MIN_PARTIAL and _is_prefix_variant(shorter, longer):
                return item
    return None


def _is_prefix_variant(shorter: str, longer: str) -> bool:
    """Onko ``longer`` sama teksti lisämääreellä ("…, verkkokurssi"), ei eri numero ("… 3")."""
    if not longer.startswith(shorter) or len(longer) == len(shorter):
        return False
    rest = longer[len(shorter) :]
    if rest[0].isalnum():
        return False  # sana jatkuu: "ohjelmointi" vs "ohjelmointitekniikka"
    rest = rest.lstrip(" ,:;-–—(")
    return bool(rest) and not rest[0].isdigit()

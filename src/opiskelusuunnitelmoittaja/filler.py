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
    removed_rows: int = 0  # korvaustilassa poistonapilla poistetut rivit
    cleared_rows: int = 0  # korvaustilassa tyhjiksi jääneet rivit (Wilmassa käsin poistettavat)

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
    * REPLACE – ``clear_rows`` ensin: samalla sivulatauksella lisätyt rivit poistetaan napilla,
      Wilmassa tallennetut tyhjennetään (niillä ei ole poistonappia) ja kirjoitetaan yli
      paikallaan; uusia rivejä lisätään vain, kun tyhjät loppuvat. Ylijäävät jäävät tyhjiksi.
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
        self.removed_rows = 0  # clear_rows: napilla poistetut
        self._cleared = False
        self._progress = progress or (lambda _msg: None)
        self._stop_requested = stop_requested or (lambda: False)
        self.selectors = config.selectors
        # Tyhjien rivien uudelleenkäyttö: lisäystilassa vain taulukon viimeinen valmis
        # tyhjä rivi (kerran); korvaustilassa kaikki tyhjennetyt rivit järjestyksessä.
        self._reuse_all = False
        self._next_reusable = 0
        self._first_row_done = False
        self._warned_multiple = False
        if page is not None:
            page.set_default_timeout(config.browser.timeout_ms)

    # --- julkinen rajapinta -------------------------------------------------

    def process_sheets(self, sheets: list[Sheet]) -> Summary:
        results: list[SheetResult] = []
        log.info("Täyttötapa: %s", self.mode.label)
        if self.mode is FillMode.COMPLETE:
            sheets, results = self._drop_existing_rows(sheets)
        if self.mode is FillMode.REPLACE and not self._cleared:
            self.clear_rows()

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

        summary = Summary(results, mode=self.mode, removed_rows=self.removed_rows)
        if self._cleared and not self.dry_run:
            summary.cleared_rows = self._trailing_empty_rows()
            if summary.cleared_rows:
                log.warning(
                    "Lomakkeen loppuun jäi %d tyhjää riviä (Wilmassa tallennettuja rivejä ei "
                    "voi poistaa napilla). Poista ne Wilmassa käsin ennen tallennusta.",
                    summary.cleared_rows,
                )
        return summary

    def read_rows(self) -> list[PlanRow]:
        """Lue lomakkeen nykyiset rivit (kentät config.field_names-järjestyksessä).

        Lomakkeen lopussa olevat tyhjät rivit (Wilman valmis tyhjä rivi) ohitetaan; rivien
        välissä olevat tyhjät säilytetään, jotta esikatselu näyttää lomakkeen sellaisenaan.
        Käytetään, kun opiskelijan olemassa oleva suunnitelma halutaan esikatseluun.
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
            rows.append(PlanRow(values))
        while rows and rows[-1].is_empty():
            rows.pop()
        log.info("Luettiin lomakkeelta %d riviä", len(rows))
        return rows

    def clear_rows(self) -> int:
        """Tyhjennä lomake korvaustäyttöä varten; palauttaa poistettujen rivien määrän.

        Rivit, joissa on poistonappi (samalla sivulatauksella lisätyt), poistetaan.
        Tallennetut rivit eivät Wilmassa ole poistettavissa, joten niiden kentät
        tyhjennetään ja ne täytetään uudelleen järjestyksessä; ylijäävät jäävät tyhjiksi.
        """
        if self.dry_run:
            log.info("[kuiva-ajo] rivien poisto")
            return 0
        removed = 0
        remove_sel = self.selectors.remove_row_button.strip()
        for _ in range(500 if remove_sel else 0):  # turvaraja; tyhjä valitsin = ei poistoja
            rows = self._rows()
            count = rows.count()
            button = None
            for i in range(count - 1, -1, -1):
                candidate = rows.nth(i).locator(remove_sel)
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
        self._reuse_all = True
        self._next_reusable = 0
        self._first_row_done = False
        self._cleared = True
        self.removed_rows += removed
        log.info("Poistettiin %d riviä, %d tyhjennettiin", removed, rows.count())
        return removed

    def _trailing_empty_rows(self) -> int:
        """Taulukon lopussa olevien tyhjien rivien määrä (korvaustilan ylijäämä)."""
        rows = self._rows()
        n = 0
        for i in range(rows.count() - 1, -1, -1):
            if not self._row_is_empty(rows.nth(i)):
                break
            n += 1
        return n

    def _drop_existing_rows(self, sheets: list[Sheet]) -> tuple[list[Sheet], list[SheetResult]]:
        """Täydennystila: poista Excel-riveistä ne, joiden avainkenttä on jo lomakkeella."""
        key = self.config.resolved_key_field
        existing = [] if self.dry_run else [r.values.get(key, "") for r in self.read_rows()]
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

        Ensin käytetään taulukossa valmiina oleva tyhjä rivi (lisäystilassa viimeinen,
        korvaustilassa kaikki tyhjennetyt järjestyksessä); muuten painetaan lisäysnappia.
        """
        if self.dry_run:
            log.info("[kuiva-ajo] uusi rivi: %s", row.values)
            return
        table_row = self._next_empty_row() or self.add_table_row()
        if row.is_empty():
            log.info("Tyhjä rivi (välirivi) jätetään tyhjäksi")
            return
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

    def _next_empty_row(self) -> Locator | None:
        """Seuraava uudelleenkäytettävä tyhjä rivi tai None, jos sellaista ei ole."""
        rows = self._rows()
        count = rows.count()
        if self._reuse_all:
            for i in range(self._next_reusable, count):
                if self._row_is_empty(rows.nth(i)):
                    self._next_reusable = i + 1
                    return rows.nth(i)
            self._reuse_all = False  # tyhjät loppuivat → jatketaan lisäysnapilla
            self._first_row_done = True
            return None
        if self._first_row_done or count == 0:
            return None
        self._first_row_done = True
        last = rows.nth(count - 1)
        if self._row_is_empty(last):
            log.info("Käytetään taulukossa valmiina olevaa tyhjää riviä")
            return last
        return None

    def _row_is_empty(self, table_row: Locator) -> bool:
        controls = table_row.locator(self.selectors.input_in_cell)
        if controls.count() < len(self.config.field_names):
            return False
        values = controls.evaluate_all("els => els.map(e => (e.value || '').trim())")
        return all(v == "" for v in values)

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
            if self._next_empty_row() is None:
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


# --- täydennystilan vertailu ------------------------------------------------------

_OSP_SUFFIX = re.compile(r"[\s,(]*\d+(?:[.,]\d+)?\s*osp\)?\s*$", re.IGNORECASE)
_MIN_PARTIAL = 8  # alkuosavertailu vain, kun lyhyempi teksti on vähintään näin pitkä


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

    Ensin täsmällinen vastaavuus normalisoituna. Sitten alkuosan vastaavuus molempiin
    suuntiin, kunhan lyhyempi teksti on tarpeeksi pitkä ja jatko on lisämääre eikä numero
    ("ohjelmoinnin perusteet" vastaa riviä "Ohjelmoinnin perusteet, verkkokurssi", mutta
    "Fysiikka 3" ei riviä "Fysiikka").
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

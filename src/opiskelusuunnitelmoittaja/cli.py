"""Komentorivikäyttöliittymä.

suunnitelmoittaja chrome            # käynnistä Chrome etädebuggauksella
suunnitelmoittaja sheets            # listaa Excelin välilehdet
suunnitelmoittaja fill 1,3          # täytä valitut välilehdet
suunnitelmoittaja fill --dry-run    # näytä mitä täytettäisiin
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .browser import BrowserError, connect, find_form_page, launch_chrome
from .config import Config, ConfigError, load_config
from .excel import ExcelError, Sheet, list_sheets, read_sheet, resolve_sheet_selection
from .filler import FormFiller, Summary
from .logsetup import setup_logging
from .paths import ensure_user_files, is_frozen, user_config_path
from .wizard import WizardCancelled, run_wizard


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="suunnitelmoittaja",
        description=(
            "Opintosuunnitelman täyttäjä: täyttää Wilman opiskelusuunnitelmalomakkeen "
            "Excel-taulukosta."
        ),
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-c", "--config", type=Path, help="asetustiedosto (oletus: config.json)")
    parser.add_argument("-e", "--excel", type=Path, help="Excel-tiedosto (ohittaa asetuksen)")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="näytä etenemisloki konsolissa"
    )
    parser.add_argument("--debug", action="store_true", help="näytä yksityiskohtainen loki")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser(
        "chrome", help="käynnistä Chrome etädebuggauksella (tai näytä komento)"
    ).add_argument(
        "--print", action="store_true", dest="print_only", help="tulosta vain käynnistyskomento"
    )
    sub.add_parser("sheets", help="listaa Excelin välilehdet")

    fill = sub.add_parser("fill", help="täytä lomake valituista välilehdistä")
    fill.add_argument(
        "sheets",
        nargs="?",
        help="välilehdet pilkuilla erotettuna: numerot (1,3) tai nimet. "
        "Ilman → ohjattu kysely (pääsuuntaus, kaksoistutkinto, YTO...).",
    )
    fill.add_argument("--dry-run", action="store_true", help="älä koske selaimeen, näytä vain data")
    fill.add_argument("--yes", "-y", action="store_true", help="älä pyydä vahvistusta")
    fill.add_argument(
        "--no-separator", action="store_true", help="ei tyhjää väliriviä välilehtien väliin"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_arg = args.config
    if config_arg is None and is_frozen():
        ensure_user_files()
        config_arg = user_config_path()
    try:
        config = load_config(config_arg)
    except ConfigError as exc:
        print(f"Virhe: {exc}", file=sys.stderr)
        return 2
    if args.excel:
        config = _replace(config, excel_file=args.excel)
    if getattr(args, "no_separator", False):
        config = _replace(config, separator_row_between_sheets=False)

    log = setup_logging(config.log_file, config.log_level, verbose=args.verbose, debug=args.debug)

    try:
        match args.command:
            case "chrome":
                return cmd_chrome(config, print_only=args.print_only)
            case "sheets":
                return cmd_sheets(config)
            case "fill":
                return cmd_fill(config, args.sheets, dry_run=args.dry_run, assume_yes=args.yes)
    except (ExcelError, BrowserError, ValueError) as exc:
        print(f"\nVirhe: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nKeskeytetty.")
        return 130
    except Exception as exc:
        log.error("Odottamaton virhe: %s", exc, exc_info=True)
        print(f"\nOdottamaton virhe: {exc}\nKatso lokitiedosto {config.log_file}", file=sys.stderr)
        return 1
    return 0


# --- komennot -----------------------------------------------------------------


def cmd_chrome(config: Config, *, print_only: bool) -> int:
    if print_only:
        print(config.browser.launch_command())
        return 0
    launch_chrome(config.browser)
    print(
        f"Chrome on käynnissä (portti {config.browser.remote_debugging_port}). "
        "Avaa lomakesivu Chromessa ja aja sitten: suunnitelmoittaja fill"
    )
    return 0


def cmd_sheets(config: Config) -> int:
    names = list_sheets(config.excel_file)
    print(f"Välilehdet tiedostossa {config.excel_file}:")
    for i, name in enumerate(names, start=1):
        print(f"  {i}: {name}")
    return 0


def cmd_fill(config: Config, selection: str | None, *, dry_run: bool, assume_yes: bool) -> int:
    available = list_sheets(config.excel_file)
    if selection is not None:
        chosen = resolve_sheet_selection(selection, available)
    elif config.wizard is not None:
        try:
            chosen = run_wizard(config.wizard, available)
        except WizardCancelled as exc:
            print(f"Peruttu: {exc}")
            return 0
    else:
        answer = _ask_selection(available)
        if answer is None:
            print("Ei valintaa, lopetetaan.")
            return 0
        chosen = resolve_sheet_selection(answer, available)

    sheets: list[Sheet] = [
        read_sheet(config.excel_file, name, config.excel_columns) for name in chosen
    ]
    total = sum(len(s.rows) for s in sheets)
    print(f"\nTäytetään {total} riviä välilehdiltä: {', '.join(chosen)}")

    if dry_run:
        for sheet in sheets:
            print(f"\n[{sheet.name}]")
            for row in sheet.rows:
                print("  " + " | ".join(f"{k}={v!r}" for k, v in row.values.items()))
        return 0

    if not assume_yes:
        print("Varmista, että lomakesivu on auki Chromessa.")
        if input("Jatketaanko? [K/e] ").strip().lower() in {"e", "ei", "n", "no"}:
            print("Peruttu.")
            return 0

    with connect(config.browser) as browser:
        page = find_form_page(browser, config.browser, config.selectors.table_body)
        print(f"Lomakesivu: {page.title() or page.url}")
        filler = FormFiller(page, config, progress=lambda m: print(m, flush=True))
        summary = filler.process_sheets(sheets)

    print_summary(summary, config.log_file)
    return 0 if summary.failed_rows == 0 else 1


# --- apurit -------------------------------------------------------------------


def _ask_selection(available: list[str]) -> str | None:
    print("Saatavilla olevat välilehdet:")
    for i, name in enumerate(available, start=1):
        print(f"  {i}: {name}")
    answer = input("\nValitse välilehdet (numerot pilkuilla erotettuna, esim. 1,3): ").strip()
    return answer or None


def print_summary(summary: Summary, log_file: Path) -> None:
    print("\n" + "=" * 60)
    print("  YHTEENVETO")
    print("=" * 60)
    for s in summary.sheets:
        print(
            f"  {s.sheet_name}: {s.successful_rows}/{s.total_rows} riviä ({s.success_rate:.0f} %)"
        )
        for err in s.errors[:3]:
            print(f"    - {err}")
        if len(s.errors) > 3:
            print(f"    ... ja {len(s.errors) - 3} muuta virhettä")
    print("-" * 60)
    print(
        f"  Yhteensä {summary.successful_rows}/{summary.total_rows} riviä onnistui "
        f"({summary.success_rate:.0f} %), virheitä {summary.total_errors}"
    )
    if summary.failed_rows:
        print(f"  Tarkemmat tiedot lokissa: {log_file}")


def _replace(config: Config, **changes: object) -> Config:
    from dataclasses import replace

    return replace(config, **changes)  # type: ignore[arg-type]

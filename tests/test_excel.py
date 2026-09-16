from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from opiskelusuunnitelmoittaja.config import Config
from opiskelusuunnitelmoittaja.excel import (
    ExcelError,
    format_cell,
    list_sheets,
    read_sheet,
    resolve_sheet_selection,
)

COLUMNS = Config().excel_columns


def test_list_sheets(excel_file: Path) -> None:
    assert list_sheets(excel_file) == ["Ohjelmistokehittäjä", "Kyber", "Rikki"]


def test_read_sheet_skips_empty_rows_and_formats_numbers(excel_file: Path) -> None:
    sheet = read_sheet(excel_file, "Ohjelmistokehittäjä", COLUMNS)
    assert sheet.name == "Ohjelmistokehittäjä"
    assert len(sheet.rows) == 2
    first = sheet.rows[0].values
    assert first["osaamistavoite"] == "Ohjelmointi"
    assert first["laajuus"] == "45"
    assert first["suoritusajankohta"] == ""
    assert sheet.rows[1].values["laajuus"] == "30"


def test_read_sheet_keeps_decimal(excel_file: Path) -> None:
    sheet = read_sheet(excel_file, "Kyber", COLUMNS)
    assert sheet.rows[0].values["laajuus"] == "15.5"


def test_read_sheet_missing_columns(excel_file: Path) -> None:
    with pytest.raises(ExcelError, match="puuttuvat sarakkeet"):
        read_sheet(excel_file, "Rikki", COLUMNS)


def test_read_sheet_unknown_sheet(excel_file: Path) -> None:
    with pytest.raises(ExcelError, match="ei ole tiedostossa"):
        read_sheet(excel_file, "Olematon", COLUMNS)


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ExcelError, match="ei löydy"):
        list_sheets(tmp_path / "puuttuu.xlsx")


def test_header_matching_is_case_and_whitespace_insensitive(excel_file: Path) -> None:
    columns = {**COLUMNS, "laajuus": "  LAAJUUS "}
    sheet = read_sheet(excel_file, "Kyber", columns)
    assert sheet.rows[0].values["laajuus"] == "15.5"


@pytest.mark.parametrize(
    ("selection", "expected"),
    [
        ("1", ["A"]),
        ("1,3", ["A", "C"]),
        (" 2 , 1 ", ["B", "A"]),
        ("B", ["B"]),
        ("1,9,C", ["A", "C"]),  # kelpaamaton 9 ohitetaan
    ],
)
def test_resolve_sheet_selection(selection: str, expected: list[str]) -> None:
    assert resolve_sheet_selection(selection, ["A", "B", "C"]) == expected


def test_resolve_sheet_selection_nothing_valid() -> None:
    with pytest.raises(ValueError):
        resolve_sheet_selection("9,0,x", ["A", "B"])


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        (25, "25"),
        (25.0, "25"),
        (12.5, "12.5"),
        (" teksti ", "teksti"),
        (True, "kyllä"),
        (date(2026, 9, 16), "16.09.2026"),
        (datetime(2026, 9, 16), "16.09.2026"),
    ],
)
def test_format_cell(value: object, expected: str) -> None:
    assert format_cell(value) == expected

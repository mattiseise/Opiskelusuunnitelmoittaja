from __future__ import annotations

from opiskelusuunnitelmoittaja.config import Config, config_from_dict
from opiskelusuunnitelmoittaja.contact import DEFAULT_TEMPLATE, TeacherContact

FIELDS = Config().field_names


def test_text_fills_placeholders() -> None:
    tc = TeacherContact(name="Matti Seise", email="m@bc.fi", phone="040 123")
    assert tc.text() == (
        "Opiskelijalla on henkilökohtainen opintosuunnitelma ja hän etenee siinä omaan tahtiinsa. "
        "Mikäli opintosuunnitelmasta on kysyttävää: Matti Seise, sähköposti: m@bc.fi "
        "tai puhelimitse: 040 123"
    )


def test_sheet_puts_text_in_chosen_field_only() -> None:
    tc = TeacherContact(name="X", email="y", phone="z", field="suoritustapa")
    sheet = tc.sheet(FIELDS)
    assert sheet is not None and sheet.name == "Yhteystiedot"
    row = sheet.rows[0].values
    assert row["suoritustapa"].startswith("Opiskelijalla")
    assert row["osaamistavoite"] == "" and row["laajuus"] == ""


def test_unknown_field_falls_back_to_first() -> None:
    tc = TeacherContact(name="X", field="olematon")
    sheet = tc.sheet(FIELDS)
    assert sheet is not None and sheet.rows[0].values["osaamistavoite"].startswith("Opiskelijalla")


def test_not_configured_returns_none() -> None:
    assert TeacherContact().sheet(FIELDS) is None
    assert not TeacherContact().is_configured()


def test_config_roundtrip_defaults() -> None:
    cfg = config_from_dict({"teacher": {"name": "A", "email": "b", "phone": "c", "default": False}})
    assert cfg.teacher.template == DEFAULT_TEMPLATE
    assert cfg.teacher.default is False
    assert config_from_dict({}).teacher == TeacherContact()


def test_default_field_is_suoritustapa() -> None:
    assert TeacherContact().field == "suoritustapa"
    assert TeacherContact.from_dict({"name": "X"}).field == "suoritustapa"
    sheet = TeacherContact(name="X").sheet(FIELDS)
    assert sheet is not None
    values = sheet.rows[0].values
    assert values["suoritustapa"].startswith("Opiskelijalla on")
    assert values["osaamistavoite"] == ""

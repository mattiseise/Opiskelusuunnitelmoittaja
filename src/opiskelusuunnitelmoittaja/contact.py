"""Opettajan yhteystietorivi lomakkeen alimmaksi riviksi."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .excel import PlanRow, Sheet

CONTACT_SHEET_NAME = "Yhteystiedot"
DEFAULT_TEMPLATE = (
    "Opiskelijalla on henkilökohtainen opintosuunnitelma ja hän etenee siinä omaan tahtiinsa. "
    "Mikäli opintosuunnitelmasta on kysyttävää: <Nimi>, sähköposti: <sähköpostiosoite> "
    "tai puhelimitse: <puhelinnumero>"
)
QUESTION = "Lisätäänkö opettajan yhteystiedot alimmaksi riviksi?"


@dataclass(frozen=True, slots=True)
class TeacherContact:
    name: str = ""
    email: str = ""
    phone: str = ""
    template: str = DEFAULT_TEMPLATE
    field: str = "osaamistavoite"  # kenttä, johon teksti kirjoitetaan
    default: bool = True  # kysymyksen oletusvastaus

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> TeacherContact:
        return cls(
            name=str(raw.get("name", "")).strip(),
            email=str(raw.get("email", "")).strip(),
            phone=str(raw.get("phone", "")).strip(),
            template=str(raw.get("template") or DEFAULT_TEMPLATE),
            field=str(raw.get("field") or "osaamistavoite"),
            default=bool(raw.get("default", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "template": self.template,
            "field": self.field,
            "default": self.default,
        }

    def is_configured(self) -> bool:
        return bool(self.name or self.email or self.phone)

    def text(self) -> str:
        return (
            self.template.replace("<Nimi>", self.name)
            .replace("<sähköpostiosoite>", self.email)
            .replace("<puhelinnumero>", self.phone)
            .strip()
        )

    def sheet(self, field_names: list[str]) -> Sheet | None:
        """Yhden rivin 'välilehti', jossa teksti on valitussa kentässä ja muut tyhjiä."""
        if not self.is_configured():
            return None
        target = self.field if self.field in field_names else field_names[0]
        values = {f: (self.text() if f == target else "") for f in field_names}
        return Sheet(CONTACT_SHEET_NAME, [PlanRow(values)])

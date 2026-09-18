"""BC Helsinki -design system Qt:lle.

Tokenit (pergamentti, burgundi, kulta, Public Sans / Source Serif 4) ja niistä johdettu
QSS. Periaatteet: ei varjoja, ei kulmapyöristyksiä, ei ikoneita, ei emojia. Erottimet ovat
typografiaa: keskipiste ·, numerot ja hairline-viivat.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

TOKENS = {
    "bg": "#F4ECDD",  # parchment
    "bg2": "#EADFC9",  # parchment-2
    "ink": "#1F1813",  # warm black
    "ink_soft": "#4A3E36",  # warm grey
    "brand": "#69013B",  # burgundy
    "brand_deep": "#4A0029",
    "gold": "#9C7A3A",
    "on_section": "#F4ECDD",
    "on_section_soft": "rgba(244,236,221,0.85)",
    "hairline": "rgba(31,24,19,0.15)",
    "hairline_strong": "rgba(31,24,19,0.18)",
    "grid_cell_bg": "rgba(234,223,201,0.35)",
    "hairline_on_dark": "rgba(244,236,221,0.25)",
    "muted_on_dark": "rgba(234,223,201,0.7)",
}

SANS = "Public Sans"
SERIF = "Source Serif 4"
MIDDOT = " · "

_FONT_DIR = Path(__file__).parent / "fonts"
_loaded_families: set[str] = set()


def load_fonts() -> None:
    """Lataa paketoidut Public Sans ja Source Serif 4 -fontit QFontDatabaseen."""
    if _loaded_families:
        return
    for ttf in sorted(_FONT_DIR.glob("*.ttf")):
        font_id = QFontDatabase.addApplicationFont(str(ttf))
        if font_id >= 0:
            _loaded_families.update(QFontDatabase.applicationFontFamilies(font_id))


def sans(size: int = 14, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    f = QFont(SANS if SANS in _loaded_families else "Helvetica Neue", size)
    f.setWeight(weight)
    return f


def serif(
    size: int = 20, *, italic: bool = False, weight: QFont.Weight = QFont.Weight.Normal
) -> QFont:
    f = QFont(SERIF if SERIF in _loaded_families else "Georgia", size)
    f.setItalic(italic)
    f.setWeight(weight)
    return f


def apply(app: QApplication) -> None:
    load_fonts()
    app.setStyle("Fusion")  # yhtenäinen pohja, jonka QSS ylikirjoittaa kaikilla alustoilla
    app.setFont(sans(14))
    app.setStyleSheet(build_qss())


def build_qss() -> str:
    t = TOKENS
    return f"""
    * {{
        font-family: "{SANS}";
        outline: none;
    }}
    QMainWindow, QDialog, QWidget#root {{
        background: {t["bg"]};
        color: {t["ink"]};
    }}
    QWidget {{ color: {t["ink"]}; }}
    QMenuBar {{ background: {t["bg"]}; border-bottom: 1px solid {t["hairline"]}; padding: 2px 8px; }}
    QMenuBar::item {{ padding: 6px 10px; background: transparent; }}
    QMenuBar::item:selected {{ background: {t["bg2"]}; }}
    QMenu {{ background: {t["bg"]}; border: 1px solid {t["hairline_strong"]}; padding: 4px 0; }}
    QMenu::item {{ padding: 6px 18px; }}
    QMenu::item:selected {{ background: {t["bg2"]}; color: {t["brand"]}; }}
    QMenu::separator {{ height: 1px; background: {t["hairline"]}; margin: 4px 0; }}

    QLabel {{ background: transparent; }}
    QLabel[role="eyebrow"] {{
        color: {t["brand"]}; font-size: 11px; font-weight: 600; letter-spacing: 1.4px;
        padding: 2px 0; min-height: 18px;
    }}
    QLabel[role="title"] {{ font-family: "{SERIF}"; font-size: 30px; color: {t["ink"]}; }}
    QLabel[role="lead"] {{ color: {t["ink_soft"]}; font-size: 14px; }}
    QLabel[role="step-number"] {{
        font-family: "{SERIF}"; font-style: italic; font-size: 26px; color: {t["brand"]};
        min-width: 34px;
    }}
    QLabel[role="step-title"] {{ font-family: "{SERIF}"; font-size: 19px; color: {t["ink"]}; }}
    QLabel[role="caps"] {{
        color: {t["ink_soft"]}; font-size: 11px; font-weight: 600; letter-spacing: 1.2px;
        padding: 3px 0 2px 0; min-height: 18px;
    }}
    QLabel[role="muted"] {{ color: {t["ink_soft"]}; font-size: 13px; }}
    QLabel[role="status-ok"] {{ color: {t["brand"]}; font-weight: 600; }}
    QLabel[role="status-off"] {{ color: {t["ink_soft"]}; }}

    QFrame[role="rule"] {{ background: {t["brand"]}; max-height: 2px; min-height: 2px; border: none; }}
    QFrame[role="hairline"] {{ background: {t["hairline"]}; max-height: 1px; min-height: 1px; border: none; }}
    QFrame[role="vhairline"] {{ background: {t["hairline"]}; max-width: 1px; min-width: 1px; border: none; }}
    QWidget[role="section"] {{ background: {t["brand"]}; }}
    QWidget[role="section"] QLabel {{ color: {t["on_section"]}; }}
    QWidget[role="section"] QLabel[role="title"] {{ color: {t["on_section"]}; font-weight: 400; }}
    QWidget[role="section"] QLabel[role="eyebrow"] {{ color: {t["muted_on_dark"]}; }}
    QWidget[role="callout"] {{ background: {t["bg2"]}; }}

    QPushButton {{
        background: {t["bg"]}; color: {t["ink"]};
        border: 1px solid {t["hairline_strong"]}; border-radius: 0;
        padding: 7px 16px; font-size: 13px; font-weight: 500;
    }}
    QPushButton:hover {{ background: {t["bg2"]}; border-color: {t["ink_soft"]}; }}
    QPushButton:pressed {{ background: {t["bg2"]}; color: {t["brand_deep"]}; }}
    QPushButton:disabled {{ color: rgba(31,24,19,0.38); border-color: {t["hairline"]}; }}
    QPushButton[variant="primary"] {{
        background: {t["brand"]}; color: {t["on_section"]}; border: 1px solid {t["brand"]};
        padding: 10px 26px; font-size: 14px; font-weight: 600; letter-spacing: 0.3px;
    }}
    QPushButton[variant="primary"]:hover {{ background: {t["brand_deep"]}; border-color: {t["brand_deep"]}; }}
    QPushButton[variant="primary"]:disabled {{
        background: {t["bg2"]}; color: rgba(31,24,19,0.38); border-color: {t["hairline"]};
    }}
    QPushButton[variant="link"] {{
        background: transparent; border: none; color: {t["brand"]}; padding: 4px 2px;
        text-decoration: underline;
    }}
    QPushButton[variant="link"]:hover {{ color: {t["brand_deep"]}; }}

    QLineEdit, QSpinBox, QPlainTextEdit, QTextEdit, QComboBox {{
        background: {t["bg"]}; color: {t["ink"]};
        border: 1px solid {t["hairline_strong"]}; border-radius: 0;
        padding: 6px 8px; selection-background-color: {t["brand"]};
        selection-color: {t["on_section"]};
    }}
    QLineEdit:focus, QSpinBox:focus, QPlainTextEdit:focus, QComboBox:focus {{ border: 1px solid {t["brand"]}; }}
    QLineEdit:read-only {{ background: {t["bg2"]}; color: {t["ink_soft"]}; }}
    QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}
    QDialog QLabel {{ font-size: 13px; }}
    QDialog QFormLayout QLabel {{ color: {t["ink_soft"]}; }}
    QDialog QCheckBox {{ font-size: 13px; }}

    QCheckBox, QRadioButton {{ spacing: 10px; padding: 5px 0; font-size: 14px; }}
    QCheckBox::indicator, QRadioButton::indicator {{
        width: 16px; height: 16px; border: 1px solid {t["ink_soft"]}; background: {t["bg"]};
        border-radius: 0;
    }}
    QRadioButton::indicator {{ border-radius: 8px; }}
    QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
        background: {t["brand"]}; border-color: {t["brand"]};
    }}
    QRadioButton::indicator:checked {{
        background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
            stop:0 {t["brand"]}, stop:0.45 {t["brand"]}, stop:0.55 {t["bg"]}, stop:1 {t["bg"]});
        border-color: {t["brand"]};
    }}
    QTableView::indicator, QListView::indicator {{
        width: 15px; height: 15px; border: 1px solid {t["ink_soft"]}; background: {t["bg"]};
        border-radius: 0;
    }}
    QTableView::indicator:checked, QListView::indicator:checked {{
        background: {t["brand"]}; border-color: {t["brand"]};
    }}
    QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{ border-color: {t["hairline"]}; }}
    QCheckBox:disabled, QRadioButton:disabled {{ color: rgba(31,24,19,0.38); }}

    QGroupBox {{ border: none; margin-top: 0; padding-top: 0; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 0; padding: 0; color: transparent; height: 0; }}

    QListWidget, QTableWidget, QTableView {{
        background: {t["bg"]}; border: 1px solid {t["hairline_strong"]}; border-radius: 0;
        gridline-color: {t["hairline"]}; alternate-background-color: {t["grid_cell_bg"]};
        selection-background-color: {t["bg2"]}; selection-color: {t["ink"]};
    }}
    QTableWidget::item, QListWidget::item {{ padding: 4px 8px; border-bottom: 1px solid {t["hairline"]}; }}
    QHeaderView {{ background: {t["bg2"]}; }}
    QHeaderView::section {{
        background: {t["bg2"]}; color: {t["ink_soft"]}; font-size: 11px; font-weight: 600;
        letter-spacing: 1.2px; text-transform: uppercase;
        padding: 8px 8px; border: none; border-bottom: 2px solid {t["brand"]};
        border-right: 1px solid {t["hairline"]};
    }}
    QTableCornerButton::section {{ background: {t["bg2"]}; border: none; }}

    QProgressBar {{
        background: {t["bg2"]}; border: none; border-radius: 0; height: 6px; max-height: 6px;
        text-align: right; color: transparent;
    }}
    QProgressBar::chunk {{ background: {t["brand"]}; }}

    QPlainTextEdit[role="log"] {{
        background: {t["bg2"]}; border: none; color: {t["ink_soft"]}; font-size: 13px;
        padding: 10px 12px;
    }}

    QTabWidget::pane {{ border: none; border-top: 1px solid {t["hairline_strong"]}; top: -1px; }}
    QTabBar::tab {{
        background: transparent; color: {t["ink_soft"]}; padding: 9px 18px; margin-right: 8px;
        border: none; border-bottom: 2px solid transparent; font-size: 13px; font-weight: 500;
        letter-spacing: 0.4px;
    }}
    QTabBar::tab:selected {{ color: {t["brand"]}; border-bottom: 2px solid {t["brand"]}; }}
    QTabBar::tab:hover {{ color: {t["brand_deep"]}; }}

    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: rgba(31,24,19,0.22); min-height: 30px; border-radius: 0; }}
    QScrollBar::handle:vertical:hover {{ background: rgba(31,24,19,0.38); }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; }}
    QScrollBar::handle:horizontal {{ background: rgba(31,24,19,0.22); min-width: 30px; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

    QSplitter::handle {{ background: {t["hairline"]}; width: 1px; }}
    QStatusBar {{ background: {t["bg"]}; color: {t["ink_soft"]}; border-top: 1px solid {t["hairline"]}; font-size: 12px; }}
    QStatusBar::item {{ border: none; }}
    QToolTip {{ background: {t["ink"]}; color: {t["on_section"]}; border: none; padding: 6px 8px; }}
    QMessageBox {{ background: {t["bg"]}; }}
    QMessageBox QLabel {{ font-size: 14px; }}
    """

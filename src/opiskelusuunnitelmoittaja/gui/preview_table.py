"""Esikatselutaulukko, jonka rivejä voi raahata uuteen järjestykseen.

Raahaus aloitetaan riviltä (kätevimmin tarttumasarakkeesta ⋮⋮) ja pudotetaan toisen rivin
päälle tai väliin. Taulukko ei siirrä soluja itse, vaan ilmoittaa ``row_moved(src, dst)``
ja pääikkuna järjestää oman rivimallinsa ja piirtää taulukon uudelleen.
"""

from __future__ import annotations

from PySide6.QtCore import QLineF, QModelIndex, QPersistentModelIndex, Qt, Signal
from PySide6.QtGui import QColor, QDropEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
)

GRIP = "⋮⋮"  # solun tekstiarvo (saavutettavuus, testit); piirto tehdään delegaatilla


class GripDelegate(QStyledItemDelegate):
    """Piirtää tarttumasarakkeeseen kuusi pistettä tekstin sijaan.

    Unicode-merkki ⋮ puuttuu monesta fontista ja katkeaa kapeassa sarakkeessa, joten
    tarttuma piirretään itse hairline-tyylisinä pisteinä.
    """

    def __init__(self, color: str, parent: QTableWidget) -> None:
        super().__init__(parent)
        self._color = QColor(color)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        widget = opt.widget
        style = widget.style() if widget is not None else None
        if style is not None:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)
        rect = option.rect
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        cx, cy = rect.center().x(), rect.center().y()
        for dx in (-3, 3):
            for dy in (-5, 0, 5):
                painter.drawEllipse(cx + dx - 1, cy + dy - 1, 2, 2)
        painter.restore()


class TrashDelegate(QStyledItemDelegate):
    """Piirtää poistosarakkeeseen pienen roskakorin ohuina viivoina (ei bittikarttaikonia)."""

    def __init__(self, color: str, parent: QTableWidget) -> None:
        super().__init__(parent)
        self._color = QColor(color)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        widget = opt.widget
        style = widget.style() if widget is not None else None
        if style is not None:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)
        rect = option.rect
        cx, cy = rect.center().x(), rect.center().y()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(self._color, 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # kansi + kahva
        painter.drawLine(QLineF(cx - 6, cy - 5, cx + 6, cy - 5))
        painter.drawLine(QLineF(cx - 2, cy - 7, cx + 2, cy - 7))
        # runko (hieman kapeneva) ja kaksi uraa
        painter.drawLine(QLineF(cx - 5, cy - 5, cx - 4, cy + 6))
        painter.drawLine(QLineF(cx + 5, cy - 5, cx + 4, cy + 6))
        painter.drawLine(QLineF(cx - 4, cy + 6, cx + 4, cy + 6))
        painter.drawLine(QLineF(cx - 1.5, cy - 2, cx - 1.5, cy + 3))
        painter.drawLine(QLineF(cx + 1.5, cy - 2, cx + 1.5, cy + 3))
        painter.restore()


class PreviewTable(QTableWidget):
    row_moved = Signal(int, int)  # lähtörivi, kohderivi (lopullinen indeksi)

    def __init__(self, rows: int, columns: int) -> None:
        super().__init__(rows, columns)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropOverwriteMode(False)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

    def dropEvent(self, event: QDropEvent) -> None:
        if event.source() is not self:
            event.ignore()
            return
        src = self.currentRow()
        index = self.indexAt(event.position().toPoint())
        if index.isValid():
            dst = index.row()
            pos = self.dropIndicatorPosition()
            if pos == QAbstractItemView.DropIndicatorPosition.BelowItem:
                dst += 1
        else:
            dst = self.rowCount()
        if src < 0:
            event.ignore()
            return
        if dst > src:
            dst -= 1  # poistettu rivi siirtää kohdetta yhdellä
        dst = max(0, min(dst, self.rowCount() - 1))
        event.setDropAction(Qt.DropAction.IgnoreAction)
        event.accept()
        if dst != src:
            self.row_moved.emit(src, dst)

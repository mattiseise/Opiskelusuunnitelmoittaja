"""Esikatselutaulukko, jonka rivejä voi raahata uuteen järjestykseen.

Raahaus aloitetaan riviltä (kätevimmin tarttumasarakkeesta ⋮⋮) ja pudotetaan rivien väliin;
paksu viiva näyttää kohdan. Taulukko ei siirrä soluja itse, vaan ilmoittaa
``row_moved(src, dst)`` ja pääikkuna järjestää oman rivimallinsa ja piirtää taulukon uudelleen.
Kenttäsolujen muokkain rivittää tekstin ja kasvaa kirjoitettaessa (``FieldDelegate``).
"""

from __future__ import annotations

import math

from PySide6.QtCore import (
    QAbstractItemModel,
    QEvent,
    QLineF,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QPoint,
    QRect,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QTextCursor,
    QTextLayout,
    QTextOption,
)
from PySide6.QtWidgets import (
    QAbstractItemDelegate,
    QAbstractItemView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QTableWidget,
    QTextEdit,
    QWidget,
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
            for dy in (-6, 0, 6):
                painter.drawEllipse(cx + dx - 1, cy + dy - 1, 3, 3)
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


class FieldDelegate(QStyledItemDelegate):
    """Kenttäsolun muokkain: rivittyvä tekstikenttä, joka kasvaa alaspäin kirjoitettaessa.

    Lomakkeen kentät ovat yksirivisiä, joten Enter tallentaa eikä lisää rivinvaihtoa, ja
    liitetyt rivinvaihdot muuttuvat välilyönneiksi. Tab siirtyy seuraavaan soluun, Esc peruu.
    """

    MIN_WIDTH = 240  # kapeassa sarakkeessa (Laajuus) muokkain levenee naapurin päälle
    MAX_LINES = 3  # pidempi teksti lyhenee "…"-merkkiin; kokonaan työkaluvihjeessä ja muokkaimessa
    # Solun padding teeman QSS:stä (QTableWidget::item { padding: 4px 8px; border-bottom: 1px })
    PAD_H, PAD_V = 8, 4

    def sizeHint(
        self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> QSize:
        """Rivittyvän tekstin korkeus solun todellisella tekstileveydellä, enintään MAX_LINES riviä.

        Qt:n oma arvio ei vähennä QSS-paddingia rivityksen leveydestä, joten pitkän tekstin
        viimeinen rivi jäisi piiloon.
        """
        size = super().sizeHint(option, index)
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        view = option.widget
        if not text or not isinstance(view, QTableView):
            return size
        style = view.style()
        margin = style.pixelMetric(QStyle.PixelMetric.PM_FocusFrameHMargin, None, view) + 1
        width = view.columnWidth(index.column()) - 2 * (self.PAD_H + margin)
        # Sama rivitys kuin Qt:n piirrossa (QTextLayout, WordWrap), rivikorkeudet liukulukuina:
        # pyöristys alaspäin lyhentäisi viimeisen rivin "…"-merkkiin.
        layout = QTextLayout(text, option.font)
        wrap = QTextOption()
        wrap.setWrapMode(QTextOption.WrapMode.WordWrap)
        layout.setTextOption(wrap)
        layout.beginLayout()
        heights: list[float] = []
        while len(heights) < self.MAX_LINES:
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(max(1, width))
            heights.append(line.height())
        layout.endLayout()
        # Qt:n oma korkeus (size) on rivittämätön arvio, joten se korvataan kokonaan
        return QSize(size.width(), math.ceil(sum(heights)) + 2 * self.PAD_V + 2)

    def createEditor(
        self,
        parent: QWidget,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QWidget:
        editor = QTextEdit(parent)
        editor.setAcceptRichText(False)
        editor.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        editor.setStyleSheet("QTextEdit { padding: 2px 4px; }")
        editor.document().setDocumentMargin(3)
        editor.textChanged.connect(lambda: self._fit(editor))
        return editor

    def setEditorData(self, editor: QWidget, index: QModelIndex | QPersistentModelIndex) -> None:
        if not isinstance(editor, QTextEdit):
            super().setEditorData(editor, index)
            return
        editor.setPlainText(str(index.data(Qt.ItemDataRole.EditRole) or ""))
        # kursori loppuun: pitkää tekstiä jatketaan tai korjataan, ei korvata vahingossa
        editor.moveCursor(QTextCursor.MoveOperation.End)

    def setModelData(
        self,
        editor: QWidget,
        model: QAbstractItemModel,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        if not isinstance(editor, QTextEdit):
            super().setModelData(editor, model, index)
            return
        parts = (p.strip() for p in editor.toPlainText().splitlines())
        model.setData(index, " ".join(p for p in parts if p), Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(
        self,
        editor: QWidget,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        editor.setProperty("cell_rect", QRect(option.rect))
        if isinstance(editor, QTextEdit):
            self._fit(editor)
        else:
            super().updateEditorGeometry(editor, option, index)

    def _fit(self, editor: QTextEdit) -> None:
        """Muokkain solun kohdalle, vähintään solun kokoisena ja niin korkeana kuin teksti vaatii.

        Viewportin alareunassa muokkain kasvaa ylöspäin, jotta kirjoitettava teksti näkyy.
        """
        cell = editor.property("cell_rect")
        area = editor.parentWidget()
        if not isinstance(cell, QRect) or area is None:
            return
        width = min(max(cell.width(), self.MIN_WIDTH), area.width())
        x = max(0, min(cell.x(), area.width() - width))
        chrome = editor.frameWidth() * 2 + 2 * 2  # kehys + oma padding (ks. createEditor)
        doc = editor.document().clone(editor)
        doc.setTextWidth(max(1, width - chrome))
        needed = math.ceil(doc.size().height()) + chrome
        doc.deleteLater()
        height = min(max(cell.height(), needed), area.height())
        y = cell.y() if cell.y() + height <= area.height() else max(0, area.height() - height)
        editor.setGeometry(x, y, width, height)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if (
            isinstance(obj, QTextEdit)
            and isinstance(event, QKeyEvent)
            and event.type() == QEvent.Type.KeyPress
        ):
            hint = {
                Qt.Key.Key_Return: QAbstractItemDelegate.EndEditHint.SubmitModelCache,
                Qt.Key.Key_Enter: QAbstractItemDelegate.EndEditHint.SubmitModelCache,
                Qt.Key.Key_Tab: QAbstractItemDelegate.EndEditHint.EditNextItem,
                Qt.Key.Key_Backtab: QAbstractItemDelegate.EndEditHint.EditPreviousItem,
            }.get(Qt.Key(event.key()))
            if hint is not None:
                self.commitData.emit(obj)
                self.closeEditor.emit(obj, hint)
                return True
        return super().eventFilter(obj, event)


class PreviewTable(QTableWidget):
    row_moved = Signal(int, int)  # lähtörivi, kohderivi (lopullinen indeksi)

    def __init__(
        self,
        rows: int,
        columns: int,
        *,
        grip_column: int = 0,
        delete_column: int | None = None,
        indicator_color: str = "#69013B",
    ) -> None:
        super().__init__(rows, columns)
        self._grip_column = grip_column
        self._delete_column = delete_column
        self._indicator = QColor(indicator_color)
        self._drop_gap: int | None = None  # rivien väli, johon raahattu rivi putoaa
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropOverwriteMode(False)
        # Qt:n oma ohut viiva hukkuu teemaan; piirretään paksu viiva itse (paintEvent)
        self.setDropIndicatorShown(False)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        # raahaus vierittää taulukkoa jo, kun osoitin on lähellä reunaa
        self.setAutoScrollMargin(48)
        self.setMouseTracking(True)

    def drop_gap_at(self, pos: QPoint) -> int:
        """Rivien väli kohdassa pos: 0 = ensimmäisen rivin yläpuoli, rowCount() = loppu.

        Rivin yläpuolisko pudottaa rivin yläpuolelle, alapuolisko alapuolelle.
        """
        row = self.rowAt(pos.y())
        if row < 0:
            return 0 if pos.y() < 0 else self.rowCount()
        middle = self.rowViewportPosition(row) + self.rowHeight(row) / 2
        return row + 1 if pos.y() >= middle else row

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        super().dragMoveEvent(event)  # automaattinen vieritys reunoilla
        if event.source() is not self:
            event.ignore()
            return
        gap = self.drop_gap_at(event.position().toPoint())
        if gap != self._drop_gap:
            self._drop_gap = gap
            self.viewport().update()
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        super().dragLeaveEvent(event)
        self._clear_drop_gap()

    def dropEvent(self, event: QDropEvent) -> None:
        gap = self.drop_gap_at(event.position().toPoint())
        self._clear_drop_gap()
        src = self.currentRow()
        if event.source() is not self or src < 0:
            event.ignore()
            return
        event.setDropAction(Qt.DropAction.IgnoreAction)
        event.accept()
        self.move_to_gap(src, gap)

    def move_to_gap(self, src: int, gap: int) -> None:
        """Siirrä rivi src väliin gap (ks. drop_gap_at); ilmoittaa row_moved(src, dst)."""
        dst = gap - 1 if gap > src else gap  # poistettu rivi siirtää kohdetta yhdellä
        dst = max(0, min(dst, self.rowCount() - 1))
        if dst != src:
            self.row_moved.emit(src, dst)

    def _clear_drop_gap(self) -> None:
        if self._drop_gap is not None:
            self._drop_gap = None
            self.viewport().update()

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        self._paint_selection(painter)
        gap = self._drop_gap
        if gap is not None and self.rowCount():
            if gap < self.rowCount():
                y = self.rowViewportPosition(gap)
            else:
                last = self.rowCount() - 1
                y = self.rowViewportPosition(last) + self.rowHeight(last) - 1
            painter.setPen(QPen(self._indicator, 3))
            painter.drawLine(0, y, self.viewport().width(), y)
        painter.end()

    def _paint_selection(self, painter: QPainter) -> None:
        """Valitulle riville reunus ja paksu palkki vasempaan laitaan (QSS antaa sävytyksen).

        Pelkkä taustasävy erottuu huonosti vuorottelevista riveistä, ja ▲▼-siirrossa pitää
        nähdä heti, mikä rivi liikkuu.
        """
        sel = self.selectionModel()
        if sel is None:
            return
        width = self.viewport().width()
        for index in sel.selectedRows():
            top = self.rowViewportPosition(index.row())
            height = self.rowHeight(index.row())
            painter.setPen(QPen(self._indicator, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(0, top, width - 1, height - 1)
            painter.fillRect(0, top, 5, height, self._indicator)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        super().mouseMoveEvent(event)
        if event.buttons() != Qt.MouseButton.NoButton:
            return
        column = self.columnAt(int(event.position().x()))
        if column == self._grip_column:
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
        elif column == self._delete_column:
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.viewport().unsetCursor()

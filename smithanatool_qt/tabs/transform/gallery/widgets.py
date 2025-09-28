from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QListWidget

class RightSelectableList(QListWidget):
    """QListWidget с выделением правой кнопкой мыши (drag-select)."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._right_selecting = False
        self._anchor_row = -1

    def _row_at_pos_clamped(self, pos: QPoint) -> int:
        row = self.row(self.itemAt(pos))
        if row >= 0:
            return row
        if pos.y() < 0 and self.count() > 0:
            return 0
        if pos.y() > self.viewport().height() - 1 and self.count() > 0:
            return self.count() - 1
        return -1

    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton:
            row = self._row_at_pos_clamped(e.pos())
            if row >= 0:
                if not (e.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier)):
                    self.clearSelection()
                self._anchor_row = row
                it = self.item(row)
                it.setSelected(True)
                self.setCurrentRow(row)
                self._right_selecting = True
                e.accept()
                return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._right_selecting:
            row = self._row_at_pos_clamped(e.pos())
            if row >= 0 and self._anchor_row >= 0:
                a, b = sorted((self._anchor_row, row))
                self.blockSignals(True)
                for i in range(self.count()):
                    self.item(i).setSelected(a <= i <= b)
                self.blockSignals(False)
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.RightButton and self._right_selecting:
            self._right_selecting = False
            e.accept()
            return
        super().mouseReleaseEvent(e)

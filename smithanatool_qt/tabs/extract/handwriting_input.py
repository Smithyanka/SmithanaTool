from __future__ import annotations

from PySide6.QtCore import Qt, QPoint, QRect, Signal

from PySide6.QtGui import QPainter, QPen, QImage
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QSizePolicy
)


class _HandwritingCanvas(QWidget):
    """
    Простой Canvas для рисования мышью.
    Рисуем чёрным по белому фону.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StaticContents, True)
        self.setMouseTracking(True)

        self._image = QImage(800, 400, QImage.Format_RGB32)
        self._image.fill(Qt.white)

        self._drawing = False
        self._last_pos: QPoint | None = None

        # перо для рисования и для ластика
        self._pen_draw = QPen(Qt.black, 6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        self._pen_erase = QPen(Qt.white, 30, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        self._use_eraser = False  # False = рисуем, True = стираем

        # позиция курсора для отображения круга
        self._cursor_pos: QPoint | None = None

        sp = self.sizePolicy()
        sp.setHorizontalPolicy(QSizePolicy.Expanding)
        sp.setVerticalPolicy(QSizePolicy.Expanding)
        self.setSizePolicy(sp)

    # --- API ---

    def clear(self):
        self._image.fill(Qt.white)
        self.update()

    def get_image(self) -> QImage:
        # отдаём копию, чтобы снаружи не портили наш буфер
        return self._image.copy()

    def set_eraser_enabled(self, enabled: bool):
        """Включить/выключить режим ластика."""
        self._use_eraser = bool(enabled)

    def is_eraser_enabled(self) -> bool:
        return self._use_eraser

    # --- events ---

    def resizeEvent(self, event):
        # при увеличении — просто расширяем холст, старый рисунок остаётся в левом верхнем
        if event.size().width() > self._image.width() or event.size().height() > self._image.height():
            new_w = max(event.size().width(), self._image.width())
            new_h = max(event.size().height(), self._image.height())
            new_img = QImage(new_w, new_h, QImage.Format_RGB32)
            new_img.fill(Qt.white)

            p = QPainter(new_img)
            p.drawImage(0, 0, self._image)
            p.end()

            self._image = new_img
        super().resizeEvent(event)

    def paintEvent(self, _):
        p = QPainter(self)
        p.drawImage(0, 0, self._image)

        # кружок-курсор
        if self._cursor_pos is not None:
            p.setRenderHint(QPainter.Antialiasing, True)
            width = self._pen_erase.width() if self._use_eraser else self._pen_draw.width()
            radius = width / 2
            r = int(radius)
            center = self._cursor_pos
            circle_rect = QRect(center.x() - r, center.y() - r, 2 * r, 2 * r)

            pen = QPen(Qt.red if self._use_eraser else Qt.darkGray)
            pen.setWidth(1)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(circle_rect)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drawing = True
            pt = event.position().toPoint()
            self._last_pos = pt
            self._cursor_pos = pt
            self.update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        self._cursor_pos = pos

        if self._drawing and (event.buttons() & Qt.LeftButton) and self._last_pos is not None:
            p = QPainter(self._image)
            pen = self._pen_erase if self._use_eraser else self._pen_draw
            p.setPen(pen)
            cur = pos
            p.drawLine(self._last_pos, cur)
            p.end()
            self._last_pos = cur

        self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drawing = False
            self._last_pos = None
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        self._cursor_pos = None
        self.update()
        super().leaveEvent(event)



class HandwritingInputDialog(QDialog):
    """
    Диалог рукописного ввода.
    Пока просто даёт порисовать и отдать QImage наружу.
    """
    extractRequested = Signal(QImage)
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Рукописный ввод")
        self.resize(600, 400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)


        self.canvas = _HandwritingCanvas(self)
        layout.addWidget(self.canvas, 1)

        btn_row = QHBoxLayout()
        btn_clear = QPushButton("Очистить")
        self.btn_eraser = QPushButton("Ластик")
        self.btn_eraser.setCheckable(True)
        btn_extract = QPushButton("Распознать текст")
        btn_cancel = QPushButton("Закрыть")

        btn_row.addWidget(btn_clear)
        btn_row.addWidget(self.btn_eraser)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_extract)
        layout.addLayout(btn_row)

        btn_clear.clicked.connect(self.canvas.clear)
        self.btn_eraser.toggled.connect(self._on_eraser_toggled)
        btn_cancel.clicked.connect(self.reject)
        btn_extract.clicked.connect(self._on_extract_clicked)


    def _on_eraser_toggled(self, checked: bool):
        # переключаем режим на холсте
        self.canvas.set_eraser_enabled(checked)
        self.btn_eraser.setText("Перо" if checked else "Ластик")

    def get_image(self) -> QImage:
        return self.canvas.get_image()

    def _on_extract_clicked(self):
        img = self.get_image()
        self.extractRequested.emit(img)

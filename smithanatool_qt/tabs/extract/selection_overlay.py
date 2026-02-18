from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, QPoint, QRect, QSize, Signal
from PySide6.QtGui import QPainter, QPen, QColor, QFont
from PySide6.QtWidgets import QWidget


class SelectionOverlay(QWidget):
    """
    ЛКМ по крестику — удалить область.
    ЛКМ внутри рамки — переместить.
    ЛКМ за правый нижний уголок — изменить размер.
    ПКМ: зажать и тянуть — добавить новую область.
    """
    rectDeleted = Signal(int, QRect)   # index, rect_img
    rectAdded = Signal(QRect)
    rectChanged = Signal(int, QRect, QRect)  # index, old_rect, new_rect

    def __init__(self, parent: QWidget, get_img_size, map_img_to_widget, map_widget_to_img):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setMouseTracking(True)

        self._img_to_w = map_img_to_widget
        self._w_to_img = map_widget_to_img

        # прямоугольники в координатах ИЗОБРАЖЕНИЯ
        self._rects_img: List[QRect] = []
        self._labels: List[str] = []          # подписи поверх рамок

        # временное рисование новой рамки (ПКМ)
        self._drag_start: Optional[QPoint] = None  # в координатах WIDGET (оверлея)
        self._drag_current: Optional[QPoint] = None

        # состояние перетаскивания/ресайза существующих рамок (ЛКМ)
        self._active_index: Optional[int] = None
        self._active_mode: Optional[str] = None  # "move" | "resize"
        self._active_start: Optional[QPoint] = None
        self._active_orig_rect_w: Optional[QRect] = None
        self._active_orig_rect_img: Optional[QRect] = None

        self._cross_size = 14  # размер крестика

    # ---- публичный API ----
    def set_rects_img(self, rects: List[QRect]):
        self._rects_img = list(rects)
        # подрежем/дополним подписи под длину rects
        if len(self._labels) != len(self._rects_img):
            self._labels = (self._labels + [""] * len(self._rects_img))[:len(self._rects_img)]
        self.update()

    def set_labels(self, labels: List[str]):
        self._labels = (list(labels) + [""] * len(self._rects_img))[:len(self._rects_img)]
        self.update()

    def rects_img(self) -> List[QRect]:
        return list(self._rects_img)

    def clear(self):
        self._rects_img.clear()
        self._labels.clear()
        self.update()

    # ---- рисование ----
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        # текущая тянущаяся рамка (ПКМ)
        if self._drag_start and self._drag_current:
            r = QRect(self._drag_start, self._drag_current).normalized()
            pen = QPen(QColor(66, 165, 245), 2, Qt.DashLine)
            p.setPen(pen)
            p.drawRect(r)

        # существующие рамки + крестик + номер + уголок
        font = QFont()
        font.setPointSize(9)
        p.setFont(font)

        for i, r_img in enumerate(self._rects_img):
            r_w = self._img_to_w(r_img)
            pen = QPen(QColor(255, 193, 7), 2)  # янтарная рамка
            p.setPen(pen)
            p.drawRect(r_w)

            # подпись/номер
            label = self._labels[i] if i < len(self._labels) and self._labels[i] else str(i + 1)
            label_rect = QRect(r_w.topLeft(), QSize(20, 14))
            p.fillRect(label_rect, QColor(255, 193, 7, 200))
            p.setPen(QPen(QColor(0, 0, 0)))
            p.drawText(label_rect, Qt.AlignCenter, label)

            # крестик для удаления
            cross_rect = self._cross_rect_widget(r_img)
            p.fillRect(cross_rect, QColor(255, 82, 82, 200))
            p.setPen(QPen(QColor(255, 255, 255), 2))
            x1 = cross_rect.topLeft() + QPoint(3, 3)
            x2 = cross_rect.bottomRight() - QPoint(3, 3)
            x3 = cross_rect.topRight() + QPoint(-3, 3)
            x4 = cross_rect.bottomLeft() + QPoint(3, -3)
            p.drawLine(x1, x2)
            p.drawLine(x3, x4)

            # уголок для ресайза (правый нижний)
            handle_rect = self._resize_handle_rect_widget(r_img)
            p.fillRect(handle_rect, QColor(66, 165, 245, 220))

    # ---- взаимодействие ----
    def mousePressEvent(self, ev):
        pt = ev.position().toPoint()

        if ev.button() == Qt.MouseButton.LeftButton:
            # удаление по клику в крестик
            for idx, r_img in enumerate(self._rects_img):
                cross = self._cross_rect_widget(r_img)
                if cross.contains(pt):
                    rect_deleted = self._rects_img[idx]
                    del self._rects_img[idx]
                    if idx < len(self._labels):
                        del self._labels[idx]
                    self.update()
                    self.rectDeleted.emit(idx, rect_deleted)
                    ev.accept()
                    return

            # выбор рамки для перемещения/ресайза
            self._active_index = None
            self._active_mode = None
            self._active_start = None
            self._active_orig_rect_w = None
            self._active_orig_rect_img = None

            # перебираем с конца, чтобы "верхняя" рамка ловилась первой
            for idx in reversed(range(len(self._rects_img))):
                r_img = self._rects_img[idx]
                r_w = self._img_to_w(r_img)

                # сначала уголок-ресайз
                handle = self._resize_handle_rect_widget(r_img)
                if handle.contains(pt):
                    self._active_index = idx
                    self._active_mode = "resize"
                    self._active_start = pt
                    self._active_orig_rect_w = QRect(r_w)
                    self._active_orig_rect_img = QRect(r_img)
                    ev.accept()
                    return

                # потом — попадание внутрь рамки для перемещения
                if r_w.contains(pt):
                    self._active_index = idx
                    self._active_mode = "move"
                    self._active_start = pt
                    self._active_orig_rect_w = QRect(r_w)
                    self._active_orig_rect_img = QRect(r_img)
                    ev.accept()
                    return

        if ev.button() == Qt.MouseButton.RightButton:
            # начало рисования новой области
            self._drag_start = pt
            self._drag_current = self._drag_start
            self.update()
            ev.accept()
            return

        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        pt = ev.position().toPoint()

        # перетаскивание/ресайз существующей рамки (ЛКМ)
        if self._active_mode and (ev.buttons() & Qt.LeftButton) and self._active_index is not None:
            if self._active_orig_rect_w is None:
                return
            orig_w = self._active_orig_rect_w
            if self._active_mode == "move":
                delta = pt - self._active_start
                new_rect_w = orig_w.translated(delta)
            else:  # "resize"
                tl = orig_w.topLeft()
                new_rect_w = QRect(tl, pt).normalized()
                if new_rect_w.width() < 3:
                    new_rect_w.setWidth(3)
                if new_rect_w.height() < 3:
                    new_rect_w.setHeight(3)

            # в координаты изображения + отсечение по границам
            new_rect_img = self._w_to_img(new_rect_w)
            self._rects_img[self._active_index] = new_rect_img
            self.update()
            ev.accept()
            return

        # рисование новой рамки (ПКМ)
        if self._drag_start is not None:
            self._drag_current = pt
            self.update()
            ev.accept()
            return

        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        pt = ev.position().toPoint()

        # завершение перемещения/ресайза
        if ev.button() == Qt.MouseButton.LeftButton and self._active_mode and self._active_index is not None:
            new_rect_img = self._rects_img[self._active_index]
            old_rect_img = self._active_orig_rect_img or new_rect_img
            if new_rect_img != old_rect_img:
                self.rectChanged.emit(self._active_index, old_rect_img, new_rect_img)

            self._active_index = None
            self._active_mode = None
            self._active_start = None
            self._active_orig_rect_w = None
            self._active_orig_rect_img = None
            ev.accept()
            return

        # завершение рисования новой области (ПКМ)
        if ev.button() == Qt.MouseButton.RightButton and self._drag_start is not None:
            r = QRect(self._drag_start, pt).normalized()
            r_img = self._w_to_img(r)
            if r_img.width() > 3 and r_img.height() > 3:
                self._rects_img.append(r_img)
                self._labels.append("")
                self.rectAdded.emit(r_img)
            self._drag_start = None
            self._drag_current = None
            self.update()
            ev.accept()
            return

        super().mouseReleaseEvent(ev)

    # ---- утилиты ----
    def _cross_rect_widget(self, r_img: QRect) -> QRect:
        r_w = self._img_to_w(r_img)
        return QRect(r_w.topLeft() + QPoint(22, 0), QSize(self._cross_size, self._cross_size))

    def _resize_handle_rect_widget(self, r_img: QRect) -> QRect:
        """Маленький квадратик в правом нижнем углу рамки для изменения размера."""
        r_w = self._img_to_w(r_img)
        size = 12
        return QRect(r_w.bottomRight() - QPoint(size, size), QSize(size, size))

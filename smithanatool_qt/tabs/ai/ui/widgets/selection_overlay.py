from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, QPoint, QRect, QSize, Signal
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QPainterPath
from PySide6.QtWidgets import QWidget


class SelectionOverlay(QWidget):
    """
    ЛКМ по крестику — удалить область.
    ЛКМ внутри рамки — переместить.
    ЛКМ по любой стороне или углу рамки — изменить размер.
    ПКМ: зажать и тянуть — добавить новую область.

    Дополнительно:
    - при клике по рамке выставляется selection (signal rectSelected)
    - при клике мимо рамок selection очищается (signal selectionCleared)
    """

    rectDeleted = Signal(int, QRect)  # index, rect_img
    rectAdded = Signal(QRect)
    rectChanged = Signal(int, QRect, QRect)  # index, old_rect, new_rect

    # Выбор области (для синхронизации со списком справа)
    rectSelected = Signal(int, QRect)  # overlay_index, rect_img
    selectionCleared = Signal()

    def __init__(self, parent: QWidget, get_img_size, map_img_to_widget, map_widget_to_img):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setMouseTracking(True)

        self._img_to_w = map_img_to_widget
        self._w_to_img = map_widget_to_img

        # прямоугольники в координатах ИЗОБРАЖЕНИЯ
        self._rects_img: List[QRect] = []
        self._labels: List[str] = []  # подписи поверх рамок

        # выбранная рамка (индекс в self._rects_img)
        self._selected_index: Optional[int] = None

        # временное рисование новой рамки (ПКМ)
        self._drag_start: Optional[QPoint] = None  # в координатах WIDGET (оверлея)
        self._drag_current: Optional[QPoint] = None

        # состояние перетаскивания/ресайза существующих рамок (ЛКМ)
        self._active_index: Optional[int] = None
        self._active_mode: Optional[str] = None  # "move" | "resize_l" | "resize_tl" | ...
        self._active_start: Optional[QPoint] = None
        self._active_orig_rect_w: Optional[QRect] = None
        self._active_orig_rect_img: Optional[QRect] = None

        self._create_button = Qt.MouseButton.RightButton

        self._cross_size = 14  # размер крестика
        self._resize_margin = 8  # толщина активной зоны по краям рамки

    # ---- публичный API ----
    def set_create_button(self, btn: Qt.MouseButton) -> None:
        if btn not in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            btn = Qt.MouseButton.RightButton
        self._create_button = btn

    def set_rects_img(self, rects: List[QRect]):
        self._rects_img = list(rects)
        # подрежем/дополним подписи под длину rects
        if len(self._labels) != len(self._rects_img):
            self._labels = (self._labels + [""] * len(self._rects_img))[: len(self._rects_img)]

        # если после обновления список стал короче — сбросим selection
        if self._selected_index is not None and not (0 <= self._selected_index < len(self._rects_img)):
            self._selected_index = None

        self.update()

    def set_labels(self, labels: List[str]):
        self._labels = (list(labels) + [""] * len(self._rects_img))[: len(self._rects_img)]
        self.update()

    def rects_img(self) -> List[QRect]:
        return list(self._rects_img)

    def clear(self):
        self._rects_img.clear()
        self._labels.clear()
        self._selected_index = None
        self.update()

    # ---- selection API ----
    def selected_index(self) -> Optional[int]:
        return self._selected_index

    def set_selected_index(self, idx: Optional[int]) -> None:
        """Установить выделение программно (БЕЗ эмита сигналов)."""
        if idx is None or idx < 0 or idx >= len(self._rects_img):
            if self._selected_index is not None:
                self._selected_index = None
                self.update()
            return
        if self._selected_index != idx:
            self._selected_index = idx
            self.update()

    def clear_selection(self) -> None:
        self.set_selected_index(None)

    def _user_select(self, idx: Optional[int]) -> None:
        """Выделение от пользователя (С ЭМИТОМ сигналов)."""
        prev = self._selected_index
        self.set_selected_index(idx)
        if self._selected_index is None:
            if prev is not None:
                try:
                    self.selectionCleared.emit()
                except Exception:
                    pass
        else:
            try:
                self.rectSelected.emit(self._selected_index, self._rects_img[self._selected_index])
            except Exception:
                pass

    # ---- рисование ----
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        # текущая тянущаяся рамка (ПКМ)
        if self._drag_start and self._drag_current:
            r = QRect(self._drag_start, self._drag_current).normalized()
            radius = min(2.0, r.width() / 2.0, r.height() / 2.0)
            pen = QPen(QColor(142,53,253), 2, Qt.DashLine)
            p.setPen(pen)
            p.drawRoundedRect(r, radius, radius)

        # существующие рамки + крестик + номер
        font = QFont()
        font.setPointSize(9)
        p.setFont(font)

        for i, r_img in enumerate(self._rects_img):
            r_w = self._img_to_w(r_img)
            radius = min(2.0, r_w.width() / 2.0, r_w.height() / 2.0)

            path = QPainterPath()
            path.addRoundedRect(float(r_w.x()), float(r_w.y()), float(r_w.width()), float(r_w.height()), radius, radius)

            # подпись/номер
            # подпись/номер
            label = self._labels[i] if i < len(self._labels) and self._labels[i] else str(i + 1)
            label_rect = QRect(r_w.topLeft(), QSize(20, 14))
            badge_radius = radius

            # выбранная рамка: подсветка + синяя рамка
            if self._selected_index is not None and i == self._selected_index:
                p.fillPath(path, QColor(66, 165, 245, 40))
                pen = QPen(QColor(35, 135, 213), 2)
                label_color = QColor(35, 135, 213, 200)
            else:
                pen = QPen(QColor(142, 53, 253), 2)
                p.fillPath(path, QColor(227, 204, 255, 40))
                label_color = QColor(142, 53, 253, 200)

            p.setPen(Qt.NoPen)
            p.setBrush(label_color)
            p.drawRoundedRect(label_rect, badge_radius, badge_radius)

            p.setPen(QPen(QColor(255, 255, 255)))
            p.drawText(label_rect, Qt.AlignCenter, label)

            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r_w, radius, radius)

            # крестик для удаления
            cross_rect = self._cross_rect_widget(r_img)
            cross_radius = radius

            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 82, 82, 200))
            p.drawRoundedRect(cross_rect, cross_radius, cross_radius)

            p.setPen(QPen(QColor(255, 255, 255), 2))
            x1 = cross_rect.topLeft() + QPoint(3, 3)
            x2 = cross_rect.bottomRight() - QPoint(3, 3)
            x3 = cross_rect.topRight() + QPoint(-3, 3)
            x4 = cross_rect.bottomLeft() + QPoint(3, -3)
            p.drawLine(x1, x2)
            p.drawLine(x3, x4)

    # ---- взаимодействие ----
    def mousePressEvent(self, ev):
        pt = ev.position().toPoint()

        # 1) ЛКМ: сначала пытаемся работать с существующими рамками
        if ev.button() == Qt.MouseButton.LeftButton:
            # удаление по клику в крестик
            for idx, r_img in enumerate(self._rects_img):
                if self._cross_rect_widget(r_img).contains(pt):
                    rect_deleted = self._rects_img[idx]
                    del self._rects_img[idx]
                    if idx < len(self._labels):
                        del self._labels[idx]

                    # поддержка selection при удалении
                    if self._selected_index is not None:
                        if idx == self._selected_index:
                            self._selected_index = None
                            self.selectionCleared.emit()
                        elif idx < self._selected_index:
                            self._selected_index -= 1

                    self.unsetCursor()
                    self.update()
                    self.rectDeleted.emit(idx, rect_deleted)
                    ev.accept()
                    return

            # сброс активного состояния
            self._active_index = None
            self._active_mode = None
            self._active_start = None
            self._active_orig_rect_w = None
            self._active_orig_rect_img = None

            # выбор рамки для move/resize (с конца)
            for idx in reversed(range(len(self._rects_img))):
                r_img = self._rects_img[idx]
                r_w = self._img_to_w(r_img)

                resize_mode = self._hit_test_resize_zone_widget(r_img, pt)
                if resize_mode is not None:
                    self._user_select(idx)
                    self._active_index = idx
                    self._active_mode = resize_mode
                    self._active_start = pt
                    self._active_orig_rect_w = QRect(r_w)
                    self._active_orig_rect_img = QRect(r_img)
                    self._set_cursor_for_mode(resize_mode)
                    ev.accept()
                    return

                if r_w.contains(pt):
                    self._user_select(idx)
                    self._active_index = idx
                    self._active_mode = "move"
                    self._active_start = pt
                    self._active_orig_rect_w = QRect(r_w)
                    self._active_orig_rect_img = QRect(r_img)
                    self.setCursor(Qt.SizeAllCursor)
                    ev.accept()
                    return

            # клик мимо рамок
            self._user_select(None)
            self.unsetCursor()

            # если ЛКМ назначена кнопкой создания — начинаем создание рамки
            if self._create_button == Qt.MouseButton.LeftButton:
                self._drag_start = pt
                self._drag_current = pt
                self.update()
                ev.accept()
                return

            ev.accept()
            return

        # 2) Создание рамки по create_button (обычно ПКМ)
        if ev.button() == self._create_button:
            self._user_select(None)  # чтобы список тоже снял выделение
            self.unsetCursor()
            self._drag_start = pt
            self._drag_current = pt
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
            else:
                new_rect_w = QRect(orig_w)
                mode = self._active_mode.split("_", 1)[1]  # tl / r / b / ...
                min_size = 3

                if "l" in mode:
                    new_left = min(pt.x(), new_rect_w.right() - min_size)
                    new_rect_w.setLeft(new_left)

                if "r" in mode:
                    new_right = max(pt.x(), new_rect_w.left() + min_size)
                    new_rect_w.setRight(new_right)

                if "t" in mode:
                    new_top = min(pt.y(), new_rect_w.bottom() - min_size)
                    new_rect_w.setTop(new_top)

                if "b" in mode:
                    new_bottom = max(pt.y(), new_rect_w.top() + min_size)
                    new_rect_w.setBottom(new_bottom)

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

        self._update_hover_cursor(pt)
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        pt = ev.position().toPoint()

        # завершение move/resize (ЛКМ)
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
            self._update_hover_cursor(pt)
            ev.accept()
            return

        # завершение СОЗДАНИЯ — по create_button
        if ev.button() == self._create_button and self._drag_start is not None:
            r = QRect(self._drag_start, pt).normalized()
            r_img = self._w_to_img(r)
            if r_img.width() > 3 and r_img.height() > 3:
                self._rects_img.append(r_img)
                self._labels.append("")
                self.rectAdded.emit(r_img)

            self._drag_start = None
            self._drag_current = None
            self._update_hover_cursor(pt)
            self.update()
            ev.accept()
            return

        super().mouseReleaseEvent(ev)

    def leaveEvent(self, ev):
        if self._active_mode is None and self._drag_start is None:
            self.unsetCursor()
        super().leaveEvent(ev)

    # ---- утилиты ----
    def _cross_rect_widget(self, r_img: QRect) -> QRect:
        r_w = self._img_to_w(r_img)
        return QRect(r_w.topLeft() + QPoint(22, 0), QSize(self._cross_size, self._cross_size))

    def _hit_test_resize_zone_widget(self, r_img: QRect, pt: QPoint) -> Optional[str]:
        """
        Возвращает:
        resize_tl, resize_tr, resize_bl, resize_br,
        resize_l, resize_r, resize_t, resize_b
        или None, если курсор не на рамке.
        """
        r_w = self._img_to_w(r_img)
        m = self._resize_margin

        outer = r_w.adjusted(-m, -m, m, m)
        if not outer.contains(pt):
            return None

        inner = r_w.adjusted(m, m, -m, -m)
        if inner.isValid() and inner.contains(pt):
            return None

        left = abs(pt.x() - r_w.left()) <= m
        right = abs(pt.x() - r_w.right()) <= m
        top = abs(pt.y() - r_w.top()) <= m
        bottom = abs(pt.y() - r_w.bottom()) <= m

        if top and left:
            return "resize_tl"
        if top and right:
            return "resize_tr"
        if bottom and left:
            return "resize_bl"
        if bottom and right:
            return "resize_br"
        if left:
            return "resize_l"
        if right:
            return "resize_r"
        if top:
            return "resize_t"
        if bottom:
            return "resize_b"

        return None

    def _set_cursor_for_mode(self, mode: Optional[str]) -> None:
        if mode in ("resize_l", "resize_r"):
            self.setCursor(Qt.SizeHorCursor)
        elif mode in ("resize_t", "resize_b"):
            self.setCursor(Qt.SizeVerCursor)
        elif mode in ("resize_tl", "resize_br"):
            self.setCursor(Qt.SizeFDiagCursor)
        elif mode in ("resize_tr", "resize_bl"):
            self.setCursor(Qt.SizeBDiagCursor)
        elif mode == "move":
            self.setCursor(Qt.SizeAllCursor)
        else:
            self.unsetCursor()

    def _update_hover_cursor(self, pt: QPoint) -> None:
        for idx in reversed(range(len(self._rects_img))):
            r_img = self._rects_img[idx]
            if self._cross_rect_widget(r_img).contains(pt):
                self.setCursor(Qt.PointingHandCursor)
                return

            resize_mode = self._hit_test_resize_zone_widget(r_img, pt)
            if resize_mode is not None:
                self._set_cursor_for_mode(resize_mode)
                return

            if self._img_to_w(r_img).contains(pt):
                self.setCursor(Qt.SizeAllCursor)
                return

        self.unsetCursor()

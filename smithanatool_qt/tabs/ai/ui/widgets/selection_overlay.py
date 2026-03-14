from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from .overlay_geometry import (
    cross_rect_widget,
    cursor_shape_for_mode,
    hit_test_resize_zone_widget,
    rect_from_drag,
)
from .overlay_paint import paint_overlay


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
        self._clear_drag_state()
        self._clear_active_interaction()
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
        painter = QPainter(self)
        paint_overlay(
            widget=self,
            painter=painter,
            rects_img=self._rects_img,
            labels=self._labels,
            selected_index=self._selected_index,
            drag_start=self._drag_start,
            drag_current=self._drag_current,
            img_to_w=self._img_to_w,
            cross_size=self._cross_size,
        )

    # ---- взаимодействие ----
    def mousePressEvent(self, ev):
        pt = ev.position().toPoint()

        # 1) ЛКМ: сначала пытаемся работать с существующими рамками
        if ev.button() == Qt.MouseButton.LeftButton:
            if self._try_delete_rect(pt, ev):
                return

            self._clear_active_interaction()

            if self._try_start_interaction(pt, ev):
                return

            # клик мимо рамок
            self._user_select(None)
            self.unsetCursor()

            # если ЛКМ назначена кнопкой создания — начинаем создание рамки
            if self._create_button == Qt.MouseButton.LeftButton:
                self._start_drag(pt)
                self.update()
                ev.accept()
                return

            ev.accept()
            return

        # 2) Создание рамки по create_button (обычно ПКМ)
        if ev.button() == self._create_button:
            self._user_select(None)  # чтобы список тоже снял выделение
            self.unsetCursor()
            self._start_drag(pt)
            self.update()
            ev.accept()
            return

        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        pt = ev.position().toPoint()

        # перетаскивание/ресайз существующей рамки (ЛКМ)
        if self._active_mode and (ev.buttons() & Qt.LeftButton) and self._active_index is not None:
            if self._active_orig_rect_w is None or self._active_start is None:
                return
            new_rect_w = rect_from_drag(self._active_orig_rect_w, self._active_start, pt, self._active_mode)
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

            self._clear_active_interaction()
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

            self._clear_drag_state()
            self._update_hover_cursor(pt)
            self.update()
            ev.accept()
            return

        super().mouseReleaseEvent(ev)

    def leaveEvent(self, ev):
        if self._active_mode is None and self._drag_start is None:
            self.unsetCursor()
        super().leaveEvent(ev)

    # ---- interaction helpers ----
    def _try_delete_rect(self, pt: QPoint, ev) -> bool:
        for idx, r_img in enumerate(self._rects_img):
            if not self._cross_rect_widget(r_img).contains(pt):
                continue

            rect_deleted = self._rects_img[idx]
            del self._rects_img[idx]
            if idx < len(self._labels):
                del self._labels[idx]

            self._update_selection_after_delete(idx)
            self.unsetCursor()
            self.update()
            self.rectDeleted.emit(idx, rect_deleted)
            ev.accept()
            return True

        return False

    def _try_start_interaction(self, pt: QPoint, ev) -> bool:
        for idx in reversed(range(len(self._rects_img))):
            r_img = self._rects_img[idx]
            r_w = self._img_to_w(r_img)

            resize_mode = self._hit_test_resize_zone_widget(r_img, pt)
            if resize_mode is not None:
                self._begin_active_interaction(idx, resize_mode, pt, r_w, r_img)
                ev.accept()
                return True

            if r_w.contains(pt):
                self._begin_active_interaction(idx, "move", pt, r_w, r_img)
                ev.accept()
                return True

        return False

    def _begin_active_interaction(self, idx: int, mode: str, pt: QPoint, r_w: QRect, r_img: QRect) -> None:
        self._user_select(idx)
        self._active_index = idx
        self._active_mode = mode
        self._active_start = pt
        self._active_orig_rect_w = QRect(r_w)
        self._active_orig_rect_img = QRect(r_img)
        self._set_cursor_for_mode(mode)

    def _update_selection_after_delete(self, idx: int) -> None:
        if self._selected_index is None:
            return
        if idx == self._selected_index:
            self._selected_index = None
            self.selectionCleared.emit()
        elif idx < self._selected_index:
            self._selected_index -= 1

    def _clear_active_interaction(self) -> None:
        self._active_index = None
        self._active_mode = None
        self._active_start = None
        self._active_orig_rect_w = None
        self._active_orig_rect_img = None

    def _start_drag(self, pt: QPoint) -> None:
        self._drag_start = pt
        self._drag_current = pt

    def _clear_drag_state(self) -> None:
        self._drag_start = None
        self._drag_current = None

    # ---- geometry/cursor helpers ----
    def _cross_rect_widget(self, r_img: QRect) -> QRect:
        return cross_rect_widget(r_img, self._img_to_w, self._cross_size)

    def _hit_test_resize_zone_widget(self, r_img: QRect, pt: QPoint) -> Optional[str]:
        return hit_test_resize_zone_widget(r_img, pt, self._img_to_w, self._resize_margin)

    def _set_cursor_for_mode(self, mode: Optional[str]) -> None:
        cursor_shape = cursor_shape_for_mode(mode)
        if cursor_shape is None:
            self.unsetCursor()
            return
        self.setCursor(cursor_shape)

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

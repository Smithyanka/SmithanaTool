from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QPointF, QRect
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import QLabel, QScrollArea


class PanZoomLabel(QLabel):
    def __init__(self, owner: "PreviewPanel", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._show_slice_labels = True
        self._owner = owner
        self._scroll: Optional[QScrollArea] = None
        self._panning = False
        self._pan_start = QPointF()
        self._hbar0 = 0
        self._vbar0 = 0
        self.setMouseTracking(True)

        self._space_down = False

    def set_show_slice_labels(self, on: bool):
        self._show_slice_labels = bool(on)
        self.update()  # мгновенная перерисовка

    def attach_scroll(self, scroll: QScrollArea):
        self._scroll = scroll

    def wheelEvent(self, e):
        # Ctrl + колесо = зум; без Ctrl — прокрутка ScrollArea
        if e.modifiers() & Qt.ControlModifier:
            delta = e.angleDelta().y()
            if delta == 0:
                return
            anchor = e.position().toPoint()
            factor = 1.1 if delta > 0 else 1 / 1.1
            self._owner._zoom_by(factor, anchor=anchor)
            e.accept()
        else:
            e.ignore()

    def _set_space_down(self, on: bool) -> None:
        self._space_down = bool(on)
        # если сейчас тащим — курсор управляется панорамированием
        if self._panning:
            return
        self.setCursor(Qt.OpenHandCursor if self._space_down else Qt.ArrowCursor)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Space and not e.isAutoRepeat():
            self._set_space_down(True)
            e.accept()
            return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key_Space and not e.isAutoRepeat():
            self._set_space_down(False)
            e.accept()
            return
        super().keyReleaseEvent(e)
    def mousePressEvent(self, e):
        # чтобы хоткеи работали после любого клика по превью
        self.setFocus(Qt.MouseFocusReason)
        try:
            self._owner.setFocus(Qt.MouseFocusReason)
        except Exception:
            pass

        # Панорамирование:
        #   - СКМ всегда
        #   - ЛКМ только при зажатом пробеле
        if e.button() == Qt.MiddleButton or (e.button() == Qt.LeftButton and self._space_down):
            # при первом драге отключаем fit для нормального панорамирования
            if self._owner._fit_to_window:
                self._owner._set_fit(True)

            self._panning = True
            self.setCursor(Qt.ClosedHandCursor)
            self._pan_start = e.globalPosition()
            e.accept()
            if self._scroll:
                self._hbar0 = self._scroll.horizontalScrollBar().value()
                self._vbar0 = self._scroll.verticalScrollBar().value()
            return
        # ЛКМ = выделение (если не зажат Space), а в режиме нарезки — перетаскивание границ
        if e.button() == Qt.LeftButton:
            # Инструмент "Рамка" (кадрирование)
            if getattr(self._owner, "_frame_enabled", False) and not self._space_down:
                if self._owner._frame_press(e.position().toPoint()):
                    e.accept()
                    return

            # В режиме нарезки — ЛКМ двигает границы
            if self._owner._slice_enabled:
                idx = self._owner._boundary_under_cursor(e.position().toPoint())
                if idx is not None:
                    self._owner._drag_boundary_index = idx
                    self.setCursor(Qt.SizeVerCursor)
                    e.accept()
                    return
                # клик вне границы — ничего
                e.accept()
                return

            # Обычный режим: выделение
            r = self._pixmap_rect_on_label()
            if not r.contains(e.position().toPoint()):
                self._owner._clear_selection()
                e.accept()
                return

            if self._owner._press_selection(e.position().toPoint()):
                e.accept()
            else:
                super().mousePressEvent(e)
            return

        super().mousePressEvent(e)

    def _pixmap_rect_on_label(self) -> QRect:
        # We don't rely on QLabel pixmap scaling anymore.
        # Display size is owned by the panel (virtual canvas size).
        ds = getattr(self._owner, "_display_size", None)
        if not ds or ds.width() <= 0 or ds.height() <= 0:
            return QRect()

        w, h = int(ds.width()), int(ds.height())
        a = self.alignment()

        # Горизонтальное выравнивание
        if a & Qt.AlignRight:
            x0 = self.width() - w
        elif a & Qt.AlignHCenter:
            x0 = (self.width() - w) // 2
        else:  # AlignLeft или по умолчанию
            x0 = 0

        # Вертикальное выравнивание
        if a & Qt.AlignBottom:
            y0 = self.height() - h
        elif a & Qt.AlignVCenter:
            y0 = (self.height() - h) // 2
        else:  # AlignTop или по умолчанию
            y0 = 0

        return QRect(int(x0), int(y0), int(w), int(h))

    def mouseMoveEvent(self, e):
        if self._panning and self._scroll:
            hbar = self._scroll.horizontalScrollBar()
            vbar = self._scroll.verticalScrollBar()

            # инкрементальная дельта в глобальных координатах экрана
            delta = e.globalPosition() - self._pan_start
            hbar.setValue(hbar.value() - int(delta.x()))
            vbar.setValue(vbar.value() - int(delta.y()))

            # "схватываем" текущую точку как новую базу
            self._pan_start = e.globalPosition()
            e.accept()
            return

        if self._owner._slice_enabled and self._owner._drag_boundary_index is not None:
            self._owner._drag_boundary_to(e.position().toPoint())
            e.accept()
            return

        # Рамка: drag/hover
        if getattr(self._owner, "_frame_enabled", False):
            if getattr(self._owner, "_frame_drag", None) is not None:
                self._owner._frame_move(e.position().toPoint())
                e.accept()
                return
            if self._owner._frame_update_hover_cursor(e.position().toPoint()):
                e.accept()
                return

        if self._owner._sel_active:
            self._owner._update_selection(e.position().toPoint())
            e.accept()
            return

        if self._owner._resizing_edge:
            self._owner._resize_selection(e.position().toPoint())
            e.accept()
            return

        # Навели на край выделения — курсор SizeVer
        if self._owner._update_hover_cursor(e.position().toPoint()):
            e.accept()
        else:
            super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._panning and e.button() in (Qt.LeftButton, Qt.MiddleButton):
            self._panning = False
            self._set_space_down(self._space_down)  # вернёт OpenHand или Arrow
            e.accept()
            return

        if e.button() == Qt.LeftButton:
            if getattr(self._owner, "_frame_enabled", False) and getattr(self._owner, "_frame_drag", None) is not None:
                self._owner._frame_release(e.position().toPoint())
                e.accept()
                return

            if self._owner._slice_enabled:
                self._owner._drag_boundary_index = None
                self.setCursor(Qt.ArrowCursor)
                e.accept()
                return

            if self._owner._sel_active:
                self._owner._end_selection(e.position().toPoint())
                e.accept()
                return

            if self._owner._resizing_edge:
                self._owner._end_resize()
                e.accept()
                return

        super().mouseReleaseEvent(e)

    def paintEvent(self, ev):
        owner = getattr(self, "_owner", None)
        pm = getattr(owner, "_view_pm", None) if owner is not None else None
        img = getattr(owner, "_view_img", None) if owner is not None else None

        # No image? fall back to the default QLabel painting (text like "Нет изображения").
        has_pm = pm is not None and getattr(pm, "isNull", lambda: True)() is False
        has_img = img is not None and getattr(img, "isNull", lambda: True)() is False

        if not has_pm and not has_img:
            super().paintEvent(ev)
            return

        # Paint base widget (stylesheet background, etc.)
        super().paintEvent(ev)

        pmr = self._pixmap_rect_on_label()
        if pmr.isNull() or pmr.width() <= 0 or pmr.height() <= 0:
            return

        # Draw only the visible part of the image (clipped by Qt to the update region).
        p = QPainter(self)

        # Use the paint event rect as the update region (more robust than clipBoundingRect across styles/platforms).
        target = ev.rect().intersected(pmr)
        if not target.isNull() and target.width() > 0 and target.height() > 0:
            # Map target rect (label coords) -> source rect (image coords)
            if has_pm:
                iw = max(1, int(pm.width()))
                ih = max(1, int(pm.height()))
            else:
                iw = max(1, int(img.width()))
                ih = max(1, int(img.height()))
            rw = max(1, int(pmr.width()))
            rh = max(1, int(pmr.height()))

            sx = (target.left() - pmr.left()) * iw / rw
            sy = (target.top() - pmr.top()) * ih / rh
            sw = target.width() * iw / rw
            sh = target.height() * ih / rh
            src_rect = QRect(int(sx), int(sy), max(1, int(sw)), max(1, int(sh)))
            if has_pm:
                p.drawPixmap(target, pm, src_rect)
            else:
                p.drawImage(target, img, src_rect)

        p.end()

        # Рамка (кадрирование) рисуется поверх всех остальных оверлеев.
        if getattr(self._owner, "_frame_enabled", False):
            pmr = self._pixmap_rect_on_label()
            if not pmr.isNull():
                p = QPainter(self)
                p.setRenderHint(QPainter.Antialiasing, False)

                # Затемнение в режиме рамки:
                #   - если рамка ещё не создана: затемняем весь pixmap
                #   - если рамка есть: затемняем область вокруг рамки
                shade = QColor(0, 0, 0, 120)
                rect_img = getattr(self._owner, "_frame_rect_img", None)
                if rect_img is None:
                    p.fillRect(pmr, shade)
                    p.end()
                else:
                    rect_label = self._owner._image_rect_to_label_rect(rect_img)
                    if not rect_label or rect_label.isNull():
                        p.fillRect(pmr, shade)
                        p.end()
                    else:
                        # top
                        if rect_label.top() > pmr.top():
                            p.fillRect(QRect(pmr.left(), pmr.top(), pmr.width(), rect_label.top() - pmr.top()), shade)
                        # bottom
                        if rect_label.bottom() < pmr.bottom():
                            p.fillRect(
                                QRect(pmr.left(), rect_label.bottom() + 1, pmr.width(), pmr.bottom() - rect_label.bottom()),
                                shade,
                            )
                        # left
                        if rect_label.left() > pmr.left():
                            p.fillRect(
                                QRect(pmr.left(), rect_label.top(), rect_label.left() - pmr.left(), rect_label.height()),
                                shade,
                            )
                        # right
                        if rect_label.right() < pmr.right():
                            p.fillRect(
                                QRect(
                                    rect_label.right() + 1,
                                    rect_label.top(),
                                    pmr.right() - rect_label.right(),
                                    rect_label.height(),
                                ),
                                shade,
                            )

                        # Border
                        pen = QPen(QColor(0, 120, 215, 220), 2)
                        p.setPen(pen)
                        p.drawRect(rect_label.adjusted(0, 0, -1, -1))

                        # Rule-of-thirds grid
                        grid_pen = QPen(QColor(255, 255, 255, 70), 1)
                        p.setPen(grid_pen)
                        x1 = rect_label.left()
                        x2 = rect_label.right()
                        y1 = rect_label.top()
                        y2 = rect_label.bottom()
                        w = max(1, rect_label.width())
                        h = max(1, rect_label.height())
                        vx1 = x1 + w // 3
                        vx2 = x1 + (w * 2) // 3
                        hy1 = y1 + h // 3
                        hy2 = y1 + (h * 2) // 3
                        p.drawLine(vx1, y1, vx1, y2)
                        p.drawLine(vx2, y1, vx2, y2)
                        p.drawLine(x1, hy1, x2, hy1)
                        p.drawLine(x1, hy2, x2, hy2)

                        # Resolution badge (W×H px)
                        try:
                            r_img = getattr(self._owner, "_frame_rect_img", None)
                            if r_img is not None:
                                w_img = int(r_img.width())
                                h_img = int(r_img.height())
                                text = f"{w_img}×{h_img}px"

                                pad = 6
                                fm = p.fontMetrics()
                                br = fm.boundingRect(text)

                                # Place near top-left inside the rect; clamp to pixmap bounds.
                                x_text = rect_label.left() + 6
                                y_text = rect_label.top() + 6

                                bg_w = br.width() + pad * 2
                                bg_h = br.height() + pad * 2
                                x_text = max(pmr.left(), min(x_text, pmr.right() - bg_w + 1))
                                y_text = max(pmr.top(), min(y_text, pmr.bottom() - bg_h + 1))

                                bg_rect = QRect(x_text, y_text, bg_w, bg_h)
                                p.fillRect(bg_rect, QColor(0, 0, 0, 160))
                                p.setPen(QColor(255, 255, 255))
                                p.drawText(bg_rect.adjusted(pad, pad, -pad, -pad), Qt.AlignLeft | Qt.AlignVCenter, text)
                        except Exception:
                            pass

                        # Handles
                        hs = int(getattr(self._owner, "_frame_handle_size", 6))
                        pad = hs
                        handle_fill = QColor(255, 255, 255, 220)
                        handle_pen = QPen(QColor(0, 120, 215, 220), 1)
                        p.setPen(handle_pen)
                        p.setBrush(handle_fill)

                        l = rect_label.left()
                        r = rect_label.right()
                        t = rect_label.top()
                        b = rect_label.bottom()
                        cx = (l + r) // 2
                        cy = (t + b) // 2
                        pts = [(l, t), (cx, t), (r, t), (l, cy), (r, cy), (l, b), (cx, b), (r, b)]
                        for px, py in pts:
                            p.drawRect(QRect(px - pad, py - pad, pad * 2, pad * 2))

                        p.end()

        # If slice mode is enabled, it owns the overlay (and frame tool is expected to be disabled).
        if getattr(self._owner, "_slice_enabled", False) and not getattr(self._owner, "_frame_enabled", False) and getattr(self._owner, "_slice_bounds", None):
            ds = getattr(self._owner, "_display_size", None)
            if ds and ds.width() > 0 and ds.height() > 0:
                p = QPainter(self)
                p.setRenderHint(QPainter.Antialiasing, False)

                w = int(ds.width())
                h = int(ds.height())

                x0 = (self.width() - w) // 2 if (self.alignment() & Qt.AlignHCenter) else 0
                y0 = (self.height() - h) // 2 if (self.alignment() & Qt.AlignVCenter) else 0

                ys_label = self._owner._slice_bounds_on_label()
                ys_img = self._owner._slice_bounds

                # ----- заливки по чётности
                for i in range(len(ys_label) - 1):
                    top = y0 + ys_label[i]
                    bot = y0 + ys_label[i + 1]
                    rect = QRect(x0, top, w, max(1, bot - top))
                    if i % 2 == 0:
                        p.fillRect(rect, QColor(0, 120, 215, 40))
                    else:
                        p.fillRect(rect, QColor(0, 120, 215, 20))

                # ----- линии срезов
                pen = QPen(QColor(0, 120, 215, 220), 2)
                p.setPen(pen)
                for y in ys_label:
                    p.drawLine(x0, y0 + y, x0 + w, y0 + y)

                # ----- бейджи с разрешением (Ш×В) для каждого фрагмента
                if getattr(self, "_show_slice_labels", True):
                    img_w = None
                    if self._owner._current_path and self._owner._current_path in self._owner._images:
                        img_w = int(self._owner._images[self._owner._current_path].width())

                    if img_w:
                        pad = 6
                        p.setPen(QColor(255, 255, 255))
                        fm = p.fontMetrics()

                        for i in range(len(ys_label) - 1):
                            h_img = max(0, int(ys_img[i + 1] - ys_img[i]))
                            text = f"{img_w}×{h_img}"

                            x_text = x0 + 6
                            y_text = y0 + ys_label[i] + 6

                            br = fm.boundingRect(text)
                            bg_rect = QRect(x_text - pad, y_text - pad, br.width() + pad * 2, br.height() + pad * 2)

                            p.fillRect(bg_rect, QColor(0, 0, 0, 160))
                            p.drawText(bg_rect.adjusted(pad, pad, -pad, -pad), Qt.AlignLeft | Qt.AlignVCenter, text)

                p.end()
                return

        # Иначе — одиночное выделение
        if self._owner._has_selection():
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing, False)

            y1, y2 = self._owner._selection_on_label()
            if y1 is not None:
                ds = getattr(self._owner, "_display_size", None)
                w = int(ds.width()) if ds and ds.width() > 0 else self.width()
                x0 = (self.width() - w) // 2 if (self.alignment() & Qt.AlignHCenter) else 0
                h = int(ds.height()) if ds and ds.height() > 0 else self.height()
                y0 = (self.height() - h) // 2 if (self.alignment() & Qt.AlignVCenter) else 0

                rect = QRect(x0, y0 + y1, w, max(1, y2 - y1))
                p.fillRect(rect, QColor(0, 120, 215, 60))

                pen = QPen(QColor(0, 120, 215, 220), 2)
                p.setPen(pen)
                p.drawLine(x0, y0 + y1, x0 + w, y0 + y1)
                p.drawLine(x0, y0 + y2, x0 + w, y0 + y2)

            p.end()

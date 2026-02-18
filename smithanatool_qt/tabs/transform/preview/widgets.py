from PySide6.QtCore import Qt, QPointF, QRect
from PySide6.QtGui import (
    QPainter, QColor, QPen
)
from PySide6.QtWidgets import (
    QLabel, QScrollArea
)
from typing import Optional

class PanZoomLabel(QLabel):
    def __init__(self, owner: 'PreviewPanel', *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._show_slice_labels = True
        self._owner = owner
        self._scroll: Optional[QScrollArea] = None
        self._panning = False
        self._pan_start = QPointF()
        self._hbar0 = 0
        self._vbar0 = 0
        self.setMouseTracking(True)

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

    def mousePressEvent(self, e):
        if e.button() in (Qt.LeftButton, Qt.MiddleButton):
            # при первом драге отключаем fit для нормального панорамирования
            if self._owner._fit_to_window:
                self._owner._set_fit(True)

            self._panning = True
            self.setCursor(Qt.ClosedHandCursor)
            self._pan_start = e.globalPosition()  # глобальные координаты
            e.accept()
            if self._scroll:
                self._hbar0 = self._scroll.horizontalScrollBar().value()
                self._vbar0 = self._scroll.verticalScrollBar().value()
            return
        elif e.button() == Qt.RightButton:
            if self._owner._slice_enabled:
                idx = self._owner._boundary_under_cursor(e.position().toPoint())
                if idx is not None:
                    self._owner._drag_boundary_index = idx
                    self.setCursor(Qt.SizeVerCursor)
                    e.accept();
                    return
                else:
                    # В режиме нарезки правый клик вне границы — ничего не делаем
                    e.accept();
                    return
            r = self._pixmap_rect_on_label()
            if not r.contains(e.position().toPoint()):
                self._owner._clear_selection()
                e.accept()
                return
            # Обычный режим одиночного выделения
            if self._owner._press_selection(e.position().toPoint()):
                e.accept()
            else:
                super().mousePressEvent(e)
        else:
            super().mousePressEvent(e)
    def _pixmap_rect_on_label(self) -> QRect:
        pm = self.pixmap()
        if not pm or pm.isNull():
            return QRect()

        w, h = pm.width(), pm.height()
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
        elif self._owner._slice_enabled and self._owner._drag_boundary_index:
            self._owner._drag_boundary_to(e.position().toPoint());
            e.accept()
        elif self._owner._sel_active:
            self._owner._update_selection(e.position().toPoint())
            e.accept()
        elif self._owner._resizing_edge:
            self._owner._resize_selection(e.position().toPoint())
            e.accept()
        else:
            # Навели на край выделения — курсор SizeVer
            if self._owner._update_hover_cursor(e.position().toPoint()):
                e.accept()
            else:
                super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._panning and e.button() in (Qt.LeftButton, Qt.MiddleButton):
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
            e.accept()
            return
        elif e.button() == Qt.RightButton:
            if self._owner._slice_enabled:
                self._owner._drag_boundary_index = None
                self.setCursor(Qt.ArrowCursor)
                e.accept()
            elif self._owner._sel_active:
                self._owner._end_selection(e.position().toPoint());
                e.accept()
            elif self._owner._resizing_edge:
                self._owner._end_resize();
                e.accept()
        else:
            super().mouseReleaseEvent(e)

    def paintEvent(self, ev):
        super().paintEvent(ev)

        # Рисуем нарезку, если включена
        if getattr(self._owner, "_slice_enabled", False) and getattr(self._owner, "_slice_bounds", None):
            pm = self.pixmap()
            if pm:
                p = QPainter(self)
                p.setRenderHint(QPainter.Antialiasing, False)

                # размеры отображаемого pixmap на label
                w = pm.width()
                h = pm.height()

                # центровка
                x0 = (self.width() - w) // 2 if (self.alignment() & Qt.AlignHCenter) else 0
                y0 = (self.height() - h) // 2 if (self.alignment() & Qt.AlignVCenter) else 0

                # label-координаты горизонталей срезов
                ys_label = self._owner._slice_bounds_on_label()

                # image-координаты (оригинальные пиксели изображения)
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
                    # всегда берём ширину из исходного изображения
                    img_w = None
                    if (self._owner._current_path
                            and self._owner._current_path in self._owner._images):
                        img_w = int(self._owner._images[self._owner._current_path].width())

                    if img_w:
                        pad = 6
                        p.setPen(QColor(255, 255, 255))
                        fm = p.fontMetrics()

                        for i in range(len(ys_label) - 1):
                            # высота фрагмента в пикселях исходного изображения
                            h_img = max(0, int(ys_img[i + 1] - ys_img[i]))
                            text = f"{img_w}×{h_img}"

                            # позиция бейджа — в координатах label (чтобы двигался при зуме)
                            x_text = x0 + 6
                            y_text = y0 + ys_label[i] + 6

                            br = fm.boundingRect(text)
                            bg_rect = QRect(x_text - pad, y_text - pad,
                                            br.width() + pad * 2, br.height() + pad * 2)

                            # фон бейджа
                            p.fillRect(bg_rect, QColor(0, 0, 0, 160))
                            # текст
                            p.drawText(bg_rect.adjusted(pad, pad, -pad, -pad),
                                       Qt.AlignLeft | Qt.AlignVCenter, text)

                p.end()
                return

        # Иначе — одиночное выделение
        if self._owner._has_selection():
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing, False)

            y1, y2 = self._owner._selection_on_label()
            if y1 is not None:
                pm = self.pixmap()
                w = pm.width() if pm else self.width()
                x0 = (self.width() - w) // 2 if (self.alignment() & Qt.AlignHCenter) else 0
                h = pm.height() if pm else self.height()
                y0 = (self.height() - h) // 2 if (self.alignment() & Qt.AlignVCenter) else 0

                rect = QRect(x0, y0 + y1, w, max(1, y2 - y1))
                p.fillRect(rect, QColor(0, 120, 215, 60))

                pen = QPen(QColor(0, 120, 215, 220), 2)
                p.setPen(pen)
                p.drawLine(x0, y0 + y1, x0 + w, y0 + y1)
                p.drawLine(x0, y0 + y2, x0 + w, y0 + y2)
            p.end()

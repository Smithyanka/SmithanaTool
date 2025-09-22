from __future__ import annotations
from typing import Optional, Dict, List, Tuple
from pathlib import Path
from .preview.slice_mode import SliceModeMixin

from PySide6.QtCore import Qt, QSize, QPoint, QRect
from PySide6.QtGui import (
    QPixmap, QImage, QPainter, QColor, QPen,
    QShortcut, QKeySequence
)
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QStyle, QFrame, QFileDialog, QMessageBox
)

from concurrent.futures import ThreadPoolExecutor, as_completed
import os

# -----------------------------------------
# Внутренний QLabel: панорамирование, зум (через owner), выделение/резайз
# -----------------------------------------
class _PanZoomLabel(QLabel):
    def __init__(self, owner: 'PreviewPanel', *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._show_slice_labels = True
        self._owner = owner
        self._scroll: Optional[QScrollArea] = None
        self._panning = False
        self._pan_start = QPoint()
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
            factor = 1.1 if delta > 0 else 1/1.1
            self._owner._zoom_by(factor, anchor=anchor)
            e.accept()
        else:
            e.ignore()

    def mousePressEvent(self, e):
        # Пан/Зум ЛКМ/МКМ как раньше
        if e.button() in (Qt.LeftButton, Qt.MiddleButton):
            # Панорамирование
            self._panning = True
            self.setCursor(Qt.ClosedHandCursor)
            self._pan_start = e.position().toPoint()
            if self._scroll:
                self._hbar0 = self._scroll.horizontalScrollBar().value()
                self._vbar0 = self._scroll.verticalScrollBar().value()
            e.accept()
        elif e.button() == Qt.RightButton:
            if self._owner._slice_enabled:
                idx = self._owner._boundary_under_cursor(e.position().toPoint())
                if idx is not None:
                    self._owner._drag_boundary_index = idx
                    self.setCursor(Qt.SizeVerCursor)
                    e.accept(); return
                else:
                    # В режиме нарезки правый клик вне границы — ничего не делаем
                    e.accept(); return
            # Обычный режим одиночного выделения
            if self._owner._press_selection(e.position().toPoint()):
                e.accept()
            else:
                super().mousePressEvent(e)
        else:
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._panning and self._scroll:
            delta = e.position().toPoint() - self._pan_start
            self._scroll.horizontalScrollBar().setValue(self._hbar0 - delta.x())
            self._scroll.verticalScrollBar().setValue(self._vbar0 - delta.y())
            e.accept()
        elif self._owner._slice_enabled and self._owner._drag_boundary_index:
            self._owner._drag_boundary_to(e.position().toPoint()); e.accept()
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
        elif e.button() == Qt.RightButton:
            if self._owner._slice_enabled:
                self._owner._drag_boundary_index = None
                self.setCursor(Qt.ArrowCursor)
                e.accept()
            elif self._owner._sel_active:
                self._owner._end_selection(e.position().toPoint()); e.accept()
            elif self._owner._resizing_edge:
                self._owner._end_resize(); e.accept()
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


# -----------------------------------------
# Основная панель предпросмотра
# -----------------------------------------
class PreviewPanel(SliceModeMixin, QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Кэш изображений и история
        self._images: Dict[str, QImage] = {}
        self._undo: Dict[str, List[QImage]] = {}
        self._redo: Dict[str, List[QImage]] = {}
        self._clip: List[QImage] = []  # последний вырезанный фрагмент(ы)
        self._current_path: Optional[str] = None

        # Зум/Fit
        self._fit_to_window = True
        self._zoom = 1.0
        self._min_zoom = 0.05
        self._max_zoom = 8.0

        # Выделение
        self._sel_active = False
        self._sel_y1: Optional[int] = None
        self._sel_y2: Optional[int] = None
        self._resizing_edge: Optional[str] = None  # 'top' | 'bottom' | None

        
        # Нарезка (многофрагментный режим)
        self._slice_enabled: bool = False
        self._slice_count: int = 2
        self._slice_bounds: List[int] = []  # границы по оси Y в координатах ИЗОБРАЖЕНИЯ: [0, y1, y2, ..., H]
        self._drag_boundary_index: Optional[int] = None  # индекс внутренней границы, которую двигаем (1..n-1)
        v = QVBoxLayout(self)

        # Верхняя панель действий
        actions = QHBoxLayout()
        self.btn_cut = QPushButton("Вырезать")
        self.btn_paste_top = QPushButton("Вставить в начало")
        self.btn_paste_bottom = QPushButton("Вставить в конец")
        self.btn_undo = QPushButton("Вернуть")
        self.btn_redo = QPushButton("Вернуть обратно")
        actions.addWidget(self.btn_cut)
        actions.addWidget(self.btn_paste_top)
        actions.addWidget(self.btn_paste_bottom)
        actions.addWidget(self.btn_undo)
        actions.addWidget(self.btn_redo)
        v.addLayout(actions)

        # Кнопки сохранения
        row_save = QHBoxLayout()
        self.btn_save = QPushButton("Сохранить")
        self.btn_save_as = QPushButton("Сохранить как…")
        row_save.addWidget(self.btn_save)
        row_save.addWidget(self.btn_save_as)
        row_save.addStretch(1)
        v.addLayout(row_save)
        v.addSpacing(4)

        help_text = (
            "Чтобы выделить область, зажмите ПКМ"
        )
        lbl = QLabel(help_text);
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size: 12px; color: #666;")
        v.addWidget(lbl)

        # Область предпросмотра
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setAlignment(Qt.AlignCenter)  # ты уже задаёшь это
        self.scroll.setViewportMargins(0, 0, 0, 0)

        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("QScrollArea{ border-left: 1px solid #d9d9d9; }")


        self.label = _PanZoomLabel(self, "Предпросмотр")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.label.setMinimumSize(QSize(200, 200))
        self.label.attach_scroll(self.scroll)
        self.scroll.setWidget(self.label)
        h = QHBoxLayout()
        h.setContentsMargins(0, 0, 0, 0)  # 10px отступ слева
        h.addWidget(self.scroll)
        v.addLayout(h)


        # Панель зума/режимов
        row = QHBoxLayout()
        self.btn_zoom_out = QPushButton("−")
        self.btn_zoom_in = QPushButton("+")
        self.btn_zoom_reset = QPushButton("По ширине")
        self.lbl_zoom = QLabel("100%")
        self.btn_fit = QPushButton("По высоте")
        self.btn_fit.setCheckable(True)
        self.btn_fit.setChecked(True)
        row.addWidget(self.btn_zoom_out)
        row.addWidget(self.btn_zoom_in)
        row.addWidget(self.btn_zoom_reset)
        row.addWidget(self.lbl_zoom)
        row.addStretch(1)
        row.addWidget(self.btn_fit)
        v.addLayout(row)


        # Инфобар размеров
        info_row = QHBoxLayout()
        self.lbl_info = QLabel("—")
        self.lbl_info.setStyleSheet("color: #666;")
        info_row.addWidget(self.lbl_info)
        info_row.addStretch(1)
        v.addLayout(info_row)


        # Соединения
        self.btn_zoom_in.clicked.connect(lambda: self._zoom_by(1.1))
        self.btn_zoom_out.clicked.connect(lambda: self._zoom_by(1/1.1))
        self.btn_zoom_reset.clicked.connect(self._zoom_reset)
        self.btn_fit.toggled.connect(self._apply_fit_mode)

        self.btn_cut.clicked.connect(self._cut_selection)
        self.btn_paste_top.clicked.connect(lambda: self._paste_fragment(at_top=True))
        self.btn_paste_bottom.clicked.connect(lambda: self._paste_fragment(at_top=False))
        self.btn_undo.clicked.connect(self._undo_last)
        self.btn_redo.clicked.connect(self._redo_last)

        # Хоткеи
        QShortcut(QKeySequence('Ctrl+X'), self, activated=self._cut_selection)
        QShortcut(QKeySequence('Ctrl+Z'), self, activated=self._undo_last)
        QShortcut(QKeySequence('Ctrl+Shift+Z'), self, activated=self._redo_last)
        QShortcut(QKeySequence('Ctrl+Y'), self, activated=self._redo_last)

        self._update_zoom_controls_enabled()
        self._update_actions_enabled()
        self._update_info_label()

    # ---------- Публичный API ----------
    def set_slice_mode(self, on: bool, count: Optional[int] = None):
        self._slice_enabled = bool(on)
        if count is not None:
            self._slice_count = max(2, int(count))
        self._rebuild_slice_bounds()
        self._update_preview_pixmap()

    def set_slice_count(self, count: int):
        self._slice_count = max(2, int(count))
        self._rebuild_slice_bounds()
        self._update_preview_pixmap()

    def save_slices(self, out_dir: str, threads: int = 4, auto_threads: bool = True) -> int:
        """Режет текущее изображение по _slice_bounds и сохраняет фрагменты параллельно.
        Возвращает число успешно сохранённых фрагментов.
        """
        if not (self._current_path and self._current_path in self._images):
            return 0
        if not self._slice_enabled or not self._slice_bounds or len(self._slice_bounds) < 2:
            return 0

        img: QImage = self._images[self._current_path]
        h, w = img.height(), img.width()
        bounds = list(self._slice_bounds)
        # подстрахуемся, что 0 и h на краях
        if bounds[0] != 0: bounds[0] = 0
        if bounds[-1] != h: bounds[-1] = h

        # авто-потоки
        if auto_threads:
            cpu = os.cpu_count() or 4
            threads = max(2, min(8, cpu))  # не перегружаем диск

        tasks = []
        def _save_one(i: int, y1: int, y2: int) -> bool:
            cut_h = max(1, y2 - y1)
            frag = img.copy(0, y1, w, cut_h)  # локальная копия для потока
            # имена вида: <basename>_s01.png
            base = os.path.splitext(os.path.basename(self._current_path))[0]
            dst = os.path.join(out_dir, f"{base}_{str(i+1).zfill(2)}.png")
            return bool(frag.save(dst))

        with ThreadPoolExecutor(max_workers=int(threads)) as ex:
            for i in range(len(bounds) - 1):
                y1, y2 = bounds[i], bounds[i + 1]
                if y2 <= y1:  # пропуск нулевой высоты
                    continue
                tasks.append(ex.submit(_save_one, i, int(y1), int(y2)))

            done_ok = 0
            for fut in as_completed(tasks):
                try:
                    if fut.result():
                        done_ok += 1
                except Exception:
                    pass

        return done_ok

    # ---------- Геометрия + перетаскивание ----------
    def _rebuild_slice_bounds(self):
        """Равномерное разбиение по высоте текущего изображения."""
        if not (self._current_path and self._current_path in self._images):
            self._slice_bounds = []
            return
        img: QImage = self._images[self._current_path]
        H = img.height()
        n = max(2, int(self._slice_count))
        step = H / n
        ys = [0]
        acc = 0.0
        for _ in range(1, n):
            acc += step
            ys.append(int(round(acc)))
        ys.append(H)
        # устраняем возможные дубликаты из-за округления
        ys2 = [ys[0]]
        for y in ys[1:]:
            if y <= ys2[-1]:
                y = ys2[-1] + 1
            ys2.append(min(y, H))
        ys2[-1] = H
        self._slice_bounds = ys2

    def _slice_bounds_on_label(self) -> List[int]:
        """Пересчёт границ из координат изображения в координаты pixmap/label."""
        pm = self.label.pixmap()
        if not pm or not (self._current_path and self._current_path in self._images):
            return []
        img = self._images[self._current_path]
        scaled_h = pm.height()
        ys = []
        for y in self._slice_bounds:
            ys.append(int(y * scaled_h / max(1, img.height())))
        # монотонность/границы
        ys2 = [max(0, min(scaled_h, ys[0]))] if ys else []
        for y in ys[1:]:
            y = max(ys2[-1], min(scaled_h, y))
            ys2.append(y)
        return ys2

    def _boundary_under_cursor(self, pos_label: QPoint, thresh: int = 6) -> Optional[int]:
        ys = self._slice_bounds_on_label()
        if not ys:
            return None
        y0 = self._v_offset_on_label()
        for i, y in enumerate(ys[1:-1], start=1):  # только внутренние границы
            if abs(pos_label.y() - (y0 + y)) <= thresh:
                return i
        return None

    def _drag_boundary_to(self, pos_label: QPoint):
        """Перетаскивание внутренней границы (индекс хранится в self._drag_boundary_index)."""
        if self._drag_boundary_index is None:
            return
        pm = self.label.pixmap()
        if not pm or not (self._current_path and self._current_path in self._images):
            return
        img = self._images[self._current_path]
        # в image-координаты
        y_img = self._label_to_image_y(pos_label.y())
        # нельзя пересекать соседей
        i = self._drag_boundary_index
        lo = self._slice_bounds[i - 1] + 1
        hi = self._slice_bounds[i + 1] - 1
        y_img = max(lo, min(hi, y_img))
        self._slice_bounds[i] = y_img
        self.label.update()
    def discard_changes(self, path: Optional[str] = None):
        """Вернуть картинку(и) к состоянию с диска без записи на диск."""
        paths = [path] if path else list(self._images.keys())
        for p in paths:
            base = self._loaded_from_disk.get(p)
            if base is not None:
                self._images[p] = base.copy()
                self._undo[p] = []
                self._redo[p] = []
                self._dirty[p] = False
        self._update_preview_pixmap()
        self._update_actions_enabled()

    def has_unsaved_changes(self) -> bool:
        return any(self._dirty.values())

    def _on_save(self):
        """Сохранить в исходный файл."""
        ok = self.save_current_overwrite()
        if ok and self._current_path:
            # обновляем базу и сбрасываем флаг грязности
            self._loaded_from_disk[self._current_path] = self._images[self._current_path].copy()
            self._dirty[self._current_path] = False

    def _on_save_as(self):
        """Сохранить как… (без добавления в галерею и без смены текущего файла)."""
        if not (self._current_path and self._current_path in self._images):
            return

        # Предложим текущее имя как базовое
        start_path = self._current_path

        # Открываем диалог ОДИН раз
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить как…",
            start_path,
            "Изображения (*.png *.jpg *.jpeg *.bmp *.webp);;Все файлы (*.*)"
        )
        if not target:
            return

        # Пишем на диск из текущего изображения
        ok = self.save_current_as(target)
        if not ok:
            # По желанию покажи ошибку
            # QMessageBox.warning(self, "Сохранение", "Не удалось сохранить файл.")
            return


    def show_path(self, path: Optional[str]):
        self._current_path = path
        self._dirty: Dict[str, bool] = {}  # путь -> есть несохранённые правки
        self._loaded_from_disk: Dict[str, QImage] = {}
        self._clear_selection()
        if not path:
            self.label.setText("Предпросмотр")
            self._update_info_label()
            return
        img = self._images.get(path)
        if img is None:
            qimg = QImage(path)
            if qimg.isNull():
                self.label.setText("Не удалось открыть изображение")
                self._update_info_label()
                return
            if qimg.format() == QImage.Format_Indexed8:
                qimg = qimg.convertToFormat(QImage.Format_RGB32)
            self._images[path] = qimg
            self._loaded_from_disk[path] = qimg.copy()  # базовый снимок (как было на диске)
            self._dirty[path] = False
        self._update_preview_pixmap()

    def save_current_overwrite(self) -> bool:
        if not self._current_path or self._current_path not in self._images:
            return False
        ok = self._images[self._current_path].save(self._current_path)
        return bool(ok)

    def save_current_as(self, target_path: str) -> bool:
        if not self._current_path or self._current_path not in self._images:
            return False
        ok = self._images[self._current_path].save(target_path)
        return bool(ok)

    # ---------- Служебные ----------
    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._current_path and self._current_path in self._images:
            self._update_preview_pixmap()

    # ---------- Зум/Fit ----------
    def _set_fit(self, fit: bool):
        self.btn_fit.setChecked(fit)
        self._apply_fit_mode(fit)

    def _apply_fit_mode(self, on: bool):
        self._fit_to_window = on
        self.scroll.setWidgetResizable(on)
        self.label.setSizePolicy(QSizePolicy.Ignored if on else QSizePolicy.Fixed,
                                 QSizePolicy.Ignored if on else QSizePolicy.Fixed)
        self.scroll.setAlignment(Qt.AlignCenter if on else Qt.AlignLeft | Qt.AlignTop)
        self._update_zoom_controls_enabled()
        self._update_preview_pixmap()

    def _update_zoom_controls_enabled(self):
        manual = not self._fit_to_window
        self.btn_zoom_in.setEnabled(manual)
        self.btn_zoom_out.setEnabled(manual)
        self.btn_zoom_reset.setEnabled(True)  # всегда доступна
        self.lbl_zoom.setEnabled(True)

    def _fit_width_zoom(self) -> float:
        if not (self._current_path and self._current_path in self._images):
            return 1.0
        img = self._images[self._current_path]
        vp = self.scroll.viewport()
        vp_w = max(1, vp.width() - 2)
        vp_h = max(1, vp.height() - 2)
        img_w = max(1, img.width())
        img_h = max(1, img.height())
        z = vp_w / img_w
        predicted_h = img_h * z
        if predicted_h > vp_h:
            sb_w = self.scroll.style().pixelMetric(QStyle.PM_ScrollBarExtent, None, self.scroll)
            vp_w -= sb_w
            z = vp_w / img_w
        return max(self._min_zoom, min(self._max_zoom, z))

    def _zoom_set(self, value: float, anchor: QPoint | None = None):
        value = max(self._min_zoom, min(self._max_zoom, float(value)))
        if abs(value - self._zoom) < 1e-6:
            return
        old_zoom = self._zoom
        self._zoom = value
        self._update_preview_pixmap(anchor=anchor, old_zoom=old_zoom)

    def _zoom_by(self, factor: float, anchor: QPoint | None = None):
        if self._fit_to_window:
            self._set_fit(False)
        self._zoom_set(self._zoom * float(factor), anchor=anchor)

    def _zoom_reset(self):
        self._set_fit(False)
        self._zoom_set(self._fit_width_zoom())

    def _update_zoom_label(self, effective_zoom=None):
        z = effective_zoom if effective_zoom is not None else self._zoom
        self.lbl_zoom.setText(f"{int(round(z * 100))}%")

    def _update_info_label(self):
        """Только исходный размер + высота выделения (без 'на экране')."""
        if not (self._current_path and self._current_path in self._images):
            self.lbl_info.setText("—")
            return
        img = self._images[self._current_path]
        ow, oh = img.width(), img.height()
        sel_txt = ""
        if self._has_selection():
            sel_px = abs(int(self._sel_y2) - int(self._sel_y1))
            sel_txt = f" • Выделение: {sel_px}px"
        self.lbl_info.setText(f"Разрешение: {ow}×{oh}px{sel_txt}")



    def _update_preview_pixmap(self, anchor: QPoint | None = None, old_zoom: float | None = None):
        if not (self._current_path and self._current_path in self._images):
            self._update_info_label()
            return
        img = self._images[self._current_path]

        if self._fit_to_window:
            avail = self.scroll.viewport().size() - QSize(2, 2)
            scaled = img.scaled(avail, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.label.setPixmap(QPixmap.fromImage(scaled))
            if img.width() and img.height():
                eff = min(scaled.width() / img.width(), scaled.height() / img.height())
                self._update_zoom_label(eff)
        else:
            target_w = max(1, int(img.width() * self._zoom))
            target_h = max(1, int(img.height() * self._zoom))
            old_pix = self.label.pixmap()
            old_w = old_pix.width() if old_pix else img.width()
            old_h = old_pix.height() if old_pix else img.height()

            scaled = img.scaled(QSize(target_w, target_h), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.label.setPixmap(QPixmap.fromImage(scaled))
            try:
                self.label.resize(scaled.size())
                self.label.adjustSize()
            except Exception:
                pass

            vp = self.scroll.viewport().size()
            align = 0
            align |= int(Qt.AlignHCenter) if scaled.width()  <= vp.width()  else int(Qt.AlignLeft)
            align |= int(Qt.AlignVCenter) if scaled.height() <= vp.height() else int(Qt.AlignTop)
            self.scroll.setAlignment(Qt.Alignment(align))

            self._update_zoom_label()

            if anchor is not None:
                try:
                    hbar = self.scroll.horizontalScrollBar()
                    vbar = self.scroll.verticalScrollBar()
                    rx = anchor.x() / max(1, old_w)
                    ry = anchor.y() / max(1, old_h)
                    new_x = int(rx * scaled.width()  - self.scroll.viewport().width()  / 2)
                    new_y = int(ry * scaled.height() - self.scroll.viewport().height() / 2)
                    hbar.setValue(max(0, min(hbar.maximum(), new_x)))
                    vbar.setValue(max(0, min(vbar.maximum(), new_y)))
                except Exception:
                    pass

        # обновим инфобар и перерисуем оверлей
        self._update_info_label()
        self.label.update()

    # ---------- Выделение ----------
    def _clear_selection(self):
        self._sel_active = False
        self._sel_y1 = None
        self._sel_y2 = None
        self._resizing_edge = None
        self.label.setCursor(Qt.ArrowCursor)
        self.label.update()
        self._update_actions_enabled()
        self._update_info_label()

    def _has_selection(self) -> bool:
        return (
            (self._current_path in self._images) if self._current_path else False
        ) and (
            self._sel_y1 is not None and self._sel_y2 is not None and abs(self._sel_y2 - self._sel_y1) > 0
        )

    def _begin_selection(self, pos_label: QPoint):
        if not (self._current_path and self._current_path in self._images):
            return
        self._sel_active = True
        y = self._label_to_image_y(pos_label.y())
        h = self._images[self._current_path].height()
        self._sel_y1 = max(0, min(h, y))
        self._sel_y2 = self._sel_y1
        self.label.update()
        self._update_actions_enabled()
        self._update_info_label()

    def _update_selection(self, pos_label: QPoint):
        if not self._sel_active or not (self._current_path and self._current_path in self._images):
            return
        y = self._label_to_image_y(pos_label.y())
        h = self._images[self._current_path].height()
        self._sel_y2 = max(1, min(h, self._label_to_image_y(pos_label.y())))
        self.label.update()
        self._update_actions_enabled()
        self._update_info_label()

    def _end_selection(self, pos_label: QPoint):
        if not self._sel_active or not (self._current_path and self._current_path in self._images):
            return
        y = self._label_to_image_y(pos_label.y())
        h = self._images[self._current_path].height()
        self._sel_y2 = max(1, min(h, self._label_to_image_y(pos_label.y())))
        self._sel_active = False
        # Нулевая высота — сброс
        if self._sel_y1 is None or self._sel_y2 is None or abs(self._sel_y2 - self._sel_y1) < 1:
            self._clear_selection()
            return
        if self._sel_y1 > self._sel_y2:
            self._sel_y1, self._sel_y2 = self._sel_y2, self._sel_y1
        h = self._images[self._current_path].height()
        y1 = int(self._sel_y1)
        y2 = int(self._sel_y2)
        self._sel_y1, self._sel_y2 = self._snap_selection_to_edges(h, y1, y2)
        self.label.update()
        self._update_actions_enabled()
        self._update_info_label()

    # --- редактирование выделения (resize) ---
    def _selection_on_label(self) -> Tuple[Optional[int], Optional[int]]:
        if not self._has_selection():
            return None, None
        img = self._images[self._current_path]
        pm = self.label.pixmap()
        scaled_h = pm.height()
        y1 = int(self._sel_y1 * scaled_h / max(1, img.height()))
        y2 = int(self._sel_y2 * scaled_h / max(1, img.height()))
        y1 = max(0, min(scaled_h, y1))
        y2 = max(0, min(scaled_h, y2))
        if y1 > y2:
            y1, y2 = y2, y1
        return y1, y2

    def _v_offset_on_label(self) -> int:
        """Вернёт вертикальный отступ (y0) pixmap внутри QLabel."""
        pm = self.label.pixmap()
        if not pm:
            return 0
        # QLabel по-прежнему с AlignCenter, поэтому центровка по вертикали работает
        return max(0, (self.label.height() - pm.height()) // 2) if (self.label.alignment() & Qt.AlignVCenter) else 0

    def _label_to_image_y(self, y_label: int) -> int:
        pm = self.label.pixmap()
        if not pm or not (self._current_path and self._current_path in self._images):
            return 0
        img = self._images[self._current_path]

        y0 = self._v_offset_on_label()
        y_rel = y_label - y0  # координата относительно ВЕРХА pixmap

        if y_rel <= 0:
            return 0
        if y_rel >= pm.height():
            return img.height()  # позволяем нижней границе быть ровно h

        # floor-мэппинг внутрь [0..h)
        return int(y_rel * img.height() / pm.height())

    def _edge_under_cursor(self, pos_label: QPoint, thresh: int = 6) -> Optional[str]:
        if not self._has_selection():
            return None
        y1, y2 = self._selection_on_label()  # координаты в системе ПИКСМАПА
        if y1 is None:
            return None
        y0 = self._v_offset_on_label()
        if abs(pos_label.y() - (y0 + y1)) <= thresh:
            return 'top'
        if abs(pos_label.y() - (y0 + y2)) <= thresh:
            return 'bottom'
        return None

    def _update_hover_cursor(self, pos_label: QPoint) -> bool:
        edge = self._edge_under_cursor(pos_label)
        if edge:
            self.label.setCursor(Qt.SizeVerCursor)
            return True
        else:
            self.label.setCursor(Qt.ArrowCursor)
            return False

    def _press_selection(self, pos_label: QPoint) -> bool:
        edge = self._edge_under_cursor(pos_label)
        if edge:
            self._resizing_edge = edge
            self.label.setCursor(Qt.SizeVerCursor)
            return True

        # клик вне области — сброс
        if self._has_selection():
            y1, y2 = self._selection_on_label()
            if y1 is not None:
                y0 = self._v_offset_on_label()
                if not (y0 + y1 <= pos_label.y() <= y0 + y2):
                    self._clear_selection()

        # начать новое выделение
        self._begin_selection(pos_label)
        return True

    def _resize_selection(self, pos_label: QPoint):
        if not self._resizing_edge or not (self._current_path and self._current_path in self._images):
            return
        y = self._label_to_image_y(pos_label.y())
        h = self._images[self._current_path].height()
        y = max(1, min(h, y))
        if self._resizing_edge == 'bottom':
            self._sel_y2 = y
        elif self._resizing_edge == 'top':
            self._sel_y1 = max(0, min(h, y))
        self.label.update()
        self._update_actions_enabled()
        self._update_info_label()

    def _end_resize(self):
        if not self._resizing_edge:
            return
        if self._sel_y1 is not None and self._sel_y2 is not None and self._sel_y1 > self._sel_y2:
            self._sel_y1, self._sel_y2 = self._sel_y2, self._sel_y1
        self._resizing_edge = None
        self.label.setCursor(Qt.ArrowCursor)
        self.label.update()
        self._update_actions_enabled()
        self._update_info_label()

    # ---------- Операции Cut / Paste / Undo / Redo ----------
    def _push_undo(self):
        if not (self._current_path and self._current_path in self._images):
            return
        st = self._undo.setdefault(self._current_path, [])
        # новая операция — чистим redo
        self._redo[self._current_path] = []
        st.append(self._images[self._current_path].copy())

    def _snap_selection_to_edges(self, h: int, y1: int, y2: int) -> tuple[int, int]:
        # clamp
        y1 = max(0, min(h, y1))
        y2 = max(0, min(h, y2))
        if y1 > y2:
            y1, y2 = y2, y1
        # snap к краям, чтобы не оставался 1px
        if y1 <= 1:
            y1 = 0
        if y2 >= h - 1:
            y2 = h
        return y1, y2

    def _cut_selection(self):
        if not self._has_selection():
            return
        img = self._images[self._current_path]
        h, w = img.height(), img.width()

        # НОРМАЛИЗУЕМ И ПРИБИВАЕМ К КРАЯМ
        y1 = int(self._sel_y1)
        y2 = int(self._sel_y2)
        y1, y2 = self._snap_selection_to_edges(h, y1, y2)
        if y2 <= y1:
            return

        cut_h = y2 - y1
        frag = img.copy(0, y1, w, cut_h)
        self._clip.append(frag)

        self._push_undo()
        new_img = QImage(w, h - cut_h, img.format() if img.format() != QImage.Format_Indexed8 else QImage.Format_RGB32)
        new_img.fill(Qt.transparent if new_img.hasAlphaChannel() else Qt.white)
        p = QPainter(new_img)
        if y1 > 0:
            p.drawImage(0, 0, img, 0, 0, w, y1)
        if y2 < h:
            p.drawImage(0, y1, img, 0, y2, w, h - y2)
        p.end()

        self._images[self._current_path] = new_img
        self._dirty[self._current_path] = True
        self._clear_selection()
        self._update_preview_pixmap()
        self._update_actions_enabled()

    def _paste_fragment(self, at_top: bool):
        if not (self._current_path and self._current_path in self._images):
            return
        if not self._clip:
            return
        base = self._images[self._current_path]
        frag = self._clip[-1]
        if frag.width() != base.width():
            frag = frag.scaled(base.width(), int(frag.height() * (base.width()/frag.width())),
                               Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

        self._push_undo()
        w = base.width()
        new_h = base.height() + frag.height()
        new_img = QImage(w, new_h, base.format() if base.format() != QImage.Format_Indexed8 else QImage.Format_RGB32)
        new_img.fill(Qt.transparent if new_img.hasAlphaChannel() else Qt.white)

        p = QPainter(new_img)
        if at_top:
            p.drawImage(0, 0, frag)
            p.drawImage(0, frag.height(), base)
        else:
            p.drawImage(0, 0, base)
            p.drawImage(0, base.height(), frag)
        p.end()

        self._images[self._current_path] = new_img
        self._dirty[self._current_path] = True
        self._update_preview_pixmap()
        self._update_actions_enabled()

    def _undo_last(self):
        if not (self._current_path and self._current_path in self._images):
            return
        st = self._undo.get(self._current_path, [])
        if not st:
            return
        cur = self._images[self._current_path].copy()
        rd = self._redo.setdefault(self._current_path, [])
        rd.append(cur)
        prev = st.pop()
        self._images[self._current_path] = prev
        self._update_preview_pixmap()
        self._update_actions_enabled()

    def _redo_last(self):
        if not (self._current_path and self._current_path in self._images):
            return
        rd = self._redo.get(self._current_path, [])
        if not rd:
            return
        st = self._undo.setdefault(self._current_path, [])
        st.append(self._images[self._current_path].copy())
        nxt = rd.pop()
        self._images[self._current_path] = nxt
        self._update_preview_pixmap()
        self._update_actions_enabled()

    
    def _update_actions_enabled(self):
        has_img = self._current_path in self._images if self._current_path else False
        self.btn_cut.setEnabled(has_img and self._has_selection())
        self.btn_paste_top.setEnabled(has_img and bool(self._clip))
        self.btn_paste_bottom.setEnabled(has_img and bool(self._clip))
        self.btn_undo.setEnabled(has_img and bool(self._undo.get(self._current_path, [])))
        self.btn_redo.setEnabled(has_img and bool(self._redo.get(self._current_path, [])))
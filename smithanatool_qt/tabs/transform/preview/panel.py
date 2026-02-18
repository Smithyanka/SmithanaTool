from __future__ import annotations
from .state_mixin import StateMixin
from .zoom_mixin import ZoomMixin
from .selection_mixin import SelectionMixin
from .undo_mixin import UndoMixin
from typing import Optional, Dict, List, Tuple
from pathlib import Path
from .slice_mode import SliceModeMixin

from PySide6.QtCore import Qt, QSize, QPoint, QPointF, QRect, Signal, QTimer, QEvent
from PySide6.QtGui import (
    QPixmap, QImage, QPainter, QColor, QPen,
    QShortcut, QKeySequence
)
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QStyle, QFrame, QFileDialog, QMessageBox, QApplication, QToolButton
)

from psd_tools import PSDImage
from PIL import Image
import numpy as np

from concurrent.futures import ThreadPoolExecutor, as_completed
import os, math

from ....theme import BG_ALT, BORDER_DIM, BG_BASE

from smithanatool_qt.settings_bind import group, get_value

from .utils import register_memory_image, unregister_memory_images, memory_image_for, clear_memory_registry, _qimage_from_pil
from .widgets import PanZoomLabel


from .state_mixin import StateMixin
from .selection_mixin import SelectionMixin
from .undo_mixin import UndoMixin
from .zoom_mixin import ZoomMixin
from .slice_mode import SliceModeMixin


# -----------------------------------------
# Основная панель предпросмотра
# -----------------------------------------
class PreviewPanel(StateMixin, SelectionMixin, UndoMixin, ZoomMixin, SliceModeMixin, QWidget):
    currentPathChanged = Signal(str)
    dirtyChanged = Signal(str, bool)
    sliceCountChanged = Signal(int)
    saveAsRequested = Signal()

    def is_dirty(self, path: Optional[str] = None) -> bool:
        """
        Возвращает флаг 'грязности' для указанного пути.
        Если path не задан, берёт текущий self._current_path.
        """
        p = path or getattr(self, "_current_path", None)
        if not p:
            return False
        return bool(self._dirty.get(p, False))


    def _set_dirty(self, path: str, value: bool):
        if not path:
            return
        old = self._dirty.get(path, False)
        self._dirty[path] = bool(value)
        if old != bool(value):
            self.dirtyChanged.emit(path, bool(value))

    def __init__(self, parent=None):
        super().__init__(parent)
        # Кэш изображений и история
        self._images: Dict[str, QImage] = {}
        self._undo: Dict[str, List[QImage]] = {}
        self._redo: Dict[str, List[QImage]] = {}
        self._clip: List[QImage] = []
        self._current_path: Optional[str] = None
        self._scroll_pos: dict[str, tuple[float, float]] = {}


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

        self._slice_by = getattr(self, "_slice_by", "count")  # "count" | "height"
        self._slice_height_px = getattr(self, "_slice_height_px", 2000)
        self._slice_state: Dict[str, dict] = {}

        # --- Превью: уровни (только для отображения, не меняет файл) ---
        self._levels_enabled = False
        self._levels_black = 0       # 0..254
        self._levels_gamma = 1.0     # 0.10..5.00
        self._levels_white = 255     # 1..255
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)

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

        row_save.addStretch(1)  # разделяет левую группу и правую подсказку

        self.lbl_hint = QLabel("Чтобы выделить область, зажмите ПКМ")
        self.lbl_hint.setWordWrap(False)  # одна строка
        self.lbl_hint.setStyleSheet("font-size: 12px; color: #454545;")
        row_save.addWidget(self.lbl_hint, 0, Qt.AlignRight | Qt.AlignVCenter)

        v.addLayout(row_save)
        v.addSpacing(0)

        # Область предпросмотра
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setAlignment(Qt.AlignCenter)
        self.scroll.setViewportMargins(0, 0, 0, 0)

        self.scroll.setFrameShape(QFrame.NoFrame)

        self.label = PanZoomLabel(self, "Нет изображения")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.label.setMinimumSize(QSize(200, 200))
        self.label.attach_scroll(self.scroll)
        self.scroll.setWidget(self.label)

        self._zoom_ui_mode = 0

        # ── Оверлейные элементы (живут на viewport ScrollArea)
        self._overlay_zoom_out = QToolButton(self.scroll.viewport())
        self._overlay_zoom_out.setText("−")
        self._overlay_zoom_out.setAutoRaise(True)
        self._overlay_zoom_out.setFixedSize(28, 28)
        self._overlay_zoom_out.setToolTip("Уменьшить масштаб")

        self._overlay_zoom_in = QToolButton(self.scroll.viewport())
        self._overlay_zoom_in.setText("+")
        self._overlay_zoom_in.setAutoRaise(True)
        self._overlay_zoom_in.setFixedSize(28, 28)
        self._overlay_zoom_in.setToolTip("Увеличить масштаб")

        for b in (self._overlay_zoom_in, self._overlay_zoom_out):
            b.setProperty("overlay", True)
            b.setFocusPolicy(Qt.NoFocus)
            b.setAttribute(Qt.WA_Hover, True)


            b.setStyleSheet(
                "QToolButton {"
                "  background-color: rgba(31,31,31,180);"  #БАЗА
            "  border: none;"
            "  padding: 2px;"
            "  min-width: 25px; min-height: 25px;"
            "  border-radius: 6px;"
            "  color: white;"
            "}"
            "QToolButton:hover {"
            "  background-color: rgba(69,69,69,150);" #при наведении
            "}"
            "QToolButton:pressed {"
            "  background-color: rgba(69,69,69,85);" #при нажатии
            "}"
            "QToolButton:!enabled {"
            "  background-color: rgba(31,31,31,100);"
            "  color: rgba(255,255,255,120);"
            "}"
            )


            self._overlay_zoom_out.hide()
        self._overlay_zoom_in.hide()
        self._overlay_zoom_out.clicked.connect(lambda: self._zoom_by(1 / 1.1))
        self._overlay_zoom_in.clicked.connect(lambda: self._zoom_by(1.1))

        self._overlay_info = QLabel(self.scroll.viewport())
        self._overlay_info.setObjectName("overlay_info")
        self._overlay_info.setStyleSheet(
            "#overlay_info {"
            " background-color: rgba(31,31,31,180); color: white;" 
            " padding: 2px 6px; border-radius: 6px; font-size: 12px;"
            "}"
        )
        self._overlay_info.hide()
        self._overlay_info.setWordWrap(False)
        self._overlay_info.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self._controls_row_widgets = []

        self.scroll.viewport().setStyleSheet(f"background: {BG_BASE.name()};")
        self.scroll.setStyleSheet(f"QScrollArea{{ border-left: 1px solid {BORDER_DIM.name()}; }}")

        # --- ТОСТ-ЛЕЙБЛ (в левом нижнем углу viewport)
        self._toast = QLabel(self.scroll.viewport())
        self._toast.setObjectName("preview_toast")
        self._toast.setStyleSheet(
            "#preview_toast {"
            " background-color: rgba(31,31,31,180); color: white;" 
            " padding: 4px 10px; border-radius: 8px;"
            " font-size: 12px;"
            "}"
        )
        self._toast.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._toast.hide)

        # чтобы позиционировать тост при ресайзе viewport
        self.scroll.viewport().installEventFilter(self)
        QTimer.singleShot(0, self._position_overlay_controls)
        QTimer.singleShot(0, self._position_toast)

        h = QHBoxLayout()
        h.setContentsMargins(0, 0, 0, 0)  # 10px отступ слева
        h.addWidget(self.scroll)
        v.addLayout(h)

        # Панель зума/режимов
        controls = QHBoxLayout()
        controls.setSpacing(6)
        controls.setContentsMargins(0, 5, 0, 0)

        # слева — "Разрешение ..."
        self.lbl_info = QLabel("—")
        self.lbl_info.setStyleSheet("color: #454545;")

        controls.addWidget(self.lbl_info)

        # разделяем левую и правую части
        controls.addStretch(1)

        # справа — все кнопки вплотную друг к другу
        self.btn_zoom_out = QToolButton();
        self.btn_zoom_out.setText("−")
        self.btn_zoom_in = QToolButton();
        self.btn_zoom_in.setText("+")
        for b in (self.btn_zoom_out, self.btn_zoom_in):
            b.setAutoRaise(True)
            b.setFixedSize(22, 22)
        self.btn_zoom_reset = QPushButton("По ширине")
        self.lbl_zoom = QLabel("100%")
        self.btn_fit = QPushButton("По высоте")

        controls.addWidget(self.lbl_zoom)
        controls.addWidget(self.btn_zoom_out)
        controls.addWidget(self.btn_zoom_in)
        controls.addWidget(self.btn_zoom_reset)
        controls.addWidget(self.btn_fit)

        self._controls_row_widgets = [
            self.lbl_info, self.lbl_zoom,
            self.btn_zoom_out, self.btn_zoom_in,
            self.btn_zoom_reset, self.btn_fit
        ]


        v.addLayout(controls)

        # Соединения
        self.btn_zoom_in.clicked.connect(lambda: self._zoom_by(1.1))
        self.btn_zoom_out.clicked.connect(lambda: self._zoom_by(1 / 1.1))
        self.btn_zoom_reset.clicked.connect(self._zoom_reset)
        self.btn_fit.clicked.connect(lambda: self._set_fit(True))

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
        QShortcut(QKeySequence('Ctrl+C'), self, activated=self._copy_selection)



        self._update_zoom_controls_enabled()
        self._update_actions_enabled()
        self._update_info_label()

        # применяем режим при старте
        self._apply_zoom_ui_mode(getattr(self, "_zoom_ui_mode", 0))
        self._position_overlay_controls()


    def _remember_scroll(self, path: str | None):
        if not path:
            return
        pm = self.label.pixmap()
        if not pm:
            return
        vp = self.scroll.viewport()
        hbar = self.scroll.horizontalScrollBar()
        vbar = self.scroll.verticalScrollBar()
        cx = hbar.value() + vp.width() / 2
        cy = vbar.value() + vp.height() / 2
        self._scroll_pos[path] = (
            cx / max(1, pm.width()),
            cy / max(1, pm.height()),
        )

    def _restore_scroll(self, path: str | None):
        if not path or path not in self._scroll_pos:
            return
        pm = self.label.pixmap()
        if not pm:
            return
        vp = self.scroll.viewport()
        hbar = self.scroll.horizontalScrollBar()
        vbar = self.scroll.verticalScrollBar()
        rx, ry = self._scroll_pos[path]
        new_x = int(rx * pm.width() - vp.width() / 2)
        new_y = int(ry * pm.height() - vp.height() / 2)
        hbar.setValue(max(0, min(hbar.maximum(), new_x)))
        vbar.setValue(max(0, min(vbar.maximum(), new_y)))

    def show_toast(self, text: str, ms: int = 3000):
        """Показать короткое сообщение поверх превью (левый нижний угол) на ms мс."""
        self._toast.setText(text)
        self._toast.adjustSize()
        self._position_toast()
        self._toast.show()
        self._toast.raise_()
        self._toast_timer.start(int(ms))

    def _position_toast(self):
        if not hasattr(self, "_toast"):
            return
        vp = self.scroll.viewport()
        if not vp:
            return
        margin = 8
        x = margin
        y = vp.height() - self._toast.height() - margin
        if y < margin:
            y = margin
        self._toast.move(x, y)

    def _pixmap_rect_on_viewport(self) -> QRect:
        """Прямоугольник pixmap в координатах viewport ScrollArea."""
        r = self.label._pixmap_rect_on_label()
        if r.isNull():
            return QRect()
        r.translate(self.label.pos())  # перенос в систему координат viewport
        return r

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._position_overlay_controls)
        QTimer.singleShot(0, self._position_toast)

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._position_overlay_controls)
        QTimer.singleShot(0, self._position_toast)

    def eventFilter(self, obj, event):
        if obj is self.scroll.viewport():
            if event.type() in (QEvent.Show, QEvent.Resize):
                try:
                    self._position_toast()
                    self._position_overlay_controls()
                except Exception:
                    pass
                return False
            if event.type() == QEvent.MouseButtonPress:
                try:
                    if (event.button() == Qt.RightButton
                            and not self._slice_enabled
                            and self._has_selection()):
                        if not self._pixmap_rect_on_viewport().contains(event.position().toPoint()):
                            self._clear_selection()
                            return True
                except Exception:
                    pass
        return super().eventFilter(obj, event)

    def _format_bytes(self, size: int) -> str:
        num = float(size)
        units = ["Б", "КБ", "МБ", "ГБ", "ТБ"]
        for u in units:
            if num < 1024 or u == units[-1]:
                return f"{int(num)} {u}" if u == "Б" else f"{num:.2f} {u}".rstrip("0").rstrip(".")
            num /= 1024

    def _is_memory_path(self, path: Optional[str]) -> bool:
        return bool(path and str(path).startswith("mem://"))

    def _is_pasted_temp_path(self, path: str | None) -> bool:
        if not path:
            return False
        try:
            p = Path(path)
            return p.parent.name.lower() == "pasted" and p.name.lower().startswith("pasted_")
        except Exception:
            return False

    # ---------- Публичный API ----------
    # ---------- Превью уровней ----------
    def set_levels_preview(self, black: int, gamma: float, white: int):
        """Включить/обновить превью уровней. Не сохраняет изменения в файл."""
        try:
            b = max(0, min(254, int(black)))
        except Exception:
            b = 0
        try:
            w = max(1, min(255, int(white)))
        except Exception:
            w = 255
        if w <= b:
            if b >= 254:
                b = 254; w = 255
            else:
                w = b + 1
        try:
            g = float(gamma)
        except Exception:
            g = 1.0
        g = max(0.10, min(5.00, g))

        changed = (b != self._levels_black) or (abs(g - self._levels_gamma) > 1e-6) or (w != self._levels_white) or (not self._levels_enabled)
        self._levels_black, self._levels_gamma, self._levels_white = b, g, w
        self._levels_enabled = not (b == 0 and abs(g - 1.0) < 1e-6 and w == 255)
        if changed:
            self._update_preview_pixmap()

    def reset_levels_preview(self):
        self._levels_enabled = False
        self._levels_black = 0
        self._levels_gamma = 1.0
        self._levels_white = 255
        self._update_preview_pixmap()

    def _is_current_psd(self) -> bool:
        ext = os.path.splitext(self._current_path or "")[1].lower()
        return ext in (".psd", ".psb")

    def _drag_boundary_to(self, pos_label: QPoint):
        """Перетаскивание внутренней границы (индекс хранится в self._drag_boundary_index)."""
        if self._drag_boundary_index is None:
            return
        pm = self.label.pixmap()
        if not pm or not (self._current_path and self._current_path in self._images):
            return

        # Координата в пикселях исходного изображения
        y_img = self._label_to_image_y(pos_label.y())

        i = self._drag_boundary_index
        prev_y = self._slice_bounds[i - 1]
        next_y = self._slice_bounds[i + 1]

        # Текущее число областей (фрагментов)
        n_frag = max(1, len(self._slice_bounds) - 1)

        # Кандидат на "схлопывание"?
        too_small = (y_img - prev_y) < 1 or (next_y - y_img) < 1

        if too_small:
            # Удалять можно ТОЛЬКО если после удаления останется >= 2 областей
            if n_frag > 2:
                try:
                    del self._slice_bounds[i]
                except Exception:
                    return

                # Сбросим состояние драга/курсора
                self._drag_boundary_index = None
                try:
                    self.label.setCursor(Qt.ArrowCursor)
                except Exception:
                    pass

                # Синхронизируем внутренний счётчик и, если есть, эмитим сигнал
                try:
                    self._slice_count = max(2, len(self._slice_bounds) - 1)
                    if hasattr(self, "sliceCountChanged"):
                        self.sliceCountChanged.emit(int(self._slice_count))
                except Exception:
                    pass

                # Сохраним пер-файловое состояние, перерисуем
                self._store_slice_state(self._current_path)
                self.label.update()
                if hasattr(self, "_update_info_label"):
                    self._update_info_label()
                return
            else:
                # Нельзя схлопнуть дальше — оставляем минимум 1 px
                y_img = max(prev_y + 1, min(next_y - 1, y_img))

        # Обычное перемещение с ограничениями, чтобы не оставить нулевую высоту
        y_img = max(prev_y + 1, min(next_y - 1, y_img))
        if y_img != self._slice_bounds[i]:
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
                self._set_dirty(p, False)
        self._update_preview_pixmap()
        self._update_actions_enabled()

    def has_unsaved_changes(self) -> bool:
        return any(getattr(self, "_dirty", {}).values())

    def _on_save(self):
        """Сохранить в исходный файл (или, если из буфера, открыть диалог сохранения)."""
        if self._is_current_psd():
            QMessageBox.information(self, "Сохранение недоступно", "Для сохранения перейдите в секцию конвертации.")
            return
        if self._is_memory_path(self._current_path) or self._is_pasted_temp_path(self._current_path):
            self.saveAsRequested.emit()
            return

        if self._is_memory_path(self._current_path) or self._is_pasted_temp_path(self._current_path):
            self._on_save_as()
            return

        ok = self.save_current_overwrite()
        if ok and self._current_path:
            self._loaded_from_disk[self._current_path] = self._images[self._current_path].copy()
            self._dirty[self._current_path] = False

    def show_path(self, path: Optional[str]):
        prev = getattr(self, "_current_path", None)
        if prev:
            self._remember_scroll(prev)

        self._store_slice_state(prev)
        self._current_path = path
        self._clear_selection()

        if not path:
            self.label.setText("Нет изображения")
            self._update_info_label()
            return

        # всегда объявляем qimg
        qimg: QImage | None = None

        # пробуем взять из кэша
        img = self._images.get(path)
        if img is not None:
            qimg = img
        else:
            mem_img = memory_image_for(path)
            if mem_img is not None:
                qimg = mem_img
            else:
                ext = os.path.splitext(path)[1].lower()
                if ext in (".psd", ".psb"):
                    try:
                        psd = PSDImage.open(path)
                        pil = psd.composite()
                        qimg = _qimage_from_pil(pil)
                    except Exception:
                        self.label.setText("Не удалось открыть PSD/PSB")
                        self._update_info_label()
                        return
                else:
                    qimg = QImage(path)
                    if qimg.isNull():
                        self.label.setText("Не удалось открыть изображение")
                        self._update_info_label()
                        return

        # нормализуем формат, если надо
        if qimg.format() == QImage.Format_Indexed8:
            qimg = qimg.convertToFormat(QImage.Format_RGB32)

        from .utils import force_dpi72
        force_dpi72(qimg)

        self._images[path] = qimg

        # обновляем кэши/флаги только для текущего пути
        self._images[path] = qimg
        if not hasattr(self, "_loaded_from_disk"):
            self._loaded_from_disk: Dict[str, QImage] = {}
        if not hasattr(self, "_dirty"):
            self._dirty: Dict[str, bool] = {}

        self._loaded_from_disk.setdefault(path, qimg.copy())
        self._dirty.setdefault(path, False)

        self._restore_slice_state(path)
        self._update_preview_pixmap()
        self._restore_scroll(path)
        self._update_actions_enabled()
        if path:
            self.currentPathChanged.emit(path)

    def save_current_overwrite(self) -> bool:
        if self._is_memory_path(self._current_path):
            return False
        if not self._current_path or self._current_path not in self._images:
            return False
        # PSD вообще нельзя сохранять
        if self._is_current_psd():
            return False
        ok = self._images[self._current_path].save(self._current_path)
        if ok:
            self._loaded_from_disk[self._current_path] = self._images[self._current_path].copy()
            self._set_dirty(self._current_path, False)
        return bool(ok)

    def save_current_as(self, target_path: str) -> bool:
        if not self._current_path or self._current_path not in self._images:
            return False
        # PSD вообще нельзя сохранять
        if self._is_current_psd():
            return False
        ok = self._images[self._current_path].save(target_path)
        if ok:
            # считаем текущее состояние сохранённым — предупреждения не будет
            self._loaded_from_disk[self._current_path] = self._images[self._current_path].copy()
            self._set_dirty(self._current_path, False)
        return bool(ok)

    # ---------- Служебные ----------
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


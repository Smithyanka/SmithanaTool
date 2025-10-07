from __future__ import annotations
from typing import Optional, Dict, List, Tuple
from pathlib import Path
from .preview.slice_mode import SliceModeMixin

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

from ...theme import BG_ALT, BORDER_DIM, BG_BASE

from smithanatool_qt.settings_bind import group, get_value


_MEM_IMAGES: Dict[str, QImage] = {}


def register_memory_image(key: str, img: QImage) -> None:
    _MEM_IMAGES[key] = img.copy()


def unregister_memory_images(paths: list[str]) -> None:
    for p in paths:
        _MEM_IMAGES.pop(p, None)


def clear_memory_registry() -> None:
    _MEM_IMAGES.clear()


app = QApplication.instance()
if app and not getattr(QApplication, "_mem_cleanup_connected", False):
    app.aboutToQuit.connect(clear_memory_registry)
    QApplication._mem_cleanup_connected = True


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
        # Пан/Зум ЛКМ/МКМ как раньше
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


def _qimage_from_pil(pil_img: Image.Image) -> QImage:
    if pil_img.mode not in ("RGBA", "RGB"):
        pil_img = pil_img.convert("RGBA")
    if pil_img.mode == "RGB":
        pil_img = pil_img.convert("RGBA")
    w, h = pil_img.size
    buf = pil_img.tobytes("raw", "RGBA")
    qimg = QImage(buf, w, h, 4 * w, QImage.Format_RGBA8888)
    return qimg.copy()


# -----------------------------------------
# Основная панель предпросмотра
# -----------------------------------------
class PreviewPanel(SliceModeMixin, QWidget):
    saveAsRequested = Signal()
    dirtyChanged = Signal(str, bool)
    currentPathChanged = Signal(str)
    sliceCountChanged = Signal(int)

    def is_dirty(self, path: str) -> bool:
        return bool(getattr(self, "_dirty", {}).get(path, False))

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

        self.label = _PanZoomLabel(self, "Нет изображения")
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
                "  background-color: rgba(31,31,31,180);" 
            "  border: none;"
            "  padding: 2px;"
            "  min-width: 25px; min-height: 25px;"
            "  border-radius: 6px;"
            "  color: white;"
            "}"
            "QToolButton:hover {"
            "  background-color: rgba(31,31,31,240);" 
            "}"
            "QToolButton:pressed {"
            "  background-color: rgba(31,31,31,85);" 
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


    def set_zoom_ui_mode(self, mode: int):
        self._apply_zoom_ui_mode(mode)

    def _apply_zoom_ui_mode(self, mode: int):
        self._zoom_ui_mode = 0 if mode not in (0, 1) else int(mode)
        is_overlay = (self._zoom_ui_mode == 1)

        for w in getattr(self, "_controls_row_widgets", []):
            w.setVisible(not is_overlay)

        if hasattr(self, "_overlay_zoom_in"):
            self._overlay_zoom_in.setVisible(is_overlay)
        if hasattr(self, "_overlay_zoom_out"):
            self._overlay_zoom_out.setVisible(is_overlay)
        if hasattr(self, "_overlay_info"):
            self._overlay_info.setVisible(is_overlay)
            if is_overlay:
                try:
                    self._overlay_info.adjustSize()
                except Exception:
                    pass

        self._position_overlay_controls()
        self._update_info_label()

    def _position_overlay_controls(self):
        vp = self.scroll.viewport()
        if not vp:
            return
        margin = 8

        if hasattr(self, "_overlay_zoom_in") and self._overlay_zoom_in.isVisible():
            h_in = self._overlay_zoom_in.height() or self._overlay_zoom_in.sizeHint().height() or 28
            h_out = self._overlay_zoom_out.height() or self._overlay_zoom_out.sizeHint().height() or 28
            total_h = h_in + 6 + h_out
            y0 = max(0, (vp.height() - total_h) // 2)
            self._overlay_zoom_in.move(margin, y0)
            self._overlay_zoom_out.move(margin, y0 + h_in + 6)

        if hasattr(self, "_overlay_info") and self._overlay_info.isVisible():
            self._overlay_info.adjustSize()
            self._overlay_info.move(margin, margin)

    def set_cut_paste_mode_enabled(self, on: bool) -> None:
        """Показ/скрытие кнопок вырезки/вставки/undo/redo/сохранения в панели превью."""
        on = bool(on)
        for w in (
                getattr(self, "btn_cut", None),
                getattr(self, "btn_paste_top", None),
                getattr(self, "btn_paste_bottom", None),
                getattr(self, "btn_undo", None),
                getattr(self, "btn_redo", None),
                getattr(self, "btn_save", None),
                getattr(self, "btn_save_as", None),
                getattr(self, "lbl_hint", None),
        ):
            if w is not None:
                w.setVisible(on)


    def _sync_slice_count_and_emit(self):
        """Синхронизирует _slice_count с текущими границами и эмитит сигнал при изменении."""
        n = max(1, len(self._slice_bounds) - 1) if self._slice_bounds else 0
        if n != getattr(self, "_slice_count", n):
            self._slice_count = n
            try:
                self.sliceCountChanged.emit(n)
            except Exception:
                pass

    def _store_slice_state(self, path: Optional[str]):
        """Снимок состояния нарезки для указанного пути (обычно текущего)."""
        if not path:
            return
        st = {
            "enabled": bool(getattr(self, "_slice_enabled", False)),
            "by": str(getattr(self, "_slice_by", "count")),
            "count": int(getattr(self, "_slice_count", 2)),
            "height_px": int(getattr(self, "_slice_height_px", 2000)),
            "bounds": list(getattr(self, "_slice_bounds", []) or []),
        }
        self._slice_state[path] = st

    def _restore_slice_state(self, path: Optional[str]):
        """Применить сохранённое состояние для пути (если есть). Безопасно к отсутствию."""
        if not path:
            return
        st = self._slice_state.get(path)
        img = self._images.get(path)
        if st is None or img is None:
            # по умолчанию — нарезка выключена
            self._slice_enabled = False
            self._slice_bounds = []
            self._sync_slice_count_and_emit()
            self._update_preview_pixmap()
            return

        # применяем режим/параметры
        self._slice_enabled = bool(st.get("enabled", False))
        self._slice_by = "height" if st.get("by") == "height" else "count"
        self._slice_count = max(2, int(st.get("count", 2)))
        self._slice_height_px = max(1, int(st.get("height_px", 2000)))

        bounds = list(st.get("bounds") or [])
        # подстраховка: корректируем под текущую высоту изображения
        H = int(img.height())
        bounds = sorted(set(max(0, min(H, int(y))) for y in bounds))
        if not bounds or bounds[0] != 0:
            bounds = [0] + bounds
        if bounds[-1] != H:
            bounds.append(H)
        # Если границы есть — используем их; иначе пересобираем по режиму
        if len(bounds) >= 3 and any(bounds[i + 1] > bounds[i] for i in range(len(bounds) - 1)):
            self._slice_bounds = bounds
            # Синхронизируем self._slice_count и, если есть, уведомим UI
            self._slice_count = max(2, len(self._slice_bounds) - 1)
            try:
                if hasattr(self, "sliceCountChanged"):
                    self.sliceCountChanged.emit(int(self._slice_count))
            except Exception:
                pass
        else:
            # как и раньше — пересобираем по активному режиму
            if self._slice_by == "height":
                try:
                    self._init_slice_bounds()
                except Exception:
                    self._slice_bounds = [0, H]
            else:
                self._rebuild_slice_bounds()

        self._update_preview_pixmap()

    def get_slice_state(self, path: Optional[str] = None) -> dict:
        """Вернуть слепок текущего состояния (для отладки/логов)."""
        p = path or self._current_path
        if not p:
            return {}
        cur = {
            "enabled": bool(getattr(self, "_slice_enabled", False)),
            "by": str(getattr(self, "_slice_by", "count")),
            "count": int(getattr(self, "_slice_count", 2)),
            "height_px": int(getattr(self, "_slice_height_px", 2000)),
            "bounds": list(getattr(self, "_slice_bounds", []) or []),
        }
        # если есть сохранённая версия — вернём её (реальное пер-файловое состояние)
        return self._slice_state.get(p, cur)

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

    def _recalc_dirty_vs_disk(self, path: str | None = None):
        p = path or self._current_path
        if not p:
            return
        base = self._loaded_from_disk.get(p)
        cur = self._images.get(p)
        if base is None or cur is None:
            return
        # QImage == сравнивает содержимое, размеры и формат
        self._set_dirty(p, not (cur == base))

    def forget_paths(self, paths: list[str]) -> None:
        """Полностью убрать пути из внутренних кэшей превью."""
        if not paths:
            return
        if getattr(self, "_current_path", None) in paths:
            self._current_path = None
            try:
                self.label.setText("Нет изображения")
            except Exception:
                pass

        # Чистим все связанные структуры
        for p in paths:
            # снять звёздочку, если была
            try:
                if getattr(self, "_dirty", {}).get(p, False):
                    self.dirtyChanged.emit(p, False)
            except Exception:
                pass
            if hasattr(self, "_images"):            self._images.pop(p, None)
            if hasattr(self, "_undo"):              self._undo.pop(p, None)
            if hasattr(self, "_redo"):              self._redo.pop(p, None)
            if hasattr(self, "_loaded_from_disk"):  self._loaded_from_disk.pop(p, None)
            if hasattr(self, "_dirty"):             self._dirty.pop(p, None)
            if hasattr(self, "_scroll_pos"):         self._scroll_pos.pop(p, None)

        # Обновить кнопки/инфо
        try:
            self._update_actions_enabled()
            self._update_info_label()
            self.label.update()
        except Exception:
            pass

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

    def eventFilter(self, obj, event):
        if obj is self.scroll.viewport():
            if event.type() == QEvent.Resize:
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
            dst = os.path.join(out_dir, f"{base}_{str(i + 1).zfill(2)}.png")
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
        self._sync_slice_count_and_emit()

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
            mem_img = _MEM_IMAGES.get(path)
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
    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._current_path and self._current_path in self._images:
            self._update_preview_pixmap()
        # поддержим корректную позицию тоста при изменении размеров панели
        try:
            self._position_toast()
        except Exception:
            pass
        try:
            self._position_overlay_controls()
        except Exception:
            pass

    # ---------- Зум/Fit ----------
    def _set_fit(self, fit: bool, *, update: bool = True):
        self.btn_fit.setChecked(fit)
        self._apply_fit_mode(fit, update=update)

    def _apply_fit_mode(self, on: bool, *, update: bool = True):
        self._fit_to_window = on
        self.scroll.setWidgetResizable(on)
        self.label.setSizePolicy(QSizePolicy.Ignored if on else QSizePolicy.Fixed,
                                 QSizePolicy.Ignored if on else QSizePolicy.Fixed)
        self.scroll.setAlignment(Qt.AlignCenter if on else Qt.AlignLeft | Qt.AlignTop)
        self._update_zoom_controls_enabled()
        if update:
            self._update_preview_pixmap()

    def _fit_window_zoom(self) -> float:
        if not (self._current_path and self._current_path in self._images):
            return 1.0
        img = self._images[self._current_path]
        vp = self.scroll.viewport()
        vp_w = max(1, vp.width() - 2)
        vp_h = max(1, vp.height() - 2)
        z = min(vp_w / max(1, img.width()), vp_h / max(1, img.height()))
        return max(self._min_zoom, min(self._max_zoom, z))

    def _update_zoom_controls_enabled(self):
        for w in (self.btn_zoom_in, self.btn_zoom_out, self.btn_zoom_reset, self.btn_fit, self.lbl_zoom):
            w.setEnabled(True)

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
            base = self._fit_window_zoom()  # фактический зум "По высоте/ширине"
            self._set_fit(False, update=False)  # тихо выходим из fit, без лишней перерисовки
            self._zoom_set(base * float(factor), anchor=anchor)
        else:
            self._zoom_set(self._zoom * float(factor), anchor=anchor)

    def _zoom_reset(self):
        if not (self._current_path and self._current_path in self._images):
            return
        self._set_fit(False)
        self._zoom_set(self._fit_width_zoom())

    def _update_zoom_label(self, effective_zoom=None):
        z = effective_zoom if effective_zoom is not None else self._zoom
        self.lbl_zoom.setText(f"{int(round(z * 100))}%")

    def _update_info_label(self):
        """Только исходный размер + высота выделения (px)."""
        if not (self._current_path and self._current_path in self._images):
            self.lbl_info.setText("—")
            if hasattr(self, "_overlay_info"):
                self._overlay_info.setText("—")
                try:
                    self._overlay_info.adjustSize()
                    self._position_overlay_controls()
                    self._overlay_info.raise_()
                except Exception:
                    pass
            return

        img = self._images[self._current_path]
        ow, oh = img.width(), img.height()
        sel_txt = ""
        if self._has_selection():
            sel_px = max(0, int(math.ceil(self._sel_y2) - math.floor(self._sel_y1)))
            sel_txt = f" • Выделение: {sel_px}px"

        size_head = ""
        try:
            if self._current_path and not self._is_memory_path(self._current_path):
                from pathlib import Path
                b = Path(self._current_path).stat().st_size
                size_head = f"{self._format_bytes(b)} • "
        except Exception:
            pass

        text = f"{size_head}{ow}×{oh}px{sel_txt}"
        self.lbl_info.setText(text)
        if getattr(self, "_zoom_ui_mode", 0) == 1 and hasattr(self, "_overlay_info"):
            self._overlay_info.setText(text)
            try:
                self._overlay_info.adjustSize()
                self._position_overlay_controls()
                self._overlay_info.raise_()
            except Exception:
                pass

    def _apply_levels_to_qimage(self, qimg: QImage) -> QImage:
        """Возвращает новую QImage с применёнными уровнями (к RGB-каналам).
        Реализация совместима с PySide6: QImage.bits() -> memoryview (без setsize).
        """
        if not self._levels_enabled:
            return qimg

        b = int(self._levels_black)
        w = int(self._levels_white)
        g = float(self._levels_gamma)
        if w <= b:
            return qimg

        img = qimg if qimg.format() == QImage.Format_RGBA8888 else qimg.convertToFormat(QImage.Format_RGBA8888)

        w_img = img.width()
        h_img = img.height()
        bpl = img.bytesPerLine()

        # PySide6: bits() возвращает memoryview, уже с нужным размером
        ptr = img.bits()
        buf = np.frombuffer(ptr, dtype=np.uint8)

        # приводим к (h, bytesPerLine), режем до видимой ширины и представляем как RGBA
        buf = buf[:h_img * bpl].reshape(h_img, bpl)
        arr = buf[:, : w_img * 4].reshape(h_img, w_img, 4)

        # LUT: y = 255 * ((x-b)/(w-b)) ** gamma
        rng = max(1, w - b)
        x = np.arange(256, dtype=np.float32)
        u = (x - b) / float(rng)
        u = np.clip(u, 0.0, 1.0)
        y = np.power(u, g) * 255.0
        lut = np.clip(y + 0.5, 0, 255).astype(np.uint8)

        # применяем к RGB (альфу не трогаем)
        arr[..., :3] = lut[arr[..., :3]]

        # возвращаем копию безопасным stride (w*4)
        out = QImage(arr.tobytes(), w_img, h_img, w_img * 4, QImage.Format_RGBA8888)
        return out.copy()
    def _update_preview_pixmap(self, anchor: QPoint | None = None, old_zoom: float | None = None):
        if not (self._current_path and self._current_path in self._images):
            self._update_info_label()
            return
        img = self._images[self._current_path]

        if self._fit_to_window:
            avail = self.scroll.viewport().size() - QSize(2, 2)
            scaled = img.scaled(avail, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            scaled = self._apply_levels_to_qimage(scaled)
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
            scaled = self._apply_levels_to_qimage(scaled)
            self.label.setPixmap(QPixmap.fromImage(scaled))
            try:
                self.label.resize(scaled.size())
                self.label.adjustSize()
            except Exception:
                pass

            vp = self.scroll.viewport().size()
            align = 0
            align |= int(Qt.AlignHCenter) if scaled.width() <= vp.width() else int(Qt.AlignLeft)
            align |= int(Qt.AlignVCenter) if scaled.height() <= vp.height() else int(Qt.AlignTop)
            self.scroll.setAlignment(Qt.Alignment(align))

            self._update_zoom_label()

            if anchor is not None:
                try:
                    hbar = self.scroll.horizontalScrollBar()
                    vbar = self.scroll.verticalScrollBar()
                    rx = anchor.x() / max(1, old_w)
                    ry = anchor.y() / max(1, old_h)
                    new_x = int(rx * scaled.width() - self.scroll.viewport().width() / 2)
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

    def _label_to_image_y_edge(self, y_label: int, *, as_top: bool) -> int:
        pm = self.label.pixmap()
        if not pm or not (self._current_path and self._current_path in self._images):
            return 0
        img = self._images[self._current_path]
        y0 = self._v_offset_on_label()
        y_rel = y_label - y0
        if y_rel <= 0:
            return 0
        if y_rel >= pm.height():
            return img.height()
        ratio = img.height() / pm.height()
        if as_top:
            return int(y_rel * ratio)  # floor
        else:
            return min(img.height(), int(math.ceil(y_rel * ratio)))  # ceil
    def _begin_selection(self, pos_label: QPoint):
        if not (self._current_path and self._current_path in self._images):
            return
        self._sel_active = True
        y_top = self._label_to_image_y_edge(pos_label.y(), as_top=True)
        h = self._images[self._current_path].height()
        self._sel_y1 = max(0, min(h, y_top))
        self._sel_y2 = self._sel_y1
        self.label.update()
        self._update_actions_enabled()
        self._update_info_label()

    def _update_selection(self, pos_label: QPoint):
        if not self._sel_active or not (self._current_path and self._current_path in self._images):
            return
        y = self._label_to_image_y(pos_label.y())
        h = self._images[self._current_path].height()
        self._sel_y2 = max(1, min(h, self._label_to_image_y_edge(pos_label.y(), as_top=False)))
        self.label.update()
        self._update_actions_enabled()
        self._update_info_label()

    def _end_selection(self, pos_label: QPoint):
        if not self._sel_active or not (self._current_path and self._current_path in self._images):
            return
        y = self._label_to_image_y(pos_label.y())
        h = self._images[self._current_path].height()
        self._sel_y2 = max(1, min(h, self._label_to_image_y_edge(pos_label.y(), as_top=False)))
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
        y2 = int(math.ceil(self._sel_y2 * scaled_h / max(1, img.height())))
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
            self._sel_y2 = max(1, min(h, self._label_to_image_y_edge(pos_label.y(), as_top=False)))
        elif self._resizing_edge == 'top':
            self._sel_y1 = max(0, min(h, self._label_to_image_y_edge(pos_label.y(), as_top=True)))
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

    def _copy_selection(self):
        # есть ли изображение и выделение
        if not (self._current_path and self._current_path in self._images and self._has_selection()):
            return

        img: QImage = self._images[self._current_path]
        h, w = img.height(), img.width()

        # нормализуем и «прибиваем» к краям, как в cut
        y1 = int(self._sel_y1)
        y2 = int(self._sel_y2)
        y1, y2 = self._snap_selection_to_edges(h, y1, y2)
        if y2 <= y1:
            return

        cut_h = y2 - y1
        frag = img.copy(0, y1, w, cut_h)

        # во внутренний буфер приложения (для "Вставить в начало/конец")
        self._clip.append(frag)

        # в системный буфер обмена — как изображение (для вставки в другие программы)
        try:
            QApplication.clipboard().setImage(frag)
        except Exception:
            pass

        # UI-обратная связь + обновление доступности вставки
        self.show_toast(f"Скопировано: {w}×{cut_h}px", 1500)
        self._update_actions_enabled()

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
        self._recalc_dirty_vs_disk()
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
            frag = frag.scaled(base.width(), int(frag.height() * (base.width() / frag.width())),
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
        self._set_dirty(self._current_path, True)
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
        self._recalc_dirty_vs_disk()
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
        self._recalc_dirty_vs_disk()
        self._update_preview_pixmap()
        self._update_actions_enabled()

    def _update_actions_enabled(self):
        has_img = self._current_path in self._images if self._current_path else False
        is_psd = self._is_current_psd()
        self.btn_cut.setEnabled(has_img and self._has_selection())
        self.btn_paste_top.setEnabled(has_img and bool(self._clip))
        self.btn_paste_bottom.setEnabled(has_img and bool(self._clip))
        self.btn_undo.setEnabled(has_img and bool(self._undo.get(self._current_path, [])))
        self.btn_redo.setEnabled(has_img and bool(self._redo.get(self._current_path, [])))
        # Сохранение недоступно для PSD
        save_ok = has_img and not is_psd
        self.btn_save.setEnabled(save_ok)
        self.btn_save_as.setEnabled(save_ok)
from __future__ import annotations

import os
import math
from pathlib import Path
from typing import Optional, Dict, List

from PySide6.QtCore import Qt, QSize, QPoint, QRect, Signal, QTimer, QEvent, QRectF
from PySide6.QtGui import QImage, QPainterPath, QRegion
from PySide6.QtWidgets import QWidget, QSizePolicy, QMessageBox, QApplication, QLineEdit, QTextEdit, QPlainTextEdit

from .ui import setup_preview_ui
from .io import load_qimage, is_psd_path
from .utils import memory_image_for

from .state import StateMixin
from .behaviors.selection import SelectionMixin
from .behaviors.zoom_undo import UndoMixin, ZoomMixin
from .behaviors.slice import SliceMixin
from .behaviors.frame import FrameMixin

from PySide6.QtGui import QShortcut, QKeySequence

from .utils import memory_image_for, unregister_memory_images

class PreviewPanel(StateMixin, SelectionMixin, UndoMixin, ZoomMixin, SliceMixin, FrameMixin, QWidget):
    currentPathChanged = Signal(str)
    dirtyChanged = Signal(str, bool)
    sliceCountChanged = Signal(int)

    ocrSortRectsRequested = Signal()
    ocrDeleteRectsRequested = Signal()
    ocrUndoRequested = Signal()
    ocrRedoRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._pan_passthrough_widget = None

        # Кэш изображений и история
        self._images: Dict[str, QImage] = {}
        self._loaded_from_disk: Dict[str, QImage] = {}
        self._dirty: Dict[str, bool] = {}

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

        self._selection_enabled: bool = True
        self._actions_ui_enabled: bool = True
        self._actions_pinned_saved: Optional[bool] = None
        self._actions_profile: str = "transform"
        self._ocr_delete_available: bool = False
        self._ocr_undo_available: bool = False
        self._ocr_redo_available: bool = False
        self._ocr_sort_tooltip: str = "Сменить порядок рамок"

        # Нарезка
        self._slice_enabled: bool = False
        self._slice_count: int = 2
        self._slice_bounds: List[int] = []
        self._drag_boundary_index: Optional[int] = None

        self._slice_by: str = getattr(self, "_slice_by", "count")  # "count" | "height"
        self._slice_height_px: int = getattr(self, "_slice_height_px", 2000)
        self._slice_state: Dict[str, dict] = {}

        # Рамка (кадрирование)
        self._frame_enabled: bool = False
        self._frame_rect_img: Optional[QRect] = None  # image coords
        self._frame_drag = None
        self._frame_sel_prev: Optional[bool] = None
        self._frame_min_w = 8
        self._frame_min_h = 8
        self._frame_handle_size = 6

        # --- Превью уровней (только отображение) ---
        self._levels_enabled = False
        self._levels_black = 0
        self._levels_gamma = 1.0
        self._levels_white = 255

        # UI
        setup_preview_ui(self)
        QApplication.instance().installEventFilter(self)

        # Соединения
        self.btn_zoom_in.clicked.connect(lambda: self._zoom_by(1.1))
        self.btn_zoom_out.clicked.connect(lambda: self._zoom_by(1 / 1.1))
        self.btn_zoom_reset.clicked.connect(self._zoom_reset)
        self.btn_fit.clicked.connect(lambda: self._set_fit(True))

        self.action_btn_cut.clicked.connect(self._cut_selection)

        # "Рамка" (кадрирование)
        if hasattr(self, "action_btn_frame"):
            try:
                self.action_btn_frame.setCheckable(True)
                self.action_btn_frame.toggled.connect(self.set_frame_enabled)
                self.action_btn_frame.setChecked(False)
            except Exception:
                # fallback
                self.action_btn_frame.clicked.connect(lambda: self.set_frame_enabled(not self._frame_enabled))
        self.action_btn_paste_top.clicked.connect(lambda: self._paste_fragment(at_top=True))
        self.action_btn_paste_bottom.clicked.connect(lambda: self._paste_fragment(at_top=False))
        self.action_btn_undo.clicked.connect(self._undo_last)
        self.action_btn_redo.clicked.connect(self._redo_last)

        if hasattr(self, "action_btn_ocr_sort"):
            self.action_btn_ocr_sort.clicked.connect(self.ocrSortRectsRequested.emit)
        if hasattr(self, "action_btn_ocr_delete"):
            self.action_btn_ocr_delete.clicked.connect(self.ocrDeleteRectsRequested.emit)
        if hasattr(self, "action_btn_ocr_undo"):
            self.action_btn_ocr_undo.clicked.connect(self.ocrUndoRequested.emit)
        elif hasattr(self, "action_btn_ocr_restore"):
            self.action_btn_ocr_restore.clicked.connect(self.ocrUndoRequested.emit)
        if hasattr(self, "action_btn_ocr_redo"):
            self.action_btn_ocr_redo.clicked.connect(self.ocrRedoRequested.emit)

        # Хоткеи

        QShortcut(QKeySequence("Ctrl+X"), self, activated=self._cut_selection)
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self._dispatch_undo_action)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, activated=self._dispatch_redo_action)
        QShortcut(QKeySequence("Ctrl+Y"), self, activated=self._dispatch_redo_action)
        QShortcut(QKeySequence("Ctrl+C"), self, activated=self._copy_selection)

        self.sc_paste_top = QShortcut(QKeySequence("Ctrl+D"), self)
        self.sc_paste_top.setContext(Qt.WindowShortcut)
        self.sc_paste_top.setAutoRepeat(False)
        self.sc_paste_top.activated.connect(lambda: self._paste_fragment(at_top=True))

        self.sc_paste_bottom = QShortcut(QKeySequence("Ctrl+Shift+D"), self)
        self.sc_paste_bottom.setContext(Qt.WindowShortcut)
        self.sc_paste_bottom.setAutoRepeat(False)
        self.sc_paste_bottom.activated.connect(lambda: self._paste_fragment(at_top=False))

        # Рамка: C — включить/выключить, Enter — применить, Esc — отмена/выйти
        self.sc_frame_toggle = QShortcut(QKeySequence("C"), self)
        self.sc_frame_toggle.setContext(Qt.WindowShortcut)
        self.sc_frame_toggle.setAutoRepeat(False)
        self.sc_frame_toggle.activated.connect(lambda: self.set_frame_enabled(not self._frame_enabled))

        for key in ("Return", "Enter"):
            sc = QShortcut(QKeySequence(key), self)
            sc.setContext(Qt.WindowShortcut)
            sc.setAutoRepeat(False)
            sc.activated.connect(self._frame_apply_from_shortcut)

        self.sc_frame_esc = QShortcut(QKeySequence("Esc"), self)
        self.sc_frame_esc.setContext(Qt.WindowShortcut)
        self.sc_frame_esc.setAutoRepeat(False)
        self.sc_frame_esc.activated.connect(self._frame_esc_from_shortcut)


        self._update_zoom_controls_enabled()
        self._update_actions_enabled()
        self._update_info_label()

        # применяем режим при старте
        self._apply_zoom_ui_mode(getattr(self, "_zoom_ui_mode", 0))
        self._position_overlay_controls()



    def _dispatch_undo_action(self) -> None:
        if getattr(self, "_actions_profile", "transform") == "ocr":
            try:
                self.ocrUndoRequested.emit()
                return
            except Exception:
                pass
        self._undo_last()

    def _dispatch_redo_action(self) -> None:
        if getattr(self, "_actions_profile", "transform") == "ocr":
            try:
                self.ocrRedoRequested.emit()
                return
            except Exception:
                pass
        self._redo_last()

    def set_pan_passthrough_widget(self, w):
        self._pan_passthrough_widget = w

    def set_selection_enabled(self, enabled: bool) -> None:
        self._selection_enabled = bool(enabled)
        if not self._selection_enabled:
            try:
                self._clear_selection()
            except Exception:
                pass
        try:
            self.label.update()
        except Exception:
            pass

    def set_actions_profile(self, profile: str) -> None:
        profile = "ocr" if str(profile).strip().lower() == "ocr" else "transform"
        self._actions_profile = profile

        for w in getattr(self, "_transform_action_widgets", []):
            try:
                w.setVisible(profile == "transform")
            except Exception:
                pass

        for w in getattr(self, "_ocr_action_widgets", []):
            try:
                w.setVisible(profile == "ocr")
            except Exception:
                pass

        try:
            self._update_actions_enabled()
        except Exception:
            pass
        try:
            QTimer.singleShot(0, self._position_overlay_controls)
        except Exception:
            pass

    def set_ocr_menu_state(
        self,
        *,
        delete_enabled: Optional[bool] = None,
        undo_enabled: Optional[bool] = None,
        redo_enabled: Optional[bool] = None,
        restore_enabled: Optional[bool] = None,
        sort_tooltip: Optional[str] = None,
    ) -> None:
        if delete_enabled is not None:
            self._ocr_delete_available = bool(delete_enabled)
        if undo_enabled is None and restore_enabled is not None:
            undo_enabled = restore_enabled
        if undo_enabled is not None:
            self._ocr_undo_available = bool(undo_enabled)
        if redo_enabled is not None:
            self._ocr_redo_available = bool(redo_enabled)
        if sort_tooltip is not None:
            self._ocr_sort_tooltip = str(sort_tooltip)
            try:
                self.action_btn_ocr_sort.setToolTip(self._ocr_sort_tooltip)
            except Exception:
                pass

        try:
            self._update_actions_enabled()
        except Exception:
            pass

    # ---------- UI helpers ----------
    def show_toast(self, text: str, ms: int = 3000) -> None:
        """Показать короткое сообщение поверх превью (левый нижний угол) на ms мс."""
        self._toast.setText(text)
        self._toast.adjustSize()
        self._position_toast()
        self._toast.show()
        self._toast.raise_()
        self._toast_timer.start(int(ms))

    def _position_toast(self) -> None:
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
        r.translate(self.label.pos())
        return r

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._position_overlay_controls)
        QTimer.singleShot(0, self._position_toast)

    def eventFilter(self, obj, event):
        # Space down/up — только если мышь над превью
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Space and not event.isAutoRepeat():
            if self.scroll.viewport().underMouse() or self.label.underMouse():
                fw = QApplication.focusWidget()
                # не ломаем ввод пробела в текстовые поля (если появятся)
                if isinstance(fw, (QLineEdit, QTextEdit, QPlainTextEdit)):
                    return False
                self.label._set_space_down(True)
                w = getattr(self, "_pan_passthrough_widget", None)
                if w is not None:
                    w.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                return True

        if event.type() == QEvent.KeyRelease and event.key() == Qt.Key_Space and not event.isAutoRepeat():
            if getattr(self.label, "_space_down", False):
                self.label._set_space_down(False)
                w = getattr(self, "_pan_passthrough_widget", None)
                if w is not None:
                    w.setAttribute(Qt.WA_TransparentForMouseEvents, False)
                return True

        # дальше оставь твою текущую логику viewport...
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
                    self.scroll.viewport().setFocus(Qt.MouseFocusReason)
                    self.setFocus(Qt.MouseFocusReason)
                except Exception:
                    pass


                try:
                    if (
                            event.button() == Qt.LeftButton
                            and not getattr(self.label, "_space_down", False)
                            and not self._slice_enabled
                            and self._has_selection()
                    ):
                        if not self._pixmap_rect_on_viewport().contains(event.position().toPoint()):
                            self._clear_selection()
                            return True
                except Exception:
                    pass

        return super().eventFilter(obj, event)

    # ---------- misc helpers used by mixins ----------
    def _format_bytes(self, size: int) -> str:
        num = float(size)
        units = ["Б", "КБ", "МБ", "ГБ", "ТБ"]
        for u in units:
            if num < 1024 or u == units[-1]:
                return f"{int(num)} {u}" if u == "Б" else f"{num:.2f} {u}".rstrip("0").rstrip(".")
            num /= 1024
        return f"{int(size)} Б"

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

    # ---------- Public API: Levels preview ----------
    def set_levels_preview(self, black: int, gamma: float, white: int) -> None:
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
                b = 254
                w = 255
            else:
                w = b + 1
        try:
            g = float(gamma)
        except Exception:
            g = 1.0
        g = max(0.10, min(5.00, g))

        changed = (
            b != self._levels_black
            or abs(g - self._levels_gamma) > 1e-6
            or w != self._levels_white
            or (not self._levels_enabled)
        )
        self._levels_black, self._levels_gamma, self._levels_white = b, g, w
        self._levels_enabled = not (b == 0 and abs(g - 1.0) < 1e-6 and w == 255)
        if changed:
            self._update_preview_pixmap()

    def reset_levels_preview(self) -> None:
        self._levels_enabled = False
        self._levels_black = 0
        self._levels_gamma = 1.0
        self._levels_white = 255
        self._update_preview_pixmap()

    def _is_current_psd(self) -> bool:
        return is_psd_path(self._current_path)

    # ---------- Slice dragging (advanced behavior kept in panel) ----------
    def _drag_boundary_to(self, pos_label: QPoint) -> None:
        """Перетаскивание внутренней границы (индекс хранится в self._drag_boundary_index)."""
        if self._drag_boundary_index is None:
            return
        if not (self._current_path and self._current_path in self._images):
            return

        y_img = self._label_to_image_y(pos_label.y())

        i = self._drag_boundary_index
        prev_y = self._slice_bounds[i - 1]
        next_y = self._slice_bounds[i + 1]

        n_frag = max(1, len(self._slice_bounds) - 1)

        too_small = (y_img - prev_y) < 1 or (next_y - y_img) < 1

        if too_small:
            if n_frag > 2:
                try:
                    del self._slice_bounds[i]
                except Exception:
                    return

                self._drag_boundary_index = None
                try:
                    self.label.setCursor(Qt.ArrowCursor)
                except Exception:
                    pass

                try:
                    self._slice_count = max(2, len(self._slice_bounds) - 1)
                    self.sliceCountChanged.emit(int(self._slice_count))
                except Exception:
                    pass

                self._store_slice_state(self._current_path)
                self.label.update()
                if hasattr(self, "_update_info_label"):
                    self._update_info_label()
                return

            y_img = max(prev_y + 1, min(next_y - 1, y_img))

        y_img = max(prev_y + 1, min(next_y - 1, y_img))
        if y_img != self._slice_bounds[i]:
            self._slice_bounds[i] = y_img
            self.label.update()

    # ---------- Save ----------
    def _on_save(self) -> None:
        """Сохранить в исходный файл (или, если из буфера, запросить Save As)."""
        if self._is_current_psd():
            QMessageBox.information(self, "Сохранение недоступно", "Для сохранения перейдите в секцию конвертации.")
            return


        ok = self.save_current_overwrite()
        if ok and self._current_path:
            self._loaded_from_disk[self._current_path] = self._images[self._current_path].copy()
            self._dirty[self._current_path] = False

    # ---------- Reset empty ----------
    def _reset_empty_preview(self, text: str = "Нет изображения") -> None:
        """Полный сброс превью в состояние 'пусто'."""
        # Clear virtual rendering state (otherwise the canvas may still paint the previous image).
        try:
            self._view_img = None
            self._view_img_key = None
            self._view_pm = None
            self._display_size = QSize(0, 0)
        except Exception:
            pass
        try:
            self._clear_selection()
        except Exception:
            pass

        # Сбрасываем/выключаем рамку, если была включена
        try:
            if getattr(self, "_frame_enabled", False):
                self.set_frame_enabled(False)
            else:
                self._frame_rect_img = None
                self._frame_drag = None
        except Exception:
            self._frame_enabled = False
            self._frame_rect_img = None
            self._frame_drag = None

        try:
            self._fit_to_window = True
            self._zoom = 1.0
            if hasattr(self, "_set_fit"):
                self._set_fit(True, update=False)
            else:
                self.scroll.setWidgetResizable(True)
                self.label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
                self.scroll.setAlignment(Qt.AlignCenter)
        except Exception:
            pass

        try:
            self.label.clear()
        except Exception:
            pass
        self.label.setText(text)
        self.label.setAlignment(Qt.AlignCenter)

        try:
            self.scroll.horizontalScrollBar().setValue(0)
            self.scroll.verticalScrollBar().setValue(0)
        except Exception:
            pass

        try:
            vp = self.scroll.viewport().size()
            if vp.isValid():
                self.label.resize(vp)
                self.label.updateGeometry()
        except Exception:
            pass

        try:
            self._update_info_label()
        except Exception:
            pass
        try:
            self._update_actions_enabled()
        except Exception:
            pass
        try:
            self._position_overlay_controls()
        except Exception:
            pass
        try:
            self._position_toast()
        except Exception:
            pass

    # ---------- Public API: show image ----------
    def show_path(self, path: Optional[str]) -> None:
        prev = getattr(self, "_current_path", None)
        if prev:
            self._remember_scroll(prev)

        self._store_slice_state(prev)
        self._current_path = path
        self._clear_selection()
        # Frame rect doesn't survive file switching
        try:
            self._frame_clear_rect()
        except Exception:
            self._frame_rect_img = None

        if not path:
            self._reset_empty_preview("Нет изображения")
            return

        qimg: QImage | None = None

        img = self._images.get(path)
        if img is not None:
            qimg = img
        else:
            mem_img = memory_image_for(path)
            if mem_img is not None:
                qimg = mem_img
            else:
                qimg = load_qimage(path)
                if qimg is None or qimg.isNull():
                    self._reset_empty_preview("Не удалось открыть изображение")
                    self._update_info_label()
                    return

        self._images[path] = qimg

        self._loaded_from_disk.setdefault(path, qimg.copy())
        self._dirty.setdefault(path, False)

        self._restore_slice_state(path)
        # Если активна "Рамка" — не даём восстановленному slice-mode включиться.
        if getattr(self, "_frame_enabled", False):
            try:
                if hasattr(self, "set_slice_mode"):
                    self.set_slice_mode(False)
                else:
                    self._slice_enabled = False
                    self._slice_bounds = []
            except Exception:
                self._slice_enabled = False
                self._slice_bounds = []
        self._update_preview_pixmap()
        self._restore_scroll(path)
        self._update_actions_enabled()
        self._update_zoom_controls_enabled()
        try:
            self._position_overlay_controls()
        except Exception:
            pass

        self.currentPathChanged.emit(path)

    def save_current_overwrite(self) -> bool:
        if self._is_memory_path(self._current_path):
            return False
        if not self._current_path or self._current_path not in self._images:
            return False
        if self._is_current_psd():
            return False

        ok = self._images[self._current_path].save(self._current_path)
        if ok:
            self._loaded_from_disk[self._current_path] = self._images[self._current_path].copy()
            self._set_dirty(self._current_path, False)
        return bool(ok)

    def relink_current_to(self, new_path: str) -> bool:
        """После Save As: сделать текущий документ 'файловым' вместо mem://... (с сохранением undo/redo и т.п.)."""
        old = getattr(self, "_current_path", None)
        if not old or not new_path or old == new_path:
            return False
        if old not in self._images:
            return False

        # Если вдруг new_path уже был открыт/в кэше — уберём, чтобы не смешать состояния
        self._images.pop(new_path, None)
        self._loaded_from_disk.pop(new_path, None)
        self._dirty.pop(new_path, None)
        self._undo.pop(new_path, None)
        self._redo.pop(new_path, None)
        if hasattr(self, "_scroll_pos"):
            self._scroll_pos.pop(new_path, None)
        if hasattr(self, "_slice_state"):
            self._slice_state.pop(new_path, None)

        # Переносим всё состояние со старого ключа на новый
        self._images[new_path] = self._images.pop(old)

        self._undo[new_path] = self._undo.pop(old, [])
        self._redo[new_path] = self._redo.pop(old, [])

        if hasattr(self, "_scroll_pos") and old in self._scroll_pos:
            self._scroll_pos[new_path] = self._scroll_pos.pop(old)

        if hasattr(self, "_slice_state") and old in self._slice_state:
            self._slice_state[new_path] = self._slice_state.pop(old)

        # После успешного сохранения считаем, что это “состояние на диске”
        self._loaded_from_disk.pop(old, None)
        self._loaded_from_disk[new_path] = self._images[new_path].copy()

        # dirty: старый ключ удаляем, новый = False
        was_dirty = self._dirty.pop(old, False)
        self._dirty.setdefault(new_path, False)
        self._set_dirty(new_path, False)

        # Если это был mem:// — вычистим registry, чтобы не держать лишнюю копию
        try:
            if self._is_memory_path(old):
                unregister_memory_images([old])
        except Exception:
            pass

        # Переключаем текущий путь БЕЗ show_path (чтобы не сбрасывать выделение)
        self._current_path = new_path

        try:
            self._update_preview_pixmap()
            self._update_actions_enabled()
            self._update_zoom_controls_enabled()
            self._update_info_label()
        except Exception:
            pass

        try:
            self.currentPathChanged.emit(new_path)
        except Exception:
            pass

        return True
    def save_current_as(self, target_path: str) -> bool:
        if not self._current_path or self._current_path not in self._images:
            return False
        if self._is_current_psd():
            return False

        ok = self._images[self._current_path].save(target_path)
        if ok:
            self._loaded_from_disk[self._current_path] = self._images[self._current_path].copy()
            self._set_dirty(self._current_path, False)
        return bool(ok)

    # ---------- Selection service ----------
    def _end_resize(self) -> None:
        if not self._resizing_edge:
            return
        if self._sel_y1 is not None and self._sel_y2 is not None and self._sel_y1 > self._sel_y2:
            self._sel_y1, self._sel_y2 = self._sel_y2, self._sel_y1
        self._resizing_edge = None
        self.label.setCursor(Qt.ArrowCursor)
        self.label.update()
        self._update_actions_enabled()
        self._update_info_label()

    def set_actions_ui_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        self._actions_ui_enabled = enabled

        handle = getattr(self, "btn_actions_handle", None)
        panel = getattr(self, "actions_panel", None)

        if not enabled:
            if getattr(self, "_actions_pinned_saved", None) is None:
                self._actions_pinned_saved = bool(getattr(self, "_actions_pinned", False))

            self._actions_pinned = False

            if handle is not None:
                handle.setChecked(False)
                handle.hide()
            if panel is not None:
                panel.hide()
        else:
            if handle is not None:
                handle.show()

            saved = getattr(self, "_actions_pinned_saved", None)
            if saved is not None:
                self._actions_pinned = bool(saved)
                self._actions_pinned_saved = None

            if panel is not None:
                panel.setVisible(bool(getattr(self, "_actions_pinned", False)))
            if handle is not None:
                handle.setChecked(bool(getattr(self, "_actions_pinned", False)))

        try:
            self._update_actions_enabled()
        except Exception:
            pass
        try:
            QTimer.singleShot(0, self._position_overlay_controls)
        except Exception:
            pass
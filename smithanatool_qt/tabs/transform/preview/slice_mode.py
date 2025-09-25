
from __future__ import annotations
from typing import Optional, List, Tuple
from pathlib import Path
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QPainter, QColor, QPen, QFontMetrics

class SliceModeMixin:
    # Public API
    def set_slice_mode(self, enabled: bool, count: Optional[int] = None):
        if enabled == getattr(self, "_slice_enabled", False) and (count is None or count == getattr(self, "_slice_count", 2)):
            return
        self._slice_enabled = bool(enabled)
        if count is not None and count >= 2:
            self._slice_count = int(count)
        if self._slice_enabled:
            self._sel_active = False
            self._resizing_edge = None
            self._init_slice_bounds()
        else:
            self._drag_boundary_index = None
        # UI updates provided by PreviewPanel
        try:
            self.label.update()
        except Exception:
            pass
        if hasattr(self, "_update_actions_enabled"):
            self._update_actions_enabled()
        if hasattr(self, "_update_info_label"):
            self._update_info_label()

    def set_slice_count(self, n: int):
        n = max(2, int(n))
        self._slice_count = n
        if getattr(self, "_slice_enabled", False):
            self._init_slice_bounds()
            try:
                self.label.update()
            except Exception:
                pass
            if hasattr(self, "_update_info_label"):
                self._update_info_label()
    def set_slice_by(self, by: str):
        by = str(by).lower()
        self._slice_by = "height" if ("height" in by or "высот" in by) else "count"
        if getattr(self, "_slice_enabled", False):
            self._init_slice_bounds()
            try:
                self.label.update()
            except Exception:
                pass
            if hasattr(self, "_update_info_label"):
                self._update_info_label()

    def set_slice_height(self, px: int):
        self._slice_height_px = max(1, int(px))
        if getattr(self, "_slice_enabled", False):
            self._init_slice_bounds()
            try:
                self.label.update()
            except Exception:
                pass
            if hasattr(self, "_update_info_label"):
                self._update_info_label()

    def save_slices(self, out_dir: str) -> int:
        if not (getattr(self, "_current_path", None) and getattr(self, "_images", None) and getattr(self, "_slice_enabled", False)):
            return 0
        img = self._images.get(self._current_path)
        if img is None: return 0
        bounds = sorted(set(max(0, min(img.height(), y)) for y in getattr(self, "_slice_bounds", [])))
        if 0 not in bounds: bounds = [0] + bounds
        if img.height() not in bounds: bounds = bounds + [img.height()]
        bounds = sorted(bounds)
        rects = []
        for i in range(len(bounds)-1):
            y1, y2 = bounds[i], bounds[i+1]
            if y2 <= y1: continue
            rects.append((y1, y2 - y1))
        if not rects: return 0

        stem = Path(self._current_path).stem
        pad = max(2, len(str(len(rects))))
        saved = 0
        for i, (y, h) in enumerate(rects, 1):
            frag = img.copy(QRect(0, y, img.width(), h))
            name = f"{stem}_{i:0{pad}d}.png"
            path = str(Path(out_dir) / name)
            try:
                frag.save(path, "PNG")
                saved += 1
            except Exception:
                pass
        return saved

    # Private helpers
    def _init_slice_bounds(self):
        if not (getattr(self, "_current_path", None) and getattr(self, "_images", None)):
            self._slice_bounds = []
            return
        img = self._images.get(self._current_path)
        if img is None:
            self._slice_bounds = []; return
        h = img.height()
        by = getattr(self, "_slice_by", "count")

        if by == "height":
            step = max(1, int(getattr(self, "_slice_height_px", 2000)))
            bounds = [0]
            y = 0
            while y + step < h:
                y += step
                bounds.append(y)
            bounds.append(h)
            self._slice_bounds = bounds
        else:
            n = max(2, getattr(self, "_slice_count", 2))
            self._slice_bounds = [int(round(i * h / n)) for i in range(n + 1)]
        for i in range(1, len(self._slice_bounds)):
            if self._slice_bounds[i] <= self._slice_bounds[i-1]:
                self._slice_bounds[i] = self._slice_bounds[i-1] + 1
        self._slice_bounds[-1] = h
        self._drag_boundary_index = None

    def _slice_bounds_on_label(self) -> List[int]:
        pm = getattr(self, "label", None).pixmap() if hasattr(self, "label") else None
        if pm is None: return []
        img = self._images.get(self._current_path) if hasattr(self, "_images") else None
        if img is None: return []
        scaled_h = pm.height()
        ys = [int(round(y * scaled_h / max(1, img.height()))) for y in getattr(self, "_slice_bounds", [])]
        return ys

    def _boundary_under_cursor(self, pos_label: QPoint, thresh: int = 6) -> Optional[int]:
        if not (getattr(self, "_slice_enabled", False) and getattr(self, "_slice_bounds", None) and getattr(self, "_current_path", None) in getattr(self, "_images", {})):
            return None
        y0 = self._v_offset_on_label() if hasattr(self, "_v_offset_on_label") else 0
        ys_lbl = self._slice_bounds_on_label()
        for i in range(1, len(ys_lbl)-1):
            if abs(pos_label.y() - (y0 + ys_lbl[i])) <= thresh:
                return i
        return None

    def _drag_boundary_to(self, pos_label: QPoint):
        if not (getattr(self, "_slice_enabled", False) and getattr(self, "_drag_boundary_index", None) and getattr(self, "_current_path", None) in getattr(self, "_images", {})):
            return
        idx = self._drag_boundary_index
        y_img = self._label_to_image_y(pos_label.y()) if hasattr(self, "_label_to_image_y") else 0
        low = self._slice_bounds[idx-1] + 1
        high = self._slice_bounds[idx+1] - 1
        y_img = max(low, min(high, y_img))
        self._slice_bounds[idx] = y_img
        try:
            self.label.update()
        except Exception:
            pass
        if hasattr(self, "_update_info_label"):
            self._update_info_label()

    def _paint_slice_dim_labels(self, p: QPainter):
        """Рисует бейджи с размерами рядом с фрагментами в режиме нарезки."""
        if not (getattr(self, "_slice_enabled", False) and getattr(self, "_current_path", None) in getattr(self,
                                                                                                           "_images",
                                                                                                           {})):
            return

        img = self._images[self._current_path]
        bounds = getattr(self, "_slice_bounds", None)
        if not bounds or len(bounds) < 2:
            return

        # Небольшие отступы внутри бейджа
        pad = 6

        for i in range(len(bounds) - 1):
            top = bounds[i]
            bottom = bounds[i + 1]
            h = max(0, bottom - top)
            w = int(img.width())

            # Подпись: "Ш×В"
            text = f"{w}×{h}"

            # Преобразуем координаты изображения -> координаты label'а
            # В проекте уже используются конвертеры вида _image_to_label_y/_image_to_label_x
            # Если у вас их нет, используйте вашу текущую математику зума/скролла.
            try:
                x_label = self._image_to_label_x(0) + 6
                y_label = self._image_to_label_y(top) + 6
            except Exception:
                # Фолбэк: без конвертера рисуем от (6, 6 + i*…)
                x_label = 6
                y_label = 6 + i * 22

            # Размер подложки под текст
            fm = QFontMetrics(self.label.font())
            br = fm.boundingRect(text)
            rect = QRect(x_label - pad, y_label - pad, br.width() + pad * 2, br.height() + pad * 2)

            # Подложка (полупрозрачная)
            p.fillRect(rect, QColor(0, 0, 0, 160))
            # Текст
            p.setPen(QColor(255, 255, 255))
            p.drawText(rect.adjusted(pad, pad, -pad, -pad), Qt.AlignLeft | Qt.AlignVCenter, text)
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

from PySide6.QtCore import Qt, QPoint, QRect
from PySide6.QtGui import QImage


@dataclass
class _FrameDrag:
    mode: str  # 'new' | 'move' | handle name: 'l','r','t','b','tl','tr','bl','br'
    anchor_f: Tuple[float, float]
    start_rect: QRect


class FrameMixin:
    """Crop tool ("Рамка").

    Stores rect in *image pixel coordinates* (x/y/width/height, right/bottom exclusive).
    """

    # ---- public API ----
    def set_frame_enabled(self, on: bool) -> None:
        on = bool(on)
        cur = bool(getattr(self, "_frame_enabled", False))
        if on == cur:
            return

        if on:
            # Disable conflicting modes.
            try:
                if getattr(self, "_slice_enabled", False) and hasattr(self, "set_slice_mode"):
                    self.set_slice_mode(False)
                else:
                    self._slice_enabled = False
                    self._drag_boundary_index = None
            except Exception:
                pass

            # Remember & disable selection.
            try:
                if getattr(self, "_frame_sel_prev", None) is None:
                    self._frame_sel_prev = bool(getattr(self, "_selection_enabled", True))
            except Exception:
                self._frame_sel_prev = True

            try:
                if hasattr(self, "set_selection_enabled"):
                    self.set_selection_enabled(False)
            except Exception:
                self._selection_enabled = False

            try:
                self._clear_selection()
            except Exception:
                pass

            self._frame_enabled = True
            self._frame_rect_img = None
            self._frame_drag = None
        else:
            self._frame_enabled = False
            self._frame_rect_img = None
            self._frame_drag = None

            # Restore selection enable state.
            prev = getattr(self, "_frame_sel_prev", None)
            if prev is None:
                prev = True
            try:
                if hasattr(self, "set_selection_enabled"):
                    self.set_selection_enabled(bool(prev))
                else:
                    self._selection_enabled = bool(prev)
            except Exception:
                pass
            self._frame_sel_prev = None

        # Sync check state of UI button if present.
        btn = getattr(self, "action_btn_frame", None)
        if btn is not None:
            try:
                if btn.isCheckable() and btn.isChecked() != on:
                    btn.setChecked(on)
            except Exception:
                pass

        try:
            self.label.update()
        except Exception:
            pass

    def frame_enabled(self) -> bool:
        return bool(getattr(self, "_frame_enabled", False))

    # ---- shortcuts ----
    def _frame_apply_from_shortcut(self) -> None:
        if not self.frame_enabled():
            return
        if getattr(self, "_frame_drag", None) is not None:
            return
        if not self._frame_has_rect():
            return
        self._frame_apply_crop()

    def _frame_esc_from_shortcut(self) -> None:
        if not self.frame_enabled():
            return
        # First Esc clears current rect; second Esc exits tool.
        if self._frame_has_rect() or getattr(self, "_frame_drag", None) is not None:
            self._frame_clear_rect()
        else:
            self.set_frame_enabled(False)

    # ---- mouse plumbing (called from PanZoomLabel) ----
    def _frame_press(self, pos_label: QPoint) -> bool:
        if not self.frame_enabled():
            return False
        if not (getattr(self, "_current_path", None) and self._current_path in getattr(self, "_images", {})):
            return False

        pmr = self.label._pixmap_rect_on_label()
        if pmr.isNull() or not pmr.contains(pos_label):
            return False

        img = self._images[self._current_path]
        pt_f = self._label_to_image_f(pos_label, img)
        if pt_f is None:
            return False

        hit = self._frame_hit_test(pos_label)
        rect = getattr(self, "_frame_rect_img", None)

        if hit is None:
            if rect is not None:
                # Use floor + clamp so edge clicks don't miss by rounding to W/H.
                ix = int(math.floor(pt_f[0]))
                iy = int(math.floor(pt_f[1]))
                ix = max(0, min(ix, int(img.width()) - 1))
                iy = max(0, min(iy, int(img.height()) - 1))
                if rect.contains(QPoint(ix, iy)):
                    mode = "move"
                    start_rect = QRect(rect)
                else:
                    mode = "new"
                    start_rect = QRect(0, 0, 0, 0)
                    self._frame_rect_img = None
            else:
                mode = "new"
                start_rect = QRect(0, 0, 0, 0)
                self._frame_rect_img = None
        else:
            mode = hit
            start_rect = QRect(rect) if rect is not None else QRect(0, 0, 0, 0)

        self._frame_drag = _FrameDrag(mode=mode, anchor_f=pt_f, start_rect=start_rect)
        self._frame_update_cursor_for_mode(mode)
        self._frame_move(pos_label)  # apply first update immediately
        return True

    def _frame_move(self, pos_label: QPoint) -> None:
        if not self.frame_enabled():
            return
        if not (getattr(self, "_current_path", None) and self._current_path in getattr(self, "_images", {})):
            return

        img = self._images[self._current_path]
        pt_f = self._label_to_image_f(pos_label, img)
        if pt_f is None:
            # keep cursor update even when outside pixmap
            if getattr(self, "_frame_drag", None) is None:
                self._frame_update_hover_cursor(pos_label)
            return

        drag: Optional[_FrameDrag] = getattr(self, "_frame_drag", None)
        if drag is None:
            self._frame_update_hover_cursor(pos_label)
            return

        W = int(img.width())
        H = int(img.height())

        min_w = int(getattr(self, "_frame_min_w", 8))
        min_h = int(getattr(self, "_frame_min_h", 8))

        ax, ay = drag.anchor_f
        cx, cy = pt_f

        def clamp(v: int, lo: int, hi: int) -> int:
            return lo if v < lo else hi if v > hi else v

        def norm_rect(x1: int, y1: int, x2: int, y2: int) -> QRect:
            x1 = clamp(x1, 0, W)
            x2 = clamp(x2, 0, W)
            y1 = clamp(y1, 0, H)
            y2 = clamp(y2, 0, H)
            if x2 - x1 < min_w:
                if x1 + min_w <= W:
                    x2 = x1 + min_w
                else:
                    x1 = max(0, W - min_w)
                    x2 = W
            if y2 - y1 < min_h:
                if y1 + min_h <= H:
                    y2 = y1 + min_h
                else:
                    y1 = max(0, H - min_h)
                    y2 = H
            return QRect(int(x1), int(y1), int(x2 - x1), int(y2 - y1))

        mode = drag.mode
        sr = drag.start_rect

        if mode == "new":
            x1 = int(math.floor(min(ax, cx)))
            x2 = int(math.ceil(max(ax, cx)))
            y1 = int(math.floor(min(ay, cy)))
            y2 = int(math.ceil(max(ay, cy)))
            self._frame_rect_img = norm_rect(x1, y1, x2, y2)

        elif mode == "move" and sr.width() > 0 and sr.height() > 0:
            dx = int(round(cx - ax))
            dy = int(round(cy - ay))
            x1 = sr.x() + dx
            y1 = sr.y() + dy
            x2 = x1 + sr.width()
            y2 = y1 + sr.height()
            # clamp by shifting
            if x1 < 0:
                x2 -= x1
                x1 = 0
            if y1 < 0:
                y2 -= y1
                y1 = 0
            if x2 > W:
                d = x2 - W
                x1 -= d
                x2 = W
            if y2 > H:
                d = y2 - H
                y1 -= d
                y2 = H
            self._frame_rect_img = norm_rect(x1, y1, x2, y2)

        else:
            # resize from handle
            if sr.width() <= 0 or sr.height() <= 0:
                return

            x1 = sr.x()
            y1 = sr.y()
            x2 = sr.x() + sr.width()
            y2 = sr.y() + sr.height()

            if "l" in mode:
                x1 = clamp(int(math.floor(cx)), 0, x2 - min_w)
            if "r" in mode:
                x2 = clamp(int(math.ceil(cx)), x1 + min_w, W)
            if "t" in mode:
                y1 = clamp(int(math.floor(cy)), 0, y2 - min_h)
            if "b" in mode:
                y2 = clamp(int(math.ceil(cy)), y1 + min_h, H)

            self._frame_rect_img = norm_rect(x1, y1, x2, y2)

        try:
            self.label.update()
        except Exception:
            pass

    def _frame_release(self, pos_label: QPoint) -> None:
        if not self.frame_enabled():
            return
        self._frame_drag = None
        try:
            self.label.setCursor(Qt.ArrowCursor)
        except Exception:
            pass
        try:
            self.label.update()
        except Exception:
            pass

    def _frame_update_hover_cursor(self, pos_label: QPoint) -> bool:
        if not self.frame_enabled():
            return False

        hit = self._frame_hit_test(pos_label)
        if hit is None:
            rect = getattr(self, "_frame_rect_img", None)
            if rect is not None and getattr(self, "_current_path", None) in getattr(self, "_images", {}):
                pt_f = self._label_to_image_f(pos_label, self._images[self._current_path])
                if pt_f is not None:
                    img = self._images[self._current_path]
                    ix = int(math.floor(pt_f[0]))
                    iy = int(math.floor(pt_f[1]))
                    ix = max(0, min(ix, int(img.width()) - 1))
                    iy = max(0, min(iy, int(img.height()) - 1))
                    if rect.contains(QPoint(ix, iy)):
                        try:
                            self.label.setCursor(Qt.SizeAllCursor)
                        except Exception:
                            pass
                        return True
            try:
                self.label.setCursor(Qt.ArrowCursor)
            except Exception:
                pass
            return False

        self._frame_update_cursor_for_mode(hit)
        return True

    # ---- apply/cancel helpers ----
    def _frame_clear_rect(self) -> None:
        self._frame_rect_img = None
        self._frame_drag = None
        try:
            self.label.setCursor(Qt.ArrowCursor)
            self.label.update()
        except Exception:
            pass

    def _frame_has_rect(self) -> bool:
        r = getattr(self, "_frame_rect_img", None)
        return bool(r is not None and r.width() > 0 and r.height() > 0)

    def _frame_apply_crop(self) -> None:
        if not (getattr(self, "_current_path", None) and self._current_path in getattr(self, "_images", {})):
            return
        if not self._frame_has_rect():
            return

        img: QImage = self._images[self._current_path]
        r: QRect = self._frame_rect_img

        x = max(0, min(int(r.x()), int(img.width())))
        y = max(0, min(int(r.y()), int(img.height())))
        w = max(1, min(int(r.width()), int(img.width() - x)))
        h = max(1, min(int(r.height()), int(img.height() - y)))

        if w == img.width() and h == img.height() and x == 0 and y == 0:
            self._frame_clear_rect()
            return

        try:
            self._push_undo()
        except Exception:
            pass

        out = img.copy(x, y, w, h)
        try:
            from ..utils import force_dpi72

            force_dpi72(out)
        except Exception:
            pass

        self._images[self._current_path] = out
        try:
            self._recalc_dirty_vs_disk()
        except Exception:
            pass

        self._frame_clear_rect()
        try:
            self._update_preview_pixmap()
        except Exception:
            pass
        try:
            self._update_actions_enabled()
        except Exception:
            pass

        try:
            self.show_toast(f"Обрезано: {out.width()}×{out.height()}px", 1800)
        except Exception:
            pass

    # ---- geometry helpers ----
    def _label_to_image_f(self, pos_label: QPoint, img: QImage) -> Optional[Tuple[float, float]]:
        pmr = self.label._pixmap_rect_on_label()
        if pmr.isNull() or pmr.width() <= 0 or pmr.height() <= 0:
            return None
        if not pmr.contains(pos_label):
            return None
        x_rel = float(pos_label.x() - pmr.x())
        y_rel = float(pos_label.y() - pmr.y())
        # Map label pixel coordinates to *pixel edge* coordinates [0..W] / [0..H].
        # This makes the rightmost/bottommost pixel map to W/H, avoiding (W-1)x(H-1) selections.
        den_w = float(max(1, int(pmr.width()) - 1))
        den_h = float(max(1, int(pmr.height()) - 1))
        x = x_rel * float(img.width()) / den_w
        y = y_rel * float(img.height()) / den_h
        x = max(0.0, min(float(img.width()), x))
        y = max(0.0, min(float(img.height()), y))
        return x, y

    def _f_to_img_point(self, pt_f: Tuple[float, float]) -> QPoint:
        x, y = pt_f
        return QPoint(int(round(x)), int(round(y)))

    def _image_rect_to_label_rect(self, rect_img: QRect) -> QRect:
        if not (getattr(self, "_current_path", None) and self._current_path in getattr(self, "_images", {})):
            return QRect()
        img = self._images[self._current_path]
        pmr = self.label._pixmap_rect_on_label()
        if pmr.isNull() or img.width() <= 0 or img.height() <= 0:
            return QRect()

        x1 = rect_img.x()
        y1 = rect_img.y()
        x2 = rect_img.x() + rect_img.width()
        y2 = rect_img.y() + rect_img.height()

        left = pmr.x() + int(math.floor(x1 * pmr.width() / img.width()))
        top = pmr.y() + int(math.floor(y1 * pmr.height() / img.height()))
        right = pmr.x() + int(math.ceil(x2 * pmr.width() / img.width()))
        bottom = pmr.y() + int(math.ceil(y2 * pmr.height() / img.height()))

        return QRect(int(left), int(top), max(1, int(right - left)), max(1, int(bottom - top)))

    # ---- hit testing & cursors ----
    def _frame_hit_test(self, pos_label: QPoint) -> Optional[str]:
        """Return handle name or None."""
        if not self._frame_has_rect():
            return None
        rect_img: QRect = self._frame_rect_img
        rect = self._image_rect_to_label_rect(rect_img)
        if rect.isNull():
            return None

        hs = int(getattr(self, "_frame_handle_size", 6))
        pad = hs + 2

        l = rect.left()
        r = rect.right()
        t = rect.top()
        b = rect.bottom()
        cx = (l + r) // 2
        cy = (t + b) // 2

        def box(x: int, y: int) -> QRect:
            return QRect(x - pad, y - pad, pad * 2, pad * 2)

        if box(l, t).contains(pos_label):
            return "tl"
        if box(r, t).contains(pos_label):
            return "tr"
        if box(l, b).contains(pos_label):
            return "bl"
        if box(r, b).contains(pos_label):
            return "br"
        if box(cx, t).contains(pos_label):
            return "t"
        if box(cx, b).contains(pos_label):
            return "b"
        if box(l, cy).contains(pos_label):
            return "l"
        if box(r, cy).contains(pos_label):
            return "r"
        return None

    def _frame_update_cursor_for_mode(self, mode: str) -> None:
        cur = Qt.ArrowCursor
        if mode == "move":
            cur = Qt.SizeAllCursor
        elif mode in ("l", "r"):
            cur = Qt.SizeHorCursor
        elif mode in ("t", "b"):
            cur = Qt.SizeVerCursor
        elif mode in ("tl", "br"):
            cur = Qt.SizeFDiagCursor
        elif mode in ("tr", "bl"):
            cur = Qt.SizeBDiagCursor
        try:
            self.label.setCursor(cur)
        except Exception:
            pass

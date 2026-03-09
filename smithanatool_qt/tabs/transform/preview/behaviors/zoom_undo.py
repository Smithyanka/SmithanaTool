from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from PySide6.QtCore import Qt, QSize, QPoint, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QSizePolicy, QStyle, QToolButton


class UndoMixin:
    def _push_undo(self) -> None:
        if not (self._current_path and self._current_path in self._images):
            return
        st = self._undo.setdefault(self._current_path, [])
        self._redo[self._current_path] = []
        st.append(self._images[self._current_path].copy())

    def _snap_selection_to_edges(self, h: int, y1: int, y2: int) -> tuple[int, int]:
        y1 = max(0, min(h, y1))
        y2 = max(0, min(h, y2))
        if y1 > y2:
            y1, y2 = y2, y1
        if y1 <= 1:
            y1 = 0
        if y2 >= h - 1:
            y2 = h
        return y1, y2

    def _undo_last(self) -> None:
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

    def _redo_last(self) -> None:
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

    def _set_enabled(self, name: str, enabled: bool) -> None:
        w = getattr(self, name, None)
        if w is None:
            return
        try:
            w.setEnabled(enabled)
            if isinstance(w, QToolButton):
                w.setCursor(Qt.PointingHandCursor if enabled else Qt.ArrowCursor)
        except Exception:
            pass

    def _update_actions_enabled(self) -> None:
        has_img = self._current_path in self._images if self._current_path else False
        is_psd = self._is_current_psd()

        cut_ok = has_img and self._has_selection()
        paste_ok = has_img and bool(self._clip)
        undo_ok = has_img and bool(self._undo.get(self._current_path, []))
        redo_ok = has_img and bool(self._redo.get(self._current_path, []))
        save_ok = has_img and not is_psd
        frame_ok = has_img

        for n in ("action_btn_cut", "btn_cut"):
            self._set_enabled(n, cut_ok)
        for n in ("action_btn_paste_top", "btn_paste_top"):
            self._set_enabled(n, paste_ok)
        for n in ("action_btn_paste_bottom", "btn_paste_bottom"):
            self._set_enabled(n, paste_ok)
        for n in ("action_btn_undo", "btn_undo"):
            self._set_enabled(n, undo_ok)
        for n in ("action_btn_redo", "btn_redo"):
            self._set_enabled(n, redo_ok)
        for n in ("action_btn_save", "btn_save"):
            self._set_enabled(n, save_ok)
        for n in ("action_btn_save_as", "btn_save_as"):
            self._set_enabled(n, save_ok)

        for n in ("action_btn_frame", "btn_frame"):
            self._set_enabled(n, frame_ok)

        # Keep the actions panel "pinned" globally (not per-file).
        handle = getattr(self, "btn_actions_handle", None)
        ap = getattr(self, "actions_panel", None)

        pinned = bool(getattr(self, "_actions_pinned", False))
        # If UI exists, keep pinned state synced with the handle.
        if handle is not None:
            try:
                # Allow toggling even if there's no image (icons will just be disabled).
                handle.setEnabled(True)
                if handle.isChecked() != pinned:
                    handle.setChecked(pinned)
            except Exception:
                pass

        if ap is not None:
            try:
                ap.setVisible(bool(pinned))
            except Exception:
                pass


class ZoomMixin:

    # ---- internal: lightweight "interactive" zoom flag (fast resampling while user scroll-zooms)
    def _mark_zoom_interacting(self) -> None:
        try:
            self._zoom_interacting = True
            t = getattr(self, "_zoom_interact_timer", None)
            if t is None:
                t = QTimer(self)
                t.setSingleShot(True)
                t.timeout.connect(self._end_zoom_interacting)
                self._zoom_interact_timer = t
            t.start(120)  # ms: after last wheel tick we switch back to smooth
        except Exception:
            pass

    def _end_zoom_interacting(self) -> None:
        self._zoom_interacting = False
        try:
            self.label.update()
        except Exception:
            pass

    def set_zoom_ui_mode(self, mode: int) -> None:
        self._apply_zoom_ui_mode(mode)

    def _apply_zoom_ui_mode(self, mode: int) -> None:
        self._zoom_ui_mode = 0 if mode not in (0, 1) else int(mode)
        is_overlay = self._zoom_ui_mode == 1

        for w in getattr(self, "_controls_row_widgets", []):
            w.setVisible(not is_overlay)

        self._update_zoom_controls_enabled()
        self._update_info_label()
        self._schedule_overlay_controls_position()

    def _schedule_overlay_controls_position(self) -> None:
        if getattr(self, "_overlay_repos_pending", False):
            return
        self._overlay_repos_pending = True
        QTimer.singleShot(0, self._run_overlay_repos)

    def _run_overlay_repos(self) -> None:
        self._overlay_repos_pending = False
        try:
            self._position_overlay_controls()
        except Exception:
            pass

    def _position_overlay_controls(self) -> None:
        scroll = self.scroll
        vp = scroll.viewport()
        if not vp:
            return

        margin = 12

        # сколько "отъел" нижний scrollbar (реально, по факту)
        fw = scroll.frameWidth() if hasattr(scroll, "frameWidth") else 0
        extra_h = max(0, (scroll.height() - 2 * fw) - vp.height())

        def h(widget, default: int) -> int:
            return widget.height() or widget.sizeHint().height() or default

        # --- Zoom +/- ---
        z_in = getattr(self, "_overlay_zoom_in", None)
        z_out = getattr(self, "_overlay_zoom_out", None)
        if z_in is not None and z_out is not None and z_in.isVisible():
            total_h = h(z_in, 28) + 6 + h(z_out, 28)
            y0 = ((vp.height() + extra_h) - total_h) // 2
            y0 = max(0, min(y0, max(0, vp.height() - total_h)))

            z_in.move(margin, y0)
            z_out.move(margin, y0 + h(z_in, 28) + 6)

        # --- Info ---
        info = getattr(self, "_overlay_info", None)
        if info is not None and info.isVisible():
            info.move(margin, margin)

        # --- Actions handle + pinned panel positioning ---
        handle = getattr(self, "btn_actions_handle", None)
        if handle is None or not handle.isVisible():
            return

        try:
            vp_geo = vp.geometry()
            hw = handle.width() or handle.sizeHint().width() or 28
            hh = handle.height() or handle.sizeHint().height() or 76

            sb_w = scroll.style().pixelMetric(QStyle.PM_ScrollBarExtent, None, scroll)
            x = max(0, scroll.width() - sb_w - hw)

            y = vp_geo.top() + max(0, ((vp_geo.height() + extra_h) - hh) // 2)
            handle.move(x, y)
            handle.raise_()

            ap = getattr(self, "actions_panel", None)
            pinned = bool(getattr(self, "_actions_pinned", False))
            if ap is None or not pinned or not ap.isVisible():
                return

            ap.adjustSize()
            pw = ap.width() or ap.sizeHint().width()
            ph = ap.height() or ap.sizeHint().height()

            gap = 4
            px = x - pw - gap
            py = y + (hh - ph) // 2

            min_x = vp_geo.left() + margin
            max_x = vp_geo.left() + vp_geo.width() - pw - margin
            min_y = vp_geo.top() + margin
            max_y = vp_geo.top() + vp_geo.height() - ph - margin

            ap.move(
                max(min_x, min(px, max_x)),
                max(min_y, min(py, max_y)),
            )
            ap.raise_()
        except Exception:
            pass

    def set_cut_paste_mode_enabled(self, on: bool) -> None:
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

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._current_path and self._current_path in self._images:
            self._update_preview_pixmap()
        try:
            self._position_toast()
        except Exception:
            pass
        try:
            self._position_overlay_controls()
        except Exception:
            pass

    # ---------- Зум/Fit ----------
    def _set_fit(self, fit: bool, *, update: bool = True) -> None:
        self.btn_fit.setChecked(fit)
        self._apply_fit_mode(fit, update=update)

    def _apply_fit_mode(self, on: bool, *, update: bool = True) -> None:
        self._fit_to_window = on
        self.scroll.setWidgetResizable(on)
        self.label.setSizePolicy(
            QSizePolicy.Ignored if on else QSizePolicy.Fixed,
            QSizePolicy.Ignored if on else QSizePolicy.Fixed,
        )
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

    def _update_zoom_controls_enabled(self) -> None:
        has_img = bool(getattr(self, "_current_path", None) and self._current_path in self._images)

        for w in (
                getattr(self, "btn_zoom_in", None),
                getattr(self, "btn_zoom_out", None),
                getattr(self, "btn_zoom_reset", None),
                getattr(self, "btn_fit", None),
                getattr(self, "lbl_zoom", None),
        ):
            if w is not None:
                w.setEnabled(has_img)

        is_overlay = getattr(self, "_zoom_ui_mode", 0) == 1

        if hasattr(self, "_overlay_zoom_in"):
            self._overlay_zoom_in.setVisible(has_img and is_overlay)
            self._overlay_zoom_in.setEnabled(has_img)

        if hasattr(self, "_overlay_zoom_out"):
            self._overlay_zoom_out.setVisible(has_img and is_overlay)
            self._overlay_zoom_out.setEnabled(has_img)

        if hasattr(self, "_overlay_info"):
            self._overlay_info.setVisible(has_img and is_overlay)

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

    def _zoom_set(self, value: float, anchor: QPoint | None = None) -> None:
        value = max(self._min_zoom, min(self._max_zoom, float(value)))
        if abs(value - self._zoom) < 1e-6:
            return
        old_zoom = self._zoom
        self._zoom = value
        self._mark_zoom_interacting()
        self._update_preview_pixmap(anchor=anchor, old_zoom=old_zoom)

    def _zoom_by(self, factor: float, anchor: QPoint | None = None) -> None:
        if self._fit_to_window:
            base = self._fit_window_zoom()
            self._set_fit(False, update=False)
            self._zoom_set(base * float(factor), anchor=anchor)
        else:
            self._zoom_set(self._zoom * float(factor), anchor=anchor)

    def _zoom_reset(self) -> None:
        if not (self._current_path and self._current_path in self._images):
            return
        self._set_fit(False)
        self._zoom_set(self._fit_width_zoom())

    def _update_zoom_label(self, effective_zoom=None) -> None:
        z = effective_zoom if effective_zoom is not None else self._zoom
        self.lbl_zoom.setText(f"{int(round(z * 100))}%")

    def _update_info_label(self) -> None:
        has_img = bool(self._current_path and self._current_path in self._images)

        if not has_img:
            text = "—"
        else:
            img = self._images[self._current_path]
            ow, oh = img.width(), img.height()

            sel_txt = ""
            if self._has_selection():
                sel_px = max(0, int(math.ceil(self._sel_y2) - math.floor(self._sel_y1)))
                sel_txt = f" • Выделено: {sel_px}px"

            size_head = ""
            try:
                if self._current_path and not self._is_memory_path(self._current_path):
                    b = Path(self._current_path).stat().st_size
                    size_head = f"{self._format_bytes(b)} • "
            except Exception:
                pass

            text = f"{size_head}{ow}×{oh}px{sel_txt}"

        self.lbl_info.setText(text)

        overlay = getattr(self, "_overlay_info", None)
        if overlay is not None and getattr(self, "_zoom_ui_mode", 0) == 1:
            overlay.setText(text)
            overlay.adjustSize()
            overlay.raise_()
            self._schedule_overlay_controls_position()

    def _apply_levels_to_qimage(self, qimg: QImage) -> QImage:
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

        ptr = img.bits()
        buf = np.frombuffer(ptr, dtype=np.uint8)

        buf = buf[: h_img * bpl].reshape(h_img, bpl)
        arr = buf[:, : w_img * 4].reshape(h_img, w_img, 4)

        rng = max(1, w - b)
        x = np.arange(256, dtype=np.float32)
        u = (x - b) / float(rng)
        u = np.clip(u, 0.0, 1.0)
        y = np.power(u, g) * 255.0
        lut = np.clip(y + 0.5, 0, 255).astype(np.uint8)

        arr[..., :3] = lut[arr[..., :3]]

        out = QImage(arr.tobytes(), w_img, h_img, w_img * 4, QImage.Format_RGBA8888)
        return out.copy()

    def _update_preview_pixmap(self, anchor: QPoint | None = None, old_zoom: float | None = None) -> None:
        if not (self._current_path and self._current_path in self._images):
            self._update_info_label()
            return

        img = self._images[self._current_path]

        # Build / reuse a view-image (with optional levels) ONCE per source-image + levels params.
        # Do NOT rescale the whole bitmap into a giant QPixmap on every zoom step.
        try:
            img_key = int(img.cacheKey()) if hasattr(img, "cacheKey") else id(img)
        except Exception:
            img_key = id(img)

        lv_on = bool(getattr(self, "_levels_enabled", False))
        lv_b = int(getattr(self, "_levels_black", 0))
        lv_w = int(getattr(self, "_levels_white", 255))
        lv_g = float(getattr(self, "_levels_gamma", 1.0))
        view_key = (self._current_path, img_key, lv_on, lv_b, round(lv_g, 6), lv_w)
        if getattr(self, "_view_img_key", None) != view_key:
            self._view_img_key = view_key
            self._view_img = self._apply_levels_to_qimage(img)
            # Prefer a QPixmap for painting on widgets (often faster and more reliable than drawing QImage directly).
            try:
                self._view_pm = QPixmap.fromImage(self._view_img)
            except Exception:
                self._view_pm = None

        # Used by PanZoomLabel to paint only the visible area.
        self._view_img = getattr(self, "_view_img", img)
        if getattr(self, "_view_pm", None) is None:
            try:
                self._view_pm = QPixmap.fromImage(self._view_img)
            except Exception:
                self._view_pm = None

        if self._fit_to_window:
            avail = self.scroll.viewport().size() - QSize(2, 2)
            disp = img.size().scaled(avail, Qt.KeepAspectRatio)
            if disp.width() < 1 or disp.height() < 1:
                disp = QSize(1, 1)
            self._display_size = disp
            try:
                self.label.setText("")
            except Exception:
                pass
            # Ensure canvas size is sane even when layout/viewport sizes are not settled yet.
            try:
                self.label.resize(self.scroll.viewport().size())
                self.label.updateGeometry()
            except Exception:
                pass
            if img.width() and img.height():
                eff = min(disp.width() / img.width(), disp.height() / img.height())
                self._update_zoom_label(eff)
        else:
            target_w = max(1, int(img.width() * self._zoom))
            target_h = max(1, int(img.height() * self._zoom))

            old_disp: QSize = getattr(self, "_display_size", QSize(img.width(), img.height()))
            old_w = max(1, int(old_disp.width()) or img.width())
            old_h = max(1, int(old_disp.height()) or img.height())

            disp = QSize(target_w, target_h)
            self._display_size = disp
            try:
                self.label.setText("")
            except Exception:
                pass

            try:
                self.label.resize(disp)
                self.label.updateGeometry()
            except Exception:
                pass

            vp = self.scroll.viewport().size()
            align = 0
            align |= int(Qt.AlignHCenter) if disp.width() <= vp.width() else int(Qt.AlignLeft)
            align |= int(Qt.AlignVCenter) if disp.height() <= vp.height() else int(Qt.AlignTop)
            self.scroll.setAlignment(Qt.Alignment(align))

            self._update_zoom_label()

            if anchor is not None:
                try:
                    hbar = self.scroll.horizontalScrollBar()
                    vbar = self.scroll.verticalScrollBar()
                    rx = anchor.x() / max(1, old_w)
                    ry = anchor.y() / max(1, old_h)
                    new_x = int(rx * disp.width() - self.scroll.viewport().width() / 2)
                    new_y = int(ry * disp.height() - self.scroll.viewport().height() / 2)
                    hbar.setValue(max(0, min(hbar.maximum(), new_x)))
                    vbar.setValue(max(0, min(vbar.maximum(), new_y)))
                except Exception:
                    pass

        self._update_info_label()
        self.label.update()

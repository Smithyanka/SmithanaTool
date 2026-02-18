from __future__ import annotations

from PySide6.QtCore import Qt, QSize, QPoint
from PySide6.QtGui import (
    QPixmap, QImage
)
from PySide6.QtWidgets import (
    QSizePolicy, QStyle
)

import numpy as np

import math


class ZoomMixin:
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
                sel_txt = f" • Выделено: {sel_px}px"
    
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
    

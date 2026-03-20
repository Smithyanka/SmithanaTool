from __future__ import annotations

import os

from smithanatool_qt.tabs.common.bind import (
    apply_bindings,
    ini_load_str,
    ini_save_str,
    reset_bindings,
)
from smithanatool_qt.tabs.common.defaults import DEFAULTS

from .service import resolve_threads


class StitchSectionStateMixin:
    def _set_smart_detector(self, detector: str, persist: bool = False):
        detector = "direct" if detector == "direct" else "smart"
        try:
            self.combo_smart_detector.blockSignals(True)
            self.combo_smart_detector.setCurrentIndex(1 if detector == "direct" else 0)
        finally:
            self.combo_smart_detector.blockSignals(False)

        is_smart = detector == "smart"
        self.lbl_smart_sensitivity.setVisible(is_smart)
        self.spin_smart_sensitivity.setVisible(is_smart)
        self.lbl_smart_scan_step.setVisible(is_smart)
        self.spin_smart_scan_step.setVisible(is_smart)
        self.lbl_smart_ignore.setVisible(is_smart)
        self.spin_smart_ignore.setVisible(is_smart)

        if persist:
            ini_save_str("StitchSection", "smart_detector", detector)

    def _set_group_by(self, by: str, persist: bool = False):
        by = "height" if by == "height" else "count"
        try:
            self.combo_auto_mode.blockSignals(True)
            self.combo_auto_mode.setCurrentIndex(0 if by == "count" else 1)
        finally:
            self.combo_auto_mode.blockSignals(False)

        self.lbl_group.setVisible(by == "count")
        self.spin_group.setVisible(by == "count")
        self.lbl_max_h.setVisible(by == "height")
        self.spin_max_h.setVisible(by == "height")

        if persist:
            ini_save_str("StitchSection", "group_by", by)

    def _set_stitch_mode(self, mode: str, persist: bool = False):
        mode = mode if mode in {"one", "multi", "smart"} else "one"
        try:
            self.rb_one.blockSignals(True)
            self.rb_auto.blockSignals(True)
            self.rb_smart.blockSignals(True)
            self.rb_one.setChecked(mode == "one")
            self.rb_auto.setChecked(mode == "multi")
            self.rb_smart.setChecked(mode == "smart")
        finally:
            self.rb_one.blockSignals(False)
            self.rb_auto.blockSignals(False)
            self.rb_smart.blockSignals(False)

        self._apply_stitch_mode(mode)
        if persist:
            ini_save_str("StitchSection", "stitch_mode", mode)

    def _apply_initial_ui_state(self):
        self.chk_no_resize.setChecked(True)

        self._set_group_by("count")
        self._set_smart_detector("smart")
        self._set_stitch_mode("one")

        self._update_dim_label()
        self._apply_dim_state()
        self._apply_threads_state()
        self._apply_compress_state(self.chk_opt.isChecked())

    def _get_last_pick_dir(self, fallback: str = "") -> str:
        path = ini_load_str("StitchSection", "last_pick_dir", "").strip()
        return path or fallback or os.path.expanduser("~")

    def _set_last_pick_dir(self, path: str):
        if not path:
            return
        norm = os.path.dirname(path) if os.path.isfile(path) else path
        ini_save_str("StitchSection", "last_pick_dir", norm)

    def _get_last_out_dir(self, fallback: str = "") -> str:
        path = ini_load_str("StitchSection", "last_out_dir", "").strip()
        return path or fallback or os.path.expanduser("~")

    def _set_last_out_dir(self, path: str):
        if not path:
            return

        path = os.path.normpath(path)
        _, ext = os.path.splitext(path)

        if os.path.isfile(path) or ext.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff", ".tga"}:
            norm = os.path.dirname(path)
        else:
            norm = path

        ini_save_str("StitchSection", "last_out_dir", norm)

    def _load_group_by(self) -> str:
        value = ini_load_str("StitchSection", "group_by", "count").strip().lower()
        return "height" if value == "height" else "count"

    def _load_stitch_mode(self) -> str:
        value = ini_load_str("StitchSection", "stitch_mode", "one").strip().lower()
        return value if value in {"one", "multi", "smart"} else "one"

    def _load_smart_detector(self) -> str:
        value = ini_load_str("StitchSection", "smart_detector", "smart").strip().lower()
        return "direct" if value == "direct" else "smart"

    def _current_smart_detector_key(self) -> str:
        return "direct" if self.combo_smart_detector.currentIndex() == 1 else "smart"

    def _current_stitch_mode(self) -> str:
        if self.rb_one.isChecked():
            return "one"
        if self.rb_smart.isChecked():
            return "smart"
        return "multi"

    def _update_zeros_controls(self, mode: str | None = None):
        mode = mode or self._current_stitch_mode()
        show_common = mode in {"multi", "smart"}
        self.lbl_common_zeros.setVisible(show_common)
        self.spin_zeros.setVisible(mode == "multi")
        self.spin_smart_zeros.setVisible(mode == "smart")

    def _apply_stitch_mode(self, mode: str):
        self.grp_auto.setVisible(mode == "multi")
        self.grp_smart.setVisible(mode == "smart")
        self._update_zeros_controls(mode)

    def _on_stitch_mode_changed(self, _checked: bool):
        self._set_stitch_mode(self._current_stitch_mode(), persist=True)

    def _on_auto_mode_changed(self, idx: int):
        self._set_group_by("count" if idx == 0 else "height", persist=True)

    def _on_smart_detector_changed(self, idx: int):
        self._set_smart_detector("direct" if idx == 1 else "smart", persist=True)

    def _apply_threads_state(self, checked: bool | None = None):
        if checked is None:
            checked = self.chk_auto_threads.isChecked()
        enabled = not checked
        self.spin_threads.setEnabled(enabled)
        self.lbl_threads.setEnabled(enabled)

    def _apply_compress_state(self, optimize_on: bool):
        self.spin_compress.setEnabled(not optimize_on)
        self.lbl_compress.setEnabled(not optimize_on)
        if optimize_on:
            self.spin_compress.setToolTip(
                "Оптимизация PNG включена — изменение уровня даёт умеренный эффект, поэтому поле отключено."
            )
        else:
            self.spin_compress.setToolTip("Уровень DEFLATE 0–9: выше — дольше и немного меньше файл.")

    def _update_dim_label(self):
        if self.cmb_dir.currentText() == "По вертикали":
            self.lbl_dim.setText("Ширина (px):")
            self.chk_no_resize.setText("Не изменять ширину")
        else:
            self.lbl_dim.setText("Высота (px):")
            self.chk_no_resize.setText("Не изменять высоту")

    def _apply_dim_state(self):
        enabled = not self.chk_no_resize.isChecked()
        self.spin_dim.setEnabled(enabled)
        self.lbl_dim.setEnabled(enabled)

    def _resolve_threads(self) -> int:
        return resolve_threads(self.chk_auto_threads.isChecked(), int(self.spin_threads.value()))

    def reset_to_defaults(self):
        auto_mode = "count" if self.combo_auto_mode.currentIndex() == 0 else "height"
        smart_detector = self._current_smart_detector_key()
        stitch_mode = self._current_stitch_mode()

        reset_bindings(self, "StitchSection")

        self._set_group_by(auto_mode, persist=True)
        self._set_smart_detector(smart_detector, persist=True)
        self._set_stitch_mode(stitch_mode, persist=True)

        self._update_dim_label()
        self._apply_dim_state()
        self._apply_compress_state(self.chk_opt.isChecked())
        self._apply_threads_state()

    def _apply_settings_from_ini(self):
        apply_bindings(
            self,
            "StitchSection",
            [
                (self.cmb_dir, "mode", 0),
                (self.chk_no_resize, "no_resize", True),
                (self.spin_dim, "dim", 800),
                (self.chk_opt, "optimize_png", True),
                (self.spin_compress, "compress_level", 6),
                (self.chk_strip, "strip_metadata", True),
                (self.spin_group, "per", 12),
                (self.spin_zeros, "zeros", 2),
                (self.spin_max_h, "group_max_height", 10000),
                (self.chk_auto_threads, "auto_threads", DEFAULTS["auto_threads"]),
                (self.spin_threads, "threads", DEFAULTS["threads"]),
                (self.spin_smart_height, "smart_height", 8000),
                (self.spin_smart_zeros, "smart_zeros", 2),
                (self.spin_smart_sensitivity, "smart_sensitivity", 90),
                (self.spin_smart_scan_step, "smart_scan_step", 5),
                (self.spin_smart_ignore, "smart_ignore_borders", 5),
            ],
        )

        self._set_group_by(self._load_group_by())
        self._set_smart_detector(self._load_smart_detector())
        self._set_stitch_mode(self._load_stitch_mode())

        self._update_dim_label()
        self._apply_dim_state()
        self._apply_compress_state(self.chk_opt.isChecked())
        self._apply_threads_state()

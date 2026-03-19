from __future__ import annotations

from PySide6.QtCore import Slot
from PySide6.QtWidgets import QFileDialog

from smithanatool_qt.settings_bind import (
    bind_attr_string,
    bind_checkbox,
    bind_line_edit,
    bind_radiobuttons,
    bind_spinbox,
    try_bind_checkbox,
    try_bind_line_edit,
)
from smithanatool_qt.tabs.common.defaults import DEFAULTS
from smithanatool_qt.tabs.parsers.common.app_paths import choose_start_dir
from smithanatool_qt.tabs.parsers.common.parser_defaults import default_thread_count
from smithanatool_qt.tabs.parsers.common.parser_state import CommonParserStateMixin


class ManhwaTabStateMixin(CommonParserStateMixin):
    def _ini_group_name(self) -> str:
        return 'ParserManhwa'

    def _bind_section_expanded(self, sec, key: str, default: bool = False) -> None:
        shadow = f'__{key}__shadow'
        setattr(self, shadow, '1' if default else '0')
        bind_attr_string(self, shadow, self._ini_key(key), '1' if default else '0')

        value = str(getattr(self, shadow, '0')).lower() in ('1', 'true', 'yes', 'on')
        sec.toggle_button.blockSignals(True)
        sec.toggle_button.setChecked(value)
        sec.toggle_button.blockSignals(False)
        try:
            sec._set_content_visible(value, animate=False)
            sec._update_header_icon(value)
            sec.setProperty('expanded', value)
        except Exception:
            pass
        sec.toggle_button.toggled.connect(lambda checked, ini_key=key: self._save_bool_ini(ini_key, checked))

    def reset_to_defaults(self) -> None:
        threads = default_thread_count()

        mode_idx = self.combo_auto_mode.currentIndex()

        self.spin_minw.setValue(720)
        self.chk_auto.setChecked(True)
        self.chk_no_resize.setChecked(True)
        self.spin_width.setValue(800)
        self.chk_same_dir.setChecked(True)
        self.chk_delete_sources.setChecked(True)
        self.chk_opt.setChecked(True)
        self.spin_comp.setValue(6)
        self.chk_strip.setChecked(True)
        self.spin_per.setValue(12)
        self.spin_zeros.setValue(2)

        try:
            self.combo_auto_mode.blockSignals(True)
            self.combo_auto_mode.setCurrentIndex(mode_idx)
        finally:
            self.combo_auto_mode.blockSignals(False)

        self.spin_max_h.setValue(10000)
        self.spin_smart_height.setValue(8000)
        self.spin_smart_sensitivity.setValue(90)
        self.spin_smart_scan_step.setValue(5)
        self.spin_smart_ignore.setValue(5)
        self.chk_auto_threads.setChecked(True)
        self.spin_threads.setValue(threads)
        self.chk_auto_buy.setChecked(False)
        self.chk_auto_use_ticket.setChecked(False)
        self.spin_scroll_ms.setValue(5000)

        mode_map = {0: 'count', 1: 'height', 2: 'smart'}
        self._group_by_shadow = mode_map.get(mode_idx, 'count')
        self._save_str_ini('group_by', self._group_by_shadow)

        self._update_mode()
        self._apply_threads_state()
        self._update_group_by_visibility()
        self._update_auto_enabled()
        self._refresh_run_enabled()

    def _persist_mode(self) -> None:
        self._update_mode()

    @Slot()
    def _pick_stitch_dir(self) -> None:
        start_dir = choose_start_dir((getattr(self, '_stitch_dir', '') or '').strip() or (getattr(self, '_out_dir', '') or '').strip())
        selected = QFileDialog.getExistingDirectory(self, 'Папка для склеек', start_dir, QFileDialog.ShowDirsOnly)
        if selected:
            self._stitch_dir = selected
            self._save_str_ini('stitch_dir', selected)
            self._refresh_stitch_dir_label()

    def _refresh_run_enabled(self) -> None:
        running = getattr(self, '_is_running', False)
        has_out = bool(self._out_dir)
        has_title = self._is_valid(self.ed_title)
        mode = 'number' if self.rb_number.isChecked() else 'id' if self.rb_id.isChecked() else 'index' if self.rb_index.isChecked() else 'ui'
        need_spec = mode in ('number', 'id', 'index')
        has_spec = (not need_spec) or self._is_valid(self.ed_spec)
        self.btn_run.setEnabled((not running) and has_out and has_title and has_spec)

    def _update_png_controls(self) -> None:
        auto_on = self.chk_auto.isChecked()
        enable_comp = auto_on and (not self.chk_opt.isChecked())
        self.spin_comp.setEnabled(enable_comp)
        self.lbl_comp.setEnabled(enable_comp)

    def _update_group_by_visibility(self) -> None:
        idx = int(self.combo_auto_mode.currentIndex())
        show_count = idx == 0
        show_height = idx == 1
        show_smart = idx == 2

        self.lbl_per.setVisible(show_count)
        self.spin_per.setVisible(show_count)
        self.lbl_max_h.setVisible(show_height)
        self.spin_max_h.setVisible(show_height)

        self.lbl_smart_height.setVisible(show_smart)
        self.spin_smart_height.setVisible(show_smart)
        self.lbl_smart_sensitivity.setVisible(show_smart)
        self.spin_smart_sensitivity.setVisible(show_smart)
        self.lbl_smart_scan_step.setVisible(show_smart)
        self.spin_smart_scan_step.setVisible(show_smart)
        self.lbl_smart_ignore.setVisible(show_smart)
        self.spin_smart_ignore.setVisible(show_smart)

    def _update_auto_enabled(self) -> None:
        on = self.chk_auto.isChecked()
        widgets = [
            self.chk_no_resize,
            self.spin_width,
            self.chk_same_dir,
            self.btn_pick_stitch,
            self.chk_delete_sources,
            self.chk_opt,
            self.spin_comp,
            self.chk_strip,
            self.spin_per,
            self.spin_zeros,
            self.spin_max_h,
            self.spin_smart_height,
            self.spin_smart_sensitivity,
            self.spin_smart_scan_step,
            self.spin_smart_ignore,
            self.lbl_stitch_text,
            self.lbl_stitch_dir,
            self.grp_png,
            self.lbl_per,
            self.lbl_zeros,
            self.lbl_max_h,
            self.lbl_smart_height,
            self.lbl_smart_sensitivity,
            self.lbl_smart_scan_step,
            self.lbl_smart_ignore,
            self.grp_dim,
            self.lbl_mode,
            self.combo_auto_mode,
            self.grp_stitch_opts,
            self.grp_setup,
        ]
        for widget in widgets:
            widget.setEnabled(on)
        self._update_same_dir()
        self._update_no_resize()
        self._update_png_controls()
        self._refresh_stitch_dir_label()

    def _update_no_resize(self) -> None:
        enabled = self.chk_auto.isChecked() and not self.chk_no_resize.isChecked()
        self.lbl_width.setEnabled(enabled)
        self.spin_width.setEnabled(enabled)

    def _update_same_dir(self) -> None:
        pick_enabled = self.chk_auto.isChecked() and not self.chk_same_dir.isChecked()
        self.btn_pick_stitch.setEnabled(pick_enabled)
        self.lbl_stitch_text.setEnabled(pick_enabled)
        self.lbl_stitch_dir.setEnabled(pick_enabled)
        self._refresh_stitch_dir_label()

    def _update_mode(self) -> None:
        new_mode = 'number' if self.rb_number.isChecked() else 'id' if self.rb_id.isChecked() else 'index' if self.rb_index.isChecked() else 'ui'
        prev = getattr(self, '_last_mode', None)

        if new_mode == 'ui':
            self.ed_spec.setValidator(None)
            if prev != 'ui':
                self._spec_before_ui = self.ed_spec.text()
            self.lbl_spec.setText('—')
            self.ed_spec.clear()
            self.ed_spec.setPlaceholderText('Выбор глав появится после нажатия «Запустить»')
            self.lbl_spec.setEnabled(False)
            self.ed_spec.setEnabled(False)
        else:
            self.lbl_spec.setEnabled(True)
            self.ed_spec.setEnabled(True)
            if new_mode == 'number':
                self.lbl_spec.setText('Глава/ы:')
                self.ed_spec.setPlaceholderText('например: 1,2,5-7')
                self.ed_spec.setValidator(self._val_ranges)
            elif new_mode == 'id':
                self.lbl_spec.setText('Viewer ID:')
                self.ed_spec.setPlaceholderText('например: 12801928, 12999192')
                self.ed_spec.setValidator(self._val_csv_ints)
            else:
                self.lbl_spec.setText('Индекс:')
                self.ed_spec.setPlaceholderText('например: 1,2,5-7')
                self.ed_spec.setValidator(self._val_ranges)
            if prev == 'ui' and not self.ed_spec.text():
                self.ed_spec.setText(self._spec_before_ui or '')

        self._last_mode = new_mode
        self._refresh_run_enabled()

    def _refresh_stitch_dir_label(self) -> None:
        use_same = self.chk_same_dir.isChecked()
        path = (self._out_dir if use_same else self._stitch_dir) or ''
        text = path or '— не выбрано —'
        self.lbl_stitch_dir.set_full_text(text)
        color = '#454545' if not self.lbl_stitch_dir.isEnabled() else '#080' if path else '#a00'
        self.lbl_stitch_dir.setStyleSheet(f'color:{color}')

    def _apply_settings_from_ini(self) -> None:
        bind_attr_string(self, '_out_dir', self._ini_key('out_dir'), '')
        bind_attr_string(self, '_stitch_dir', self._ini_key('stitch_dir'), '')
        bind_line_edit(self.ed_title, self._ini_key('title'), '')
        bind_line_edit(self.ed_spec, self._ini_key('spec'), '')
        try_bind_line_edit(self, 'ed_vol', self._ini_key('volumes'), '')
        try_bind_checkbox(self, 'chk_auto_buy', self._ini_key('auto_buy'), False)
        try_bind_checkbox(self, 'chk_auto_use_ticket', self._ini_key('auto_use_ticket'), False)
        bind_spinbox(self.spin_minw, self._ini_key('min_width'), 720)
        bind_spinbox(self.spin_width, self._ini_key('target_width'), 800)
        bind_spinbox(self.spin_comp, self._ini_key('compress_level'), 6)
        bind_spinbox(self.spin_per, self._ini_key('per'), 12)
        bind_spinbox(self.spin_scroll_ms, self._ini_key('scroll_ms'), 5000)
        bind_radiobuttons([self.rb_number, self.rb_id, self.rb_index, self.rb_ui], self._ini_key('mode'), 0)
        bind_checkbox(self.chk_auto, self._ini_key('auto_stitch'), True)
        bind_checkbox(self.chk_no_resize, self._ini_key('no_resize_width'), True)
        bind_checkbox(self.chk_same_dir, self._ini_key('same_dir'), True)
        bind_checkbox(self.chk_delete_sources, self._ini_key('delete_sources'), True)
        bind_checkbox(self.chk_opt, self._ini_key('optimize_png'), True)
        bind_checkbox(self.chk_strip, self._ini_key('strip_metadata'), True)
        bind_spinbox(self.spin_zeros, self._ini_key('zeros'), 2)
        bind_spinbox(self.spin_max_h, self._ini_key('group_max_height'), 10000)
        bind_spinbox(self.spin_smart_height, self._ini_key('smart_height'), 8000)
        bind_spinbox(self.spin_smart_sensitivity, self._ini_key('smart_sensitivity'), 90)
        bind_spinbox(self.spin_smart_scan_step, self._ini_key('smart_scan_step'), 5)
        bind_spinbox(self.spin_smart_ignore, self._ini_key('smart_ignore_borders'), 5)
        bind_attr_string(self, '_group_by_shadow', self._ini_key('group_by'), 'count')
        bind_checkbox(self.chk_auto_threads, self._ini_key('auto_threads'), DEFAULTS['auto_threads'])
        bind_spinbox(self.spin_threads, self._ini_key('threads'), DEFAULTS['threads'])

        group_by = str(getattr(self, '_group_by_shadow', 'count') or 'count').lower()
        if group_by == 'height':
            idx = 1
        elif group_by == 'smart':
            idx = 2
        else:
            idx = 0

        self.combo_auto_mode.blockSignals(True)
        try:
            self.combo_auto_mode.setCurrentIndex(idx)
        finally:
            self.combo_auto_mode.blockSignals(False)

        self._refresh_out_dir_label()
        self._refresh_stitch_dir_label()
        self._apply_threads_state()
        self._update_group_by_visibility()
        self._update_mode()
        self._update_auto_enabled()
        self._refresh_run_enabled()

from __future__ import annotations

from smithanatool_qt.settings_bind import bind_attr_string, bind_line_edit, bind_radiobuttons, group
from smithanatool_qt.tabs.parsers.common.parser_defaults import default_thread_count
from smithanatool_qt.tabs.parsers.common.parser_state import CommonParserStateMixin


class NovelTabStateMixin(CommonParserStateMixin):
    def _ini_group_name(self) -> str:
        return 'ParserNovel'

    def reset_to_defaults(self) -> None:
        threads = default_thread_count()
        keep_mode_idx = 1 if self.rb_id.isChecked() else 0
        self.rb_ui.setChecked(keep_mode_idx == 0)
        self.rb_id.setChecked(keep_mode_idx == 1)
        self.chk_auto_threads.setChecked(True)
        self.spin_threads.setValue(threads)
        self.chk_auto_buy.setChecked(False)
        self.chk_auto_use_ticket.setChecked(False)

        self._save_int_ini('mode', keep_mode_idx)
        self._save_bool_ini('auto_threads', True)
        self._save_int_ini('threads', threads)
        self._save_bool_ini('auto_buy', False)
        self._save_bool_ini('auto_use_ticket', False)
        self._update_mode()
        self._refresh_run_enabled()

    def _update_mode(self) -> None:
        if self.rb_id.isChecked():
            self.lbl_spec.setText('Product ID(ы):')
            self.ed_spec.setPlaceholderText('например: 49248366, 49248367')
            self.ed_spec.setValidator(self._val_csv_ints)
            self.lbl_spec.show()
            self.ed_spec.show()
            self.ed_spec.setEnabled(True)
            return
        self.lbl_spec.hide()
        self.ed_spec.hide()
        self.ed_spec.clear()
        self.ed_spec.setEnabled(False)
        self.ed_spec.setValidator(None)

    def _refresh_run_enabled(self) -> None:
        running = getattr(self, '_is_running', False)
        out_ok = bool(self._out_dir)
        title_ok = self._is_valid(self.ed_title)
        spec_ok = True if self.rb_ui.isChecked() else self._is_valid(self.ed_spec)
        self.btn_run.setEnabled((not running) and out_ok and title_ok and spec_ok)

    def _apply_settings_from_ini(self) -> None:
        with group(self._ini_group_name()):
            bind_attr_string(self, '_out_dir', 'out_dir', '')
            bind_line_edit(self.ed_title, 'title', '')
            bind_line_edit(self.ed_spec, 'spec', '')
            bind_radiobuttons([self.rb_ui, self.rb_id], 'mode', 0)
            try:
                from smithanatool_qt.settings_bind import try_bind_checkbox

                try_bind_checkbox(self, 'chk_auto_threads', 'auto_threads', True)
                try_bind_checkbox(self, 'chk_auto_buy', 'auto_buy', False)
                try_bind_checkbox(self, 'chk_auto_use_ticket', 'auto_use_ticket', False)
            except Exception:
                pass
            bind_attr_string(self, '__threads__shadow', 'threads', str(self.spin_threads.value()))

        self._refresh_out_dir_label()
        try:
            threads = int(str(getattr(self, '__threads__shadow', self.spin_threads.value()) or self.spin_threads.value()))
            self.spin_threads.setValue(max(1, min(32, threads)))
        except Exception:
            pass
        self._apply_threads_state(self.chk_auto_threads.isChecked())
        self._update_mode()
        self._refresh_run_enabled()

    def _persist_mode(self) -> None:
        self._save_int_ini('mode', 1 if self.rb_id.isChecked() else 0)
        self._update_mode()
        self._refresh_run_enabled()

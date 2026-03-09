from __future__ import annotations

import inspect
from typing import Optional

from PySide6.QtCore import Slot
from PySide6.QtWidgets import QFileDialog, QMessageBox

from smithanatool_qt.settings_bind import group, save_attr_string

from .app_paths import choose_start_dir, get_settings_dir, open_in_explorer


class CommonParserStateMixin:
    def _ini_group_name(self) -> str:
        raise NotImplementedError

    def _settings_dir(self) -> str:
        try:
            anchor = inspect.getsourcefile(type(self)) or inspect.getfile(type(self))
        except Exception:
            anchor = None
        return get_settings_dir(anchor)

    def _save_str_ini(self, key: str, value: str) -> None:
        try:
            shadow_attr = f'__{key}__shadow'
            setattr(self, shadow_attr, value)
            with group(self._ini_group_name()):
                save_attr_string(self, shadow_attr, key)
        except Exception:
            pass

    def _save_int_ini(self, key: str, value: int) -> None:
        self._save_str_ini(key, str(int(value)))

    def _save_bool_ini(self, key: str, value: bool) -> None:
        self._save_str_ini(key, '1' if value else '0')

    def _confirm_and_reset(self) -> None:
        btn = QMessageBox.warning(
            self,
            'Сброс настроек',
            'Сбросить настройки?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if btn == QMessageBox.Yes:
            self.reset_to_defaults()

    def _toggle_ids_panel(self) -> None:
        if not self._ids_panel.ui_built:
            self._ids_panel.build_into(self._ids_slot)
        if not self._ids_panel.loaded:
            self._ids_panel.ensure_loaded()
        self._ids_panel.toggle_visibility()
        self.btn_toggle_ids.setText('Скрыть сохранённые ID' if self._ids_panel.visible else 'Показать сохранённые ID')

    def _on_copy_id_to_title_and_save(self, id_value: str) -> None:
        value = (id_value or '').strip()
        if not value:
            return
        self.ed_title.setText(value)
        self._save_str_ini('title', value)

    def _apply_threads_state(self, checked: Optional[bool] = None) -> None:
        if checked is None:
            checked = bool(self.chk_auto_threads.isChecked())
        enabled = not bool(checked)
        self.spin_threads.setEnabled(enabled)
        self.lbl_threads.setEnabled(enabled)

    def _refresh_out_dir_label(self) -> None:
        out_dir = (getattr(self, '_out_dir', '') or '').strip()
        self.lbl_out.set_full_text(out_dir or '— не выбрано —')
        self.lbl_out.setStyleSheet('color:#080' if out_dir else 'color:#a00')
        self.btn_open_dir.setEnabled(bool(out_dir))

    def _set_out_dir(self, path: str, *, persist: bool = True) -> None:
        self._out_dir = (path or '').strip()
        if persist:
            self._save_str_ini('out_dir', self._out_dir)
        self._refresh_out_dir_label()
        if hasattr(self, '_refresh_stitch_dir_label'):
            self._refresh_stitch_dir_label()
        if hasattr(self, '_refresh_run_enabled'):
            self._refresh_run_enabled()

    @Slot()
    def _pick_out(self) -> None:
        start_dir = choose_start_dir((getattr(self, '_out_dir', '') or '').strip() or self._settings_dir())
        selected = QFileDialog.getExistingDirectory(
            self,
            'Папка сохранения',
            start_dir,
            QFileDialog.ShowDirsOnly,
        )
        if selected:
            self._set_out_dir(selected)

    @Slot()
    def _open_out_dir(self) -> None:
        out_dir = (getattr(self, '_out_dir', '') or '').strip()
        if not out_dir:
            QMessageBox.information(self, 'Папка', 'Сначала выберите папку сохранения.')
            return
        open_in_explorer(out_dir)

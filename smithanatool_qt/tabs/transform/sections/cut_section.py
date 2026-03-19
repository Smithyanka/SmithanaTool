from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QLineEdit,
)

from smithanatool_qt.tabs.common.bind import (
    apply_bindings,
    reset_bindings,
    ini_save_int,
    ini_save_str,
)
from smithanatool_qt.tabs.common.defaults import DEFAULTS
from smithanatool_qt.tabs.transform.utils.fs import open_in_explorer


class CutSection(QWidget):
    def __init__(self, preview=None, parent=None, paths_provider=None):
        super().__init__(parent)
        self._preview = preview
        self._paths_provider = paths_provider

        self._slice_by_le = QLineEdit(self)
        self._slice_by_le.setVisible(False)
        self._cut_out_dir_le = QLineEdit(self)
        self._cut_out_dir_le.setVisible(False)

        self.setContentsMargins(0, 0, 0, 0)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)
        root.setAlignment(Qt.AlignTop)

        self.grp_regular = QGroupBox("Настройки")
        root.addWidget(self.grp_regular)

        v_main = QVBoxLayout(self.grp_regular)
        v_main.setSpacing(8)
        v_main.setAlignment(Qt.AlignTop)

        row_mode = QHBoxLayout()
        row_mode.addWidget(QLabel("Режим:"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["По количеству фрагментов", "По высоте"])
        row_mode.addWidget(self.combo_mode)
        row_mode.addStretch(1)
        v_main.addLayout(row_mode)

        row_count = QHBoxLayout()
        self.lbl_count = QLabel("Количество фрагментов:")
        row_count.addWidget(self.lbl_count)
        self.spin_slices = QSpinBox()
        self.spin_slices.setRange(2, 100)
        self.spin_slices.setValue(8)
        row_count.addWidget(self.spin_slices)
        row_count.addStretch(1)
        v_main.addLayout(row_count)

        row_height = QHBoxLayout()
        self.lbl_height = QLabel("Высота (px):")
        self.spin_height = QSpinBox()
        self.spin_height.setRange(100, 30000)
        self.spin_height.setSingleStep(50)
        self.spin_height.setValue(8000)
        row_height.addWidget(self.lbl_height)
        row_height.addWidget(self.spin_height)
        row_height.addStretch(1)
        v_main.addLayout(row_height)

        self.lbl_height.setVisible(False)
        self.spin_height.setVisible(False)

        self.grp_extra = QGroupBox("Доп. настройки")
        root.addWidget(self.grp_extra)

        v_extra = QVBoxLayout(self.grp_extra)
        v_extra.setSpacing(8)
        v_extra.setAlignment(Qt.AlignTop)

        row_labels = QHBoxLayout()
        self.chk_show_labels = QCheckBox("Показывать разрешение")
        self.chk_show_labels.setChecked(True)
        row_labels.addWidget(self.chk_show_labels)
        row_labels.addStretch(1)
        v_extra.addLayout(row_labels)

        row_threads = QHBoxLayout()
        self.chk_auto_threads = QCheckBox("Авто потоки")
        self.chk_auto_threads.setChecked(True)

        self.lbl_threads = QLabel("Потоки:")
        self.spin_threads = QSpinBox()
        self.spin_threads.setRange(1, 64)
        self.spin_threads.setValue(6)

        row_threads.addWidget(self.chk_auto_threads)
        row_threads.addSpacing(0)
        row_threads.addWidget(self.lbl_threads)
        row_threads.addWidget(self.spin_threads)
        row_threads.addStretch(1)
        v_extra.addLayout(row_threads)

        row_buttons = QHBoxLayout()
        row_buttons.setContentsMargins(0, 0, 0, 0)
        row_buttons.setSpacing(6)
        row_buttons.addStretch(1)

        self.btn_toggle = QPushButton("Вкл")
        self.btn_toggle.setMinimumWidth(55)
        self.btn_toggle.setCheckable(True)
        self.btn_toggle.setChecked(False)
        self.btn_save = QPushButton("Нарезать выделенные")
        row_buttons.addWidget(self.btn_toggle)
        row_buttons.addWidget(self.btn_save)
        root.addLayout(row_buttons)

        self.chk_auto_threads.toggled.connect(self._set_threads_enabled)
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)

        QTimer.singleShot(0, self._apply_settings_from_ini)

        if self._preview:
            self._preview.currentPathChanged.connect(self._on_preview_path_changed)
            self._preview.sliceCountChanged.connect(self._on_preview_slice_count_changed)

            self.btn_toggle.toggled.connect(self._on_toggle)
            self.spin_slices.valueChanged.connect(self._on_count_changed)
            self.spin_height.valueChanged.connect(self._on_height_changed)
            self.btn_save.clicked.connect(self._batch_cut_selected)
            self.chk_show_labels.toggled.connect(self._preview.label.set_show_slice_labels)

            if getattr(self._preview, "_slice_enabled", False):
                self.btn_toggle.setChecked(True)
                self.btn_toggle.setText("Выкл")
            else:
                self.btn_toggle.setChecked(False)
                self.btn_toggle.setText("Вкл")

        self._set_threads_enabled(self.chk_auto_threads.isChecked())

    def _refresh_geometry(self):
        self.updateGeometry()
        parent = self.parentWidget()
        if parent is not None:
            parent.updateGeometry()

    def refresh_stack_geometry(self):
        self._refresh_geometry()

    def _set_threads_enabled(self, auto_on: bool):
        on = not auto_on
        self.spin_threads.setEnabled(on)
        self.lbl_threads.setEnabled(on)

    def _current_slice_by(self) -> str:
        return "count" if self.combo_mode.currentIndex() == 0 else "height"

    def _selected_paths(self) -> list[str]:
        if callable(getattr(self, "_paths_provider", None)):
            try:
                paths = list(self._paths_provider() or [])
                return [p for p in paths if isinstance(p, str) and p]
            except Exception:
                pass
        cur = getattr(self._preview, "_current_path", None) if self._preview else None
        return [cur] if cur else []

    def _on_preview_slice_count_changed(self, n: int):
        try:
            self.spin_slices.blockSignals(True)
            self.spin_slices.setValue(max(self.spin_slices.minimum(), n))
        finally:
            self.spin_slices.blockSignals(False)
        ini_save_int("CutSection", "slices", int(self.spin_slices.value()))

    def _on_preview_path_changed(self, path: str):
        st = self._preview.get_slice_state(path)
        enabled = bool(st.get("enabled"))

        self.btn_toggle.blockSignals(True)
        self.btn_toggle.setChecked(enabled)
        self.btn_toggle.setText("Выкл" if enabled else "Вкл")
        self.btn_toggle.blockSignals(False)

        by = "height" if st.get("by") == "height" else "count"
        count = int(st.get("count", self.spin_slices.value()))
        height_px = int(st.get("height_px", self.spin_height.value()))

        try:
            self.combo_mode.blockSignals(True)
            self.spin_slices.blockSignals(True)
            self.spin_height.blockSignals(True)

            self.combo_mode.setCurrentIndex(0 if by == "count" else 1)
            self.spin_slices.setValue(max(self.spin_slices.minimum(), min(self.spin_slices.maximum(), count)))
            self.spin_height.setValue(max(self.spin_height.minimum(), min(self.spin_height.maximum(), height_px)))
        finally:
            self.combo_mode.blockSignals(False)
            self.spin_slices.blockSignals(False)
            self.spin_height.blockSignals(False)

        show_count = by == "count"
        self.lbl_count.setVisible(show_count)
        self.spin_slices.setVisible(show_count)
        self.lbl_height.setVisible(not show_count)
        self.spin_height.setVisible(not show_count)

    def _on_mode_changed(self, idx: int):
        by = self._current_slice_by()
        show_count = by == "count"

        self.lbl_count.setVisible(show_count)
        self.spin_slices.setVisible(show_count)
        self.lbl_height.setVisible(not show_count)
        self.spin_height.setVisible(not show_count)

        ini_save_str("CutSection", "slice_by", by)

        if self._preview and getattr(self._preview, "_slice_enabled", False):
            if by == "count":
                self._preview.set_slice_by("count")
                self._preview.set_slice_count(int(self.spin_slices.value()))
            else:
                self._preview.set_slice_by("height")
                self._preview.set_slice_height(int(self.spin_height.value()))

    def _on_height_changed(self, value: int):
        if not self._preview:
            return

        if getattr(self._preview, "_slice_enabled", False) and self._current_slice_by() == "height":
            self._preview.set_slice_height(int(value))
        else:
            try:
                self._preview._slice_height_px = int(value)
            except Exception:
                pass

        try:
            cur = getattr(self._preview, "_current_path", None)
            self._preview._store_slice_state(cur)
        except Exception:
            pass

    def _on_count_changed(self, value: int):
        if not self._preview:
            return
        if getattr(self._preview, "_slice_enabled", False):
            self._preview.set_slice_count(int(value))

    def _on_toggle(self, checked: bool):
        if not self._preview:
            return
        self.btn_toggle.setText("Выкл" if checked else "Вкл")
        if not checked:
            self._preview.set_slice_mode(False)
            return

        by = self._current_slice_by()
        self._preview.set_slice_by(by)
        if by == "count":
            self._preview.set_slice_mode(True, int(self.spin_slices.value()))
        else:
            self._preview.set_slice_mode(True)
            self._preview.set_slice_height(int(self.spin_height.value()))

    def _batch_cut_selected(self):
        if not self._preview:
            QMessageBox.warning(self, "Нарезка", "Нет панели предпросмотра.")
            return

        paths = self._selected_paths()
        if not paths:
            QMessageBox.information(self, "Нарезка", "Не выбрано ни одного файла.")
            return

        start_out = self._cut_out_dir_le.text() or os.path.expanduser("~")
        out_dir = QFileDialog.getExistingDirectory(self, "Папка для сохранения фрагментов", start_out)
        if not out_dir:
            return

        self._cut_out_dir_le.setText(out_dir)
        ini_save_str("CutSection", "cut_out_dir", out_dir)

        auto_threads = bool(self.chk_auto_threads.isChecked())
        threads = int(self.spin_threads.value())

        dlg = QProgressDialog("Режу выделенные файлы…", None, 0, 0, self)
        dlg.setWindowTitle("Нарезка")
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setCancelButton(None)
        dlg.setMinimumDuration(0)
        dlg.show()
        QApplication.processEvents()

        total_saved = 0
        skipped: list[str] = []
        current_before = getattr(self._preview, "_current_path", None)

        try:
            for path in paths:
                try:
                    self._preview.show_path(path)
                    st = self._preview.get_slice_state()
                    if not bool(st.get("enabled")):
                        skipped.append(path)
                        continue

                    bounds = list(st.get("bounds") or [])
                    if len(bounds) < 2:
                        skipped.append(path)
                        continue

                    saved = self._preview.save_slices(out_dir, threads=threads, auto_threads=auto_threads)
                    total_saved += int(saved or 0)
                except Exception:
                    skipped.append(path)
        finally:
            dlg.close()
            try:
                if current_before:
                    self._preview.show_path(current_before)
            except Exception:
                pass

        msg = [f"Сохранено фрагментов: {total_saved}"]
        if skipped:
            msg.append(f"Пропущено файлов: {len(skipped)}")

        box = QMessageBox(self)
        box.setWindowTitle("Готово")
        box.setText("\n".join(msg))
        btn_open = box.addButton("Открыть папку", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.exec()
        if box.clickedButton() is btn_open:
            open_in_explorer(out_dir)

    def _save(self):
        if not self._preview or not getattr(self._preview, "_slice_enabled", False):
            QMessageBox.warning(self, "Нарезка", "Сначала включите режим нарезки (Вкл).")
            return

        start_out = self._cut_out_dir_le.text() or os.path.expanduser("~")
        out_dir = QFileDialog.getExistingDirectory(self, "Папка для сохранения фрагментов", start_out)
        if not out_dir:
            return

        self._cut_out_dir_le.setText(out_dir)
        ini_save_str("CutSection", "cut_out_dir", out_dir)

        auto_threads = bool(self.chk_auto_threads.isChecked())
        threads = int(self.spin_threads.value())

        dlg = QProgressDialog("Сохраняю фрагменты…", None, 0, 0, self)
        dlg.setWindowTitle("Сохранение")
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setCancelButton(None)
        dlg.setMinimumDuration(0)
        dlg.show()
        QApplication.processEvents()
        try:
            count = self._preview.save_slices(out_dir, threads=threads, auto_threads=auto_threads)
        finally:
            dlg.close()

        if count > 0:
            box = QMessageBox(self)
            box.setWindowTitle("Готово")
            box.setText(f"Сохранено фрагментов: {count}")
            btn_open = box.addButton("Открыть папку", QMessageBox.ActionRole)
            box.addButton(QMessageBox.Ok)
            box.exec()
            if box.clickedButton() is btn_open:
                open_in_explorer(out_dir)
        else:
            QMessageBox.information(self, "Нарезка", "Нет фрагментов для сохранения.")

    def reset_to_defaults(self):
        mode_idx = self.combo_mode.currentIndex()

        reset_bindings(self, "CutSection")

        try:
            self.combo_mode.blockSignals(True)
            self.combo_mode.setCurrentIndex(mode_idx)
        finally:
            self.combo_mode.blockSignals(False)

        self._slice_by_le.setText("count" if mode_idx == 0 else "height")
        ini_save_str("CutSection", "slice_by", self._slice_by_le.text())

        self._on_mode_changed(self.combo_mode.currentIndex())
        self._set_threads_enabled(self.chk_auto_threads.isChecked())
        self._refresh_geometry()

    def _apply_settings_from_ini(self):
        apply_bindings(
            self,
            "CutSection",
            [
                (self.chk_show_labels, "show_labels", True),
                (self.spin_slices, "slices", 8),
                (self.spin_height, "height_px", 8000),
                (self.chk_auto_threads, "auto_threads", DEFAULTS["auto_threads"]),
                (self.spin_threads, "threads", DEFAULTS["threads"]),
                (self._cut_out_dir_le, "cut_out_dir", DEFAULTS["cut_out_dir"]),
                (self._slice_by_le, "slice_by", "count"),
            ],
        )
        by = self._slice_by_le.text() or "count"
        self.combo_mode.setCurrentIndex(0 if by == "count" else 1)
        self._on_mode_changed(self.combo_mode.currentIndex())
        self._set_threads_enabled(self.chk_auto_threads.isChecked())

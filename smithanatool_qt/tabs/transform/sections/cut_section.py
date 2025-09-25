
from __future__ import annotations
import os, sys, subprocess
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QPushButton,
    QFileDialog, QMessageBox, QProgressDialog, QApplication, QCheckBox, QComboBox, QLineEdit
)
from PySide6.QtCore import Qt, QTimer
from smithanatool_qt.settings_bind import group, bind_spinbox, bind_checkbox, bind_line_edit

def _open_in_explorer(path: str):
    try:
        if sys.platform.startswith('win'):
            os.startfile(path)  # type: ignore
        elif sys.platform.startswith('darwin'):
            subprocess.Popen(['open', path])
        else:
            subprocess.Popen(['xdg-open', path])
    except Exception:
        pass

class CutSection(QWidget):
    def __init__(self, preview=None, parent=None):
        super().__init__(parent)
        self._preview = preview
        self._slice_by_le = QLineEdit(self)
        self._slice_by_le.setVisible(False)
        v = QVBoxLayout(self); v.setAlignment(Qt.AlignTop)

        # ---- режим нарезки
        row_mode = QHBoxLayout()
        row_mode.addWidget(QLabel("Режим:"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["По количеству фрагментов", "По высоте"])
        row_mode.addWidget(self.combo_mode)
        row_mode.addStretch(1)
        v.addLayout(row_mode)

        # ---- строка с количеством фрагментов
        row1 = QHBoxLayout()
        self.lbl_count = QLabel("Количество фрагментов:")
        row1.addWidget(self.lbl_count)
        self.spin_slices = QSpinBox();
        self.spin_slices.setRange(2, 99);
        self.spin_slices.setValue(8)
        row1.addWidget(self.spin_slices)
        row1.addStretch(1)
        v.addLayout(row1)

        # ---- строка "Высота (px)" для режима "По высоте"
        row1h = QHBoxLayout()
        self.lbl_height = QLabel("Высота (px):")
        self.spin_height = QSpinBox()
        self.spin_height.setRange(100, 30000)
        self.spin_height.setSingleStep(50)
        self.spin_height.setValue(2000)
        row1h.addWidget(self.lbl_height)
        row1h.addWidget(self.spin_height)
        row1h.addStretch(1)
        v.addLayout(row1h)

        # по умолчанию высота скрыта (активен режим по количеству)
        self.lbl_height.setVisible(False)
        self.spin_height.setVisible(False)

        # ---- чекбокс под спинбоксом
        row1b = QHBoxLayout()
        self.chk_show_labels = QCheckBox("Показывать разрешение")
        self.chk_show_labels.setChecked(True)
        QTimer.singleShot(0, self._apply_settings_from_ini)
        row1b.addWidget(self.chk_show_labels)
        row1b.addStretch(1)
        v.addLayout(row1b)

        row_threads = QHBoxLayout()
        self.chk_auto_threads = QCheckBox("Авто потоки")
        self.chk_auto_threads.setChecked(True)
        self.spin_threads = QSpinBox();
        self.spin_threads.setRange(1, 64);
        self.spin_threads.setValue(6)
        self.spin_threads.setEnabled(False)
        row_threads.addWidget(self.chk_auto_threads)
        row_threads.addWidget(QLabel("Потоки:"))
        row_threads.addWidget(self.spin_threads)
        row_threads.addStretch(1)
        v.addLayout(row_threads)

        # биндинги и включение/выключение поля
        self.chk_auto_threads.toggled.connect(lambda on: self.spin_threads.setEnabled(not on))
        self.chk_auto_threads.toggled.connect(lambda v: self._save_bool_ini("auto_threads", v))
        self.spin_threads.valueChanged.connect(lambda v: self._save_int_ini("threads", v))

        # ---- строка с одной кнопкой-переключателем
        row2 = QHBoxLayout(); row2.addStretch(1)
        self.btn_toggle = QPushButton("Вкл")
        self.btn_toggle.setCheckable(True)
        self.btn_toggle.setChecked(False)  # по умолчанию выкл
        self.btn_save = QPushButton("Сохранить нарезку")
        row2.addWidget(self.btn_toggle)
        row2.addWidget(self.btn_save)
        v.addLayout(row2)

        # Подсказка
        help_text = ("Чтобы поменять высоту фрагментов, зажмите ПКМ")
        lbl = QLabel(help_text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size: 12px; color: #666;")
        v.addWidget(lbl)

        # signals
        if self._preview:
            # единая кнопка
            self.btn_toggle.toggled.connect(self._on_toggle)

            # изменения количества — сразу в превью, если режим активен
            self.spin_slices.valueChanged.connect(self._on_count_changed)
            self.spin_slices.valueChanged.connect(lambda v: self._save_int_ini("slices", v))

            self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)

            self.spin_height.valueChanged.connect(self._on_height_changed)
            self.spin_height.valueChanged.connect(lambda v: self._save_int_ini("height_px", v))

            # сохранение
            self.btn_save.clicked.connect(self._save)

            # показа/скрытия бейджей — мгновенная перерисовка
            self.chk_show_labels.toggled.connect(self._preview.label.set_show_slice_labels)
            self.chk_show_labels.toggled.connect(lambda v: self._save_bool_ini("show_labels", v))

            # (опционально) синхронизировать кнопку с текущим состоянием превью
            if getattr(self._preview, "_slice_enabled", False):
                self.btn_toggle.setChecked(True)
                self.btn_toggle.setText("Выкл")
            else:
                self.btn_toggle.setChecked(False)
                self.btn_toggle.setText("Вкл")

    # ---- новые/обновлённые методы ----
    def _current_slice_by(self) -> str:
        # "count" или "height"
        return "count" if self.combo_mode.currentIndex() == 0 else "height"

    def _on_mode_changed(self, idx: int):
        by = self._current_slice_by()
        show_count = (by == "count")

        # показываем нужный блок
        self.lbl_count.setVisible(show_count)
        self.spin_slices.setVisible(show_count)
        self.lbl_height.setVisible(not show_count)
        self.spin_height.setVisible(not show_count)

        # сохранить в ini (как строку)
        self._save_str_ini("slice_by", by)

        # если режим уже включён — пересчитать превью
        if self._preview and getattr(self._preview, "_slice_enabled", False):
            if by == "count":
                self._preview.set_slice_by("count")
                self._preview.set_slice_count(int(self.spin_slices.value()))
            else:
                self._preview.set_slice_by("height")
                self._preview.set_slice_height(int(self.spin_height.value()))

    def _on_height_changed(self, v: int):
        if not self._preview:
            return
        if getattr(self._preview, "_slice_enabled", False) and self._current_slice_by() == "height":
            self._preview.set_slice_height(int(v))
    def reset_to_defaults(self):
        defaults = dict(
            slices=8,
            height_px=2000,
            slice_by="count",
            show_labels=True,
            auto_threads=True,
            threads=6,
        )

        # временно снимаем сигналы, чтобы не сработали биндинги сохранения
        try:
            if hasattr(self, "chk_auto_threads"):
                self.chk_auto_threads.toggled.disconnect()
            if hasattr(self, "spin_threads"):
                self.spin_threads.valueChanged.disconnect()
        except Exception:
            pass
        if hasattr(self, "spin_height"):
            self.spin_height.setValue(defaults["height_px"])
        if hasattr(self, "combo_mode"):
            self.combo_mode.setCurrentIndex(0 if defaults["slice_by"] == "count" else 1)
        if hasattr(self, "spin_slices"):
            self.spin_slices.setValue(defaults["slices"])
        if hasattr(self, "chk_show_labels"):
            self.chk_show_labels.setChecked(defaults["show_labels"])

        if hasattr(self, "chk_auto_threads"):
            self.chk_auto_threads.setChecked(defaults["auto_threads"])
        if hasattr(self, "spin_threads"):
            self.spin_threads.setValue(defaults["threads"])
            # включаем/выключаем в соответствии с авто-режимом
            self.spin_threads.setEnabled(not defaults["auto_threads"])

        # сохранить в INI
        self._save_int_ini("slices", defaults["slices"])
        self._save_bool_ini("show_labels", defaults["show_labels"])
        self._save_bool_ini("auto_threads", defaults["auto_threads"])
        self._save_int_ini("threads", defaults["threads"])
        self._save_int_ini("height_px", defaults["height_px"])
        self._save_str_ini("slice_by", defaults["slice_by"])

        try:
            if hasattr(self, "chk_auto_threads"):
                self.chk_auto_threads.toggled.connect(lambda v: self._save_bool_ini("auto_threads", v))
                # чтобы UI сразу блокировал/разблокировал спин:
                self.chk_auto_threads.toggled.connect(lambda on: self.spin_threads.setEnabled(not on))
            if hasattr(self, "spin_threads"):
                self.spin_threads.valueChanged.connect(lambda v: self._save_int_ini("threads", v))
        except Exception:
            pass

        try:
            if hasattr(self, "_on_count_changed"):
                self._on_count_changed(defaults["slices"])
            if hasattr(self, "_preview") and self._preview:
                if hasattr(self._preview, "label"):
                    self._preview.label.set_show_slice_labels(defaults["show_labels"])
        except Exception:
            pass

    def _save_str_ini(self, key: str, value: str):
        try:
            shadow_attr = f"__{key}__shadow"
            setattr(self, shadow_attr, value)
            with group("CutSection"):
                from smithanatool_qt.settings_bind import save_attr_string
                save_attr_string(self, shadow_attr, key)
        except Exception:
            pass

    def _save_int_ini(self, key: str, value: int):
        self._save_str_ini(key, str(int(value)))

    def _save_bool_ini(self, key: str, value: bool):
        self._save_str_ini(key, "1" if value else "0")

    def _on_toggle(self, checked: bool):
        if not self._preview:
            return
        if checked:
            self.btn_toggle.setText("Выкл")
            by = self._current_slice_by()
            if by == "count":
                self._preview.set_slice_by("count")
                self._preview.set_slice_mode(True, self.spin_slices.value())
            else:
                by = self._current_slice_by()
                self._preview.set_slice_mode(True)  # 1) включили
                if by == "count":
                    self._preview.set_slice_by("count")  # 2) задали режим
                    self._preview.set_slice_count(self.spin_slices.value())  # 3) параметр
                else:
                    self._preview.set_slice_by("height")
                    self._preview.set_slice_height(self.spin_height.value())
        else:
            self.btn_toggle.setText("Вкл")
            self._preview.set_slice_mode(False)

    def _on_count_changed(self, v: int):
        if not self._preview:
            return
        if getattr(self._preview, "_slice_enabled", False):
            self._preview.set_slice_count(int(v))

    def _enable(self):
        if not self._preview:
            return
        by = self._current_slice_by()
        if by == "count":
            self._preview.set_slice_by("count")
            self._preview.set_slice_mode(True, self.spin_slices.value())
        else:
            by = self._current_slice_by()
            self._preview.set_slice_mode(True)
            if by == "count":
                self._preview.set_slice_by("count")
                self._preview.set_slice_count(self.spin_slices.value())
            else:
                self._preview.set_slice_by("height")
                self._preview.set_slice_height(self.spin_height.value())

    def _disable(self):
        if not self._preview: return
        self._preview.set_slice_mode(False)

    def _save(self):
        if not self._preview or not getattr(self._preview, "_slice_enabled", False):
            QMessageBox.warning(self, "Нарезка", "Сначала включите режим нарезки (Вкл).")
            return
        out_dir = QFileDialog.getExistingDirectory(self, "Папка для сохранения фрагментов")
        if not out_dir: return

        auto_threads = bool(self.chk_auto_threads.isChecked())
        threads = int(self.spin_threads.value())

        dlg = QProgressDialog("Сохраняю фрагменты…", None, 0, 0, self)
        dlg.setWindowTitle("Сохранение");
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setCancelButton(None);
        dlg.setMinimumDuration(0);
        dlg.show()
        QApplication.processEvents()
        try:
            # обновлённая сигнатура:
            count = self._preview.save_slices(out_dir, threads=threads, auto_threads=auto_threads)
        finally:
            dlg.close()
        if count > 0:
            box = QMessageBox(self);
            box.setWindowTitle("Готово");
            box.setText(f"Сохранено фрагментов: {count}")
            btn_open = box.addButton("Открыть папку", QMessageBox.ActionRole)
            box.addButton(QMessageBox.Ok);
            box.exec()
            if box.clickedButton() is btn_open: _open_in_explorer(out_dir)
        else:
            QMessageBox.information(self, "Нарезка", "Нет фрагментов для сохранения.")

    def _apply_settings_from_ini(self):
        from smithanatool_qt.settings_bind import group, bind_spinbox, bind_checkbox
        with group("CutSection"):
            bind_spinbox(self.spin_slices, "slices", 8)
            bind_spinbox(self.spin_height, "height_px", 2000)  # ← добавили
            bind_checkbox(self.chk_show_labels, "show_labels", True)
            bind_checkbox(self.chk_auto_threads, "auto_threads", True)
            bind_spinbox(self.spin_threads, "threads", 4)
            self.spin_threads.setEnabled(not self.chk_auto_threads.isChecked())

            # попытаться восстановить режим (если раньше сохраняли self._save_str_ini("slice_by", ...))
            try:
                val = getattr(self, "__slice_by__shadow", None)
                if val:
                    self.combo_mode.setCurrentIndex(0 if val == "count" else 1)
            except Exception:
                pass
        with group("CutSection"):
            bind_line_edit(self._slice_by_le, "slice_by", "count")

        by = (self._slice_by_le.text() or "count").strip()
        self.combo_mode.setCurrentIndex(0 if by == "count" else 1)
        self._on_mode_changed(self.combo_mode.currentIndex())



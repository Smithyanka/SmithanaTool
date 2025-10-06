
from __future__ import annotations
import os, sys, subprocess
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QPushButton,
    QFileDialog, QMessageBox, QProgressDialog, QApplication, QCheckBox, QComboBox, QLineEdit
)
from PySide6.QtCore import Qt, QTimer
from smithanatool_qt.settings_bind import group

from smithanatool_qt.tabs.common.bind import apply_bindings
from smithanatool_qt.tabs.common.defaults import DEFAULTS


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
    def __init__(self, preview=None, parent=None, paths_provider=None):
        super().__init__(parent)
        self._preview = preview
        self._paths_provider = paths_provider
        self._slice_by_le = QLineEdit(self)
        self._slice_by_le.setVisible(False)
        self._cut_out_dir_le = QLineEdit(self)
        self._cut_out_dir_le.setVisible(False)
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
        self.spin_height.setFixedWidth(55)
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

        self.lbl_threads = QLabel("Потоки:")
        self.spin_threads = QSpinBox()
        self.spin_threads.setRange(1, 64)
        self.spin_threads.setValue(6)

        row_threads.addWidget(self.chk_auto_threads)
        row_threads.addWidget(self.lbl_threads)
        row_threads.addWidget(self.spin_threads)
        row_threads.addStretch(1)
        v.addLayout(row_threads)

        # синхронизация состояния
        def _set_threads_enabled(auto_on: bool):
            on = not auto_on
            self.spin_threads.setEnabled(on)
            self.lbl_threads.setEnabled(on)

        _set_threads_enabled(self.chk_auto_threads.isChecked())


        # биндинги и включение/выключение поля
        self.chk_auto_threads.toggled.connect(_set_threads_enabled)


        if self._preview:
            self._preview.currentPathChanged.connect(self._on_preview_path_changed)
            self._preview.sliceCountChanged.connect(self._on_preview_slice_count_changed)

        # ---- строка с одной кнопкой-переключателем
        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 8, 0, 0)
        row2.addStretch(1)
        self.btn_toggle = QPushButton("Вкл")
        self.btn_toggle.setMinimumWidth(60)
        self.btn_toggle.setCheckable(True)
        self.btn_toggle.setChecked(False)  # по умолчанию выкл
        self.btn_save = QPushButton("Нарезать выделенные")
        row2.addWidget(self.btn_toggle)
        row2.addWidget(self.btn_save)
        v.addLayout(row2)

        # Подсказка
        help_text = ("Чтобы поменять высоту фрагментов, зажмите ПКМ")
        lbl = QLabel(help_text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size: 12px; color: #454545;")
        v.addWidget(lbl)

        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        # signals
        if self._preview:
            # единая кнопка
            self.btn_toggle.toggled.connect(self._on_toggle)

            # изменения количества — сразу в превью, если режим активен
            self.spin_slices.valueChanged.connect(self._on_count_changed)



            self.spin_height.valueChanged.connect(self._on_height_changed)

            # сохранение
            self.btn_save.clicked.connect(self._batch_cut_selected)

            # показа/скрытия бейджей — мгновенная перерисовка
            self.chk_show_labels.toggled.connect(self._preview.label.set_show_slice_labels)

            # (опционально) синхронизировать кнопку с текущим состоянием превью
            if getattr(self._preview, "_slice_enabled", False):
                self.btn_toggle.setChecked(True)
                self.btn_toggle.setText("Выкл")
            else:
                self.btn_toggle.setChecked(False)
                self.btn_toggle.setText("Вкл")

    def _ini_load_str(self, key: str, default: str = "") -> str:
        try:
            shadow_attr = f"__{key}__shadow"
            setattr(self, shadow_attr, default)
            with group("CutSection"):
                from smithanatool_qt.settings_bind import bind_attr_string
                bind_attr_string(self, shadow_attr, key, default)
            return getattr(self, shadow_attr, default)
        except Exception:
            return default
    def _on_preview_slice_count_changed(self, n: int):
        # Обновляем UI, но без обратного вызова _on_count_changed
        try:
            self.spin_slices.blockSignals(True)
            # Если хочешь, чтобы спинбокс мог показывать и 1 фрагмент — см. комментарий ниже.
            self.spin_slices.setValue(max(self.spin_slices.minimum(), n))
        finally:
            self.spin_slices.blockSignals(False)
        # Сохраним в INI, чтобы новое значение не потерялось
        self._save_int_ini("slices", int(self.spin_slices.value()))

    def _on_preview_path_changed(self, path: str):
        # было: синхронизация кнопки
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
            self.spin_slices.setValue(max(self.spin_slices.minimum(),
                                          min(self.spin_slices.maximum(), count)))
            self.spin_height.setValue(max(self.spin_height.minimum(),
                                          min(self.spin_height.maximum(), height_px)))
        finally:
            self.combo_mode.blockSignals(False)
            self.spin_slices.blockSignals(False)
            self.spin_height.blockSignals(False)

        # Обновить видимость «Количество/Высота»
        self._on_mode_changed(self.combo_mode.currentIndex())

    def _selected_paths(self) -> list[str]:
        if callable(getattr(self, "_paths_provider", None)):
            try:
                paths = list(self._paths_provider() or [])
                return [p for p in paths if isinstance(p, str) and p]
            except Exception:
                pass
        # фолбэк — только текущий файл из превью
        cur = getattr(self._preview, "_current_path", None) if self._preview else None
        return [cur] if cur else []

    def _batch_cut_selected(self):
        if not self._preview:
            QMessageBox.warning(self, "Нарезка", "Нет панели предпросмотра.")
            return

        paths = self._selected_paths()
        if not paths:
            QMessageBox.information(self, "Нарезка", "Не выбрано ни одного файла.")
            return

        start_out = (self._cut_out_dir_le.text() or os.path.expanduser("~"))
        out_dir = QFileDialog.getExistingDirectory(self, "Папка для сохранения фрагментов", start_out)
        if not out_dir:
            return

        self._cut_out_dir_le.setText(out_dir)
        self._save_str_ini("cut_out_dir", out_dir)

        auto_threads = bool(self.chk_auto_threads.isChecked())
        threads = int(self.spin_threads.value())

        dlg = QProgressDialog("Режу выделенные файлы…", None, 0, 0, self)
        dlg.setWindowTitle("Нарезка");
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setCancelButton(None);
        dlg.setMinimumDuration(0)
        dlg.show();
        QApplication.processEvents()

        total_saved = 0
        skipped: list[str] = []
        current_before = getattr(self._preview, "_current_path", None)

        try:
            for p in paths:
                try:
                    # показать файл (это автоматически сохранит состояние предыдущего и восстановит p)
                    self._preview.show_path(p)

                    # если для p нарезка выключена и нет валидных границ, пробуем построить по режиму
                    st = self._preview.get_slice_state()
                    # РЕЖЕМ ТОЛЬКО ЕСЛИ ДЛЯ ЭТОГО ФАЙЛА БЫЛО НАЖАТО "Вкл"
                    if not bool(st.get("enabled")):
                        skipped.append(p)
                        continue

                    bounds = list(st.get("bounds") or [])
                    if len(bounds) < 2:
                        skipped.append(p)
                        continue

                    saved = self._preview.save_slices(out_dir, threads=threads, auto_threads=auto_threads)
                    total_saved += int(saved or 0)
                except Exception:
                    skipped.append(p)
        finally:
            dlg.close()
            # вернём прежний файл в предпросмотр
            try:
                if current_before:
                    self._preview.show_path(current_before)
            except Exception:
                pass

        # итог
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
            _open_in_explorer(out_dir)


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

        # Если режим «По высоте» включён — перестроить превью через API миксина
        if getattr(self._preview, "_slice_enabled", False) and self._current_slice_by() == "height":
            self._preview.set_slice_height(int(v))
        else:
            # Режим не активен — просто обновим пер-файловое значение
            try:
                self._preview._slice_height_px = int(v)
            except Exception:
                pass

        # В любом случае: зафиксировать новое значение в пер-файловом слепке
        try:
            cur = getattr(self._preview, "_current_path", None)
            self._preview._store_slice_state(cur)
        except Exception:
            pass
    def reset_to_defaults(self):
        defaults = dict(
            slices=8,
            height_px=2000,
            slice_by="count",
            show_labels=True,
            auto_threads=True,
            threads=6,
        )

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

        if hasattr(self, "lbl_threads"):
            self.lbl_threads.setEnabled(not defaults["auto_threads"])

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
        self.btn_toggle.setText("Выкл" if checked else "Вкл")
        if not checked:
            self._preview.set_slice_mode(False);
            return
        by = self._current_slice_by()
        self._preview.set_slice_by(by)
        if by == "count":
            self._preview.set_slice_mode(True, int(self.spin_slices.value()))
        else:
            self._preview.set_slice_mode(True)
            self._preview.set_slice_height(int(self.spin_height.value()))

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
        start_out = (self._cut_out_dir_le.text() or os.path.expanduser("~"))
        out_dir = QFileDialog.getExistingDirectory(self, "Папка для сохранения фрагментов", start_out)
        if not out_dir:
            return
        self._cut_out_dir_le.setText(out_dir)
        self._save_str_ini("cut_out_dir", out_dir)

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
        apply_bindings(self, "CutSection", [
            (self.chk_show_labels, "show_labels", True),
            (self.spin_slices, "slices", 8),
            (self.spin_height, "height_px", 2000),

            # потоки — единые дефолты
            (self.chk_auto_threads, "auto_threads", DEFAULTS["auto_threads"]),
            (self.spin_threads, "threads", DEFAULTS["threads"]),

            # директория сохранения (скрытое поле)
            (self._cut_out_dir_le, "cut_out_dir", DEFAULTS["cut_out_dir"]),
        ])
        by = self._ini_load_str("slice_by", "count")
        self.combo_mode.setCurrentIndex(0 if by == "count" else 1)
        self._on_mode_changed(self.combo_mode.currentIndex())



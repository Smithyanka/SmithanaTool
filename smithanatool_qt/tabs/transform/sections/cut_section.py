
from __future__ import annotations
import os, sys, subprocess
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QPushButton,
    QFileDialog, QMessageBox, QProgressDialog, QApplication, QCheckBox
)
from PySide6.QtCore import Qt

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

        v = QVBoxLayout(self); v.setAlignment(Qt.AlignTop)

        # ---- строка с количеством фрагментов
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Количество фрагментов:"))
        self.spin_slices = QSpinBox(); self.spin_slices.setRange(2, 99); self.spin_slices.setValue(8)
        row1.addWidget(self.spin_slices)
        row1.addStretch(1)  # ← оставляем только один stretch
        v.addLayout(row1)

        # ---- чекбокс под спинбоксом
        row1b = QHBoxLayout()
        self.chk_show_labels = QCheckBox("Показывать разрешение")
        self.chk_show_labels.setChecked(True)
        row1b.addWidget(self.chk_show_labels)
        row1b.addStretch(1)
        v.addLayout(row1b)

        # ---- строка с одной кнопкой-переключателем
        row2 = QHBoxLayout(); row2.addStretch(1)
        self.btn_toggle = QPushButton("Вкл")
        self.btn_toggle.setCheckable(True)
        self.btn_toggle.setChecked(False)  # по умолчанию выкл
        self.btn_save = QPushButton("Сохранить нарезку...")
        row2.addWidget(self.btn_toggle)
        row2.addWidget(self.btn_save)
        v.addLayout(row2)

        # Подсказка
        help_text = ("Чтобы поменять высоту области, нажмите ПКМ")
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

            # сохранение
            self.btn_save.clicked.connect(self._save)

            # показа/скрытия бейджей — мгновенная перерисовка
            self.chk_show_labels.toggled.connect(self._preview.label.set_show_slice_labels)

            # (опционально) синхронизировать кнопку с текущим состоянием превью
            if getattr(self._preview, "_slice_enabled", False):
                self.btn_toggle.setChecked(True)
                self.btn_toggle.setText("Выкл")
            else:
                self.btn_toggle.setChecked(False)
                self.btn_toggle.setText("Вкл")

    # ---- новые/обновлённые методы ----
    def _on_toggle(self, checked: bool):
        if not self._preview:
            return
        if checked:
            self.btn_toggle.setText("Выкл")
            self._preview.set_slice_mode(True, self.spin_slices.value())
        else:
            self.btn_toggle.setText("Вкл")
            self._preview.set_slice_mode(False)

    def _on_count_changed(self, v: int):
        if not self._preview:
            return
        if getattr(self._preview, "_slice_enabled", False):
            self._preview.set_slice_count(int(v))

    def _enable(self):
        if not self._preview: return
        self._preview.set_slice_mode(True, self.spin_slices.value())

    def _disable(self):
        if not self._preview: return
        self._preview.set_slice_mode(False)


    def _save(self):
        if not self._preview or not getattr(self._preview, "_slice_enabled", False):
            QMessageBox.warning(self, "Нарезка", "Сначала включите режим нарезки (Вкл).")
            return
        out_dir = QFileDialog.getExistingDirectory(self, "Папка для сохранения фрагментов")
        if not out_dir: return
        dlg = QProgressDialog("Сохраняю фрагменты…", None, 0, 0, self)
        dlg.setWindowTitle("Сохранение"); dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setCancelButton(None); dlg.setMinimumDuration(0); dlg.show()
        QApplication.processEvents()
        try:
            count = self._preview.save_slices(out_dir)
        finally:
            dlg.close()
        if count > 0:
            box = QMessageBox(self); box.setWindowTitle("Готово"); box.setText(f"Сохранено фрагментов: {count}")
            btn_open = box.addButton("Открыть папку", QMessageBox.ActionRole)
            box.addButton(QMessageBox.Ok); box.exec()
            if box.clickedButton() is btn_open: _open_in_explorer(out_dir)
        else:
            QMessageBox.information(self, "Нарезка", "Нет фрагментов для сохранения.")

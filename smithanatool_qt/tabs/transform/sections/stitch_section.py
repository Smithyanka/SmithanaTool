
from __future__ import annotations
import os, sys, subprocess
from typing import List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSpinBox, QCheckBox,
    QPushButton, QGroupBox, QFileDialog, QMessageBox, QProgressDialog, QApplication
)
from PySide6.QtCore import Qt
from ..stitcher import load_images, merge_vertical, merge_horizontal, save_png

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

class StitchSection(QWidget):
    def __init__(self, gallery=None, parent=None):
        super().__init__(parent)
        self._gallery = gallery

        v = QVBoxLayout(self); v.setAlignment(Qt.AlignTop)

        # Направление
        row_dir = QHBoxLayout()
        row_dir.addWidget(QLabel("Направление склейки:"))
        self.cmb_dir = QComboBox(); self.cmb_dir.addItems(["По вертикали", "По горизонтали"])
        row_dir.addWidget(self.cmb_dir); row_dir.addStretch(1)
        v.addLayout(row_dir)

        # Размер
        grp_dim = QGroupBox("Размер")
        row_dim = QHBoxLayout(grp_dim)
        self.chk_no_resize = QCheckBox("Не изменять ширину")
        self.lbl_dim = QLabel("Ширина:")
        self.spin_dim = QSpinBox(); self.spin_dim.setRange(50, 20000); self.spin_dim.setValue(800)
        row_dim.addWidget(self.chk_no_resize); row_dim.addSpacing(8)
        row_dim.addWidget(self.lbl_dim); row_dim.addWidget(self.spin_dim); row_dim.addStretch(1)
        v.addWidget(grp_dim)

        # PNG-опции
        grp_png = QGroupBox("Опции PNG")
        v_png = QVBoxLayout(grp_png)

        # строка 1 — оптимизация + уровень сжатия
        row_png1 = QHBoxLayout()
        self.chk_opt = QCheckBox("Оптимизировать PNG")
        self.chk_opt.setChecked(True)
        self.spin_compress = QSpinBox()
        self.spin_compress.setRange(0, 9)
        self.spin_compress.setValue(6)
        row_png1.addWidget(self.chk_opt)
        row_png1.addSpacing(12)
        row_png1.addWidget(QLabel("Уровень сжатия (0–9):"))
        row_png1.addWidget(self.spin_compress)
        row_png1.addStretch(1)
        v_png.addLayout(row_png1)

        # строка 2 — удаление метаданных
        row_png2 = QHBoxLayout()
        self.chk_strip = QCheckBox("Удалять метаданные")
        self.chk_strip.setChecked(True)
        row_png2.addWidget(self.chk_strip)
        row_png2.addStretch(1)
        v_png.addLayout(row_png2)

        v.addWidget(grp_png)

        # Склейка по одной
        grp_one = QGroupBox("Склейка по одной")
        row_one = QHBoxLayout(grp_one); row_one.addStretch(1)
        self.btn_one = QPushButton("Склейка в один PNG")
        self.btn_one_pick = QPushButton("Выбрать файлы…")
        row_one.addWidget(self.btn_one); row_one.addWidget(self.btn_one_pick)
        v.addWidget(grp_one)

        # Автосклейка
        grp_auto = QGroupBox("Автосклейка")
        av = QVBoxLayout(grp_auto)
        row_a1 = QHBoxLayout()
        row_a1.addWidget(QLabel("По сколько клеить:"))
        self.spin_group = QSpinBox(); self.spin_group.setRange(2, 999); self.spin_group.setValue(12)
        row_a1.addWidget(self.spin_group); row_a1.addSpacing(16)
        row_a1.addWidget(QLabel("Нули:"))
        self.spin_zeros = QSpinBox(); self.spin_zeros.setRange(1, 6); self.spin_zeros.setValue(2)
        row_a1.addWidget(self.spin_zeros); row_a1.addStretch(1)
        av.addLayout(row_a1)
        row_a2 = QHBoxLayout(); row_a2.addStretch(1)
        self.btn_auto = QPushButton("Склеить выбранные")
        self.btn_auto_pick = QPushButton("Выбрать файлы…")
        row_a2.addWidget(self.btn_auto); row_a2.addWidget(self.btn_auto_pick)
        av.addLayout(row_a2)
        v.addWidget(grp_auto)

        # defaults + сигналы
        self.chk_no_resize.setChecked(True)
        self._update_dim_label()
        self.cmb_dir.currentIndexChanged.connect(self._update_dim_label)
        self.chk_no_resize.toggled.connect(self._apply_dim_state)
        self.btn_one.clicked.connect(self._do_stitch_one)
        self.btn_one_pick.clicked.connect(self._do_stitch_one_pick)
        self.btn_auto.clicked.connect(self._do_stitch_auto)
        self.btn_auto_pick.clicked.connect(self._do_stitch_auto_pick)
        self._apply_dim_state()

    # helpers
    def _update_dim_label(self):
        if self.cmb_dir.currentText() == "По вертикали":
            self.lbl_dim.setText("Ширина:")
            self.chk_no_resize.setText("Не изменять ширину")
        else:
            self.lbl_dim.setText("Высота:")
            self.chk_no_resize.setText("Не изменять высоту")

    def _apply_dim_state(self):
        self.spin_dim.setEnabled(not self.chk_no_resize.isChecked())

    def _ask_selected_paths(self) -> List[str]:
        if self._gallery and hasattr(self._gallery, 'selected_files'):
            sel = self._gallery.selected_files()
            if sel: return sel
        if self._gallery and hasattr(self._gallery, 'files'):
            return self._gallery.files()
        return []

    def _build_output_params(self):
        direction = self.cmb_dir.currentText()
        no_resize = self.chk_no_resize.isChecked()
        dim_val = None if no_resize else int(self.spin_dim.value())
        optimize = self.chk_opt.isChecked()
        compress = int(self.spin_compress.value())
        strip = self.chk_strip.isChecked()
        return direction, dim_val, optimize, compress, strip

    # actions
    def _do_stitch_one(self):
        paths = self._ask_selected_paths()
        if len(paths) < 2:
            QMessageBox.warning(self, "Склейка", "Выберите минимум два изображения в галерее или используйте «Выбрать файлы…».")
            return
        out_path, out_dir = self._stitch_and_save_single(paths)
        if out_path:
            self._show_done_box(out_dir, f"Сохранено: {os.path.basename(out_path)}")

    def _do_stitch_one_pick(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Выберите изображения", "", "Изображения (*.png *.jpg *.jpeg *.bmp *.webp)")
        if len(files) < 2: return
        out_path, _ = QFileDialog.getSaveFileName(self, "Сохранить как", "result.png", "PNG (*.png)")
        if not out_path: return
        if not out_path.lower().endswith(".png"): out_path += ".png"
        out_path2, out_dir2 = self._stitch_and_save_single(files, out_path)
        if out_path2:
            self._show_done_box(out_dir2, f"Сохранено: {os.path.basename(out_path2)}")

    def _stitch_and_save_single(self, paths: List[str], direct_out_path: str | None = None):
        dlg = QProgressDialog("Сохраняю…", None, 0, 0, self)
        dlg.setWindowTitle("Сохранение"); dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setCancelButton(None); dlg.setMinimumDuration(0); dlg.setAutoClose(False); dlg.show()
        QApplication.processEvents()

        direction, dim_val, optimize, compress, strip = self._build_output_params()
        imgs = load_images(paths)
        try:
            if direction == "По вертикали":
                img = merge_vertical(imgs, target_width=dim_val)
            else:
                img = merge_horizontal(imgs, target_height=dim_val)
        except Exception as e:
            dlg.close(); QMessageBox.critical(self, "Склейка", f"Ошибка при склейке: {e}"); return None, None

        if direct_out_path:
            out_path = direct_out_path
        else:
            out_path, _ = QFileDialog.getSaveFileName(self, "Сохранить как", "01.png", "PNG (*.png)")
            if not out_path: dlg.close(); return None, None
            if not out_path.lower().endswith('.png'): out_path += '.png'

        try:
            save_png(img, out_path, optimize=optimize, compress_level=compress, strip_metadata=strip)
        except Exception as e:
            dlg.close(); QMessageBox.critical(self, "Сохранение", f"Не удалось сохранить PNG: {e}"); return None, None

        dlg.close()
        return out_path, os.path.dirname(out_path)

    def _do_stitch_auto(self):
        paths = self._ask_selected_paths()
        if len(paths) < 2:
            QMessageBox.warning(self, "Автосклейка", "Выберите минимум два изображения или используйте «Выбрать файлы…».")
            return
        out_dir = QFileDialog.getExistingDirectory(self, "Выберите папку для сохранения")
        if not out_dir: return
        count = self._stitch_and_save_groups(paths, out_dir)
        if count > 0: self._show_done_box(out_dir, f"Файлов сохранено: {count}")

    def _do_stitch_auto_pick(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Выберите изображения", "", "Изображения (*.png *.jpg *.jpeg *.bmp *.webp)")
        if len(files) < 2: return
        out_dir = QFileDialog.getExistingDirectory(self, "Папка для сохранения PNG")
        if not out_dir: return
        count = self._stitch_and_save_groups(files, out_dir)
        if count > 0: self._show_done_box(out_dir, f"Файлов сохранено: {count}")

    def _stitch_and_save_groups(self, paths: List[str], out_dir: str) -> int:
        group = int(self.spin_group.value())
        zeros = int(self.spin_zeros.value())
        direction, dim_val, optimize, compress, strip = self._build_output_params()

        total = max(1, (len(paths) + group - 1) // group)
        prog = QProgressDialog("Сохраняю…", None, 0, total, self)
        prog.setWindowTitle("Сохранение"); prog.setWindowModality(Qt.ApplicationModal)
        prog.setCancelButton(None); prog.setMinimumDuration(0); prog.setAutoClose(False); prog.show()
        QApplication.processEvents()

        made = 0; i = 0
        while i < len(paths):
            chunk = paths[i:i+group]
            imgs = load_images(chunk)
            if not imgs:
                cur = min(total, (i // group) + 1); prog.setValue(cur); QApplication.processEvents(); i += group; continue
            try:
                if direction == "По вертикали":
                    merged = merge_vertical(imgs, target_width=dim_val)
                else:
                    merged = merge_horizontal(imgs, target_height=dim_val)
            except Exception as e:
                QMessageBox.warning(self, "Автосклейка", f"Пропущена группа {i//group+1}: {e}")
                cur = min(total, (i // group) + 1); prog.setValue(cur); QApplication.processEvents(); i += group; continue

            fname = f"{(i//group)+1:0{zeros}d}.png"
            out_path = os.path.join(out_dir, fname)
            try:
                save_png(merged, out_path, optimize=optimize, compress_level=compress, strip_metadata=strip)
                made += 1
            except Exception as e:
                QMessageBox.warning(self, "Сохранение", f"Не удалось сохранить {fname}: {e}")

            cur = min(total, (i // group) + 1); prog.setValue(cur); QApplication.processEvents(); i += group

        prog.close()
        return made

    def _show_done_box(self, out_dir: str, message: str):
        box = QMessageBox(self); box.setWindowTitle("Готово"); box.setText(message)
        btn_open = box.addButton("Открыть папку", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok); box.exec()
        if box.clickedButton() is btn_open: _open_in_explorer(out_dir)

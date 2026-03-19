from __future__ import annotations
import os, sys, subprocess
from typing import List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSpinBox, QCheckBox,
    QPushButton, QGroupBox, QFileDialog, QMessageBox, QProgressDialog, QApplication,
    QLineEdit, QRadioButton, QButtonGroup
)
from PySide6.QtCore import Qt, QTimer
from smithanatool_qt.tabs.transform.core.stitcher import load_images, merge_vertical, merge_horizontal, save_png


from concurrent.futures import ThreadPoolExecutor

from smithanatool_qt.tabs.common.bind import (
    apply_bindings, reset_bindings,
    ini_load_str, ini_save_str
)
from smithanatool_qt.tabs.common.defaults import DEFAULTS

from PySide6.QtGui import QImageReader
try:
    from ..preview.utils import memory_image_for
except Exception:
    memory_image_for = None

from ..utils.fs import open_in_explorer


class StitchSection(QWidget):
    def __init__(self, gallery=None, parent=None):
        super().__init__(parent)
        self._gallery = gallery

        self._executor = ThreadPoolExecutor(
            max_workers=max(2, min(32, (os.cpu_count() or 4) - 1))
        )

        v = QVBoxLayout(self)
        v.setAlignment(Qt.AlignTop)

        self._save_dir_le = QLineEdit(self)
        self._save_dir_le.setVisible(False)  # stitch_out_dir
        self._save_file_dir_le = QLineEdit(self)
        self._save_file_dir_le.setVisible(False)  # stitch_save_dir
        self._pick_dir_le = QLineEdit(self)
        self._pick_dir_le.setVisible(False)  # stitch_pick_dir
        self._auto_pick_dir_le = QLineEdit(self)
        self._auto_pick_dir_le.setVisible(False)  # stitch_auto_pick_dir

        self._group_by_le = QLineEdit(self)
        self._group_by_le.setVisible(False)  # group_by

        self._stitch_mode_le = QLineEdit(self)
        self._stitch_mode_le.setVisible(False)  # stitch_mode

        # Настройки
        grp_dim = QGroupBox("Настройки")
        v_dim = QVBoxLayout(grp_dim)
        v_dim.setSpacing(8)

        row_dir = QHBoxLayout()
        row_dir.addWidget(QLabel("Направление склейки:"))
        self.cmb_dir = QComboBox()
        self.cmb_dir.addItems(["По вертикали", "По горизонтали"])
        row_dir.addWidget(self.cmb_dir)
        row_dir.addStretch(1)
        v_dim.addLayout(row_dir)

        row_dim = QHBoxLayout()
        self.chk_no_resize = QCheckBox("Не изменять ширину")
        self.lbl_dim = QLabel("Ширина:")
        self.spin_dim = QSpinBox()
        self.spin_dim.setRange(50, 20000)
        self.spin_dim.setValue(800)

        row_dim.addWidget(self.chk_no_resize)
        row_dim.addSpacing(8)
        row_dim.addWidget(self.lbl_dim)
        row_dim.addWidget(self.spin_dim)
        row_dim.addStretch(1)
        v_dim.addLayout(row_dim)

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
        self.lbl_compress = QLabel("Уровень сжатия (0–9):")
        row_png1.addWidget(self.lbl_compress)
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

        # Режим склейки
        row_stitch_mode = QHBoxLayout()
        row_stitch_mode.addStretch(1)

        self.rb_one = QRadioButton("По одному")
        self.rb_auto = QRadioButton("По несколько")

        self._stitch_mode_group = QButtonGroup(self)
        self._stitch_mode_group.addButton(self.rb_one)
        self._stitch_mode_group.addButton(self.rb_auto)

        row_stitch_mode.addWidget(self.rb_one)
        row_stitch_mode.addSpacing(24)
        row_stitch_mode.addWidget(self.rb_auto)
        row_stitch_mode.addStretch(1)
        v.addLayout(row_stitch_mode)

        # Склейка по одной
        self.grp_one = QGroupBox("По одному")
        row_one = QHBoxLayout(self.grp_one)
        row_one.addStretch(1)

        self.btn_one = QPushButton("Склеить")
        self.btn_one_pick = QPushButton("Выбрать файлы…")

        row_one.addWidget(self.btn_one)
        row_one.addSpacing(0)
        row_one.addWidget(self.btn_one_pick)

        v.addWidget(self.grp_one)

        # Склейка по несколько
        self.grp_auto = QGroupBox("По несколько")
        av = QVBoxLayout(self.grp_auto)

        # ── Режим автосклейки (как в cut_section)
        row_a_mode = QHBoxLayout()
        row_a_mode.addWidget(QLabel("Режим:"))
        self.combo_auto_mode = QComboBox()
        self.combo_auto_mode.addItems(["По количеству фрагментов", "По высоте"])
        row_a_mode.addWidget(self.combo_auto_mode)
        row_a_mode.addStretch(1)
        av.addLayout(row_a_mode)

        # ── Общий ряд параметров (без стека) + "Нули"
        row_params = QHBoxLayout()

        self.lbl_group = QLabel("По сколько клеить:")
        self.spin_group = QSpinBox()
        self.spin_group.setRange(2, 999)
        self.spin_group.setValue(12)

        self.lbl_max_h = QLabel("Макс. высота (px):")
        self.spin_max_h = QSpinBox()
        self.spin_max_h.setRange(100, 100000)
        self.spin_max_h.setSingleStep(50)
        self.spin_max_h.setValue(10000)

        row_params.addWidget(self.lbl_group)
        row_params.addWidget(self.spin_group)
        row_params.addWidget(self.lbl_max_h)
        row_params.addWidget(self.spin_max_h)

        row_params.addSpacing(16)
        row_params.addWidget(QLabel("Нули:"))
        self.spin_zeros = QSpinBox()
        self.spin_zeros.setRange(1, 6)
        self.spin_zeros.setValue(2)
        row_params.addWidget(self.spin_zeros)
        row_params.addStretch(1)
        av.addLayout(row_params)

        # ----- Потоки
        row_a_threads = QHBoxLayout()
        self.chk_auto_threads = QCheckBox("Авто потоки")
        self.chk_auto_threads.setChecked(True)

        self.spin_threads = QSpinBox()
        self.spin_threads.setRange(1, 32)
        # разумный дефолт: половина ядер, но не меньше 2
        _default_thr = max(2, (os.cpu_count() or 4) // 2)
        self.spin_threads.setValue(min(32, _default_thr))

        # Метка и состояние
        row_a_threads.addWidget(self.chk_auto_threads)
        row_a_threads.addSpacing(12)
        self.lbl_threads = QLabel("Потоки:")
        row_a_threads.addWidget(self.lbl_threads)
        row_a_threads.addWidget(self.spin_threads)
        row_a_threads.addStretch(1)

        self._apply_threads_state(self.chk_auto_threads.isChecked())
        self.chk_auto_threads.toggled.connect(self._apply_threads_state)

        av.addLayout(row_a_threads)
        # ----- /Потоки

        row_a2 = QHBoxLayout()
        row_a2.setContentsMargins(0, 8, 0, 0)
        row_a2.addStretch(1)

        self.btn_auto = QPushButton("Склеить")
        self.btn_auto_pick = QPushButton("Выбрать файлы…")

        row_a2.addWidget(self.btn_auto)
        row_a2.addSpacing(0)
        row_a2.addWidget(self.btn_auto_pick)

        av.addLayout(row_a2)
        v.addWidget(self.grp_auto)

        # defaults + сигналы
        self.chk_no_resize.setChecked(True)
        self._update_dim_label()
        self.cmb_dir.currentIndexChanged.connect(self._update_dim_label)
        self.chk_no_resize.toggled.connect(self._apply_dim_state)
        self.btn_one.clicked.connect(self._do_stitch_one)
        self.btn_one_pick.clicked.connect(self._do_stitch_one_pick)
        self.btn_auto.clicked.connect(self._do_stitch_auto)
        self.btn_auto_pick.clicked.connect(self._do_stitch_auto_pick)
        self.combo_auto_mode.currentIndexChanged.connect(self._on_auto_mode_changed)
        self.rb_one.toggled.connect(self._on_stitch_mode_changed)
        self.rb_auto.toggled.connect(self._on_stitch_mode_changed)
        self._apply_dim_state()
        QTimer.singleShot(0, self._apply_settings_from_ini)
        # настройки пишутся через apply_bindings (см. _apply_settings_from_ini)
        self.chk_opt.toggled.connect(self._apply_compress_state)
        self._apply_compress_state(self.chk_opt.isChecked())

        self.rb_one.setChecked(True)
        self._apply_stitch_mode("one")

        # управление доступностью поля "Потоки" от чекбокса "Авто потоки"

    def _img_wh(self, path: str) -> tuple[int, int]:
        # mem:// из буфера
        if isinstance(path, str) and path.startswith("mem://") and callable(memory_image_for):
            try:
                img = memory_image_for(path)
                if img is not None and not img.isNull():
                    return int(img.width()), int(img.height())
            except Exception:
                pass
        # обычный файл
        try:
            r = QImageReader(path)
            sz = r.size()
            if sz.isValid():
                return int(sz.width()), int(sz.height())
        except Exception:
            pass
        return (0, 0)

    def _scaled_h(self, wh: tuple[int, int], direction: str, target_dim: int | None) -> int:
        w, h = wh
        if w <= 0 or h <= 0:
            return 0
        if direction == "По вертикали":
            # при вертикали выравниваем по ширине
            if target_dim is None:
                return h
            # масштабирование по ширине с сохранением пропорций
            return max(1, int(round(h * (float(target_dim) / max(1, float(w))))))
        else:
            # при горизонтали конечная высота — либо target_height, либо max(h)
            return int(target_dim) if target_dim else h

    def _split_chunks_by_max_height(self, paths: list[str], direction: str,
                                    target_dim: int | None, max_h: int) -> list[list[str]]:
        chunks: list[list[str]] = []
        cur: list[str] = []
        cur_metric = 0  # сумма (вертикаль) или max (горизонталь)

        for p in paths:
            hh = self._scaled_h(self._img_wh(p), direction, target_dim)
            if direction == "По вертикали":
                new_metric = cur_metric + hh
            else:
                new_metric = max(cur_metric, hh)

            if cur and new_metric > max_h:
                chunks.append(cur)
                cur = [p]
                cur_metric = hh if direction == "По вертикали" else hh
            else:
                cur.append(p)
                cur_metric = new_metric

        if cur:
            chunks.append(cur)
        return chunks

    def _apply_stitch_mode(self, mode: str):
        is_one = (mode == "one")
        self.grp_one.setVisible(is_one)
        self.grp_auto.setVisible(not is_one)

    def _on_stitch_mode_changed(self, _checked: bool):
        mode = "one" if self.rb_one.isChecked() else "multi"
        self._stitch_mode_le.setText(mode)
        self._apply_stitch_mode(mode)
        ini_save_str("StitchSection", "stitch_mode", mode)

    def _on_auto_mode_changed(self, idx: int):
        by = "count" if int(idx) == 0 else "height"
        show_count = (by == "count")

        # показываем нужную пару слева
        self.lbl_group.setVisible(show_count)
        self.spin_group.setVisible(show_count)
        self.lbl_max_h.setVisible(not show_count)
        self.spin_max_h.setVisible(not show_count)

        self._group_by_le.setText(by)
        ini_save_str("StitchSection", "group_by", by)

    def _apply_threads_state(self, checked: bool | None = None):
        if checked is None:
            checked = self.chk_auto_threads.isChecked()
        on = not checked
        self.spin_threads.setEnabled(on)
        if hasattr(self, "lbl_threads"):
            self.lbl_threads.setEnabled(on)

    def _apply_compress_state(self, optimize_on: bool):
        """Вариант А: затемнить = отключить контрол уровня при включённой оптимизации."""
        # выключаем/включаем спин и его метку
        self.spin_compress.setEnabled(not optimize_on)
        if hasattr(self, "lbl_compress"):
            self.lbl_compress.setEnabled(not optimize_on)

        # понятные подсказки
        if optimize_on:
            self.spin_compress.setToolTip(
                "Оптимизация PNG включена — изменение уровня даёт умеренный эффект, поэтому поле отключено.")
        else:
            self.spin_compress.setToolTip("Уровень DEFLATE 0–9: выше — дольше и немного меньше файл.")

    def _resolve_threads(self) -> int:
        """Осторожный выбор числа потоков для слабых ПК."""
        if getattr(self, "chk_auto_threads", None) and self.chk_auto_threads.isChecked():
            c = os.cpu_count() or 2
            # осторожная лестница
            if c <= 2:
                auto = 1
            elif c <= 4:
                auto = 2
            elif c <= 8:
                auto = 4
            else:
                auto = min(8, c - 2)  # чуть меньше максимума
            return max(1, min(8, auto))
        # ручной режим
        try:
            val = int(self.spin_threads.value())
        except Exception:
            val = 1
        return max(1, min(32, val))

    # helpers
    def reset_to_defaults(self):
        auto_mode_idx = self.combo_auto_mode.currentIndex()  # 0=count, 1=height
        stitch_mode = "one" if self.rb_one.isChecked() else "multi"

        reset_bindings(self, "StitchSection")

        try:
            self.combo_auto_mode.blockSignals(True)
            self.combo_auto_mode.setCurrentIndex(auto_mode_idx)
        finally:
            self.combo_auto_mode.blockSignals(False)

        by = "count" if auto_mode_idx == 0 else "height"
        self._group_by_le.setText(by)
        ini_save_str("StitchSection", "group_by", by)
        self._on_auto_mode_changed(self.combo_auto_mode.currentIndex())

        try:
            self.rb_one.blockSignals(True)
            self.rb_auto.blockSignals(True)
            self.rb_one.setChecked(stitch_mode == "one")
            self.rb_auto.setChecked(stitch_mode != "one")
        finally:
            self.rb_one.blockSignals(False)
            self.rb_auto.blockSignals(False)

        self._stitch_mode_le.setText(stitch_mode)
        ini_save_str("StitchSection", "stitch_mode", stitch_mode)
        self._apply_stitch_mode(stitch_mode)

        # привести зависимые состояния в актуальный вид
        self._apply_compress_state(self.chk_opt.isChecked())
        self._apply_dim_state()
        self._apply_threads_state()

    def _apply_settings_from_ini(self):
        apply_bindings(self, "StitchSection", [
            (self.cmb_dir, "mode", 0),  # индекс: 0=вертикаль
            (self.chk_no_resize, "no_resize", True),
            (self.spin_dim, "dim", 800),
            (self.chk_opt, "optimize_png", True),
            (self.spin_compress, "compress_level", 6),
            (self.chk_strip, "strip_metadata", True),
            (self.spin_group, "per", 12),
            (self.spin_zeros, "zeros", 2),
            (self.spin_max_h, "group_max_height", 10000),

            # потоки — единые дефолты
            (self.chk_auto_threads, "auto_threads", DEFAULTS["auto_threads"]),
            (self.spin_threads, "threads", DEFAULTS["threads"]),

            # директории
            (self._save_dir_le, "stitch_out_dir", DEFAULTS["stitch_out_dir"]),
            (self._save_file_dir_le, "stitch_save_dir", DEFAULTS["stitch_save_dir"]),
            (self._pick_dir_le, "stitch_pick_dir", DEFAULTS["stitch_pick_dir"]),
            (self._auto_pick_dir_le, "stitch_auto_pick_dir", DEFAULTS["stitch_auto_pick_dir"]),

            # строковые флаги
            (self._group_by_le, "group_by", "count"),
            (self._stitch_mode_le, "stitch_mode", "one"),
        ])
        # восстановить режим (count/height)
        gb = (self._group_by_le.text() or "count")
        self.combo_auto_mode.setCurrentIndex(0 if gb == "count" else 1)
        self._on_auto_mode_changed(self.combo_auto_mode.currentIndex())

        mode = (self._stitch_mode_le.text() or "one")
        try:
            self.rb_one.blockSignals(True)
            self.rb_auto.blockSignals(True)
            self.rb_one.setChecked(mode == "one")
            self.rb_auto.setChecked(mode != "one")
        finally:
            self.rb_one.blockSignals(False)
            self.rb_auto.blockSignals(False)

        self._apply_stitch_mode(mode)

        self._apply_compress_state(self.chk_opt.isChecked())
        self._apply_dim_state()

    def _update_dim_label(self):
        if self.cmb_dir.currentText() == "По вертикали":
            self.lbl_dim.setText("Ширина (px):")
            self.chk_no_resize.setText("Не изменять ширину")
        else:
            self.lbl_dim.setText("Высота (px):")
            self.chk_no_resize.setText("Не изменять высоту")

    def _apply_dim_state(self):
        on = not self.chk_no_resize.isChecked()
        self.spin_dim.setEnabled(on)
        if hasattr(self, "lbl_dim"):
            self.lbl_dim.setEnabled(on)

    def _ask_selected_paths(self) -> List[str]:
        if self._gallery and hasattr(self._gallery, 'selected_files'):
            sel = self._gallery.selected_files()
            if sel:
                return sel
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
        start_pick = ini_load_str("StitchSection", "stitch_pick_dir", os.path.expanduser("~"))
        files, _ = QFileDialog.getOpenFileNames(
            self, "Выберите изображения", start_pick,
            "Изображения (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if len(files) < 2:
            return
        # сохранить папку выбора
        ini_save_str("StitchSection", "stitch_pick_dir", os.path.dirname(files[0]))

        start_save = ini_load_str("StitchSection", "stitch_save_dir", os.path.dirname(files[0]))
        out_path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить как", os.path.join(start_save, "result.png"),
            "PNG (*.png)"
        )
        if not out_path:
            return
        if not out_path.lower().endswith(".png"):
            out_path += ".png"
        # сохранить папку сохранения
        ini_save_str("StitchSection", "stitch_save_dir", os.path.dirname(out_path))

        out_path2, out_dir2 = self._stitch_and_save_single(files, out_path)
        if out_path2:
            self._show_done_box(out_dir2, f"Сохранено: {os.path.basename(out_path2)}")

    def _stitch_and_save_single(self, paths: List[str], direct_out_path: str | None = None):
        direction, dim_val, optimize, compress, strip = self._build_output_params()

        # Куда сохраняем
        if direct_out_path:
            out_path = direct_out_path
        else:
            start_save = ini_load_str("StitchSection", "stitch_save_dir", os.path.expanduser("~"))
            out_path, _ = QFileDialog.getSaveFileName(
                self, "Сохранить как", os.path.join(start_save, "result.png"),
                "PNG (*.png)"
            )
            if not out_path:
                return None, None
            if not out_path.lower().endswith(".png"):
                out_path += ".png"
            ini_save_str("StitchSection", "stitch_save_dir", os.path.dirname(out_path))

        # Показываем прогресс только когда реально начинаем склейку/сохранение
        dlg = QProgressDialog("Сохраняю…", None, 0, 0, self)
        dlg.setWindowTitle("Сохранение")
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setCancelButton(None)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.show()
        QApplication.processEvents()

        def _job():
            imgs = load_images(paths)
            if not imgs:
                raise RuntimeError("Нет валидных изображений")
            if direction == "По вертикали":
                merged = merge_vertical(imgs, target_width=dim_val)
            else:
                merged = merge_horizontal(imgs, target_height=dim_val)
            try:
                save_png(merged, out_path, optimize=optimize,
                         compress_level=compress, strip_metadata=strip)
            except MemoryError:
                try:
                    save_png(merged, out_path, optimize=False,
                             compress_level=min(3, int(compress) if isinstance(compress, int) else 3),
                             strip_metadata=strip)
                except MemoryError as e:
                    raise RuntimeError("Недостаточно памяти для параллельной склейки") from e
            return out_path

        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(_job)
                while not fut.done():
                    QApplication.processEvents()
                result_path = fut.result()
        except Exception as e:
            dlg.close()
            QMessageBox.critical(self, "Сохранение", f"Не удалось сохранить PNG: {e}")
            return None, None

        dlg.close()
        return result_path, os.path.dirname(result_path)

    def _do_stitch_auto(self):
        paths = self._ask_selected_paths()
        if len(paths) < 2:
            QMessageBox.warning(self, "Склейка",
                                "Выберите минимум два изображения или используйте «Выбрать файлы…».")
            return
        start_out = ini_load_str("StitchSection", "stitch_out_dir", os.path.expanduser("~"))
        out_dir = QFileDialog.getExistingDirectory(self, "Выберите папку для сохранения", start_out)
        if not out_dir:
            return
        ini_save_str("StitchSection", "stitch_out_dir", out_dir)

        count = self._stitch_and_save_groups(paths, out_dir)
        if count > 0:
            self._show_done_box(out_dir, f"Файлов сохранено: {count}")

    def _do_stitch_auto_pick(self):
        start_pick = ini_load_str("StitchSection", "stitch_auto_pick_dir", os.path.expanduser("~"))
        files, _ = QFileDialog.getOpenFileNames(
            self, "Выберите изображения", start_pick,
            "Изображения (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if len(files) < 2:
            return
        ini_save_str("StitchSection", "stitch_auto_pick_dir", os.path.dirname(files[0]))

        start_out = ini_load_str("StitchSection", "stitch_out_dir", os.path.dirname(files[0]))
        out_dir = QFileDialog.getExistingDirectory(self, "Папка для сохранения PNG", start_out)
        if not out_dir:
            return
        ini_save_str("StitchSection", "stitch_out_dir", out_dir)

        count = self._stitch_and_save_groups(files, out_dir)
        if count > 0:
            self._show_done_box(out_dir, f"Файлов сохранено: {count}")

    def _stitch_and_save_groups(self, paths: List[str], out_dir: str) -> int:
        group = int(self.spin_group.value())
        zeros = int(self.spin_zeros.value())
        direction, dim_val, optimize, compress, strip = self._build_output_params()

        # --- выбираем режим группировки
        by = "count" if self.combo_auto_mode.currentIndex() == 0 else "height"
        if by == "count":
            chunks = [paths[i:i + group] for i in range(0, len(paths), group)]
        else:
            max_h = int(self.spin_max_h.value())
            chunks = self._split_chunks_by_max_height(paths, direction, dim_val, max_h)

        total = len(chunks)
        if total == 0:
            return 0

        prog = QProgressDialog("Сохраняю…", None, 0, total, self)
        prog.setWindowTitle("Сохранение")
        prog.setWindowModality(Qt.ApplicationModal)
        prog.setCancelButton(None)
        prog.setMinimumDuration(0)
        prog.setAutoClose(False)
        prog.show()
        QApplication.processEvents()

        workers = self._resolve_threads()
        workers = max(1, min(workers, total))
        made = 0
        done = 0

        def _job(chunk, out_path):
            imgs = load_images(chunk)
            if not imgs:
                raise RuntimeError("Нет валидных изображений")
            if direction == "По вертикали":
                merged = merge_vertical(imgs, target_width=dim_val)
            else:
                merged = merge_horizontal(imgs, target_height=dim_val)
            save_png(merged, out_path, optimize=optimize, compress_level=compress, strip_metadata=strip)
            return out_path

        # Стартуем задания
        futures = []
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for idx, chunk in enumerate(chunks, start=1):
                fname = f"{idx:0{zeros}d}.png"
                out_path = os.path.join(out_dir, fname)
                fut = ex.submit(_job, chunk, out_path)
                fut._stitch_idx = idx  # для сообщения об ошибках
                fut._stitch_name = fname
                futures.append(fut)

            # Отслеживаем завершение в стабильном порядке отображения прогресса
            for fut in futures:
                try:
                    while not fut.done():
                        QApplication.processEvents()
                    fut.result()
                    made += 1
                except Exception as e:
                    idx = getattr(fut, "_stitch_idx", "?")
                    fname = getattr(fut, "_stitch_name", "<unknown>")
                    QMessageBox.warning(self, "Сохранение", f"Группа {idx} ({fname}) пропущена: {e}")
                finally:
                    done += 1
                    prog.setValue(done)
                    QApplication.processEvents()

        prog.close()
        return made

    def _show_done_box(self, out_dir: str, message: str):
        box = QMessageBox(self)
        box.setWindowTitle("Готово")
        box.setText(message)
        btn_open = box.addButton("Открыть папку", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.exec()
        if box.clickedButton() is btn_open:
            open_in_explorer(out_dir)


from __future__ import annotations
import os, sys, subprocess
from typing import List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSpinBox, QCheckBox,
    QPushButton, QGroupBox, QFileDialog, QMessageBox, QProgressDialog, QApplication, QLineEdit
)
from PySide6.QtCore import Qt, QTimer
from ..stitcher import load_images, merge_vertical, merge_horizontal, save_png

from smithanatool_qt.settings_bind import (
    group, bind_spinbox, bind_checkbox, bind_line_edit,
    bind_attr_string, bind_radiobuttons, save_attr_string
)

from concurrent.futures import ThreadPoolExecutor, as_completed

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

class StitchSection(QWidget):
    def __init__(self, gallery=None, parent=None):
        super().__init__(parent)
        self._gallery = gallery

        self._executor = ThreadPoolExecutor(
            max_workers=max(2, min(32, (os.cpu_count() or 4) - 1))
        )

        v = QVBoxLayout(self); v.setAlignment(Qt.AlignTop)

        self._save_dir_le = QLineEdit(self);
        self._save_dir_le.setVisible(False)  # stitch_out_dir
        self._save_file_dir_le = QLineEdit(self);
        self._save_file_dir_le.setVisible(False)  # stitch_save_dir
        self._pick_dir_le = QLineEdit(self);
        self._pick_dir_le.setVisible(False)  # stitch_pick_dir
        self._auto_pick_dir_le = QLineEdit(self);
        self._auto_pick_dir_le.setVisible(False)  # stitch_auto_pick_dir

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
        self.spin_dim.setMinimumWidth(60)

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

        # Склейка по одной
        grp_one = QGroupBox("По одной")
        row_one = QHBoxLayout(grp_one); row_one.addStretch(1)
        self.btn_one = QPushButton("Склейка в один PNG")
        self.btn_one_pick = QPushButton("Выбрать файлы…")
        row_one.addWidget(self.btn_one); row_one.addWidget(self.btn_one_pick)
        v.addWidget(grp_one)

        # Склейка по несколько
        grp_auto = QGroupBox("По несколько")
        av = QVBoxLayout(grp_auto)
        row_a1 = QHBoxLayout()
        row_a1.addWidget(QLabel("По сколько клеить:"))
        self.spin_group = QSpinBox(); self.spin_group.setRange(2, 999); self.spin_group.setValue(12)
        row_a1.addWidget(self.spin_group); row_a1.addSpacing(16)
        row_a1.addWidget(QLabel("Нули:"))
        self.spin_zeros = QSpinBox(); self.spin_zeros.setRange(1, 6); self.spin_zeros.setValue(2)
        row_a1.addWidget(self.spin_zeros); row_a1.addStretch(1)
        av.addLayout(row_a1)

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
        QTimer.singleShot(0, self._apply_settings_from_ini)

        self.spin_dim.valueChanged.connect(lambda v: self._save_int_ini("dim", v))
        self.chk_opt.toggled.connect(lambda v: self._save_bool_ini("optimize_png", v))
        self.chk_opt.toggled.connect(self._apply_compress_state)
        self.spin_compress.valueChanged.connect(lambda v: self._save_int_ini("compress_level", v))
        self.chk_strip.toggled.connect(lambda v: self._save_bool_ini("strip_metadata", v))
        self.spin_group.valueChanged.connect(lambda v: self._save_int_ini("per", v))
        self.spin_zeros.valueChanged.connect(lambda v: self._save_int_ini("zeros", v))

        # управление доступностью поля "Потоки" от чекбокса "Авто потоки"

    def _apply_threads_state(self, checked: bool | None = None):
        if checked is None:
            checked = self.chk_auto_threads.isChecked()
        on = not checked
        self.spin_threads.setEnabled(on)
        if hasattr(self, "lbl_threads"):
            self.lbl_threads.setEnabled(on)

    def _ini_load_str(self, key: str, default: str = "") -> str:
        try:
            shadow_attr = f"__{key}__shadow"
            setattr(self, shadow_attr, default)
            with group("StitchSection"):
                bind_attr_string(self, shadow_attr, key, default)
            return getattr(self, shadow_attr, default)
        except Exception:
            return default
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
        defaults = dict(
            mode=0,  # 0=вертикаль
            no_resize=True,
            dim=800,
            optimize_png=True,
            compress_level=6,
            strip_metadata=True,
            per=12,
            zeros=2,
            auto_threads=True,
            threads=max(2, (os.cpu_count() or 4) // 2),
        )
        # UI
        if hasattr(self, "cmb_dir"):
            self.cmb_dir.blockSignals(True)
            self.cmb_dir.setCurrentIndex(defaults["mode"])
            self.cmb_dir.blockSignals(False)
        if hasattr(self, "chk_no_resize"):
            self.chk_no_resize.setChecked(defaults["no_resize"])
        if hasattr(self, "spin_dim"):
            self.spin_dim.setValue(defaults["dim"])
        if hasattr(self, "chk_opt"):
            self.chk_opt.setChecked(defaults["optimize_png"])
        if hasattr(self, "spin_compress"):
            self.spin_compress.setValue(defaults["compress_level"])
        if hasattr(self, "chk_strip"):
            self.chk_strip.setChecked(defaults["strip_metadata"])
        if hasattr(self, "spin_group"):
            self.spin_group.setValue(defaults["per"])
        if hasattr(self, "spin_zeros"):
            self.spin_zeros.setValue(defaults["zeros"])
        if hasattr(self, "chk_auto_threads"):
            self.chk_auto_threads.setChecked(defaults["auto_threads"])
        if hasattr(self, "spin_threads"):
            self.spin_threads.setValue(min(32, defaults["threads"]))

        # применить доступность "Потоки"
        on = not self.chk_auto_threads.isChecked()
        self.spin_threads.setEnabled(on)
        if hasattr(self, "lbl_threads"):
            self.lbl_threads.setEnabled(on)
        # применить внутренние завязки UI
        if hasattr(self, "_apply_dim_state"):
            self._apply_dim_state()



        # сохранить в INI
        self._save_int_ini("mode", defaults["mode"])
        self._save_bool_ini("no_resize", defaults["no_resize"])
        self._save_int_ini("dim", defaults["dim"])
        self._save_bool_ini("optimize_png", defaults["optimize_png"])
        self._save_int_ini("compress_level", defaults["compress_level"])
        self._save_bool_ini("strip_metadata", defaults["strip_metadata"])
        self._save_int_ini("per", defaults["per"])
        self._save_int_ini("zeros", defaults["zeros"])
        self._save_bool_ini("auto_threads", defaults["auto_threads"])
        self._save_int_ini("threads", min(32, defaults["threads"]))

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

            # потоки — единые дефолты
            (self.chk_auto_threads, "auto_threads", DEFAULTS["auto_threads"]),
            (self.spin_threads, "threads", DEFAULTS["threads"]),

            # директории
            (self._save_dir_le, "stitch_out_dir", DEFAULTS["stitch_out_dir"]),
            (self._save_file_dir_le, "stitch_save_dir", DEFAULTS["stitch_save_dir"]),
            (self._pick_dir_le, "stitch_pick_dir", DEFAULTS["stitch_pick_dir"]),
            (self._auto_pick_dir_le, "stitch_auto_pick_dir", DEFAULTS["stitch_auto_pick_dir"]),
        ])
        self._apply_compress_state(self.chk_opt.isChecked())
        self._apply_dim_state()

    def _save_str_ini(self, key: str, value: str):
        try:
            shadow_attr = f"__{key}__shadow"
            setattr(self, shadow_attr, value)
            with group("StitchSection"):
                save_attr_string(self, shadow_attr, key)
        except Exception:
            pass

    def _save_int_ini(self, key: str, value: int):
        self._save_str_ini(key, str(int(value)))

    def _save_bool_ini(self, key: str, value: bool):
        self._save_str_ini(key, "1" if value else "0")

    def _update_dim_label(self):
        if self.cmb_dir.currentText() == "По вертикали":
            self.lbl_dim.setText("Ширина:")
            self.chk_no_resize.setText("Не изменять ширину")
        else:
            self.lbl_dim.setText("Высота:")
            self.chk_no_resize.setText("Не изменять высоту")

    def _apply_dim_state(self):
        on = not self.chk_no_resize.isChecked()
        self.spin_dim.setEnabled(on)
        if hasattr(self, "lbl_dim"):
            self.lbl_dim.setEnabled(on)

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
        start_pick = self._ini_load_str("stitch_pick_dir", os.path.expanduser("~"))
        files, _ = QFileDialog.getOpenFileNames(
            self, "Выберите изображения", start_pick,
            "Изображения (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if len(files) < 2:
            return
        # сохранить папку выбора
        self._save_str_ini("stitch_pick_dir", os.path.dirname(files[0]))

        start_save = self._ini_load_str("stitch_save_dir", os.path.dirname(files[0]))
        out_path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить как", os.path.join(start_save, "result.png"),
            "PNG (*.png)"
        )
        if not out_path:
            return
        if not out_path.lower().endswith(".png"):
            out_path += ".png"
        # сохранить папку сохранения
        self._save_str_ini("stitch_save_dir", os.path.dirname(out_path))

        out_path2, out_dir2 = self._stitch_and_save_single(files, out_path)
        if out_path2:
            self._show_done_box(out_dir2, f"Сохранено: {os.path.basename(out_path2)}")

    def _stitch_and_save_single(self, paths: List[str], direct_out_path: str | None = None):
        dlg = QProgressDialog("Сохраняю…", None, 0, 0, self)
        dlg.setWindowTitle("Сохранение");
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setCancelButton(None);
        dlg.setMinimumDuration(0);
        dlg.setAutoClose(False);
        dlg.show()
        QApplication.processEvents()

        direction, dim_val, optimize, compress, strip = self._build_output_params()

        # Куда сохраняем
        if direct_out_path:
            out_path = direct_out_path
        else:
            start_save = self._ini_load_str("stitch_save_dir", os.path.expanduser("~"))
            out_path, _ = QFileDialog.getSaveFileName(
                self, "Сохранить как", os.path.join(start_save, "result.png"),
                "PNG (*.png)"
            )
            if not out_path:
                dlg.close();
                return None, None
            if not out_path.lower().endswith(".png"):
                out_path += ".png"
            self._save_str_ini("stitch_save_dir", os.path.dirname(out_path))

        # Вынесем тяжёлую часть в отдельный поток (1 воркер тут достаточно)
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
                # план Б: без optimize и с пониженной компрессией
                try:
                    save_png(merged, out_path, optimize=False,
                             compress_level=min(3, int(compress) if isinstance(compress, int) else 3),
                             strip_metadata=strip)
                except MemoryError as e:
                    # финальный откат: последовательное сохранение (вызовем тот же код синхронно)
                    raise RuntimeError("Недостаточно памяти для параллельной склейки") from e
            return out_path

        try:
            # max_workers=1: этого хватает, мы просто не блокируем GUI
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
            QMessageBox.warning(self, "Автосклейка",
                                "Выберите минимум два изображения или используйте «Выбрать файлы…».")
            return
        start_out = self._ini_load_str("stitch_out_dir", os.path.expanduser("~"))
        out_dir = QFileDialog.getExistingDirectory(self, "Выберите папку для сохранения", start_out)
        if not out_dir:
            return
        self._save_str_ini("stitch_out_dir", out_dir)

        count = self._stitch_and_save_groups(paths, out_dir)
        if count > 0:
            self._show_done_box(out_dir, f"Файлов сохранено: {count}")

    def _do_stitch_auto_pick(self):
        start_pick = self._ini_load_str("stitch_auto_pick_dir", os.path.expanduser("~"))
        files, _ = QFileDialog.getOpenFileNames(
            self, "Выберите изображения", start_pick,
            "Изображения (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if len(files) < 2:
            return
        self._save_str_ini("stitch_auto_pick_dir", os.path.dirname(files[0]))

        start_out = self._ini_load_str("stitch_out_dir", os.path.dirname(files[0]))
        out_dir = QFileDialog.getExistingDirectory(self, "Папка для сохранения PNG", start_out)
        if not out_dir:
            return
        self._save_str_ini("stitch_out_dir", out_dir)

        count = self._stitch_and_save_groups(files, out_dir)
        if count > 0:
            self._show_done_box(out_dir, f"Файлов сохранено: {count}")

    def _stitch_and_save_groups(self, paths: List[str], out_dir: str) -> int:
        group = int(self.spin_group.value())
        zeros = int(self.spin_zeros.value())
        direction, dim_val, optimize, compress, strip = self._build_output_params()

        # Разбиваем вход на чанки
        chunks = [paths[i:i + group] for i in range(0, len(paths), group)]
        total = len(chunks)
        if total == 0:
            return 0

        prog = QProgressDialog("Сохраняю…", None, 0, total, self)
        prog.setWindowTitle("Сохранение");
        prog.setWindowModality(Qt.ApplicationModal)
        prog.setCancelButton(None);
        prog.setMinimumDuration(0);
        prog.setAutoClose(False);
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
        box = QMessageBox(self); box.setWindowTitle("Готово"); box.setText(message)
        btn_open = box.addButton("Открыть папку", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok); box.exec()
        if box.clickedButton() is btn_open: _open_in_explorer(out_dir)

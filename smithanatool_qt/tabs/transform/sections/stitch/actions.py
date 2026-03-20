from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QProgressDialog

from smithanatool_qt.tabs.transform.utils.fs import open_in_explorer

from .service import (
    natural_key,
    normalize_files,
    run_smartstitch,
    stitch_chunks_to_dir,
    stitch_single_to_file,
    suggest_base_name,
)

IMAGE_FILTER = "Изображения (*.png *.jpg *.jpeg *.bmp *.webp)"
SMART_IMAGE_FILTER = "Изображения (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff *.tga)"


class StitchSectionActionsMixin:
    def _show_done_box(self, out_dir: str, message: str):
        box = QMessageBox(self)
        box.setWindowTitle("Готово")
        box.setText(message)
        btn_open = box.addButton("Открыть папку", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.exec()
        if box.clickedButton() is btn_open:
            open_in_explorer(out_dir)

    def _on_run_clicked(self):
        mode = self._current_stitch_mode()
        if mode == "one":
            self._do_stitch_one()
        elif mode == "smart":
            self._do_stitch_smart()
        else:
            self._do_stitch_auto()

    def _on_pick_clicked(self):
        mode = self._current_stitch_mode()
        if mode == "one":
            self._do_stitch_one_pick()
        elif mode == "smart":
            self._do_stitch_smart_pick()
        else:
            self._do_stitch_auto_pick()

    def _do_stitch_one(self):
        paths = self._ask_selected_paths()
        if len(paths) < 2:
            QMessageBox.warning(
                self,
                "Склейка",
                "Выберите минимум два изображения в галерее или используйте «Выбрать файлы…».",
            )
            return

        out_path, out_dir = self._stitch_and_save_single(paths)
        if out_path:
            self._show_done_box(out_dir, f"Сохранено: {os.path.basename(out_path)}")

    def _do_stitch_one_pick(self):
        start_pick = self._get_last_pick_dir()
        files, _ = QFileDialog.getOpenFileNames(self, "Выберите изображения", start_pick, IMAGE_FILTER)
        if len(files) < 2:
            return
        self._set_last_pick_dir(files[0])

        start_save = self._get_last_out_dir(os.path.dirname(files[0]))
        out_path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить как",
            os.path.join(start_save, "result.png"),
            "PNG (*.png)",
        )
        if not out_path:
            return
        if not out_path.lower().endswith(".png"):
            out_path += ".png"
        self._set_last_out_dir(out_path)

        result_path, result_dir = self._stitch_and_save_single(files, out_path)
        if result_path:
            self._show_done_box(result_dir, f"Сохранено: {os.path.basename(result_path)}")

    def _stitch_and_save_single(self, paths: List[str], direct_out_path: str | None = None):
        direction, dim_val, optimize, compress, strip = self._build_output_params()

        if direct_out_path:
            out_path = direct_out_path
            self._set_last_out_dir(out_path)
        else:
            start_save = self._get_last_out_dir()
            out_path, _ = QFileDialog.getSaveFileName(
                self,
                "Сохранить как",
                os.path.join(start_save, "result.png"),
                "PNG (*.png)",
            )
            if not out_path:
                return None, None
            if not out_path.lower().endswith(".png"):
                out_path += ".png"
            self._set_last_out_dir(out_path)

        dlg = QProgressDialog("Сохраняю…", None, 0, 0, self)
        dlg.setWindowTitle("Сохранение")
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setCancelButton(None)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.show()
        QApplication.processEvents()

        def _job():
            return stitch_single_to_file(
                paths,
                out_path,
                direction=direction,
                dim_val=dim_val,
                optimize=optimize,
                compress=compress,
                strip=strip,
            )

        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_job)
                while not future.done():
                    QApplication.processEvents()
                result_path = future.result()
        except Exception as exc:
            dlg.close()
            QMessageBox.critical(self, "Сохранение", f"Не удалось сохранить PNG: {exc}")
            return None, None

        dlg.close()
        return result_path, os.path.dirname(result_path)

    def _do_stitch_auto(self):
        paths = self._ask_selected_paths()
        if len(paths) < 2:
            QMessageBox.warning(
                self,
                "Склейка",
                "Выберите минимум два изображения или используйте «Выбрать файлы…».",
            )
            return

        start_out = self._get_last_out_dir()
        out_dir = QFileDialog.getExistingDirectory(self, "Выберите папку для сохранения", start_out)
        if not out_dir:
            return
        self._set_last_out_dir(out_dir)

        count = self._stitch_and_save_groups(paths, out_dir)
        if count > 0:
            self._show_done_box(out_dir, f"Файлов сохранено: {count}")

    def _do_stitch_auto_pick(self):
        start_pick = self._get_last_pick_dir()
        files, _ = QFileDialog.getOpenFileNames(self, "Выберите изображения", start_pick, SMART_IMAGE_FILTER)
        if len(files) < 2:
            return
        self._set_last_pick_dir(files[0])

        start_out = self._get_last_out_dir(os.path.dirname(files[0]))
        out_dir = QFileDialog.getExistingDirectory(self, "Папка для сохранения PNG", start_out)
        if not out_dir:
            return
        self._set_last_out_dir(out_dir)

        count = self._stitch_and_save_groups(files, out_dir)
        if count > 0:
            self._show_done_box(out_dir, f"Файлов сохранено: {count}")

    def _stitch_and_save_groups(self, paths: List[str], out_dir: str) -> int:
        group = int(self.spin_group.value())
        zeros = int(self.spin_zeros.value())
        direction, dim_val, optimize, compress, strip = self._build_output_params()

        group_by = "count" if self.combo_auto_mode.currentIndex() == 0 else "height"
        if group_by == "count":
            chunks = [paths[i : i + group] for i in range(0, len(paths), group)]
        else:
            chunks = self._split_chunks_by_max_height(paths, direction, dim_val, int(self.spin_max_h.value()))

        total = len(chunks)
        if total == 0:
            return 0

        progress = QProgressDialog("Сохраняю…", None, 0, total, self)
        progress.setWindowTitle("Сохранение")
        progress.setWindowModality(Qt.ApplicationModal)
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.show()
        QApplication.processEvents()

        def _on_progress(done: int, total_count: int):
            progress.setMaximum(total_count)
            progress.setValue(done)
            QApplication.processEvents()

        made, errors = stitch_chunks_to_dir(
            chunks,
            out_dir,
            zeros=zeros,
            direction=direction,
            dim_val=dim_val,
            optimize=optimize,
            compress=compress,
            strip=strip,
            workers=max(1, min(self._resolve_threads(), total)),
            progress_callback=_on_progress,
        )

        progress.close()

        for idx, name, error_text in errors:
            QMessageBox.warning(self, "Сохранение", f"Группа {idx} ({name}) пропущена: {error_text}")

        return made

    def _do_stitch_smart(self):
        files = normalize_files(self._ask_selected_paths())
        if not files:
            QMessageBox.information(self, "SmartStitch", "В галерее нет файлов для обработки.")
            return

        try:
            files = sorted(files, key=lambda path: natural_key(Path(path).name))
        except Exception:
            pass

        start_out = self._get_last_out_dir()
        out_dir = QFileDialog.getExistingDirectory(self, "Папка для сохранения PNG", start_out)
        if not out_dir:
            return
        self._set_last_out_dir(out_dir)

        total_saved = self._run_smartstitch(files, out_dir)
        if total_saved > 0:
            self._show_done_box(out_dir, f"Сохранено фрагментов: {total_saved}")

    def _do_stitch_smart_pick(self):
        start_pick = self._get_last_pick_dir()
        files, _ = QFileDialog.getOpenFileNames(self, "Выберите изображения", start_pick, IMAGE_FILTER)
        files = normalize_files(files)
        if len(files) < 2:
            return

        try:
            files = sorted(files, key=lambda path: natural_key(Path(path).name))
        except Exception:
            pass

        self._set_last_pick_dir(files[0])

        start_out = self._get_last_out_dir(str(Path(files[0]).parent))
        out_dir = QFileDialog.getExistingDirectory(self, "Папка для сохранения PNG", start_out)
        if not out_dir:
            return
        self._set_last_out_dir(out_dir)

        total_saved = self._run_smartstitch(files, out_dir)
        if total_saved > 0:
            self._show_done_box(out_dir, f"Сохранено фрагментов: {total_saved}")

    def _run_smartstitch(self, files: list[str], out_dir: str) -> int:
        if self.cmb_dir.currentText() != "По вертикали":
            QMessageBox.warning(self, "SmartStitch", "SmartStitch работает только при вертикальной склейке.")
            return 0

        _, dim_val, optimize, compress, strip = self._build_output_params()

        progress = QProgressDialog("Склеиваю и нарезаю главу…", None, 0, 0, self)
        progress.setWindowTitle("SmartStitch")
        progress.setWindowModality(Qt.ApplicationModal)
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.show()
        QApplication.processEvents()

        def _job():
            return run_smartstitch(
                files,
                out_dir,
                detector=self._current_smart_detector_key(),
                slice_height=int(self.spin_smart_height.value()),
                digits=int(self.spin_smart_zeros.value()),
                sensitivity=int(self.spin_smart_sensitivity.value()),
                scan_step=int(self.spin_smart_scan_step.value()),
                ignore_borders=int(self.spin_smart_ignore.value()),
                base_name=suggest_base_name(files),
                target_width=0 if dim_val is None else int(dim_val),
                strip_metadata=strip,
                optimize_png=optimize,
                compress_level=compress,
            )

        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_job)
                while not future.done():
                    QApplication.processEvents()
                total_saved = future.result()
        except Exception as exc:
            progress.close()
            QMessageBox.warning(self, "SmartStitch", f"Не удалось обработать файлы:\n{exc}")
            return 0

        progress.close()
        return int(total_saved or 0)

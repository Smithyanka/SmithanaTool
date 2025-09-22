
from __future__ import annotations
from typing import List
import os, sys, subprocess
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox, QSpinBox,
    QCheckBox, QFileDialog, QMessageBox, QProgressDialog, QApplication
)
from PySide6.QtCore import Qt, QTimer
from .converters.png_gif import filter_png as filter_png_for_gif, convert_png_to_gif
from .converters.png_pdf import filter_png as filter_png_for_pdf, convert_png_to_pdf, merge_pngs_to_pdf
from .converters.psd_png import filter_psd, convert_psd_to_png

from smithanatool_qt.settings_bind import (
    group, bind_spinbox, bind_checkbox, save_attr_string
)
from concurrent.futures import ThreadPoolExecutor, as_completed

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

class ConversionsPanel(QWidget):
    def __init__(self, gallery=None, parent=None):
        super().__init__(parent)
        self._gallery = gallery
        v = QVBoxLayout(self); v.setAlignment(Qt.AlignTop)

        # GIF
        box_gif = QGroupBox("PNG → GIF конвертор"); g = QVBoxLayout(box_gif)
        row_g1 = QHBoxLayout(); self.gif_dither = QCheckBox("Дизеринг"); self.gif_dither.setChecked(True); row_g1.addWidget(self.gif_dither); row_g1.addStretch(1); g.addLayout(row_g1)
        row_g2 = QHBoxLayout(); row_g2.addStretch(1); self.btn_gif_convert_sel = QPushButton("Преобразовать выделенные"); self.btn_gif_convert_pick = QPushButton("Выбрать файлы…"); row_g2.addWidget(self.btn_gif_convert_sel); row_g2.addWidget(self.btn_gif_convert_pick); g.addLayout(row_g2)

        # PDF
        box_pdf = QGroupBox("PNG → PDF конвертор"); p = QVBoxLayout(box_pdf)
        row_p1 = QHBoxLayout()

        row_p1.addWidget(QLabel("Качество JPEG:")); self.pdf_quality = QSpinBox(); self.pdf_quality.setRange(10, 100); self.pdf_quality.setValue(92); row_p1.addWidget(self.pdf_quality)
        row_p1.addSpacing(16); row_p1.addWidget(QLabel("DPI страницы:")); self.pdf_dpi = QSpinBox(); self.pdf_dpi.setRange(50, 1200); self.pdf_dpi.setValue(100); row_p1.addWidget(self.pdf_dpi)
        row_p1.addSpacing(16); self.pdf_one_file = QCheckBox("Один файл"); self.pdf_one_file.setChecked(True); row_p1.addWidget(self.pdf_one_file); row_p1.addStretch(1); p.addLayout(row_p1)
        row_p2 = QHBoxLayout(); row_p2.addStretch(1); self.btn_pdf_convert_sel = QPushButton("Преобразовать выделенные"); self.btn_pdf_convert_pick = QPushButton("Выбрать файлы…"); row_p2.addWidget(self.btn_pdf_convert_sel); row_p2.addWidget(self.btn_pdf_convert_pick); p.addLayout(row_p2)

        # PSD
        box_psd = QGroupBox("PSD → PNG конвертор"); s = QVBoxLayout(box_psd)
        row_s1 = QHBoxLayout(); self.psd_replace = QCheckBox("Заменять файлы"); row_s1.addWidget(self.psd_replace); row_s1.addSpacing(12)
        self.psd_auto_threads = QCheckBox("Авто потоки"); self.psd_auto_threads.setChecked(True); row_s1.addWidget(self.psd_auto_threads); row_s1.addSpacing(12)
        row_s1.addWidget(QLabel("Потоки:")); self.psd_threads = QSpinBox(); self.psd_threads.setRange(1, 8); self.psd_threads.setValue(8); row_s1.addWidget(self.psd_threads); row_s1.addStretch(1); s.addLayout(row_s1)
        row_s2 = QHBoxLayout(); row_s2.addWidget(QLabel("Уровень сжатия PNG (0–9):"));


        self.psd_compress = QSpinBox(); self.psd_compress.setRange(0, 9); self.psd_compress.setValue(7); row_s2.addWidget(self.psd_compress); row_s2.addStretch(1); s.addLayout(row_s2)

        row_s3 = QHBoxLayout()
        row_s3.addStretch(1)
        self.btn_psd_convert_sel = QPushButton("Преобразовать выделенные")
        self.btn_psd_pick = QPushButton("Выбрать файлы...")
        row_s3.addWidget(self.btn_psd_convert_sel)
        row_s3.addWidget(self.btn_psd_pick)
        s.addLayout(row_s3)


        # Примечение
        self.psd_note = QLabel(
            "Примечание: При выборе 1 или 2 очень больших файлов желательно выставлять 1-2 потока."
        )
        self.psd_note.setWordWrap(True)


        self.psd_note.setStyleSheet("color: #666; font-size: 12px;")
        s.addSpacing(6)
        s.addWidget(self.psd_note)




        v.addWidget(box_gif); v.addWidget(box_pdf); v.addWidget(box_psd); v.addStretch(1)

        self.psd_auto_threads.toggled.connect(self._apply_psd_threads_state); self._apply_psd_threads_state()
        self.btn_gif_convert_sel.clicked.connect(self._gif_convert_selected); self.btn_gif_convert_pick.clicked.connect(self._gif_convert_pick)
        self.btn_pdf_convert_sel.clicked.connect(self._pdf_convert_selected); self.btn_pdf_convert_pick.clicked.connect(self._pdf_convert_pick)
        self.btn_psd_pick.clicked.connect(self._psd_pick_convert)
        self.btn_psd_convert_sel.clicked.connect(self._psd_convert_selected)

        # --- persist changes to INI ---
        self.gif_dither.toggled.connect(lambda v: self._save_bool_ini("gif_dither", v))
        self.pdf_quality.valueChanged.connect(lambda v: self._save_int_ini("pdf_quality", v))
        self.pdf_dpi.valueChanged.connect(lambda v: self._save_int_ini("pdf_dpi", v))
        self.pdf_one_file.toggled.connect(lambda v: self._save_bool_ini("pdf_one_file", v))
        self.psd_replace.toggled.connect(lambda v: self._save_bool_ini("psd_replace", v))
        self.psd_auto_threads.toggled.connect(lambda v: self._save_bool_ini("psd_auto_threads", v))
        self.psd_threads.valueChanged.connect(lambda v: self._save_int_ini("psd_threads", v))
        self.psd_compress.valueChanged.connect(lambda v: self._save_int_ini("psd_compress", v))

        QTimer.singleShot(0, self._apply_settings_from_ini)

    def reset_to_defaults(self):
        # дефолты
        d = dict(
            gif_dither=True,
            pdf_quality=92,
            pdf_dpi=100,
            pdf_one_file=True,
            psd_replace=False,
            psd_auto_threads=True,
            psd_threads=8,
            psd_compress=7,
        )

        # UI без шумных сигналов, там где надо
        self.gif_dither.setChecked(d["gif_dither"])
        self.pdf_quality.setValue(d["pdf_quality"])
        self.pdf_dpi.setValue(d["pdf_dpi"])
        self.pdf_one_file.setChecked(d["pdf_one_file"])
        self.psd_replace.setChecked(d["psd_replace"])
        self.psd_auto_threads.setChecked(d["psd_auto_threads"])
        self.psd_threads.setValue(d["psd_threads"])
        self.psd_compress.setValue(d["psd_compress"])

        # сохранить в INI
        self._save_bool_ini("gif_dither", d["gif_dither"])
        self._save_int_ini("pdf_quality", d["pdf_quality"])
        self._save_int_ini("pdf_dpi", d["pdf_dpi"])
        self._save_bool_ini("pdf_one_file", d["pdf_one_file"])
        self._save_bool_ini("psd_replace", d["psd_replace"])
        self._save_bool_ini("psd_auto_threads", d["psd_auto_threads"])
        self._save_int_ini("psd_threads", d["psd_threads"])
        self._save_int_ini("psd_compress", d["psd_compress"])

    def _apply_settings_from_ini(self):
        with group("ConversionsPanel"):
            bind_checkbox(self.gif_dither, "gif_dither", True)
            bind_spinbox(self.pdf_quality, "pdf_quality", 92)
            bind_spinbox(self.pdf_dpi, "pdf_dpi", 100)
            bind_checkbox(self.pdf_one_file, "pdf_one_file", True)
            bind_checkbox(self.psd_replace, "psd_replace", False)
            bind_checkbox(self.psd_auto_threads, "psd_auto_threads", True)
            bind_spinbox(self.psd_threads, "psd_threads", 8)
            bind_spinbox(self.psd_compress, "psd_compress", 7)

    def _save_str_ini(self, key: str, value: str):
        try:
            shadow_attr = f"__{key}__shadow"
            setattr(self, shadow_attr, value)
            with group("ConversionsPanel"):
                save_attr_string(self, shadow_attr, key)
        except Exception:
            pass

    def _save_int_ini(self, key: str, value: int):
        self._save_str_ini(key, str(int(value)))

    def _save_bool_ini(self, key: str, value: bool):
        self._save_str_ini(key, "1" if value else "0")

    def _selected_from_gallery(self, filter_func) -> list[str]:
        if self._gallery and hasattr(self._gallery, 'selected_files'):
            sel = self._gallery.selected_files()
            if sel:
                return filter_func(sel)
        if self._gallery and hasattr(self._gallery, 'files'):
            return filter_func(self._gallery.files())
        return []

    def _ask_out_dir(self, title: str) -> str | None:
        d = QFileDialog.getExistingDirectory(self, title)
        return d or None

    def _apply_psd_threads_state(self):
        self.psd_threads.setEnabled(not self.psd_auto_threads.isChecked())

    def _show_done_box(self, out_dir: str, message: str):
        box = QMessageBox(self); box.setWindowTitle("Готово"); box.setText(message)
        btn_open = box.addButton("Открыть папку", QMessageBox.ActionRole); box.addButton(QMessageBox.Ok)
        box.exec()
        if box.clickedButton() is btn_open:
            _open_in_explorer(out_dir)

    # GIF
    def _gif_convert_selected(self):
        files = self._selected_from_gallery(filter_png_for_gif)
        if not files: QMessageBox.information(self, "PNG→GIF", "Нет выбранных PNG в галерее."); return
        out_dir = self._ask_out_dir("Папка для GIF"); 
        if not out_dir: return
        self._gif_convert(files, out_dir)

    def _gif_convert_pick(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Выберите PNG", "", "PNG (*.png)")
        if not files: return
        out_dir = self._ask_out_dir("Папка для GIF")
        if not out_dir: return
        self._gif_convert(files, out_dir)

    def _gif_convert(self, files: list[str], out_dir: str):
        dither = bool(self.gif_dither.isChecked())
        dlg = QProgressDialog("PNG→GIF: выполняется конвертация…", None, 0, len(files), self)
        dlg.setWindowTitle("Конвертация"); dlg.setWindowModality(Qt.ApplicationModal); dlg.setCancelButton(None); dlg.setMinimumDuration(0); dlg.show(); QApplication.processEvents()
        ok = 0
        for i, src in enumerate(files, 1):
            dst = os.path.join(out_dir, os.path.splitext(os.path.basename(src))[0] + ".gif")
            success, msg = convert_png_to_gif(src, dst, dither=dither)
            if success: ok += 1
            else: QMessageBox.warning(self, "PNG→GIF", f"{os.path.basename(src)}: {msg}")
            dlg.setValue(i); QApplication.processEvents()
        dlg.close(); self._show_done_box(out_dir, f"PNG→GIF: успешно {ok}/{len(files)}")

    # PDF
    def _pdf_convert_selected(self):
        files = self._selected_from_gallery(filter_png_for_pdf)
        if not files: QMessageBox.information(self, "PNG→PDF", "Нет выбранных PNG в галерее."); return
        if self.pdf_one_file.isChecked():
            out_path, _ = QFileDialog.getSaveFileName(self, "Сохранить один PDF как", "images.pdf", "PDF (*.pdf)")
            if not out_path: return
            self._pdf_convert_onefile(files, out_path)
        else:
            out_dir = self._ask_out_dir("Папка для PDF")
            if not out_dir: return
            self._pdf_convert_many(files, out_dir)

    def _pdf_convert_pick(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Выберите PNG", "", "PNG (*.png)")
        if not files: return
        if self.pdf_one_file.isChecked():
            out_path, _ = QFileDialog.getSaveFileName(self, "Сохранить один PDF как", "images.pdf", "PDF (*.pdf)")
            if not out_path: return
            self._pdf_convert_onefile(files, out_path)
        else:
            out_dir = self._ask_out_dir("Папка для PDF")
            if not out_dir: return
            self._pdf_convert_many(files, out_dir)

    def _pdf_convert_many(self, files: list[str], out_dir: str):
        qual = int(self.pdf_quality.value()); dpi = int(self.pdf_dpi.value())
        dlg = QProgressDialog("PNG→PDF: выполняется конвертация…", None, 0, len(files), self)
        dlg.setWindowTitle("Конвертация"); dlg.setWindowModality(Qt.ApplicationModal); dlg.setCancelButton(None); dlg.setMinimumDuration(0); dlg.show(); QApplication.processEvents()
        ok = 0
        for i, src in enumerate(files, 1):
            dst = os.path.join(out_dir, os.path.splitext(os.path.basename(src))[0] + ".pdf")
            success, msg = convert_png_to_pdf(src, dst, jpeg_quality=qual, dpi=dpi)
            if success: ok += 1
            else: QMessageBox.warning(self, "PNG→PDF", f"{os.path.basename(src)}: {msg}")
            dlg.setValue(i); QApplication.processEvents()
        dlg.close(); self._show_done_box(out_dir, f"PNG→PDF: успешно {ok}/{len(files)}")

    def _pdf_convert_onefile(self, files: list[str], out_path: str):
        qual = int(self.pdf_quality.value()); dpi = int(self.pdf_dpi.value())
        dlg = QProgressDialog("PNG→PDF (один файл): выполняется конвертация…", None, 0, 0, self)
        dlg.setWindowTitle("Конвертация"); dlg.setWindowModality(Qt.ApplicationModal); dlg.setCancelButton(None); dlg.setMinimumDuration(0); dlg.show(); QApplication.processEvents()
        success, msg = merge_pngs_to_pdf(files, out_path, jpeg_quality=qual, dpi=dpi)
        dlg.close()
        if success: self._show_done_box(os.path.dirname(out_path), f"PNG→PDF: сохранено {os.path.basename(out_path)}")
        else: QMessageBox.critical(self, "PNG→PDF", f"Ошибка: {msg}")

    # PSD

    def _psd_convert_selected(self):
        files = self._selected_from_gallery(filter_psd)
        if not files:
            QMessageBox.information(self, "PSD→PNG", "Нет выбранных PSD/PSB в галерее.")
            return
        replace = bool(self.psd_replace.isChecked())
        threads = None if self.psd_auto_threads.isChecked() else int(self.psd_threads.value())
        compress = int(self.psd_compress.value())

        out_dir = self._ask_out_dir("Папка для PNG")
        if not out_dir:
            return

        self._psd_convert(files, out_dir, replace, threads, compress)

    def _psd_pick_convert(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Выберите PSD", "", "PSD/PSB (*.psd *.psb)")
        if not files:
            return
        replace = bool(self.psd_replace.isChecked())
        threads = None if self.psd_auto_threads.isChecked() else int(self.psd_threads.value())
        compress = int(self.psd_compress.value())

        # ВСЕГДА спрашиваем папку сохранения, даже при включенной замене файлов
        out_dir = self._ask_out_dir("Папка для PNG")
        if not out_dir:
            return

        self._psd_convert(files, out_dir, replace, threads, compress)

    def _psd_convert(self, files: list[str], out_dir: str | None, replace: bool, threads: int | None, compress: int):

        total = len(files)
        skipped = 0

        # Автопотоки — как в других местах: не перегружаем диск/CPU
        if threads is None:
            cpu = os.cpu_count() or 4
            threads = max(2, min(8, cpu))

        os.makedirs(out_dir or ".", exist_ok=True)

        def _dst_path(dst: str) -> str | None:
            if replace or not os.path.exists(dst):
                return dst
            return None

        tasks = []
        for src in files:
            base = os.path.splitext(os.path.basename(src))[0] + ".png"
            dst = os.path.join(out_dir or os.path.dirname(src), base)

            dst = _dst_path(dst)
            if dst is None:
                skipped += 1
                continue
            tasks.append((src, dst))

        dlg = QProgressDialog("PSD→PNG: выполняется конвертация…", None, 0, len(tasks), self)
        dlg.setWindowTitle("Конвертация")
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setCancelButton(None)
        dlg.setMinimumDuration(0)
        dlg.show();
        QApplication.processEvents()

        ok = 0
        errors = []

        with ThreadPoolExecutor(max_workers=int(threads)) as ex:
            futs = [ex.submit(convert_psd_to_png, src, dst, png_compress_level=compress, optimize=False,
                              strip_metadata=True)
                    for (src, dst) in tasks]
            for i, fut in enumerate(as_completed(futs), 1):
                try:
                    success, msg = fut.result()
                    if success:
                        ok += 1
                    else:
                        errors.append(msg)
                except Exception as e:
                    errors.append(str(e))
                dlg.setValue(i);
                QApplication.processEvents()

        dlg.close()
        self._show_done_box(
            out_dir or os.path.dirname(files[0]),
            f"PSD→PNG: успешно {ok}/{total}, пропущено {skipped}"
        )
        if errors:
            # Покажем первые несколько ошибок, чтобы не заспамить
            err_text = "\n".join(list(dict.fromkeys(errors))[:5])
            QMessageBox.warning(self, "PSD→PNG", f"Некоторые файлы не сконвертированы:\n{err_text}")


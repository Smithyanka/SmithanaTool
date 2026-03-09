from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox, QSpinBox,
    QCheckBox, QMessageBox, QLineEdit, QGridLayout, QDialogButtonBox, QSizePolicy,
    QToolButton, QFrame,
)

from smithanatool_qt.tabs.transform.converters.png_gif import filter_images as filter_png_for_gif
from smithanatool_qt.tabs.transform.converters.png_pdf import filter_images as filter_png_for_pdf
from smithanatool_qt.tabs.transform.converters.psd_png import filter_psd
from smithanatool_qt.tabs.transform.converters.any_png import filter_non_psd as filter_any_for_png

from smithanatool_qt.tabs.common.bind import apply_bindings, reset_bindings, ini_load_bool, ini_save_bool
from smithanatool_qt.tabs.common.defaults import DEFAULTS

from .conversions_dialogs import (
    ensure_qt_ru,
    ask_open_directories_multi,
    ask_out_dir,
    ask_open_files,
    ask_save_file,
)
from .conversions_jobs import (
    png_convert,
    gif_convert,
    pdf_convert_many,
    pdf_convert_onefile,
    pdf_convert_dirs,
    psd_convert,
)

class CollapsibleSection(QWidget):
    toggled = Signal(bool)  # True = развернуто

    def __init__(self, title: str, start_collapsed: bool = False, parent=None):
        super().__init__(parent)
        self._main = QVBoxLayout(self); self._main.setContentsMargins(0, 0, 0, 0)
        self._main.setSpacing(6)

        self.setObjectName("collSection")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._main.setContentsMargins(8, 8, 8, 8)
        self._main.setSpacing(6)

        # Заголовок-кнопка
        self._btn = QToolButton(self)
        self._btn.setObjectName('convSectionHeader')
        self._btn.setText(title)
        self._btn.setCheckable(True)
        self._btn.setChecked(not start_collapsed)   # checked == expanded

        self._btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)  # стрелка слева, текст справа
        self._btn.setAutoRaise(True)  # убирает «кнопочный» вид
        self._btn.setFocusPolicy(Qt.NoFocus)  # без фокуса-рамки
        self._btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)  # кликабельна вся строка
        self._btn.setArrowType(Qt.DownArrow if self._btn.isChecked() else Qt.RightArrow)
        self._btn.clicked.connect(self._on_clicked)
        self._main.addWidget(self._btn)

        # Контент
        self._content = QFrame(self)
        self._content.setObjectName('sectionContent')
        self._content.setFrameShape(QFrame.NoFrame)
        self.content_layout = QVBoxLayout(self._content)
        self.content_layout.setContentsMargins(12, 4, 12, 8)
        self._main.addWidget(self._content)

        self._content.setVisible(self._btn.isChecked())

    def _on_clicked(self):
        expanded = self._btn.isChecked()
        self._btn.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self._content.setVisible(expanded)
        self.toggled.emit(expanded)

    # Удобные методы, если пригодятся
    def set_collapsed(self, collapsed: bool):
        self._btn.setChecked(not collapsed); self._on_clicked()

    def is_collapsed(self) -> bool:
        return not self._btn.isChecked()


class ConversionsPanel(QWidget):
    def __init__(self, gallery=None, parent=None):
        super().__init__(parent)
        self.setObjectName('ConversionsPanel')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._ensure_qt_ru()
        self._gallery = gallery
        v = QVBoxLayout(self); v.setAlignment(Qt.AlignTop)

        # GIF
        gif_collapsed = ini_load_bool("ConversionsPanel", "gif_collapsed", True)
        self.box_gif = CollapsibleSection("GIF конвертор", start_collapsed=gif_collapsed)
        self.box_gif.toggled.connect(lambda expanded: ini_save_bool("ConversionsPanel", "gif_collapsed", not expanded))
        g = self.box_gif.content_layout

        # Ряд 1: Авто потоки + Потоки
        row_g1 = QHBoxLayout()
        self.gif_auto_threads = QCheckBox("Авто потоки");
        self.gif_auto_threads.setChecked(True)
        row_g1.addWidget(self.gif_auto_threads);
        row_g1.addSpacing(12)

        self.gif_lbl_threads = QLabel("Потоки:")
        row_g1.addWidget(self.gif_lbl_threads)

        self.gif_threads = QSpinBox();
        self.gif_threads.setRange(1, 32)
        _default_thr = min(32, max(2, (os.cpu_count() or 4) // 2))
        self.gif_threads.setValue(_default_thr)
        row_g1.addWidget(self.gif_threads)
        row_g1.addStretch(1)
        g.addLayout(row_g1)

        # Ряд 1b: Дизеринг (под потоками)
        row_g1b = QHBoxLayout()
        self.gif_dither = QCheckBox("Дизеринг");
        self.gif_dither.setChecked(True)
        row_g1b.addWidget(self.gif_dither)
        row_g1b.addStretch(1)
        g.addLayout(row_g1b)

        # Ряд 2: кнопки
        row_g2 = QHBoxLayout();
        row_g2.setContentsMargins(0, 8, 0, 0)
        row_g2.addStretch(1)
        self.btn_gif_convert_sel = QPushButton("Преобразовать")
        self.btn_gif_convert_pick = QPushButton("Выбрать файлы…")
        row_g2.addWidget(self.btn_gif_convert_sel);
        row_g2.addWidget(self.btn_gif_convert_pick)
        g.addLayout(row_g2)
        # PDF
        pdf_collapsed = ini_load_bool("ConversionsPanel", "pdf_collapsed", True)
        self.box_pdf = CollapsibleSection("PDF конвертор", start_collapsed=pdf_collapsed)
        self.box_pdf.toggled.connect(lambda expanded: ini_save_bool("ConversionsPanel", "pdf_collapsed", not expanded))
        p = self.box_pdf.content_layout

        # Ряд 1: Качество + DPI
        row_p1 = QHBoxLayout()
        row_p1.addWidget(QLabel("Качество JPEG:"))
        self.pdf_quality = QSpinBox();
        self.pdf_quality.setRange(10, 100);
        self.pdf_quality.setValue(92);
        row_p1.addWidget(self.pdf_quality)
        row_p1.addSpacing(16)
        row_p1.addWidget(QLabel("DPI страницы:"))
        self.pdf_dpi = QSpinBox();
        self.pdf_dpi.setRange(50, 1200);
        self.pdf_dpi.setValue(100);
        row_p1.addWidget(self.pdf_dpi)
        row_p1.addStretch(1)
        p.addLayout(row_p1)

        # Ряд 1b: Один файл (под качеством и DPI)
        row_p1b = QHBoxLayout()
        self.pdf_one_file = QCheckBox("Один файл");
        self.pdf_one_file.setChecked(True)
        row_p1b.addWidget(self.pdf_one_file)
        row_p1b.addStretch(1)
        p.addLayout(row_p1b)

        # Ряд 2: кнопки
        row_p2 = QHBoxLayout();
        row_p2.setContentsMargins(0, 8, 0, 0)
        row_p2.addStretch(1)
        self.btn_pdf_convert_sel = QPushButton("Преобразовать")
        self.btn_pdf_convert_pick = QPushButton("Выбрать файлы…")
        self.btn_pdf_pick_dirs = QPushButton("Выбрать папки…")
        row_p2.addWidget(self.btn_pdf_convert_sel);
        row_p2.addWidget(self.btn_pdf_convert_pick)
        row_p2.addWidget(self.btn_pdf_pick_dirs)
        p.addLayout(row_p2)
        # PSD
        psd_collapsed = ini_load_bool("ConversionsPanel", "psd_collapsed", True)
        self.box_psd = CollapsibleSection("PSD → PNG конвертор", start_collapsed=psd_collapsed)
        self.box_psd.toggled.connect(lambda expanded: ini_save_bool("ConversionsPanel", "psd_collapsed", not expanded))
        s = self.box_psd.content_layout

        # Ряд 1: Авто потоки + Потоки
        row_s1 = QHBoxLayout()
        self.psd_auto_threads = QCheckBox("Авто потоки");
        self.psd_auto_threads.setChecked(True)
        row_s1.addWidget(self.psd_auto_threads);
        row_s1.addSpacing(12)

        self.psd_lbl_threads = QLabel("Потоки:")
        row_s1.addWidget(self.psd_lbl_threads)

        self.psd_threads = QSpinBox();
        self.psd_threads.setRange(1, 8);
        self.psd_threads.setValue(8)
        row_s1.addWidget(self.psd_threads)
        row_s1.addStretch(1)
        s.addLayout(row_s1)

        # Ряд 1b: Заменять файлы (под потоками)
        row_s1b = QHBoxLayout()
        self.psd_replace = QCheckBox("Заменять файлы")
        row_s1b.addWidget(self.psd_replace)
        row_s1b.addStretch(1)
        s.addLayout(row_s1b)

        # Ряд 2: Уровень сжатия
        row_s2 = QHBoxLayout();
        row_s2.addWidget(QLabel("Уровень сжатия PNG (0–9):"))
        self.psd_compress = QSpinBox();
        self.psd_compress.setRange(0, 9);
        self.psd_compress.setValue(7);
        row_s2.addWidget(self.psd_compress)
        row_s2.addStretch(1);
        s.addLayout(row_s2)

        row_s3 = QHBoxLayout()
        row_s3.setContentsMargins(0, 8, 0, 0)
        row_s3.addStretch(1)
        self.btn_psd_convert_sel = QPushButton("Преобразовать")
        self.btn_psd_pick = QPushButton("Выбрать файлы...")
        row_s3.addWidget(self.btn_psd_convert_sel)
        row_s3.addWidget(self.btn_psd_pick)
        s.addLayout(row_s3)

        # Примечение
        self.psd_note = QLabel(
            "Примечание: При выборе 1 или 2 очень больших файлов желательно выставлять 1-2 потока."
        )
        self.psd_note.setWordWrap(True)
        self.psd_note.setObjectName("hintLabel")
        s.addSpacing(6)
        s.addWidget(self.psd_note)

        # PNG
        png_collapsed = ini_load_bool("ConversionsPanel", "png_collapsed", True)
        self.box_png = CollapsibleSection("PNG конвертор", start_collapsed=png_collapsed)
        self.box_png.toggled.connect(lambda expanded: ini_save_bool("ConversionsPanel", "png_collapsed", not expanded))
        n = self.box_png.content_layout

        # Ряд 1: Авто потоки + Потоки
        row_n1 = QHBoxLayout()
        self.png_auto_threads = QCheckBox("Авто потоки");
        self.png_auto_threads.setChecked(True)
        row_n1.addWidget(self.png_auto_threads);
        row_n1.addSpacing(12)

        self.png_lbl_threads = QLabel("Потоки:")
        row_n1.addWidget(self.png_lbl_threads)

        self.png_threads = QSpinBox();
        self.png_threads.setRange(1, 32)
        _default_thr_png = min(32, max(2, (os.cpu_count() or 4) // 2))
        self.png_threads.setValue(_default_thr_png)
        row_n1.addWidget(self.png_threads)
        row_n1.addStretch(1)
        n.addLayout(row_n1)

        # Ряд 1b: Заменять файлы (под потоками)
        row_n1b = QHBoxLayout()
        self.png_replace = QCheckBox("Заменять файлы")
        row_n1b.addWidget(self.png_replace)
        row_n1b.addStretch(1)
        n.addLayout(row_n1b)

        # Ряд 2: Уровень сжатия PNG
        row_n2 = QHBoxLayout()
        row_n2.addWidget(QLabel("Уровень сжатия PNG (0–9):"))
        self.png_compress = QSpinBox();
        self.png_compress.setRange(0, 9);
        self.png_compress.setValue(6);
        row_n2.addWidget(self.png_compress)
        row_n2.addStretch(1)
        n.addLayout(row_n2)

        # Ряд 3: кнопки
        row_n3 = QHBoxLayout()
        row_n3.setContentsMargins(0, 8, 0, 0)
        row_n3.addStretch(1)
        self.btn_png_convert_sel = QPushButton("Преобразовать выделенные")
        self.btn_png_convert_pick = QPushButton("Выбрать файлы…")
        row_n3.addWidget(self.btn_png_convert_sel)
        row_n3.addWidget(self.btn_png_convert_pick)
        n.addLayout(row_n3)

        v.addWidget(self.box_gif); v.addWidget(self.box_pdf); v.addWidget(self.box_psd); v.addWidget(self.box_png); v.addStretch(1)


        # UI state hooks
        self.psd_auto_threads.toggled.connect(self._apply_psd_threads_state); self._apply_psd_threads_state()
        self.gif_auto_threads.toggled.connect(self._apply_gif_threads_state); self._apply_gif_threads_state()
        self.png_auto_threads.toggled.connect(self._apply_png_threads_state);
        self._apply_png_threads_state()

        # Actions
        self.btn_gif_convert_sel.clicked.connect(self._gif_convert_selected); self.btn_gif_convert_pick.clicked.connect(self._gif_convert_pick)
        self.btn_pdf_convert_sel.clicked.connect(self._pdf_convert_selected); self.btn_pdf_convert_pick.clicked.connect(self._pdf_convert_pick)
        self.btn_psd_pick.clicked.connect(self._psd_pick_convert)
        self.btn_psd_convert_sel.clicked.connect(self._psd_convert_selected)
        self.btn_png_convert_sel.clicked.connect(self._png_convert_selected)
        self.btn_png_convert_pick.clicked.connect(self._png_convert_pick)
        self.btn_pdf_pick_dirs.clicked.connect(self._pdf_pick_dirs)



        QTimer.singleShot(0, self._apply_settings_from_ini)

    def _ensure_qt_ru(self) -> None:
        ensure_qt_ru()

    def _ask_open_directories_multi(self, title: str, ini_key: str) -> list[str]:
        return ask_open_directories_multi(self, title, "ConversionsPanel", ini_key)

    def _ask_out_dir(self, title: str, ini_key: str) -> str | None:
        return ask_out_dir(self, title, "ConversionsPanel", ini_key)

    def _ask_open_files(self, title: str, ini_key: str, filter_str: str) -> list[str]:
        return ask_open_files(self, title, "ConversionsPanel", ini_key, filter_str)

    def _ask_save_file(self, title: str, ini_key: str, default_name: str, filter_str: str) -> str | None:
        return ask_save_file(self, title, "ConversionsPanel", ini_key, default_name, filter_str)

    def _pdf_pick_dirs(self) -> None:
        dirs = self._ask_open_directories_multi("Выберите папки с изображениями", "pdf_pick_dirs")
        if not dirs:
            return

        out_dir = self._ask_out_dir("Папка для PDF", "pdf_out_dir")
        if not out_dir:
            return

        qual = int(self.pdf_quality.value())
        dpi = int(self.pdf_dpi.value())
        pdf_convert_dirs(self, dirs, out_dir, jpeg_quality=qual, dpi=dpi)

    def reset_to_defaults(self) -> None:
        reset_bindings(self, "ConversionsPanel")

        # применить зависимые состояния UI
        self._apply_gif_threads_state()
        self._apply_psd_threads_state()
        self._apply_png_threads_state()

    def _apply_settings_from_ini(self) -> None:
        apply_bindings(
            self,
            "ConversionsPanel",
            [
                # GIF
                (self.gif_dither, "gif_dither", True),
                (self.gif_auto_threads, "gif_auto_threads", True),
                (self.gif_threads, "gif_threads", DEFAULTS["threads"]),

                # PDF
                (self.pdf_quality, "pdf_quality", 92),
                (self.pdf_dpi, "pdf_dpi", 100),
                (self.pdf_one_file, "pdf_one_file", True),

                # PSD→PNG
                (self.psd_replace, "psd_replace", False),
                (self.psd_auto_threads, "psd_auto_threads", True),
                (self.psd_threads, "psd_threads", 8),
                (self.psd_compress, "psd_compress", 7),

                # PNG
                (self.png_replace, "png_replace", False),
                (self.png_auto_threads, "png_auto_threads", True),
                (self.png_threads, "png_threads", DEFAULTS["threads"]),
                (self.png_compress, "png_compress", 6),
            ],
        )

        # После биндинга — обновить доступность «Потоков»
        self._apply_gif_threads_state()
        self._apply_psd_threads_state()
        self._apply_png_threads_state()

    def _selected_from_gallery(self, filter_func) -> list[str]:
        if self._gallery and hasattr(self._gallery, "selected_files"):
            sel = self._gallery.selected_files()
            if sel:
                return filter_func(sel)
        if self._gallery and hasattr(self._gallery, "files"):
            return filter_func(self._gallery.files())
        return []

    def _apply_gif_threads_state(self) -> None:
        on = not self.gif_auto_threads.isChecked()
        self.gif_threads.setEnabled(on)
        if hasattr(self, "gif_lbl_threads"):
            self.gif_lbl_threads.setEnabled(on)

    def _apply_psd_threads_state(self) -> None:
        on = not self.psd_auto_threads.isChecked()
        self.psd_threads.setEnabled(on)
        if hasattr(self, "psd_lbl_threads"):
            self.psd_lbl_threads.setEnabled(on)

    def _apply_png_threads_state(self) -> None:
        on = not self.png_auto_threads.isChecked()
        self.png_threads.setEnabled(on)
        if hasattr(self, "png_lbl_threads"):
            self.png_lbl_threads.setEnabled(on)

    def _resolve_gif_threads(self) -> int:
        """Логика 'как в StitchSection': осторожный авто-подбор потоков."""
        if self.gif_auto_threads.isChecked():
            c = os.cpu_count() or 2
            if c <= 2:
                auto = 1
            elif c <= 4:
                auto = 2
            elif c <= 8:
                auto = 4
            else:
                auto = min(8, c - 2)
            return max(1, min(8, auto))

        try:
            val = int(self.gif_threads.value())
        except Exception:
            val = 1
        return max(1, min(32, val))

    def _resolve_png_threads(self) -> int:
        """Аккуратный авто-подбор потоков, как в других конверторах."""
        try:
            cpu = os.cpu_count() or 4
            return max(2, min(32, cpu // 2))
        except Exception:
            return 2

    # PNG (generic)
    def _png_convert_selected(self) -> None:
        files = self._selected_from_gallery(filter_any_for_png)
        if not files:
            QMessageBox.information(self, "PNG конвертор", "Нет подходящих файлов в галерее (PSD/PSB исключены).")
            return

        replace = bool(self.png_replace.isChecked())
        threads = None if self.png_auto_threads.isChecked() else int(self.png_threads.value())
        compress = int(self.png_compress.value())
        out_dir = self._ask_out_dir("Папка для PNG", "png_out_dir")
        if not out_dir:
            return

        self._png_convert(files, out_dir, replace, threads, compress)

    def _png_convert_pick(self) -> None:
        # Разрешаем выбрать любые файлы; PSD/PSB отфильтруем
        files = self._ask_open_files("Выберите файлы (все, кроме PSD/PSB)", "png_pick_dir", "Все файлы (*.*)")
        if not files:
            return

        files = [f for f in files if not f.lower().endswith((".psd", ".psb"))]
        if not files:
            QMessageBox.information(self, "PNG конвертор", "Все выбранные файлы — PSD/PSB, используйте PSD → PNG.")
            return

        out_dir = self._ask_out_dir("Папка для PNG", "png_out_dir")
        if not out_dir:
            return

        replace = bool(self.png_replace.isChecked())
        threads = None if self.png_auto_threads.isChecked() else int(self.png_threads.value())
        compress = int(self.png_compress.value())
        self._png_convert(files, out_dir, replace, threads, compress)

    def _png_convert(
        self,
        files: list[str],
        out_dir: str,
        replace: bool,
        threads: int | None,
        compress: int,
    ) -> None:
        if threads is None:
            threads = self._resolve_png_threads()
        png_convert(self, files, out_dir, replace=replace, threads=int(threads), compress=int(compress))

    # PNG -> GIF
    def _gif_convert_selected(self) -> None:
        files = self._selected_from_gallery(filter_png_for_gif)
        if not files:
            QMessageBox.information(self, "PNG→GIF", "Нет выбранных картинок в галерее.")
            return

        out_dir = self._ask_out_dir("Папка для GIF", "gif_out_dir")
        if not out_dir:
            return

        self._gif_convert(files, out_dir)

    def _gif_convert_pick(self) -> None:
        files = self._ask_open_files(
            "Выберите изображения",
            "gif_pick_dir",
            "Изображения (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff *.gif)",
        )
        if not files:
            return

        out_dir = self._ask_out_dir("Папка для GIF", "gif_out_dir")
        if not out_dir:
            return

        self._gif_convert(files, out_dir)

    def _gif_convert(self, files: list[str], out_dir: str) -> None:
        dither = bool(self.gif_dither.isChecked())
        total = len(files)
        workers = self._resolve_gif_threads()
        workers = max(1, min(workers, total))
        gif_convert(self, files, out_dir, dither=dither, workers=int(workers))

    # PNG -> PDF
    def _pdf_convert_selected(self) -> None:
        files = self._selected_from_gallery(filter_png_for_pdf)
        if not files:
            QMessageBox.information(self, "PNG→PDF", "Нет выбранных картинок в галерее.")
            return

        if self.pdf_one_file.isChecked():
            out_path = self._ask_save_file("Сохранить один PDF как", "pdf_save_dir", "images.pdf", "PDF (*.pdf)")
            if not out_path:
                return
            self._pdf_convert_onefile(files, out_path)
        else:
            out_dir = self._ask_out_dir("Папка для PDF", "pdf_out_dir")
            if not out_dir:
                return
            self._pdf_convert_many(files, out_dir)

    def _pdf_convert_pick(self) -> None:
        files = self._ask_open_files(
            "Выберите изображения",
            "pdf_pick_dir",
            "Изображения (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff *.gif)",
        )
        if not files:
            return

        if self.pdf_one_file.isChecked():
            out_path = self._ask_save_file("Сохранить один PDF как", "pdf_save_dir", "images.pdf", "PDF (*.pdf)")
            if not out_path:
                return
            self._pdf_convert_onefile(files, out_path)
        else:
            out_dir = self._ask_out_dir("Папка для PDF", "pdf_out_dir")
            if not out_dir:
                return
            self._pdf_convert_many(files, out_dir)

    def _pdf_convert_many(self, files: list[str], out_dir: str) -> None:
        qual = int(self.pdf_quality.value())
        dpi = int(self.pdf_dpi.value())
        pdf_convert_many(self, files, out_dir, jpeg_quality=qual, dpi=dpi)

    def _pdf_convert_onefile(self, files: list[str], out_path: str) -> None:
        qual = int(self.pdf_quality.value())
        dpi = int(self.pdf_dpi.value())
        pdf_convert_onefile(self, files, out_path, jpeg_quality=qual, dpi=dpi)

    # PSD -> PNG
    def _psd_convert_selected(self) -> None:
        files = self._selected_from_gallery(filter_psd)
        if not files:
            QMessageBox.information(self, "PSD→PNG", "Нет выбранных PSD/PSB в галерее.")
            return

        replace = bool(self.psd_replace.isChecked())
        threads = None if self.psd_auto_threads.isChecked() else int(self.psd_threads.value())
        compress = int(self.psd_compress.value())
        out_dir = self._ask_out_dir("Папка для PNG", "psd_out_dir")
        if not out_dir:
            return

        self._psd_convert(files, out_dir, replace, threads, compress)

    def _psd_pick_convert(self) -> None:
        files = self._ask_open_files("Выберите PSD", "psd_pick_dir", "PSD/PSB (*.psd *.psb)")
        if not files:
            return

        replace = bool(self.psd_replace.isChecked())
        threads = None if self.psd_auto_threads.isChecked() else int(self.psd_threads.value())
        compress = int(self.psd_compress.value())

        # ВСЕГДА спрашиваем папку сохранения, даже при включенной замене файлов
        out_dir = self._ask_out_dir("Папка для PNG", "psd_out_dir")
        if not out_dir:
            return

        self._psd_convert(files, out_dir, replace, threads, compress)

    def _psd_convert(
        self,
        files: list[str],
        out_dir: str | None,
        replace: bool,
        threads: int | None,
        compress: int,
    ) -> None:
        psd_convert(self, files, out_dir, replace=replace, threads=threads, compress=int(compress))

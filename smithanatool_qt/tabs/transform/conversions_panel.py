from __future__ import annotations
from typing import List
import os, sys, subprocess
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox, QSpinBox,
    QCheckBox, QFileDialog, QMessageBox, QProgressDialog, QApplication, QListView, QTreeView, QAbstractItemView, QLineEdit, QGridLayout, QDialogButtonBox, QSplitter, QSizePolicy, QToolButton, QFrame
)
from PySide6.QtGui import QAction
import re
from PySide6.QtCore import Qt, QTimer, QTranslator, QLocale, QLibraryInfo, Signal
from .converters.png_gif import filter_images as filter_png_for_gif, convert_png_to_gif
from .converters.png_pdf import filter_images as filter_png_for_pdf, convert_png_to_pdf, merge_pngs_to_pdf, merge_images_to_pdf
from .converters.psd_png import filter_psd, convert_psd_to_png

from smithanatool_qt.settings_bind import (
    group, bind_spinbox, bind_checkbox, save_attr_string
)
from concurrent.futures import ThreadPoolExecutor, as_completed

from .converters.any_png import filter_non_psd as filter_any_for_png, convert_any_to_png
from smithanatool_qt.tabs.common.bind import apply_bindings
from smithanatool_qt.tabs.common.defaults import DEFAULTS

class CollapsibleSection(QWidget):
    toggled = Signal(bool)  # True = развернуто

    def __init__(self, title: str, start_collapsed: bool = False, parent=None):
        super().__init__(parent)
        self._main = QVBoxLayout(self); self._main.setContentsMargins(0, 0, 0, 0)
        self._main.setSpacing(6)

        self.setObjectName("collSection")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("""
            #collSection {
                border: 1px solid palette(mid);
                border-radius: 4px;
                background: transparent;
            }
        """)
        self._main.setContentsMargins(8, 8, 8, 8)
        self._main.setSpacing(6)

        # Заголовок-кнопка
        self._btn = QToolButton(self)
        self._btn.setText(title)
        self._btn.setCheckable(True)
        self._btn.setChecked(not start_collapsed)   # checked == expanded

        self._btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)  # стрелка слева, текст справа
        self._btn.setAutoRaise(True)  # убирает «кнопочный» вид
        self._btn.setFocusPolicy(Qt.NoFocus)  # без фокуса-рамки
        self._btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)  # кликабельна вся строка
        self._btn.setStyleSheet("""
            QToolButton { background: transparent; border: none; padding: 4px 0; }
            QToolButton:hover { background: transparent; }
            QToolButton:pressed { background: transparent; }
        """)
        self._btn.setArrowType(Qt.DownArrow if self._btn.isChecked() else Qt.RightArrow)
        self._btn.clicked.connect(self._on_clicked)
        self._main.addWidget(self._btn)

        # Контент
        self._content = QFrame(self)
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
        self._ensure_qt_ru()
        self._gallery = gallery
        v = QVBoxLayout(self); v.setAlignment(Qt.AlignTop)

        # GIF
        gif_collapsed = (self._ini_load_str("gif_collapsed", "1") == "1")
        self.box_gif = CollapsibleSection("GIF конвертор", start_collapsed=gif_collapsed)
        self.box_gif.toggled.connect(lambda expanded: self._save_bool_ini("gif_collapsed", not expanded))
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
        pdf_collapsed = (self._ini_load_str("pdf_collapsed", "1") == "1")
        self.box_pdf = CollapsibleSection("PDF конвертор", start_collapsed=pdf_collapsed)
        self.box_pdf.toggled.connect(lambda expanded: self._save_bool_ini("pdf_collapsed", not expanded))
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
        psd_collapsed = (self._ini_load_str("psd_collapsed", "1") == "1")
        self.box_psd = CollapsibleSection("PSD → PNG конвертор", start_collapsed=psd_collapsed)
        self.box_psd.toggled.connect(lambda expanded: self._save_bool_ini("psd_collapsed", not expanded))
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
        self.psd_note.setStyleSheet("color: #454545; font-size: 12px;")
        s.addSpacing(6)
        s.addWidget(self.psd_note)

        # PNG
        png_collapsed = (self._ini_load_str("png_collapsed", "1") == "1")
        self.box_png = CollapsibleSection("PNG конвертор", start_collapsed=png_collapsed)
        self.box_png.toggled.connect(lambda expanded: self._save_bool_ini("png_collapsed", not expanded))
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

    def _ensure_qt_ru(self):
        app = QApplication.instance()
        if not app or getattr(app, "_qt_ru_installed", False):
            return

        try:
            # Глобально русская локаль
            QLocale.setDefault(QLocale(QLocale.Russian, QLocale.Russia))
        except Exception:
            pass

        tr_path = QLibraryInfo.path(QLibraryInfo.TranslationsPath)
        installed = []

        # qtbase_ru
        try:
            tr1 = QTranslator(app)
            ok1 = tr1.load(QLocale("ru_RU"), "qtbase", "_", tr_path) or tr1.load("qtbase_ru", tr_path)
            if ok1:
                app.installTranslator(tr1)
                installed.append(tr1)
        except Exception:
            pass

        # qt_ru (иногда не требуется, но не помешает)
        try:
            tr2 = QTranslator(app)
            ok2 = tr2.load(QLocale("ru_RU"), "qt", "_", tr_path) or tr2.load("qt_ru", tr_path)
            if ok2:
                app.installTranslator(tr2)
                installed.append(tr2)
        except Exception:
            pass

        app._qt_ru_installed = True
        self._qt_ru_translators = installed

    def _ask_open_directories_multi(self, title: str, ini_key: str) -> list[str]:
        start_dir = self._ini_load_str(ini_key, os.path.expanduser("~"))

        dlg = QFileDialog(self, title)
        dlg.setFileMode(QFileDialog.Directory)
        dlg.setOption(QFileDialog.ShowDirsOnly, True)
        dlg.setOption(QFileDialog.DontUseNativeDialog, True)  # для мультивыбора папок
        dlg.setDirectory(start_dir)

        # Разрешаем расширенный выбор в списке/дереве (кроме sidebar)
        for v in dlg.findChildren(QListView) + dlg.findChildren(QTreeView):
            if v.objectName() != "sidebar":
                v.setSelectionMode(QAbstractItemView.ExtendedSelection)

        # Скрыть левую боковую панель (sidebar) и схлопнуть сплиттер
        try:
            for side in dlg.findChildren(QListView, "sidebar"):
                side.hide()
            for w in dlg.findChildren(QWidget):
                if w.objectName() == "sidebar":
                    w.hide()
            for sp in dlg.findChildren(QSplitter):
                sizes = sp.sizes()
                if len(sizes) >= 2:
                    sp.setSizes([0] + sizes[1:])
        except Exception:
            pass

        # ---------- СКРЫТЬ кнопку «Создать папку» ----------
        try:
            # Спрятать кнопку на тулбаре
            for b in dlg.findChildren(QToolButton):
                tt = (b.toolTip() or "").lower()
                tx = (b.text() or "").lower()
                if ("создать папку" in tt) or ("создать папку" in tx) or ("new folder" in tt) or ("new folder" in tx):
                    b.hide()
            # Отключить одноимённые действия (на случай хоткеев)
            for act in dlg.findChildren(QAction):
                txt = (act.text() or "").lower().replace("&", "")
                ttp = (act.toolTip() or "").lower()
                if ("создать папку" in txt) or ("создать папку" in ttp) or ("new folder" in txt) or ("new folder" in ttp):
                    act.setEnabled(False)
                    act.setVisible(False)
        except Exception:
            pass
        # ---------------------------------------------------

        # --- Автопереход по полю «Каталог» через 300 мс ---
        try:
            # В ненативном диалоге у поля обычно objectName == "fileNameEdit"
            dir_edit = dlg.findChild(QLineEdit, "fileNameEdit")
            if dir_edit is None:
                edits = [e for e in dlg.findChildren(QLineEdit) if e.isVisible()]
                if edits:
                    dir_edit = sorted(edits, key=lambda e: e.geometry().y())[-1]

            if dir_edit is not None:
                nav_timer = QTimer(dlg)
                nav_timer.setInterval(300)
                nav_timer.setSingleShot(True)

                def _navigate():
                    raw = (dir_edit.text() or "").strip().strip('"')
                    if not raw:
                        return
                    # Абсолютный или относительный путь
                    path = raw
                    try:
                        cur = dlg.directory().absolutePath()
                    except Exception:
                        cur = start_dir
                    if not os.path.isabs(path):
                        path = os.path.join(cur, raw)
                    if os.path.isdir(path):
                        try:
                            dlg.setDirectory(path)  # переходим, но НЕ выделяем
                        except Exception:
                            pass

                dir_edit.textEdited.connect(lambda _=None: nav_timer.start())
                nav_timer.timeout.connect(_navigate)
        except Exception:
            pass
        # --- конец автоперехода ---

        if dlg.exec() == QFileDialog.Accepted:
            paths = [p for p in dlg.selectedFiles() if os.path.isdir(p)]
            if paths:
                try:
                    common = os.path.commonpath(paths)
                except Exception:
                    common = os.path.dirname(paths[0])
                self._save_str_ini(ini_key, common)
            return paths
        return []

    def _ensure_unique_path(self, path: str) -> str:
        """Если файл уже существует, добавляет суффикс (2), (3), ..."""
        root, ext = os.path.splitext(path)
        cand = path
        k = 2
        while os.path.exists(cand):
            cand = f"{root} ({k}){ext}"
            k += 1
        return cand

    def _natural_key(self, s: str):
        """Ключ для «естественной» сортировки: file2 < file10."""
        return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', os.path.basename(s))]

    def _pdf_pick_dirs(self):
        """
        PNG→PDF по папкам: выбор, сохранение и конвертация.
        Исправление «белого окна» — сначала показываем диалог в режиме занятости (0..0),
        принудительно отрисовываем его, затем переводим в обычный прогресс и запускаем пул.
        """
        dirs = self._ask_open_directories_multi("Выберите папки с изображениями", "pdf_pick_dirs")
        if not dirs:
            return

        out_dir = self._ask_out_dir("Папка для PDF", "pdf_out_dir")
        if not out_dir:
            return

        qual = int(self.pdf_quality.value())
        dpi = int(self.pdf_dpi.value())

        # --- ПРОГРЕСС-ДИАЛОГ ---
        dlg = QProgressDialog(self)
        dlg.setWindowTitle("Конвертация")
        dlg.setLabelText("PNG→PDF (папки): выполняется конвертация…")
        dlg.setCancelButton(None)
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.setMinimumDuration(0)

        # Показать сразу с занятым состоянием
        dlg.setRange(0, 0)
        dlg.setValue(0)
        dlg.resize(dlg.sizeHint())
        dlg.show()
        QApplication.processEvents()
        dlg.repaint()
        QApplication.processEvents()
        # ----------------------------------------------------------------------

        dlg.setRange(0, len(dirs))
        dlg.setValue(0)
        QApplication.processEvents()

        ok = 0
        skipped = 0
        errors: list[str] = []

        def _task_dir(d: str):
            try:
                candidates = [os.path.join(d, name) for name in os.listdir(d)
                              if os.path.isfile(os.path.join(d, name))]
                imgs = filter_png_for_pdf(candidates)
                imgs.sort(key=self._natural_key)

                if not imgs:
                    return ("skipped", d, None)

                base_name = os.path.basename(os.path.normpath(d)) or "output"
                dst_pdf = self._ensure_unique_path(os.path.join(out_dir, f"{base_name}.pdf"))

                success, msg = merge_images_to_pdf(imgs, dst_pdf, jpeg_quality=qual, dpi=dpi)
                return ("ok", d, None) if success else ("error", d, f"{base_name}: {msg}")
            except Exception as e:
                return ("error", d, f"{os.path.basename(d) or d}: {e}")

        from concurrent.futures import ThreadPoolExecutor, as_completed
        workers = min(max(1, (os.cpu_count() or 2) // 2), 8)
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(_task_dir, d) for d in dirs]
            for i, fut in enumerate(as_completed(futs), 1):
                try:
                    status, d, msg = fut.result()
                    if status == "ok":
                        ok += 1
                    elif status == "skipped":
                        skipped += 1
                    elif status == "error" and msg:
                        errors.append(msg)
                except Exception as e:
                    errors.append(str(e))
                finally:
                    dlg.setValue(i)
                    QApplication.processEvents()

        dlg.close()
        self._show_done_box(out_dir, f"PNG→PDF (папки): успешно {ok}/{len(dirs)}, пустых {skipped}")
        if errors:
            uniq = list(dict.fromkeys(errors))[:5]
            QMessageBox.warning(self, "PNG→PDF (папки)", "Некоторые папки не обработаны:\n" + "\n".join(uniq))


    def reset_to_defaults(self):
        # дефолты
        d = dict(
            gif_dither=True,
            gif_auto_threads=True,
            gif_threads=min(32, max(2, (os.cpu_count() or 4)//2)),

            pdf_quality=92,
            pdf_dpi=100,
            pdf_one_file=True,
            psd_replace=False,
            psd_auto_threads=True,
            psd_threads=8,
            psd_compress=7,

            png_replace=False,
            png_auto_threads=True,
            png_threads=min(32, max(2, (os.cpu_count() or 4) // 2)),
            png_compress=6,
        )

        self.gif_dither.setChecked(d["gif_dither"])
        self.gif_auto_threads.setChecked(d["gif_auto_threads"])
        self.gif_threads.setValue(d["gif_threads"])

        self.pdf_quality.setValue(d["pdf_quality"])
        self.pdf_dpi.setValue(d["pdf_dpi"])
        self.pdf_one_file.setChecked(d["pdf_one_file"])
        self.psd_replace.setChecked(d["psd_replace"])
        self.psd_auto_threads.setChecked(d["psd_auto_threads"])
        self.psd_threads.setValue(d["psd_threads"])
        self.psd_compress.setValue(d["psd_compress"])

        self.png_replace.setChecked(d["png_replace"])
        self.png_auto_threads.setChecked(d["png_auto_threads"])
        self.png_threads.setValue(d["png_threads"])
        self.png_compress.setValue(d["png_compress"])

        # сохранить в INI
        self._save_bool_ini("gif_dither", d["gif_dither"])
        self._save_bool_ini("gif_auto_threads", d["gif_auto_threads"])
        self._save_int_ini("gif_threads", d["gif_threads"])

        self._save_int_ini("pdf_quality", d["pdf_quality"])
        self._save_int_ini("pdf_dpi", d["pdf_dpi"])
        self._save_bool_ini("pdf_one_file", d["pdf_one_file"])
        self._save_bool_ini("psd_replace", d["psd_replace"])
        self._save_bool_ini("psd_auto_threads", d["psd_auto_threads"])
        self._save_int_ini("psd_threads", d["psd_threads"])
        self._save_int_ini("psd_compress", d["psd_compress"])

        self._save_bool_ini("png_replace", d["png_replace"])
        self._save_bool_ini("png_auto_threads", d["png_auto_threads"])
        self._save_int_ini("png_threads", d["png_threads"])
        self._save_int_ini("png_compress", d["png_compress"])

        self._apply_gif_threads_state()
        self._apply_psd_threads_state()

        #  сброс состояний секций конверторов
        # self._save_bool_ini("gif_collapsed", True)
        # self._save_bool_ini("pdf_collapsed", True)
        # self._save_bool_ini("psd_collapsed", True)
        # self._save_bool_ini("png_collapsed", True)
        #
        # for w in (getattr(self, "box_gif", None),
        #           getattr(self, "box_pdf", None),
        #           getattr(self, "box_psd", None),
        #           getattr(self, "box_png", None)):
        #     if w is None:
        #         continue
        #     prev = w.blockSignals(True)
        #     w.set_collapsed(True)
        #     w.blockSignals(prev)

    def _apply_settings_from_ini(self):
        apply_bindings(self, "ConversionsPanel", [
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
        ])
        # После биндинга — обновить доступность «Потоков»
        self._apply_gif_threads_state()
        self._apply_psd_threads_state()
        self._apply_png_threads_state()

    def _ini_load_str(self, key: str, default: str = "") -> str:
        try:
            shadow_attr = f"__{key}__shadow"
            setattr(self, shadow_attr, default)
            with group("ConversionsPanel"):
                from smithanatool_qt.settings_bind import bind_attr_string  # локальный импорт
                bind_attr_string(self, shadow_attr, key, default)
            return getattr(self, shadow_attr, default)
        except Exception:
            return default
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

    def _ask_out_dir(self, title: str, ini_key: str) -> str | None:
        start_dir = self._ini_load_str(ini_key, os.path.expanduser("~"))
        d = QFileDialog.getExistingDirectory(self, title, start_dir)
        if d:
            self._save_str_ini(ini_key, d)
        return d or None

    def _ask_open_files(self, title: str, ini_key: str, filter_str: str) -> list[str]:
        start_dir = self._ini_load_str(ini_key, os.path.expanduser("~"))
        files, _ = QFileDialog.getOpenFileNames(self, title, start_dir, filter_str)
        if files:
            self._save_str_ini(ini_key, os.path.dirname(files[0]))
        return files

    def _ask_save_file(self, title: str, ini_key: str, default_name: str, filter_str: str) -> str | None:
        start_dir = self._ini_load_str(ini_key, os.path.expanduser("~"))
        start_path = os.path.join(start_dir, default_name)
        path, _ = QFileDialog.getSaveFileName(self, title, start_path, filter_str)
        if path:
            self._save_str_ini(ini_key, os.path.dirname(path))
        return path or None

    def _apply_gif_threads_state(self):
        on = not self.gif_auto_threads.isChecked()
        self.gif_threads.setEnabled(on)
        if hasattr(self, "gif_lbl_threads"):
            self.gif_lbl_threads.setEnabled(on)

    def _apply_psd_threads_state(self):
        on = not self.psd_auto_threads.isChecked()
        self.psd_threads.setEnabled(on)
        if hasattr(self, "psd_lbl_threads"):
            self.psd_lbl_threads.setEnabled(on)

    def _apply_png_threads_state(self):
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
    def _png_convert_selected(self):
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

    def _png_convert_pick(self):
        # Разрешаем выбрать любые файлы; PSD/PSB отфильтруем
        files = self._ask_open_files("Выберите файлы (все, кроме PSD/PSB)", "png_pick_dir", "Все файлы (*.*)")
        if not files:
            return
        files = [f for f in files if not f.lower().endswith(('.psd', '.psb'))]
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

    def _png_convert(self, files: list[str], out_dir: str, replace: bool, threads: int | None, compress: int):
        total = len(files)
        os.makedirs(out_dir or ".", exist_ok=True)

        # Потоки
        if threads is None:
            threads = self._resolve_png_threads()
        threads = max(1, min(32, threads))

        # Подготовка задач
        tasks = []
        skipped = 0
        for src in files:
            base = os.path.splitext(os.path.basename(src))[0] + ".png"
            dst = os.path.join(out_dir, base)
            if (not replace) and os.path.exists(dst):
                skipped += 1
                continue
            tasks.append((src, dst))

        if not tasks:
            QMessageBox.information(self, "PNG конвертор",
                                    "Нечего конвертировать (возможно, все выходные файлы уже существуют).")
            return

        dlg = QProgressDialog("Конвертация в PNG…", None, 0, len(tasks), self)
        dlg.setWindowTitle("Конвертация")
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setCancelButton(None)
        dlg.setMinimumDuration(0)
        dlg.show();
        QApplication.processEvents()

        ok = 0
        errors: list[str] = []

        def _task(src: str, dst: str):
            return convert_any_to_png(src, dst, png_compress_level=compress, optimize=False, strip_metadata=True)

        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=int(threads)) as ex:
            futs = [ex.submit(_task, src, dst) for (src, dst) in tasks]
            for i, fut in enumerate(as_completed(futs), 1):
                try:
                    success, msg = fut.result()
                    if success:
                        ok += 1
                    else:
                        errors.append(f"{os.path.basename(msg) if os.path.isabs(msg) else msg}")
                except Exception as e:
                    errors.append(str(e))
                dlg.setValue(i);
                QApplication.processEvents()

        dlg.close()
        self._show_done_box(out_dir, f"→ PNG: успешно {ok}/{len(tasks)}, пропущено {skipped}")
        if errors:
            uniq = list(dict.fromkeys(errors))[:5]
            QMessageBox.warning(self, "PNG конвертор", "Некоторые файлы не сконвертированы:\n" + "\n".join(uniq))

    def _show_done_box(self, out_dir: str, message: str):
        box = QMessageBox(self); box.setWindowTitle("Готово"); box.setText(message)
        btn_open = box.addButton("Открыть папку", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.exec()
        if box.clickedButton() is btn_open:
            _open_in_explorer(out_dir)

    # GIF
    def _gif_convert_selected(self):
        files = self._selected_from_gallery(filter_png_for_gif)
        if not files: QMessageBox.information(self, "PNG→GIF", "Нет выбранных картинок в галерее."); return
        out_dir = self._ask_out_dir("Папка для GIF", "gif_out_dir")
        if not out_dir: return
        self._gif_convert(files, out_dir)

    def _gif_convert_pick(self):
        files = self._ask_open_files("Выберите изображения", "gif_pick_dir",
                                     "Изображения (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff *.gif)")
        if not files: return
        out_dir = self._ask_out_dir("Папка для GIF", "gif_out_dir")
        if not out_dir: return
        self._gif_convert(files, out_dir)

    def _gif_convert(self, files: list[str], out_dir: str):
        dither = bool(self.gif_dither.isChecked())
        os.makedirs(out_dir, exist_ok=True)

        total = len(files)
        workers = self._resolve_gif_threads()
        workers = max(1, min(workers, total))

        dlg = QProgressDialog("PNG→GIF: выполняется конвертация…", None, 0, total, self)
        dlg.setWindowTitle("Конвертация"); dlg.setWindowModality(Qt.ApplicationModal); dlg.setCancelButton(None); dlg.setMinimumDuration(0); dlg.show(); QApplication.processEvents()

        ok = 0
        errors: list[str] = []

        def _task(src: str, dst: str):
            return convert_png_to_gif(src, dst, dither=dither)

        # подготовим все назначения
        tasks = []
        for src in files:
            base = os.path.splitext(os.path.basename(src))[0] + ".gif"
            dst = os.path.join(out_dir, base)
            tasks.append((src, dst))

        # параллельно, но без перегруза
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(_task, s, d) for (s, d) in tasks]
            for i, fut in enumerate(as_completed(futs), 1):
                try:
                    success, msg = fut.result()
                    if success:
                        ok += 1
                    else:
                        errors.append(f"{os.path.basename(msg) if os.path.isabs(msg) else msg}")
                except Exception as e:
                    errors.append(str(e))
                dlg.setValue(i); QApplication.processEvents()

        dlg.close()
        self._show_done_box(out_dir, f"PNG→GIF: успешно {ok}/{total}")
        if errors:
            # Покажем до 5 уникальных ошибок
            uniq = list(dict.fromkeys(errors))[:5]
            QMessageBox.warning(self, "PNG→GIF", "Некоторые файлы не сконвертированы:\n" + "\n".join(uniq))

    # PDF
    def _pdf_convert_selected(self):
        files = self._selected_from_gallery(filter_png_for_pdf)
        if not files: QMessageBox.information(self, "PNG→PDF", "Нет выбранных картинок в галерее."); return
        if self.pdf_one_file.isChecked():
            out_path = self._ask_save_file("Сохранить один PDF как", "pdf_save_dir", "images.pdf", "PDF (*.pdf)")
            if not out_path: return
            self._pdf_convert_onefile(files, out_path)
        else:
            out_dir = self._ask_out_dir("Папка для PDF", "pdf_out_dir")
            if not out_dir: return
            self._pdf_convert_many(files, out_dir)

    def _pdf_convert_pick(self):
        files = self._ask_open_files("Выберите изображения", "pdf_pick_dir",
                                     "Изображения (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff *.gif)")
        if not files: return
        if self.pdf_one_file.isChecked():
            out_path = self._ask_save_file("Сохранить один PDF как", "pdf_save_dir", "images.pdf", "PDF (*.pdf)")
            if not out_path: return
            self._pdf_convert_onefile(files, out_path)
        else:
            out_dir = self._ask_out_dir("Папка для PDF", "pdf_out_dir")
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
        out_dir = self._ask_out_dir("Папка для PNG", "psd_out_dir")
        if not out_dir: return
        self._psd_convert(files, out_dir, replace, threads, compress)

    def _psd_pick_convert(self):
        files = self._ask_open_files("Выберите PSD", "psd_pick_dir", "PSD/PSB (*.psd *.psb)")
        if not files:
            return
        replace = bool(self.psd_replace.isChecked())
        threads = None if self.psd_auto_threads.isChecked() else int(self.psd_threads.value())
        compress = int(self.psd_compress.value())

        # ВСЕГДА спрашиваем папку сохранения, даже при включенной замене файлов
        out_dir = self._ask_out_dir("Папка для PNG", "psd_out_dir")
        if not out_dir: return
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
            err_text = "\n".join(list(dict.fromkeys(errors))[:5])
            QMessageBox.warning(self, "PSD→PNG", f"Некоторые файлы не сконвертированы:\n{err_text}")

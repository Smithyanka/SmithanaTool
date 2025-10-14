from __future__ import annotations
from typing import List, Optional, Callable
import os

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QAbstractItemView, QComboBox, QListWidgetItem, QMessageBox, QFrame
)
from PySide6.QtGui import QGuiApplication, QKeySequence, QAction, QIcon, QPixmap, QImage

from ..common import is_image, dedup_keep_order
from .widgets import RightSelectableList
from .settings_mixin import IniStringsMixin
from . import io, sort, menu, list_ops

from smithanatool_qt.settings_bind import group, get_value

from ..preview_panel import memory_image_for, _qimage_from_pil
from psd_tools import PSDImage
from PIL import Image as PILImage


class GalleryPanel(QWidget, IniStringsMixin):
    filesChanged = Signal(list)
    currentPathChanged = Signal(object)
    saveRequested = Signal()
    saveAsRequested = Signal()

    INI_GROUP = "GalleryPanel"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._files: List[str] = []
        self._added_seq = 0
        self._added_order: dict[str, int] = {}
        self._unsaved_checker: Optional[Callable[[], bool]] = None
        self._dirty_checker: Optional[Callable[[str], bool]] = None
        self._forget_cb: Optional[Callable[[list[str]], None]] = None

        v = QVBoxLayout(self)
        v.setContentsMargins(15, 0, 12, 0)
        v.setSpacing(6)

        # ——— Панель открытия ———
        row_open = QHBoxLayout()
        self.btn_open_files = QPushButton("Добавить…")
        self.btn_open_folder = QPushButton("Открыть папку…")
        row_open.addWidget(self.btn_open_files)
        row_open.addWidget(self.btn_open_folder)
        row_open.addStretch(1)
        v.addLayout(row_open)

        # ——— Панель сортировки ———
        row_sort = QHBoxLayout()
        self.cmb_sort_field = QComboBox(); self.cmb_sort_field.addItems(["По названию", "По дате", "По добавлению"])
        self.cmb_sort_order = QComboBox(); self.cmb_sort_order.addItems(["По возрастанию", "По убыванию"])
        row_sort.addWidget(QLabel("Сорт.:"))
        row_sort.addWidget(self.cmb_sort_field)
        row_sort.addWidget(self.cmb_sort_order)
        row_sort.addStretch(1)
        v.addLayout(row_sort)
        v.addSpacing(7)

        # ——— Список файлов ———
        self.lbl_files = QLabel("—")
        v.addWidget(self.lbl_files)
        self.list = RightSelectableList()
        self.list.setFrameShape(QFrame.NoFrame)
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.itemSelectionChanged.connect(self._update_files_label)
        self.list.setDragEnabled(True)
        self.list.setAcceptDrops(True)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        v.addWidget(self.list)

        # --- миниатюры в списке ---
        self._thumb_cache = {}
        self._show_thumbs = self._read_show_thumbs()
        self.list.setIconSize(QSize(72, 72) if self._show_thumbs else QSize(0, 0))

        # ——— Действия ———
        row_sel = QHBoxLayout()
        self.btn_select_all = QPushButton("Выделить все")
        self.btn_delete_selected = QPushButton("Удалить выбранные")
        self.btn_clear = QPushButton("Очистить")
        row_sel.addWidget(self.btn_select_all)
        row_sel.addWidget(self.btn_delete_selected)
        row_sel.addWidget(self.btn_clear)
        v.addLayout(row_sel)

        row_move = QHBoxLayout()
        self.btn_up = QPushButton("↑")
        self.btn_down = QPushButton("↓")
        for b in (self.btn_up, self.btn_down):
            b.setFixedSize(40, 30)
        row_move.addWidget(self.btn_up)
        row_move.addWidget(self.btn_down)
        row_move.addStretch(1)
        v.addLayout(row_move)

        # Контекстное меню
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(lambda pos: menu.show_list_menu(self, pos))

        # Сигналы
        self.btn_open_files.clicked.connect(self._open_files)
        self.btn_open_folder.clicked.connect(self._open_folder)
        self.cmb_sort_field.currentIndexChanged.connect(self._apply_sort)
        self.cmb_sort_order.currentIndexChanged.connect(self._apply_sort)
        self.list.currentRowChanged.connect(self._on_row_changed)
        try:
            self.list.model().rowsMoved.connect(lambda *args: list_ops.sync_files_from_list(self))
        except Exception:
            pass

        self.btn_select_all.clicked.connect(self.list.selectAll)
        self.btn_delete_selected.clicked.connect(lambda: self._delete_selected(confirm=None))
        self.btn_clear.clicked.connect(self._clear_all)
        self.btn_up.clicked.connect(self._move_up_one_step)
        self.btn_down.clicked.connect(self._move_down_one_step)

        self.setAcceptDrops(True)

        # Горячая клавиша/Action для вставки из буфера
        self.act_paste = QAction("Вставить из буфера", self)
        self.act_paste.setShortcut(QKeySequence.Paste)
        self.act_paste.triggered.connect(self._paste_from_clipboard)
        self.addAction(self.act_paste)
        self.list.addAction(self.act_paste)

        # INI
        self._last_files_dir = self._ini_load_str("last_files_dir", os.path.expanduser("~"))
        self._last_folder_dir = self._ini_load_str("last_folder_dir", os.path.expanduser("~"))


        # Обновление количества файлов
        self.filesChanged.connect(self._update_files_label)
        self._update_files_label()


    # Миниатюры в галерее
    def _read_show_thumbs(self) -> bool:
        try:
            with group("PreviewSection"):
                val = get_value("gallery_previews", 0)
            if isinstance(val, str):
                val = val.strip().lower() in ("1", "true", "yes", "on")
            else:
                val = bool(int(val))
            return bool(val)
        except Exception:
            return False

    def set_show_thumbnails(self, on: bool):
        """Применить немедленно (на случай прямого сигнала из PreviewSection)."""
        self._show_thumbs = bool(on)
        self.list.setIconSize(QSize(128, 128) if self._show_thumbs else QSize(0, 0))
        self._thumb_cache.clear()
        self._rebuild_list()

    def _thumbnail_for(self, path: str) -> QIcon:
        ic = self._thumb_cache.get(path)
        if ic is not None:
            return ic

        pm: QPixmap | None = None
        if isinstance(path, str) and path.startswith("mem://"):
            try:
                img = memory_image_for(path)
                if img is not None and not img.isNull():
                    pm = QPixmap.fromImage(img)
            except Exception:
                pm = None
        else:
            # PSD/PSB: собираем сводный слой через psd_tools → PIL → QImage → QPixmap
            ext = os.path.splitext(path)[1].lower()
            if ext in (".psd", ".psb"):
                try:
                    psd = psd = PSDImage.open(path)
                    pil = psd.composite()  # PIL.Image

                    # Оптимизация: уменьшаем до ~2× размера иконки списка, чтобы не держать гигантское изображение
                    isz = self.list.iconSize()
                    tw = max(64, (isz.width() if isz.width() > 0 else 72) * 2)
                    th = max(64, (isz.height() if isz.height() > 0 else 72) * 2)
                    try:
                        # Pillow 9.1+: Image.Resampling.LANCZOS; для старых версий — fallback на Image.LANCZOS
                        Resampling = getattr(PILImage, "Resampling", PILImage)
                        pil.thumbnail((tw, th), Resampling.LANCZOS)
                    except Exception:
                        try:
                            pil.thumbnail((tw, th), PILImage.LANCZOS)
                        except Exception:
                            pil.thumbnail((tw, th))

                    qimg = _qimage_from_pil(pil) 
                    pm = QPixmap.fromImage(qimg)
                except Exception:
                    pm = None
            else:
                pm = QPixmap(path)

        if pm is None or pm.isNull():
            ic = QIcon()
        else:
            size = self.list.iconSize()
            if size.width() <= 0 or size.height() <= 0:
                size = QSize(72, 72)
            ic = QIcon(pm.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        self._thumb_cache[path] = ic
        return ic

    # ---------- Публичные ----------
    def _update_files_label(self, *args):
        try:
            total = len(self._files)
            selected = len(self.list.selectedItems())
            text = f"Всего файлов: {total}"
            if selected:
                text += f" • Выбрано: {selected}"
            self.lbl_files.setText(text)
        except Exception:
            pass


    def set_forget_callback(self, fn: Callable[[list[str]], None]):
        self._forget_cb = fn

    def set_unsaved_checker(self, fn: Callable[[], bool]):
        self._unsaved_checker = fn

    def set_dirty_checker(self, fn: Callable[[str], bool]):
        self._dirty_checker = fn

    def _is_dirty(self, path: str) -> bool:
        try:
            return bool(self._dirty_checker and self._dirty_checker(path))
        except Exception:
            return False

    def files(self) -> List[str]:
        return list(self._files)

    def selected_files(self) -> list[str]:
        rows = [self.list.row(i) for i in self.list.selectedItems()]
        rows_sorted = sorted(rows)
        return [self._files[r] for r in rows_sorted if 0 <= r < len(self._files)]

    def set_files(self, paths: List[str], sort_refresh=True):
        self._files = [p for p in paths if is_image(p)]
        self._remember_added(self._files)
        if sort_refresh:
            self._apply_sort(refresh=True)
        else:
            self._rebuild_list()
        self.filesChanged.emit(self.files())
        if self.list.count():
            self.list.setCurrentRow(0)

    def add_file(self, path: str, select: bool = True):
        if not is_image(path):
            return
        if path in self._files:
            if select:
                try:
                    idx = self._files.index(path)
                    self.list.setCurrentRow(idx)
                except Exception:
                    pass
            return
        self._files.append(path)
        self._remember_added([path])
        self._apply_sort(refresh=False)
        if select and self.list.count():
            try:
                idx = self._files.index(path)
                self.list.setCurrentRow(idx)
            except Exception:
                pass
        self.filesChanged.emit(self.files())

    # ---------- Ввод ----------
    def _open_files(self):
        start_dir = self._last_files_dir or self._last_folder_dir or os.path.expanduser("~")
        files = io.pick_files(self, start_dir)
        if files:
            self._last_files_dir = os.path.dirname(files[0])
            self._ini_save_str("last_files_dir", self._last_files_dir)
            self._files = dedup_keep_order(self._files + files)
            self._remember_added(files)
            self._apply_sort(refresh=True)
            self.filesChanged.emit(self.files())

    def _open_folder(self):
        start_dir = self._last_folder_dir or self._last_files_dir or os.path.expanduser("~")
        imgs = io.pick_folder(self, start_dir)
        if not imgs:
            return
        self._last_folder_dir = os.path.dirname(imgs[0]) if imgs else start_dir
        self._ini_save_str("last_folder_dir", self._last_folder_dir)
        self._files = dedup_keep_order(self._files + imgs)
        self._remember_added(imgs)
        self._apply_sort(refresh=True)
        self.filesChanged.emit(self.files())

    def _paste_from_clipboard(self):
        cb = QGuiApplication.clipboard()
        new_paths = io.paths_from_clipboard(self, cb)
        if not new_paths:
            try:
                from smithanatool_qt.utils import dialogs
                dialogs.info(self, "Буфер обмена не содержит изображения или путей к изображениям.")
            except Exception:
                pass
            return
        self._files = dedup_keep_order(self._files + new_paths)
        self._remember_added(new_paths)
        self._apply_sort(refresh=True)
        self.filesChanged.emit(self.files())

    # ---------- DnD ----------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        if e.source() is self.list:
            super().dropEvent(e)
            list_ops.sync_files_from_list(self)
            return
        paths = io.paths_from_drop(e.mimeData().urls())
        if paths:
            self._files = dedup_keep_order(self._files + paths)
            self._remember_added(paths)
            self._apply_sort(refresh=True)
            self.filesChanged.emit(self.files())

    # ---------- Список ----------
    def _rebuild_list(self):
        self.list.blockSignals(True)
        self.list.clear()
        for idx, p in enumerate(self._files, start=1):
            star = " *" if self._is_dirty(p) else ""
            it = QListWidgetItem(f"{idx}. {os.path.basename(p)}{star}")
            it.setData(Qt.UserRole, p)
            if self._show_thumbs:
                it.setIcon(self._thumbnail_for(p))
                # (необязательно, но помогает гарантировать высоту строки)
                it.setSizeHint(QSize(0, max(26, self.list.iconSize().height() + 6)))
            self.list.addItem(it)
        self.list.blockSignals(False)
        if not self._files:
            self.currentPathChanged.emit(None)
        self._update_files_label()

    def mark_dirty(self, path: str, dirty: bool):
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.data(Qt.UserRole) == path:
                base = os.path.basename(path)
                star = " *" if dirty else ""
                it.setText(f"{i + 1}. {base}{star}")
                break

    def _refresh_labels(self):
        for i in range(self.list.count()):
            it = self.list.item(i)
            p = it.data(Qt.UserRole)
            star = " *" if self._is_dirty(p) else ""
            it.setText(f"{i + 1}. {os.path.basename(p)}{star}")

    def refresh_numbers(self):
        self._refresh_labels()

    def _sync_files_from_list(self):
        list_ops.sync_files_from_list(self)

    def _on_row_changed(self, row: int):
        if 0 <= row < len(self._files):
            self.currentPathChanged.emit(self._files[row])
        else:
            self.currentPathChanged.emit(None)

    # ---------- Операции выбора (делегаты в list_ops) ----------
    def _has_unsaved(self) -> bool:
        if hasattr(self, "_dirty_checker") and self._dirty_checker:
            return any(self._is_dirty(p) for p in self._files)
        try:
            return bool(self._unsaved_checker and self._unsaved_checker())
        except Exception:
            return False

    def _confirm_clear(self) -> bool:
        msg = "Очистить список файлов?"
        if self._has_unsaved():
            msg = ("Есть несохранённые изменения. Удалить?")
        btn = QMessageBox.warning(self, "Очистить список", msg,
                                  QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return btn == QMessageBox.Yes

    def _confirm_delete_selected(self, count: int) -> bool:
        if count <= 0:
            return False
        if self._has_unsaved():
            msg = ("Есть несохранённые изменения. Удалить?")
        else:
            msg = "Удалить выбранные элементы?"
        btn = QMessageBox.warning(self, "Удалить выбранные", msg,
                                  QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return btn == QMessageBox.Yes

    def _delete_selected(self, *, confirm: bool = True):
        list_ops.delete_selected(self, confirm=confirm)

    def _clear_all(self):
        list_ops.clear_all(self)

    def _move_up_one_step(self):
        list_ops.move_up_one_step(self)

    def _move_down_one_step(self):
        list_ops.move_down_one_step(self)

    # ---------- Сортировка ----------
    def _remember_added(self, paths: list[str]):
        for p in paths:
            if p not in self._added_order:
                self._added_seq += 1
                self._added_order[p] = self._added_seq

    def _apply_sort(self, refresh=False):
        if not self._files:
            return
        selected_paths = [self.list.item(i).data(Qt.UserRole)
                          for i in range(self.list.count()) if self.list.item(i).isSelected()]
        cur_idx = self.list.currentRow()
        current_path = self._files[cur_idx] if 0 <= cur_idx < len(self._files) else None

        field = self.cmb_sort_field.currentText()
        order = self.cmb_sort_order.currentText()
        self._files = sort.apply_sort(self._files, field, order, self._added_order)

        self._rebuild_list()
        if refresh and self._files:
            if current_path and current_path in self._files:
                self._select_by_paths([current_path], current_path)
            else:
                self.list.setCurrentRow(0)
        else:
            self._select_by_paths(selected_paths, current_path)
        self.filesChanged.emit(self.files())

    def _select_by_paths(self, paths, current_path=None):
        current_index = -1
        for idx in range(self.list.count()):
            it = self.list.item(idx)
            if it.data(Qt.UserRole) in paths:
                it.setSelected(True)
            if current_path and it.data(Qt.UserRole) == current_path:
                current_index = idx
        if current_index >= 0:
            self.list.setCurrentRow(current_index)
        elif paths:
            first = next((i for i in range(self.list.count()) if self.list.item(i).isSelected()), -1)
            if first >= 0:
                self.list.setCurrentRow(first)

from __future__ import annotations
from typing import List, Optional, Callable
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QAbstractItemView, QComboBox, QListWidgetItem, QMessageBox
)
from PySide6.QtGui import QGuiApplication, QKeySequence, QAction

from ..common import is_image, dedup_keep_order
from .widgets import RightSelectableList
from .settings_mixin import IniStringsMixin
from . import io, sort, menu, list_ops


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
        v.addWidget(QLabel("Файлы"))
        self.list = RightSelectableList()
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.setDragEnabled(True)
        self.list.setAcceptDrops(True)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        v.addWidget(self.list)

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

    # ---------- Публичные ----------
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
            self.list.addItem(it)
        self.list.blockSignals(False)
        if not self._files:
            self.currentPathChanged.emit(None)

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

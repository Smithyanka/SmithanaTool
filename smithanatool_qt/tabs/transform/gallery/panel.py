from __future__ import annotations

from typing import List, Optional, Callable, Dict
import os

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import QWidget, QListWidgetItem, QMessageBox, QAbstractItemView
from PySide6.QtGui import QGuiApplication, QKeySequence, QAction, QIcon

from ..common import is_image, dedup_keep_order
from smithanatool_qt.tabs.common.bind import ini_load_str, ini_save_str, ini_load_bool, ini_save_bool
from smithanatool_qt.settings_bind import group, get_value

from . import io, sort, menu, list_ops
from .ui import build_ui
from .thumbs import ThumbnailProvider




class GalleryPanel(QWidget):
    filesChanged = Signal(list)
    currentPathChanged = Signal(object)
    saveRequested = Signal()
    saveAsRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._files: List[str] = []
        self._added_seq = 0
        self._added_order: dict[str, int] = {}
        self._unsaved_checker: Optional[Callable[[], bool]] = None
        self._dirty_checker: Optional[Callable[[str], bool]] = None
        self._forget_cb: Optional[Callable[[list[str]], None]] = None

        # UI (layout + widgets)
        self.ui = build_ui(self)

        # sort menu internals
        self._sort_menu = self.ui.sort_menu
        self._sort_field_actions = self.ui.sort_field_actions
        self._sort_order_actions = self.ui.sort_order_actions
        self._sort_menu.aboutToShow.connect(self._sync_sort_menu_checks)

        # thumbnails
        self._thumbs = ThumbnailProvider()
        legacy = self._read_show_thumbs_legacy()
        self._show_thumbs = ini_load_bool("GalleryPanel", "view_thumbs", default=legacy)
        self._apply_view_mode(self._show_thumbs)
        self.ui.set_view_mode(self._show_thumbs)

        # контекстное меню
        self.ui.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.list.customContextMenuRequested.connect(lambda pos: menu.show_list_menu(self, pos))

        # сигналы
        self.ui.btn_open_files.clicked.connect(self._open_files)
        self.ui.btn_open_folder.clicked.connect(self._open_folder)

        self.ui.cmb_sort_field.currentIndexChanged.connect(self._apply_sort)
        self.ui.cmb_sort_order.currentIndexChanged.connect(self._apply_sort)

        self.ui.btn_view.toggled.connect(self._on_view_toggled)

        self.ui.list.itemSelectionChanged.connect(self._update_files_label)
        self.ui.list.currentRowChanged.connect(self._on_row_changed)
        try:
            self.ui.list.model().rowsMoved.connect(lambda *args: list_ops.sync_files_from_list(self))
        except Exception:
            pass

        self.ui.btn_select_all.clicked.connect(self.ui.list.selectAll)
        self.ui.btn_delete_selected.clicked.connect(lambda: self._delete_selected(confirm=None))
        self.ui.btn_clear.clicked.connect(self._clear_all)
        self.ui.btn_up.clicked.connect(self._move_up_one_step)
        self.ui.btn_down.clicked.connect(self._move_down_one_step)

        self.setAcceptDrops(True)

        # paste
        self.act_paste = QAction("Вставить из буфера", self)
        self.act_paste.setShortcut(QKeySequence.Paste)
        self.act_paste.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        self.act_paste.triggered.connect(self._paste_from_clipboard)
        self.addAction(self.act_paste)
        self.ui.list.addAction(self.act_paste)

        # ini
        self._last_files_dir = ini_load_str("GalleryPanel", "last_files_dir", os.path.expanduser("~"))
        self._last_folder_dir = ini_load_str("GalleryPanel", "last_folder_dir", os.path.expanduser("~"))

        self.filesChanged.connect(self._update_files_label)
        self._update_files_label()

    # ---------- VIEW ----------
    def _read_show_thumbs_legacy(self) -> bool:
        try:
            with group("PreviewSection"):
                val = get_value("gallery_previews", 0)
            if isinstance(val, str):
                return val.strip().lower() in ("1", "true", "yes", "on")
            return bool(int(val))
        except Exception:
            return False

    def _apply_view_mode(self, thumbs: bool) -> None:
        # миниатюры = список, просто больше иконка
        self.ui.list.setIconSize(QSize(128, 128) if thumbs else QSize(0, 0))


    def _on_view_toggled(self, on: bool) -> None:
        self.set_show_thumbnails(on)

    def set_show_thumbnails(self, on: bool) -> None:
        self._show_thumbs = bool(on)
        ini_save_bool("GalleryPanel", "view_thumbs", self._show_thumbs)
        self._apply_view_mode(self._show_thumbs)
        self._thumbs.clear()
        self.ui.set_view_mode(self._show_thumbs)
        self._rebuild_list()

    # ---------- SORT MENU ----------
    def _sync_sort_menu_checks(self) -> None:
        fi = self.ui.cmb_sort_field.currentIndex()
        oi = self.ui.cmb_sort_order.currentIndex()
        for i, act in enumerate(self._sort_field_actions):
            act.setChecked(i == fi)
        for i, act in enumerate(self._sort_order_actions):
            act.setChecked(i == oi)

    # ---------- UI helpers ----------
    def _update_files_label(self, *args) -> None:
        total = len(self._files)
        selected = len(self.ui.list.selectedItems())
        self.ui.lbl_files.setText(f"Всего: {total} | Выбрано: {selected}")

    def _focus_path(self, path: Optional[str]) -> None:
        """Сделать path текущим элементом (чтобы сработал currentRowChanged и превью обновилось)."""
        lst = self.ui.list
        if not self._files or lst.count() <= 0:
            return

        row = -1
        if path:
            try:
                row = self._files.index(path)
            except ValueError:
                row = -1

        # если path не найден — покажем первый
        if row < 0:
            row = 0

        if 0 <= row < lst.count():
            lst.setCurrentRow(row)
            it = lst.item(row)
            if it:
                it.setSelected(True)
                try:
                    lst.scrollToItem(it, QAbstractItemView.EnsureVisible)
                except Exception:
                    pass

    def set_forget_callback(self, fn: Callable[[list[str]], None]) -> None:
        self._forget_cb = fn

    def set_unsaved_checker(self, fn: Callable[[], bool]) -> None:
        self._unsaved_checker = fn

    def set_dirty_checker(self, fn: Callable[[str], bool]) -> None:
        self._dirty_checker = fn

    def _is_dirty(self, path: str) -> bool:
        try:
            return bool(self._dirty_checker and self._dirty_checker(path))
        except Exception:
            return False

    def files(self) -> List[str]:
        return list(self._files)

    def selected_files(self) -> list[str]:
        rows = [self.ui.list.row(i) for i in self.ui.list.selectedItems()]
        rows_sorted = sorted(rows)
        return [self._files[r] for r in rows_sorted if 0 <= r < len(self._files)]

    def apply_path_mapping(self, mapping: Dict[str, str], *, refresh_sort: bool = True, call_forget_cb: bool = True) -> None:
        """Обновляет пути в галерее после внешнего переименования файлов.

        mapping: old_path -> new_path
        """

        if call_forget_cb:
            try:
                if self._forget_cb:
                    self._forget_cb(list(mapping.keys()) + list(mapping.values()))
            except Exception:
                pass
        if not mapping:
            return

        try:
            if self._forget_cb:
                self._forget_cb(list(mapping.keys()) + list(mapping.values()))
        except Exception:
            pass

        lst = self.ui.list

        # запомним скролл
        vsb = lst.verticalScrollBar() if hasattr(lst, "verticalScrollBar") else None
        scroll = vsb.value() if vsb else None

        # 1) Обновим data у текущих items, чтобы selection/current сохранились по Qt.UserRole
        lst.blockSignals(True)
        try:
            for i in range(lst.count()):
                it = lst.item(i)
                p = it.data(Qt.UserRole)
                if p in mapping:
                    it.setData(Qt.UserRole, mapping[p])
        finally:
            lst.blockSignals(False)

        # 2) Обновим модель
        self._files = [mapping.get(p, p) for p in list(self._files)]
        self._files = dedup_keep_order(self._files)

        # 3) Перенесём порядок добавления (ключуется путём)
        for old, new in mapping.items():
            if old in self._added_order:
                v = self._added_order.pop(old)
                self._added_order[new] = min(v, self._added_order.get(new, v))

        # 4) Сбросим кэш миниатюр (ключуется путём)
        try:
            self._thumbs.clear()
        except Exception:
            pass

        # 5) Перестроим список с учётом сортировки/нумерации
        if refresh_sort and self._files:
            self._apply_sort(refresh=True)
        else:
            self._rebuild_list()
            self.filesChanged.emit(self.files())

        # восстановим скролл
        if vsb is not None and scroll is not None:
            try:
                vsb.setValue(scroll)
            except Exception:
                pass

    # ---------- List build ----------

    def _format_item_text(self, idx0: int, path: str) -> str:
        base = os.path.basename(path)
        star = " *" if self._is_dirty(path) else ""
        return f"{idx0 + 1}. {base}{star}"


    def _rebuild_list(self) -> None:
        lst = self.ui.list
        selected_paths = {it.data(Qt.UserRole) for it in lst.selectedItems()}
        cur_item = lst.currentItem()
        cur_path = cur_item.data(Qt.UserRole) if cur_item else None

        lst.blockSignals(True)
        lst.clear()

        for i, p in enumerate(self._files):
            it = QListWidgetItem(self._format_item_text(i, p))
            it.setData(Qt.UserRole, p)

            if self._show_thumbs:
                it.setIcon(self._thumbs.icon_for(p, lst.iconSize()))
                it.setSizeHint(QSize(0, max(36, lst.iconSize().height() + 5)))
            else:
                it.setIcon(QIcon())
                it.setSizeHint(QSize(0, 32))

            lst.addItem(it)

        lst.blockSignals(False)

        # восстановим выделение/текущий
        for i in range(lst.count()):
            it = lst.item(i)
            if it.data(Qt.UserRole) in selected_paths:
                it.setSelected(True)
            if cur_path and it.data(Qt.UserRole) == cur_path:
                lst.setCurrentRow(i)

        # если ничего не было текущим — выберем первый элемент, чтобы превью не было пустым
        if lst.count() and lst.currentRow() < 0:
            lst.setCurrentRow(0)

        if not self._files:
            self.currentPathChanged.emit(None)
        self._update_files_label()

    def _refresh_labels(self) -> None:
        lst = self.ui.list
        for i in range(lst.count()):
            it = lst.item(i)
            p = it.data(Qt.UserRole)
            it.setText(self._format_item_text(i, p))
            if self._show_thumbs:
                it.setIcon(self._thumbs.icon_for(p, lst.iconSize()))
                it.setSizeHint(QSize(0, max(36, lst.iconSize().height() + 12)))
            else:
                it.setIcon(QIcon())
                it.setSizeHint(QSize(0, 36))

    def refresh_numbers(self) -> None:
        self._refresh_labels()

    def mark_dirty(self, path: str, dirty: bool) -> None:
        self._refresh_labels()

    def _on_row_changed(self, row: int) -> None:
        if 0 <= row < len(self._files):
            self.currentPathChanged.emit(self._files[row])
        else:
            self.currentPathChanged.emit(None)

    # ---------- Ops (делегаты) ----------
    def _has_unsaved(self) -> bool:
        try:
            if self._dirty_checker:
                return any(self._is_dirty(p) for p in self._files)
            return bool(self._unsaved_checker and self._unsaved_checker())
        except Exception:
            return False

    def _confirm_clear(self) -> bool:
        msg = "Очистить список файлов?"
        if self._has_unsaved():
            msg = "Есть несохранённые изменения. Удалить?"
        btn = QMessageBox.warning(
            self,
            "Очистить список",
            msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return btn == QMessageBox.Yes

    def _confirm_delete_selected(self, count: int) -> bool:
        if count <= 0:
            return False
        msg = "Удалить выбранные элементы?"
        if self._has_unsaved():
            msg = "Есть несохранённые изменения. Удалить?"
        btn = QMessageBox.warning(
            self,
            "Удалить выбранные",
            msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return btn == QMessageBox.Yes

    def _delete_selected(self, *, confirm: bool = True) -> None:
        list_ops.delete_selected(self, confirm=confirm)

    def _clear_all(self) -> None:
        list_ops.clear_all(self)

    def _move_up_one_step(self) -> None:
        list_ops.move_up_one_step(self)

    def _move_down_one_step(self) -> None:
        list_ops.move_down_one_step(self)

    # ---------- sort ----------
    def _remember_added(self, paths: list[str]) -> None:
        for p in paths:
            if p not in self._added_order:
                self._added_seq += 1
                self._added_order[p] = self._added_seq

    def _apply_sort(self, refresh: bool = False) -> None:
        if not self._files:
            self._rebuild_list()
            return

        lst = self.ui.list
        selected_paths = {it.data(Qt.UserRole) for it in lst.selectedItems()}
        cur_item = lst.currentItem()
        cur_path = cur_item.data(Qt.UserRole) if cur_item else None

        field = self.ui.cmb_sort_field.currentText()
        order = self.ui.cmb_sort_order.currentText()
        self._files = sort.apply_sort(self._files, field, order, self._added_order)

        self._rebuild_list()

        # восстановим выделение/текущий
        for i in range(lst.count()):
            it = lst.item(i)
            p = it.data(Qt.UserRole)
            if p in selected_paths:
                it.setSelected(True)
            if cur_path and p == cur_path:
                lst.setCurrentRow(i)

        self.filesChanged.emit(self.files())

    # ---------- input ----------
    def set_files(self, paths: List[str], sort_refresh: bool = True) -> None:
        self._files = [p for p in paths if is_image(p)]
        self._remember_added(self._files)
        if sort_refresh:
            self._apply_sort(refresh=True)
        else:
            self._rebuild_list()
        self.filesChanged.emit(self.files())
        if self.ui.list.count():
            self.ui.list.setCurrentRow(0)

    def add_file(self, path: str, select: bool = True) -> None:
        if not is_image(path):
            return
        if path in self._files:
            return
        self._files.append(path)
        self._remember_added([path])
        self._apply_sort(refresh=False)
        if select and self.ui.list.count():
            try:
                self.ui.list.setCurrentRow(self._files.index(path))
            except Exception:
                pass
        self.filesChanged.emit(self.files())

    def _open_files(self) -> None:
        start_dir = self._last_files_dir or self._last_folder_dir or os.path.expanduser("~")
        files = io.pick_files(self, start_dir)
        if files:
            self._last_files_dir = os.path.dirname(files[0])
            ini_save_str("GalleryPanel", "last_files_dir", self._last_files_dir)
            self._files = dedup_keep_order(self._files + files)
            self._remember_added(files)
            self._apply_sort(refresh=True)
            self._focus_path(files[0] if files else None)
            self.filesChanged.emit(self.files())

    def _open_folder(self) -> None:
        start_dir = self._last_folder_dir or self._last_files_dir or os.path.expanduser("~")
        imgs = io.pick_folder(self, start_dir)
        if not imgs:
            return
        self._last_folder_dir = os.path.dirname(imgs[0]) if imgs else start_dir
        ini_save_str("GalleryPanel", "last_folder_dir", self._last_folder_dir)
        self._files = dedup_keep_order(self._files + imgs)
        self._remember_added(imgs)
        self._apply_sort(refresh=True)
        self._focus_path(imgs[0] if imgs else None)
        self.filesChanged.emit(self.files())

    def _paste_from_clipboard(self) -> None:
        cb = QGuiApplication.clipboard()
        new_paths = io.paths_from_clipboard(self, cb)
        if not new_paths:
            return
        self._files = dedup_keep_order(self._files + new_paths)
        self._remember_added(new_paths)
        self._apply_sort(refresh=True)
        self._focus_path(new_paths[0] if new_paths else None)
        self.filesChanged.emit(self.files())

    # ---------- DnD ----------
    def dragEnterEvent(self, e) -> None:  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:  # noqa: N802
        if e.source() is self.ui.list:
            super().dropEvent(e)
            list_ops.sync_files_from_list(self)
            return
        paths = io.paths_from_drop(e.mimeData().urls())
        if paths:
            self._files = dedup_keep_order(self._files + paths)
            self._remember_added(paths)
            self._apply_sort(refresh=True)
            self._focus_path(paths[0] if paths else None)
            self.filesChanged.emit(self.files())

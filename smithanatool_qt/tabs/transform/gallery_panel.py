
from __future__ import annotations
from typing import List
import os

from PySide6.QtCore import Qt, QPoint, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QLabel, QPushButton,
    QAbstractItemView, QMenu, QComboBox, QListWidgetItem
)

from smithanatool_qt.utils import dialogs
from .common import natural_key, mtime_key, is_image, dedup_keep_order, open_in_explorer


class _RightSelectableList(QListWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._right_selecting = False
        self._anchor_row = -1

    def _row_at_pos_clamped(self, pos: QPoint) -> int:
        """row под курсором, с зажимом к границам (если мышь выше/ниже списка)."""
        row = self.row(self.itemAt(pos))
        if row >= 0:
            return row
        if pos.y() < 0 and self.count() > 0:
            return 0
        if pos.y() > self.viewport().height() - 1 and self.count() > 0:
            return self.count() - 1
        return -1

    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton:
            row = self._row_at_pos_clamped(e.pos())
            if row >= 0:
                if not (e.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier)):
                    # обычный ПКМ-клик — как одиночное выделение
                    self.clearSelection()
                # ставим якорь и выделяем строку
                self._anchor_row = row
                it = self.item(row)
                it.setSelected(True)
                self.setCurrentRow(row)
                self._right_selecting = True
                e.accept()
                return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._right_selecting:
            row = self._row_at_pos_clamped(e.pos())
            if row >= 0 and self._anchor_row >= 0:
                a, b = sorted((self._anchor_row, row))
                self.blockSignals(True)
                # выделяем диапазон якорь..row
                for i in range(self.count()):
                    self.item(i).setSelected(a <= i <= b)
                self.blockSignals(False)
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.RightButton and self._right_selecting:
            self._right_selecting = False
            e.accept()
            return
        super().mouseReleaseEvent(e)


class GalleryPanel(QWidget):
    filesChanged = Signal(list)
    currentPathChanged = Signal(object)
    saveRequested = Signal()
    saveAsRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._files: List[str] = []

        self._added_seq = 0  # монотонный счётчик добавлений
        self._added_order: dict[str, int] = {}  # path -> порядковый номер добавления

        v = QVBoxLayout(self)

        row_open = QHBoxLayout()
        self.btn_open_files = QPushButton("Добавить…")
        self.btn_open_folder = QPushButton("Открыть папку…")
        row_open.addWidget(self.btn_open_files)
        row_open.addWidget(self.btn_open_folder)
        row_open.addStretch(1)

        v.addLayout(row_open)

        row_sort = QHBoxLayout()
        self.cmb_sort_field = QComboBox();
        self.cmb_sort_field.addItems(["По названию", "По дате", "По добавлению"])
        self.cmb_sort_order = QComboBox(); self.cmb_sort_order.addItems(["По возрастанию", "По убыванию"])
        row_sort.addWidget(QLabel("Сорт.:"))
        row_sort.addWidget(self.cmb_sort_field)
        row_sort.addWidget(self.cmb_sort_order)
        row_sort.addStretch(1)
        v.addLayout(row_sort)
        v.addSpacing(7)

        v.addWidget(QLabel("Файлы"))
        self.list = _RightSelectableList()
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.setDragEnabled(True)
        self.list.setAcceptDrops(True)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        v.addWidget(self.list)

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
        self.list.customContextMenuRequested.connect(self._show_list_menu)

        # Сигналы
        self.btn_open_files.clicked.connect(self._open_files)
        self.btn_open_folder.clicked.connect(self._open_folder)
        self.cmb_sort_field.currentIndexChanged.connect(self._apply_sort)
        self.cmb_sort_order.currentIndexChanged.connect(self._apply_sort)
        self.list.currentRowChanged.connect(self._on_row_changed)

        try:
            self.list.model().rowsMoved.connect(self._on_rows_moved)
        except Exception:
            pass

        self.btn_select_all.clicked.connect(self.list.selectAll)
        self.btn_delete_selected.clicked.connect(self._delete_selected)
        self.btn_clear.clicked.connect(self._clear_all)
        self.btn_up.clicked.connect(self._move_up_one_step)
        self.btn_down.clicked.connect(self._move_down_one_step)

        self.setAcceptDrops(True)

    # ---------- Публичные ----------
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
        files, _ = dialogs.ask_open_files(
            self, "Выберите файлы",
            "Изображения (*.png *.jpg *.jpeg *.gif *.bmp *.webp *.psd *.psb);;Все файлы (*.*)"
        )
        if files:
            self._files = dedup_keep_order(self._files + files)
            self._remember_added(files)
            self._apply_sort(refresh=True)
            self.filesChanged.emit(self.files())

    def _open_folder(self):
        folder = dialogs.ask_open_dir(self, "Выберите папку")
        if not folder:
            return
        try:
            entries = [os.path.join(folder, name) for name in os.listdir(folder)]
        except Exception:
            entries = []
        imgs = [p for p in entries if is_image(p)]
        if imgs:
            self._files = dedup_keep_order(self._files + imgs)
            self._remember_added(imgs)
            self._apply_sort(refresh=True)
            self.filesChanged.emit(self.files())

    # ---------- DnD ----------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        if e.source() is self.list:
            super().dropEvent(e)
            self._sync_files_from_list()
            return
        paths = []
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            if not p:
                continue
            if os.path.isdir(p):
                try:
                    for name in os.listdir(p):
                        fp = os.path.join(p, name)
                        if is_image(fp):
                            paths.append(fp)
                except Exception:
                    pass
            elif is_image(p):
                paths.append(p)
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
            label = f"{idx}. {os.path.basename(p)}"
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, p)
            self.list.addItem(it)
        self.list.blockSignals(False)
        if not self._files:
            self.currentPathChanged.emit(None)

    def _refresh_labels(self):
        # Пронумеровать видимые элементы согласно текущему порядку
        for i in range(self.list.count()):
            it = self.list.item(i)
            p = it.data(Qt.UserRole)
            it.setText(f"{i+1}. {os.path.basename(p)}")

    # Публичный метод для внешних панелей (например, переименования)
    def refresh_numbers(self):
        self._refresh_labels()

    def _sync_files_from_list(self):
        self._files = [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]
        self._refresh_labels()
        self.filesChanged.emit(self.files())

    def _on_row_changed(self, row: int):
        if 0 <= row < len(self._files):
            self.currentPathChanged.emit(self._files[row])
        else:
            self.currentPathChanged.emit(None)

    # ---------- Контекстное меню ----------
    def _show_list_menu(self, pos: QPoint):
        item = self.list.itemAt(pos)
        menu = QMenu(self)
        act_add_files = menu.addAction("Добавить файлы…")
        act_add_folder = menu.addAction("Открыть папку…")
        menu.addSeparator()
        act_open_dir = menu.addAction("Открыть в проводнике")
        act_remove = menu.addAction("Удалить выбранные")


        act = menu.exec_(self.list.mapToGlobal(pos))
        if act == act_add_files:
            self._open_files()
        elif act == act_add_folder:
            self._open_folder()
        elif act == act_remove:
            self._delete_selected()
        elif act == act_open_dir:
            folder = None
            if item:
                full_path = item.data(Qt.UserRole)
                folder = os.path.dirname(full_path)
            elif self._files:
                folder = os.path.dirname(self._files[0])
            if folder:
                open_in_explorer(folder)

    # ---------- Операции выбора ----------
    def _get_selected_mask(self):
        n = self.list.count()
        sel = [False] * n
        for it in self.list.selectedItems():
            sel[self.list.row(it)] = True
        return sel

    def _delete_selected(self):
        rows = sorted({self.list.row(i) for i in self.list.selectedItems()}, reverse=True)
        removed_paths = []
        for r in rows:
            if 0 <= r < len(self._files):
                removed_paths.append(self._files[r])
                self._files.pop(r)
                self.list.takeItem(r)
        for p in removed_paths:
            self._added_order.pop(p, None)
        self._sync_files_from_list()

    def _clear_all(self):
        self._files.clear()
        self._added_order.clear()
        self._rebuild_list()
        self.filesChanged.emit(self.files())

    # ---------- Сортировка ----------

    def _remember_added(self, paths: list[str]):
        # регистрируем порядок добавления только для новых путей
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
        reverse = (order == "По убыванию")

        if field == "По названию":
            key_fn = natural_key
        elif field == "По добавлению":
            key_fn = lambda p: self._added_order.get(p, float("inf"))
        else:
            key_fn = mtime_key

        self._files.sort(key=key_fn, reverse=reverse)

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

    # ---------- Перемещение ----------
    def _move_up_one_step(self):
        n = self.list.count()
        if n <= 1:
            return

        # сохраним скролл и текущий элемент
        bar = self.list.verticalScrollBar()
        keep_scroll = bar.value()
        cur_idx = self.list.currentRow()
        cur_path = self.list.item(cur_idx).data(Qt.UserRole) if 0 <= cur_idx < n else None

        # маска выделения
        sel = [self.list.item(i).isSelected() for i in range(n)]

        self.list.blockSignals(True)
        # один ПАСС сверху вниз: меняем местами [i-1] и [i], если верх не выделен, низ выделен
        for i in range(1, n):
            if sel[i] and not sel[i - 1]:
                # swap в QListWidget
                it = self.list.takeItem(i)
                self.list.insertItem(i - 1, it)
                it.setSelected(True)  # оставляем выделенным
                # элемент, уехавший вниз, должен остаться невыделенным
                self.list.item(i).setSelected(False)

                # swap в self._files и маске
                self._files[i - 1], self._files[i] = self._files[i], self._files[i - 1]
                sel[i - 1], sel[i] = sel[i], sel[i]
        self.list.blockSignals(False)

        # восстановим current и скролл
        if cur_path:
            for idx in range(self.list.count()):
                if self.list.item(idx).data(Qt.UserRole) == cur_path:
                    self.list.setCurrentRow(idx)
                    break
        bar.setValue(keep_scroll)
        self._refresh_labels()
        self.filesChanged.emit(self.files())

    def _move_down_one_step(self):
        n = self.list.count()
        if n <= 1:
            return

        bar = self.list.verticalScrollBar()
        keep_scroll = bar.value()
        cur_idx = self.list.currentRow()
        cur_path = self.list.item(cur_idx).data(Qt.UserRole) if 0 <= cur_idx < n else None

        sel = [self.list.item(i).isSelected() for i in range(n)]

        self.list.blockSignals(True)
        # один ПАСС снизу вверх: меняем местами [i] и [i+1], если текущий выделен, следующий — нет
        for i in range(n - 2, -1, -1):
            if sel[i] and not sel[i + 1]:
                it = self.list.takeItem(i)
                self.list.insertItem(i + 1, it)
                it.setSelected(True)
                self.list.item(i).setSelected(False)

                self._files[i], self._files[i + 1] = self._files[i + 1], self._files[i]
                sel[i], sel[i + 1] = sel[i + 1], sel[i]
        self.list.blockSignals(False)

        if cur_path:
            for idx in range(self.list.count()):
                if self.list.item(idx).data(Qt.UserRole) == cur_path:
                    self.list.setCurrentRow(idx)
                    break
        bar.setValue(keep_scroll)
        self._refresh_labels()
        self.filesChanged.emit(self.files())


    def _on_rows_moved(self, *args):
        self._sync_files_from_list()

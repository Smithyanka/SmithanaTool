from __future__ import annotations
import os
from typing import List

from PySide6.QtCore import Qt, QPoint, QSize


_ITEM_UID_ROLE = int(Qt.UserRole + 1)
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QListWidgetItem, QFileDialog, QMenu


class RightPanelListMixin:
    """
    Логика работы со списком фрагментов:
    - set_items/items
    - копирование/удаление/перенумерация
    - контекстное меню
    - обработка редактирования
    - сохранение в файл
    """

    # ---- helpers ----
    def set_items(self, texts: List[str]):
        self._block_item_changed = True
        try:
            self.list.clear()
            for i, t in enumerate(texts, 1):
                it = QListWidgetItem(f"{i}. {t}")
                it.setFlags(
                    it.flags()
                    | Qt.ItemIsEditable
                    | Qt.ItemIsDragEnabled
                    | Qt.ItemIsSelectable
                    | Qt.ItemIsEnabled
                )
                self.list.addItem(it)
        finally:
            self._block_item_changed = False

    def items(self) -> List[str]:
        out = []
        for i in range(self.list.count()):
            s = self.list.item(i).text()
            if ". " in s:
                s = s.split(". ", 1)[1]
            out.append(s)
        return out

    def _relabel(self):
        self._block_item_changed = True
        try:
            for i in range(self.list.count()):
                item = self.list.item(i)
                s = item.text()
                if ". " in s:
                    s = s.split(". ", 1)[1]
                item.setText(f"{i + 1}. {s}")
        finally:
            self._block_item_changed = False

    def _copy_selected(self):
        print("COPY TRIGGERED")
        rows = sorted({mi.row() for mi in self.list.selectedIndexes()})
        if not rows:
            return
        texts = []
        for r in rows:
            item = self.list.item(r)
            s = item.text()
            if ". " in s:
                s = s.split(". ", 1)[1]
            texts.append(s)
        QGuiApplication.clipboard().setText("\n".join(texts))

    def _delete_selected(self):
        rows = sorted({mi.row() for mi in self.list.selectedIndexes()}, reverse=True)
        if rows:
            self._delete_rows(rows)
            return
        idx = self.list.currentRow()
        if idx >= 0:
            self._delete_rows([idx])

    def _delete_rows(self, rows: List[int]):
        if not rows:
            return
        rows = sorted(set(r for r in rows if 0 <= r < self.list.count()), reverse=True)
        if not rows:
            return

        payload: list[tuple[int, str]] = []
        for r in rows:
            item = self.list.item(r)
            uid = str(item.data(_ITEM_UID_ROLE) or "") if item is not None else ""
            payload.append((r, uid))

        self._block_item_changed = True
        try:
            for r, _uid in payload:
                self.list.takeItem(r)
        finally:
            self._block_item_changed = False

        for _r, uid in payload:
            if uid:
                self.itemDeletedByUid.emit(uid)
        self._relabel()

    def _on_save(self):
        start_dir = self._get_save_text_dir()
        start_path = os.path.join(start_dir, "extracted.txt") if start_dir else "extracted.txt"

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить как",
            start_path,
            "Текст (*.txt)",
        )
        if not path:
            return

        self._set_save_text_dir(os.path.dirname(path))
        self.saveRequested.emit(path)

    def _on_save_all(self):
        start_dir = self._get_save_all_text_dir()
        start_path = (
            os.path.join(start_dir, "extracted_all.txt")
            if start_dir
            else "extracted_all.txt"
        )

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить всё как",
            start_path,
            "Текст (*.txt)",
        )
        if not path:
            return

        self._set_save_all_text_dir(os.path.dirname(path))
        self.saveAllRequested.emit(path)

    # контекстное меню списка
    def _on_context_menu(self, pos: QPoint):
        idx = self.list.indexAt(pos).row()
        if idx < 0:
            return

        menu = QMenu(self)
        act_edit = menu.addAction("Редактировать")
        act_copy_many = menu.addAction("Копировать")
        act_del_many = menu.addAction("Удалить")
        menu.addSeparator()
        act_select_all = menu.addAction("Выделить всё")

        chosen = menu.exec(self.list.mapToGlobal(pos))

        if chosen is act_edit:
            self.list.editItem(self.list.item(idx))

        elif chosen is act_copy_many:
            rows = sorted({mi.row() for mi in self.list.selectedIndexes()})
            if rows:
                texts = []
                for r in rows:
                    item = self.list.item(r)
                    s = item.text()
                    if ". " in s:
                        s = s.split(". ", 1)[1]
                    texts.append(s)
                QGuiApplication.clipboard().setText("\n".join(texts))

        elif chosen is act_del_many:
            rows = sorted({mi.row() for mi in self.list.selectedIndexes()}, reverse=True)
            if rows:
                self._delete_rows(rows)

        elif chosen is act_select_all:
            self.list.selectAll()

    # изменения текста пользователем
    def _on_item_changed(self, item: QListWidgetItem):
        if self._block_item_changed:
            return

        text = item.text()
        if ". " in text:
            text = text.split(". ", 1)[1]

        uid = str(item.data(_ITEM_UID_ROLE) or "")
        if not uid:
            return

        self.itemEditedByUid.emit(uid, text)

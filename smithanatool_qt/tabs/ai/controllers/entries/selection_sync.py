from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QRect, Qt


_ITEM_RECT_ROLE = int(Qt.UserRole)
_ITEM_UID_ROLE = int(Qt.UserRole + 1)


class EntriesSelectionSyncMixin:
    # -------- selection sync --------
    def _install_selection_sync(self) -> None:
        try:
            self.viewer.overlay.rectSelected.connect(self._on_overlay_rect_selected)
            self.viewer.overlay.selectionCleared.connect(self._on_overlay_selection_cleared)
        except Exception:
            pass

        try:
            self.right.list.itemSelectionChanged.connect(self._on_list_selection_changed)
        except Exception:
            pass

        try:
            model = self.right.list.model()
            model.rowsMoved.connect(lambda *args: self._on_list_structure_changed())
            model.layoutChanged.connect(lambda *args: self._on_list_structure_changed())
            model.modelReset.connect(lambda *args: self._on_list_structure_changed())
        except Exception:
            pass

    def _list_item_uids_in_order(self) -> list[str]:
        uids: list[str] = []
        count = self.right.list.count()
        for row in range(count):
            item = self.right.list.item(row)
            if item is None:
                continue
            uid = self._item_uid(item)
            if uid:
                uids.append(uid)
        return uids

    def _on_list_structure_changed(self) -> None:
        current_path = self._current_path()
        try:
            self._ensure_list_item_rect_data(current_path)

            uids = self._list_item_uids_in_order()
            if uids:
                self._store.reorder_entries_by_uids(current_path, uids)

            self._sync_overlay_labels(current_path)
            self._remember_rect_state(current_path)
            self._update_preview_ocr_menu_state(current_path)
        except Exception:
            pass

    def _clear_list_selection(self) -> None:
        try:
            self.right.list.clearSelection()
        except Exception:
            pass
        try:
            self.right.list.setCurrentRow(-1)
        except Exception:
            pass

    def _clear_both_selection(self) -> None:
        if self._syncing_selection:
            return
        self._syncing_selection = True
        try:
            try:
                self.viewer.overlay.clear_selection()
            except Exception:
                pass
            self._clear_list_selection()
        finally:
            self._syncing_selection = False

    def _item_rect(self, item) -> Optional[QRect]:
        if item is None:
            return None
        value = item.data(_ITEM_RECT_ROLE)
        return value if isinstance(value, QRect) and not value.isNull() else None

    def _item_uid(self, item) -> str:
        if item is None:
            return ""
        value = item.data(_ITEM_UID_ROLE)
        return str(value or "")

    def _set_item_entry_data(self, item, uid: str, rect: Optional[QRect]) -> None:
        if item is None:
            return
        item.setData(_ITEM_UID_ROLE, str(uid or "") or None)
        item.setData(_ITEM_RECT_ROLE, QRect(rect) if rect is not None and not rect.isNull() else None)

    def _find_row_in_list_by_uid(self, uid: str) -> int:
        uid = str(uid or "")
        if not uid:
            return -1
        count = self.right.list.count()
        for row in range(count):
            item = self.right.list.item(row)
            if item is None:
                continue
            if self._item_uid(item) == uid:
                return row
        return -1

    def _uid_for_list_row(self, row: int) -> str:
        if row is None or row < 0 or row >= self.right.list.count():
            return ""
        item = self.right.list.item(int(row))
        uid = self._item_uid(item)
        if uid:
            return uid
        try:
            entries = self._store.entries(self._current_path())
        except Exception:
            entries = []
        if 0 <= int(row) < len(entries):
            uid = str(getattr(entries[int(row)], "uid", "") or "")
            if uid:
                self._set_item_entry_data(item, uid, getattr(entries[int(row)], "rect", None))
            return uid
        return ""

    def _uid_for_rect(self, path: str, rect_img: Optional[QRect]) -> str:
        if rect_img is None or rect_img.isNull():
            return ""

        try:
            idx = self._store.index_by_rect(path, rect_img)
        except Exception:
            idx = -1

        if idx >= 0:
            try:
                entries = self._store.entries(path)
                if 0 <= idx < len(entries):
                    return str(getattr(entries[idx], "uid", "") or "")
            except Exception:
                pass

        count = self.right.list.count()
        for row in range(count):
            item = self.right.list.item(row)
            if item is None:
                continue
            item_rect = self._item_rect(item)
            if item_rect is not None and item_rect == rect_img:
                return self._item_uid(item)
        return ""

    def _rect_for_uid(self, path: str, uid: str) -> Optional[QRect]:
        uid = str(uid or "")
        if not uid:
            return None
        try:
            entry = self._store.get_entry(path, uid)
        except Exception:
            entry = None
        rect = getattr(entry, "rect", None) if entry is not None else None
        return QRect(rect) if rect is not None and not rect.isNull() else None

    def _set_list_selected_row(self, row: int) -> None:
        if row is None or row < 0 or row >= self.right.list.count():
            self._clear_list_selection()
            return

        try:
            from PySide6.QtCore import QItemSelectionModel

            self.right.list.setCurrentRow(int(row), QItemSelectionModel.ClearAndSelect)
        except Exception:
            try:
                self._clear_list_selection()
                self.right.list.setCurrentRow(int(row))
                item = self.right.list.item(int(row))
                if item is not None:
                    item.setSelected(True)
            except Exception:
                pass

        try:
            item = self.right.list.item(int(row))
            if item is not None:
                self.right.list.scrollToItem(item)
        except Exception:
            pass

    def _ensure_list_item_rect_data(self, path: str, *, force: bool = False) -> None:
        count = self.right.list.count()
        if count <= 0:
            return

        if not force:
            all_have_uid = True
            for row in range(count):
                item = self.right.list.item(row)
                if item is None:
                    continue
                if not self._item_uid(item):
                    all_have_uid = False
                    break
            if all_have_uid:
                return

        try:
            entries = self._store.entries(path)
        except Exception:
            entries = []

        for row in range(count):
            item = self.right.list.item(row)
            if item is None:
                continue
            entry = entries[row] if 0 <= row < len(entries) else None
            uid = str(getattr(entry, "uid", "") or "") if entry is not None else ""
            rect = getattr(entry, "rect", None) if entry is not None else None
            self._set_item_entry_data(item, uid, rect)

    def _replace_rect_in_list_items(self, old_rect: Optional[QRect], new_rect: Optional[QRect]) -> None:
        if old_rect is None or old_rect.isNull():
            return
        count = self.right.list.count()
        for row in range(count):
            item = self.right.list.item(row)
            if item is None:
                continue
            item_rect = self._item_rect(item)
            if item_rect is not None and item_rect == old_rect:
                self._set_item_entry_data(item, self._item_uid(item), new_rect)

    def _clear_all_list_item_rect_data(self) -> None:
        count = self.right.list.count()
        for row in range(count):
            item = self.right.list.item(row)
            if item is None:
                continue
            self._set_item_entry_data(item, self._item_uid(item), None)

    def _find_row_in_list_by_rect(self, rect_img: QRect) -> int:
        if rect_img is None or rect_img.isNull():
            return -1

        uid = self._uid_for_rect(self._current_path(), rect_img)
        if uid:
            row = self._find_row_in_list_by_uid(uid)
            if row >= 0:
                return row

        count = self.right.list.count()
        for row in range(count):
            item = self.right.list.item(row)
            if item is None:
                continue
            if self._item_rect(item) == rect_img:
                return row
        return -1

    def _set_overlay_selected_rect(self, rect_img: Optional[QRect]) -> None:
        try:
            if rect_img is None or rect_img.isNull():
                self.viewer.overlay.clear_selection()
                return

            rects = self.viewer.rects_img()
            for index, rect in enumerate(rects):
                if rect == rect_img:
                    self.viewer.overlay.set_selected_index(index)
                    return
            self.viewer.overlay.clear_selection()
        except Exception:
            pass

    def _set_overlay_selected_uid(self, uid: str) -> None:
        rect = self._rect_for_uid(self._current_path(), uid)
        self._set_overlay_selected_rect(rect)

    def _on_overlay_rect_selected(self, overlay_index: int, rect_img: QRect) -> None:
        if self._syncing_selection:
            return

        path = self._current_path()
        self._selected_rect_img = rect_img
        self._selected_entry_uid = self._uid_for_rect(path, rect_img)

        row = self._find_row_in_list_by_uid(self._selected_entry_uid) if self._selected_entry_uid else -1
        if row < 0:
            row = self._find_row_in_list_by_rect(rect_img)

        self._syncing_selection = True
        try:
            if row >= 0:
                self._set_list_selected_row(row)
            else:
                self._clear_list_selection()
        finally:
            self._syncing_selection = False

    def _on_overlay_selection_cleared(self) -> None:
        if self._syncing_selection:
            return
        self._selected_rect_img = None
        self._selected_entry_uid = None

        self._syncing_selection = True
        try:
            self._clear_list_selection()
        finally:
            self._syncing_selection = False

    def _on_list_selection_changed(self) -> None:
        if self._syncing_selection:
            return

        try:
            rows = sorted({model_index.row() for model_index in self.right.list.selectedIndexes()})
        except Exception:
            rows = []

        if len(rows) != 1:
            self._selected_rect_img = None
            self._selected_entry_uid = None
            self._syncing_selection = True
            try:
                self._set_overlay_selected_rect(None)
            finally:
                self._syncing_selection = False
            return

        row = rows[0]
        uid = self._uid_for_list_row(row)
        rect = self._rect_for_uid(self._current_path(), uid) if uid else None
        if rect is None:
            item = self.right.list.item(row)
            rect = self._item_rect(item) if item is not None else None

        self._selected_entry_uid = uid or None
        self._selected_rect_img = rect

        self._syncing_selection = True
        try:
            if uid:
                self._set_overlay_selected_uid(uid)
            else:
                self._set_overlay_selected_rect(rect)
        finally:
            self._syncing_selection = False

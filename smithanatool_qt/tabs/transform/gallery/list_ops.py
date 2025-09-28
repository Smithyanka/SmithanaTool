from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt

# Набор операций над списком вынесен сюда, чтобы разгрузить GalleryPanel
def sync_files_from_list(panel) -> None:
    panel._files = [panel.list.item(i).data(Qt.UserRole) for i in range(panel.list.count())]
    panel._refresh_labels()
    panel.filesChanged.emit(panel.files())

def delete_selected(panel, *, confirm: Optional[bool] = True) -> None:
    rows = sorted({panel.list.row(i) for i in panel.list.selectedItems()}, reverse=True)
    if not rows:
        return

    if confirm is None:
        confirm = any((0 <= r < len(panel._files)) and panel._is_dirty(panel._files[r]) for r in rows)
    if confirm and not panel._confirm_delete_selected(len(rows)):
        return

    removed_paths: list[str] = []
    for r in rows:
        if 0 <= r < len(panel._files):
            removed_paths.append(panel._files[r])
            panel._files.pop(r)
            panel.list.takeItem(r)
    for p in removed_paths:
        panel._added_order.pop(p, None)

    try:
        from ..preview_panel import unregister_memory_images
        unregister_memory_images(removed_paths)
    except Exception:
        pass

    if panel._forget_cb:
        try:
            panel._forget_cb(removed_paths)
        except Exception:
            pass

    sync_files_from_list(panel)

def clear_all(panel) -> None:
    if not panel._files:
        return
    if not panel._confirm_clear():
        return

    try:
        from ..preview_panel import unregister_memory_images
        unregister_memory_images(panel._files)
    except Exception:
        pass

    if panel._forget_cb:
        try:
            panel._forget_cb(list(panel._files))
        except Exception:
            pass

    panel._files.clear()
    panel._added_order.clear()
    panel._rebuild_list()
    panel.filesChanged.emit(panel.files())

def _restore_current(panel, cur_path):
    if not cur_path:
        return
    for idx in range(panel.list.count()):
        if panel.list.item(idx).data(Qt.UserRole) == cur_path:
            panel.list.setCurrentRow(idx)
            break

def move_up_one_step(panel) -> None:
    n = panel.list.count()
    if n <= 1:
        return
    bar = panel.list.verticalScrollBar()
    keep_scroll = bar.value()
    cur_idx = panel.list.currentRow()
    cur_path = panel.list.item(cur_idx).data(Qt.UserRole) if 0 <= cur_idx < n else None
    sel = [panel.list.item(i).isSelected() for i in range(n)]

    panel.list.blockSignals(True)
    for i in range(1, n):
        if sel[i] and not sel[i - 1]:
            it = panel.list.takeItem(i)
            panel.list.insertItem(i - 1, it)
            it.setSelected(True)
            panel.list.item(i).setSelected(False)
            panel._files[i - 1], panel._files[i] = panel._files[i], panel._files[i - 1]
            sel[i - 1], sel[i] = sel[i], sel[i]
    panel.list.blockSignals(False)

    _restore_current(panel, cur_path)
    bar.setValue(keep_scroll)
    panel._refresh_labels()
    panel.filesChanged.emit(panel.files())

def move_down_one_step(panel) -> None:
    n = panel.list.count()
    if n <= 1:
        return
    bar = panel.list.verticalScrollBar()
    keep_scroll = bar.value()
    cur_idx = panel.list.currentRow()
    cur_path = panel.list.item(cur_idx).data(Qt.UserRole) if 0 <= cur_idx < n else None
    sel = [panel.list.item(i).isSelected() for i in range(n)]

    panel.list.blockSignals(True)
    for i in range(n - 2, -1, -1):
        if sel[i] and not sel[i + 1]:
            it = panel.list.takeItem(i)
            panel.list.insertItem(i + 1, it)
            it.setSelected(True)
            panel.list.item(i).setSelected(False)
            panel._files[i], panel._files[i + 1] = panel._files[i + 1], panel._files[i]
            sel[i], sel[i + 1] = sel[i + 1], sel[i]
    panel.list.blockSignals(False)

    _restore_current(panel, cur_path)
    bar.setValue(keep_scroll)
    panel._refresh_labels()
    panel.filesChanged.emit(panel.files())

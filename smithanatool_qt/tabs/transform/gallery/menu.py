from __future__ import annotations
import os
from PySide6.QtWidgets import QMenu
from PySide6.QtCore import Qt
from ..common import open_in_explorer

# Контекстное меню вынесено в отдельную функцию
def show_list_menu(panel, pos):
    item = panel.list.itemAt(pos)
    menu = QMenu(panel)
    act_add_files = menu.addAction("Добавить файлы…")
    act_add_folder = menu.addAction("Открыть папку…")
    act_paste = menu.addAction("Вставить из буфера	Ctrl+V")
    menu.addSeparator()
    act_open_dir = menu.addAction("Открыть в проводнике")
    act_remove = menu.addAction("Удалить выбранные")

    act = menu.exec_(panel.list.mapToGlobal(pos))
    if act == act_add_files:
        panel._open_files()
    elif act == act_add_folder:
        panel._open_folder()
    elif act == act_paste:
        panel._paste_from_clipboard()
    elif act == act_remove:
        panel._delete_selected()
    elif act == act_open_dir:
        folder = None
        if item:
            full_path = item.data(Qt.UserRole)
            folder = os.path.dirname(full_path)
        elif panel._files:
            folder = os.path.dirname(panel._files[0])
        if folder:
            open_in_explorer(folder)

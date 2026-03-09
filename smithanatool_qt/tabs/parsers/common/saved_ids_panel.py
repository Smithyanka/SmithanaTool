from __future__ import annotations

import json
import os
import inspect
from typing import Callable, Optional

from PySide6.QtCore import QTimer

from .app_paths import get_settings_dir
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QVBoxLayout,
    QWidget,
)


class SavedIdsPanel:
    """Общий UI + JSON-персист для сохранённых ID манхв и новелл."""

    def __init__(
        self,
        *,
        values_key: str,
        on_copy_to_title: Callable[[str], None],
        parent: Optional[QWidget] = None,
        settings_dir_provider: Optional[Callable[[], str]] = None,
    ):
        self.values_key = (values_key or '').strip() or 'saved_ids'
        self.on_copy_to_title = on_copy_to_title
        self.parent = parent
        self._settings_dir_provider = settings_dir_provider

        self.ui_built = False
        self.loaded = False
        self.visible = False

        self._ids: list[dict[str, str]] = []
        self._ids_grp: Optional[QGroupBox] = None
        self.ids_table: Optional[QTableWidget] = None

        self._ids_save_timer = QTimer(parent)
        self._ids_save_timer.setSingleShot(True)
        self._ids_save_timer.setInterval(200)
        self._ids_save_timer.timeout.connect(self._refresh_ids_from_table_and_save)

    def build_into(self, slot_layout: QVBoxLayout):
        if self.ui_built:
            return

        ids_grp = QGroupBox()
        self._ids_grp = ids_grp
        ids_grp.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        ids_v = QVBoxLayout(ids_grp)
        ids_v.setContentsMargins(8, 8, 8, 8)
        ids_v.setSpacing(6)

        self.ids_table = QTableWidget(0, 2)
        self.ids_table.setHorizontalHeaderLabels(["Название", "ID"])
        self.ids_table.setFixedHeight(200)
        self.ids_table.horizontalHeader().setStretchLastSection(True)
        self.ids_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.ids_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.ids_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.ids_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.ids_table.setEditTriggers(QAbstractItemView.AllEditTriggers)
        self.ids_table.setSortingEnabled(False)
        ids_v.addWidget(self.ids_table)

        row_btns = QHBoxLayout()
        row_btns.addStretch(1)
        self.btn_add_id = QPushButton("Добавить")
        self.btn_del_id = QPushButton("Удалить выбранные")
        self.btn_copy_to_title = QPushButton("→ в ID тайтла")
        for b in (self.btn_copy_to_title, self.btn_del_id, self.btn_add_id):
            b.setFixedHeight(24)
        row_btns.addWidget(self.btn_copy_to_title)
        row_btns.addWidget(self.btn_del_id)
        row_btns.addWidget(self.btn_add_id)
        ids_v.addLayout(row_btns)

        self.btn_add_id.clicked.connect(lambda: self._add_id_entry('', ''))
        self.btn_del_id.clicked.connect(self._delete_selected_ids)
        self.btn_copy_to_title.clicked.connect(self._copy_selected_id_to_title)
        self.ids_table.itemChanged.connect(self._on_ids_item_changed)

        slot_layout.addWidget(ids_grp)
        ids_grp.setVisible(False)
        self.ui_built = True
        self.visible = False

    def ensure_loaded(self):
        if self.loaded:
            return
        self._ids = self._load_ids_json()
        self._rebuild_ids_ui()
        self.loaded = True

    def toggle_visibility(self):
        if not self.ui_built or not self._ids_grp:
            return
        visible = self._ids_grp.isVisible()
        self._ids_grp.setVisible(not visible)
        self.visible = not visible

    def _settings_dir(self) -> str:
        if callable(self._settings_dir_provider):
            try:
                provided = (self._settings_dir_provider() or '').strip()
                if provided:
                    return provided
            except Exception:
                pass

        cached = getattr(self, '_settings_dir_cached', None)
        if cached:
            return cached

        try:
            anchor = inspect.getsourcefile(type(self.parent)) if self.parent is not None else None
        except Exception:
            anchor = None
        base = get_settings_dir(anchor)
        self._settings_dir_cached = base
        return base


    def _ids_json_path(self) -> str:
        return os.path.join(self._settings_dir(), 'values.json')

    def _load_all_values(self) -> dict:
        path = self._ids_json_path()
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {}

    def _save_all_values(self, data: dict):
        path = self._ids_json_path()
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_ids_json(self) -> list[dict[str, str]]:
        blob = self._load_all_values()
        raw = blob.get(self.values_key, [])
        out: list[dict[str, str]] = []
        if isinstance(raw, list):
            for it in raw:
                name = (it.get('name') or '').strip() if isinstance(it, dict) else ''
                _id = (it.get('id') or '').strip() if isinstance(it, dict) else ''
                if name or _id:
                    out.append({'name': name, 'id': _id})
        return out

    def _save_ids_json(self):
        blob = self._load_all_values()
        blob[self.values_key] = self._ids
        self._save_all_values(blob)

    def _rebuild_ids_ui(self):
        if not self.ids_table:
            return
        self.ids_table.setUpdatesEnabled(False)
        self.ids_table.blockSignals(True)
        try:
            self.ids_table.setRowCount(len(self._ids))
            for row, item in enumerate(self._ids):
                self.ids_table.setItem(row, 0, QTableWidgetItem(item.get('name', '')))
                self.ids_table.setItem(row, 1, QTableWidgetItem(item.get('id', '')))
        finally:
            self.ids_table.blockSignals(False)
            self.ids_table.setUpdatesEnabled(True)

    def _table_to_ids(self) -> list[dict[str, str]]:
        data: list[dict[str, str]] = []
        if not self.ids_table:
            return data
        rows = self.ids_table.rowCount()
        for r in range(rows):
            it_name = self.ids_table.item(r, 0)
            it_id = self.ids_table.item(r, 1)
            name = it_name.text().strip() if it_name else ''
            _id = it_id.text().strip() if it_id else ''
            if name or _id:
                data.append({'name': name, 'id': _id})
        return data

    def _refresh_ids_from_table_and_save(self):
        self._ids = self._table_to_ids()
        self._save_ids_json()

    def _on_ids_item_changed(self, _item: QTableWidgetItem):
        self._ids_save_timer.start()

    def _add_id_entry(self, name: str, id_value: str):
        if not self.ids_table:
            return
        self.ids_table.blockSignals(True)
        r = self.ids_table.rowCount()
        self.ids_table.insertRow(r)
        self.ids_table.setItem(r, 0, QTableWidgetItem((name or '').strip()))
        self.ids_table.setItem(r, 1, QTableWidgetItem((id_value or '').strip()))
        self.ids_table.blockSignals(False)
        self._refresh_ids_from_table_and_save()

    def _delete_selected_ids(self):
        if not self.ids_table:
            return
        rows = sorted({i.row() for i in self.ids_table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        self.ids_table.blockSignals(True)
        for r in rows:
            self.ids_table.removeRow(r)
        self.ids_table.blockSignals(False)
        self._refresh_ids_from_table_and_save()

    def _copy_selected_id_to_title(self):
        if not self.ids_table:
            return
        sel = self.ids_table.selectedItems()
        if not sel:
            return
        row = sel[0].row()
        id_item = self.ids_table.item(row, 1)
        if not id_item:
            return
        id_value = (id_item.text() or '').strip()
        if not id_value:
            return
        try:
            self.on_copy_to_title(id_value)
        except Exception:
            pass

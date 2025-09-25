from __future__ import annotations
import os, sys, json, pathlib
from typing import Callable, List, Dict, Optional

from PySide6.QtCore import QStandardPaths, QTimer
from PySide6.QtWidgets import (
    QGroupBox, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QPushButton, QHBoxLayout, QSizePolicy, QWidget, QMessageBox
)

class IdsBankPanel:
    """Инкапсулирует UI и JSON-персист для 'сохранённых ID'."""
    def __init__(self, on_copy_to_title: Callable[[str], None], parent: Optional[QWidget] = None):
        self.on_copy_to_title = on_copy_to_title
        self.parent = parent
        self.ui_built = False
        self.loaded = False
        self.visible = False

        self._ids: List[Dict[str, str]] = []
        self._ids_grp: Optional[QGroupBox] = None
        self.ids_table: Optional[QTableWidget] = None

        # отложенное сохранение
        self._ids_save_timer = QTimer(parent)
        self._ids_save_timer.setSingleShot(True)
        self._ids_save_timer.setInterval(200)
        self._ids_save_timer.timeout.connect(self._refresh_ids_from_table_and_save)

    # === Build / show ===
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
        self.ids_table.setFixedHeight(120)
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

        # wiring
        self.btn_add_id.clicked.connect(lambda: self._add_id_entry("", ""))
        self.btn_del_id.clicked.connect(self._delete_selected_ids)
        self.btn_copy_to_title.clicked.connect(self._copy_selected_id_to_title)
        self.ids_table.itemChanged.connect(self._on_ids_item_changed)

        slot_layout.addWidget(ids_grp)
        ids_grp.setVisible(False)
        self.ui_built = True
        self.visible = False

    def toggle_visibility(self):
        if not self.ui_built or not self._ids_grp:
            return
        vis = self._ids_grp.isVisible()
        self._ids_grp.setVisible(not vis)
        self.visible = not vis

    # === Data ===
    def ensure_loaded(self):
        if self.loaded:
            return
        self._ids = self._load_ids_json()
        self._rebuild_ids_ui()
        self.loaded = True

    # === Internals ===
    def _settings_dir(self) -> str:
        cached = getattr(self, "_settings_dir_cached", None)
        if cached:
            return cached

        def _is_writable(dir_path: str) -> bool:
            try:
                os.makedirs(dir_path, exist_ok=True)
                test = os.path.join(dir_path, ".write_test")
                with open(test, "w", encoding="utf-8") as f:
                    f.write("")
                os.remove(test)
                return True
            except Exception:
                return False

        base: Optional[str] = None
        try:
            if getattr(sys, "frozen", False):
                base = os.path.dirname(sys.executable)
            else:
                cwd = os.getcwd()
                if os.path.exists(os.path.join(cwd, "settings.ini")):
                    base = cwd
                else:
                    p = pathlib.Path(__file__).resolve()
                    for parent in [p.parent, *p.parents]:
                        if (parent / "settings.ini").exists():
                            base = str(parent)
                            break
                    if not base:
                        base = cwd

            if not _is_writable(base):
                app_data = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or ""
                if app_data and _is_writable(app_data):
                    base = app_data
                else:
                    home = os.path.expanduser("~")
                    base = home if _is_writable(home) else os.getcwd()
        except Exception:
            home = os.path.expanduser("~")
            base = home if os.path.isdir(home) else os.getcwd()

        self._settings_dir_cached = base
        return base

    def _ids_json_path(self) -> str:
        return os.path.join(self._settings_dir(), "values.json")

    def _load_all_values(self) -> dict:
        path = self._ids_json_path()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {}

    def _save_all_values(self, data: dict):
        path = self._ids_json_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_ids_json(self) -> list[dict]:
        blob = self._load_all_values()
        raw = blob.get("manhwa_ids", [])
        out = []
        if isinstance(raw, list):
            for it in raw:
                name = (it.get("name") or "").strip() if isinstance(it, dict) else ""
                _id = (it.get("id") or "").strip() if isinstance(it, dict) else ""
                if name or _id:
                    out.append({"name": name, "id": _id})
        return out

    def _save_ids_json(self):
        blob = self._load_all_values()
        blob["manhwa_ids"] = self._ids
        self._save_all_values(blob)

    def _rebuild_ids_ui(self):
        if not self.ids_table:
            return
        self.ids_table.setUpdatesEnabled(False)
        self.ids_table.blockSignals(True)
        try:
            self.ids_table.setRowCount(len(self._ids))
            for row, item in enumerate(self._ids):
                self.ids_table.setItem(row, 0, QTableWidgetItem(item.get("name", "")))
                self.ids_table.setItem(row, 1, QTableWidgetItem(item.get("id", "")))
        finally:
            self.ids_table.blockSignals(False)
            self.ids_table.setUpdatesEnabled(True)

    def _table_to_ids(self) -> list[dict]:
        data: list[dict] = []
        if not self.ids_table:
            return data
        rows = self.ids_table.rowCount()
        for r in range(rows):
            name_item = self.ids_table.item(r, 0)
            id_item = self.ids_table.item(r, 1)
            name = name_item.text().strip() if name_item else ""
            _id = id_item.text().strip() if id_item else ""
            if name or _id:
                data.append({"name": name, "id": _id})
        return data

    def _refresh_ids_from_table_and_save(self):
        self._ids = self._table_to_ids()
        self._save_ids_json()

    def _on_ids_item_changed(self, item):
        self._ids_save_timer.start()

    def _add_id_entry(self, name: str, id_value: str):
        if not self.ids_table:
            return
        self.ids_table.blockSignals(True)
        r = self.ids_table.rowCount()
        self.ids_table.insertRow(r)
        self.ids_table.setItem(r, 0, QTableWidgetItem((name or "").strip()))
        self.ids_table.setItem(r, 1, QTableWidgetItem((id_value or "").strip()))
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
        if id_item:
            id_value = (id_item.text() or "").strip()
            if id_value:
                try:
                    self.on_copy_to_title(id_value)
                except Exception:
                    pass

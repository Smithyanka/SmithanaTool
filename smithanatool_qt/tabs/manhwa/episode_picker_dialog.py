from __future__ import annotations
from typing import List, Dict, Any, Iterable
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QAbstractItemView, QHeaderView, QCheckBox, QWidget, QApplication, QLabel, QMenu
)
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QKeySequence, QShortcut, QGuiApplication

class EpisodePickerDialog(QDialog):
    """
    rows: Iterable[dict] из episode_map.json:
      {
        "productId": int,
        "title": str,
        "episodeNo": int | float | None,
        "isFree": bool | None,
        "isViewed": bool | None,
        "scheme": str | None,
        ...
      }
    """
    def __init__(self, series_title: str, rows: Iterable[Dict[str, Any]], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Выбор глав — {series_title or 'серия'}")
        self.resize(860, 600)

        self._rows = list(rows) or []
        self.table = QTableWidget(self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["✓", "Индекс", "Название", "productId"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)

        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)  # не редактируем
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)  # можно выделять диапазоны
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)  # выделяем ячейки (а не строки)

        # Ctrl+C
        QShortcut(QKeySequence.Copy, self.table, self._copy_selection)

        # Контекст-меню "Копировать"
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_menu)

        self._fill_table()

        btn_select_all = QPushButton("Выбрать все")
        btn_clear_all  = QPushButton("Снять все")
        btn_ok     = QPushButton("Скачать")
        btn_cancel = QPushButton("Отмена")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_select_all.clicked.connect(self._select_all)
        btn_clear_all.clicked.connect(self._clear_all)

        top_note = QLabel("Отметьте нужные главы и нажмите «Скачать».")
        top_note.setStyleSheet("color:#888;")

        lay = QVBoxLayout(self)
        lay.addWidget(top_note)
        lay.addWidget(self.table)

        row = QHBoxLayout()
        row.addWidget(btn_select_all)
        row.addWidget(btn_clear_all)
        row.addStretch(1)
        row.addWidget(btn_cancel)
        row.addWidget(btn_ok)
        lay.addLayout(row)

    def _fill_table(self):
        self.table.setRowCount(len(self._rows))
        for r, row in enumerate(self._rows):
            # чекбокс
            w = QWidget()
            cb = QCheckBox(w);
            cb.setChecked(False)
            ml = QHBoxLayout(w);
            ml.setContentsMargins(0, 0, 0, 0);
            ml.addWidget(cb);
            ml.addStretch(1)
            self.table.setCellWidget(r, 0, w)
            self.table.setRowHeight(r, 22)

            cur = row.get("cursor")
            try:
                idx_str = str(int(cur))
            except Exception:
                idx_str = str(r + 1)

            pid = row.get("productId") or ""
            title = (row.get("title") or "").strip()

            self.table.setItem(r, 1, QTableWidgetItem(idx_str))
            self.table.setItem(r, 2, QTableWidgetItem(title))
            self.table.setItem(r, 3, QTableWidgetItem(str(pid)))

            def _mk_item(text: str):
                it = QTableWidgetItem(text)
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)  # можно выделять/копировать, но не редактировать
                return it

            self.table.setItem(r, 1, _mk_item(idx_str))  # Индекс
            self.table.setItem(r, 2, _mk_item(title))  # Название
            self.table.setItem(r, 3, _mk_item(str(pid)))  # productId


    def _each_checkbox(self):
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 0)
            if not w:
                continue
            cb = w.findChild(QCheckBox)
            if cb:
                yield cb

    def _select_all(self):
        for cb in self._each_checkbox():
            cb.setChecked(True)

    def _clear_all(self):
        for cb in self._each_checkbox():
            cb.setChecked(False)

    def selected_product_ids(self) -> List[int]:
        out: List[int] = []
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 0)
            cb = w.findChild(QCheckBox) if w else None
            if cb and cb.isChecked():
                pid_item = self.table.item(r, 3)
                try:
                    out.append(int(pid_item.text()))
                except Exception:
                    pass
        return out

    def _copy_selection(self):
        tbl = self.table
        ranges = tbl.selectedRanges()
        # если ничего не выделено — копируем текущую ячейку
        if not ranges:
            it = tbl.currentItem()
            if it:
                QGuiApplication.clipboard().setText(it.text())
            return

        r = ranges[0]
        lines = []
        for row in range(r.topRow(), r.bottomRow() + 1):
            vals = []
            for col in range(r.leftColumn(), r.rightColumn() + 1):
                if col == 0:
                    continue  # пропускаем чекбокс
                it = tbl.item(row, col)
                if it is not None:
                    vals.append(it.text())
                else:
                    w = tbl.cellWidget(row, col)
                    vals.append(getattr(w, "text", "") if w else "")
            if vals:
                lines.append("\t".join(vals))
        QGuiApplication.clipboard().setText("\n".join(lines))

    def _on_table_menu(self, pos: QPoint):
        menu = QMenu(self)
        act = menu.addAction("Копировать")
        act.triggered.connect(self._copy_selection)
        menu.exec(self.table.viewport().mapToGlobal(pos))
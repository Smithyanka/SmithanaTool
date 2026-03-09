from __future__ import annotations

from typing import Any, Dict, Iterable, List

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class EpisodePickerDialog(QDialog):
    """
    Модальное окно выбора глав/томов.
    Может использоваться как с уже готовым списком rows, так и с отложенным заполнением через set_rows().
    """

    def __init__(self, series_title: str, rows: Iterable[Dict[str, Any]] | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Выбор глав — {series_title or 'серия'}")
        self.resize(860, 600)
        self._rows: list[dict] = []
        self._loading = False

        self.top_note = QLabel('Подготовка списка глав...')
        self.top_note.setStyleSheet('color:#888;')

        self.status_label = QLabel('')
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet('color:#666;')

        self.table = QTableWidget(self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(['✓', 'Индекс', 'Название', 'productId'])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)

        QShortcut(QKeySequence.Copy, self.table, self._copy_selection)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_menu)

        self.btn_select_all = QPushButton('Выбрать все')
        self.btn_clear_all = QPushButton('Снять все')
        self.btn_ok = QPushButton('Скачать')
        self.btn_cancel = QPushButton('Отмена')
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_select_all.clicked.connect(self._select_all)
        self.btn_clear_all.clicked.connect(self._clear_all)

        lay = QVBoxLayout(self)
        lay.addWidget(self.top_note)
        lay.addWidget(self.status_label)
        lay.addWidget(self.table)

        row = QHBoxLayout()
        row.addWidget(self.btn_select_all)
        row.addWidget(self.btn_clear_all)
        row.addStretch(1)
        row.addWidget(self.btn_cancel)
        row.addWidget(self.btn_ok)
        lay.addLayout(row)

        self.set_loading('Загрузка списка глав...')
        if rows:
            self.set_rows(rows)

    def set_loading(self, text: str = 'Загрузка списка глав...') -> None:
        self._loading = True
        self.top_note.setText('Подготовка списка глав...')
        self.status_label.setText(text)
        self.status_label.setStyleSheet('color:#666;')
        self.table.setRowCount(0)
        self.btn_select_all.setEnabled(False)
        self.btn_clear_all.setEnabled(False)
        self.btn_ok.setEnabled(False)

    def set_rows(self, rows: Iterable[Dict[str, Any]]) -> None:
        self._rows = list(rows) or []
        self._loading = False
        self.top_note.setText('Отметьте нужные главы и нажмите «Скачать».')
        self.status_label.setText(f'Найдено элементов: {len(self._rows)}')
        self.status_label.setStyleSheet('color:#666;')
        self._fill_table()
        has_rows = bool(self._rows)
        self.btn_select_all.setEnabled(has_rows)
        self.btn_clear_all.setEnabled(has_rows)
        self.btn_ok.setEnabled(has_rows)

    def set_error(self, text: str) -> None:
        self._loading = False
        self.top_note.setText('Не удалось загрузить список глав.')
        self.status_label.setText(text or 'Неизвестная ошибка.')
        self.status_label.setStyleSheet('color:#a00;')
        self.table.setRowCount(0)
        self.btn_select_all.setEnabled(False)
        self.btn_clear_all.setEnabled(False)
        self.btn_ok.setEnabled(False)

    def is_loading(self) -> bool:
        return self._loading

    def _fill_table(self) -> None:
        self.table.setRowCount(len(self._rows))
        for r, row in enumerate(self._rows):
            w = QWidget()
            cb = QCheckBox(w)
            cb.setChecked(False)
            ml = QHBoxLayout(w)
            ml.setContentsMargins(0, 0, 0, 0)
            ml.addWidget(cb)
            ml.addStretch(1)
            self.table.setCellWidget(r, 0, w)
            self.table.setRowHeight(r, 22)

            cur = row.get('cursor')
            try:
                idx_str = str(int(cur))
            except Exception:
                idx_str = str(r + 1)

            pid = row.get('productId') or ''
            title = (row.get('title') or '').strip()

            def _mk_item(text: str):
                it = QTableWidgetItem(text)
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                return it

            self.table.setItem(r, 1, _mk_item(idx_str))
            self.table.setItem(r, 2, _mk_item(title))
            self.table.setItem(r, 3, _mk_item(str(pid)))

    def _each_checkbox(self):
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 0)
            if not w:
                continue
            cb = w.findChild(QCheckBox)
            if cb:
                yield cb

    def _select_all(self) -> None:
        for cb in self._each_checkbox():
            cb.setChecked(True)

    def _clear_all(self) -> None:
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

    def _copy_selection(self) -> None:
        tbl = self.table
        ranges = tbl.selectedRanges()
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
                    continue
                it = tbl.item(row, col)
                if it is not None:
                    vals.append(it.text())
                else:
                    w = tbl.cellWidget(row, col)
                    vals.append(getattr(w, 'text', '') if w else '')
            if vals:
                lines.append('\t'.join(vals))
        QGuiApplication.clipboard().setText('\n'.join(lines))

    def _on_table_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        act = menu.addAction('Копировать')
        act.triggered.connect(self._copy_selection)
        menu.exec(self.table.viewport().mapToGlobal(pos))

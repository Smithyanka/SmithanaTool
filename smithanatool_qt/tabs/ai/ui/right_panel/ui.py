from __future__ import annotations

from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QListWidget,
    QAbstractItemView,
)
from PySide6.QtGui import QKeySequence, QShortcut


def build_action_buttons(panel, parent_layout: QVBoxLayout) -> None:
    row_buttons = QHBoxLayout()
    row_buttons.setSpacing(8)
    panel.btn_extract = QPushButton("Распознать текст")
    panel.btn_handwriting = QPushButton("Рукописный ввод")

    row_buttons.addWidget(panel.btn_extract)
    row_buttons.addWidget(panel.btn_handwriting)
    parent_layout.addLayout(row_buttons)


def build_list(panel, parent_layout: QVBoxLayout) -> None:
    panel.list = QListWidget()
    panel.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
    panel.list.setDragEnabled(True)
    panel.list.setAcceptDrops(True)
    panel.list.setDragDropMode(QAbstractItemView.InternalMove)
    parent_layout.addWidget(panel.list, 1)

    # Шорткаты для списка (Ctrl+A/Ctrl+C/Del)
    panel._sc_select_all = QShortcut(QKeySequence.SelectAll, panel.list)
    panel._sc_select_all.activated.connect(panel.list.selectAll)
    panel._sc_select_all.activatedAmbiguously.connect(panel.list.selectAll)

    panel._sc_copy = QShortcut(QKeySequence.Copy, panel.list)
    panel._sc_copy.activated.connect(panel._copy_selected)
    panel._sc_copy.activatedAmbiguously.connect(panel._copy_selected)

    panel._sc_delete = QShortcut(QKeySequence.Delete, panel.list)
    panel._sc_delete.activated.connect(panel._delete_selected)
    panel._sc_delete.activatedAmbiguously.connect(panel._delete_selected)


def build_save_button(panel, parent_layout: QVBoxLayout) -> None:
    panel.btn_save = QPushButton("Сохранить…")
    parent_layout.addWidget(panel.btn_save)

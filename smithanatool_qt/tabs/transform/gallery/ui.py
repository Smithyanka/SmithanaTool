from __future__ import annotations

from dataclasses import dataclass
from typing import List
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import (
    QAction,
)
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QAbstractItemView,
    QComboBox,
    QFrame,
    QToolButton,
    QMenu,
)

from .widgets import RightSelectableList
from smithanatool_qt.graphic.foundation.assets import DEFAULT_ICON_SIZE, set_themed_icon, make_sep

# -----------------------------------------------------------------------------

ARROW_ICON_SIZE = QSize(11, 11)

@dataclass(slots=True)
class GalleryPanelUi:
    layout: QVBoxLayout

    # top
    btn_open_files: QPushButton
    btn_open_folder: QToolButton
    cmb_sort_field: QComboBox
    cmb_sort_order: QComboBox
    btn_sort: QToolButton
    sort_menu: QMenu
    sort_field_actions: List[QAction]
    sort_order_actions: List[QAction]
    btn_view: QToolButton

    # stats
    lbl_files: QLabel
    btn_select_all: QPushButton

    # list
    list: RightSelectableList

    # bottom
    btn_up: QPushButton
    btn_down: QPushButton
    btn_delete_selected: QPushButton
    btn_clear: QPushButton


    def set_view_mode(self, thumbs: bool) -> None:
        # Переключает кнопку вида (иконка/текст/checked) без срабатывания toggled.
        self.btn_view.blockSignals(True)
        self.btn_view.setChecked(bool(thumbs))
        if thumbs:
            set_themed_icon(self.btn_view, "grid.svg", "view_grid.svg", "preview.svg", "grid.png", size=DEFAULT_ICON_SIZE)
        else:
            set_themed_icon(self.btn_view, "list.svg", "view_list.svg", "list.png", size=DEFAULT_ICON_SIZE)
        self.btn_view.blockSignals(False)



def build_ui(panel: QWidget) -> GalleryPanelUi:
    # Панель должна занимать всю ширину, без внешних отступов.
    outer = QVBoxLayout(panel)
    outer.setContentsMargins(4, 0, 0, 0)
    outer.setSpacing(0)

    # Единый «контейнер галереи» на всю область.
    root = QFrame(panel)
    root.setObjectName("galleryRoot")
    root.setFrameShape(QFrame.NoFrame)


    outer.addWidget(root, 1)

    v = QVBoxLayout(root)
    v.setContentsMargins(10, 10, 10, 10)
    v.setSpacing(10)

    # =========================
    # TOP ROW
    # =========================
    row_top = QHBoxLayout()
    row_top.setSpacing(8)

    btn_open_files = QPushButton(" Добавить")
    set_themed_icon(btn_open_files, "add.svg", "plus.svg", "add.png", "plus.png", size=DEFAULT_ICON_SIZE)


    btn_open_folder = QToolButton()
    btn_open_folder.setText("")
    btn_open_folder.setToolTip("Добавить папку…")
    btn_open_folder.setAutoRaise(True)
    set_themed_icon(btn_open_folder,  "open_folder.svg", size=DEFAULT_ICON_SIZE)
    btn_open_folder.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    btn_open_folder.setObjectName("btnFolder")

    # сортировка (combobox скрытые; меню на кнопке)
    cmb_sort_field = QComboBox()
    cmb_sort_field.addItems(["По названию", "По дате", "По добавлению"])
    cmb_sort_field.setVisible(False)

    cmb_sort_order = QComboBox()
    cmb_sort_order.addItems(["По возрастанию", "По убыванию"])
    cmb_sort_order.setVisible(False)

    btn_sort = QToolButton()
    btn_sort.setText("")
    btn_sort.setToolTip("Сортировка")
    btn_sort.setAutoRaise(True)
    btn_sort.setPopupMode(QToolButton.InstantPopup)
    set_themed_icon(btn_sort, "sort.svg", "sort.png", "sort_alpha.svg", "sort_down.svg", size=DEFAULT_ICON_SIZE)
    btn_sort.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

    sort_menu = QMenu(panel)
    m_field = sort_menu.addMenu("Поле")
    m_order = sort_menu.addMenu("Порядок")

    sort_field_actions: List[QAction] = []
    for i in range(cmb_sort_field.count()):
        text = cmb_sort_field.itemText(i)
        act = QAction(text, panel, checkable=True)
        act.triggered.connect(lambda _=False, idx=i: cmb_sort_field.setCurrentIndex(idx))
        m_field.addAction(act)
        sort_field_actions.append(act)

    sort_order_actions: List[QAction] = []
    for i in range(cmb_sort_order.count()):
        text = cmb_sort_order.itemText(i)
        act = QAction(text, panel, checkable=True)
        act.triggered.connect(lambda _=False, idx=i: cmb_sort_order.setCurrentIndex(idx))
        m_order.addAction(act)
        sort_order_actions.append(act)

    btn_sort.setMenu(sort_menu)

    # вид (список/превью-список)
    btn_view = QToolButton()
    btn_view.setCheckable(True)
    btn_view.setAutoRaise(True)
    btn_view.setText("")
    btn_view.setToolTip("Вид")
    set_themed_icon(btn_view, "list.svg", "view_list.svg", "list.png", size=DEFAULT_ICON_SIZE)
    btn_view.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

    row_top.addWidget(btn_open_files)
    row_top.addWidget(btn_open_folder)
    row_top.addStretch(1)
    row_top.addWidget(btn_sort)
    row_top.addWidget(btn_view)
    v.addLayout(row_top)

    TOP_H = 32
    ICON_W = 36
    ADD_MIN_W = 100

    # "Добавить"
    btn_open_files.setProperty("topFrame", True)
    btn_open_files.setProperty("topKind", "add")
    btn_open_files.setObjectName("btnAdd")
    btn_open_files.setFixedHeight(TOP_H)
    btn_open_files.setMinimumWidth(ADD_MIN_W)


    # иконки (папка / сортировка / вид)
    for b in (btn_open_folder, btn_sort, btn_view):
        b.setAutoRaise(False)  # иначе будет “плоско”
        b.setProperty("topFrame", True)
        b.setProperty("topKind", "icon")
        b.setFixedSize(ICON_W, TOP_H)
        b.setToolButtonStyle(Qt.ToolButtonIconOnly)


        # визуальное разделение между 1-й и 2-й строкой
    v.addWidget(make_sep(root))

    # =========================
    # STATS ROW
    # =========================
    lbl_files = QLabel("Всего: 0 | Выбрано: 0")
    btn_select_all = QPushButton("Выбрать все")

    row_stats = QHBoxLayout()
    row_stats.setSpacing(8)
    row_stats.addWidget(lbl_files)
    row_stats.addStretch(1)
    row_stats.addWidget(btn_select_all)
    v.addLayout(row_stats)

    # =========================
    # LIST
    # =========================
    lst = RightSelectableList()
    lst.setFrameShape(QFrame.NoFrame)
    lst.setSelectionMode(QAbstractItemView.ExtendedSelection)
    lst.setDragEnabled(True)
    lst.setAcceptDrops(True)
    lst.setDragDropMode(QAbstractItemView.InternalMove)
    lst.setDefaultDropAction(Qt.MoveAction)
    v.addWidget(lst, 1)

    # небольшое разделение перед нижними кнопками
    v.addWidget(make_sep(root))

    # =========================
    # BOTTOM ROW
    # =========================
    row_bottom = QHBoxLayout()
    row_bottom.setSpacing(8)

    btn_up = QPushButton("")
    btn_up.setToolTip("Вверх")
    set_themed_icon(btn_up, "up.svg", size=ARROW_ICON_SIZE)

    btn_down = QPushButton("")
    btn_down.setToolTip("Вниз")
    set_themed_icon(btn_down, "down.svg", size=ARROW_ICON_SIZE)

    for b in (btn_up, btn_down):
        b.setFixedSize(40, 30)


    btn_delete_selected = QPushButton("Удалить")
    btn_clear = QPushButton("Очистить")

    row_bottom.addWidget(btn_up)
    row_bottom.addWidget(btn_down)
    row_bottom.addStretch(1)
    row_bottom.addWidget(btn_delete_selected)
    row_bottom.addWidget(btn_clear)
    v.addLayout(row_bottom)

    return GalleryPanelUi(
        layout=outer,
        btn_open_files=btn_open_files,
        btn_open_folder=btn_open_folder,
        cmb_sort_field=cmb_sort_field,
        cmb_sort_order=cmb_sort_order,
        btn_sort=btn_sort,
        sort_menu=sort_menu,
        sort_field_actions=sort_field_actions,
        sort_order_actions=sort_order_actions,
        btn_view=btn_view,
        lbl_files=lbl_files,
        btn_select_all=btn_select_all,
        list=lst,
        btn_up=btn_up,
        btn_down=btn_down,
        btn_delete_selected=btn_delete_selected,
        btn_clear=btn_clear,
    )

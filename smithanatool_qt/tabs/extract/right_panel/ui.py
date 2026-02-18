from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QLineEdit,
    QSpinBox,
    QCheckBox,
    QPushButton,
    QListWidget,
    QAbstractItemView,
)
from PySide6.QtGui import QKeySequence, QShortcut


def build_settings_group(panel) -> QWidget:
    w = QWidget()
    lv = QVBoxLayout(w)
    lv.setContentsMargins(8, 6, 8, 6)
    lv.setSpacing(6)

    # ── Движок ─────────────────────────────────────────────────────────────
    row_engine = QHBoxLayout()
    row_engine.setSpacing(8)
    lv.addLayout(row_engine)
    row_engine.addWidget(QLabel("Движок:"), 0)
    panel.cmb_engine = QComboBox()
    panel.cmb_engine.addItems(["Gemini (RouterAI)", "Yandex Cloud"])
    panel.cmb_engine.setSizeAdjustPolicy(QComboBox.AdjustToContents)
    panel.cmb_engine.setMinimumContentsLength(1)
    panel.cmb_engine.setMaximumWidth(180)
    row_engine.addWidget(panel.cmb_engine)
    row_engine.addStretch(1)

    # ── Gemini API key ─────────────────────────────────────────────────────
    row0 = QHBoxLayout()
    row0.setSpacing(8)
    lv.addLayout(row0)
    panel.lbl_gemini_api_key = QLabel("RouterAI API key:")
    row0.addWidget(panel.lbl_gemini_api_key, 0)
    panel.ed_api_key = QLineEdit()
    panel.ed_api_key.setEchoMode(QLineEdit.Password)
    panel.ed_api_key.setPlaceholderText(
        "ROUTERAI_API_KEY"
    )
    row0.addWidget(panel.ed_api_key, 1)

    # ── Модель ────────────────────────────────────────────────────────────
    row1 = QHBoxLayout()
    row1.setSpacing(8)
    lv.addLayout(row1)
    panel.lbl_gemini_model = QLabel("Модель:")
    row1.addWidget(panel.lbl_gemini_model)
    panel.cmb_model = QComboBox()
    panel.cmb_model.clear()

    _models = [
        ("Gemini 2.5 Flash", "google/gemini-2.5-flash"),
        #("Gemini 3 Flash Preview", "google/gemini-3-flash-preview"),
        #("Gemini 3 Pro Preview", "google/gemini-3-pro-preview"),


    ]
    for title, model_id in _models:
        panel.cmb_model.addItem(title, model_id)

    panel.cmb_model.setSizeAdjustPolicy(QComboBox.AdjustToContents)
    panel.cmb_model.setMinimumContentsLength(1)
    panel.cmb_model.setMaximumWidth(160)
    row1.addWidget(panel.cmb_model)
    row1.addStretch(1)

    # ── Размер батча ──────────────────────────────────────────────────────
    row_bs = QHBoxLayout()
    row_bs.setSpacing(8)
    lv.addLayout(row_bs)

    panel.lbl_gemini_batch = QLabel("Размер батча*:")
    row_bs.addWidget(panel.lbl_gemini_batch, 0)

    panel.spn_gemini_batch = QSpinBox()
    panel.spn_gemini_batch.setRange(1, 16)
    panel.spn_gemini_batch.setValue(4)
    panel.spn_gemini_batch.setMaximumWidth(80)
    row_bs.addWidget(panel.spn_gemini_batch, 0)
    row_bs.addStretch(1)

    # ── Пояснение под полем ────────────────────────────────────────────
    row_bs_hint = QHBoxLayout()
    row_bs_hint.setSpacing(0)
    row_bs_hint.setContentsMargins(0, 0, 0, 5)
    lv.addLayout(row_bs_hint)

    panel.lbl_gemini_batch_hint = QLabel(
        "*Сколько фрагментов за один запрос.\nБольше — дешевле, но медленнее."
    )
    panel.lbl_gemini_batch_hint.setStyleSheet("color: #454545; font-size: 12px;")
    row_bs_hint.addWidget(panel.lbl_gemini_batch_hint, 0)
    row_bs_hint.addStretch(1)

    # ── Yandex Cloud ───────────────────────────────────────────────────
    row_y1 = QHBoxLayout()
    row_y1.setSpacing(8)
    lv.addLayout(row_y1)
    panel.lbl_yc_api_key = QLabel("Yandex API key:")
    row_y1.addWidget(panel.lbl_yc_api_key, 0)
    panel.ed_yc_api_key = QLineEdit()
    panel.ed_yc_api_key.setEchoMode(QLineEdit.Password)
    panel.ed_yc_api_key.setPlaceholderText(
        "YC_API_KEY"
    )
    row_y1.addWidget(panel.ed_yc_api_key, 1)

    row_y2 = QHBoxLayout()
    row_y2.setSpacing(8)
    lv.addLayout(row_y2)
    panel.lbl_yc_folder_id = QLabel("Folder ID:")
    row_y2.addWidget(panel.lbl_yc_folder_id, 0)
    panel.ed_yc_folder_id = QLineEdit()
    panel.ed_yc_folder_id.setPlaceholderText("YC_FOLDER_ID (b1g...)")
    row_y2.addWidget(panel.ed_yc_folder_id, 1)

    # ── Подсказка языка ─────────────────────────────────────────────────
    row2 = QHBoxLayout()
    row2.setSpacing(8)
    lv.addLayout(row2)
    panel.lbl_text_lang = QLabel("Подсказка языка:")
    row2.addWidget(panel.lbl_text_lang)

    panel.cmb_lang = QComboBox()
    panel.cmb_lang.clear()

    # отображение (text) и то, что реально уходит в код/ini (data)
    panel.cmb_lang.addItem("Auto", "")  # пустая строка = нет подсказки
    panel.cmb_lang.addItem("English", "en")
    panel.cmb_lang.addItem("Korean", "ko")
    panel.cmb_lang.addItem("Japanese", "ja")

    panel.cmb_lang.setSizeAdjustPolicy(QComboBox.AdjustToContents)
    panel.cmb_lang.setMinimumContentsLength(1)
    panel.cmb_lang.setMaximumWidth(500)
    row2.addWidget(panel.cmb_lang)
    row2.addStretch(1)

    return w


def build_extra_group(panel) -> QWidget:
    w = QWidget()
    ev = QVBoxLayout(w)
    ev.setContentsMargins(8, 6, 8, 6)
    ev.setSpacing(6)

    rowx = QHBoxLayout()
    rowx.setSpacing(8)
    ev.addLayout(rowx)
    panel.chk_thumbs = QCheckBox("Миниатюры")
    rowx.addWidget(panel.chk_thumbs)
    rowx.addStretch(1)

    rowz = QHBoxLayout()
    rowz.setSpacing(8)
    ev.addLayout(rowz)
    rowz.addWidget(QLabel("Кнопки масштаба:"))
    panel.cmb_zoom_ui = QComboBox()
    panel.cmb_zoom_ui.addItems(["Классический", "Компактный"])
    panel.cmb_zoom_ui.setSizeAdjustPolicy(QComboBox.AdjustToContents)
    panel.cmb_zoom_ui.setMinimumContentsLength(1)
    panel.cmb_zoom_ui.setMaximumWidth(panel.cmb_zoom_ui.sizeHint().width() + 16)
    rowz.addWidget(panel.cmb_zoom_ui)
    rowz.addStretch(1)

    return w


def build_action_buttons(panel, parent_layout: QVBoxLayout) -> None:
    row_buttons = QHBoxLayout()
    row_buttons.setSpacing(8)
    panel.btn_extract = QPushButton("Извлечь текст")
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

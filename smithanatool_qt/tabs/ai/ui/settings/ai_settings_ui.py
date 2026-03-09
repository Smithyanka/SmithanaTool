from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QLineEdit,
    QSpinBox,
    QPushButton,
)

WIDTH = 27
HEIGHT = 27


from PySide6.QtCore import QSize, Qt
from smithanatool_qt.graphic.foundation.assets import set_themed_icon

def build_settings_group(host) -> QWidget:
    """Собирает UI блока "Настройки".

    `host` — объект-владелец, на который навешиваются атрибуты виджетов
    (cmb_engine, ed_api_key, cmb_model, cmb_lang и т.д.).

    Так блок можно встраивать в разные панели/вкладки.
    """

    w = QWidget()
    lv = QVBoxLayout(w)
    lv.setContentsMargins(8, 6, 8, 6)
    lv.setSpacing(6)

    # ── Движок ─────────────────────────────────────────────────────────────
    row_engine = QHBoxLayout()
    row_engine.setSpacing(8)
    lv.addLayout(row_engine)
    row_engine.addWidget(QLabel("Движок:"), 0)

    host.cmb_engine = QComboBox()
    host.cmb_engine.setSizeAdjustPolicy(QComboBox.AdjustToContents)
    host.cmb_engine.setMinimumContentsLength(1)
    host.cmb_engine.setMaximumWidth(220)
    row_engine.addWidget(host.cmb_engine)

    host.btn_add_engine = QPushButton("+")
    host.btn_add_engine.setFixedWidth(WIDTH)
    host.btn_add_engine.setFixedHeight(HEIGHT)
    host.btn_add_engine.setToolTip("Добавить движок")
    row_engine.addWidget(host.btn_add_engine)

    host.btn_remove_engine = QPushButton("−")
    host.btn_remove_engine.setFixedWidth(WIDTH)
    host.btn_remove_engine.setFixedHeight(HEIGHT)
    host.btn_remove_engine.setToolTip("Удалить движок")
    row_engine.addWidget(host.btn_remove_engine)

    host.btn_edit_engine = QPushButton("")
    host.btn_edit_engine.setFixedWidth(WIDTH)
    host.btn_edit_engine.setFixedHeight(HEIGHT)
    host.btn_edit_engine.setToolTip("Редактировать движок")

    set_themed_icon(host.btn_edit_engine, "engine_edit.svg", size=QSize(10, 10))

    row_engine.addWidget(host.btn_edit_engine)

    row_engine.addStretch(1)

    # ── API key (LLM) ──────────────────────────────────────────────────────
    row0 = QHBoxLayout()
    row0.setSpacing(8)
    lv.addLayout(row0)

    host.lbl_gemini_api_key = QLabel("API key:")
    row0.addWidget(host.lbl_gemini_api_key, 0)

    host.ed_api_key = QLineEdit()
    host.ed_api_key.setEchoMode(QLineEdit.Password)
    host.ed_api_key.setPlaceholderText("API_KEY")
    row0.addWidget(host.ed_api_key, 1)

    # ── Модель ────────────────────────────────────────────────────────────
    row1 = QHBoxLayout()
    row1.setSpacing(8)
    lv.addLayout(row1)

    host.lbl_gemini_model = QLabel("Модель:")
    row1.addWidget(host.lbl_gemini_model)

    host.cmb_model = QComboBox()
    host.cmb_model.clear()

    # базовый набор (встроенный движок)
    _models = [
        ("Gemini 2.5 Flash Lite", "google/gemini-2.5-flash-lite"),
        ("Gemini 2.5 Flash", "google/gemini-2.5-flash"),
    ]
    for title, model_id in _models:
        host.cmb_model.addItem(title, model_id)

    host.cmb_model.setSizeAdjustPolicy(QComboBox.AdjustToContents)
    host.cmb_model.setMinimumContentsLength(1)
    host.cmb_model.setMaximumWidth(200)
    row1.addWidget(host.cmb_model)
    row1.addStretch(1)

    # ── Размер батча ──────────────────────────────────────────────────────
    row_bs = QHBoxLayout()
    row_bs.setSpacing(8)
    lv.addLayout(row_bs)

    host.lbl_batch = QLabel("Размер батча*:")
    row_bs.addWidget(host.lbl_batch, 0)

    host.spn_batch = QSpinBox()
    host.spn_batch.setRange(1, 32)
    host.spn_batch.setValue(4)
    host.spn_batch.setMaximumWidth(80)
    row_bs.addWidget(host.spn_batch, 0)
    row_bs.addStretch(1)

    # ── Пояснение под полем ───────────────────────────────────────────────
    row_bs_hint = QHBoxLayout()
    row_bs_hint.setSpacing(0)
    row_bs_hint.setContentsMargins(0, 0, 0, 5)
    lv.addLayout(row_bs_hint)

    host.lbl_batch_hint = QLabel(
        "*Сколько фрагментов за один запрос.\nБольше — дешевле, но медленнее."
    )
    host.lbl_batch_hint.setWordWrap(True)
    host.lbl_batch_hint.setTextFormat(Qt.PlainText)
    host.lbl_batch_hint.setProperty("role", "hint")
    row_bs_hint.addWidget(host.lbl_batch_hint, 0)
    row_bs_hint.addStretch(1)

    # ── Yandex Cloud ──────────────────────────────────────────────────────
    row_y1 = QHBoxLayout()
    row_y1.setSpacing(8)
    lv.addLayout(row_y1)

    host.lbl_yc_api_key = QLabel("Yandex API key:")
    row_y1.addWidget(host.lbl_yc_api_key, 0)

    host.ed_yc_api_key = QLineEdit()
    host.ed_yc_api_key.setEchoMode(QLineEdit.Password)
    host.ed_yc_api_key.setPlaceholderText("YC_API_KEY")
    row_y1.addWidget(host.ed_yc_api_key, 1)

    row_y2 = QHBoxLayout()
    row_y2.setSpacing(8)
    lv.addLayout(row_y2)

    host.lbl_yc_folder_id = QLabel("Folder ID:")
    row_y2.addWidget(host.lbl_yc_folder_id, 0)

    host.ed_yc_folder_id = QLineEdit()
    host.ed_yc_folder_id.setPlaceholderText("YC_FOLDER_ID (b1g...)")
    row_y2.addWidget(host.ed_yc_folder_id, 1)

    # ── Подсказка языка ───────────────────────────────────────────────────
    row2 = QHBoxLayout()
    row2.setSpacing(8)
    lv.addLayout(row2)

    host.lbl_text_lang = QLabel("Подсказка языка:")
    row2.addWidget(host.lbl_text_lang)

    host.cmb_lang = QComboBox()
    host.cmb_lang.clear()

    # отображение (text) и то, что реально уходит в код/ini (data)
    host.cmb_lang.addItem("Auto", "")
    host.cmb_lang.addItem("English", "en")
    host.cmb_lang.addItem("Korean", "ko")
    host.cmb_lang.addItem("Japanese", "ja")

    host.cmb_lang.setSizeAdjustPolicy(QComboBox.AdjustToContents)
    host.cmb_lang.setMinimumContentsLength(1)
    host.cmb_lang.setMaximumWidth(500)
    row2.addWidget(host.cmb_lang)
    row2.addStretch(1)

    return w

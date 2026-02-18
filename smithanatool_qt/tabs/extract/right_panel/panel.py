from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget, QVBoxLayout

from .delegate import FragmentItemDelegate
from .ini_mixin import RightPanelIniMixin
from .list_mixin import RightPanelListMixin
from .ui import (
    build_settings_group,
    build_extra_group,
    build_action_buttons,
    build_list,
    build_save_button,
)


class OcrRightPanel(QWidget, RightPanelIniMixin, RightPanelListMixin):
    extractRequested = Signal()
    saveRequested = Signal(str)

    # сигналы CRUD по текстам
    itemDeleted = Signal(int)  # index
    itemEdited = Signal(int, str)  # index, new_text

    handwritingRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(8)

        # UI blocks
        from smithanatool_qt.widgets.collapsible import CollapsibleSection

        # UI blocks
        settings_widget = build_settings_group(self)
        sec_settings = CollapsibleSection("Настройки", settings_widget, expanded=True)
        self._bind_section_expanded(sec_settings, "expanded_settings", default=True)
        v.addWidget(sec_settings)

        extra_widget = build_extra_group(self)
        sec_extra = CollapsibleSection("Доп. настройки", extra_widget, expanded=False)
        self._bind_section_expanded(sec_extra, "expanded_extra", default=False)
        v.addWidget(sec_extra)

        build_action_buttons(self, v)
        build_list(self, v)
        build_save_button(self, v)

        # delegate
        self.list.setItemDelegate(FragmentItemDelegate(self.list))

        # контекстное меню
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._on_context_menu)

        # редактирование
        from PySide6.QtWidgets import QAbstractItemView
        self.list.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.SelectedClicked
        )

        # signals

        self.btn_extract.clicked.connect(self.extractRequested.emit)
        self.btn_handwriting.clicked.connect(self.handwritingRequested.emit)
        self.btn_save.clicked.connect(self._on_save)

        self._block_item_changed = False
        self.list.itemChanged.connect(self._on_item_changed)
        try:
            self.list.model().rowsMoved.connect(lambda *args: self._relabel())
        except Exception:
            pass

        # INI
        self._restore_ini()
        self._wire_persistence()

        # engine switching
        self.cmb_engine.currentIndexChanged.connect(lambda _i: self._refresh_engine_ui())
        self._refresh_engine_ui()

    def _refresh_engine_ui(self):
        """Показывает/скрывает поля Gemini/Yandex в зависимости от выбранного движка."""
        is_gemini = (self.cmb_engine.currentIndex() == 0)

        # Gemini
        self.lbl_gemini_api_key.setVisible(is_gemini)
        self.ed_api_key.setVisible(is_gemini)
        self.lbl_gemini_model.setVisible(is_gemini)
        self.cmb_model.setVisible(is_gemini)
        self.lbl_gemini_batch.setVisible(is_gemini)
        self.spn_gemini_batch.setVisible(is_gemini)
        self.lbl_gemini_batch_hint.setVisible(is_gemini)

        # "язык текста" полезен и для Gemini, и для Yandex, поэтому оставляем видимым всегда
        self.lbl_text_lang.setVisible(True)
        self.cmb_lang.setVisible(True)

        # Yandex
        self.lbl_yc_api_key.setVisible(not is_gemini)
        self.ed_yc_api_key.setVisible(not is_gemini)
        self.lbl_yc_folder_id.setVisible(not is_gemini)
        self.ed_yc_folder_id.setVisible(not is_gemini)

    def _bind_section_expanded(self, sec, key: str, default: bool = False):
        # прочитать
        val = self._get_ini_bool(key, default)

        # применить без анимации (как в твоём SectionsPanel)
        sec.toggle_button.blockSignals(True)
        sec.toggle_button.setChecked(val)
        sec.toggle_button.blockSignals(False)
        try:
            sec._set_content_visible(val, animate=False)
            sec._update_header_icon(val)
            sec.setProperty("expanded", val)
        except Exception:
            pass

        # сохранить
        sec.toggle_button.toggled.connect(lambda checked, k=key: self._save_ini(k, bool(checked)))

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from smithanatool_qt.widgets.collapsible import CollapsibleSection

from .delegate import FragmentItemDelegate
from .ini_mixin import RightPanelIniMixin
from .list_mixin import RightPanelListMixin
from .ui import build_action_buttons, build_list, build_save_button

from ..settings.ai_settings_widget import AiSettingsWidget


class OcrRightPanel(QWidget, RightPanelIniMixin, RightPanelListMixin):
    aiRequested = Signal()
    saveRequested = Signal(str)
    saveAllRequested = Signal(str)

    # CRUD по текстам
    itemDeletedByUid = Signal(str)  # uid
    itemEditedByUid = Signal(str, str)  # uid, new_text

    handwritingRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 4, 0)
        v.setSpacing(8)

        # --- Настройки  ---
        self._settings_holder = QWidget()
        sh = QVBoxLayout(self._settings_holder)
        sh.setContentsMargins(0, 0, 0, 0)
        sh.setSpacing(0)

        # ВАЖНО: вставляем виджет сразу (он лёгкий)
        self.settings = AiSettingsWidget(self)
        sh.addWidget(self.settings)

        sec_settings = CollapsibleSection("Настройки", self._settings_holder, expanded=True)
        self._bind_section_expanded(sec_settings, "expanded_settings", default=True)
        v.addWidget(sec_settings)

        QTimer.singleShot(0, lambda: QTimer.singleShot(0, self._install_settings_widget_late))

        # --- Остальной UI ---
        build_action_buttons(self, v)
        build_list(self, v)
        build_save_button(self, v)


        # ── List UI ───────────────────────────────────────────────────────
        self.list.setItemDelegate(FragmentItemDelegate(self.list))

        self.list.setUniformItemSizes(False)
        self.list.setWordWrap(True)

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
        self.btn_extract.clicked.connect(self.aiRequested.emit)
        self.btn_handwriting.clicked.connect(self.handwritingRequested.emit)
        self.btn_save.clicked.connect(self._on_save)
        self.btn_save_all.clicked.connect(self._on_save_all)

        self._block_item_changed = False
        self.list.itemChanged.connect(self._on_item_changed)
        try:
            self.list.model().rowsMoved.connect(lambda *args: self._relabel())
        except Exception:
            pass

    def _install_settings_widget_late(self) -> None:
        try:
            self.settings.start_async_init()
        except Exception:
            pass

    # ── Sections persistence helpers ────────────────────────────────────
    def _bind_section_expanded(self, sec, key: str, default: bool = False):
        """Привязка expanded/collapsed секции к INI."""
        val = self._get_ini_bool(key, default)

        # применить без анимации
        sec.toggle_button.blockSignals(True)
        sec.toggle_button.setChecked(val)
        sec.toggle_button.blockSignals(False)
        try:
            sec._set_content_visible(val, animate=False)
            sec._update_header_icon(val)
            sec.setProperty("expanded", val)
        except Exception:
            pass

        sec.toggle_button.toggled.connect(lambda checked, k=key: self._save_ini(k, bool(checked)))

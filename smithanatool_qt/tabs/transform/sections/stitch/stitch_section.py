from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from .actions import StitchSectionActionsMixin
from .helpers import StitchSectionHelpersMixin
from .state import StitchSectionStateMixin
from .ui import StitchSectionUiMixin


class StitchSection(
    QWidget,
    StitchSectionUiMixin,
    StitchSectionStateMixin,
    StitchSectionHelpersMixin,
    StitchSectionActionsMixin,
):
    def __init__(self, gallery=None, parent=None):
        super().__init__(parent)
        self._gallery = gallery

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)
        root.setAlignment(Qt.AlignTop)

        self._build_mode_row(root)
        self._build_multi_group(root)
        self._build_smart_group(root)
        self._build_common_settings_group(root)
        self._build_png_group(root)
        self._build_footer_buttons(root)

        self._apply_initial_ui_state()
        self._connect_signals()
        self._apply_settings_from_ini()

__all__ = ["StitchSection"]

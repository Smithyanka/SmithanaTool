
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt
from smithanatool_qt.widgets.collapsible import CollapsibleSection
from .sections.stitch_section import StitchSection
from .sections.cut_section import CutSection
from .conversions_panel import ConversionsPanel
from .rename_panel import RenamePanel

class SectionsPanel(QWidget):
    def __init__(self, gallery=None, preview=None, parent=None):
        super().__init__(parent)
        self._gallery = gallery
        self._preview = preview

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Scroll area — без горизонтального скролла
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(self._scroll)

        # Контент внутри скролла: тянем по ширине viewport
        self._content = QWidget()
        self._content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        cv = QVBoxLayout(self._content)
        cv.setContentsMargins(8, 8, 8, 8)
        cv.setSpacing(10)
        cv.setAlignment(Qt.AlignTop)

        # ====== СКЛЕЙКА ======
        cv.addWidget(CollapsibleSection("Склейка", StitchSection(gallery), expanded=False))

        # ====== НАРЕЗКА ======
        cv.addWidget(CollapsibleSection("Нарезка", CutSection(preview), expanded=False))

        # ====== КОНВЕРТАЦИЯ ======
        conv = ConversionsPanel(gallery)
        conv.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        cv.addWidget(CollapsibleSection("Конвертация", conv, expanded=False))

        # ====== ПАКЕТНОЕ ПЕРЕИМЕНОВЫВАНИЕ ======
        ren = RenamePanel(gallery)
        ren.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        cv.addWidget(CollapsibleSection("Пакетное переименовывание", ren, expanded=False))

        cv.addStretch(1)
        self._scroll.setWidget(self._content)

        # Фикс ширины контента под viewport (сразу и при ресайзе окна)
        self._content.setMinimumWidth(self._scroll.viewport().width())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._content.setMinimumWidth(self._scroll.viewport().width())

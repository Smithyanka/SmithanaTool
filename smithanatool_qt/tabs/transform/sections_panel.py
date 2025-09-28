from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QFrame, QSizePolicy,
    QPushButton, QHBoxLayout
)
from PySide6.QtCore import Qt
from smithanatool_qt.widgets.collapsible import CollapsibleSection
from .sections.stitch_section import StitchSection
from .sections.cut_section import CutSection
from .sections.preview_section import PreviewSection
from .conversions_panel import ConversionsPanel
from .rename_panel import RenamePanel



class SectionsPanel(QWidget):
    def __init__(self, gallery=None, preview=None, parent=None):
        super().__init__(parent)
        self._gallery = gallery
        self._preview = preview

        # ----- OUTER LAYOUT (главный контейнер) -----
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ----- SCROLL AREA (контент со скроллом) -----
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(self._scroll, 1)

        # ----- CONTENT INSIDE SCROLL -----
        self._content = QWidget()
        self._content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        cv = QVBoxLayout(self._content)
        cv.setContentsMargins(8, 8, 8, 8)
        cv.setSpacing(10)
        cv.setAlignment(Qt.AlignTop)

        # ====== СКЛЕЙКА ======
        self._stitch = StitchSection(gallery)
        cv.addWidget(CollapsibleSection("Склейка", self._stitch, expanded=False))

        # ====== НАРЕЗКА ======
        self._cut = CutSection(preview)
        cv.addWidget(CollapsibleSection("Нарезка", self._cut, expanded=False))

        # ====== КОНВЕРТАЦИЯ ======
        self._conv = ConversionsPanel(gallery)
        self._conv.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        cv.addWidget(CollapsibleSection("Конвертация", self._conv, expanded=False))

        # ====== ПАКЕТНОЕ ПЕРЕИМЕНОВЫВАНИЕ ======
        self._ren = RenamePanel(gallery)
        self._ren.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        cv.addWidget(CollapsibleSection("Пакетное переименовывание", self._ren, expanded=False))

        # ====== ПРЕВЬЮ ======
        self._preview_section = PreviewSection(preview)
        cv.addWidget(CollapsibleSection("Превью", self._preview_section, expanded=False))

        # Растяжка внутри скролла — прижать все секции к верху
        cv.addStretch(1)

        self._scroll.setWidget(self._content)
        self._content.setMinimumWidth(self._scroll.viewport().width())

        # ----- FOOTER (кнопка вне скролла, всегда снизу справа) -----
        footer = QHBoxLayout()
        footer.setContentsMargins(8, 6, 0, 0)
        footer.setSpacing(0)

        reset_btn = QPushButton("Сброс настроек")
        reset_btn.setFixedHeight(28)
        reset_btn.setFixedWidth(100)
        reset_btn.clicked.connect(self._reset_all_sections)

        footer.addStretch(1)      # прижать вправо
        footer.addWidget(reset_btn)

        outer.addLayout(footer)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._content.setMinimumWidth(self._scroll.viewport().width())

    # NEW:
    def _reset_all_sections(self):
        # У каждой секции вызываем их локальный reset + они сами сохранятся в INI
        if hasattr(self, "_stitch") and hasattr(self._stitch, "reset_to_defaults"):
            self._stitch.reset_to_defaults()
        if hasattr(self, "_cut") and hasattr(self._cut, "reset_to_defaults"):
            self._cut.reset_to_defaults()
        if hasattr(self, "_conv") and hasattr(self._conv, "reset_to_defaults"):
            self._conv.reset_to_defaults()
        if hasattr(self, "_ren") and hasattr(self._ren, "reset_to_defaults"):
            self._ren.reset_to_defaults()

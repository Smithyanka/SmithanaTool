from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QFrame, QSizePolicy,
    QPushButton, QHBoxLayout, QStyle, QMessageBox,
)
from PySide6.QtCore import Qt
from smithanatool_qt.widgets.collapsible import CollapsibleSection
from smithanatool_qt.tabs.transform.sections.stitch.stitch_section import StitchSection
from smithanatool_qt.tabs.transform.sections.cut_section import CutSection
from smithanatool_qt.tabs.transform.sections.preview_section import PreviewSection
from smithanatool_qt.tabs.transform.sections.conversions.conversions_panel import ConversionsPanel
from smithanatool_qt.tabs.transform.sections.rename_section import RenamePanel

from smithanatool_qt.tabs.common.bind import ini_load_bool, ini_save_bool

class SectionsPanel(QWidget):
    def __init__(self, gallery=None, preview=None, parent=None):
        super().__init__(parent)
        self._gallery = gallery
        self._preview = preview

        # ----- OUTER LAYOUT (главный контейнер) -----
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        outer_frame = QFrame(self)
        outer_frame.setObjectName("sectionsOuter")
        outer_frame.setFrameShape(QFrame.NoFrame)

        root.addWidget(outer_frame, 1)

        outer = QVBoxLayout(outer_frame)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ----- SCROLL AREA (контент со скроллом) -----
        self._scroll = QScrollArea(self)

        self._scroll.setViewportMargins(0, 0, 1, 0)


        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

        sb = self._scroll.verticalScrollBar()
        w = self._scroll.style().pixelMetric(QStyle.PM_ScrollBarExtent, None, self._scroll)



        outer.addWidget(self._scroll, 1)

        # ----- CONTENT INSIDE SCROLL -----
        self._content = QWidget()
        self._content.setObjectName("sectionsScrollContent")
        self._content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        cv = QVBoxLayout(self._content)
        cv.setAlignment(Qt.AlignTop)

        cv.setContentsMargins(0, 0, 2, 0)
        cv.setSpacing(8)

        # ====== СКЛЕЙКА ======
        self._stitch = StitchSection(gallery)
        sec_stitch = CollapsibleSection("Склейка", self._stitch, expanded=False)
        self._bind_section_expanded(sec_stitch, "expanded_stitch", default=False)
        sec_stitch.setObjectName("section-stitch")
        sec_stitch.setProperty("sectionKind", "stitch")
        cv.addWidget(sec_stitch)

        # ====== НАРЕЗКА ======
        self._cut = CutSection(preview, paths_provider=self._gallery.selected_files)
        sec_cut = CollapsibleSection("Нарезка", self._cut, expanded=False)
        self._bind_section_expanded(sec_cut, "expanded_cut", default=False)
        sec_cut.setObjectName("section-cut")
        sec_cut.setProperty("sectionKind", "cut")
        cv.addWidget(sec_cut)

        # ====== КОНВЕРТАЦИЯ ======
        self._conv = ConversionsPanel(gallery)
        self._conv.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        sec_conv = CollapsibleSection("Конвертация", self._conv, expanded=False)
        self._bind_section_expanded(sec_conv, "expanded_conv", default=False)
        sec_conv.setObjectName("section-conv")
        sec_conv.setProperty("sectionKind", "conv")
        cv.addWidget(sec_conv)

        # ====== ПАКЕТНОЕ ПЕРЕИМЕНОВЫВАНИЕ ======
        self._ren = RenamePanel(gallery)
        self._ren.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        sec_ren = CollapsibleSection("Пакетное переименование", self._ren, expanded=False)
        self._bind_section_expanded(sec_ren, "expanded_ren", default=False)
        sec_ren.setObjectName("section-ren")
        sec_ren.setProperty("sectionKind", "ren")
        cv.addWidget(sec_ren)

        # ====== ВЬЮВЕР ======
        self._preview_section = PreviewSection(preview)

        # Вернуть привязку уровней из секции "Вьювер" к реальному PreviewPanel.
        if self._preview is not None:
            try:
                if hasattr(self._preview_section, "levelsChanged") and hasattr(self._preview, "set_levels_preview"):
                    self._preview_section.levelsChanged.connect(self._preview.set_levels_preview)

                if hasattr(self._preview_section, "resetLevelsRequested") and hasattr(self._preview, "reset_levels_preview"):
                    self._preview_section.resetLevelsRequested.connect(self._preview.reset_levels_preview)

                # Синхронизация стартового состояния UI -> preview
                if hasattr(self._preview_section, "levels"):
                    b, g, w = self._preview_section.levels.values()
                    self._preview.set_levels_preview(b, g, w)
            except Exception:
                pass

        sec_prev = CollapsibleSection("Вьювер", self._preview_section, expanded=False)
        self._bind_section_expanded(sec_prev, "expanded_preview", default=False)
        sec_prev.setObjectName("section-preview")
        sec_prev.setProperty("sectionKind", "preview")
        cv.addWidget(sec_prev)

        # Растяжка внутри скролла — прижать все секции к верху
        cv.addStretch(1)

        self._scroll.setWidget(self._content)
        self._content.setMinimumWidth(self._scroll.viewport().width())

        # ----- FOOTER -----
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 8, 15, 0)
        footer.setSpacing(0)

        reset_btn = QPushButton("Сброс настроек")
        reset_btn.clicked.connect(self._confirm_and_reset)

        footer.addStretch(1)
        footer.addWidget(reset_btn)

        outer.addLayout(footer)

    def _bind_section_expanded(self, sec, key: str, default: bool = False):
        val = ini_load_bool("SectionsPanel", key, default)

        sec.toggle_button.blockSignals(True)
        sec.toggle_button.setChecked(val)
        sec.toggle_button.blockSignals(False)
        try:
            sec._set_content_visible(val, animate=False)
            sec._update_header_icon(val)
            sec.setProperty("expanded", val)
        except Exception:
            pass
        sec.toggle_button.toggled.connect(lambda checked, k=key: ini_save_bool("SectionsPanel", k, bool(checked)))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._content.setMinimumWidth(self._scroll.viewport().width())

    def _confirm_and_reset(self):
        btn = QMessageBox.warning(
            self,
            "Сброс настроек",
            "Сбросить настройки?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if btn == QMessageBox.Yes:
            self._reset_all_sections()
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

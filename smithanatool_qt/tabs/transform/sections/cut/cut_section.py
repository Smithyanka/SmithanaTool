from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QStackedWidget,
    QSizePolicy,
    QRadioButton,
    QButtonGroup,
)

from smithanatool_qt.tabs.common.bind import ini_load_str, ini_save_str

from .cut_regular_section import CutRegularSection
from .smartstitch import SmartStitchSection


class _CurrentSizeStackedWidget(QStackedWidget):
    def _best_width(self, use_minimum: bool = False) -> int:
        width = 0
        for i in range(self.count()):
            w = self.widget(i)
            if w is None:
                continue
            hint = w.minimumSizeHint() if use_minimum else w.sizeHint()
            width = max(width, hint.width())
        if width <= 0:
            hint = super().minimumSizeHint() if use_minimum else super().sizeHint()
            width = hint.width()
        return width

    def sizeHint(self) -> QSize:
        current = self.currentWidget()
        if current is None:
            return super().sizeHint()
        hint = current.sizeHint()
        return QSize(self._best_width(use_minimum=False), hint.height())

    def minimumSizeHint(self) -> QSize:
        current = self.currentWidget()
        if current is None:
            return super().minimumSizeHint()
        hint = current.minimumSizeHint()
        return QSize(self._best_width(use_minimum=True), hint.height())


class CutSection(QWidget):
    def __init__(self, preview=None, parent=None, paths_provider=None):
        super().__init__(parent)

        v = QVBoxLayout(self)
        v.setAlignment(Qt.AlignTop)

        row_mode = QHBoxLayout()
        row_mode.addStretch(1)

        self.rb_regular = QRadioButton("Ручная")
        self.rb_smart = QRadioButton("Пакетная")

        self._mode_group = QButtonGroup(self)
        self._mode_group.addButton(self.rb_regular)
        self._mode_group.addButton(self.rb_smart)

        row_mode.addWidget(self.rb_regular)
        row_mode.addSpacing(24)
        row_mode.addWidget(self.rb_smart)
        row_mode.addStretch(1)
        v.addLayout(row_mode)

        self.stack = _CurrentSizeStackedWidget(self)
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        self.page_regular = CutRegularSection(preview=preview, parent=self, paths_provider=paths_provider)
        self.page_smart = SmartStitchSection(parent=self, paths_provider=paths_provider)
        self.page_regular.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.page_smart.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        self.stack.addWidget(self.page_regular)
        self.stack.addWidget(self.page_smart)
        v.addWidget(self.stack)

        self.rb_regular.toggled.connect(self._on_mode_changed)
        self.rb_smart.toggled.connect(self._on_mode_changed)
        self.stack.currentChanged.connect(lambda _i: self._refresh_geometry())

        mode = ini_load_str("CutSectionHost", "mode", "regular")
        if mode == "smart":
            self.rb_smart.setChecked(True)
        else:
            self.rb_regular.setChecked(True)

        self._on_mode_changed()

    def _page_height(self, page: QWidget | None) -> int:
        if page is None:
            return 0
        page.ensurePolished()
        lay = page.layout()
        if lay is not None:
            lay.activate()
            margins = page.contentsMargins()
            layout_h = lay.sizeHint().height() + margins.top() + margins.bottom()
        else:
            layout_h = 0
        return max(page.minimumSizeHint().height(), page.sizeHint().height(), layout_h)

    def _refresh_geometry(self):
        current = self.stack.currentWidget()
        if current is not None:
            self.stack.setFixedHeight(self._page_height(current))
        self.stack.updateGeometry()
        self.updateGeometry()
        parent = self.parentWidget()
        if parent is not None:
            parent.updateGeometry()

    def refresh_stack_geometry(self):
        self._refresh_geometry()

    def _on_mode_changed(self, _checked: bool = False):
        is_smart = self.rb_smart.isChecked()
        self.stack.setCurrentIndex(1 if is_smart else 0)
        ini_save_str("CutSectionHost", "mode", "smart" if is_smart else "regular")
        self._refresh_geometry()

    def reset_to_defaults(self):
        try:
            self.rb_regular.blockSignals(True)
            self.rb_smart.blockSignals(True)
            self.rb_regular.setChecked(True)
            self.rb_smart.setChecked(False)
        finally:
            self.rb_regular.blockSignals(False)
            self.rb_smart.blockSignals(False)

        self._on_mode_changed()

        if hasattr(self.page_regular, "reset_to_defaults"):
            self.page_regular.reset_to_defaults()
        if hasattr(self.page_smart, "reset_to_defaults"):
            self.page_smart.reset_to_defaults()
        self._refresh_geometry()
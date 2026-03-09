from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from PySide6.QtCore import Qt, Signal, QSignalBlocker
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QToolButton,
    QButtonGroup,
    QStackedWidget,
QSizePolicy,
)

from smithanatool_qt.tabs.transform.sections.panel import SectionsPanel

if TYPE_CHECKING:
    from smithanatool_qt.tabs.ai.ui.right_panel.panel import OcrRightPanel


class WorkshopRightPanel(QWidget):
    """Правая панель для вкладки "Мастерская".

    Сверху — переключатель режимов (Преобразования / Распознавание),
    снизу — QStackedWidget с соответствующими панелями.

    OCR-панель создаётся лениво (по первому входу в режим OCR).
    """

    modeChanged = Signal(str)  # "transform" | "ai"

    def __init__(self, *, gallery: QWidget, preview: QWidget, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._gallery = gallery
        self._preview = preview

        self._ocr_panel: Optional[OcrRightPanel] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 5, 0, 0)
        root.setSpacing(8)

        # ---- Top switch (segmented-like) ----
        top = QFrame(self)
        top.setObjectName("workshopModeBar")
        top_lay = QHBoxLayout(top)
        top_lay.setContentsMargins(4, 4, 4, 4)
        top_lay.setSpacing(0)


        self.btn_transform = QToolButton(top)
        self.btn_transform.setText("Преобразования")
        self.btn_transform.setCheckable(True)
        self.btn_transform.setAutoRaise(False)
        self.btn_transform.setCursor(Qt.PointingHandCursor)
        self.btn_transform.setObjectName("workshopModeBtn")
        self.btn_transform.setProperty("mode", "transform")

        self.btn_ocr = QToolButton(top)
        self.btn_ocr.setText("Распознавание текста")
        self.btn_ocr.setCheckable(True)
        self.btn_ocr.setAutoRaise(False)
        self.btn_ocr.setCursor(Qt.PointingHandCursor)
        self.btn_ocr.setObjectName("workshopModeBtn")

        grp = QButtonGroup(self)
        grp.setExclusive(True)
        grp.addButton(self.btn_transform, 0)
        grp.addButton(self.btn_ocr, 1)
        self._grp = grp

        top_lay.addWidget(self.btn_transform)
        top_lay.addWidget(self.btn_ocr)

        root.addWidget(top, 0)

        # ---- Content stack ----
        self.stack = QStackedWidget(self)
        self.stack.setObjectName("workshopModeStack")

        self.transform_panel = SectionsPanel(self._gallery, self._preview, self)
        self.stack.addWidget(self.transform_panel)

        # placeholder for OCR (lazy)
        self._ocr_placeholder = QWidget(self)
        self.stack.addWidget(self._ocr_placeholder)

        root.addWidget(self.stack, 1)

        # default mode
        self.btn_transform.setChecked(True)
        self.stack.setCurrentIndex(0)

        self.btn_transform.setProperty("pos", "left")
        self.btn_ocr.setProperty("pos", "right")


        for b in (self.btn_transform, self.btn_ocr):
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)  # сегменты занимают всю высоту бара
            b.setFocusPolicy(Qt.NoFocus)


        top_lay.setSpacing(4)

        grp.idToggled.connect(self._on_mode_toggled)

    # ---- INI ----
    def set_mode(self, mode: str, *, emit: bool = True) -> None:
        """Программно выставить режим: 'transform' | 'ocr'."""
        mode = (mode or "transform").strip().lower()
        if mode not in ("transform", "ocr"):
            mode = "transform"

        # чтобы не триггерить _on_mode_toggled() дважды
        with QSignalBlocker(self._grp):
            if mode == "transform":
                self.btn_transform.setChecked(True)
                self.stack.setCurrentIndex(0)
            else:
                self.ensure_ocr_panel()
                self.btn_ocr.setChecked(True)
                self.stack.setCurrentIndex(1)

        if emit:
            self.modeChanged.emit(mode)
    # ---- public API ----
    def current_mode(self) -> str:
        return "transform" if self.stack.currentIndex() == 0 else "ocr"

    def ensure_ocr_panel(self) -> "OcrRightPanel":
        if self._ocr_panel is not None:
            return self._ocr_panel

        # ЛЕНИВЫЙ ИМПОРТ
        from smithanatool_qt.tabs.ai.ui.right_panel.panel import OcrRightPanel

        ocr = OcrRightPanel(self)

        idx = self.stack.indexOf(self._ocr_placeholder)
        if idx >= 0:
            self.stack.removeWidget(self._ocr_placeholder)
            self._ocr_placeholder.deleteLater()
            self.stack.insertWidget(idx, ocr)

        self._ocr_panel = ocr
        return ocr

    @property
    def ocr_panel(self) -> Optional[OcrRightPanel]:
        return self._ocr_panel

    # ---- internals ----
    def _on_mode_toggled(self, idx: int, checked: bool) -> None:
        if not checked:
            return

        if idx == 0:
            self.stack.setCurrentIndex(0)
            self.modeChanged.emit("transform")
            return

        # OCR
        self.ensure_ocr_panel()
        self.stack.setCurrentIndex(1)
        self.modeChanged.emit("ocr")

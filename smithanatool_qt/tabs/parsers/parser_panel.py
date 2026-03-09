from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal, QSignalBlocker

from .common.modes import MODE_MANHWA, MODE_NOVEL, VALID_PARSER_MODES
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QSizePolicy, QStackedWidget, QToolButton, QVBoxLayout, QWidget


class ParsersStackPanel(QWidget):
    modeChanged = Signal(str)  # "manhwa" | "novel"

    def __init__(
        self,
        *,
        manhwa_factory: Callable[[], QWidget],
        novel_factory: Callable[[], QWidget],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)

        self._manhwa_factory = manhwa_factory
        self._novel_factory = novel_factory

        self._manhwa_page: Optional[QWidget] = None
        self._novel_page: Optional[QWidget] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 5, 0, 0)
        root.setSpacing(0)

        top = QFrame(self)
        top.setObjectName("workshopModeBar")
        top_lay = QHBoxLayout(top)
        top_lay.setContentsMargins(4, 4, 4, 4)
        top_lay.setSpacing(4)

        self.btn_manhwa = QToolButton(top)
        self.btn_manhwa.setText("Парсер манхв")
        self.btn_manhwa.setCheckable(True)
        self.btn_manhwa.setAutoRaise(False)
        self.btn_manhwa.setCursor(Qt.PointingHandCursor)
        self.btn_manhwa.setObjectName("workshopModeBtn")
        self.btn_manhwa.setProperty("pos", "left")

        self.btn_novel = QToolButton(top)
        self.btn_novel.setText("Парсер новелл")
        self.btn_novel.setCheckable(True)
        self.btn_novel.setAutoRaise(False)
        self.btn_novel.setCursor(Qt.PointingHandCursor)
        self.btn_novel.setObjectName("workshopModeBtn")
        self.btn_novel.setProperty("pos", "right")

        self._grp = QButtonGroup(self)
        self._grp.setExclusive(True)
        self._grp.addButton(self.btn_manhwa, 0)
        self._grp.addButton(self.btn_novel, 1)

        for btn in (self.btn_manhwa, self.btn_novel):
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setFocusPolicy(Qt.NoFocus)
            top_lay.addWidget(btn)

        root.addWidget(top, 0)

        self.stack = QStackedWidget(self)
        self.stack.setObjectName("workshopModeStack")

        self._manhwa_placeholder = QWidget(self)
        self._novel_placeholder = QWidget(self)
        self.stack.addWidget(self._manhwa_placeholder)
        self.stack.addWidget(self._novel_placeholder)
        root.addWidget(self.stack, 1)

        self.btn_manhwa.setChecked(True)
        self.stack.setCurrentIndex(0)

        self._grp.idToggled.connect(self._on_mode_toggled)

    def set_mode(self, mode: str, *, emit: bool = True) -> None:
        mode = (mode or "manhwa").strip().lower()
        if mode not in VALID_PARSER_MODES:
            mode = MODE_MANHWA

        with QSignalBlocker(self._grp):
            if mode == MODE_MANHWA:
                self.ensure_manhwa_page()
                self.btn_manhwa.setChecked(True)
                self.stack.setCurrentIndex(0)
            else:
                self.ensure_novel_page()
                self.btn_novel.setChecked(True)
                self.stack.setCurrentIndex(1)

        if emit:
            self.modeChanged.emit(mode)

    def current_mode(self) -> str:
        return MODE_MANHWA if self.stack.currentIndex() == 0 else MODE_NOVEL

    def current_page(self) -> Optional[QWidget]:
        return self._manhwa_page if self.current_mode() == MODE_MANHWA else self._novel_page

    def ensure_manhwa_page(self) -> QWidget:
        if self._manhwa_page is not None:
            return self._manhwa_page

        page = self._manhwa_factory()
        idx = self.stack.indexOf(self._manhwa_placeholder)
        if idx >= 0:
            self.stack.removeWidget(self._manhwa_placeholder)
            self._manhwa_placeholder.deleteLater()
            self.stack.insertWidget(idx, page)
        self._manhwa_page = page
        return page

    def ensure_novel_page(self) -> QWidget:
        if self._novel_page is not None:
            return self._novel_page

        page = self._novel_factory()
        idx = self.stack.indexOf(self._novel_placeholder)
        if idx >= 0:
            self.stack.removeWidget(self._novel_placeholder)
            self._novel_placeholder.deleteLater()
            self.stack.insertWidget(idx, page)
        self._novel_page = page
        return page

    def _on_mode_toggled(self, idx: int, checked: bool) -> None:
        if not checked:
            return

        if idx == 0:
            self.ensure_manhwa_page()
            self.stack.setCurrentIndex(0)
            self.modeChanged.emit(MODE_MANHWA)
            return

        self.ensure_novel_page()
        self.stack.setCurrentIndex(1)
        self.modeChanged.emit(MODE_NOVEL)

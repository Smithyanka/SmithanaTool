from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, QPoint, QRect, QEvent
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QProgressBar


class BusyOverlay(QWidget):
    """Полупрозрачный оверлей поверх выбранной области (dim).
    """
    def __init__(self, parent: QWidget, cover_widgets: Optional[List[QWidget]] = None):
        super().__init__(parent)
        self.setObjectName("busyOverlay")
        self.setVisible(False)

        # Чтобы фон из QSS гарантированно рисовался
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(True)

        # Клики/скролл НЕ блокируем (оверлей прозрачен для мыши)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.NoFocus)

        # Какие виджеты должны быть "прикрыты" оверлеем (например Preview + Right)
        self._cover_widgets: List[QWidget] = list(cover_widgets or [])

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._label = QLabel("Распознавание...", self)
        self._label.setObjectName("busyOverlayLabel")
        self._label.setAlignment(Qt.AlignCenter)

        self._bar = QProgressBar(self)
        self._bar.setObjectName("busyOverlayBar")
        self._bar.setRange(0, 0)  # бесконечная анимация
        self._bar.setTextVisible(False)
        self._bar.setFixedWidth(260)

        # Центрируем текст
        lay.addStretch(1)
        lay.addWidget(self._label, 0, Qt.AlignCenter)
        lay.addWidget(self._bar, 0, Qt.AlignCenter)
        lay.addStretch(1)

        # Стили

        # Следим за ресайзом/движением родителя и прикрываемых виджетов
        parent.installEventFilter(self)
        for w in self._cover_widgets:
            try:
                w.installEventFilter(self)
            except Exception:
                pass

        self._update_geometry()

    def set_text(self, text: str):
        self._label.setText(text or "Распознавание...")

    def _update_geometry(self):
        """Подгоняем геометрию оверлея под cover_widgets (или под весь parent)."""
        parent = self.parentWidget()
        if parent is None:
            return

        if not self._cover_widgets:
            self.setGeometry(parent.rect())
            return

        rect: Optional[QRect] = None
        for w in self._cover_widgets:
            if w is None:
                continue
            try:
                tl = w.mapTo(parent, QPoint(0, 0))
                r = QRect(tl, w.size())
            except Exception:
                continue
            rect = r if rect is None else rect.united(r)

        if rect is None:
            rect = parent.rect()

        self.setGeometry(rect)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Resize, QEvent.Move, QEvent.Show, QEvent.LayoutRequest):
            self._update_geometry()
        return super().eventFilter(watched, event)


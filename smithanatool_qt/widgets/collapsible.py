
from PySide6.QtWidgets import QWidget, QVBoxLayout, QToolButton, QSizePolicy, QScrollArea
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve

class CollapsibleSection(QWidget):
    """Простой складывающийся блок (раскрыть/скрыть содержимое).
    Использование:
        section = CollapsibleSection(title="Склейка", content=someWidget)
    """
    def __init__(self, title: str, content: QWidget, parent=None, expanded: bool = False):
        super().__init__(parent)
        self.toggle_button = QToolButton(text=title, checkable=True, checked=expanded)
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.toggle_button.clicked.connect(self._on_toggled)

        # Оборачиваем контент в прокручиваемую область, если нужно
        self.content_area = QWidget()
        lay = QVBoxLayout(self.content_area)
        lay.setContentsMargins(8, 4, 8, 8)
        lay.addWidget(content)

        self.content_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._animation = QPropertyAnimation(self.content_area, b"maximumHeight", self)
        self._animation.setDuration(150)
        self._animation.setEasingCurve(QEasingCurve.InOutQuad)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.toggle_button)
        main_layout.addWidget(self.content_area)

        self._set_content_visible(expanded, animate=False)

    def _on_toggled(self, checked: bool):
        self.toggle_button.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        self._set_content_visible(checked, animate=True)

    def _set_content_visible(self, visible: bool, animate: bool = True):
        # Вычисляем целевую высоту
        self.content_area.setMaximumHeight(16777215)  # сначала раскроем, чтобы померить
        target = self.content_area.sizeHint().height() if visible else 0

        if animate:
            self._animation.stop()
            self._animation.setStartValue(self.content_area.maximumHeight())
            self._animation.setEndValue(target)
            self._animation.start()
        else:
            self.content_area.setMaximumHeight(target)

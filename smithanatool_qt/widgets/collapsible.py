
from PySide6.QtWidgets import QWidget, QVBoxLayout, QToolButton, QSizePolicy, QScrollArea, QStyle
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QSize, Signal, QEvent
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPen, QPalette

class CollapsibleSection(QWidget):
    """Простой складывающийся блок (раскрыть/скрыть содержимое).
    Использование:
        section = CollapsibleSection(title="Склейка", content=someWidget)
    """
    def __init__(self, title: str, content: QWidget, parent=None, expanded: bool = False):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_Hover, True)
        self.setMouseTracking(True)
        self.setProperty("expanded", expanded)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.toggle_button = QToolButton(text=title, checkable=True, checked=expanded)
        self.toggle_button.setObjectName("sectionHeader")
        self.toggle_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setLayoutDirection(Qt.RightToLeft)
        self._update_header_icon(expanded)
        self.toggle_button.clicked.connect(self._on_toggled)

        self.content_area = QWidget()
        self.content_area.setObjectName("sectionBody")
        lay = QVBoxLayout(self.content_area)
        lay.setContentsMargins(8, 4, 8, 8)
        lay.addWidget(content)

        self.content_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.content_area.setMinimumHeight(0)  # важно для свёрнутого состояния
        self.content_area.installEventFilter(self)

        self._animation = QPropertyAnimation(self.content_area, b"maximumHeight", self)
        self._animation.setDuration(150)
        self._animation.setEasingCurve(QEasingCurve.InOutQuad)
        self._animation.finished.connect(self._sync_to_hint)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.toggle_button)
        main_layout.addWidget(self.content_area)
        main_layout.setSpacing(0)

        self._set_content_visible(expanded, animate=False)

    def eventFilter(self, obj, ev):
        # Если контент меняет размер/лейаут и секция раскрыта — подвинем максимум
        if obj is self.content_area and self.toggle_button.isChecked():
            if ev.type() in (QEvent.LayoutRequest, QEvent.Resize):
                self._sync_to_hint()
        return super().eventFilter(obj, ev)

    def _sync_to_hint(self):
        if self.toggle_button.isChecked():
            self.content_area.setMaximumHeight(self.content_area.sizeHint().height())


    def _update_header_icon(self, expanded: bool):
        self.toggle_button.setIcon(self._plusminus_icon(expanded))
        self.toggle_button.setIconSize(QSize(12, 12))

    def _plusminus_icon(self, expanded: bool, size: QSize = QSize(12, 12)) -> QIcon:
        pm = QPixmap(size)
        pm.fill(Qt.transparent)

        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)

        # Берём цвет текста кнопки, чтобы совпадало с темой
        color = self.toggle_button.palette().color(QPalette.ButtonText)
        pen = QPen(color)
        pen.setWidthF(1.6)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)

        w, h = size.width(), size.height()
        m = 2  # внутренний отступ
        cx, cy = w / 2, h / 2

        # Горизонтальная черта — всегда
        p.drawLine(m, cy, w - m, cy)

        # Вертикальная — только когда секция свернута (показываем "+")
        if not expanded:
            p.drawLine(cx, m, cx, h - m)

        p.end()
        return QIcon(pm)

    def _on_toggled(self, checked: bool):
        self._update_header_icon(checked)
        self._set_content_visible(checked, animate=True)

    def _set_content_visible(self, visible: bool, animate: bool = True):
        self.content_area.setMaximumHeight(16777215)
        target = self.content_area.sizeHint().height() if visible else 0
        if animate:
            self._animation.stop()
            self._animation.setStartValue(self.content_area.maximumHeight())
            self._animation.setEndValue(target)
            self._animation.start()
            self.setProperty("expanded", visible)
            self.style().unpolish(self)
            self.style().polish(self)
        else:
            self.content_area.setMaximumHeight(target)

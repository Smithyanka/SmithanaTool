from PySide6.QtWidgets import QWidget, QScrollArea, QLabel, QVBoxLayout, QSizePolicy
from PySide6.QtCore import Qt, QSize, QPoint, Signal, QEvent
from PySide6.QtGui import QPixmap

class ImageView(QWidget):
    """Прокручиваемый предпросмотр с ручным масштабом и перетаскиванием мышью.
    - Ctrl + колесо мыши — масштабирование
    - ЛКМ и перетаскивание — панорамирование (скролл)
    - Fit-to-window (вписать в окно) поддерживается
    """
    zoomChanged = Signal(float)  # текущий масштаб (1.0 = 100%)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._orig = QPixmap()
        self._scale = 1.0
        self._fit = True
        self._panning = False
        self._last_pos = QPoint()

        self._label = QLabel("Предпросмотр")
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self._label.setScaledContents(False)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setAlignment(Qt.AlignCenter)
        self._scroll.setWidget(self._label)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._scroll)

        # перехватываем события на viewport для колеса и перетаскивания
        self._scroll.viewport().installEventFilter(self)

    # ---------- Public API ----------
    def setPixmap(self, pm: QPixmap):
        self._orig = QPixmap(pm) if (pm and not pm.isNull()) else QPixmap()
        self._update_view()

    def setFitToWindow(self, on: bool):
        self._fit = bool(on)
        self._update_view()

    def isFitToWindow(self) -> bool:
        return self._fit

    def zoomTo(self, factor: float):
        factor = max(0.05, min(8.0, float(factor)))
        self._scale = factor
        if not self._fit:
            self._update_view()
        self.zoomChanged.emit(self._scale)

    def zoomIn(self, step: float = 0.1):
        self.zoomTo(self._scale + step)

    def zoomOut(self, step: float = 0.1):
        self.zoomTo(self._scale - step)

    def resetZoom(self):
        self.zoomTo(1.0)

    def hasPixmap(self) -> bool:
        return not self._orig.isNull()

    # ---------- Internals ----------
    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._fit:
            self._update_view()

    def eventFilter(self, obj, event):
        et = event.type()
        if obj is self._scroll.viewport():
            # Мышиные события для панорамирования
            if et == QEvent.MouseButtonPress and event.button() == Qt.LeftButton and self.hasPixmap():
                self._panning = True
                self._last_pos = event.position().toPoint()
                self._scroll.viewport().setCursor(Qt.ClosedHandCursor)
                return True
            elif et == QEvent.MouseMove and self._panning:
                delta = event.position().toPoint() - self._last_pos
                self._last_pos = event.position().toPoint()
                h = self._scroll.horizontalScrollBar()
                v = self._scroll.verticalScrollBar()
                h.setValue(h.value() - delta.x())
                v.setValue(v.value() - delta.y())
                return True
            elif et == QEvent.MouseButtonRelease and self._panning and event.button() == Qt.LeftButton:
                self._panning = False
                self._scroll.viewport().unsetCursor()
                return True

            # Масштаб колесом при Ctrl
            if et == QEvent.Wheel and (event.modifiers() & Qt.ControlModifier) and self.hasPixmap():
                delta = event.angleDelta().y()
                if delta > 0:
                    self.zoomIn()
                elif delta < 0:
                    self.zoomOut()
                return True
        return super().eventFilter(obj, event)

    def _update_view(self):
        if self._orig.isNull():
            self._label.setText("Предпросмотр")
            self._label.setPixmap(QPixmap())
            return

        if self._fit:
            avail = self._scroll.viewport().size() - QSize(2, 2)
            scaled = self._orig.scaled(avail, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._label.setPixmap(scaled)
        else:
            target = self._orig.size() * self._scale
            target = QSize(max(1, int(target.width())), max(1, int(target.height())))
            scaled = self._orig.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._label.setPixmap(scaled)

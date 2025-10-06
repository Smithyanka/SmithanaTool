from PySide6.QtCore import QObject, Qt, QEvent, QPoint
from PySide6.QtWidgets import QApplication, QWidget

class FramelessHelper(QObject):
    """
    Поддержка перетаскивания и изменения размеров безрамочного окна.
    Устанавливается на всё приложение и следит только за указанным окном.
    """
    def __init__(self, window: QWidget, margin: int = 6):
        super().__init__(window)
        self._window = window
        self._margin = margin
        app = QApplication.instance()
        app.installEventFilter(self)

    def _edges_at(self, pos: QPoint) -> Qt.Edges:
        m = self._margin
        r = self._window.rect()
        edges = Qt.Edges()
        if pos.x() <= m: edges |= Qt.LeftEdge
        if pos.x() >= r.width() - m: edges |= Qt.RightEdge
        if pos.y() <= m: edges |= Qt.TopEdge
        if pos.y() >= r.height() - m: edges |= Qt.BottomEdge
        return edges

    def _update_resize_cursor(self, edges: Qt.Edges):
        if not edges or self._window.isMaximized():
            self._window.unsetCursor()
            return
        hor = bool(edges & (Qt.LeftEdge | Qt.RightEdge))
        ver = bool(edges & (Qt.TopEdge | Qt.BottomEdge))
        if hor and ver:
            left = bool(edges & Qt.LeftEdge)
            top = bool(edges & Qt.TopEdge)
            self._window.setCursor(Qt.SizeFDiagCursor if (left and top) or (not left and not top)
                                   else Qt.SizeBDiagCursor)
        elif hor:
            self._window.setCursor(Qt.SizeHorCursor)
        elif ver:
            self._window.setCursor(Qt.SizeVerCursor)

    def eventFilter(self, obj, ev):
        # обрабатываем только виджеты внутри нашего окна
        if isinstance(obj, QWidget) and obj.window() is self._window:
            t = ev.type()
            if t in (QEvent.MouseMove, QEvent.HoverMove):
                if not self._window.isMaximized():
                    pos_global = ev.globalPosition().toPoint()
                    pos_local = self._window.mapFromGlobal(pos_global)
                    self._update_resize_cursor(self._edges_at(pos_local))
            elif t == QEvent.Leave:
                self._window.unsetCursor()
            elif t == QEvent.MouseButtonPress and ev.button() == Qt.LeftButton and not self._window.isMaximized():
                pos_global = ev.globalPosition().toPoint()
                pos_local = self._window.mapFromGlobal(pos_global)
                edges = self._edges_at(pos_local)
                if edges:
                    wh = self._window.windowHandle()
                    if wh and hasattr(wh, "startSystemResize"):
                        wh.startSystemResize(edges)
                        return True
        return super().eventFilter(obj, ev)

def install_frameless_resize(window: QWidget, margin: int = 6) -> FramelessHelper:
    """Подключить поддержку изменения размера по краю для безрамочного окна."""
    return FramelessHelper(window, margin=margin)

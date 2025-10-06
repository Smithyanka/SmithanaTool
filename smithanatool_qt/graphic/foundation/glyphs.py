from PySide6.QtCore import Qt, QPointF, QSize
from PySide6.QtGui import QIcon, QPainter, QPen, QColor, QPainterPath, QPixmap

def glyph_icon(kind: str, size: int = 16, color: QColor = QColor("white")) -> QIcon:
    """
    Рисует минималистичные иконки: min | max | restore | close | gear.
    Все — белые, без заливки, с одинаковой толщиной линий.
    """
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(color, max(1.5, size * 0.10), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)

    s = float(size)
    pad = s * 0.22

    if kind == "min":
        y = s * 0.65
        p.drawLine(QPointF(pad, y), QPointF(s - pad, y))

    elif kind == "max":
        r = pm.rect().adjusted(int(pad), int(pad), int(-pad), int(-pad))
        p.drawRect(r)

    elif kind == "restore":
        r1 = pm.rect().adjusted(int(pad*0.7), int(pad*0.3), int(-pad*1.3), int(-pad*0.9))
        r2 = pm.rect().adjusted(int(pad*0.3), int(pad*0.7), int(-pad*0.9), int(-pad*1.3))
        p.drawRect(r1); p.drawRect(r2)

    elif kind == "close":
        a, b = QPointF(pad, pad), QPointF(s-pad, s-pad)
        c, d = QPointF(pad, s-pad), QPointF(s-pad, pad)
        p.drawLine(a, b); p.drawLine(c, d)

    elif kind == "gear":
        center = QPointF(s/2, s/2)
        r_outer = s*0.38
        r_inner = s*0.18
        for i in range(8):
            angle = i * (360/8)
            p.save()
            p.translate(center)
            p.rotate(angle)
            p.drawLine(QPointF(0, -r_outer), QPointF(0, -r_outer - s*0.10))
            p.restore()
        p.drawEllipse(center, r_outer, r_outer)
        p.drawEllipse(center, r_inner, r_inner)

    p.end()
    return QIcon(pm)

def circular_pixmap(src, size: int = 28) -> QPixmap:
    """src: QIcon | QPixmap | str(path). Возвращает круглый QPixmap size×size."""
    if isinstance(src, QIcon):
        pm = src.pixmap(size, size)
    elif isinstance(src, QPixmap):
        pm = src
    else:
        pm = QPixmap(str(src))
    if pm.isNull():
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)

    pm = pm.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    out = QPixmap(size, size)
    out.fill(Qt.transparent)

    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing, True)
    path = QPainterPath()
    path.addEllipse(0, 0, size, size)
    p.setClipPath(path)
    p.drawPixmap(0, 0, pm)
    p.end()
    return out

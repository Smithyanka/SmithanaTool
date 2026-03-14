from __future__ import annotations

from typing import Callable, List, Optional

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen

from .overlay_geometry import cross_rect_widget


ImgToWidgetMapper = Callable[[QRect], QRect]


def paint_overlay(
    widget,
    painter: QPainter,
    rects_img: List[QRect],
    labels: List[str],
    selected_index: Optional[int],
    drag_start: Optional[QPoint],
    drag_current: Optional[QPoint],
    img_to_w: ImgToWidgetMapper,
    cross_size: int,
) -> None:
    painter.setRenderHint(QPainter.Antialiasing, True)

    _paint_drag_rect(painter, drag_start, drag_current)

    font = QFont()
    font.setPointSize(9)
    painter.setFont(font)

    for i, r_img in enumerate(rects_img):
        _paint_single_rect(
            painter=painter,
            index=i,
            r_img=r_img,
            label=_label_for(labels, i),
            selected=(selected_index is not None and i == selected_index),
            img_to_w=img_to_w,
            cross_size=cross_size,
        )


def _paint_drag_rect(p: QPainter, drag_start: Optional[QPoint], drag_current: Optional[QPoint]) -> None:
    if not (drag_start and drag_current):
        return

    r = QRect(drag_start, drag_current).normalized()
    radius = min(2.0, r.width() / 2.0, r.height() / 2.0)
    pen = QPen(QColor(142, 53, 253), 2, Qt.DashLine)
    p.setPen(pen)
    p.drawRoundedRect(r, radius, radius)


def _paint_single_rect(
    painter: QPainter,
    index: int,
    r_img: QRect,
    label: str,
    selected: bool,
    img_to_w: ImgToWidgetMapper,
    cross_size: int,
) -> None:
    r_w = img_to_w(r_img)
    radius = min(2.0, r_w.width() / 2.0, r_w.height() / 2.0)

    path = QPainterPath()
    path.addRoundedRect(float(r_w.x()), float(r_w.y()), float(r_w.width()), float(r_w.height()), radius, radius)

    label_rect = QRect(r_w.topLeft(), QSize(20, 14))
    badge_radius = radius

    pen, label_color = _selection_style(selected)
    fill_color = QColor(66, 165, 245, 40) if selected else QColor(227, 204, 255, 40)

    painter.fillPath(path, fill_color)

    painter.setPen(Qt.NoPen)
    painter.setBrush(label_color)
    painter.drawRoundedRect(label_rect, badge_radius, badge_radius)

    painter.setPen(QPen(QColor(255, 255, 255)))
    painter.drawText(label_rect, Qt.AlignCenter, label)

    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(r_w, radius, radius)

    _paint_delete_cross(painter, r_img, radius, img_to_w, cross_size)


def _paint_delete_cross(
    painter: QPainter,
    r_img: QRect,
    radius: float,
    img_to_w: ImgToWidgetMapper,
    cross_size: int,
) -> None:
    cross_rect = cross_rect_widget(r_img, img_to_w, cross_size)

    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(255, 82, 82, 200))
    painter.drawRoundedRect(cross_rect, radius, radius)

    painter.setPen(QPen(QColor(255, 255, 255), 2))
    x1 = cross_rect.topLeft() + QPoint(3, 3)
    x2 = cross_rect.bottomRight() - QPoint(3, 3)
    x3 = cross_rect.topRight() + QPoint(-3, 3)
    x4 = cross_rect.bottomLeft() + QPoint(3, -3)
    painter.drawLine(x1, x2)
    painter.drawLine(x3, x4)


def _selection_style(selected: bool):
    if selected:
        return QPen(QColor(35, 135, 213), 2), QColor(35, 135, 213, 200)
    return QPen(QColor(142, 53, 253), 2), QColor(142, 53, 253, 200)


def _label_for(labels: List[str], index: int) -> str:
    if index < len(labels) and labels[index]:
        return labels[index]
    return str(index + 1)

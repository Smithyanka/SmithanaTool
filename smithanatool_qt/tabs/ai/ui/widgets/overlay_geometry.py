from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QPoint, QRect, QSize, Qt


ImgToWidgetMapper = Callable[[QRect], QRect]


MIN_RECT_SIZE = 3


def cross_rect_widget(r_img: QRect, img_to_w: ImgToWidgetMapper, cross_size: int) -> QRect:
    r_w = img_to_w(r_img)
    return QRect(r_w.topLeft() + QPoint(22, 0), QSize(cross_size, cross_size))


def hit_test_resize_zone_widget(
    r_img: QRect,
    pt: QPoint,
    img_to_w: ImgToWidgetMapper,
    resize_margin: int,
) -> Optional[str]:
    """
    Возвращает:
    resize_tl, resize_tr, resize_bl, resize_br,
    resize_l, resize_r, resize_t, resize_b
    или None, если курсор не на рамке.
    """
    r_w = img_to_w(r_img)
    m = resize_margin

    outer = r_w.adjusted(-m, -m, m, m)
    if not outer.contains(pt):
        return None

    inner = r_w.adjusted(m, m, -m, -m)
    if inner.isValid() and inner.contains(pt):
        return None

    left = abs(pt.x() - r_w.left()) <= m
    right = abs(pt.x() - r_w.right()) <= m
    top = abs(pt.y() - r_w.top()) <= m
    bottom = abs(pt.y() - r_w.bottom()) <= m

    if top and left:
        return "resize_tl"
    if top and right:
        return "resize_tr"
    if bottom and left:
        return "resize_bl"
    if bottom and right:
        return "resize_br"
    if left:
        return "resize_l"
    if right:
        return "resize_r"
    if top:
        return "resize_t"
    if bottom:
        return "resize_b"

    return None


def cursor_shape_for_mode(mode: Optional[str]):
    if mode in ("resize_l", "resize_r"):
        return Qt.SizeHorCursor
    if mode in ("resize_t", "resize_b"):
        return Qt.SizeVerCursor
    if mode in ("resize_tl", "resize_br"):
        return Qt.SizeFDiagCursor
    if mode in ("resize_tr", "resize_bl"):
        return Qt.SizeBDiagCursor
    if mode == "move":
        return Qt.SizeAllCursor
    return None


def rect_from_drag(orig_w: QRect, active_start: QPoint, current_pt: QPoint, active_mode: str) -> QRect:
    if active_mode == "move":
        delta = current_pt - active_start
        return orig_w.translated(delta)

    new_rect_w = QRect(orig_w)
    mode = active_mode.split("_", 1)[1]  # tl / r / b / ...

    if "l" in mode:
        new_left = min(current_pt.x(), new_rect_w.right() - MIN_RECT_SIZE)
        new_rect_w.setLeft(new_left)

    if "r" in mode:
        new_right = max(current_pt.x(), new_rect_w.left() + MIN_RECT_SIZE)
        new_rect_w.setRight(new_right)

    if "t" in mode:
        new_top = min(current_pt.y(), new_rect_w.bottom() - MIN_RECT_SIZE)
        new_rect_w.setTop(new_top)

    if "b" in mode:
        new_bottom = max(current_pt.y(), new_rect_w.top() + MIN_RECT_SIZE)
        new_rect_w.setBottom(new_bottom)

    return new_rect_w

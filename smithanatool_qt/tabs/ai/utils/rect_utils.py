from __future__ import annotations

from PySide6.QtCore import QRect


def sort_rects_top_down(rects: list[QRect]) -> list[QRect]:
    """Сортирует QRect: сверху вниз, внутри строки слева направо."""
    if not rects:
        return rects

    hs = sorted(r.height() for r in rects)
    h_med = hs[len(hs) // 2]
    line_tol = int(h_med * 0.6)

    rects_sorted = sorted(rects, key=lambda r: r.y())

    lines: list[list[QRect]] = []
    for r in rects_sorted:
        placed = False
        for line in lines:
            if abs(line[0].y() - r.y()) <= line_tol:
                line.append(r)
                placed = True
                break
        if not placed:
            lines.append([r])

    for line in lines:
        line.sort(key=lambda r: r.x())

    out: list[QRect] = []
    for line in lines:
        out.extend(line)

    return out

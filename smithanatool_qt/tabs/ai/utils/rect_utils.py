from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QRect

RECT_SORT_MANUAL = "manual"
RECT_SORT_WEBTOON = "webtoon"
RECT_SORT_MANGA = "manga"
RECT_SORT_MANHUA_COMIC = "manhua_comic"

# Обратная совместимость со старыми именами/константами.
RECT_SORT_MANHUA_HORIZONTAL = RECT_SORT_MANHUA_COMIC
RECT_SORT_MANHUA_VERTICAL = RECT_SORT_MANHUA_COMIC
RECT_SORT_MANGA_HORIZONTAL = RECT_SORT_MANGA
RECT_SORT_MANGA_VERTICAL = RECT_SORT_MANGA

RECT_SORT_LTR_TTB = RECT_SORT_WEBTOON
RECT_SORT_LTR = RECT_SORT_MANHUA_COMIC
RECT_SORT_RTL = RECT_SORT_MANGA
RECT_SORT_RTL_TTB = RECT_SORT_MANGA

RECT_SORT_MODES = (
    RECT_SORT_MANUAL,
    RECT_SORT_WEBTOON,
    RECT_SORT_MANGA,
    RECT_SORT_MANHUA_COMIC,
)

_OLD_MODE_ALIASES = {
    "manual": RECT_SORT_MANUAL,
    "webtoon": RECT_SORT_WEBTOON,
    "manga": RECT_SORT_MANGA,
    "manhua_comic": RECT_SORT_MANHUA_COMIC,

    # старые режимы
    "ltr_ttb": RECT_SORT_WEBTOON,
    "ltr": RECT_SORT_MANHUA_COMIC,
    "rtl": RECT_SORT_MANGA,
    "rtl_ttb": RECT_SORT_MANGA,
    "manhua_horizontal": RECT_SORT_MANHUA_COMIC,
    "manhua_vertical": RECT_SORT_MANHUA_COMIC,
    "manga_horizontal": RECT_SORT_MANGA,
    "manga_vertical": RECT_SORT_MANGA,
}


def rect_key(rect: QRect) -> tuple[int, int, int, int]:
    return int(rect.x()), int(rect.y()), int(rect.width()), int(rect.height())


def normalize_rect_sort_mode(mode: Optional[str]) -> str:
    mode = (mode or RECT_SORT_WEBTOON).strip().lower()
    return _OLD_MODE_ALIASES.get(mode, RECT_SORT_WEBTOON)


def cycle_rect_sort_mode(mode: Optional[str]) -> str:
    mode = normalize_rect_sort_mode(mode)
    idx = RECT_SORT_MODES.index(mode)
    return RECT_SORT_MODES[(idx + 1) % len(RECT_SORT_MODES)]


def rect_sort_mode_title(mode: Optional[str]) -> str:
    mode = normalize_rect_sort_mode(mode)
    if mode == RECT_SORT_MANUAL:
        return "Ручной"
    if mode == RECT_SORT_MANGA:
        return "Манга"
    if mode == RECT_SORT_MANHUA_COMIC:
        return "Маньхуа/Комикс"
    return "Вебтун"


def sort_rects_top_down(rects: list[QRect]) -> list[QRect]:
    return sort_rects_by_mode(rects, RECT_SORT_WEBTOON)


def sort_rects_by_mode(
    rects: list[QRect],
    mode: Optional[str],
    *,
    manual_order_getter: Optional[Callable[[QRect], int]] = None,
) -> list[QRect]:
    mode = normalize_rect_sort_mode(mode)
    items = [QRect(r) for r in (rects or []) if r is not None and not r.isNull()]
    if not items:
        return []

    if mode == RECT_SORT_MANUAL:
        if manual_order_getter is None:
            return items
        return sorted(
            items,
            key=lambda r: (
                int(manual_order_getter(r)),
                _top(r),
                _left(r),
                int(r.width()),
                int(r.height()),
            ),
        )

    if mode == RECT_SORT_WEBTOON:
        return _sort_by_rows(items, rtl=False)

    if mode == RECT_SORT_MANGA:
        return _sort_by_rows(items, rtl=True)

    if mode == RECT_SORT_MANHUA_COMIC:
        return _sort_by_columns(items)

    return _sort_by_rows(items, rtl=False)


def _sort_by_rows(items: list[QRect], *, rtl: bool) -> list[QRect]:
    rows = _group_into_rows(items)
    rows.sort(key=lambda row: (int(row["center"]), int(row["top"])))

    out: list[QRect] = []
    for row in rows:
        row_items: list[QRect] = row["items"]  # type: ignore[assignment]
        row_items = sorted(
            row_items,
            key=lambda r: (
                -_left(r) if rtl else _left(r),
                _top(r),
                int(r.width()),
                int(r.height()),
            ),
        )
        out.extend(QRect(r) for r in row_items)
    return out


def _sort_by_columns(items: list[QRect]) -> list[QRect]:
    cols = _group_into_columns(items)
    cols.sort(key=lambda col: (int(col["center"]), int(col["left"])))

    out: list[QRect] = []
    for col in cols:
        col_items: list[QRect] = col["items"]  # type: ignore[assignment]
        col_items = sorted(
            col_items,
            key=lambda r: (
                _top(r),
                _left(r),
                int(r.height()),
                int(r.width()),
            ),
        )
        out.extend(QRect(r) for r in col_items)
    return out


def _group_into_rows(items: list[QRect]) -> list[dict]:
    if not items:
        return []

    items_sorted = sorted(
        items,
        key=lambda r: (
            _center_y(r),
            _top(r),
            _left(r),
        ),
    )
    tol = max(8, int(_median(max(1, int(r.height())) for r in items_sorted) * 0.45))

    rows: list[dict] = []
    for r in items_sorted:
        r_top = _top(r)
        r_bottom = _bottom(r)
        r_center = _center_y(r)
        r_h = max(1, int(r.height()))

        best_idx: Optional[int] = None
        best_key: Optional[tuple[int, int, int]] = None

        for idx, row in enumerate(rows):
            row_top = int(row["top"])
            row_bottom = int(row["bottom"])
            row_center = int(row["center"])
            row_avg_h = max(1, int(row["avg_size"]))

            overlap = _overlap_1d(r_top, r_bottom, row_top, row_bottom)
            overlap_ratio = overlap / max(1, min(r_h, row_avg_h))
            center_diff = abs(r_center - row_center)

            if overlap_ratio >= 0.25 or center_diff <= tol:
                key = (center_diff, -overlap, abs(r_top - row_top))
                if best_key is None or key < best_key:
                    best_key = key
                    best_idx = idx

        if best_idx is None:
            rows.append(
                {
                    "items": [QRect(r)],
                    "top": r_top,
                    "bottom": r_bottom,
                    "center_sum": r_center,
                    "size_sum": r_h,
                    "count": 1,
                    "center": r_center,
                    "avg_size": r_h,
                }
            )
            continue

        row = rows[best_idx]
        row["items"].append(QRect(r))
        row["top"] = min(int(row["top"]), r_top)
        row["bottom"] = max(int(row["bottom"]), r_bottom)
        row["center_sum"] = int(row["center_sum"]) + r_center
        row["size_sum"] = int(row["size_sum"]) + r_h
        row["count"] = int(row["count"]) + 1
        row["center"] = int(row["center_sum"]) // int(row["count"])
        row["avg_size"] = int(row["size_sum"]) // int(row["count"])

    return rows


def _group_into_columns(items: list[QRect]) -> list[dict]:
    if not items:
        return []

    items_sorted = sorted(
        items,
        key=lambda r: (
            _center_x(r),
            _left(r),
            _top(r),
        ),
    )
    tol = max(8, int(_median(max(1, int(r.width())) for r in items_sorted) * 0.45))

    cols: list[dict] = []
    for r in items_sorted:
        r_left = _left(r)
        r_right = _right(r)
        r_center = _center_x(r)
        r_w = max(1, int(r.width()))

        best_idx: Optional[int] = None
        best_key: Optional[tuple[int, int, int]] = None

        for idx, col in enumerate(cols):
            col_left = int(col["left"])
            col_right = int(col["right"])
            col_center = int(col["center"])
            col_avg_w = max(1, int(col["avg_size"]))

            overlap = _overlap_1d(r_left, r_right, col_left, col_right)
            overlap_ratio = overlap / max(1, min(r_w, col_avg_w))
            center_diff = abs(r_center - col_center)

            if overlap_ratio >= 0.25 or center_diff <= tol:
                key = (center_diff, -overlap, abs(r_left - col_left))
                if best_key is None or key < best_key:
                    best_key = key
                    best_idx = idx

        if best_idx is None:
            cols.append(
                {
                    "items": [QRect(r)],
                    "left": r_left,
                    "right": r_right,
                    "center_sum": r_center,
                    "size_sum": r_w,
                    "count": 1,
                    "center": r_center,
                    "avg_size": r_w,
                }
            )
            continue

        col = cols[best_idx]
        col["items"].append(QRect(r))
        col["left"] = min(int(col["left"]), r_left)
        col["right"] = max(int(col["right"]), r_right)
        col["center_sum"] = int(col["center_sum"]) + r_center
        col["size_sum"] = int(col["size_sum"]) + r_w
        col["count"] = int(col["count"]) + 1
        col["center"] = int(col["center_sum"]) // int(col["count"])
        col["avg_size"] = int(col["size_sum"]) // int(col["count"])

    return cols


def _median(values) -> int:
    vals = sorted(int(v) for v in values)
    if not vals:
        return 1
    return vals[len(vals) // 2]


def _overlap_1d(a1: int, a2: int, b1: int, b2: int) -> int:
    return max(0, min(a2, b2) - max(a1, b1))


def _left(r: QRect) -> int:
    return int(r.x())


def _top(r: QRect) -> int:
    return int(r.y())


def _right(r: QRect) -> int:
    return int(r.x()) + int(r.width())


def _bottom(r: QRect) -> int:
    return int(r.y()) + int(r.height())


def _center_x(r: QRect) -> int:
    return _left(r) + int(r.width()) // 2


def _center_y(r: QRect) -> int:
    return _top(r) + int(r.height()) // 2
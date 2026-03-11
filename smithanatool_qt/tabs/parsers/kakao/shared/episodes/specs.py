from __future__ import annotations

from typing import Callable, Optional

from smithanatool_qt.tabs.parsers.kakao.shared.episodes.map_content import (
    safe_list_all as _common_safe_list_all,
)


def parse_chapter_spec(spec: str) -> list[int]:
    out, seen = [], set()
    for chunk in (spec or '').replace(',', ' ').split():
        if '-' in chunk:
            a, b = chunk.split('-', 1)
            if a.isdigit() and b.isdigit():
                lo, hi = int(a), int(b)
                if lo <= hi:
                    for x in range(lo, hi + 1):
                        if x not in seen:
                            out.append(x)
                            seen.add(x)
        elif chunk.isdigit():
            x = int(chunk)
            if x not in seen:
                out.append(x)
                seen.add(x)
    return out


def parse_index_spec(spec: str) -> list[int]:
    return parse_chapter_spec(spec)


def _safe_list_all(series_id: int, sort: str, cookie_raw: Optional[str], log: Optional[Callable[[str], None]],
                   stop_flag: Optional[Callable[[], bool]] = None, retries: int = 2) -> list[dict]:
    return _common_safe_list_all(
        series_id=series_id,
        sort=sort,
        cookie_raw=cookie_raw,
        log=log,
        stop_flag=stop_flag,
        retries=retries,
    )

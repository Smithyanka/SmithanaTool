from __future__ import annotations
from typing import Optional, Callable, List
from dataclasses import dataclass

# Пытаемся найти graphql_client рядом (оба варианта относительного импорта)
try:
    from .graphql_client import KakaoGraphQL  # если лежит в той же папке
except Exception:
    try:
        from .graphql_client import KakaoGraphQL  # если лежит на уровень выше
    except Exception:
        KakaoGraphQL = None

_USE_GRAPHQL = KakaoGraphQL is not None

def parse_chapter_spec(spec: str) -> list[int]:
    out, seen = [], set()
    for chunk in (spec or "").replace(",", " ").split():
        if "-" in chunk:
            a, b = chunk.split("-", 1)
            if a.isdigit() and b.isdigit():
                lo, hi = int(a), int(b)
                if lo <= hi:
                    for x in range(lo, hi + 1):
                        if x not in seen:
                            out.append(x); seen.add(x)
        elif chunk.isdigit():
            x = int(chunk)
            if x not in seen:
                out.append(x); seen.add(x)
    return out

def parse_index_spec(spec: str) -> list[int]:
    return parse_chapter_spec(spec)

def _normalize_episode(ep: dict) -> Optional[dict]:
    if not isinstance(ep, dict): return None
    base = ep.get("node", ep)
    single = base.get("single")
    if isinstance(single, dict):
        for k in ("isViewed","showPlayerIcon","scheme","row1","row2","row3"):
            if k in base and k not in single:
                single[k] = base.get(k)
        base = single
    pid = base.get("productId")
    return base if pid else None

def _list_episodes_once(series_id: int, sort: str, cookie_raw: Optional[str], log: Optional[Callable[[str], None]]) -> list[dict]:
    if not _USE_GRAPHQL or KakaoGraphQL is None:
        raise RuntimeError("GraphQL client not available")
    client = KakaoGraphQL(cookie_raw=cookie_raw)
    rows, skipped = [], 0
    for ep in client.list_episodes(series_id=int(series_id), sort=sort, page_size=200):
        ne = _normalize_episode(ep)
        if ne is None:
            skipped += 1
            continue
        rows.append(ne)
    if log: log(f"[DEBUG] GraphQL получил эпизодов: {len(rows)} (sort='{sort}') (пропущено: {skipped})")
    return rows

def _safe_list_all(series_id: int, sort: str, cookie_raw: Optional[str], log: Optional[Callable[[str], None]],
                   stop_flag: Optional[Callable[[], bool]] = None, retries: int = 2) -> list[dict]:
    last_err = None
    for i in range(retries + 1):
        if stop_flag and stop_flag():
            return []
        try:
            return _list_episodes_once(series_id, sort, cookie_raw, log)
        except Exception as e:
            last_err = e
            if log: log(f"[WARN] list_episodes попытка {i+1}/{retries+1} провалилась: {e}")
    if last_err and log: log(f"[WARN] Не удалось получить общий список эпизодов: {last_err}")
    return []

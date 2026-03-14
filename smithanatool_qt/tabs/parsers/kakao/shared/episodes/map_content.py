from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable, Iterable, Optional

from smithanatool_qt.tabs.parsers.kakao.shared.api.kakao_api import KakaoPageApi
from smithanatool_qt.tabs.parsers.kakao.shared.utils.kakao_common import ensure_dir


def _extract_episode_no(title: str) -> Optional[int]:
    m = re.search(r"(\d+)\s*화", str(title or ""))
    return int(m.group(1)) if m else None


def _to_int(value) -> Optional[int]:
    try:
        return int(value)
    except Exception:
        return None


def normalize_episode_row(ep: dict) -> Optional[dict]:
    if not isinstance(ep, dict):
        return None

    base = ep.get("node", ep)
    single = base.get("single")
    if isinstance(single, dict):
        for key in ("isViewed", "showPlayerIcon", "scheme", "row1", "row2", "row3"):
            if key in base and key not in single:
                single[key] = base.get(key)
        base = single

    product_id = base.get("productId")
    if not product_id:
        return None

    title = (base.get("title") or base.get("row1") or "").strip()
    return {
        "cursor": ep.get("cursor") or base.get("cursor"),
        "productId": product_id,
        "title": title,
        "episodeNo": base.get("episodeNo") if isinstance(base.get("episodeNo"), int) else _extract_episode_no(title),
        "isFree": base.get("isFree"),
        "isViewed": bool(base.get("isViewed", False)),
        "scheme": base.get("scheme"),
    }


def _canonicalize_episode_rows(rows: Iterable[dict]) -> list[dict]:
    prepared: list[dict] = []
    seen_product_ids: set[int] = set()

    for idx, raw in enumerate(rows or []):
        if not isinstance(raw, dict):
            continue

        if "node" in raw or "single" in raw:
            row = normalize_episode_row(raw)
        else:
            row = dict(raw)

        if not isinstance(row, dict):
            continue

        pid = _to_int(row.get("productId"))
        if not pid or pid in seen_product_ids:
            continue

        seen_product_ids.add(pid)
        row["productId"] = pid
        row["_orig_idx"] = idx
        prepared.append(row)

    # Сохраняем исходный порядок из list_episodes().
    prepared.sort(key=lambda row: row["_orig_idx"])

    out: list[dict] = []
    for row in prepared:
        row = dict(row)
        row.pop("_orig_idx", None)
        out.append(row)
    return out


def safe_list_all(series_id: int, sort: str, cookie_raw: Optional[str], log: Optional[Callable[[str], None]],
                  stop_flag: Optional[Callable[[], bool]] = None, retries: int = 2) -> list[dict]:
    last_err = None
    for i in range(retries + 1):
        if stop_flag and stop_flag():
            return []
        try:
            client = KakaoPageApi(cookie_raw=cookie_raw, log=log)
            rows = [
                normalized
                for edge in client.list_episodes(series_id=int(series_id), sort=sort)
                for normalized in [normalize_episode_row(edge)]
                if normalized is not None
            ]
            return _canonicalize_episode_rows(rows)
        except Exception as e:
            last_err = e
            if log:
                log(f"[WARN] list_episodes попытка {i + 1}/{retries + 1} провалилась: {e}")
    if last_err and log:
        log(f"[WARN] Не удалось получить общий список эпизодов: {last_err}")
    return []


def episode_map_path(out_dir: str | Path, series_id: int) -> Path:
    series_dir = ensure_dir(Path(out_dir or ".") / str(int(series_id)))
    cache_dir = ensure_dir(series_dir / "cache")
    return cache_dir / "episode_map.json"


def load_episode_map(out_dir: str | Path, series_id: int, log: Optional[Callable[[str], None]] = None) -> list[dict]:
    path = episode_map_path(out_dir, series_id)
    if not path.exists():
        return []

    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        rows = json.loads(path.read_text(encoding="utf-8-sig"))

    if isinstance(rows, list):
        rows = _canonicalize_episode_rows(rows)
        if log:
            log(f"[CACHE] Загружена карта эпизодов из {path}")
        return rows

    if log:
        log(f"[WARN] Некорректный формат кэша карты эпизодов: {path}")
    return []


def save_episode_map(out_dir: str | Path, series_id: int, rows: Iterable[dict],
                     log: Optional[Callable[[str], None]] = None) -> Path:
    path = episode_map_path(out_dir, series_id)
    data = _canonicalize_episode_rows(rows)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if log:
        log(f"[CACHE] Сохранена карта эпизодов: {path}")
    return path


def refresh_episode_map(series_id: int, out_dir: str | Path, cookie_raw: Optional[str],
                        log: Optional[Callable[[str], None]] = None,
                        stop_flag: Optional[Callable[[], bool]] = None,
                        sort: str = "asc",
                        retries: int = 2,
                        fallback_to_cache: bool = True) -> list[dict]:
    rows = safe_list_all(
        series_id=int(series_id),
        sort=sort,
        cookie_raw=cookie_raw,
        log=log,
        stop_flag=stop_flag,
        retries=retries,
    )
    if rows:
        save_episode_map(out_dir, series_id, rows, log=log)
        return rows

    if fallback_to_cache:
        cached = load_episode_map(out_dir, series_id, log=log)
        if cached:
            if log:
                log("[WARN] Использую сохранённый episode_map.json, потому что обновить список не удалось.")
            return cached

    return []


def picker_rows_from_episode_map(rows: Iterable[dict]) -> list[dict]:
    ordered = [dict(row) for row in (rows or []) if isinstance(row, dict)]
    for idx, row in enumerate(ordered, 1):
        row["cursor"] = idx
        if not row.get("title"):
            pid = row.get("productId") or "?"
            row["title"] = f"Эпизод {pid}"
    return ordered
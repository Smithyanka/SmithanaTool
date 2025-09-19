# -*- coding: utf-8 -*-
"""Сбор карты глав/томов (манхва-стиль раскрытия вверх/вниз + сбор)."""

from __future__ import annotations

from typing import List, Optional

from .dom_novel import collect_chapter_map_both, reveal_all_chapters
from .actions import _scroll_one_step


def _prepare_maps_incremental(
    page,
    title_id: str,
    on_log,
    want_chs: Optional[list[int]] = None,
    want_vols: Optional[list[int]] = None,
    prefer: Optional[str] = None,
) -> List[dict]:
    """
    На странице тайтла:
      - по возможности раскрываем в нужную сторону;
      - если целевая глава уже видна — возвращаем текущую выборку без «допрогрузки»;
      - иначе раскрываем (с приоритетом направления), затем собираем карту.
    Возвращает список словарей:
      {id:str, href:str, num:int|None, vol:int|None, label:str}
    """
    try:
        if want_chs or want_vols:
            visible = collect_chapter_map_both(page, title_id) or []
            # Быстрый матч целевых глав
            t_nums = set(want_chs or [])
            t_vols = set(want_vols or [])
            def _match(rec: dict) -> bool:
                ok = True
                if t_nums:
                    ok = ok and isinstance(rec.get("num"), int) and rec.get("num") in t_nums
                if t_vols:
                    ok = ok and isinstance(rec.get("vol"), int) and rec.get("vol") in t_vols
                return ok
            if any(_match(r) for r in visible):
                try: on_log("[OK] Нашёл целевую главу в зоне видимости — доп.раскрытие не требуется.")
                except Exception: pass
                return visible
    except Exception:
        pass

    # Пытаемся корректно раскрыть список (с учётом предпочитаемого направления)
    try:
        reveal_all_chapters(page, title_id, on_log=on_log, max_rounds=80, pause=0.6, prefer=prefer, want_chs=want_chs, want_vols=want_vols, stop_on_match=True)
    except Exception:
        pass

    merged = collect_chapter_map_both(page, title_id) or []
    if merged:
        return merged

    # Fallback: плавная прокрутка вниз, собираем всё, что найдём
    try:
        seen = set()
        merged = []
        prev_h = 0
        stable_loops = 0
        for _ in range(200):
            cur = collect_chapter_map_both(page, title_id) or []
            for r in cur:
                rid = r.get("id") or r.get("href") or r.get("label")
                if not rid or rid in seen:
                    continue
                seen.add(rid)
                merged.append(r)
            cur_h = _scroll_one_step(page, pause_ms=600)
            if cur_h == prev_h:
                stable_loops += 1
            else:
                stable_loops = 0
            prev_h = cur_h
            if stable_loops >= 3:
                break
        return merged
    except Exception:
        return merged

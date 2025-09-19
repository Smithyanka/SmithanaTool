# -*- coding: utf-8 -*-
"""Основной раннер новелл Kakao Page (text/EPUB) — вынесен из core.py."""

from __future__ import annotations
from typing import Callable, Iterable, List, Optional, Tuple, Dict
from pathlib import Path
import os
from playwright.sync_api import sync_playwright
from smithanatool_qt.parsers.kakao.constants import UA
from smithanatool_qt.parsers.kakao.io import ensure_dir
from smithanatool_qt.parsers.kakao.imagery import sanitize_ext
from .dom_novel import collect_chapter_map_both, extract_main_content, get_best_text_frame
from .spec import parse_num_spec
from .listing import _prepare_maps_incremental
from .actions import (
    _force_eager_assets, _unlock_scroll_in, _scroll_one_step, _scroll_to_top,
    _is_text_viewer, _scroll_one_step_in, _click_top_icon, _get_progress_percent,
    _jump_progress_bar, _scroll_to_top_in, _collect_image_urls_in, _click_next_chunk,
    _activate_viewer,
)
from .io_novel import _save_images_sequential

def run_novel_parser(
    title_id: str,
    chapter_spec: Optional[str] = None,
    chapters: Optional[Iterable[str]] = None,
    out_dir: str = "",
    on_log: Optional[Callable[[str], None]] = None,
    on_need_login: Optional[Callable[[], None]] = None,
    stop_flag: Optional[Callable[[], bool]] = None,
    min_width: int = 720,
    auto_concat: Optional[dict] = None,   # не используется для новелл
    on_confirm_purchase: Optional[Callable[[int, Optional[int]], bool]] = None,
    on_confirm_use_rental: Optional[Callable[[int, int, Optional[int], str], bool]] = None,
    volume_spec: Optional[str] = None,    # фильтр по томам (권)
) -> None:
    """
    Основной раннер новелл Kakao.
    """
    from smithanatool_qt.parsers.kakao.purchase import handle_ticket_modal, handle_buy_page

    log = (on_log or (lambda s: None))
    should_stop = (stop_flag or (lambda: False))

    out_dir = out_dir or os.getcwd()
    ensure_dir(out_dir)
    state_path = Path(os.path.join(out_dir, "kakao_auth.json"))
    title_root = Path(os.path.join(out_dir, f"kakao_novel_{title_id}"))
    ensure_dir(title_root.as_posix())

    def _log(msg: str):
        try:
            log(msg)
        except Exception:
            pass

    if not str(title_id or "").strip().isdigit():
        _log('[ERROR] Пустой или некорректный title_id — остановка. Проверь поле "ID тайтла".')
        return

    try:
        with sync_playwright() as p:
            # Chromium/Edge
            try:
                browser = p.chromium.launch(
                    headless=False, channel="msedge",
                    args=[
                        "--disable-http2", "--no-sandbox", "--disable-setuid-sandbox",
                        "--disable-features=NetworkServiceInProcess",
                        "--disable-blink-features=AutomationControlled"
                    ]
                )
            except Exception:
                browser = p.chromium.launch(
                    headless=False,
                    args=[
                        "--disable-http2", "--no-sandbox", "--disable-setuid-sandbox",
                        "--disable-features=NetworkServiceInProcess",
                        "--disable-blink-features=AutomationControlled"
                    ]
                )

            # Сессия/логин — как у манхвы
            if state_path.exists():
                _log("[OK] Найдена сохранённая сессия. Повторный вход не требуется.")
                context = browser.new_context(
                    user_agent=UA, java_script_enabled=True, bypass_csp=True,
                    viewport={"width": 1600, "height": 2600}, ignore_https_errors=True,
                    locale="ko-KR", timezone_id="Asia/Seoul",
                    storage_state=str(state_path),
                )
                page = context.new_page()
                # --- network slimming: block fonts/media and common trackers for faster flips
                def _should_block(req):
                    rt = (req.resource_type or "").lower()
                    url = (req.url or "").lower()
                    if rt in ("font", "media"):
                        return True
                    bad = ("doubleclick", "googletagmanager", "googletagservices", "analytics", "criteo", "adsystem")
                    return any(b in url for b in bad)
                try:
                    context.route("**/*", lambda route: route.abort() if _should_block(route.request) else route.continue_())
                except Exception:
                    pass

                content_url = f"https://page.kakao.com/content/{title_id}"
                if not chapters:
                    _log(f"[OPEN] Тайтл → {content_url}")
                    page.goto(content_url, wait_until="domcontentloaded", timeout=90000)
                    page.wait_for_load_state("networkidle", timeout=60000)

                # ---------- формирование списка для скачивания ----------
                to_fetch: List[Tuple[str, Optional[int], Optional[int], str]] = []

                # Ветка «по viewerId» — не строим карту, переходим сразу к циклу
                if chapters:
                    chapter_ids = [str(x) for x in chapters if str(x).isdigit()]
                    _log(f"[INFO] Режим по ID: сразу открываю viewer для: {chapter_ids}")
                    to_fetch = [(vid, None, None, vid) for vid in chapter_ids]
                else:
                    # Режим по номерам/томам: авто-определение направления и сбор карты
                    vols = parse_num_spec(volume_spec or "")
                    chs  = parse_num_spec(chapter_spec or "")

                    # Автовыбор направления (вверх/вниз) по видимому диапазону
                    prefer: str | None = None
                    try:
                        _vis = collect_chapter_map_both(page, title_id) or []
                        _nums = [r.get('num') for r in _vis if isinstance(r.get('num'), int)]
                        if _nums and chs:
                            _min_v, _max_v = min(_nums), max(_nums)
                            _min_t, _max_t = min(chs), max(chs)
                            if _max_t < _min_v:
                                prefer = 'down'  # целевая глава «меньше» — раскрываем вниз
                            elif _min_t > _max_v:
                                prefer = 'up'    # целевая «больше» — раскрываем вверх
                            else:
                                # внутри диапазона — выберем ближайшее направление
                                prefer = 'down' if (_min_t <= (_min_v + _max_v)//2) else 'up'
                        _log(f"[AUTO] Предпочтительное направление раскрытия: {prefer or 'auto'}")
                    except Exception:
                        prefer = None

                    # Инкрементальная карта с приоритетом выбранного направления;
                    # если нужная глава уже в зоне видимости — функция вернёт видимый срез
                    cmap = _prepare_maps_incremental(page, title_id, _log, want_chs=chs, want_vols=vols, prefer=prefer)
                    if not cmap:
                        _log("[WARN] Не удалось обнаружить ни одной главы на странице контента.")
                        try:
                            context.close(); browser.close()
                        except Exception:
                            pass
                        return

                    # Построим вспомогательные индексы
                    id_to_meta: Dict[str, Dict[str, object]] = {}
                    num_to_id: Dict[int, str] = {}
                    vol_to_ids: Dict[int, List[str]] = {}
                    vol_num_to_id: Dict[Tuple[int,int], str] = {}

                    for r in cmap:
                        vid = str(r.get("id") or "") or str(r.get("href") or "").rpartition("/")[-1]
                        if not vid:
                            continue
                        num = r.get("num")
                        vol = r.get("vol")
                        lbl = str(r.get("label") or "")
                        id_to_meta[vid] = {"num": num, "vol": vol, "label": lbl}
                        if isinstance(num, int) and num not in num_to_id:
                            num_to_id[num] = vid
                        if isinstance(vol, int):
                            vol_to_ids.setdefault(vol, []).append(vid)
                            if isinstance(num, int):
                                vol_num_to_id.setdefault((vol, num), vid)

                    # Сформируем to_fetch согласно фильтрам
                    if vols and chs:
                        for v in vols:
                            for c in chs:
                                vid = vol_num_to_id.get((v, c))
                                if not vid:
                                    _log(f"[SKIP] Не нашёл главу: том {v} (권), глава {c} (화).")
                                    continue
                                meta = id_to_meta.get(vid, {})
                                to_fetch.append((vid, c, v, meta.get("label") or f"{v}권 {c}화"))
                    elif vols and not chs:
                        for v in vols:
                            ids = vol_to_ids.get(v, [])
                            if not ids:
                                _log(f"[SKIP] Не найден том {v} (권).")
                                continue
                            for vid in ids:
                                meta = id_to_meta.get(vid, {})
                                to_fetch.append((vid, meta.get("num"), v, meta.get("label") or f"{v}권"))
                    elif chs and not vols:
                        for c in chs:
                            vid = num_to_id.get(c)
                            if not vid:
                                _log(f"[SKIP] Не найден номер главы {c} (화).")
                                continue
                            meta = id_to_meta.get(vid, {})
                            to_fetch.append((vid, c, meta.get("vol"), meta.get("label") or f"{c}화"))
                    else:
                        # если фильтров нет — берём всё по порядку
                        for r in cmap:
                            vid = str(r.get("id") or "") or str(r.get("href") or "").rpartition("/")[-1]
                            if not vid:
                                continue
                            to_fetch.append((vid, r.get("num"), r.get("vol"), str(r.get("label") or vid)))
                PRICE = 100  # целевая цена (как в манхва-UI)

            # ---------- цикл по главам ----------
            for idx, (viewer_id, num, vol, label) in enumerate(to_fetch, start=1):
                if should_stop():
                    break

                url = f"https://page.kakao.com/content/{title_id}/viewer/{viewer_id}"
                _log(f"[OPEN] {label}")

                # открываем viewer
                page.goto(url, wait_until="domcontentloaded", timeout=90000)
                page.wait_for_load_state("networkidle", timeout=60000)

                # обработка тикетов/покупки
                try:
                    res = handle_ticket_modal(
                        page, context, title_id, url, PRICE, _log,
                        chapter_label=label,
                        confirm_use_rental_cb=(on_confirm_use_rental or (lambda r, o, b, cl: True)),
                        confirm_purchase_cb=(on_confirm_purchase or (lambda price, bal: True)),
                    )
                except Exception:
                    res = None

                if res == "need_buy" or "/buy/ticket" in (page.url or ""):
                    ok = handle_buy_page(
                        page, context, title_id, url, PRICE, _log,
                        confirm_purchase_cb=(on_confirm_purchase or (lambda price, bal: True))
                    )
                    if ok != "purchased":
                        if ok == "skipped":
                            _log("[SKIP] Покупка тикета отменена пользователем.")
                        else:
                            _log("[SKIP] Покупка не выполнена.")
                        continue
                    try:
                        handle_ticket_modal(
                            page, context, title_id, url, PRICE, _log,
                            chapter_label=label,
                            confirm_use_rental_cb=(on_confirm_use_rental or (lambda r, o, b, cl: True)),
                            confirm_purchase_cb=(on_confirm_purchase or (lambda price, bal: True)),
                        )
                    except Exception:
                        pass

                # Гарантированно в начало страницы

                # определить текстовый фрейм (если это EPUB/text viewer)
                text_frame = get_best_text_frame(page) if _is_text_viewer(page) else None

                # принудительно подгружаем ассеты (страница + iframe)
                try:
                    _force_eager_assets(page)
                    if text_frame: _force_eager_assets(text_frame)
                except Exception:
                    pass

                try:
                    _activate_viewer(page, text_frame)
                except Exception:
                    pass

                # Attempt the "scroll to top" icon (safety)
                try:
                    _click_top_icon(page)
                except Exception:
                    pass

                # сначала пробуем прыгнуть по прогресс-бару в самый старт
                try:
                    _jump_progress_bar(page, text_frame, 0.0)  # 0% — край слева
                except Exception:
                    pass

                # перейти в начало правильного контекста
                _scroll_to_top_in(text_frame or page)

                # Папка главы: одна на текст и картинки
                folder_name = (
                    f"{(vol if isinstance(vol, int) else 0):03d}_{(num if isinstance(num, int) else 0):04d}"
                    if (vol is not None or num is not None) else str(viewer_id)
                )
                ch_dir = title_root / folder_name
                os.makedirs(ch_dir, exist_ok=True)

                # Инкрементальная загрузка: «сохранить → перейти “다음” → сохранить …»
                collected_html: list[str] = []
                collected_txt: list[str] = []
                saved_urls: set[str] = set()
                stuck_same_progress = 0  # сколько раз подряд прогресс не растёт
                last_progress = -1.0  # последний известный процент

                step_idx = 0
                max_steps = 1000  # предохранитель

                while step_idx < max_steps and not should_stop():
                    step_idx += 1

                    # перед снимком — заставим ленивые ассеты подгрузиться
                    try:
                        _force_eager_assets(page)
                        if text_frame: _force_eager_assets(text_frame)
                    except Exception:
                        pass

                    # первый шаг — если текст всё ещё пустой/микроскопический, пнёем вьюер
                    if step_idx == 1:
                        try:
                            # быстро проверим "живость" текстового контейнера
                            probe = extract_main_content(text_frame or page) or {}
                            probe_len = len((probe.get("text") or "").strip())
                            if probe_len < 50:
                                _activate_viewer(page, text_frame)
                        except Exception:
                            pass
                    # 1) Снимок текста/HTML из правильного контекста
                    res = extract_main_content(text_frame or page) or {}
                    html = (res.get("html") or "").strip()
                    txt = (res.get("text") or "").strip()

                    if html and (len(html) > 50) and (html not in collected_html):
                        collected_html.append(html)
                    if txt and (len(txt) > 20) and (txt not in collected_txt):
                        collected_txt.append(txt)

                    # пересохраняем сводные файлы
                    try:
                        if collected_html:
                            (ch_dir / "chapter.html").write_text(
                                "\n<!-- chunk split -->\n".join(collected_html), encoding="utf-8"
                            )
                        if collected_txt:
                            (ch_dir / "chapter.txt").write_text(
                                ("\n\n".join(collected_txt)).strip(), encoding="utf-8"
                            )
                    except Exception as e:
                        _log(f"[WARN] Не удалось сохранить HTML/TXT на шаге {step_idx}: {e}")

                    # 2) Картинки — собираем и со страницы, и из iframe (если есть)
                    try:
                        urls_page = set(_collect_image_urls_in(page, min_width) or [])
                        urls_frame = set(_collect_image_urls_in(text_frame, min_width) or []) if text_frame else set()
                        urls_all = list((urls_page | urls_frame) - saved_urls)
                    except Exception:
                        urls_all = []

                    if urls_all:
                        saved, failed = _save_images_sequential(
                            context, urls_all, ch_dir, ref_url=url, pick_ext=sanitize_ext
                        )
                        for u in urls_all:
                            saved_urls.add(u)
                        _log(
                            f"[STEP {step_idx}] Сохранены изображения: +{saved} (ошибок: {failed}), всего: {len(saved_urls)}")

                    # 3) Переход к следующему куску внутри главы (с учётом прогресс-бара)
                    try:
                        _activate_viewer(page, text_frame)  # держим фокус на ридере каждый шаг
                    except Exception:
                        pass

                    prev_pct = _get_progress_percent(page, text_frame)

                    moved = False
                    try:
                        moved = _click_next_chunk(page)  # клики «다음»/SVG
                    except Exception:
                        moved = False

                    # пауза на подгрузку следующего участка
                    try:
                        page.wait_for_timeout(600)
                    except Exception:
                        pass

                    cur_pct = _get_progress_percent(page, text_frame)

                    # если не сдвинулись или прогресс не вырос — попробуем клавиатуру
                    if (not moved) or (cur_pct >= 0 and prev_pct >= 0 and cur_pct <= prev_pct + 0.01):
                        try:
                            _activate_viewer(page, text_frame)
                            page.keyboard.press("ArrowRight")
                            page.wait_for_timeout(250)
                        except Exception:
                            pass
                        cur_pct2 = _get_progress_percent(page, text_frame)

                        # если ПО-ПРЕЖНЕМУ стоим — микропрыжок по прогресс-бару +2% (но не дальше 99.5%)
                        if cur_pct2 >= 0 and max(prev_pct, cur_pct) >= 0 and cur_pct2 <= max(prev_pct, cur_pct) + 0.01:
                            try:
                                JUMP_STEP = 0.05 if stuck_same_progress >= 1 else 0.03
                                target_pos = min(0.995, max(0.0, (max(prev_pct, cur_pct) / 100.0) + JUMP_STEP))
                                _jump_progress_bar(page, text_frame, target_pos)
                                cur_pct2 = _wait_progress_increase(page, text_frame, prev_pct, timeout_ms=300)
                            except Exception:
                                pass
                            cur_pct = _get_progress_percent(page, text_frame)
                        else:
                            cur_pct = cur_pct2

                    # условия выхода — ТОЛЬКО когда реально дошли до конца
                    if cur_pct >= 99.0:
                        break

                    # антизалипание: если прогресс не растёт — считаем шаг безрезультатным
                    if cur_pct >= 0:
                        if last_progress >= 0 and cur_pct <= last_progress + 0.01:
                            stuck_same_progress += 1
                        else:
                            stuck_same_progress = 0
                        if cur_pct > last_progress:
                            last_progress = cur_pct
                    else:
                        # когда прогрессбар не находится, не считаем это концом: просто аккуратно двигаемся дальше
                        stuck_same_progress += 1

                    # если 6 раз подряд ничего не изменилось — сделаем финальный прыжок и выйдем
                    if stuck_same_progress >= 3:
                        try:
                            _jump_progress_bar(page, text_frame, min(0.995, max(0.0, (cur_pct/100.0) + 0.10)))
                            cur_pct = _wait_progress_increase(page, text_frame, cur_pct, timeout_ms=250)
                        except Exception:
                            pass
                        
                        if stuck_same_progress >= 6:
                            try:
                                _jump_progress_bar(page, text_frame, 0.995)
                                cur_pct = _wait_progress_increase(page, text_frame, cur_pct, timeout_ms=280)
                            except Exception:
                                pass
                        break

                    # иначе продолжаем цикл без принудительного break

                _log(f"Завершено.")

            # закрытие
            try:
                context.close(); browser.close()
            except Exception:
                pass

        if not should_stop():
            _log("Завершено.")
    except Exception as e:
        _log(f"[ERROR] {e}")

def ensure_dir(p: str):
    import os
    os.makedirs(p, exist_ok=True)

# -*- coding: utf-8 -*-
"""
kakao_parser/core.py

Два режима:
  1) chapter_spec: номера глав ("1,2,5" или "1-5") → viewerId по странице контента.
  2) chapters: список viewerId напрямую.

Структура сохранения скачанных глав:
  <out_dir>/kakao_state.json
  <out_dir>/kakao_<title_id>/<номер главы>/001.png ...

Автосклейка (опционально):
  • после выгрузки каждой главы, склеивает её изображения батчами и сохраняет в:
      <auto_out_dir>/kakao_<title_id>/<номер главы>.png  (или -01.png, -02.png, если батчей > 1)
  • удаляет метаданные, может увеличить по ширине (target_width>0).
"""

import os
import re
from pathlib import Path
from typing import Callable, Iterable, Optional, List, Tuple

from PIL import Image, ImageOps
from playwright.sync_api import sync_playwright

from .constants import UA
from .imagery import sanitize_ext
from .dom import smart_scroll, collect_urls_with_width, collect_chapter_map, reveal_all_chapters, read_total_chapters, collect_viewer_links_dom_order

from .io import ensure_dir, chapter_has_files, save_images_with_context

from .purchase import looks_locked, handle_ticket_modal, handle_buy_page, handle_rental_expired_modal
from typing import Optional, Iterable, Callable


# --------- вспомогательные парсеры / построители карт ---------
def parse_chapter_spec(spec: str) -> List[int]:
    """'1,2,5-7 10' → [1,2,5,6,7,10] (без дублей, порядок сохраняем)."""
    nums: List[int] = []
    spec = (spec or "").strip()
    if not spec:
        return nums
    tokens = re.split(r"[,\s]+", spec)
    for t in tokens:
        if not t:
            continue
        m = re.match(r"^(\d+)-(\d+)$", t)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            step = 1 if a <= b else -1
            nums.extend(range(a, b + step, step))
        elif t.isdigit():
            nums.append(int(t))
    # de-dupe, keep order
    seen = set()
    out: List[int] = []
    for n in nums:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _build_maps_from_content(page, title_id: str) -> Tuple[dict, dict]:
    """
    Возвращает две карты по странице https://page.kakao.com/content/<title_id>:
      num_to_id: номер_главы(int) → viewerId(str)
      id_to_num: viewerId(str) → номер_главы(int)
    """
    cmap = collect_chapter_map(page, title_id)  # [{num:int, id:str, href:str}, ...]
    num_to_id, id_to_num = {}, {}
    for r in (cmap or []):
        try:
            n = int(r.get("num"))
            vid = str(r.get("id"))
            if n not in num_to_id:
                num_to_id[n] = vid
            if vid not in id_to_num:
                id_to_num[vid] = n
        except Exception:
            continue
    return num_to_id, id_to_num


# --------- автосклейка ---------
def _list_images_sorted(ch_dir: Path) -> List[Path]:
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    files = [p for p in sorted(ch_dir.iterdir()) if p.is_file() and p.suffix.lower() in exts]
    return files


def _concat_vertical(paths: List[Path]) -> Image.Image:
    imgs = []
    for p in paths:
        im = Image.open(p)
        im = ImageOps.exif_transpose(im)
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA")
        imgs.append(im)

    base_w = max(im.width for im in imgs)
    resized = []
    h_total = 0
    for im in imgs:
        if im.width != base_w:
            nh = int(im.height * (base_w / im.width))
            im = im.resize((base_w, nh), Image.LANCZOS)
        resized.append(im)
        h_total += im.height

    canvas = Image.new("RGBA", (base_w, h_total), (0, 0, 0, 0))
    y = 0
    for im in resized:
        canvas.paste(im, (0, y))
        y += im.height
    return canvas


def _strip_png(im: Image.Image) -> Image.Image:
    # Сохранение без pnginfo — метаданные отбрасываются (делаем это на этапе save)
    return im


def _auto_concat_chapter(ch_dir: Path, title_id: str, chapter_name: str, cfg: dict, log: Callable[[str], None]):
    """
    Склеивает изображения главы батчами и сохраняет:
      - либо в cfg['out_dir']/kakao_<title_id>/ (по умолчанию),
      - либо в саму папку главы (если same_dir=True).

    В конце, если delete_sources=True, удаляет ВСЕ исходники главы разом.
    """
    import os
    from PIL import Image

    per = int(cfg.get("per", 0) or 0)
    if per < 1:
        log("[WARN] per<1 — пропуск автосклейки.")
        return

    # Куда сохраняем результат
    same_dir = bool(cfg.get("same_dir", False))
    out_base = (Path(ch_dir) if same_dir else Path(cfg["out_dir"]) / f"kakao_{title_id}")
    ensure_dir(out_base.as_posix())

    # Список исходников
    files = _list_images_sorted(ch_dir)
    if not files:
        log("[WARN] Автосклейка: в главе нет файлов.")
        return

    # Батчим по per
    groups = [files[i:i + per] for i in range(0, len(files), per)]
    pad = max(2, len(str(len(groups))))


    target_w = int(cfg.get("target_width", 0) or 0)  # 0 — не менять
    strip = bool(cfg.get("strip_metadata", True))
    optimize = bool(cfg.get("optimize_png", True))
    level = int(cfg.get("compress_level", 6) or 6)

    for gi, group in enumerate(groups, start=1):
        # Склейка по вертикали
        merged = _concat_vertical(group)

        # Изменение ширины при необходимости
        if target_w and target_w > 0 and merged.width != target_w:
            nh = int(merged.height * (target_w / merged.width))
            merged = merged.resize((target_w, nh), Image.LANCZOS)

        # Имя файла: <глава>.png или <глава>-01.png, -02.png ...
        suffix = str(gi).zfill(pad)
        fname = f"{suffix}.png" if len(groups) > 1 else f"{chapter_name}.png"
        out_path = out_base / fname

        # Сохранение PNG
        out_img = _strip_png(merged) if strip else merged
        out_img.save(out_path.as_posix(), "PNG", optimize=optimize, compress_level=level)
        log(f"[AUTO] Склейка: сохранено {out_path}")

    # Удаляем все исходники главы ОДНИМ заходом (после успешной склейки всей главы)
    if bool(cfg.get("delete_sources", False)):
        removed = 0
        for src in files:
            try:
                os.remove(src)
                removed += 1
            except Exception:
                pass
        if removed:
            log(f"[AUTO] Удалено исходников всей главы: {removed} шт")



# --- helper: гарантированно оказываемся на странице viewer этой главы ---
def _ensure_on_viewer(context, page, viewer_url: str, log):
    """Возвращает актуальную page, на которой точно открыт viewer данной главы."""
    try:
        # если уже открыта вкладка viewer — переключимся на неё
        for p in reversed(context.pages):
            if "/viewer/" in (p.url or ""):
                try:
                    p.bring_to_front()
                except Exception:
                    pass
                return p

        # если текущая вкладка не viewer — откроем тут (или в новой, если вкладка «мертва»)
        if "/viewer/" not in (page.url or ""):
            try:
                page.goto(viewer_url, wait_until="domcontentloaded", timeout=90000)
            except Exception:
                page = context.new_page()
                page.goto(viewer_url, wait_until="domcontentloaded", timeout=90000)

        page.wait_for_load_state("networkidle", timeout=60000)
        return page
    except Exception as e:
        log(f"[DEBUG] ensure_on_viewer fallback: {e}")
        try:
            p = context.new_page()
            p.goto(viewer_url, wait_until="domcontentloaded", timeout=90000)
            p.wait_for_load_state("networkidle", timeout=60000)
            return p
        except Exception:
            return page


def run_parser(
    title_id: str,
    chapter_spec: Optional[str] = None,
    chapters: Optional[Iterable[str]] = None,
    out_dir: str = "",
    on_log: Optional[Callable[[str], None]] = None,
    on_need_login: Optional[Callable[[], None]] = None,
    stop_flag: Optional[Callable[[], bool]] = None,
    min_width: int = 720,
    auto_concat: Optional[dict] = None,
    on_confirm_purchase: Optional[Callable[[int, Optional[int]], bool]] = None,    # ← НОВОЕ
    on_confirm_use_rental: Optional[Callable[[int, int, Optional[int], str], bool]] = None,
    by_index: Optional[int] = None, # ← НОВОЕ
) -> None:
    log = (on_log or (lambda s: None))
    should_stop = (stop_flag or (lambda: False))

    ensure_dir(out_dir)
    state_path = Path(os.path.join(out_dir, "kakao_auth.json"))
    title_dir = Path(os.path.join(out_dir, f"kakao_{title_id}"))
    ensure_dir(title_dir.as_posix())
    out_root = title_dir
    log(f"[DEBUG] Выставленная ширина (px) = {min_width}")
    try:
        with sync_playwright() as p:
            # запуск Edge → fallback на Chromium
            try:
                browser = p.chromium.launch(
                    headless=False, channel="msedge",
                    args=["--disable-http2","--no-sandbox","--disable-setuid-sandbox",
                          "--disable-features=NetworkServiceInProcess","--disable-blink-features=AutomationControlled"]
                )
            except Exception:
                browser = p.chromium.launch(
                    headless=False,
                    args=["--disable-http2","--no-sandbox","--disable-setuid-sandbox",
                          "--disable-features=NetworkServiceInProcess","--disable-blink-features=AutomationControlled"]
                )

            # контекст: сессия из файла или первичный вход
            if state_path.exists():
                context = browser.new_context(
                    user_agent=UA, java_script_enabled=True, bypass_csp=True,
                    viewport={"width": 1000, "height": 1400}, ignore_https_errors=True,
                    locale="ko-KR", timezone_id="Asia/Seoul",
                    storage_state=str(state_path),
                )
                page = context.new_page()
                log("[OK] Найдена сохранённая сессия. Повторный вход не требуется.")
            else:
                log("[INFO] Сохранённая сессия не найдена — потребуется вход.")
                context = browser.new_context(
                    user_agent=UA, java_script_enabled=True, bypass_csp=True,
                    viewport={"width": 1200, "height": 1800}, ignore_https_errors=True,
                    locale="ko-KR", timezone_id="Asia/Seoul",
                )
                page = context.new_page()
                page.goto("https://page.kakao.com", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_load_state("networkidle", timeout=300000)
                log("[LOGIN] Открылся браузер. Войдите в аккаунт, затем нажмите «Продолжить после входа».")
                if on_need_login:
                    on_need_login()
                context.storage_state(path=str(state_path))
                log(f"[OK] Авторизация сохранена: {state_path}")
                context.close()
                context = browser.new_context(
                    user_agent=UA, java_script_enabled=True, bypass_csp=True,
                    viewport={"width": 1200, "height": 1800}, ignore_https_errors=True,
                    locale="ko-KR", timezone_id="Asia/Seoul",
                    storage_state=str(state_path),
                )
                page = context.new_page()
            
            # ---------- подготовка карты глав ----------
            
            def _prepare_maps() -> Tuple[dict, dict]:
                """Готовит карты глав с ИНКРЕМЕНТАЛЬНЫМ раскрытием списка.

                Идея: раскрываем «по одному шагу» (вниз/вверх) через reveal_all_chapters(..., max_rounds=1),
                после каждого шага собираем карту collect_chapter_map и проверяем, появились ли все нужные главы.
                Если нужные главы не заданы — идём до «дна» (как раньше).
                """
                content_url = f"https://page.kakao.com/content/{title_id}"
                page.goto(content_url, wait_until="domcontentloaded", timeout=90000)
                page.wait_for_load_state("networkidle", timeout=60000)
                smart_scroll(page)
                page.wait_for_load_state("networkidle", timeout=30000)

                # Что требуется найти? (из внешних переменных chapter_spec/chapters)
                _want_ids: set = set()
                _want_nums: set = set()
                try:
                    if chapters:
                        for _x in chapters:
                            if str(_x).isdigit():
                                _want_ids.add(str(_x))
                    if (chapter_spec or "").strip():
                        from_numbers = parse_chapter_spec(chapter_spec)
                        for _n in from_numbers:
                            try:
                                _want_nums.add(int(_n))
                            except Exception:
                                pass
                except Exception:
                    pass

                # Вспомогательные проверки
                def _enough(num_to_id: dict, id_to_num: dict) -> bool:
                    if _want_ids:
                        have_ids = set(id_to_num.keys())
                        if not _want_ids.issubset(have_ids):
                            return False
                    if _want_nums:
                        have_nums = set(num_to_id.keys())
                        if not _want_nums.issubset(have_nums):
                            return False
                    return True

                # Начальный снимок без раскрытия
                num_to_id, id_to_num = _build_maps_from_content(page, title_id)
                # --- авто-направление: сравниваем видимый диапазон и цели ---
                prefer = None
                try:
                    vis_nums = [int(k) for k in (sorted(num_to_id.keys()) if num_to_id else [])]
                    if vis_nums and _want_nums:
                        vmin, vmax = min(vis_nums), max(vis_nums)
                        tmin, tmax = min(_want_nums), max(_want_nums)
                        if tmax < vmin:
                            prefer = 'down'
                        elif tmin > vmax:
                            prefer = 'up'
                        else:
                            prefer = 'down' if (tmin <= (vmin+vmax)//2) else 'up'
                    if prefer:
                        try: log(f"[AUTO] Предпочтительное направление раскрытия: {prefer}")
                        except Exception: pass
                except Exception:
                    prefer = None

                if _enough(num_to_id, id_to_num):
                    return num_to_id, id_to_num

                # Если ничего конкретного не просили — старое поведение: раскрываем «до дна»
                if not _want_ids and not _want_nums:
                    try:
                        reveal_all_chapters(page, title_id, on_log=log, max_rounds=80, pause=0.6, prefer=None, target_nums=None, stop_on_match=False)
                    except Exception as e:
                        log(f"[WARN] Не удалось раскрыть список глав кликами: {e}")
                    smart_scroll(page, max_loops=5, step=2500, pause=0.3)
                    return _build_maps_from_content(page, title_id)

                # Идём шагами, пока не найдём всё запрошенное или не достигнем «дна»
                prev_count = len(id_to_num)
                stable_loops = 0
                for i in range(120):
                    try:
                        log(f"[DEBUG] Раскрытие списка глав — шаг {i+1}…")
                    except Exception:
                        pass
                    try:
                        reveal_all_chapters(page, title_id, on_log=lambda s: None, max_rounds=1, pause=0.5, prefer=prefer, target_nums=list(_want_nums), stop_on_match=True)
                    except Exception:
                        pass
                    smart_scroll(page, max_loops=2, step=2500, pause=0.25)
                    num_to_id, id_to_num = _build_maps_from_content(page, title_id)

                    cur_count = len(id_to_num)
                    try:
                        log(f"[DEBUG] Найдено ссылок /viewer/: {cur_count} (+{cur_count - prev_count})")
                    except Exception:
                        pass

                    if _enough(num_to_id, id_to_num):
                        try:
                            log("[INFO] Нашли все запрошенные главы — останавливаем раскрытие.")
                        except Exception:
                            pass
                        return num_to_id, id_to_num

                    if cur_count <= prev_count:
                        stable_loops += 1
                    else:
                        stable_loops = 0
                    prev_count = cur_count

                    if stable_loops >= 3:
                        try:
                            log("[INFO] Похоже, достигли конца списка глав.")
                        except Exception:
                            pass
                        break

                return num_to_id, id_to_num

            to_fetch: List[Tuple[str, Optional[int]]] = []
            
            if chapters:
                chapter_ids = [str(x) for x in chapters if str(x).isdigit()]
                log(f"[INFO] Используем viewerId: {chapter_ids}")
                # Прямой режим по ID: сразу идём в viewer и качаем изображения без построения карты глав.
                for vid in chapter_ids:
                    to_fetch.append((vid, None))

            elif by_index:
                try:
                    idx_value = int(by_index)
                except Exception:
                    idx_value = 0
                if idx_value == 0:
                    log("[ERROR] Индекс 0 недопустим. Используйте 1, 2, ... или -1, -2, ...")
                    try:
                        browser.close()
                    except Exception:
                        pass
                    return

                # Открываем страницу тайтла
                content_url = f"https://page.kakao.com/content/{title_id}"
                page.goto(content_url, wait_until="domcontentloaded", timeout=90000)
                page.wait_for_load_state("networkidle", timeout=60000)
                smart_scroll(page)
                # Определим prefer на основе видимого диапазона номеров
                try:
                    cmap0 = collect_chapter_map(page, title_id) or []
                    vis_nums = [int(r.get('num')) for r in cmap0 if isinstance(r.get('num'), int)]
                    prefer = None
                    if vis_nums:
                        vmin, vmax = min(vis_nums), max(vis_nums)
                        # Эвристика: если верхние номера > нижних, а нам нужен "ранний" индекс — раскрываем вниз,
                        # иначе вверх. Это лишь выбор направления; фактическая выборка ниже.
                        prefer = 'down' if (vmin > 1) else 'up'
                    log(f"[AUTO] Предпочтительное направление раскрытия: {prefer or 'auto'}")
                except Exception:
                    prefer = None

                page.wait_for_load_state("networkidle", timeout=30000)

                # Считать и залогировать 전체
                total = read_total_chapters(page)
                if isinstance(total, int) and total > 0:
                    log(f"[INFO] Всего глав = {total}")
                else:
                    total = None

                # Полностью раскрыть список глав
                reveal_all_chapters(page, title_id, on_log=log, max_rounds=80, pause=0.6, prefer=None, target_nums=None, stop_on_match=False)

                # Собрать ссылки /viewer/ в DOM-порядке
                arr = collect_viewer_links_dom_order(page, title_id) or []

                if not total:
                    total = len(arr)
                    log(f"[INFO] Всего ссылок: {total}")

                if idx_value > (total or 0):
                    log(f"[WARN] Запрошенный индекс ({idx_value}) > общего числа глав ({total}). Завершение.")
                    try:
                        browser.close()
                    except Exception:
                        pass
                    return

                # Определить направление (от первой к новой)
                def first_num(items):
                    for it in items:
                        n = it.get('num')
                        if isinstance(n, int):
                            return n
                    return None

                first = first_num(arr)
                last = first_num(list(reversed(arr)))
                # По умолчанию — считаем, что DOM идёт от новой к старой → разворачиваем.
                earliest_first = list(reversed(arr))
                if isinstance(first, int) and isinstance(last, int):
                    if first < last:
                        # уже от старой к новой
                        earliest_first = arr

                # Индексация 1-based
                # Индексация 1-based; поддержка отрицательных индексов (от конца)
                seq = earliest_first if idx_value > 0 else list(reversed(earliest_first))
                pos = abs(idx_value)
                n = len(seq)
                if pos > n:
                    log(f"[ERROR] Индекс вне диапазона: {pos} (всего глав: {n}).")
                    try:
                        browser.close()
                    except Exception:
                        pass
                    return

                target = seq[pos - 1]
                vid = str(target.get('id'))
                num_guess = target.get('num') if isinstance(target.get('num'), int) else None
                log(f"[INFO] Индекс {idx_value} → viewerId {vid}" + (f" (№{num_guess})" if num_guess else ""))
                to_fetch.append((vid, num_guess))


            elif chapter_spec:
                num_to_id, id_to_num = _prepare_maps()
                wanted_nums = parse_chapter_spec(chapter_spec)
                log(f"[INFO] Запрошены главы (номера): {wanted_nums}")
                for n in wanted_nums:
                    vid = num_to_id.get(n)
                    if vid: to_fetch.append((vid, n))
                    else:   log(f"[WARN] Не найден viewerId для главы №{n} — пропуск.")

            if not to_fetch:
                log("[ERROR] Нет ни одной главы для скачивания (проверьте ввод).")
                try: browser.close()
                except Exception: pass
                return

            # ---------- загрузка глав ----------
            PRICE = 200
            for ch_id, ch_num in to_fetch:
                if should_stop():
                    break

                folder_name = str(ch_num) if (ch_num is not None) else str(ch_id)
                ch_dir = out_root / folder_name
                if chapter_has_files(ch_dir):
                    tag = f"№{ch_num}" if ch_num is not None else f"id={ch_id}"
                    log(f"[SKIP] Глава {tag}: уже есть файлы в {ch_dir}. Пропускаю.")
                    continue
                # Если папка существует, но пуста — сообщаем и продолжаем сохранять в неё
                if ch_dir.exists() and not chapter_has_files(ch_dir):
                    log(f"[INFO] Папка {ch_dir} уже существует, но пуста. Продолжаю сохранять сюда.")
                url = f"https://page.kakao.com/content/{title_id}/viewer/{ch_id}"
                page.set_extra_http_headers({"Referer": url})
                tag = f"№{ch_num} (id={ch_id})" if ch_num is not None else f"id={ch_id}"
                log(f"[Загрузка] Глава {tag} ...")
                chap_label = (f"№{ch_num}" if ch_num is not None else f"id={ch_id}")

                page.goto(url, wait_until="domcontentloaded", timeout=90000)
                page.wait_for_load_state("networkidle", timeout=60000)
                # --- 0) если показалась модалка об истечении аренды — закроем её ---
                try:
                    handled_expire = handle_rental_expired_modal(page, log)
                    if handled_expire:
                        pass  # дальше появится модалка применения тикета
                except Exception:
                    pass

                # --- 1) модалка тикетов ---
                res = handle_ticket_modal(
                    page, context, title_id, url, PRICE, log,
                    chapter_label=chap_label, confirm_use_rental_cb=(on_confirm_use_rental or (lambda r,o,b,cl: True)),
                    confirm_purchase_cb=on_confirm_purchase
                )
                if res == "skipped":
                    continue  # отказ/ошибка
                # 'purchased'/'consumed' — ок, 'absent' → проверим buy-страницу

                # --- 2) buy-страница без модалки ---

                if res == "need_buy" or "/buy/ticket" in (page.url or ""):
                    ok = handle_buy_page(page, context, title_id, url, PRICE, log,
                                         confirm_purchase_cb=(on_confirm_purchase or (lambda price, bal: True)))
                    if ok != "purchased":
                        if ok == "skipped":
                            log("[SKIP] Покупка тикета отменена пользователем.")
                        else:
                            log("[SKIP] Покупка не выполнена.")
                        continue
                    # после успешной покупки вернёмся в viewer и попробуем снова
                    res3 = handle_ticket_modal(page, context, title_id, url, PRICE, log,
                                               chapter_label=chap_label,
                                               confirm_use_rental_cb=(
                                                           on_confirm_use_rental or (lambda r, o, b, cl: True)),
                                               confirm_purchase_cb=on_confirm_purchase)
                    if res3 == "skipped":
                        # пользователь отказал / не смогли нажать — эту главу пропускаем
                        continue
                    # res3 == 'consumed' или 'purchased' — ок, можно идти дальше
                    # res3 == 'absent' — модалки нет, значит доступ открыт, идём дальше

                # --- 3) гарантированно оказываемся на viewer + легкий «прогрев» ---
                page = _ensure_on_viewer(context, page, url, log)
                try:
                    page.wait_for_timeout(600)
                    page.evaluate("window.scrollTo(0, 0)")
                    page.wait_for_timeout(200)
                except Exception:
                    pass

                # --- 4) автоскролл и сбор ссылок ---
                smart_scroll(page)
                page.wait_for_load_state("networkidle", timeout=30000)

                urls = collect_urls_with_width(page, url, min_width)
                if not urls:
                    log("[DEBUG] Не вижу изображений — перезагружаю viewer и пробую ещё раз…")
                    try:
                        page.reload()
                        page.wait_for_load_state("domcontentloaded", timeout=90000)
                        page.wait_for_load_state("networkidle", timeout=60000)
                        page.wait_for_timeout(500)
                        page.evaluate("window.scrollTo(0, Math.min(1200, document.body.scrollHeight/3))")
                        page.wait_for_timeout(600)
                    except Exception:
                        pass
                    urls = collect_urls_with_width(page, url, min_width)

                log(f"[DEBUG] При ширине = {min_width} найдено файлов: {len(urls)}")
                if not urls and min_width > 1:
                    log("[HINT] Пусто. Попробуйте снизить «Мин. ширина (px)».")

                saved, failed = save_images_with_context(
                    context, urls, ch_dir, ref_url=url,
                    target_w=0, pick_ext=sanitize_ext, log=log
                )
                log(f"[OK] Глава {tag}: сохранено {saved} изображений (ошибок: {failed})")

                # --- 5) автосклейка (если включена) ---
                if auto_concat and auto_concat.get("enable"):
                    try:
                        _auto_concat_chapter(ch_dir, title_id, folder_name, auto_concat, log)
                    except Exception as e:
                        log(f"[WARN] Автосклейка главы '{folder_name}' не выполнена: {e}")

            try:
                context.close(); browser.close()
            except Exception:
                pass

        if not should_stop():
            log(f"Завершено.")
    except Exception as e:
        log(f"[ERROR] {e}")

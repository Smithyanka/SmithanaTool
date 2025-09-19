# -*- coding: utf-8 -*-
"""
DOM-утилиты: прокрутка страницы и сбор URL изображений с учётом минимальной ширины.
"""

from typing import List
import re



def _smart_scroll_legacy(page, max_loops: int = 40, step: int = 3000, pause: float = 0.4) -> None:
    """
    Плавно прокручивает страницу вниз, пока высота документа не перестанет расти
    несколько итераций подряд (или не достигнем max_loops).
    """
    import time
    stable_rounds = 0
    last_height = page.evaluate("() => document.body.scrollHeight")
    for _ in range(max_loops):
        page.mouse.wheel(0, step)
        time.sleep(pause)
        new_h = page.evaluate("() => document.body.scrollHeight")
        if new_h <= last_height:
            stable_rounds += 1
        else:
            stable_rounds = 0
        last_height = new_h
        if stable_rounds >= 3:
            break

def _count_viewer_links(page, title_id: str) -> int:
    js = f"() => document.querySelectorAll('a[href*=\"/content/{title_id}/viewer/\"]').length"
    try:
        return int(page.evaluate(js))
    except Exception:
        return 0



def reveal_all_chapters(page, title_id: str, on_log=lambda s: None, max_rounds: int = 80, pause: float = 0.6,
                        prefer: str | None = None, target_nums: list[int] | None = None, stop_on_match: bool = False):
    """
    Пытается нажать «показать ещё» (вниз/вверх), пока число ссылок /viewer/ растёт.
    Работает на странице https://page.kakao.com/content/<title_id>.
    prefer: 'down' | 'up' | None — приоритет направления кликов.
    target_nums: список целевых номеров глав; если stop_on_match=True, прекращает раскрытие при появлении цели.
    """
    import time

    DOWN_SELECTORS = [
        "div.flex.cursor-pointer.items-center.justify-center.rounded-b-12pxr.bg-bg-a-20.py-8pxr",
        "img[alt*='아래']",
    ]
    UP_SELECTORS = [
        "div.flex.items-center.justify-center.bg-bg-a-20.cursor-pointer.mx-15pxr.py-8pxr.border-t-1.border-solid.border-line-20",
        "img[alt*='위']",
    ]

    def try_click_any(selectors) -> bool:
        for sel in (selectors or []):
            try:
                loc = page.locator(sel).first
                if loc and loc.count() > 0:
                    try:
                        loc.click(timeout=800)
                        return True
                    except Exception:
                        pass
            except Exception:
                continue
        return False

    def _count() -> int:
        return _count_viewer_links(page, title_id)

    def _has_target_visible() -> bool:
        if not target_nums:
            return False
        nums = set(int(x) for x in (target_nums or []) if isinstance(x, int) or (isinstance(x, str) and str(x).isdigit()))
        try:
            cur = collect_chapter_map(page, title_id) or []
            for r in cur:
                n = r.get('num')
                if isinstance(n, int) and n in nums:
                    return True
            return False
        except Exception:
            return False

    # формируем порядок направления
    pref = (str(prefer).lower() if isinstance(prefer, str) else None)
    if pref == 'up':
        orders = (('up', UP_SELECTORS), ('down', DOWN_SELECTORS))
    elif pref == 'down':
        orders = (('down', DOWN_SELECTORS), ('up', UP_SELECTORS))
    else:
        orders = (('down', DOWN_SELECTORS), ('up', UP_SELECTORS))

    stable = 0
    last = _count()
    try: on_log(f"[DEBUG] Найдено ссылок перед раскрытием: {last}")
    except Exception: pass
    for _ in range(max_rounds):
        changed = False

        # ранний выход, если цель уже видна
        if stop_on_match and _has_target_visible():
            try: on_log("[AUTO] Целевая глава видна — прекращаю раскрытие.")
            except Exception: pass
            break

        # пробуем в предпочитаемом порядке
        for label, sels in orders:
            try:
                if try_click_any(sels):
                    try: on_log(f"[AUTO] Раскрываю {label}")
                    except Exception: pass
                    time.sleep(pause)
                    # легкий прогрев/скролл
                    try: smart_scroll(page, max_loops=1, step=2000, pause=pause / 2)
                    except Exception: pass
                    cur = _count()
                    if cur > last:
                        last = cur
                        changed = True
                        break  # в этом раунде хватит
            except Exception:
                pass

        # доброскролл до низа — вдруг ленивый догруз
        try:
            page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(pause / 2)
            cur = _count()
            if cur > last:
                changed = True
                last = cur
        except Exception:
            pass

        if changed:
            stable = 0
            try: on_log(f"[DEBUG] Ссылок после раскрытия: {last}")
            except Exception: pass
        else:
            stable += 1
            if stable >= 3:
                break


def collect_urls_with_width(page, base_url: str, min_width: int):
    """
    Возвращает URL только тех изображений, у которых известная/оценённая ширина >= min_width.
    Источники: img[src|data-src|srcset], source[srcset], background-image (по ширине элемента).
    """
    js = r"""
    (function(){
        const abs = (u) => { try { return new URL(u, window.location.href).href } catch(e) { return null } };
        const out = [];

        // IMG
        document.querySelectorAll('img').forEach(img => {
            const rectW = (img.getBoundingClientRect().width || 0) * (window.devicePixelRatio || 1);
            const natW  = img.naturalWidth || 0;
            const baseW = Math.max(natW, rectW);

            const add = (url, w) => { if (!url || url.startsWith('data:')) return;
                                       out.push({url: abs(url), w: w || baseW || 0}); };

            const src = img.getAttribute('src');          if (src)  add(src, baseW);
            const dsrc = img.getAttribute('data-src') ||
                         img.getAttribute('data-original'); if (dsrc) add(dsrc, baseW);

            const sset = img.getAttribute('srcset');
            if (sset) {
                sset.split(',').forEach(part => {
                    const bits = part.trim().split(/\s+/);
                    if (!bits[0]) return;
                    const u = abs(bits[0]);
                    let w = 0;
                    if (bits[1] && /(\d+)w/.test(bits[1])) w = parseInt(RegExp.$1, 10);
                    out.push({ url: u, w: w || baseW || 0 });
                });
            }
        });

        // SOURCE srcset
        document.querySelectorAll('source[srcset]').forEach(el => {
            const rectW = (el.parentElement?.getBoundingClientRect().width || 0) * (window.devicePixelRatio || 1);
            const sset = el.getAttribute('srcset') || '';
            sset.split(',').forEach(part => {
                const bits = part.trim().split(/\s+/);
                if (!bits[0]) return;
                const u = abs(bits[0]);
                let w = 0;
                if (bits[1] && /(\d+)w/.test(bits[1])) w = parseInt(RegExp.$1, 10);
                out.push({ url: u, w: w || rectW || 0 });
            });
        });

        // background-image (ширина = ширина элемента на экране)
        document.querySelectorAll('[style*="background-image"]').forEach(el => {
            const style = el.getAttribute('style') || '';
            const m = style.match(/background-image\s*:\s*url\((['"]?)([^'")]+)\1\)/i);
            if (m && m[2]) {
                const rectW = (el.getBoundingClientRect().width || 0) * (window.devicePixelRatio || 1);
                out.push({ url: abs(m[2]), w: rectW || 0 });
            }
        });

        // de-dupe: keep max width per URL
        const map = {};
        for (const o of out) {
            if (!o || !o.url) continue;
            if (!map[o.url] || (o.w||0) > (map[o.url].w||0)) map[o.url] = o;
        }
        return Object.values(map);
    })();
    """
    arr = page.evaluate(js)

    # фильтрация по min_width
    urls, seen = [], set()
    mw = int(min_width or 0)
    for obj in (arr or []):
        try:
            u = obj.get("url")
            w = int(obj.get("w") or 0)
        except Exception:
            continue
        if not u or w < mw:
            continue
        if u not in seen:
            seen.add(u)
            urls.append(u)
    return urls


    # фильтрация по min_width и финальная дедупликация
    urls: List[str] = []
    seen = set()
    mw = int(min_width or 0)
    for obj in (arr or []):
        try:
            u = obj.get("url")
            w = int(obj.get("w") or 0)
        except Exception:
            continue
        if not u or w < mw:
            continue
        if u not in seen:
            seen.add(u)
            urls.append(u)
    return urls

def smart_scroll(page, max_loops=60, step=3500, pause=0.6):
    import time
    stable_rounds = 0
    last_height = page.evaluate("() => document.body.scrollHeight")
    for _ in range(max_loops):
        page.mouse.wheel(0, step)
        time.sleep(pause)
        new_h = page.evaluate("() => document.body.scrollHeight")
        if new_h <= last_height:
            stable_rounds += 1
        else:
            stable_rounds = 0
        last_height = new_h
        if stable_rounds >= 3:
            break
    # доброскролл в самый низ
    page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(0.8)



def collect_chapter_map(page, title_id: str):
    """
    Возвращает список словарей {num:int, id:str, href:str} для всех ссылок вида
    /content/<title_id>/viewer/<id> на странице https://page.kakao.com/content/<title_id>.
    Номер берём ТОЛЬКО из подписи формата '<число>화' (напр. '1화', '12 화'), чтобы исключить трейлеры ('1차 ...').
    """
    js = rf"""
    (function() {{
        const list = [];
        const links = Array.from(document.querySelectorAll('a[href*="/content/{title_id}/viewer/"]'));
        for (const a of links) {{
            const href = a.getAttribute('href') || a.href || '';
            const m = href && href.match(/\/content\/{title_id}\/viewer\/(\d+)/);
            if (!m) continue;
            const vid = m[1];

            // ищем номер главы в тексте ссылки или ближайших предков
            const grabNum = (el) => {{
                let cur = el;
                for (let i=0; i<3 && cur; i++) {{
                    const t = (cur.textContent || '').replace(/\s+/g,' ').trim();
                    // ключевое: номер только если рядом есть '화'
                    const mm = t.match(/(\d+)\s*화/);
                    if (mm) return parseInt(mm[1], 10);
                    cur = cur.parentElement;
                }}
                return null;
            }};
            const num = grabNum(a);
            list.push({{ num, id: vid, href }});
        }}

        // de-dupe по id, затем отбрасываем пустые num
        const seen = new Set();
        const out = [];
        for (const r of list) {{
            if (!r || !r.id) continue;
            if (seen.has(r.id)) continue;
            seen.add(r.id);
            if (typeof r.num === 'number' && !isNaN(r.num)) out.push(r);
        }}
        return out;
    }})();
    """
    arr = page.evaluate(js)
    try:
        arr.sort(key=lambda r: int(r.get("num", 0)))
    except Exception:
        pass
    return arr

def read_total_chapters(page) -> int | None:
    """
    Ищет '전체 <число>' СНАЧАЛА внутри
      <div class="flex h-44pxr w-full flex-row items-center justify-between bg-bg-a-20 px-18pxr">
    Если не найдено — пытается подобрать похожие контейнеры (частичные совпадения классов).
    В крайнем случае — глобальный фолбэк по всей странице.
    """
    js = r"""
    (function() {
        function extractNumFrom(node) {
            if (!node) return null;
            let text = '';
            try { text = (node.innerText || node.textContent || ''); } catch(e) {}
            if (!text) return null;
            const m = text.match(/전체\s*([0-9,]+)/);
            if (!m) return null;
            const val = parseInt((m[1] || '').replace(/,/g, ''), 10);
            return Number.isNaN(val) ? null : val;
        }

        // 1) Жёсткий селектор с точным списком классов (если классы приходят ровно так)
        const strictSel = 'div.flex.h-44pxr.w-full.flex-row.items-center.justify-between.bg-bg-a-20.px-18pxr';
        const strict = Array.from(document.querySelectorAll(strictSel));
        for (const el of strict) {
            // Сначала сам контейнер
            let n = extractNumFrom(el);
            if (n !== null) return n;
            // затем дочерние span/div
            const parts = el.querySelectorAll('span,div');
            for (const p of parts) {
                n = extractNumFrom(p);
                if (n !== null) return n;
            }
        }

        // 2) Более гибкие варианты — классы могут идти в другом порядке
        const looseSels = [
            // порядок классов может отличаться
            'div.flex.w-full.flex-row.items-center.justify-between.bg-bg-a-20.px-18pxr',
            // частичные совпадения
            'div[class*="h-44pxr"][class*="justify-between"][class*="bg-bg-a-20"][class*="px-18pxr"]',
            'div[class*="justify-between"][class*="px-18pxr"][class*="bg-bg-a-20"]',
        ];
        for (const sel of looseSels) {
            const els = Array.from(document.querySelectorAll(sel));
            for (const el of els) {
                let n = extractNumFrom(el);
                if (n !== null) return n;
                const parts = el.querySelectorAll('span,div');
                for (const p of parts) {
                    n = extractNumFrom(p);
                    if (n !== null) return n;
                }
            }
        }

        // 3) Фолбэк — по всей странице (на случай редизайна)
        return extractNumFrom(document.body);
    })();
    """
    try:
        return page.evaluate(js)
    except Exception:
        return None



def collect_viewer_links_dom_order(page, title_id: str):
    """Возвращает массив объектов {id:str, href:str, text:str, num:int|None} в ПОРЯДКЕ DOM."""
    js = f"""
    (function() {{
        const list = [];
        const links = Array.from(document.querySelectorAll('a[href*="/content/{title_id}/viewer/"]'));
        const seen = new Set();
        for (const a of links) {{
            const href = a.getAttribute('href') || a.href || '';
            const m = href && href.match(/\\/content\\/{title_id}\\/viewer\\/(\\d+)/);
            if (!m) continue;
            const vid = m[1];
            if (seen.has(vid)) continue;
            seen.add(vid);
            let txt = '';
            try {{ txt = (a.innerText || a.textContent || ''); }} catch(e){{}}
            let num = null;

            // Попробуем найти "<число>화" в ближайшем окружении
            const tryGetNumber = (root) => {{
                if (!root) return null;
                const t = (root.innerText || root.textContent || '').replace(/\\s+/g,' ').trim();
                let mm = t.match(/(\\d+)\\s*화/);
                if (mm) return parseInt(mm[1], 10);
                return null;
            }};

            let m2 = tryGetNumber(a);
            if (m2 === null) {{
                let p = a.closest('li, article, div');
                if (p) {{
                    m2 = tryGetNumber(p);
                }}
            }}
            if (typeof m2 === 'number' && !Number.isNaN(m2)) {{
                num = m2;
            }}

            list.push({{ id: vid, href, text: txt, num }});
        }}
        return list;
    }})();
    """
    try:
        return page.evaluate(js)
    except Exception:
        return []

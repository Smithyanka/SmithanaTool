from __future__ import annotations

import time

def _wait_progress_increase(page, frame, prev_pct: float, timeout_ms: int = 350) -> float:
    """
    Короткое адаптивное ожидание: опрашиваем прогресс, пока он реально не вырастет
    или пока не истечёт timeout_ms. Возвращаем текущий прогресс.
    """
    deadline = time.time() + (timeout_ms / 1000.0)
    last = prev_pct if isinstance(prev_pct, (int, float)) else -1.0
    step = 40
    while time.time() < deadline:
        try:
            cur = _get_progress_percent(page, frame)
            if (cur is not None) and (cur >= 0):
                if last >= 0 and cur > last + 0.01:
                    return cur
                last = max(last, cur)
        except Exception:
            pass
        try:
            page.wait_for_timeout(step)
        except Exception:
            pass
        step = min(120, step + 10)
    try:
        return _get_progress_percent(page, frame)
    except Exception:
        return last

# -*- coding: utf-8 -*-
"""Действия/JS-хелперы для ридера Kakao (novel/text)."""


def _force_eager_assets(target) -> None:
    """
    Принудительно включаем загрузку изображений/фонов в target (page или frame):
    - img.loading='eager'
    - переносим реальные URL из data-* (data-src/data-original/...) в src
    - нормализуем <picture><source srcset>
    - восстанавливаем background-image из data-bg/data-background(-image)
    - триггерим resize/scroll
    """
    js = r"""
    (() => {
      const doc = document;

      const bestFromSrcset = (img) => {
        const ss = img.getAttribute('srcset'); if (!ss) return null;
        let best = null, bestW = 0;
        ss.split(',').map(s=>s.trim()).forEach(it=>{
          const [u,w] = it.split(/\s+/);
          const W = (w && /w$/.test(w)) ? parseInt(w,10) : 0;
          if (W >= bestW) { bestW = W; best = u; }
        });
        return best;
      };

      // IMG: снимаем "ленивость", переносим реальные источники
      doc.querySelectorAll('img').forEach(img => {
        try { img.loading = 'eager'; } catch(e) {}
        const ds = img.dataset || {};
        const dataCand = ds.src || ds.lazySrc || ds.original || ds.source || ds.kkSrc || ds.kkImage
                      || img.getAttribute('data-src') || img.getAttribute('data-original');
        const best = bestFromSrcset(img) || dataCand || img.getAttribute('src');
        if (best && best !== img.src) img.src = best;
      });

      // <picture><source>
      doc.querySelectorAll('picture source').forEach(s => {
        const ds = s.dataset || {};
        const cand = ds.srcset || s.getAttribute('data-srcset') || s.getAttribute('srcset');
        if (cand) s.setAttribute('srcset', cand);
      });

      // background-image из data-*
      doc.querySelectorAll('[data-bg],[data-background],[data-background-image]').forEach(el=>{
        const u = el.getAttribute('data-bg') || el.getAttribute('data-background') || el.getAttribute('data-background-image');
        if (u) el.style.backgroundImage = `url("${u}")`;
      });

      // дёрнем события
      try { window.dispatchEvent(new Event('resize')); } catch(e) {}
      try { document.dispatchEvent(new Event('scroll')); } catch(e) {}
      return true;
    })();
    """
    try:
        target.evaluate(js)
    except Exception:
        pass




def _unlock_scroll_in(target) -> int:
    """
    Делает прокрутку возможной в документе target (page или frame):
      - снимает overflow:hidden/overscroll ограничения у html/body/scrollingElement
      - выключает полноэкранные «перекрывающие» оверлеи (fixed/sticky с большим z-index)
      - фокусирует основной scroll-контейнер
    Возвращает кол-во скрытых оверлеев.
    """
    js = r"""
    (() => {
      const doc = document;
      const se  = doc.scrollingElement || doc.documentElement || doc.body;

      [doc.documentElement, doc.body, se].forEach(el => {
        if (!el) return;
        el.style.overflow = 'auto';
        el.style.overscrollBehavior = 'auto';
        try { el.style.setProperty('-webkit-overflow-scrolling', 'touch', 'important'); } catch(e){}
      });

      const vw = window.innerWidth, vh = window.innerHeight;
      const killers = [];
      doc.querySelectorAll('div,section,aside,header,footer,nav,main').forEach(el => {
        const cs = getComputedStyle(el);
        const pos = cs.position;
        const zi  = parseInt(cs.zIndex || '0', 10) || 0;
        const r   = el.getBoundingClientRect();
        const big = r.width >= vw * 0.8 && r.height >= vh * 0.8;
        const overlay = (pos === 'fixed' || pos === 'sticky') && zi >= 1000 && big;
        if (overlay) killers.push(el);
      });
      killers.forEach(el => {
        el.setAttribute('data-kx-unlocked', '1');
        el.style.pointerEvents = 'none';
        el.style.display = 'none';
      });

      try { (se || doc.body).focus({ preventScroll: true }); } catch(e) {}
      return killers.length;
    })();
    """
    try:
        return int(target.evaluate(js) or 0)
    except Exception:
        return 0




def _scroll_one_step(page, pause_ms: int = 300) -> int:
    """Прокрутка на ~1 экран. Возвращает новый scrollHeight."""
    try:
        h = page.evaluate("""
            (function(){
                const y = window.scrollY || document.documentElement.scrollTop || 0;
                window.scrollTo(0, y + Math.floor(window.innerHeight*0.92));
                return document.documentElement.scrollHeight || document.body.scrollHeight || 0;
            })();
        """)
        page.wait_for_timeout(pause_ms)
        return int(h or 0)
    except Exception:
        try:
            page.wait_for_timeout(pause_ms)
        except Exception:
            pass
        try:
            return int(page.evaluate("document.documentElement.scrollHeight || document.body.scrollHeight || 0") or 0)
        except Exception:
            return 0




def _scroll_to_top(page):
    try:
        page.evaluate("window.scrollTo(0,0)")
        page.wait_for_timeout(300)
    except Exception:
        pass




def _is_text_viewer(page) -> bool:
    """Эвристика определения текстового/EPUB viewer'a (через __NEXT_DATA__)."""
    try:
        data_txt = page.evaluate("""() => (document.getElementById('__NEXT_DATA__')?.textContent) || '' """) or ""
        if '"singleIsTextViewer":true' in data_txt:
            return True
        if '"singleSlideType":"EPUB"' in data_txt:
            return True
    except Exception:
        pass
    return False



def _scroll_one_step_in(target, pause_ms: int = 600) -> int:
    try:
        h = target.evaluate("""
            () => {
              const se = document.scrollingElement || document.body || document.documentElement;
              const y  = (se && se.scrollTop) || 0;
              const H  = (se && se.scrollHeight) || document.body.scrollHeight || 0;
              const vh = (se && se.clientHeight) || window.innerHeight || 800;
              const next = y + Math.floor(vh * 0.92);
              if (se) se.scrollTo(0, next); else window.scrollTo(0, next);
              return H;
            }
        """)
        target.wait_for_timeout(pause_ms)
        return int(h or 0)
    except Exception:
        try:
            target.wait_for_timeout(pause_ms)
        except Exception:
            pass
        try:
            return int(target.evaluate("() => (document.scrollingElement||document.body||document.documentElement).scrollHeight") or 0)
        except Exception:
            return 0



def _click_top_icon(page) -> bool:
    """
    Try clicking the 'scroll to top' icon to ensure the viewer resets.
    Searches by Korean alt text and data:image SVG fragment. Falls back to Home key.
    """
    # By alt attribute
    try:
        btn = page.locator("img[alt*='상단']").first
        if btn and btn.count() > 0:
            try:
                btn.click(timeout=800)
                page.wait_for_timeout(300)
                return True
            except Exception:
                pass
    except Exception:
        pass

    # By data URL fragment (path pieces from the provided SVG)
    try:
        sel = (
            "img[src^='data:image/svg+xml'][src*='M3 5V19H4.5V5H3Z'],"
            "img[src^='data:image/svg+xml'][src*='5.93994 12.0428']"
        )
        imgs = page.locator(sel)
        cnt = imgs.count() if imgs else 0
        if cnt > 0:
            for i in range(min(5, cnt)):
                try:
                    imgs.nth(i).click(timeout=800)
                    page.wait_for_timeout(300)
                    return True
                except Exception:
                    continue
    except Exception:
        pass

    # Keyboard fallback
    try:
        page.keyboard.press("Home")
        page.wait_for_timeout(100)
        return True
    except Exception:
        pass

    return False



def _get_progress_percent(page, frame=None) -> float:
    """
    Возвращает процент из прогресс-бара главы (0..100), либо -1, если не нашли.
    Ищем внутренний <div class="relative h-full bg-el-70" style="width: NN.NN%;">
    """
    try:
        host = frame or page
        js = r"""
        () => {
          function pickBarRoot(){
            const cands = Array.from(document.querySelectorAll(
              "div.relative.flex.w-full.cursor-pointer.flex-row.items-center.bg-bg-a-10"
            ));
            // обычно высота у бара 4px
            for (const c of cands){
              const st = (c.getAttribute("style")||"");
              if (st.includes("height: 4px")) return c;
            }
            return document;
          }
          const root = pickBarRoot();
          const bars = Array.from(root.querySelectorAll("div.relative.h-full.bg-el-70"));
          let best = null;
          for (const el of bars){
            const s = el.getAttribute("style") || "";
            if (/width:\s*[\d.]+%/.test(s)) best = el;
          }
          if (!best && bars.length) best = bars[bars.length - 1];
          if (!best) return -1;
          const m = (best.getAttribute("style")||"").match(/width:\s*([\d.]+)%/);
          return m ? parseFloat(m[1]) : -1;
        }
        """
        val = host.evaluate(js)
        return float(val) if val is not None else -1.0
    except Exception:
        return -1.0



def _jump_progress_bar(page, frame=None, pos: float = 0.0) -> bool:
    """
    Клик по прогресс-бару ридера, чтобы прыгнуть к позиции pos (0.0..1.0).
    Работает и по основному page, и по iframe (frame). Координаты клика — относительно окна.
    """
    # селекторы для самого "тонкого" 4px бара + запасные варианты
    selectors = [
        # твой случай: <div class="relative flex w-full cursor-pointer flex-row items-center bg-bg-a-10" style="height: 4px;">
        "div.relative.flex.w-full.cursor-pointer.flex-row.items-center.bg-bg-a-10[style*='height: 4px']",
        "div.w-full.cursor-pointer.flex-row[style*='height: 4px']",
        "div.cursor-pointer[style*='height: 4px']",
    ]

    # где искать элементы
    host = frame or page

    # основной путь: кликнуть по самому бару в x = left + width*pos
    for sel in selectors:
        try:
            loc = host.locator(sel).first
            if loc and loc.count() > 0:
                bb = loc.bounding_box()
                if bb and bb.get("width", 0) > 2:
                    x = bb["x"] + max(2, min(bb["width"] - 2, bb["width"] * max(0.0, min(1.0, pos))))
                    y = bb["y"] + bb["height"] / 2
                    page.mouse.move(x, y)
                    page.mouse.click(x, y)
                    page.wait_for_timeout(250)
                    return True
        except Exception:
            continue

    # запасной путь: кликнуть немного левее "ползунка" (handle)
    try:
        handle = host.locator("div.w-21pxr.bg-el-70").first  # <div class="relative h-full w-21pxr bg-el-70">
        if handle and handle.count() > 0:
            hb = handle.bounding_box()
            if hb:
                x = hb["x"] - 20  # к левому краю
                y = hb["y"] + hb["height"] / 2
                page.mouse.click(x, y)
                page.wait_for_timeout(250)
                return True
    except Exception:
        pass

    # крайний случай — клавиша Home
    try:
        page.keyboard.press("Home")
        page.wait_for_timeout(120)
        return True
    except Exception:
        pass

    return False



def _scroll_to_top_in(target):
    try:
        target.evaluate("""() => {
          const se = document.scrollingElement || document.body || document.documentElement;
          if (se) se.scrollTo(0,0); else window.scrollTo(0,0);
        }""")
        target.wait_for_timeout(300)
    except Exception:
        pass




def _collect_image_urls_in(target, min_width: int = 1) -> list[str]:
    """
    Собирает URL изображений внутри target (страница ИЛИ iframe):
    - <img>: currentSrc/srcset/src, берёт самый широкий вариант
    - CSS background-image: url(...)
    Фильтрует по видимой/натуральной ширине >= min_width.
    (ТЕПЕРЬ: рекурсивно проходит через open shadowRoot)
    """
    js = f"""
    () => {{
      function abs(u) {{ try {{ return new URL(u, document.baseURI).href; }} catch(e) {{ return null; }} }}
      const MINW = MINW_PLACEHOLDER;

      function walk(node, visitEl, visitImg){{
        if (!node) return;
        if (node.nodeType === 1){{
          const el = node;
          if (visitImg && el.tagName === 'IMG') visitImg(el);
          if (visitEl) visitEl(el);
          if (el.shadowRoot) Array.from(el.shadowRoot.childNodes).forEach(n=>walk(n, visitEl, visitImg));
          Array.from(el.childNodes).forEach(n=>walk(n, visitEl, visitImg));
        }}
      }}

      const out = new Set();

      // IMG (including shadow DOM)
      walk(document.documentElement, null, (img)=>{{
        const r = img.getBoundingClientRect();
        const dispW = Math.max(0, Math.floor(r.width || 0));
        const natW  = Math.max(0, parseInt(img.naturalWidth || 0));
        let cand = img.currentSrc || img.getAttribute('src');
        const ss = img.getAttribute('srcset');
        if (ss){{
          let best = null, bestW = 0;
          ss.split(',').map(s=>s.trim()).forEach(it=>{{
            const [u,w] = it.split(/\\s+/);
            const W = (w && /w$/.test(w)) ? parseInt(w,10) : 0;
            if (W >= bestW) {{ bestW = W; best = u; }}
          }});
          if (best) cand = best;
        }}
        const useW = Math.max(dispW, natW);
        if (useW >= MINW && cand) {{
          const u = abs(cand); if (u) out.add(u);
        }}
      }});

      // CSS background-image url(...) (including shadow DOM)
      walk(document.documentElement, (el)=>{{
        const cs = getComputedStyle(el);
        const bi = cs.backgroundImage || '';
        if (!bi || bi === 'none') return;
        const urls = bi.match(/url\\(([^)]+)\\)/g) || [];
        const r = el.getBoundingClientRect();
        const W = Math.max(0, Math.floor(r.width || 0));
        if (W < MINW) return;
        urls.forEach(m => {{
          const raw = m.replace(/^url\\((.+)\\)$/, '$1').trim().replace(/^["']|["']$/g, '');
          const u = abs(raw);
          if (u) out.add(u);
        }});
      }}, null);

      return Array.from(out);
    }}
    """.replace("MINW_PLACEHOLDER", str(int(max(1, min_width))))
    try:
        return target.evaluate(js) or []
    except Exception:
        return []




def _click_next_chunk(page) -> bool:
    """
    Move to the next chunk/page inside the current chapter.
    Order:
      1) Click bottom button with exact text "다음" (NOT "다음화").
      2) Click right-arrow SVG (data:image) button per user's selector.
      3) Click any visible element containing "다음" but not "다음화".
      4) Keyboard fallbacks: ArrowRight, PageDown.
    Returns True if we likely moved.
    """
    # 1) Exact "다음" (avoid "다음화")
    try:
        spans = page.locator("span:visible").all()
        for i in range(len(spans) - 1, -1, -1):
            ok = False
            try:
                txt = spans[i].inner_text().strip()
                ok = (txt == "다음")
            except Exception:
                ok = False
            if ok:
                try:
                    spans[i].click()
                    page.wait_for_timeout(500)
                    return True
                except Exception:
                    pass
    except Exception:
        pass

    # 2) Right-arrow SVG (data:image) in toolbar — твой SVG с clipPath id
    try:
        imgs = page.locator("img[src^='data:image/svg+xml'][src*='clip0_5308_49691']")
        cnt = imgs.count() if imgs else 0
        if cnt > 0:
            for i in range(min(5, cnt)):
                try:
                    imgs.nth(i).click(timeout=800)
                    page.wait_for_timeout(300)
                    return True
                except Exception:
                    continue
    except Exception:
        pass

    # 3) Any visible element with '다음' (but not '다음화')
    try:
        candidates = page.locator(":visible").all()
        for i in range(len(candidates) - 1, -1, -1):
            try:
                txt = candidates[i].inner_text().strip()
            except Exception:
                continue
            if txt and ("다음" in txt) and ("다음화" not in txt):
                try:
                    candidates[i].click(timeout=800)
                    page.wait_for_timeout(400)
                    return True
                except Exception:
                    continue
    except Exception:
        pass

    # 4) Keyboard fallbacks
    for key in ("ArrowRight", "PageDown"):
        try:
            page.keyboard.press(key)
            page.wait_for_timeout(120)
            return True
        except Exception:
            pass

    return False



def _activate_viewer(page, frame=None):
    """
    Даем странице/фрейму "user activation":
    - выводим окно на передний план и кликаем по видимым контейнерам;
    - шлем wheel + синтетические события мыши;
    - для iframe кликаем внутри него.
    """
    try:
        page.bring_to_front()
    except Exception:
        pass

    # Клик по главным контейнерам на странице
    for sel in ("main", "div.min-h-screen", "div.min-h-full.w-full", "body"):
        try:
            page.click(sel, timeout=800)
            break
        except Exception:
            continue

    # Легкий wheel, чтобы дернуть IntersectionObserver/ленивые хендлеры
    try:
        page.mouse.wheel(0, 1)
    except Exception:
        pass

    # Попробуем синтетический клик по центру viewport
    try:
        page.evaluate("""
            (function(){
              const el = document.elementFromPoint(innerWidth/2, innerHeight*0.6) || document.body;
              for (const t of ['pointerdown','mousedown','mouseup','click']) {
                el.dispatchEvent(new MouseEvent(t, {bubbles:true, cancelable:true, view:window}));
              }
              return true;
            })();
        """)
    except Exception:
        pass

    # Если есть iframe-вьюер — кликнем и в нем
    if frame:
        for sel in ("main", "body"):
            try:
                frame.click(sel, timeout=800)
                break
            except Exception:
                continue
        try:
            frame.evaluate("""
                (function(){
                  window.dispatchEvent(new Event('scroll'));
                  document.dispatchEvent(new Event('scroll'));
                  return true;
                })();
            """)
        except Exception:
            pass





# -*- coding: utf-8 -*-
"""
DOM-утилиты для НОВЕЛЛ Kakao:
- Распознаём главы по "화" и/или "권" на странице контента.
- Извлекаем основной HTML/текст новеллы, материализуя ::before/::after, скрывая невидимое и
  нормализуя <img srcset> → src. Возвращаем {'html':..., 'text':...}.
"""
from __future__ import annotations


def collect_chapter_map_both(page, title_id: str):
    """
    Возвращает список словарей:
      {id:str, href:str, num:int|None, vol:int|None, label:str}
    Ищем ссылки вида /content/<title_id>/viewer/<id>, подпись берём из ближайшего текста,
    распознаём "<число>권" (том) и "<число>화" (глава), допускаем их совместное присутствие.
    Список отсортирован по (vol?, num?).
    """
    js = rf"""
    (function() {{
        const list = [];
        const links = Array.from(document.querySelectorAll('a[href*="/content/{title_id}/viewer/"]'));
        for (const a of links) {{
            const href = a.getAttribute('href') || a.href || '';
            const m = href.match(/\/content\/{title_id}\/viewer\/(\d+)/);
            if (!m) continue;
            const vid = m[1];

            // Ищем подпись поблизости
            let label = '';
            const cand = [a, a.parentElement, a.closest('li,div,article,section')];
            for (const el of cand) {{
                if (!el) continue;
                const txt = (el.innerText || '').trim().replace(/\s+/g, ' ');
                if (txt && txt.length < 400) {{ label = txt; break; }}
            }}
            if (!label) continue;

            // num/vol
            let vol = null, num = null;
            const mv = label.match(/(\d+)\s*권/);
            const mn = label.match(/(\d+)\s*화/);
            if (mv) vol = parseInt(mv[1], 10);
            if (mn) num = parseInt(mn[1], 10);

            list.push({{ id: vid, href, num, vol, label }});
        }}

        // Дедуп по id
        const seen = new Set();
        const out = [];
        for (const r of list) {{
            if (!r || !r.id) continue;
            if (seen.has(r.id)) continue;
            seen.add(r.id);
            out.push(r);
        }}

        // Сортировка: сначала том, затем глава (нулевые в конец)
        out.sort((a,b) => {{
            const av = (a.vol==null? 1e9 : a.vol);
            const bv = (b.vol==null? 1e9 : b.vol);
            if (av !== bv) return av - bv;
            const an = (a.num==null? 1e9 : a.num);
            const bn = (b.num==null? 1e9 : b.num);
            return an - bn;
        }});
        return out;
    }})();
    """
    return page.evaluate(js)


# CHANGED: используем фрейм (если найден) для извлечения html+text
def extract_main_content(page_or_frame):
    js = r"""
    (function () {
      function normLen(el){ return ((el && el.innerText)||'').replace(/\s+/g,' ').trim().length; }

      // ==== выбор "корневого" контейнера с текстом ====
      function pickContainer() {
        const sels = [
          'main div.mx-auto[style*="max-width"]',
          'div.min-h-screen',
          'div.min-h-full.w-full',
          'article[role="article"]',
          'article',
          'main',
          '[role="main"]'
        ];
        const vwH = window.innerHeight || 900;
        const footerWords = /(댓글|코멘트|리뷰|평점|별점|작가의\s*말|공유|신고|구매|후기|작품\s*정보|상세정보)/;

        function scoreEl(el){
          if (!el) return -1;
          const r = el.getBoundingClientRect();
          const top = Math.max(0, r.top|0);
          const text = (el.innerText||'').replace(/\s+/g,' ').trim();
          const L = text.length;
          const pCount = el.querySelectorAll('p, br, h1, h2, h3, h4, h5, h6').length;
          const btnCount = el.querySelectorAll('button, [role="button"], a[href]').length;
          const asidePenalty = (/^(ASIDE|FOOTER)$/).test(el.tagName) ? 6000 : 0;
          const footerPenalty = footerWords.test(text.slice(0,2000)) ? 8000 : 0; // явные "комменты/рейтинг"
          const buttonPenalty = btnCount > 8 ? 2000 : 0; // слишком "интерактивный" блок
          const posPenalty = top > vwH ? 3000 : 0;       // далеко от верха
          return (L + pCount*1500) - (asidePenalty + footerPenalty + buttonPenalty + posPenalty);
        }

        const cands = new Set();
        sels.forEach(s => document.querySelectorAll(s).forEach(el => cands.add(el)));
        // добавим родителей первых <p> как кандидатов
        Array.from(document.querySelectorAll('p')).slice(0, 30).forEach(p=>{
          let n=p; for(let i=0;i<3;i++){ if(!n) break; cands.add(n); n=n.parentElement; }
        });

        let best=null, bestScore=-1;
        cands.forEach(el=>{
          const sc = scoreEl(el);
          if (sc > bestScore){ bestScore=sc; best=el; }
        });

        return best || document.querySelector('article, main, body') || document.body;
      }

      // ========== вспомогательные ==========
      function visibleText(el){
        let total = '';
        function grab(node){
          if (!node) return;
          if (node.nodeType === 3){
            const t=(node.nodeValue||'').replace(/\s+/g,' ');
            total += t;
            return;
          }
          if (node.nodeType !== 1) return;
          const cs = getComputedStyle(node);
          if (cs.display==='none'||cs.visibility==='hidden'||+cs.opacity===0||+cs.fontSize===0) return;
          // тени (open shadow-root)
          if (node.shadowRoot) Array.from(node.shadowRoot.childNodes).forEach(grab);
          Array.from(node.childNodes).forEach(grab);
          if (/^(P|DIV|BR|SECTION|ARTICLE|LI|UL|OL|H[1-6])$/.test(node.tagName)) total += '\n';
        }
        grab(el);
        return total.replace(/\n{3,}/g, '\n\n').trim();
      }

      // --- аккуратная материализация ::before/::after (без "none") ---
      function pseudoContent(el, which){
        // which: '::before' | '::after'
        const cs = getComputedStyle(el, which);
        if (!cs) return '';
        let c = cs.content;

        // служебные/пустые значения не материализуем
        if (!c || c === 'none' || c === 'normal' || c === 'initial' || c === 'inherit') return '';

        // материализуем ТОЛЬКО строковые литералы в кавычках
        if (!/^["'].*["']$/.test(c)) return '';

        // снимаем кавычки
        c = c.slice(1, -1);

        // перевод строки в CSS content пишут как \A
        c = c.replace(/\\A/g, '\n');

        return c.trim().length ? c : '';
      }

      function materializePseudo(el){
        const before = pseudoContent(el, '::before');
        if (before) { el.insertBefore(document.createTextNode(before + ' '), el.firstChild); }

        const after  = pseudoContent(el, '::after');
        if (after)  { el.appendChild(document.createTextNode(' ' + after)); }
      }

      function deepMaterialize(root){
        (function rec(n){
          if (!n || n.nodeType !== 1) return;
          materializePseudo(n);
          if (n.shadowRoot) Array.from(n.shadowRoot.childNodes).forEach(rec);
          Array.from(n.childNodes).forEach(rec);
        })(root);
      }

      // шум: удаляем/скрываем футеры, сайдбары, блоки "комментарии/рейтинг" внутри выбранного root
      function dropNoise(root){
        if (!root) return;
        const K = /(댓글|코멘트|리뷰|평점|별점|작가의\s*말|공유|신고|구매|후기|작품\s*정보|상세정보)/;
        root.querySelectorAll('aside, footer, nav, [role="contentinfo"], [role="complementary"]').forEach(el=> el.remove());
        Array.from(root.querySelectorAll('*')).forEach(el=>{
          try{
            const t=(el.innerText||'').replace(/\s+/g,' ').trim();
            const btns = el.querySelectorAll('button,[role="button"]').length;
            if (K.test(t) && t.length < 4000) { el.remove(); return; }
            if (btns > 10 && t.length < 1200) { el.remove(); return; }
          }catch(e){}
        });
      }

      // ========== основной алгоритм ==========
      const root = pickContainer();
      if (!root) return null;

      // скрыть явно невидимое
      root.querySelectorAll('*').forEach(el=>{
        const cs = getComputedStyle(el);
        const hidden = cs.display==='none'||cs.visibility==='hidden'||+cs.opacity===0||+cs.fontSize===0;
        const transparent = (cs.color||'').includes('rgba(0, 0, 0, 0)');
        if (hidden || transparent) el.style.display='none';
      });

      dropNoise(root);
      deepMaterialize(root);

      // убрать длинные хэши
      const HEX=/^[0-9a-f]{32,}$/i;
      (function purge(n){
        for (const c of Array.from(n.childNodes)){
          if (c.nodeType===3){
            const t=(c.nodeValue||'').trim(); if (t && HEX.test(t)) c.nodeValue='';
          } else if (c.nodeType===1){ purge(c); }
        }
      })(root);

      // нормализовать <img srcset> → src (на всякий случай для видимости)
      root.querySelectorAll('img[srcset]').forEach(img=>{
        const ss = img.getAttribute('srcset'); if (!ss) return;
        const best = ss.split(',').map(s=>s.trim()).reduce((acc,it)=>{
          const [u,w]=it.split(/\s+/); const W=(w&&/w$/.test(w))?parseInt(w,10):0;
          return (!acc||W>=acc.w)?{u, w:W}:acc;
        }, null);
        if (best) img.setAttribute('src', best.u);
      });

      return { html: root.innerHTML, text: visibleText(root) };
    })();
    """
    try:
        return page_or_frame.evaluate(js)
    except Exception:
        return None


def extract_main_content_html(page_or_frame):
    res = extract_main_content(page_or_frame)
    return res["html"] if res and "html" in res else None

def get_best_text_frame(page):
    try:
        best = None
        best_score = 0
        for fr in page.frames:
            # длина видимого текста внутри фрейма
            try:
                length = fr.evaluate("""() => {
                  const se = document.scrollingElement || document.body || document.documentElement;
                  const t = (se && se.innerText) ? se.innerText : (document.body?.innerText || '');
                  return (t || '').replace(/\\s+/g, ' ').trim().length;
                }""") or 0
            except Exception:
                length = 0
            url = (fr.url or "").lower()
            # бонус за «похожий» URL
            bonus = 5000 if ("viewer" in url or "epub" in url or "reader" in url) else 0
            score = int(length) + bonus
            if score > best_score:
                best_score = score
                best = fr
        # порог, чтобы не брать пустой фрейм
        return best if best and best_score >= 500 else None
    except Exception:
        return None

def _count_viewer_links(page, title_id: str) -> int:
    """Возвращает количество ссылок /content/<title_id>/viewer/<id> на странице тайтла."""
    try:
        return int(page.evaluate(f"""
            () => {{
              const sel = 'a[href*="/content/{title_id}/viewer/"]';
              return Array.from(document.querySelectorAll(sel)).length || 0;
            }}
        """) or 0)
    except Exception:
        return 0



def reveal_all_chapters(
    page,
    title_id: str,
    on_log=lambda s: None,
    max_rounds: int = 80,
    pause: float = 0.6,
    prefer: str | None = None,
    want_chs: list[int] | None = None,
    want_vols: list[int] | None = None,
    stop_on_match: bool = True,
):
    """
    Манхва-стиль раскрытия с учётом приоритета направления.
    - prefer: "down"/"up"/None — порядок попыток;
    - want_chs / want_vols: если указаны, прекращаем раскрытие при появлении целевой главы;
    Работает на странице https://page.kakao.com/content/<title_id>.
    """
    def _count():
        try:
            return int(page.evaluate(
                f"""() => (Array.from(document.querySelectorAll('a[href*="/content/{title_id}/viewer/"]'))||[]).length"""
            ) or 0)
        except Exception:
            return 0

    def _click_any(selectors: list[str]) -> bool:
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if loc and loc.count() > 0:
                    try:
                        loc.click(timeout=800)
                        page.wait_for_timeout(int(pause * 1000))
                        return True
                    except Exception:
                        pass
            except Exception:
                pass
        return False

    # селекторы
    DOWN_SELECTORS = [
        "div.flex.cursor-pointer.items-center.justify-center.rounded-b-12pxr.bg-bg-a-20.py-8pxr",
        "img[alt*='아래']",
        "button:has-text('더보기')",
    ]
    UP_SELECTORS = [
        "div.flex.items-center.justify-center.bg-bg-a-20.cursor-pointer.mx-15pxr.py-8pxr.border-t-1.border-solid.border-line-20",
        "img[alt*='위']",
    ]

    # порядок попыток
    pref = (str(prefer).lower() if isinstance(prefer, str) else None)
    if pref == "up":
        orders = (UP_SELECTORS, DOWN_SELECTORS)
    elif pref == "down":
        orders = (DOWN_SELECTORS, UP_SELECTORS)
    else:
        orders = (DOWN_SELECTORS, UP_SELECTORS)

    # вспом. матч целевой главы
    target_nums = set(want_chs or [])
    target_vols = set(want_vols or [])
    def _has_target_visible() -> bool:
        try:
            from .dom_novel import collect_chapter_map_both as _collect
            lst = _collect(page, title_id) or []
            for r in lst:
                ok = True
                if target_nums:
                    ok = ok and isinstance(r.get('num'), int) and r.get('num') in target_nums
                if target_vols:
                    ok = ok and isinstance(r.get('vol'), int) and r.get('vol') in target_vols
                if ok:
                    return True
            return False
        except Exception:
            return False

    last = _count()
    stable = 0

    for _ in range(max_rounds):
        changed = False

        # останавливаемся, если цель уже видна
        if stop_on_match and (target_nums or target_vols):
            if _has_target_visible():
                try: on_log("[AUTO] Целевая глава видна — прекращаю раскрытие."); 
                except Exception: pass
                break

        # пробуем по порядку (сначала prefer-направление)
        for sels, label in ((orders[0], "down" if orders[0] is DOWN_SELECTORS else "up"),
                            (orders[1], "down" if orders[1] is DOWN_SELECTORS else "up")):
            try:
                if _click_any(sels):
                    try: on_log(f"[AUTO] Раскрываю {label}"); 
                    except Exception: pass
                    cur = _count()
                    if cur > last:
                        last = cur
                        changed = True
                        break  # в этом раунде достаточно одного клика
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

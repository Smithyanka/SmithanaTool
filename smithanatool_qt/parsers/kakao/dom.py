from __future__ import annotations
from typing import Optional, Callable
from pathlib import Path
import time, json, re
from playwright.sync_api import sync_playwright

def _collect_dom_urls_in_ctx(ctx, url, urls_json_path, log=None, stop_flag=None, pre_action=None, scroll_ms=45000):
    page = ctx.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

        if callable(pre_action):
            try:
                ok = pre_action(page)
                if log: log("[INFO] Попытка использовать тикет: " + ("успех" if ok else "не потребовалась/не найдена"))
            except Exception as e:
                if log: log(f"[WARN] Ошибка pre_action: {e}")

        t0, stable_rounds, last_scroll_y = time.time(), 0, -1
        while True:
            if stop_flag and stop_flag(): raise RuntimeError("[CANCEL] Остановлено пользователем.")
            page.evaluate("window.scrollBy(0, Math.floor(window.innerHeight * 0.95))")
            page.wait_for_timeout(180)
            try: page.wait_for_load_state("networkidle", timeout=1500)
            except Exception: pass
            scroll_y = page.evaluate("Math.floor(window.scrollY + window.innerHeight)")
            stable_rounds = stable_rounds + 1 if scroll_y == last_scroll_y else 0
            last_scroll_y = scroll_y
            if (time.time() - t0) * 1000 > scroll_ms and stable_rounds >= 3:
                break

        urls = page.evaluate("""() => {
            const out = new Set();
            for (const img of Array.from(document.querySelectorAll('img'))) {
                if (img.currentSrc) out.add(img.currentSrc);
                if (img.src) out.add(img.src);
                const ss = img.getAttribute('srcset');
                if (ss) for (const part of ss.split(',')) { const u = part.trim().split(' ')[0]; if (u) out.add(u); }
            }
            for (const s of Array.from(document.querySelectorAll('source'))) {
                const ss = s.getAttribute('srcset');
                if (ss) for (const part of ss.split(',')) { const u = part.trim().split(' ')[0]; if (u) out.add(u); }
                const src = s.getAttribute('src'); if (src) out.add(src);
            }
            for (const el of Array.from(document.querySelectorAll('*'))) {
                const st = getComputedStyle(el); const bg = (st && st.backgroundImage) || '';
                const m = Array.from(bg.matchAll(/url\(([^)]+)\)/g));
                for (const mm of m) { let u = (mm[1] || '').trim().replace(/^['"]|['"]$/g, ''); if (u) out.add(u); }
            }
            return Array.from(out);
        }""")
        urls_abs = page.evaluate("""(list) => list.map(u => { try { return new URL(u, location.href).href; } catch { return u; } })""", urls)

        with open(urls_json_path, "w", encoding="utf-8") as f:
            json.dump(urls_abs, f, ensure_ascii=False, indent=0)
        page.wait_for_timeout(400)
        if log: log(f"[URLS] Собрано: {len(urls_abs)}")
    finally:
        try:
            page.close()
        except Exception:
            pass
from smithanatool_qt.parsers.auth_session import get_session_path
from .utils import _viewer_url

def _collect_dom_urls(series_id: int, product_id: str | int, *,
                      out_dir: str, auth_dir: Optional[str] = None,
                      log: Optional[Callable[[str], None]] = None,
                      stop_flag: Optional[Callable[[], bool]] = None,
                      episode_no: int | None = None,
                      pre_action: Optional[Callable] = None,
                      scroll_ms: int = 45000,
                      ctx=None) -> Optional[str]:
    urls_dir = Path(out_dir or ".") / "cache"  # совместимость с уже существующим путём
    urls_dir.mkdir(parents=True, exist_ok=True)
    label = f"{episode_no:04d}" if isinstance(episode_no, int) else f"id_{product_id}"
    urls_json_path = str(urls_dir / f"{label}_urls.json")

    state_path = None
    try:
        state_path = get_session_path(auth_dir or out_dir)
    except Exception:
        state_path = None
    state_path_str = str(state_path) if state_path and Path(state_path).exists() else None
    if log:
        log(f"[DEBUG] Storage state path: {state_path_str or '(нет файла)'}")

    url = _viewer_url(int(series_id), str(product_id))

    # Опционально используем уже созданный контекст (ctx) для ускорения.
    url = _viewer_url(int(series_id), str(product_id))

    if ctx is not None:
        _collect_dom_urls_in_ctx(ctx, url, urls_json_path, log=log, stop_flag=stop_flag, pre_action=callable(pre_action) and pre_action, scroll_ms=scroll_ms)
        return urls_json_path

    # Старый путь: создаём Playwright/браузер/контекст на время одного эпизода
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="msedge")
        ctx_local = None
        try:
            ctx_local = browser.new_context(
                storage_state=state_path_str,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36",
                viewport={"width": 1280, "height": 860},
                locale="ko-KR", timezone_id="Asia/Seoul",
            )
            _collect_dom_urls_in_ctx(ctx_local, url, urls_json_path, log=log, stop_flag=stop_flag, pre_action=callable(pre_action) and pre_action, scroll_ms=scroll_ms)
        finally:
            try:
                if ctx_local: ctx_local.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass

    return urls_json_path


from playwright.sync_api import TimeoutError as PwTimeoutError

def _try_use_rental_ticket(page, log=None):
    """
    Находясь на viewer-странице: кликаем '대여권' / '대여권 사용' и подтверждаем, если появляется диалог.
    Возвращает True при успехе или если ничего нажимать не нужно; False — если кнопка не найдена/не получилось.
    """
    try:
        # Частые варианты текста кнопок
        btn = page.get_by_role("button", name=re.compile("대여권")).first
        if not btn or not btn.is_visible():
            # запасной способ: любой видимый текст содержащий '대여권'
            cand = page.locator("text=/.*대여권.*/").first
            if not cand or not cand.is_visible():
                return False
            btn = cand
        btn.click()
        # иногда всплывает подтверждение
        try:
            confirm = page.get_by_role("button", name=re.compile("확인|사용|예")).first
            if confirm and confirm.is_visible():
                confirm.click()
        except Exception:
            pass

        # ждём, что экспресс-оверлей пропадёт и начнёт грузиться контент
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass

        return True
    except PwTimeoutError:
        return False
    except Exception as e:
        if log: log(f"[WARN] Не удалось нажать '대여권': {e}")
        return False
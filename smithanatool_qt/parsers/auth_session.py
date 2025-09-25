# -*- coding: utf-8 -*-
"""
Единая точка для запуска браузера, фикса окна/viewport/DPI,
сброса зума и проверки/сохранения сессии Kakao.

Использование:
with sync_playwright() as p:
    browser, context, page, state_path = ensure_browser_and_session(
        p, out_dir, UA, on_need_login=on_need_login, log=log,
        viewport=(1280, 860), win_size=(1280, 900), win_pos=(100, 60),
        lang="ko-KR", tz="Asia/Seoul"
    )
"""

from __future__ import annotations
from typing import Callable, Optional, Tuple

import os, json, time, datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

def cookies_look_logged_in(out_dir: str) -> bool:
    """Проверяем kakao_auth.json на наличие куков, похожих на залогиненую сессию."""
    try:
        p = get_session_path(out_dir)
        if not p.exists():
            return False
        data = json.loads(p.read_text(encoding="utf-8", errors="ignore"))
        cookies = data.get("cookies", []) or []
        names = {c.get("name") for c in cookies if isinstance(c, dict)}
        if not names:
            return False
        markers = {
            "_kpwtkn", "_kawlt", "_kawltea", "_karmt", "_karmtea", "_kau", "_kadu",
            "_kpawbat_e", "_kp_collector"
        }
        return any(n in names for n in markers)
    except Exception:
        return False

def _apply_zoom_and_meta(page):
    # 1) Ctrl+0 (без паники, если в IFrame не сработает)
    try:
        page.keyboard.press("Control+0")
    except Exception:
        pass

    # 2) Жёсткий zoom через CSS на всякий
    try:
        page.add_init_script("""
        () => {
          const apply = () => {
            document.documentElement.style.zoom = "100%";
            document.body.style.zoom = "100%";
          };
          window.addEventListener("load", apply, { once: true });
          apply();
        }
        """)
    except Exception:
        pass

    # 3) Нормализуем meta viewport (чтобы не уезжало в «мобильный» режим)
    try:
        page.add_init_script("""
        () => {
          const m = document.querySelector('meta[name="viewport"]');
          if (m) m.setAttribute('content','width=1280, initial-scale=1, maximum-scale=1');
        }
        """)
    except Exception:
        pass


def _kill_overlays_for_login(page):
    # Иногда поверх инпутов висят fixed-хедеры/оверлеи
    try:
        page.add_style_tag(content="""
          html, body { overflow: auto !important; }
          [class*="overlay"], [class*="modal"], [id*="overlay"], header, nav {
            pointer-events: none !important;
          }
        """)
    except Exception:
        pass

    # Проскроллиться к полям логина
    try:
        email = page.locator(
            'input[type="email"], input[name="email"], input[id*="login"], input[name*="login"]'
        ).first
        passwd = page.locator(
            'input[type="password"], input[name*="pass"], input[id*="pass"]'
        ).first
        if email.count() > 0:
            email.scroll_into_view_if_needed()
        if passwd.count() > 0:
            passwd.scroll_into_view_if_needed()
    except Exception:
        pass


def _launch_browser(p, channel: str | None,
                    win_size=(1280, 900), win_pos=(100, 60)):

    args_common = [
        "--disable-http2", "--no-sandbox", "--disable-setuid-sandbox",
        "--disable-features=NetworkServiceInProcess",
        "--disable-blink-features=AutomationControlled",
        f"--window-size={win_size[0]},{win_size[1]}",
        f"--window-position={win_pos[0]},{win_pos[1]}",
        "--force-device-scale-factor=1",
    ]
    try:
        return p.chromium.launch(headless=False, channel=channel, args=args_common)
    except Exception:
        return p.chromium.launch(headless=False, args=args_common)


def ensure_browser_and_session(
    p,
    out_dir: str,
    user_agent: str,
    on_need_login: Optional[Callable[[], None]] = None,
    log: Optional[Callable[[str], None]] = None,
    viewport: Tuple[int, int] = (1280, 860),
    win_size: Tuple[int, int] = (1280, 900),
    win_pos: Tuple[int, int] = (100, 60),
    lang: str = "ko-KR",
    tz: str = "Asia/Seoul",
    channel: Optional[str] = "msedge",
    wait_continue: Optional[Callable[[], bool]] = None,
    stop_flag: Optional[Callable[[], bool]] = None,
):
    """
    Возвращает (browser, context, page, state_path).
    Всегда приводит окно/viewport/DPI к детерминированным значениям и
    обеспечивает наличие/сохранение kakao_auth.json.
    """
    _log = log or (lambda *_: None)
    out_dir = out_dir or os.getcwd()
    os.makedirs(out_dir, exist_ok=True)
    state_path = Path(os.path.join(out_dir, "kakao_auth.json"))

    browser = _launch_browser(p, channel, win_size, win_pos)
    closed_by_user = False

    def _mark_closed(*_):
        nonlocal closed_by_user, closing_programmatically
        if closing_programmatically:
            # наше служебное закрытие: не считаем «закрытием пользователем» и не логируем
            return
        closed_by_user = True
        if log:
            try:
                log("[INFO] Браузер закрыт.")
            except Exception:
                pass
    try:
        browser.on("disconnected", _mark_closed)
    except Exception:
        pass

    def _new_context(with_state: bool):
        kw = dict(
            user_agent=user_agent, java_script_enabled=True, bypass_csp=True,
            viewport={"width": viewport[0], "height": viewport[1]},
            device_scale_factor=1, is_mobile=False,
            ignore_https_errors=True, locale=lang, timezone_id=tz,
        )
        if with_state:
            kw["storage_state"] = str(state_path)
        ctx = browser.new_context(**kw)
        pg = ctx.new_page()
        try:
            pg.on("close", _mark_closed)
        except Exception:
            pass
        _apply_zoom_and_meta(pg)
        return ctx, pg

    if state_path.exists():
        _log("[OK] Найдена сохранённая сессия. Повторный вход не требуется. ")
        context, page = _new_context(with_state=True)
        return browser, context, page, state_path

    # Нет сохранённой сессии — логин
    _log("[INFO] Сохранённая сессия не найдена — потребуется вход. Войдите в аккаунт, затем нажмите «Продолжить после входа».")
    context, page = _new_context(with_state=False)
    page.goto("https://page.kakao.com", wait_until="domcontentloaded", timeout=90000)
    _kill_overlays_for_login(page)
    deadline = time.time() + 60
    while True:
        # мгновенно выходим по стопу/закрытию окна
        if stop_flag and stop_flag():
            raise RuntimeError("LOGIN_ABORTED_BY_STOP")
        if closed_by_user:
            raise RuntimeError("LOGIN_ABORTED_BY_USER")

        # как только DOM хотя бы «interactive» — дальше логинить уже можно
        try:
            if page.is_closed():
                raise RuntimeError("LOGIN_ABORTED_BY_USER")
            rs = page.evaluate("document.readyState")  # 'loading' | 'interactive' | 'complete'
            if rs in ("interactive", "complete"):
                break
        except Exception:
            # контекст/страница исчезли → считаем закрытием
            raise RuntimeError("LOGIN_ABORTED_BY_USER")

        if time.time() > deadline:
            # не ждём «networkidle» бесконечно — продолжаем логин-флоу
            break

        try:
            page.wait_for_timeout(150)
        except Exception:
            raise RuntimeError("LOGIN_ABORTED_BY_USER")

    if on_need_login:
        try:
            on_need_login()
        except Exception:
            pass

    # Сохраняем и пересоздаём контекст с state
    deadline = time.time() + 90
    while True:
        if stop_flag and stop_flag():
            raise RuntimeError("LOGIN_ABORTED_BY_STOP")
        if closed_by_user:
            raise RuntimeError("LOGIN_ABORTED_BY_USER")
        try:
            if page.is_closed():
                raise RuntimeError("LOGIN_ABORTED_BY_USER")
            if "page.kakao.com" in (page.url or ""):
                break
        except Exception:
            raise RuntimeError("LOGIN_ABORTED_BY_USER")
        if time.time() > deadline:
            break  # дальше разберёмся по cookies/state
        try:
            page.wait_for_timeout(200)
        except Exception:
            raise RuntimeError("LOGIN_ABORTED_BY_USER")

    # Ждём логин: читаем state в память, ДИСК НЕ ТРОГАЕМ
    state_json = None
    for _ in range(240):  # ~до 2 минут (240 * 500мс)
        # прерывание по Stop
        if stop_flag and stop_flag():
            raise RuntimeError("LOGIN_ABORTED_BY_STOP")

        # браузер закрыли вручную
        if 'closed_by_user' in locals() and closed_by_user:
            raise RuntimeError("LOGIN_ABORTED_BY_USER")

        try:
            state_json = context.storage_state()  # dict
        except Exception:
            state_json = None

        try:
            if state_json and _state_has_login_markers(state_json):
                # Если требуется дождаться «Продолжить» — ждём тут
                if wait_continue:
                    for __ in range(3600):  # ~12 минут, шаг 200мс
                        if stop_flag and stop_flag():
                            raise RuntimeError("LOGIN_ABORTED_BY_STOP")
                        if 'closed_by_user' in locals() and closed_by_user:
                            raise RuntimeError("LOGIN_ABORTED_BY_USER")
                        if wait_continue():
                            break
                        try:
                            page.wait_for_timeout(200)
                        except Exception:
                            raise RuntimeError("LOGIN_ABORTED_BY_USER")
                    # если к этому моменту Continue так и не нажали — считаем отменой
                    if not wait_continue():
                        raise RuntimeError("LOGIN_ABORTED_BY_STOP")
                break
        except Exception:
            pass

        try:
            page.wait_for_timeout(500)
        except Exception:
            raise RuntimeError("LOGIN_ABORTED_BY_USER")

    # Мини-поллинг: ждём, пока в state появятся «толстые» куки (page.kakao.com)
    def _has_thick_page_cookies(state: dict) -> bool:
        try:
            cookies = state.get("cookies", []) or []
            names = {c.get("name") for c in cookies if isinstance(c, dict)}
            domains = {c.get("domain") for c in cookies if isinstance(c, dict)}
            # Куки, которые обычно добавляются страницей page.kakao.com после логина
            page_markers = {"__T_", "__T_SECURE"}
            return (names & page_markers) or any("page.kakao.com" in (d or "") for d in domains)
        except Exception:
            return False

    # если залогинились, но "страничных" куков ещё нет — аккуратно «догреем»
    if state_json and _state_has_login_markers(state_json) and not _has_thick_page_cookies(state_json):
        # короткий визит на page.kakao.com, чтобы сервер навесил host-cookies
        try:
            if page.is_closed():
                raise RuntimeError("LOGIN_ABORTED_BY_USER")
            page.goto("https://page.kakao.com/menu/10", wait_until="domcontentloaded", timeout=45000)
        except Exception:
            # если вкладка/контекст уже закрыт — трактуем как отмену
            raise RuntimeError("LOGIN_ABORTED_BY_USER")

        warmup_deadline = time.time() + 15  # до ~15 сек
        while time.time() < warmup_deadline:
            # немедленное прерывание по стопу / закрытию окна
            if stop_flag and stop_flag():
                raise RuntimeError("LOGIN_ABORTED_BY_STOP")
            if 'closed_by_user' in locals() and closed_by_user:
                raise RuntimeError("LOGIN_ABORTED_BY_USER")

            # обновляем state из текущего контекста и проверяем «толстые» куки
            try:
                if page.is_closed():
                    raise RuntimeError("LOGIN_ABORTED_BY_USER")
                state_json = context.storage_state()
                if _has_thick_page_cookies(state_json):
                    break
            except Exception:
                raise RuntimeError("LOGIN_ABORTED_BY_USER")

            # мелкая пауза между тиками
            try:
                page.wait_for_timeout(250)
            except Exception:
                raise RuntimeError("LOGIN_ABORTED_BY_USER")
    # --- конец мини-поллинга ---
    # Теперь — ОДИН РАЗ сохраняем на диск (после возвращения из on_need_login)
    try:
        if state_json and _state_has_login_markers(state_json):
            state_path.write_text(json.dumps(state_json, ensure_ascii=False, indent=2), encoding="utf-8")
            _log(f"[OK] Авторизация сохранена: {state_path}")
        else:
            _log("[WARN] Не удалось распознать залогиненную сессию (маркеры не найдены).")
    except Exception:
        _log("[WARN] Не удалось сохранить состояние сессии.")
    closing_programmatically = True
    try:
        context.close()
    except Exception:
        pass

    context, page = _new_context(with_state=state_path.exists())
    return browser, context, page, state_path

def get_session_path(out_dir: str):
    from pathlib import Path
    import os
    out_dir = out_dir or os.getcwd()
    return Path(os.path.join(out_dir, "kakao_auth.json"))

def delete_session(out_dir: str) -> bool:
    """
    Удаляет kakao_auth.json в указанном out_dir.
    Возвращает True, если файл существовал и удалён; False — если его не было.
    """
    p = get_session_path(out_dir)
    try:
        if p.exists():
            p.unlink()
            return True
        return False
    except Exception:
        return False

def _state_has_login_markers(state_json: dict) -> bool:
    try:
        cookies = state_json.get("cookies", []) or []
        names = {c.get("name") for c in cookies if isinstance(c, dict)}
        if not names:
            return False
        markers = {
            "_kpwtkn", "_kawlt", "_kawltea", "_karmt", "_karmtea", "_kau", "_kadu",
            "_kpawbat_e", "_kp_collector"
        }
        return any(n in names for n in markers)
    except Exception:
        return False
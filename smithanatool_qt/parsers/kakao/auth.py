from __future__ import annotations
from typing import Optional, Callable, Tuple
from pathlib import Path
import json
from smithanatool_qt.parsers.auth_session import get_session_path, ensure_browser_and_session

def _build_cookie_from_storage_state(state_json: dict, log=None) -> Optional[str]:
    try:
        cookies = state_json.get("cookies", []) or []
        parts = [f"{c['name']}={c['value']}" for c in cookies if c.get("name") and c.get("value") is not None]
        raw = "; ".join(parts) if parts else None
        if log and raw:
            log(f"[DEBUG] Собрано cookies для GraphQL: {len(parts)} шт.")
        return raw
    except Exception as e:
        if log: log(f"[WARN] Не удалось собрать cookies: {e}")
        return None

def _has_login_markers(state_json: dict) -> bool:
    try:
        names = {c.get("name") for c in state_json.get("cookies", []) if isinstance(c, dict)}
        return bool(names and any(n in names for n in {
            "_kpwtkn","_kawlt","_kawltea","_karmt","_karmtea","_kau","_kadu","_kpawbat_e","_kp_collector"
        }))
    except Exception:
        return False

def _load_cookie_raw_from_session(out_dir: str, on_need_login=None,
                                  stop_flag: Optional[Callable[[], bool]] = None, log=None,
                                  wait_continue: Optional[Callable[[], bool]] = None,

                                  ) -> Tuple[Optional[str], bool, bool]:
    """Возвращает (cookie_raw, attempted_login, login_aborted)."""
    try:
        state_path = get_session_path(out_dir) if get_session_path else Path(out_dir) / "kakao_auth.json"
        if state_path and Path(state_path).exists():
            data = json.loads(Path(state_path).read_text(encoding="utf-8", errors="ignore"))
            cookie = _build_cookie_from_storage_state(data, log=log)
            if cookie and _has_login_markers(data):
                if log: log("[OK] Найдена сохранённая сессия. Повторный вход не требуется.")
                return cookie, False, False

        if ensure_browser_and_session is None:
            return None, False, False
        if stop_flag and stop_flag():
            return None, False, True

        from playwright.sync_api import sync_playwright
        attempted, aborted, state_path_obj = True, False, None
        browser = context = None
        try:
            with sync_playwright() as p:
                UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36"
                browser, context, page, state_path_obj = ensure_browser_and_session(
                    p, out_dir, UA, on_need_login=on_need_login, log=log,
                    viewport=(1280, 860), win_size=(1280, 900), win_pos=(100, 60),
                    lang="ko-KR", tz="Asia/Seoul", channel="msedge",
                    wait_continue=wait_continue,
                    stop_flag=stop_flag,
                )
                if stop_flag and stop_flag():
                    aborted = True
                    return None, attempted, aborted
        except Exception:
            aborted = True
            return None, attempted, aborted
        finally:
            try:
                if context: context.close()
            except Exception: pass
            try:
                if browser: browser.close()
            except Exception: pass

        if not (state_path_obj and Path(state_path_obj).exists()):
            return None, attempted, True
        data = json.loads(Path(state_path_obj).read_text(encoding="utf-8", errors="ignore"))
        cookie = _build_cookie_from_storage_state(data, log=log)
        if not cookie or not _has_login_markers(data):
            return None, attempted, True
        return cookie, attempted, False
    except Exception:
        return None, False, False

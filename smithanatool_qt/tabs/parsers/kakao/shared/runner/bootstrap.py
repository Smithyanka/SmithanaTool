from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from smithanatool_qt.tabs.parsers.kakao.shared.api.graphql import KakaoPageApi
from smithanatool_qt.tabs.parsers.kakao.shared.auth.auth import _load_cookie_raw_from_session
from smithanatool_qt.tabs.parsers.kakao.shared.episodes.map_graphql import episode_map_path, refresh_episode_map, safe_list_all
from smithanatool_qt.tabs.parsers.kakao.shared.utils.kakao_common import ensure_dir


@dataclass(frozen=True)
class KakaoSeriesRuntime:
    series_id: int
    session_dir: Path
    series_dir: Path
    cache_dir: Path
    cookie_raw: str
    api: KakaoPageApi


def prepare_series_runtime(
    *,
    title_id: str,
    out_dir: str,
    on_log: Optional[Callable[[str], None]] = None,
    on_need_login: Optional[Callable[[], None]] = None,
    stop_flag: Optional[Callable[[], bool]] = None,
    wait_continue: Optional[Callable[[], bool]] = None,
    auth_only: bool = False,
    on_after_auth: Optional[Callable[[str], None]] = None,
) -> KakaoSeriesRuntime:
    log = on_log or (lambda *_: None)

    if stop_flag and stop_flag():
        raise RuntimeError('[CANCEL] Остановлено пользователем.')

    try:
        series_id = int(str(title_id).strip())
    except Exception:
        raise RuntimeError('ID тайтла должен быть числовым series_id.')

    session_dir = Path(out_dir or '.')
    series_dir = ensure_dir(session_dir / str(series_id))
    cache_dir = ensure_dir(series_dir / 'cache')

    cookie_raw, attempted_login, login_aborted = _load_cookie_raw_from_session(
        str(session_dir),
        on_need_login=on_need_login,
        stop_flag=stop_flag,
        log=log,
        wait_continue=wait_continue,
    )
    if login_aborted:
        raise RuntimeError('[CANCEL] Авторизация отменена пользователем.')
    if not cookie_raw:
        raise RuntimeError('Не удалось получить cookies из сохранённой сессии.')

    if attempted_login:
        log('[OK] Авторизация выполнена через общий auth-файл.')
    else:
        log('[OK] Использована сохранённая сессия.')

    if on_after_auth:
        try:
            on_after_auth(cookie_raw)
        except Exception:
            pass

    runtime = KakaoSeriesRuntime(
        series_id=series_id,
        session_dir=session_dir,
        series_dir=series_dir,
        cache_dir=cache_dir,
        cookie_raw=cookie_raw,
        api=KakaoPageApi(cookie_raw=cookie_raw, log=log),
    )

    if auth_only:
        return runtime
    return runtime


def load_episode_rows(
    runtime: KakaoSeriesRuntime,
    *,
    on_log: Optional[Callable[[str], None]] = None,
    stop_flag: Optional[Callable[[], bool]] = None,
    sort: str = 'desc',
    retries: int = 2,
    use_cache_map: bool = True,
    fallback_to_cache: bool = True,
) -> tuple[list[dict], Path, bool]:
    log = on_log or (lambda *_: None)
    epmap_path = episode_map_path(runtime.session_dir, runtime.series_id)
    had_cache_before = epmap_path.exists()

    if use_cache_map:
        rows = refresh_episode_map(
            runtime.series_id,
            runtime.session_dir,
            runtime.cookie_raw,
            log=log,
            stop_flag=stop_flag,
            sort=sort,
            retries=retries,
            fallback_to_cache=fallback_to_cache,
        )
    else:
        rows = safe_list_all(
            runtime.series_id,
            sort=sort,
            cookie_raw=runtime.cookie_raw,
            log=log,
            stop_flag=stop_flag,
            retries=retries,
        )

    created_now = bool(rows) and not had_cache_before and epmap_path.exists()
    return rows or [], epmap_path, created_now

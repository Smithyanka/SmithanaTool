from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from playwright.sync_api import sync_playwright

from .download import _download_images_from_list
from .dom import _collect_dom_urls
from .stitch import _auto_stitch_chapter
from .utils import _viewer_url, ensure_dir
from smithanatool_qt.tabs.parsers.kakao.shared.episodes.specs import _safe_list_all, parse_chapter_spec, parse_index_spec
from smithanatool_qt.tabs.parsers.kakao.shared.runner.bootstrap import (
    KakaoSeriesRuntime,
    load_episode_rows,
    prepare_series_runtime,
)
from smithanatool_qt.tabs.parsers.kakao.shared.tickets.runtime import ensure_product_access


def _resolve_targets(
    *,
    all_rows: list[dict],
    chapters: Optional[Iterable[str]],
    chapter_spec: Optional[str],
    by_index: Optional[int],
    by_index_spec: Optional[str],
    log: Callable[[str], None],
) -> tuple[list[str], dict[str, int]]:
    num_to_id: Dict[int, str] = {}
    id_to_num: Dict[str, int] = {}
    for ep in all_rows:
        pid, ep_no = ep.get('productId'), ep.get('episodeNo')
        if not pid or not isinstance(ep_no, int):
            continue
        pid_s = str(pid)
        num_to_id.setdefault(ep_no, pid_s)
        id_to_num.setdefault(pid_s, ep_no)

    targets: List[str] = []
    if chapters:
        targets = [str(x) for x in chapters]
    elif chapter_spec:
        for n in parse_chapter_spec(chapter_spec):
            pid = num_to_id.get(int(n))
            if pid:
                targets.append(pid)
            else:
                log(f'[DEBUG] Нет номера {n} (возможно, пролог/трейлер)')
    elif by_index or by_index_spec:
        rows = list(reversed(all_rows))
        pids = [str(ep['productId']) for ep in rows if ep.get('productId')]
        if by_index_spec:
            idx_list = parse_index_spec(by_index_spec)
        elif by_index:
            idx_list = [int(by_index)]
        else:
            idx_list = []
        seen = set()
        idx_uniq = []
        for x in idx_list:
            if x not in seen:
                idx_uniq.append(x)
                seen.add(x)
        for x in idx_uniq:
            if 1 <= x <= len(pids):
                targets.append(pids[x - 1])
                log(f'[DEBUG] by_index {x} → productId={pids[x - 1]}')
            else:
                log(f'[WARN] by_index {x} вне диапазона (1..{len(pids)})')
    else:
        targets = [pid for _, pid in sorted(num_to_id.items(), key=lambda kv: kv[0])]

    return targets, id_to_num


def run_parser(
    title_id: str,
    chapter_spec: Optional[str] = None,
    chapters: Optional[Iterable[str]] = None,
    out_dir: str = '',
    on_log: Optional[Callable[[str], None]] = None,
    on_need_login: Optional[Callable[[], None]] = None,
    stop_flag: Optional[Callable[[], bool]] = None,
    min_width: int = 720,
    auto_concat: Optional[dict] = None,
    on_choose_ticket_action: Optional[Callable[[dict], str]] = None,
    by_index: Optional[int] = None,
    by_index_spec: Optional[str] = None,
    viewer_ids: Optional[Iterable[int]] = None,
    save_har: bool = True,
    use_cache_map: bool = False,
    delete_cache_after: bool = True,
    scroll_ms: int = 30000,
    auth_only: bool = False,
    on_after_auth: Optional[Callable[[str], None]] = None,
    wait_continue: Optional[Callable[[], bool]] = None,
    runtime: Optional[KakaoSeriesRuntime] = None,
) -> None:
    log = on_log or (lambda s: None)

    if runtime is None:
        runtime = prepare_series_runtime(
            title_id=title_id,
            out_dir=out_dir,
            on_log=log,
            on_need_login=on_need_login,
            stop_flag=stop_flag,
            wait_continue=wait_continue,
            auth_only=auth_only,
            on_after_auth=on_after_auth,
        )
    else:
        if auth_only:
            return

    if auth_only:
        return

    sid = runtime.series_id
    series_dir = str(runtime.series_dir)
    cache_dir = str(runtime.cache_dir)

    if use_cache_map:
        all_rows, epmap_path, epmap_created_now = load_episode_rows(
            runtime,
            on_log=log,
            stop_flag=stop_flag,
            sort='desc',
            retries=2,
            use_cache_map=True,
            fallback_to_cache=True,
        )
    else:
        all_rows = _safe_list_all(sid, sort='desc', cookie_raw=runtime.cookie_raw, log=log, stop_flag=stop_flag, retries=2)
        epmap_path = Path(cache_dir) / 'episode_map.json'
        epmap_created_now = False

    if stop_flag and stop_flag():
        raise RuntimeError('[CANCEL] Остановлено пользователем.')

    targets, id_to_num = _resolve_targets(
        all_rows=all_rows,
        chapters=chapters,
        chapter_spec=chapter_spec,
        by_index=by_index,
        by_index_spec=by_index_spec,
        log=log,
    )
    if viewer_ids:
        targets = [str(x) for x in viewer_ids]

    if stop_flag and stop_flag():
        raise RuntimeError('[CANCEL] Остановлено пользователем.')
    if not targets:
        raise RuntimeError('[ERROR] Нет ни одной главы для скачивания (проверьте ввод).')

    target_ids = [int(x) if str(x).isdigit() else str(x) for x in targets]
    log(f'[INFO] series_id={sid}')
    log(f'[INFO] product_ids={target_ids}')

    pw = None
    browser = None
    shared_ctx = None

    state_path = runtime.session_dir / 'kakao_auth.json'
    state_path_str = str(state_path) if state_path.exists() else None

    try:
        pw = sync_playwright().start()
        try:
            browser = pw.chromium.launch(headless=True, channel='msedge')
        except Exception:
            browser = pw.chromium.launch(headless=True)

        ctx_kwargs = dict(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36',
            viewport={'width': 1280, 'height': 860},
            locale='ko-KR',
            timezone_id='Asia/Seoul',
        )
        if state_path_str:
            ctx_kwargs['storage_state'] = state_path_str
        shared_ctx = browser.new_context(**ctx_kwargs)

        for i, pid in enumerate(targets, 1):
            if stop_flag and stop_flag():
                raise RuntimeError('[CANCEL] Остановлено пользователем.')

            url = _viewer_url(sid, pid)
            log(f'[OPEN] {url}')

            ep_no = id_to_num.get(str(pid))
            label = f'{ep_no:03d}' if isinstance(ep_no, int) else f'id_{pid}'
            product_id = int(pid)

            access_ok, _ = ensure_product_access(
                api=runtime.api,
                series_id=sid,
                product_id=product_id,
                parser_kind='manhwa',
                log=log,
                stop_flag=stop_flag,
                chapter_label=label,
                on_choose_action=on_choose_ticket_action,
            )
            if not access_ok:
                continue

            try:
                urls_json_path = _collect_dom_urls(
                    sid,
                    product_id,
                    out_dir=series_dir,
                    auth_dir=str(runtime.session_dir),
                    log=log,
                    stop_flag=stop_flag,
                    episode_no=ep_no,
                    pre_action=None,
                    scroll_ms=int(scroll_ms),
                    ctx=shared_ctx,
                )
                if urls_json_path:
                    log(f'[OK] URLS {label}: {urls_json_path}')
            except Exception as e:
                log(f'[WARN] URLS {label} не получены: {e}')
                urls_json_path = None

            chapter_dir = str(Path(series_dir) / label)
            try:
                if stop_flag and stop_flag():
                    raise RuntimeError('[CANCEL] Остановлено пользователем.')
                if urls_json_path and Path(urls_json_path).exists():
                    with open(urls_json_path, 'r', encoding='utf-8') as f:
                        urls = json.load(f)

                    _download_images_from_list(
                        urls,
                        chapter_dir,
                        referer=url,
                        cookie_raw=runtime.cookie_raw,
                        min_width=int(min_width) if min_width else 0,
                        log=log,
                        stop_flag=stop_flag,
                        auto_threads=bool((auto_concat or {}).get('auto_threads', True)),
                        threads=int((auto_concat or {}).get('threads', 4)),
                    )

                    if auto_concat and auto_concat.get('enable'):
                        _auto_stitch_chapter(chapter_dir, auto_cfg=auto_concat, log=log, stop_flag=stop_flag)
                else:
                    log(f'[WARN] Нет DOM-URL для {label} (или файл отсутствует)')
            except Exception as e:
                log(f'[WARN] Ошибка докачки DOM-URL для {label}: {e}')
    finally:
        try:
            if shared_ctx:
                shared_ctx.close()
        except Exception as e:
            log(f'[WARN] Не удалось закрыть shared context: {e}')
        try:
            if browser:
                browser.close()
        except Exception as e:
            log(f'[WARN] Не удалось закрыть browser: {e}')
        try:
            if pw:
                pw.stop()
        except Exception as e:
            log(f'[WARN] Не удалось остановить Playwright: {e}')
        if delete_cache_after:
            try:
                if runtime.cache_dir.exists():
                    shutil.rmtree(runtime.cache_dir)
                    log(f'[CACHE] Удалена папка кэша: {runtime.cache_dir}')
            except Exception as e:
                log(f'[WARN] Не удалось удалить папку кэша {runtime.cache_dir}: {e}')

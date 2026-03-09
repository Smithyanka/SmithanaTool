from __future__ import annotations

import html
import json
import re
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Iterable, Optional

from smithanatool_qt.tabs.parsers.kakao.shared.api.graphql import KakaoPageApi
from smithanatool_qt.tabs.parsers.kakao.shared.episodes.map_graphql import picker_rows_from_episode_map
from smithanatool_qt.tabs.parsers.kakao.shared.runner.bootstrap import load_episode_rows, prepare_series_runtime
from smithanatool_qt.tabs.parsers.kakao.shared.tickets.runtime import ensure_product_access
from smithanatool_qt.tabs.parsers.kakao.shared.utils.kakao_common import (
    compute_workers,
    ensure_dir,
    repair_mojibake_text,
    safe_name,
)


def _save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8-sig')


KakaoNovelApi = KakaoPageApi


def _build_resource_url(base_url: str, secure_url: str) -> str:
    if not secure_url:
        raise RuntimeError('Пустой secureUrl')

    secure_url = str(secure_url).strip()
    base_url = str(base_url).strip()

    if secure_url.startswith('http://') or secure_url.startswith('https://'):
        return secure_url
    if base_url.endswith('=') or '?kid=' in base_url:
        return f'{base_url}{secure_url}'
    if base_url.endswith('/'):
        return f"{base_url}{secure_url.lstrip('/')}"
    return f"{base_url}/{secure_url.lstrip('/')}"


def _get_payload_paragraphs(payload: dict) -> list[dict]:
    candidates = [
        payload.get('paragraphList'),
        (payload.get('contentInfo') or {}).get('paragraphList'),
        (payload.get('result') or {}).get('paragraphList'),
        ((payload.get('result') or {}).get('contentInfo') or {}).get('paragraphList'),
    ]
    for paragraphs in candidates:
        if isinstance(paragraphs, list):
            return [p for p in paragraphs if isinstance(p, dict)]
    return []


def _extract_inline_text(node: dict) -> list[str]:
    out: list[str] = []
    txt = node.get('text')
    if isinstance(txt, str) and txt:
        out.append(txt)
    for child in node.get('childParagraphList') or []:
        if isinstance(child, dict):
            out.extend(_extract_inline_text(child))
    return out


def _paragraph_to_text(paragraph: dict) -> str:
    parts: list[str] = []
    txt = paragraph.get('text')
    if isinstance(txt, str) and txt:
        parts.append(txt)
    for child in paragraph.get('childParagraphList') or []:
        if isinstance(child, dict):
            parts.extend(_extract_inline_text(child))
    line = ''.join(parts)
    line = repair_mojibake_text(line)
    line = html.unescape(line)
    line = line.replace(' ', ' ').replace('&nbsp;', ' ')
    line = re.sub(r'[ 	]+', ' ', line)
    return line.strip()


def flatten_text_payload(payload: dict) -> str:
    paragraphs = _get_payload_paragraphs(payload)
    out: list[str] = []
    for p in paragraphs:
        line = _paragraph_to_text(p)
        if not line or line == '&nbsp;':
            continue
        out.append(line)
    return '\n\n'.join(out).strip()


def _normalize_product_ids(chapters: Optional[Iterable[str]]) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    for raw in chapters or []:
        s = str(raw).strip()
        if not s:
            continue
        if not s.isdigit():
            raise RuntimeError(f'Некорректный product_id: {s}')
        pid = int(s)
        if pid not in seen:
            out.append(pid)
            seen.add(pid)
    return out


def _download_part(api: KakaoNovelApi, ats_server_url: str, idx: int, part: dict) -> dict:
    secure_url = str(part.get('secureUrl') or '').strip()
    chapter_id = int(part.get('chapterId', 0))
    content_id = int(part.get('contentId', 0))
    if not secure_url:
        return {
            'idx': idx,
            'chapter_id': chapter_id,
            'content_id': content_id,
            'payload': {},
            'text': '',
            'skipped': True,
        }

    full_url = _build_resource_url(ats_server_url, secure_url)
    payload = api.fetch_json(full_url)
    text = flatten_text_payload(payload)
    return {
        'idx': idx,
        'chapter_id': chapter_id,
        'content_id': content_id,
        'payload': payload,
        'text': text,
        'skipped': False,
    }


def _fetch_parts_parallel(
    api: KakaoNovelApi,
    parts: list[dict],
    ats_server_url: str,
    log: Callable[[str], None],
    stop_flag: Optional[Callable[[], bool]],
    auto_threads: bool,
    threads: int,
) -> list[dict]:
    if not parts:
        return []

    workers = min(len(parts), compute_workers(auto_threads, threads))
    log(f'[INFO] Загрузка частей текста в {workers} поток(ов).')

    if workers <= 1:
        results = []
        for idx, part in enumerate(parts, 1):
            if stop_flag and stop_flag():
                raise RuntimeError('[CANCEL] Остановлено пользователем.')
            result = _download_part(api, ats_server_url, idx, part)
            results.append(result)
            log(
                f"[OK] part {idx}/{len(parts)} "
                f"(chapterId={result['chapter_id']}, contentId={result['content_id']}) "
                f"chars={len(result['text'])}"
            )
        return results

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(_download_part, api, ats_server_url, idx, part): idx
            for idx, part in enumerate(parts, 1)
        }
        for future in as_completed(future_map):
            if stop_flag and stop_flag():
                executor.shutdown(wait=False, cancel_futures=True)
                raise RuntimeError('[CANCEL] Остановлено пользователем.')
            result = future.result()
            results.append(result)
            log(
                f"[OK] part {result['idx']}/{len(parts)} "
                f"(chapterId={result['chapter_id']}, contentId={result['content_id']}) "
                f"chars={len(result['text'])}"
            )

    results.sort(key=lambda x: x['idx'])
    return results


def _fetch_one_product_text(
    api: KakaoNovelApi,
    series_id: int,
    product_id: int,
    series_dir: Path,
    cache_dir: Path,
    log: Callable[[str], None],
    stop_flag: Optional[Callable[[], bool]] = None,
    auto_threads: bool = True,
    threads: int = 4,
) -> Path:
    if stop_flag and stop_flag():
        raise RuntimeError('[CANCEL] Остановлено пользователем.')

    ready = api.ready_to_use_ticket(series_id, product_id)
    viewer_root = api.viewer_data(series_id, product_id)
    viewer_data = viewer_root.get('viewerData') or {}
    viewer_type = viewer_data.get('__typename') or viewer_data.get('type')

    if viewer_type != 'TextViewerData':
        raise RuntimeError(f'product_id={product_id}: viewerData не TextViewerData, а {viewer_type!r}')

    ats_server_url = viewer_data.get('atsServerUrl') or ''
    meta_secure_url = viewer_data.get('metaSecureUrl') or ''
    contents = viewer_data.get('contentsList') or []

    if not ats_server_url:
        raise RuntimeError(f'product_id={product_id}: пустой atsServerUrl')
    if not contents:
        raise RuntimeError(f'product_id={product_id}: contentsList пуст')

    item = viewer_root.get('item') or {}
    title = item.get('title') or f'product_{product_id}'
    safe_title = safe_name(title)

    product_cache_dir = ensure_dir(cache_dir / f'product_{product_id}')
    _save_json(product_cache_dir / 'viewer_data.json', viewer_root)
    _save_json(product_cache_dir / 'ready_to_use.json', ready)

    if meta_secure_url:
        try:
            meta_url = _build_resource_url(ats_server_url, meta_secure_url)
            meta_payload = api.fetch_json(meta_url)
            _save_json(product_cache_dir / 'meta.json', meta_payload)
            log(f'[OK] Meta получена: pid={product_id}')
        except Exception as e:
            log(f'[WARN] Не удалось скачать meta для pid={product_id}: {e}')

    parts = sorted(
        [p for p in contents if isinstance(p, dict)],
        key=lambda x: (int(x.get('chapterId', 0)), int(x.get('contentId', 0))),
    )

    results = _fetch_parts_parallel(
        api=api,
        parts=parts,
        ats_server_url=ats_server_url,
        log=lambda s: log(f'[OK] pid={product_id} {s[5:]}' if s.startswith('[OK] ') else s),
        stop_flag=stop_flag,
        auto_threads=auto_threads,
        threads=threads,
    )

    full_parts: list[str] = []
    for result in results:
        json_name = f"part_{result['idx']:03d}_ch{result['chapter_id']}_ct{result['content_id']}.json"
        _save_json(product_cache_dir / json_name, result['payload'])
        text = result['text']
        if text:
            full_parts.append(text)

    final_text = '\n\n'.join(x for x in full_parts if x.strip()).strip()


    if not final_text:
        raise RuntimeError(f'product_id={product_id}: итоговый текст пуст')

    out_path = series_dir / f'{safe_title} [pid {product_id}].txt'
    out_path.write_text(final_text, encoding='utf-8-sig')
    log(f'[SAVE] Сохранено: {out_path}')
    return out_path


def list_novel_products_for_picker(
    title_id: str,
    out_dir: str = '',
    on_log: Optional[Callable[[str], None]] = None,
    on_need_login: Optional[Callable[[], None]] = None,
    stop_flag: Optional[Callable[[], bool]] = None,
    wait_continue: Optional[Callable[[], bool]] = None,
) -> list[dict]:
    log = on_log or (lambda *_: None)
    runtime = prepare_series_runtime(
        title_id=title_id,
        out_dir=out_dir,
        on_log=log,
        on_need_login=on_need_login,
        stop_flag=stop_flag,
        wait_continue=wait_continue,
    )
    episode_map_rows, _epmap_path, _created_now = load_episode_rows(
        runtime,
        on_log=log,
        stop_flag=stop_flag,
        sort='desc',
        retries=2,
        use_cache_map=True,
        fallback_to_cache=True,
    )
    if not episode_map_rows:
        raise RuntimeError('Не удалось получить список глав через GraphQL.')
    rows = picker_rows_from_episode_map(episode_map_rows)
    log(f'[OK] Получен список эпизодов: {len(rows)} шт.')
    return rows


def run_novel_parser(
    *,
    title_id: str,
    chapters: Optional[Iterable[str]],
    out_dir: str,
    on_log: Optional[Callable[[str], None]] = None,
    on_need_login: Optional[Callable[[], None]] = None,
    stop_flag: Optional[Callable[[], bool]] = None,
    wait_continue: Optional[Callable[[], bool]] = None,
    auto_threads: bool = True,
    threads: int = 4,
    on_choose_ticket_action: Optional[Callable[[dict], str]] = None,
    delete_cache_after: bool = True,
) -> None:
    log = on_log or (lambda s: None)
    runtime = prepare_series_runtime(
        title_id=title_id,
        out_dir=out_dir,
        on_log=log,
        on_need_login=on_need_login,
        stop_flag=stop_flag,
        wait_continue=wait_continue,
    )

    product_ids = _normalize_product_ids(chapters)
    if not product_ids:
        raise RuntimeError('Не переданы product_id для скачивания.')

    _episode_rows, _epmap_path, _epmap_created_now = load_episode_rows(
        runtime,
        on_log=log,
        stop_flag=stop_flag,
        sort='desc',
        retries=2,
        use_cache_map=True,
        fallback_to_cache=True,
    )

    log(f'[INFO] series_id={runtime.series_id}')
    log(f'[INFO] product_ids={product_ids}')

    cache_dir = ensure_dir(runtime.series_dir / 'cache' / 'novel_text')
    saved_paths: list[Path] = []

    try:
        for idx, product_id in enumerate(product_ids, 1):
            if stop_flag and stop_flag():
                raise RuntimeError('[CANCEL] Остановлено пользователем.')

            url = f'https://page.kakao.com/viewer?product_id={product_id}&series_id={runtime.series_id}'
            log(f'[Ep {idx:03d}] {url}')
            access_ok, _ = ensure_product_access(
                api=runtime.api,
                series_id=runtime.series_id,
                product_id=product_id,
                parser_kind='novel',
                log=log,
                stop_flag=stop_flag,
                chapter_label=f'product_{product_id}',
                on_choose_action=on_choose_ticket_action,
            )
            if not access_ok:
                continue

            saved = _fetch_one_product_text(
                api=runtime.api,
                series_id=runtime.series_id,
                product_id=product_id,
                series_dir=runtime.series_dir,
                cache_dir=cache_dir,
                log=log,
                stop_flag=stop_flag,
                auto_threads=auto_threads,
                threads=threads,
            )
            saved_paths.append(saved)
    finally:
        if delete_cache_after:
            try:
                if runtime.cache_dir.exists():
                    shutil.rmtree(runtime.cache_dir)
                    log(f'[CACHE] Удалена папка кэша: {runtime.cache_dir}')
            except Exception as e:
                log(f'[WARN] Не удалось удалить папку кэша {runtime.cache_dir}: {e}')

    log(f'[DONE] Готово. Сохранено файлов: {len(saved_paths)}')

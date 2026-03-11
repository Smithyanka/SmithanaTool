from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from smithanatool_qt.tabs.parsers.common.parser_defaults import default_thread_count
from smithanatool_qt.tabs.parsers.kakao.manhwa.platform.runner import run_parser
from smithanatool_qt.tabs.parsers.kakao.shared.episodes.map_graphql import (
    picker_rows_from_episode_map,
    refresh_episode_map,
)
from smithanatool_qt.tabs.parsers.kakao.shared.worker.base import BaseInteractiveParserWorker

from smithanatool_qt.tabs.parsers.kakao.shared.runner.bootstrap import prepare_series_runtime

@dataclass
class ManhwaParserConfig:
    title_id: str
    mode: str  # 'number'|'id'|'index'|'ui'
    spec_text: str
    out_dir: str
    min_width: int = 720
    auto_enabled: bool = True
    no_resize_width: bool = True
    target_width: int = 800
    same_dir: bool = False
    stitch_out_dir: Optional[str] = None
    delete_sources: bool = True
    optimize_png: bool = True
    compress_level: int = 6
    strip_metadata: bool = True
    per: int = 12
    zeros: int = 2
    group_by: str = 'count'
    group_max_height: int = 10000
    auto_confirm_purchase: bool = False
    auto_confirm_use_rental: bool = False
    auto_threads: bool = True
    threads: int = default_thread_count()
    cache_episode_map: bool = False
    delete_cache_after: bool = True
    scroll_ms: int = 30000
    by_index_spec: Optional[str] = None


class ManhwaParserWorker(BaseInteractiveParserWorker):
    def _build_auto_concat(self) -> Optional[dict]:
        if not self.cfg.auto_enabled:
            return None
        out_dir = self.cfg.stitch_out_dir or self.cfg.out_dir
        return {
            'per': int(self.cfg.per),
            'same_dir': bool(self.cfg.same_dir),
            'out_dir': out_dir,
            'target_width': 0 if self.cfg.no_resize_width else int(self.cfg.target_width),
            'strip_metadata': bool(self.cfg.strip_metadata),
            'optimize_png': bool(self.cfg.optimize_png),
            'compress_level': int(self.cfg.compress_level),
            'delete_sources': bool(self.cfg.delete_sources),
            'enable': True,
            'auto_threads': bool(self.cfg.auto_threads),
            'threads': int(self.cfg.threads),
            'zeros': int(self.cfg.zeros),
            'group_by': str(self.cfg.group_by),
            'group_max_height': int(self.cfg.group_max_height),
        }

    def run(self) -> None:
        try:
            mode = self.cfg.mode
            title_id = self.cfg.title_id.strip()
            spec = self.cfg.spec_text.strip()
            chapter_spec = None
            chapters: Optional[Iterable[str]] = None
            by_index: Optional[int] = None
            by_index_spec: Optional[str] = None
            runtime = None

            if mode == 'number':
                chapter_spec = spec
            elif mode == 'id':
                chapters = [part.strip() for part in spec.replace(',', ' ').split() if part.strip()]
            elif mode == 'index':
                if (',' in spec) or ('-' in spec):
                    by_index_spec = spec
                else:
                    try:
                        by_index = int(spec)
                    except Exception:
                        self.error.emit("Индекс должен быть числом или диапазоном (например, '1,2' или '7-10').")
                        return
            elif mode == 'ui':
                        try:
                            sid = int(title_id)
                        except Exception:
                            self.error.emit('ID тайтла должен быть числом.')
                            return

                        runtime = prepare_series_runtime(
                            title_id=title_id,
                            out_dir=self.cfg.out_dir,
                            on_log=self._on_log,
                            on_need_login=self._on_need_login,
                            stop_flag=self._stop_flag,
                            wait_continue=self._wait_continue,
                        )
                        self._browser_closed_seen = False

                        if self._stop_event.is_set():
                            return

                        episode_map_rows = refresh_episode_map(
                            sid,
                            self.cfg.out_dir,
                            runtime.cookie_raw,
                            log=self._on_log,
                            stop_flag=self._stop_flag,
                            sort='desc',
                            retries=2,
                            fallback_to_cache=True,
                        ) or []

                        if self._stop_event.is_set():
                            return
                        if not episode_map_rows:
                            self.error.emit('Не удалось получить список эпизодов.')
                            return

                        rows = picker_rows_from_episode_map(episode_map_rows)
                        chapters = self._request_ui_selected_ids(sid, rows)
                        if chapters is None:
                            return
                        if not chapters:
                            self.error.emit('Ничего не выбрано.')
                            return
            else:
                self.error.emit('Неизвестный режим.')
                return

            run_parser(
                title_id=title_id,
                chapter_spec=chapter_spec,
                chapters=chapters,
                out_dir=self.cfg.out_dir,
                on_log=self._on_log,
                on_need_login=self._on_need_login,
                stop_flag=self._stop_flag,
                min_width=int(self.cfg.min_width),
                use_cache_map=bool(self.cfg.cache_episode_map),
                delete_cache_after=bool(self.cfg.delete_cache_after),
                scroll_ms=int(self.cfg.scroll_ms),
                auto_concat=self._build_auto_concat(),
                on_choose_ticket_action=self._confirm_ticket_action,
                by_index=by_index,
                by_index_spec=by_index_spec,
                wait_continue=self._wait_continue,
                runtime=runtime,
            )
        except Exception as err:
            self._emit_exception(err)

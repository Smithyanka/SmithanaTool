from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from smithanatool_qt.tabs.parsers.common.parser_defaults import default_thread_count
from smithanatool_qt.tabs.parsers.kakao.novel.platform.runner import (
    list_novel_products_for_picker,
    run_novel_parser,
)
from smithanatool_qt.tabs.parsers.kakao.shared.worker.base import BaseInteractiveParserWorker


@dataclass
class NovelParserConfig:
    title_id: str
    mode: str  # 'ui' | 'id'
    spec_text: str
    out_dir: str
    auto_threads: bool = True
    threads: int = default_thread_count()
    auto_confirm_purchase: bool = False
    auto_confirm_use_rental: bool = False
    delete_cache_after: bool = True


class NovelParserWorker(BaseInteractiveParserWorker):
    def _handle_browser_closed_logline(self, _text: str) -> bool:
        self.request_stop()
        self.error.emit('Браузер был закрыт')
        return True

    def run(self) -> None:
        try:
            chapters: Optional[Iterable[str]] = None

            if self.cfg.mode == 'id':
                chapters = [s.strip() for s in (self.cfg.spec_text or '').split(',') if s.strip()]
            else:
                try:
                    sid = int(str(self.cfg.title_id).strip())
                except Exception:
                    raise RuntimeError('ID тайтла должен быть числовым series_id.')

                rows = list_novel_products_for_picker(
                    title_id=self.cfg.title_id,
                    out_dir=self.cfg.out_dir,
                    on_log=self._on_log,
                    on_need_login=self._on_need_login,
                    stop_flag=self._stop_flag,
                    wait_continue=self._wait_continue,
                )
                if self._stop_event.is_set():
                    return
                if not rows:
                    raise RuntimeError('Не удалось получить список глав для выбора.')

                chapters = self._request_ui_selected_ids(sid, rows)
                if chapters is None:
                    return
                if not chapters:
                    raise RuntimeError('Ничего не выбрано.')

            run_novel_parser(
                title_id=self.cfg.title_id,
                chapters=chapters,
                out_dir=self.cfg.out_dir,
                on_log=self._on_log,
                on_need_login=self._on_need_login,
                stop_flag=self._stop_flag,
                wait_continue=self._wait_continue,
                auto_threads=bool(self.cfg.auto_threads),
                threads=int(self.cfg.threads),
                on_choose_ticket_action=self._confirm_ticket_action,
                delete_cache_after=bool(self.cfg.delete_cache_after),
            )
        except Exception as err:
            self._emit_exception(err)

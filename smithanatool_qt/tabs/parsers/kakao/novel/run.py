from __future__ import annotations

from PySide6.QtCore import Slot
from PySide6.QtWidgets import QMessageBox

from .worker import NovelParserConfig, NovelParserWorker
from ..shared.run_common import CommonParserRunMixin
from ..shared.tickets.run_mixin import TicketDecisionRunMixin


class NovelTabRunMixin(TicketDecisionRunMixin, CommonParserRunMixin):
    def _collect_cfg(self) -> NovelParserConfig:
        return NovelParserConfig(
            title_id=self.ed_title.text().strip(),
            mode='id' if self.rb_id.isChecked() else 'ui',
            spec_text=self.ed_spec.text().strip(),
            out_dir=self._out_dir or '',
            auto_threads=self.chk_auto_threads.isChecked(),
            threads=int(self.spin_threads.value()),
            auto_confirm_purchase=self.chk_auto_buy.isChecked(),
            auto_confirm_use_rental=self.chk_auto_use_ticket.isChecked(),
            delete_cache_after=True,
        )

    @Slot()
    def _start(self) -> None:
        if not self._out_dir:
            QMessageBox.warning(self, 'Парсер', 'Сначала выберите папку сохранения.')
            return

        self._had_error = False
        self._awaiting_login = False
        self._log('[DEBUG] Запуск парсера новелл Kakao.')
        self._start_worker_common(NovelParserWorker(self._collect_cfg()))

    def _connect_extra_worker_signals(self, worker) -> None:
        worker.error.connect(self._on_error)
        worker.ask_ticket_action.connect(self._on_ask_ticket_action)

    @Slot(str)
    def _on_error(self, msg: str) -> None:
        self._had_error = True
        self._log(f'[ERROR] {msg}')

    def _before_continue(self) -> None:
        self._awaiting_login = False

    def _set_awaiting_login(self, value: bool) -> None:
        self._awaiting_login = value

    def _log_done_if_needed(self) -> None:
        worker = getattr(self, '_worker', None)
        if self._had_error or (worker and getattr(worker, '_saw_done_log', False)):
            return
        self._log('[DONE] Готово.')

    def _set_specific_running_state(self, running: bool) -> None:
        if not running:
            self._awaiting_login = False

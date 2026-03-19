from __future__ import annotations

from PySide6.QtCore import Slot
from PySide6.QtWidgets import QMessageBox

from .worker import ManhwaParserConfig, ManhwaParserWorker
from ..shared.run_common import CommonParserRunMixin
from ..shared.tickets.run_mixin import TicketDecisionRunMixin


class ManhwaTabRunMixin(TicketDecisionRunMixin, CommonParserRunMixin):
    def _current_auto_mode_key(self) -> str:
        idx = int(self.combo_auto_mode.currentIndex())
        return 'count' if idx == 0 else 'height' if idx == 1 else 'smart'

    def _collect_cfg(self) -> ManhwaParserConfig:
        mode = 'number' if self.rb_number.isChecked() else ('id' if self.rb_id.isChecked() else ('index' if self.rb_index.isChecked() else 'ui'))
        return ManhwaParserConfig(
            title_id=self.ed_title.text().strip(),
            mode=mode,
            spec_text=self.ed_spec.text().strip(),
            out_dir=self._out_dir,
            min_width=int(self.spin_minw.value()),
            auto_enabled=self.chk_auto.isChecked(),
            no_resize_width=self.chk_no_resize.isChecked(),
            target_width=int(self.spin_width.value()),
            same_dir=self.chk_same_dir.isChecked(),
            stitch_out_dir=self._stitch_dir or self._out_dir,
            delete_sources=self.chk_delete_sources.isChecked(),
            optimize_png=self.chk_opt.isChecked(),
            compress_level=int(self.spin_comp.value()),
            strip_metadata=self.chk_strip.isChecked(),
            per=int(self.spin_per.value()),
            zeros=int(self.spin_zeros.value()),
            group_by=self._current_auto_mode_key(),
            group_max_height=int(self.spin_max_h.value()),
            smart_height=int(self.spin_smart_height.value()),
            smart_sensitivity=int(self.spin_smart_sensitivity.value()),
            smart_scan_step=int(self.spin_smart_scan_step.value()),
            smart_ignore_borders=int(self.spin_smart_ignore.value()),
            smart_detector='smart',
            auto_confirm_purchase=self.chk_auto_buy.isChecked(),
            auto_confirm_use_rental=self.chk_auto_use_ticket.isChecked(),
            auto_threads=self.chk_auto_threads.isChecked(),
            threads=int(self.spin_threads.value()),
            cache_episode_map=True,
            delete_cache_after=True,
            scroll_ms=int(self.spin_scroll_ms.value()),
        )

    @Slot()
    def _start(self) -> None:
        if not self._out_dir:
            QMessageBox.warning(self, 'Парсер', 'Сначала выберите папку сохранения.')
            return
        self._start_worker_common(ManhwaParserWorker(self._collect_cfg()))

    def _connect_extra_worker_signals(self, worker) -> None:
        worker.error.connect(lambda e: self._log(f'[ERROR] {e}'))
        worker.ask_ticket_action.connect(self._on_ask_ticket_action)

    def _after_stop_requested(self) -> None:
        self._log('[STOP] Останавливаю…')

    def _log_done_if_needed(self) -> None:
        worker = getattr(self, '_worker', None)
        if worker and getattr(worker, '_saw_done_log', False):
            return
        self._log('[DONE] Парсер завершил работу.')

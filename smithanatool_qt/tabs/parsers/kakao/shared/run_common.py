from __future__ import annotations

from PySide6.QtCore import QTimer, Slot

from .episodes.blocking_flow import BlockingEpisodePickerFlowMixin


class CommonParserRunMixin(BlockingEpisodePickerFlowMixin):
    def _start_worker_common(self, worker) -> None:
        self._worker = worker
        self._connect_common_worker_signals(worker)
        self._connect_extra_worker_signals(worker)
        self._set_running(True)
        QTimer.singleShot(0, worker.start)

    def _connect_common_worker_signals(self, worker) -> None:
        worker.need_login.connect(self._on_need_login)
        worker.log.connect(self._log)
        worker.finished.connect(self._on_finished)
        worker.ui_pick_required.connect(self._on_ui_pick_required)

    def _connect_extra_worker_signals(self, worker) -> None:
        pass

    @Slot()
    def _stop(self):
        worker = getattr(self, '_worker', None)
        if worker:
            worker.stop()
        self._after_stop_requested()

    @Slot()
    def _continue(self):
        worker = getattr(self, '_worker', None)
        if not worker:
            return

        self._before_continue()
        self.btn_continue.setEnabled(False)
        self._resume_worker_after_login(worker)

    def _resume_worker_after_login(self, worker) -> None:
        if hasattr(worker, 'continue_after_login'):
            worker.continue_after_login()
        elif hasattr(worker, 'resume_after_login'):
            worker.resume_after_login()

    def _after_stop_requested(self) -> None:
        pass

    def _before_continue(self) -> None:
        pass

    @Slot()
    def _on_need_login(self):
        self._set_awaiting_login(True)
        self.btn_continue.setEnabled(True)

    def _set_awaiting_login(self, value: bool) -> None:
        pass

    @Slot()
    def _on_finished(self):
        self._log_done_if_needed()
        self._worker = None
        self._set_running(False)

    def _log_done_if_needed(self) -> None:
        self._log('[DONE] Готово.')

    def _set_running(self, running: bool):
        self._is_running = running
        self._set_specific_running_state(running)
        self._set_common_running_state(running)

    def _set_common_running_state(self, running: bool) -> None:
        self.btn_stop.setEnabled(running)
        self.btn_continue.setEnabled(False)
        self._refresh_run_enabled()

    def _set_specific_running_state(self, running: bool) -> None:
        pass

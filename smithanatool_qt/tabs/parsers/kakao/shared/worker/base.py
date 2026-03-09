from __future__ import annotations

import threading
from typing import Any, Optional

from PySide6.QtCore import QThread, Signal, Slot

from .waiters import browser_closed_text_if_any, is_browser_closed_logline, wait_event_or_stop


class BaseInteractiveParserWorker(QThread):
    log = Signal(str)
    need_login = Signal()
    error = Signal(str)
    ui_pick_required = Signal(int, object)

    ask_ticket_action = Signal(object)

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self._stop_event = threading.Event()
        self._resume_event = threading.Event()
        self._ticket_action_event = threading.Event()
        self._ticket_action_result: str = 'skip'
        self._ui_pick_event = threading.Event()
        self._ui_selected_ids: Optional[list[str]] = None
        self._ui_pick_cancelled = False
        self._browser_closed_seen = False
        self._saw_done_log = False

    @Slot(object)
    def provide_ui_selected_ids(self, ids: object) -> None:
        try:
            self._ui_selected_ids = [str(x) for x in (ids or [])]
        except Exception:
            self._ui_selected_ids = None
        self._ui_pick_event.set()

    @Slot()
    def cancel_ui_pick(self) -> None:
        self._ui_pick_cancelled = True
        self._ui_pick_event.set()

    @Slot(str)
    def provide_ticket_action_answer(self, ans: str) -> None:
        self._ticket_action_result = str(ans or 'skip')
        self._ticket_action_event.set()

    def request_stop(self) -> None:
        self._stop_event.set()
        self._resume_event.set()
        self._ticket_action_event.set()
        self._ui_pick_event.set()

    @Slot()
    def stop(self) -> None:
        self.request_stop()
        self.log.emit('[STOP] Запрошена остановка.')

    def stop_and_wait(self, timeout_ms: int = 8000) -> bool:
        self.stop()
        if self.isRunning():
            return self.wait(int(timeout_ms))
        return True

    @Slot()
    def continue_after_login(self) -> None:
        self._resume_event.set()

    @Slot()
    def resume_after_login(self) -> None:
        self._resume_event.set()

    def _stop_flag(self) -> bool:
        return self._stop_event.is_set()

    def _wait_continue(self) -> bool:
        return self._resume_event.is_set() or self._stop_event.is_set()

    def _on_need_login(self) -> None:
        self._resume_event.clear()
        self.need_login.emit()

    def _handle_browser_closed_logline(self, _text: str) -> bool:
        self._resume_event.set()
        return True

    def _on_log(self, s: str) -> None:
        text = str(s or '')
        if text.startswith('[DONE]'):
            self._saw_done_log = True
        if not self._browser_closed_seen and is_browser_closed_logline(text):
            self._browser_closed_seen = True
            if self._handle_browser_closed_logline(text):
                return
        self.log.emit(text)

    def _confirm_ticket_action(self, payload: dict[str, Any]) -> str:
        actions = payload.get('actions') or []
        auto_use = bool(getattr(self.cfg, 'auto_confirm_use_rental', False))
        auto_buy = bool(getattr(self.cfg, 'auto_confirm_purchase', False))

        if auto_use:
            for preferred in ('use_free', 'use_rental', 'use_own'):
                if any(isinstance(a, dict) and a.get('key') == preferred for a in actions):
                    self.log.emit(f'[ASK] Выбираю {preferred} (авто).')
                    return preferred
        if auto_buy:
            for preferred in ('buy_rental', 'buy_own'):
                if any(isinstance(a, dict) and a.get('key') == preferred for a in actions):
                    self.log.emit(f'[ASK] Выбираю {preferred} (авто).')
                    return preferred

        self._ticket_action_event.clear()
        self.ask_ticket_action.emit(payload)
        wait_event_or_stop(self._ticket_action_event, self._stop_event)
        if self._stop_event.is_set():
            return 'skip'

        action = str(self._ticket_action_result or 'skip')
        if action != 'skip':
            self.log.emit(f'[OK] Пользователь выбрал действие: {action}.')
        return action

    def _request_ui_selected_ids(
        self,
        series_id: int,
        rows: object,
        *,
        cancel_message: str = '[STOP] Выбор глав отменён пользователем.',
    ) -> Optional[list[str]]:
        self._ui_selected_ids = None
        self._ui_pick_cancelled = False
        self._ui_pick_event.clear()
        self.ui_pick_required.emit(series_id, rows)
        wait_event_or_stop(self._ui_pick_event, self._stop_event)
        if self._stop_event.is_set() or self._ui_pick_cancelled:
            self.log.emit(cancel_message)
            return None
        return [str(x).strip() for x in (self._ui_selected_ids or []) if str(x).strip()]

    def _emit_exception(self, err: BaseException) -> None:
        message = str(err) or ''
        if message.startswith('[CANCEL]'):
            self.log.emit(message)
            return
        friendly = browser_closed_text_if_any(err)
        self.error.emit(friendly or message)

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Slot

from .dialogs import show_ticket_action_dialog


class TicketDecisionRunMixin:
    def _ticket_dialog_parent(self):
        return self

    def _auto_confirm_purchase_enabled(self) -> bool:
        chk = getattr(self, 'chk_auto_buy', None)
        return bool(chk and chk.isChecked())

    def _auto_confirm_use_rental_enabled(self) -> bool:
        chk = getattr(self, 'chk_auto_use_ticket', None)
        return bool(chk and chk.isChecked())

    @staticmethod
    def _coerce_optional_int(value) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except Exception:
            return None

    def _send_ticket_action_answer(self, ans: str) -> None:
        worker = getattr(self, '_worker', None)
        if worker and hasattr(worker, 'provide_ticket_action_answer'):
            worker.provide_ticket_action_answer(str(ans or 'skip'))

    @Slot(object)
    def _on_ask_ticket_action(self, payload) -> None:
        payload = payload if isinstance(payload, dict) else {}
        auto_use = self._auto_confirm_use_rental_enabled()
        auto_buy = self._auto_confirm_purchase_enabled()

        if auto_use or auto_buy:
            actions = payload.get('actions') or []
            answer = 'skip'
            if isinstance(actions, list):
                if auto_use:
                    for preferred in ('use_free', 'use_rental', 'use_own'):
                        if any(isinstance(a, dict) and a.get('key') == preferred for a in actions):
                            answer = preferred
                            break
                if answer == 'skip' and auto_buy:
                    for preferred in ('buy_rental', 'buy_own'):
                        if any(isinstance(a, dict) and a.get('key') == preferred for a in actions):
                            answer = preferred
                            break
        else:
            answer = show_ticket_action_dialog(self._ticket_dialog_parent(), payload)

        self._send_ticket_action_answer(answer)

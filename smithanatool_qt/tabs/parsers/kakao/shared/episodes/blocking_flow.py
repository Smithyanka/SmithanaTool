from __future__ import annotations

from PySide6.QtCore import Slot
from PySide6.QtWidgets import QDialog, QMessageBox


class BlockingEpisodePickerFlowMixin:
    """Общий blocking-flow выбора глав для novel/manhwa.

    Окно открывается только после того, как worker уже прошёл авторизацию
    и полностью подготовил rows для выбора.
    """
    def _show_blocking_episode_picker(self, sid: int, rows: object) -> None:
        try:
            from .picker_dialog import EpisodePickerDialog


            dlg = EpisodePickerDialog(f'ID {sid}', rows, parent=self)
            if dlg.exec() != QDialog.Accepted:
                worker = getattr(self, '_worker', None)
                if worker:
                    worker.cancel_ui_pick()
                return

            ids = dlg.selected_product_ids()
            if not ids:
                QMessageBox.information(self, 'Выбор глав', 'Ничего не выбрано.')
                worker = getattr(self, '_worker', None)
                if worker:
                    worker.cancel_ui_pick()
                return

            worker = getattr(self, '_worker', None)
            if worker:
                worker.provide_ui_selected_ids([str(x) for x in ids])
        except Exception as e:
            QMessageBox.critical(self, 'Выбор глав', f'Ошибка окна выбора глав: {e}')
            worker = getattr(self, '_worker', None)
            if worker:
                worker.cancel_ui_pick()

    @Slot(int, object)
    def _on_ui_pick_required(self, sid: int, rows: object):
        self._show_blocking_episode_picker(sid, rows)

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QRect, QThreadPool
from PySide6.QtWidgets import QMessageBox

from smithanatool_qt.tabs.ai.controllers.entries import (
    EntriesExporterMixin,
    EntriesHandwritingMixin,
    EntriesOcrRunnerMixin,
    EntriesRectHistoryMixin,
    EntriesSelectionSyncMixin,
    RectActionSnapshot,
)
from smithanatool_qt.tabs.ai.store.entries_store import EntriesStore
from smithanatool_qt.tabs.ai.ui.widgets.busy_overlay import BusyOverlay
from smithanatool_qt.tabs.ai.utils.rect_utils import RECT_SORT_LTR_TTB


class AiEntriesController(
    EntriesSelectionSyncMixin,
    EntriesRectHistoryMixin,
    EntriesOcrRunnerMixin,
    EntriesHandwritingMixin,
    EntriesExporterMixin,
):
    """Оркестратор: viewer/right + OCR + оверлей.

    - EntriesStore хранит фрагменты (текст + QRect)
    - entries_ocr_jobs готовит функцию OCR для фона (Yandex/RouterAI)

    Синхронизация выбора (рамка <-> строка):
    - НЕЛЬЗЯ полагаться на "row == index рамки" (пользователь может менять порядок текста).
    - Поэтому мы храним rect каждой строки в QListWidgetItem.setData(Qt.UserRole, QRect).
      При drag&drop данные переезжают вместе со строкой.
    """

    def __init__(self, tab, viewer, right, ai):
        self._label_mode = "visual"
        self.tab = tab
        self.viewer = viewer
        self.right = right
        self.ai = ai

        self._store = EntriesStore()

        self._pool = QThreadPool.globalInstance()
        self._ocr_running = False

        self._ocr_signals = None
        self._ocr_task = None

        # Синхронизация выделений
        self._syncing_selection = False
        self._selected_rect_img: Optional[QRect] = None
        self._selected_entry_uid: Optional[str] = None

        # Режим сортировки рамок и ручной порядок их создания.
        self._rect_sort_mode: str = RECT_SORT_LTR_TTB
        self._manual_rect_orders: Dict[str, Dict[Tuple[int, int, int, int], int]] = {}
        self._manual_rect_order_next: Dict[str, int] = {}

        # История действий с рамками (undo/redo) и последний зафиксированный state.
        self._rect_undo_history: Dict[str, List[RectActionSnapshot]] = {}
        self._rect_redo_history: Dict[str, List[RectActionSnapshot]] = {}
        self._last_rect_states: Dict[str, RectActionSnapshot] = {}

        # Оверлей поверх области просмотра (галереи)
        parent_for_overlay = getattr(self.tab, "host", None) or self.tab
        self._busy_overlay = BusyOverlay(
            parent_for_overlay,
            cover_widgets=[getattr(self.viewer, "preview", None)],
        )

        self._install_selection_sync()
        self._install_right_panel_sync()

    def _install_right_panel_sync(self) -> None:
        try:
            self.right.itemEditedByUid.connect(self.on_item_edited_by_uid)
        except Exception:
            pass
        try:
            self.right.itemDeletedByUid.connect(self.on_item_deleted_by_uid)
        except Exception:
            pass

    def _current_path(self) -> str:
        return getattr(self.viewer.preview, "_current_path", "") or ""

    # -------- events --------
    def on_path_changed(self, path: Optional[str]):
        self.viewer.show_path(path)
        current_path = path or ""
        self._store.ensure_path(current_path)

        rects = self._store.rects(current_path)
        self._ensure_manual_orders(current_path, rects)
        self.viewer.set_rects_img(self._sorted_rects_for_mode(current_path, rects))

        self._store.reorder_entries_by_rects(current_path, self.viewer.rects_img())
        self.right.set_items(self._store.texts(current_path))
        self._ensure_list_item_rect_data(current_path, force=True)
        self._sync_overlay_labels(current_path)

        self._selected_rect_img = None
        self._clear_both_selection()
        self._reset_rect_action_history(current_path)

    def on_rect_added(self, rect_img: QRect):
        current_path = self._current_path()
        before_state = self._last_state_for(current_path)
        self._assign_manual_order(current_path, rect_img)
        self._apply_rect_order(current_path)
        self._commit_rect_action(current_path, before_state)

    def on_rect_deleted(self, idx: int, rect_img: QRect):
        current_path = self._current_path()
        before_state = self._last_state_for(current_path)
        self._store.mark_rect_deleted(current_path, rect_img)
        self._pop_manual_order(current_path, rect_img)

        self._ensure_list_item_rect_data(current_path)
        self._replace_rect_in_list_items(rect_img, None)

        if self._selected_rect_img is not None and rect_img == self._selected_rect_img:
            self._selected_rect_img = None
            self._clear_both_selection()

        self._apply_rect_order(current_path)
        self._commit_rect_action(current_path, before_state)

    def on_rect_changed(self, idx: int, old_rect: QRect, new_rect: QRect):
        current_path = self._current_path()
        before_state = self._last_state_for(current_path)
        self._store.update_rect(current_path, old_rect, new_rect)
        self._move_manual_order(current_path, old_rect, new_rect)

        if self._selected_rect_img is not None and old_rect == self._selected_rect_img:
            self._selected_rect_img = new_rect

        self._ensure_list_item_rect_data(current_path)
        self._replace_rect_in_list_items(old_rect, new_rect)

        self._apply_rect_order(current_path)
        self._commit_rect_action(current_path, before_state)

    # -------- overlay labels / clearing --------
    def _sync_overlay_labels(self, path: str):
        rects = self.viewer.rects_img()

        if self._label_mode == "visual":
            labels: List[str] = []
            for index, rect in enumerate(rects):
                row = self._find_row_in_list_by_rect(rect)
                labels.append(str(row + 1) if row >= 0 else str(index + 1))
            self.viewer.set_labels(labels)
            return

        labels = self._store.labels_for_rects(path, rects, mode=self._label_mode)
        self.viewer.set_labels(labels)

    def clear_rectangles(self):
        current_path = self._current_path()
        rects = self.viewer.rects_img()
        if not rects:
            return

        before_state = self._last_state_for(current_path)

        self._store.clear_rectangles(current_path, rects)
        for rect in rects:
            self._pop_manual_order(current_path, rect)
        self.viewer.clear_overlay()

        self._clear_all_list_item_rect_data()
        self._sync_overlay_labels(current_path)

        self._selected_rect_img = None
        self._clear_both_selection()

        self._commit_rect_action(current_path, before_state)

    def on_item_edited_by_uid(self, uid: str, text: str):
        current_path = self._current_path()
        if uid:
            self._store.set_text_by_uid(current_path, uid, text)
        self._sync_overlay_labels(current_path)
        self._remember_rect_state(current_path)
        self._update_preview_ocr_menu_state(current_path)

    def on_item_deleted_by_uid(self, uid: str):
        current_path = self._current_path()
        if uid:
            self._store.delete_by_uid(current_path, uid)
        self.right.set_items(self._store.texts(current_path))
        self._ensure_list_item_rect_data(current_path, force=True)
        self._sync_overlay_labels(current_path)

        self._selected_rect_img = None
        self._selected_entry_uid = None
        self._clear_both_selection()
        self._remember_rect_state(current_path)
        self._update_preview_ocr_menu_state(current_path)

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QRect

from smithanatool_qt.tabs.ai.store.entries_store import Entry
from smithanatool_qt.tabs.ai.utils.rect_utils import (
    cycle_rect_sort_mode,
    rect_key,
    rect_sort_mode_title,
    sort_rects_by_mode,
)

from .types import RectActionSnapshot, RectKey


class EntriesRectHistoryMixin:
    # -------- utilities / rect history --------
    def _manual_orders_for(self, path: str) -> Dict[Tuple[int, int, int, int], int]:
        return self._manual_rect_orders.setdefault(path or "", {})

    def _manual_next_for(self, path: str) -> int:
        path_key = path or ""
        return self._manual_rect_order_next.setdefault(path_key, 0)

    def _assign_manual_order(self, path: str, rect: QRect) -> int:
        path_key = path or ""
        orders = self._manual_orders_for(path_key)
        key = rect_key(rect)
        if key in orders:
            return int(orders[key])
        next_value = self._manual_next_for(path_key)
        orders[key] = int(next_value)
        self._manual_rect_order_next[path_key] = int(next_value) + 1
        return int(orders[key])

    def _ensure_manual_orders(self, path: str, rects: List[QRect]) -> None:
        for rect in rects or []:
            if rect is None or rect.isNull():
                continue
            self._assign_manual_order(path, rect)

    def _pop_manual_order(self, path: str, rect: QRect) -> Optional[int]:
        if rect is None or rect.isNull():
            return None
        return self._manual_orders_for(path).pop(rect_key(rect), None)

    def _set_manual_order(self, path: str, rect: QRect, order: int) -> None:
        if rect is None or rect.isNull():
            return
        path_key = path or ""
        order = int(order)
        self._manual_orders_for(path_key)[rect_key(rect)] = order
        current_next = self._manual_rect_order_next.get(path_key, 0)
        if order >= current_next:
            self._manual_rect_order_next[path_key] = order + 1

    def _move_manual_order(self, path: str, old_rect: QRect, new_rect: QRect) -> None:
        order = self._pop_manual_order(path, old_rect)
        if order is None:
            order = self._assign_manual_order(path, old_rect)
            self._pop_manual_order(path, old_rect)
        self._set_manual_order(path, new_rect, order)

    def _sorted_rects_for_mode(self, path: str, rects: List[QRect]) -> List[QRect]:
        path_key = path or ""
        self._ensure_manual_orders(path_key, rects)
        orders = self._manual_orders_for(path_key)
        fallback_base = max(orders.values(), default=-1) + 1
        return sort_rects_by_mode(
            rects,
            self._rect_sort_mode,
            manual_order_getter=lambda rect: int(orders.get(rect_key(rect), fallback_base)),
        )

    def _apply_rect_order(self, path: Optional[str] = None, rects: Optional[List[QRect]] = None) -> List[QRect]:
        path_key = path if path is not None else self._current_path()
        rects_to_sort = list(rects if rects is not None else self.viewer.rects_img())
        ordered = self._sorted_rects_for_mode(path_key, rects_to_sort)
        self.viewer.set_rects_img(ordered)
        self._store.reorder_entries_by_rects(path_key, ordered)
        self.right.set_items(self._store.texts(path_key))
        self._ensure_list_item_rect_data(path_key, force=True)

        if self._selected_rect_img is not None:
            self._set_overlay_selected_rect(self._selected_rect_img)

        self._sync_overlay_labels(path_key)
        return ordered

    def _clone_entries(self, entries: List[Entry]) -> List[Entry]:
        return [
            Entry(
                text=(entry.text or ""),
                rect=QRect(entry.rect) if (entry.rect is not None and not entry.rect.isNull()) else None,
                uid=str(getattr(entry, "uid", "")),
            )
            for entry in entries or []
        ]

    def _clone_snapshot(self, snapshot: RectActionSnapshot) -> RectActionSnapshot:
        return RectActionSnapshot(
            overlay_rects=[QRect(rect) for rect in snapshot.overlay_rects],
            entries=self._clone_entries(snapshot.entries),
            manual_orders={key: int(value) for key, value in snapshot.manual_orders.items()},
            manual_next=int(snapshot.manual_next),
            sort_mode=str(snapshot.sort_mode),
        )

    def _capture_rect_state(self, path: Optional[str] = None) -> RectActionSnapshot:
        path_key = path if path is not None else self._current_path()
        return RectActionSnapshot(
            overlay_rects=[QRect(rect) for rect in self.viewer.rects_img()],
            entries=self._clone_entries(self._store.entries(path_key)),
            manual_orders={key: int(value) for key, value in self._manual_orders_for(path_key).items()},
            manual_next=int(self._manual_rect_order_next.get(path_key or "", 0)),
            sort_mode=str(self._rect_sort_mode),
        )

    def _state_signature(self, snapshot: RectActionSnapshot) -> tuple:
        return (
            tuple(rect_key(rect) for rect in snapshot.overlay_rects),
            tuple(
                (
                    str(getattr(entry, "uid", "")),
                    rect_key(entry.rect) if entry.rect is not None else None,
                )
                for entry in snapshot.entries
            ),
            tuple(sorted((tuple(key), int(value)) for key, value in snapshot.manual_orders.items())),
            int(snapshot.manual_next),
            str(snapshot.sort_mode),
        )

    def _states_equal(self, left: RectActionSnapshot, right: RectActionSnapshot) -> bool:
        return self._state_signature(left) == self._state_signature(right)

    def _undo_history_for(self, path: str) -> List[RectActionSnapshot]:
        return self._rect_undo_history.setdefault(path or "", [])

    def _redo_history_for(self, path: str) -> List[RectActionSnapshot]:
        return self._rect_redo_history.setdefault(path or "", [])

    def _last_state_for(self, path: str) -> RectActionSnapshot:
        path_key = path or ""
        state = self._last_rect_states.get(path_key)
        if state is None:
            state = self._capture_rect_state(path_key)
            self._last_rect_states[path_key] = self._clone_snapshot(state)
        return self._clone_snapshot(state)

    def _remember_rect_state(self, path: Optional[str] = None) -> RectActionSnapshot:
        path_key = path if path is not None else self._current_path()
        state = self._capture_rect_state(path_key)
        self._last_rect_states[path_key or ""] = self._clone_snapshot(state)
        return state

    def _reset_rect_action_history(self, path: Optional[str] = None) -> None:
        path_key = path if path is not None else self._current_path()
        self._undo_history_for(path_key).clear()
        self._redo_history_for(path_key).clear()
        self._remember_rect_state(path_key)
        self._update_preview_ocr_menu_state(path_key)

    def _commit_rect_action(self, path: str, before_state: RectActionSnapshot) -> None:
        path_key = path or ""
        after_state = self._capture_rect_state(path_key)
        if self._states_equal(before_state, after_state):
            self._last_rect_states[path_key] = self._clone_snapshot(after_state)
            self._update_preview_ocr_menu_state(path_key)
            return
        self._undo_history_for(path_key).append(self._clone_snapshot(before_state))
        self._redo_history_for(path_key).clear()
        self._last_rect_states[path_key] = self._clone_snapshot(after_state)
        self._update_preview_ocr_menu_state(path_key)

    def _rebind_snapshot_entries(
        self,
        snapshot: RectActionSnapshot,
        current_entries: List[Entry],
    ) -> RectActionSnapshot:
        snap = self._clone_snapshot(snapshot)
        current_by_rect: Dict[RectKey, Entry] = {}
        for entry in current_entries:
            rect = entry.rect
            if rect is None or rect.isNull():
                continue
            current_by_rect[rect_key(rect)] = Entry(
                text=(entry.text or ""),
                rect=QRect(rect),
                uid=str(getattr(entry, "uid", "")),
            )

        snap_rect_keys = {rect_key(rect) for rect in snap.overlay_rects}
        rebound_entries: List[Entry] = []
        seen_uids = set()

        for entry in snap.entries:
            uid = str(getattr(entry, "uid", ""))
            if not uid or uid in seen_uids:
                continue

            rect = QRect(entry.rect) if (entry.rect is not None and not entry.rect.isNull()) else None
            if rect is not None and rect_key(rect) not in snap_rect_keys:
                rect = None

            rebound_entries.append(
                Entry(
                    text=(entry.text or ""),
                    rect=rect,
                    uid=uid,
                )
            )
            seen_uids.add(uid)

        for rect in snap.overlay_rects:
            current = current_by_rect.get(rect_key(rect))
            if current is None:
                continue

            uid = str(getattr(current, "uid", ""))
            if not uid or uid in seen_uids:
                continue

            rebound_entries.append(
                Entry(
                    text=(current.text or ""),
                    rect=QRect(rect),
                    uid=uid,
                )
            )
            seen_uids.add(uid)

        snap.entries = rebound_entries
        return snap

    def _rebind_rect_history_entries(self, path: Optional[str] = None) -> None:
        path_key = path if path is not None else self._current_path()
        current_entries = self._clone_entries(self._store.entries(path_key))

        self._rect_undo_history[path_key or ""] = [
            self._rebind_snapshot_entries(snapshot, current_entries)
            for snapshot in self._undo_history_for(path_key)
        ]
        self._rect_redo_history[path_key or ""] = [
            self._rebind_snapshot_entries(snapshot, current_entries)
            for snapshot in self._redo_history_for(path_key)
        ]

        last_state = self._last_rect_states.get(path_key or "")
        if last_state is not None:
            self._last_rect_states[path_key or ""] = self._rebind_snapshot_entries(last_state, current_entries)

    def _apply_rect_state(self, path: str, snapshot: RectActionSnapshot) -> None:
        path_key = path or ""
        snap = self._clone_snapshot(snapshot)
        self._rect_sort_mode = str(snap.sort_mode)
        self._manual_rect_orders[path_key] = {key: int(value) for key, value in snap.manual_orders.items()}
        self._manual_rect_order_next[path_key] = int(snap.manual_next)

        current_entries = self._clone_entries(self._store.entries(path_key))
        snap_by_uid = {
            str(getattr(entry, "uid", "")): entry
            for entry in snap.entries
            if str(getattr(entry, "uid", ""))
        }
        snap_rect_keys = {rect_key(rect) for rect in snap.overlay_rects}

        merged_entries: List[Entry] = []
        seen_uids = set()

        for current in current_entries:
            uid = str(getattr(current, "uid", ""))
            if uid in seen_uids:
                continue

            snap_entry = snap_by_uid.get(uid) if uid else None
            if snap_entry is not None:
                rect = QRect(snap_entry.rect) if (snap_entry.rect is not None and not snap_entry.rect.isNull()) else None
            else:
                rect = (
                    QRect(current.rect)
                    if (current.rect is not None and not current.rect.isNull() and rect_key(current.rect) in snap_rect_keys)
                    else None
                )

            merged_entries.append(
                Entry(
                    text=(current.text or ""),
                    rect=rect,
                    uid=uid,
                )
            )
            seen_uids.add(uid)

        self._store.replace_entries(path_key, merged_entries)
        self.viewer.set_rects_img([QRect(rect) for rect in snap.overlay_rects])
        self.right.set_items(self._store.texts(path_key))
        self._ensure_list_item_rect_data(path_key, force=True)
        self._selected_rect_img = None
        self._clear_both_selection()
        self._sync_overlay_labels(path_key)
        self._last_rect_states[path_key] = self._clone_snapshot(snap)
        self._update_preview_ocr_menu_state(path_key)

    def _current_sort_tooltip(self) -> str:
        title = rect_sort_mode_title(self._rect_sort_mode)
        return f"Порядок рамок: {title}"

    def _update_preview_ocr_menu_state(self, path: Optional[str] = None) -> None:
        path_key = path if path is not None else self._current_path()
        try:
            self.viewer.preview.set_ocr_menu_state(
                delete_enabled=bool(self.viewer.rects_img()),
                undo_enabled=bool(self._undo_history_for(path_key)),
                redo_enabled=bool(self._redo_history_for(path_key)),
                sort_tooltip=self._current_sort_tooltip(),
            )
        except Exception:
            pass

    def cycle_rect_sort_mode(self) -> str:
        path_key = self._current_path()
        before_state = self._last_state_for(path_key)
        self._rect_sort_mode = cycle_rect_sort_mode(self._rect_sort_mode)
        self._apply_rect_order(path_key)
        self._commit_rect_action(path_key, before_state)
        return rect_sort_mode_title(self._rect_sort_mode)

    def undo_last_action(self) -> None:
        path_key = self._current_path()
        history = self._undo_history_for(path_key)
        if not history:
            self._update_preview_ocr_menu_state(path_key)
            return
        current_state = self._capture_rect_state(path_key)
        prev_state = history.pop()
        self._redo_history_for(path_key).append(self._clone_snapshot(current_state))
        self._apply_rect_state(path_key, prev_state)

    def redo_last_action(self) -> None:
        path_key = self._current_path()
        history = self._redo_history_for(path_key)
        if not history:
            self._update_preview_ocr_menu_state(path_key)
            return
        current_state = self._capture_rect_state(path_key)
        next_state = history.pop()
        self._undo_history_for(path_key).append(self._clone_snapshot(current_state))
        self._apply_rect_state(path_key, next_state)

    # Backward compatibility with the old preview action name.
    def restore_last_rectangles(self) -> None:
        self.undo_last_action()

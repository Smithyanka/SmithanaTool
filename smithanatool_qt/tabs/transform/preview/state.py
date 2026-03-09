from __future__ import annotations

from typing import Optional

from PySide6.QtGui import QImage


class StateMixin:

    # ---- Dirty flags ----
    def is_dirty(self, path: Optional[str] = None) -> bool:
        p = path or getattr(self, "_current_path", None)
        if not p:
            return False
        return bool(getattr(self, "_dirty", {}).get(p, False))

    def _set_dirty(self, path: str, value: bool) -> None:
        if not path:
            return
        old = getattr(self, "_dirty", {}).get(path, False)
        self._dirty[path] = bool(value)
        if old != bool(value):
            try:
                self.dirtyChanged.emit(path, bool(value))
            except Exception:
                pass

    def has_unsaved_changes(self) -> bool:
        return any(getattr(self, "_dirty", {}).values())

    def _recalc_dirty_vs_disk(self, path: str | None = None) -> None:
        p = path or getattr(self, "_current_path", None)
        if not p:
            return
        base = getattr(self, "_loaded_from_disk", {}).get(p)
        cur = getattr(self, "_images", {}).get(p)
        if base is None or cur is None:
            return
        # QImage == compares content + geometry + format
        self._set_dirty(p, not (cur == base))

    def discard_changes(self, path: Optional[str] = None) -> None:
        """Revert image(s) to the disk-loaded base state without writing to disk."""
        paths = [path] if path else list(getattr(self, "_images", {}).keys())
        for p in paths:
            base = getattr(self, "_loaded_from_disk", {}).get(p)
            if base is not None:
                self._images[p] = base.copy()
                self._undo[p] = []
                self._redo[p] = []
                self._set_dirty(p, False)

        try:
            self._update_preview_pixmap()
        except Exception:
            pass
        try:
            self._update_actions_enabled()
        except Exception:
            pass

    # ---- Scroll remember/restore ----
    def _remember_scroll(self, path: str | None) -> None:
        if not path:
            return
        ds = getattr(self, "_display_size", None)
        if not ds or ds.width() <= 0 or ds.height() <= 0:
            return
        vp = self.scroll.viewport()
        hbar = self.scroll.horizontalScrollBar()
        vbar = self.scroll.verticalScrollBar()
        cx = hbar.value() + vp.width() / 2
        cy = vbar.value() + vp.height() / 2
        self._scroll_pos[path] = (
            cx / max(1, int(ds.width())),
            cy / max(1, int(ds.height())),
        )

    def _restore_scroll(self, path: str | None) -> None:
        if not path or path not in getattr(self, "_scroll_pos", {}):
            return
        ds = getattr(self, "_display_size", None)
        if not ds or ds.width() <= 0 or ds.height() <= 0:
            return
        vp = self.scroll.viewport()
        hbar = self.scroll.horizontalScrollBar()
        vbar = self.scroll.verticalScrollBar()
        rx, ry = self._scroll_pos[path]
        new_x = int(rx * int(ds.width()) - vp.width() / 2)
        new_y = int(ry * int(ds.height()) - vp.height() / 2)
        hbar.setValue(max(0, min(hbar.maximum(), new_x)))
        vbar.setValue(max(0, min(vbar.maximum(), new_y)))

    # ---- Cache cleanup ----
    def forget_paths(self, paths: list[str]) -> None:
        if not paths:
            return

        if getattr(self, "_current_path", None) in paths:
            self._current_path = None
            try:
                self._reset_empty_preview("Нет изображения")
            except Exception:
                try:
                    self.label.setText("Нет изображения")
                except Exception:
                    pass

        for p in paths:
            try:
                if getattr(self, "_dirty", {}).get(p, False):
                    self.dirtyChanged.emit(p, False)
            except Exception:
                pass

            if hasattr(self, "_images"):
                self._images.pop(p, None)
            if hasattr(self, "_undo"):
                self._undo.pop(p, None)
            if hasattr(self, "_redo"):
                self._redo.pop(p, None)
            if hasattr(self, "_loaded_from_disk"):
                self._loaded_from_disk.pop(p, None)
            if hasattr(self, "_dirty"):
                self._dirty.pop(p, None)
            if hasattr(self, "_scroll_pos"):
                self._scroll_pos.pop(p, None)

        try:
            self._update_actions_enabled()
            self._update_info_label()
            self.label.update()
        except Exception:
            pass

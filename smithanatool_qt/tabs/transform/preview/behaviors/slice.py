from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List

from PySide6.QtCore import QPoint
from PySide6.QtGui import QImage


class SliceMixin:
    """Slice mode (multi-fragment) behavior.

    Consolidates functionality that was previously split between state_mixin.py and slice_mode.py.
    """

    # ---- public API ----
    def set_slice_mode(self, on: bool, count: Optional[int] = None) -> None:
        self._slice_enabled = bool(on)
        if count is not None:
            self._slice_count = max(2, int(count))

        if self._slice_enabled:
            # slice mode выключает одиночное выделение
            self._sel_active = False
            self._resizing_edge = None
            self._init_slice_bounds()
        else:
            self._drag_boundary_index = None

        self._store_slice_state(getattr(self, "_current_path", None))

        try:
            self.label.update()
        except Exception:
            pass
        if hasattr(self, "_update_actions_enabled"):
            self._update_actions_enabled()
        if hasattr(self, "_update_info_label"):
            self._update_info_label()

    def set_slice_count(self, count: int) -> None:
        self._slice_count = max(2, int(count))
        if self._slice_enabled:
            self._init_slice_bounds()
            try:
                self.label.update()
            except Exception:
                pass
            if hasattr(self, "_update_info_label"):
                self._update_info_label()

        self._store_slice_state(getattr(self, "_current_path", None))

    def set_slice_by(self, by: str) -> None:
        by = str(by).lower()
        self._slice_by = "height" if ("height" in by or "высот" in by) else "count"
        if self._slice_enabled:
            self._init_slice_bounds()
            try:
                self.label.update()
            except Exception:
                pass
            if hasattr(self, "_update_info_label"):
                self._update_info_label()

        self._store_slice_state(getattr(self, "_current_path", None))

    def set_slice_height(self, px: int) -> None:
        self._slice_height_px = max(1, int(px))
        if self._slice_enabled:
            self._init_slice_bounds()
            try:
                self.label.update()
            except Exception:
                pass
            if hasattr(self, "_update_info_label"):
                self._update_info_label()

        self._store_slice_state(getattr(self, "_current_path", None))

    def save_slices(self, out_dir: str, threads: int = 4, auto_threads: bool = True) -> int:
        """Cut current image by _slice_bounds and save fragments in parallel."""
        if not (self._current_path and self._current_path in self._images):
            return 0
        if not self._slice_enabled or not self._slice_bounds or len(self._slice_bounds) < 2:
            return 0

        img: QImage = self._images[self._current_path]
        h, w = img.height(), img.width()
        bounds = list(self._slice_bounds)
        if bounds[0] != 0:
            bounds[0] = 0
        if bounds[-1] != h:
            bounds[-1] = h

        if auto_threads:
            cpu = os.cpu_count() or 4
            threads = max(2, min(8, cpu))

        def _save_one(i: int, y1: int, y2: int) -> bool:
            cut_h = max(1, y2 - y1)
            frag = img.copy(0, y1, w, cut_h)
            base = os.path.splitext(os.path.basename(self._current_path))[0]
            dst = os.path.join(out_dir, f"{base}_{str(i + 1).zfill(2)}.png")
            return bool(frag.save(dst))

        tasks = []
        with ThreadPoolExecutor(max_workers=int(threads)) as ex:
            for i in range(len(bounds) - 1):
                y1, y2 = bounds[i], bounds[i + 1]
                if y2 <= y1:
                    continue
                tasks.append(ex.submit(_save_one, i, int(y1), int(y2)))

            done_ok = 0
            for fut in as_completed(tasks):
                try:
                    if fut.result():
                        done_ok += 1
                except Exception:
                    pass

        return done_ok

    # ---- per-path state ----
    def _sync_slice_count_and_emit(self) -> None:
        n = max(1, len(self._slice_bounds) - 1) if self._slice_bounds else 0
        if n != getattr(self, "_slice_count", n):
            self._slice_count = n
            try:
                self.sliceCountChanged.emit(n)
            except Exception:
                pass

    def _store_slice_state(self, path: Optional[str]) -> None:
        if not path:
            return
        st = {
            "enabled": bool(getattr(self, "_slice_enabled", False)),
            "by": str(getattr(self, "_slice_by", "count")),
            "count": int(getattr(self, "_slice_count", 2)),
            "height_px": int(getattr(self, "_slice_height_px", 2000)),
            "bounds": list(getattr(self, "_slice_bounds", []) or []),
        }
        self._slice_state[path] = st

    def _restore_slice_state(self, path: Optional[str]) -> None:
        if not path:
            return
        st = self._slice_state.get(path)
        img = self._images.get(path)
        if st is None or img is None:
            self._slice_enabled = False
            self._slice_bounds = []
            self._sync_slice_count_and_emit()
            try:
                self._update_preview_pixmap()
            except Exception:
                pass
            return

        self._slice_enabled = bool(st.get("enabled", False))
        self._slice_by = "height" if st.get("by") == "height" else "count"
        self._slice_count = max(2, int(st.get("count", 2)))
        self._slice_height_px = max(1, int(st.get("height_px", 2000)))

        bounds = list(st.get("bounds") or [])
        H = int(img.height())
        bounds = sorted(set(max(0, min(H, int(y))) for y in bounds))
        if not bounds or bounds[0] != 0:
            bounds = [0] + bounds
        if bounds[-1] != H:
            bounds.append(H)

        if len(bounds) >= 3 and any(bounds[i + 1] > bounds[i] for i in range(len(bounds) - 1)):
            self._slice_bounds = bounds
            self._slice_count = max(2, len(self._slice_bounds) - 1)
            try:
                self.sliceCountChanged.emit(int(self._slice_count))
            except Exception:
                pass
        else:
            self._init_slice_bounds()

        try:
            self._update_preview_pixmap()
        except Exception:
            pass

    def get_slice_state(self, path: Optional[str] = None) -> dict:
        p = path or getattr(self, "_current_path", None)
        if not p:
            return {}
        cur = {
            "enabled": bool(getattr(self, "_slice_enabled", False)),
            "by": str(getattr(self, "_slice_by", "count")),
            "count": int(getattr(self, "_slice_count", 2)),
            "height_px": int(getattr(self, "_slice_height_px", 2000)),
            "bounds": list(getattr(self, "_slice_bounds", []) or []),
        }
        return self._slice_state.get(p, cur)

    # ---- geometry helpers ----
    def _init_slice_bounds(self) -> None:
        if not (self._current_path and self._current_path in self._images):
            self._slice_bounds = []
            return

        img: QImage = self._images[self._current_path]
        H = img.height()

        if getattr(self, "_slice_by", "count") == "height":
            step = max(1, int(getattr(self, "_slice_height_px", 2000)))
            bounds = [0]
            y = 0
            while y + step < H:
                y += step
                bounds.append(y)
            bounds.append(H)
            self._slice_bounds = bounds
            self._slice_count = max(2, len(bounds) - 1)
            self._sync_slice_count_and_emit()
            return

        self._rebuild_slice_bounds()

    def _rebuild_slice_bounds(self) -> None:
        if not (self._current_path and self._current_path in self._images):
            self._slice_bounds = []
            return

        img: QImage = self._images[self._current_path]
        H = img.height()
        n = max(2, int(self._slice_count))
        step = H / n

        ys = [0]
        acc = 0.0
        for _ in range(1, n):
            acc += step
            ys.append(int(round(acc)))
        ys.append(H)

        ys2 = [ys[0]]
        for y in ys[1:]:
            if y <= ys2[-1]:
                y = ys2[-1] + 1
            ys2.append(min(y, H))
        ys2[-1] = H

        self._slice_bounds = ys2
        self._sync_slice_count_and_emit()

    def _slice_bounds_on_label(self) -> List[int]:
        ds = getattr(self, "_display_size", None)
        if not ds or ds.height() <= 0 or not (self._current_path and self._current_path in self._images):
            return []
        img = self._images[self._current_path]
        scaled_h = int(ds.height())
        ys = [int(y * scaled_h / max(1, img.height())) for y in self._slice_bounds]

        ys2 = [max(0, min(scaled_h, ys[0]))] if ys else []
        for y in ys[1:]:
            y = max(ys2[-1], min(scaled_h, y))
            ys2.append(y)
        return ys2

    def _boundary_under_cursor(self, pos_label: QPoint, thresh: int = 6) -> Optional[int]:
        ys = self._slice_bounds_on_label()
        if not ys:
            return None
        y0 = self._v_offset_on_label()
        for i, y in enumerate(ys[1:-1], start=1):
            if abs(pos_label.y() - (y0 + y)) <= thresh:
                return i
        return None

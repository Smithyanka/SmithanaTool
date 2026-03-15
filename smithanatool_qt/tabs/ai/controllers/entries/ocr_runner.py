from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QMessageBox

from smithanatool_qt.tabs.ai.jobs.entries_ocr_jobs import OcrConfigError, prepare_ocr_work
from smithanatool_qt.tabs.ai.adapters.runtime_config import build_ocr_runtime_config
from smithanatool_qt.tabs.ai.workers.qt_runnable import OcrSignals, OcrTask


class EntriesOcrRunnerMixin:
    # -------- extract --------
    def _is_path_ocr_running(self, path: Optional[str] = None) -> bool:
        path_key = path if path is not None else self._current_path()
        return bool(getattr(self, "_ocr_running_by_path", {}).get(path_key or "", False))

    def _set_path_ocr_running(self, path: str, busy: bool) -> None:
        path_key = path or ""
        running = getattr(self, "_ocr_running_by_path", None)
        if running is None:
            self._ocr_running_by_path = {}
            running = self._ocr_running_by_path

        if busy:
            running[path_key] = True
        else:
            running.pop(path_key, None)

        self._sync_current_ocr_ui()

    def _sync_current_ocr_ui(self, text: str = "Распознавание...") -> None:
        busy = self._is_path_ocr_running(self._current_path())

        try:
            self.right.btn_extract.setEnabled(not busy)
        except Exception:
            pass
        try:
            self.right.btn_handwriting.setEnabled(not busy)
        except Exception:
            pass

        try:
            if busy:
                self._busy_overlay.set_text(text)
                self._busy_overlay.raise_()
                self._busy_overlay.show()
            else:
                self._busy_overlay.hide()
        except Exception:
            pass

    def _run_ocr_background(
        self,
        *,
        path: str,
        rects_fixed: List[QRect],
        work_fn: Callable[[], Tuple[List[str], str]],
    ) -> None:
        self._set_path_ocr_running(path, True)

        signals = OcrSignals()
        self._ocr_signals_by_path[path or ""] = signals

        def on_done(texts, first_error):
            from shiboken6 import isValid

            if not isValid(self.tab):
                self._ocr_tasks_by_path.pop(path or "", None)
                self._ocr_signals_by_path.pop(path or "", None)
                self._set_path_ocr_running(path, False)
                return

            try:
                self._store.apply_ocr_results(path, rects_fixed, texts)
                self._ensure_manual_orders(path, rects_fixed)
                self._store.reorder_entries_by_rects(path, self._sorted_rects_for_mode(path, rects_fixed))

                if first_error:
                    title_path = path or "<без имени>"
                    QMessageBox.warning(self.tab, "Ошибка распознавания текста", f"{title_path}\n\n{first_error}")

                if path == self._current_path():
                    self._apply_rect_order(path)
                    self._rebind_rect_history_entries(path)
                    self._remember_rect_state(path)
                    self._update_preview_ocr_menu_state(path)
            finally:
                self._ocr_tasks_by_path.pop(path or "", None)
                self._ocr_signals_by_path.pop(path or "", None)
                self._set_path_ocr_running(path, False)

        def on_error(tb):
            from shiboken6 import isValid

            if not isValid(self.tab):
                self._ocr_tasks_by_path.pop(path or "", None)
                self._ocr_signals_by_path.pop(path or "", None)
                self._set_path_ocr_running(path, False)
                return

            try:
                title_path = path or "<без имени>"
                QMessageBox.warning(self.tab, "Ошибка распознавания текста", f"{title_path}\n\n{tb}")
            finally:
                self._ocr_tasks_by_path.pop(path or "", None)
                self._ocr_signals_by_path.pop(path or "", None)
                self._set_path_ocr_running(path, False)

        signals.done.connect(on_done)
        signals.error.connect(on_error)

        task = OcrTask(work_fn, signals)
        self._ocr_tasks_by_path[path or ""] = task
        self._pool.start(task)

    def ai_all(self):
        path = self._current_path()
        if self._is_path_ocr_running(path):
            return

        self._store.ensure_path(path)

        rects = self.viewer.rects_img()
        if not rects:
            QMessageBox.information(self.tab, "Распознать текст", "Нет выделенных областей.")
            return
        cfg = build_ocr_runtime_config(self.right)

        try:
            rects_fixed, work = prepare_ocr_work(
                viewer=self.viewer,
                ai=self.ai,
                rects=list(rects),
                cfg=cfg,
            )
        except OcrConfigError as exc:
            QMessageBox.warning(self.tab, "Ошибка", str(exc))
            return

        self._run_ocr_background(path=path, rects_fixed=rects_fixed, work_fn=work)

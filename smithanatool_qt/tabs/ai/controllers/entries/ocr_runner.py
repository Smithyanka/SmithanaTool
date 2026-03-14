from __future__ import annotations

from typing import Callable, List, Tuple

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QMessageBox

from smithanatool_qt.tabs.ai.jobs.entries_ocr_jobs import OcrConfigError, prepare_ocr_work
from smithanatool_qt.tabs.ai.adapters.runtime_config import build_ocr_runtime_config
from smithanatool_qt.tabs.ai.workers.qt_runnable import OcrSignals, OcrTask


class EntriesOcrRunnerMixin:
    # -------- extract --------
    def _set_ocr_busy(self, busy: bool, text: str = "Распознавание..."):
        self._ocr_running = bool(busy)

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
        self._set_ocr_busy(True, "Распознавание...")

        signals = OcrSignals()
        self._ocr_signals = signals

        def on_done(texts, first_error):
            from shiboken6 import isValid

            if not isValid(self.tab):
                self._ocr_task = None
                self._ocr_signals = None
                self._set_ocr_busy(False)
                return

            try:
                self._store.apply_ocr_results(path, rects_fixed, texts)
                self._ensure_manual_orders(path, rects_fixed)
                self._store.reorder_entries_by_rects(path, self._sorted_rects_for_mode(path, rects_fixed))

                if first_error:
                    QMessageBox.warning(self.tab, "Ошибка распознавания текста", first_error)

                self._apply_rect_order(path)
                self._rebind_rect_history_entries(path)
                self._remember_rect_state(path)
                self._update_preview_ocr_menu_state(path)
            finally:
                self._ocr_task = None
                self._ocr_signals = None
                self._set_ocr_busy(False)

        def on_error(tb):
            from shiboken6 import isValid

            if not isValid(self.tab):
                self._ocr_task = None
                self._ocr_signals = None
                self._set_ocr_busy(False)
                return

            try:
                QMessageBox.warning(self.tab, "Ошибка распознавания текста", tb)
            finally:
                self._ocr_task = None
                self._ocr_signals = None
                self._set_ocr_busy(False)

        signals.done.connect(on_done)
        signals.error.connect(on_error)

        task = OcrTask(work_fn, signals)
        self._ocr_task = task
        self._pool.start(task)

    def ai_all(self):
        if getattr(self, "_ocr_running", False):
            return

        path = self._current_path()
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

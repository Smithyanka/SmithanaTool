from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, QRunnable, Signal


class OcrSignals(QObject):
    done = Signal(list, str)  # texts: List[str], first_error: str
    error = Signal(str)  # traceback


class OcrTask(QRunnable):
    """QRunnable wrapper for OCR background work.
    """

    def __init__(self, work_fn, signals: OcrSignals):
        super().__init__()
        self._work_fn = work_fn
        self.signals = signals

    def run(self):
        try:
            texts, first_error = self._work_fn()
            self.signals.done.emit(texts, first_error or "")
        except Exception:
            self.signals.error.emit(traceback.format_exc())

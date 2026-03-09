from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtGui import QValidator
from PySide6.QtWidgets import QLineEdit, QWidget


class BaseParserPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._out_dir: str = ""
        self._content_splitter_sizes: tuple[int, int] | None = None
        self._external_log_splitter_sizes: tuple[int, int] = (1, 0)
        self._log_sink: Optional[Callable[[str], None]] = None
        self._using_external_log = False

    @staticmethod
    def _is_valid_line_edit(le: QLineEdit) -> bool:
        validator = le.validator()
        if not validator:
            return bool(le.text().strip())

        pos = 0
        state, _, _ = validator.validate(le.text(), pos)
        return state == QValidator.Acceptable

    def _apply_splitter_sizes(self) -> None:
        splitter = getattr(self, "splitter", None)
        if splitter is None:
            return

        splitter.setChildrenCollapsible(True)
        if self._using_external_log:
            splitter.setSizes(list(self._external_log_splitter_sizes))
        elif self._content_splitter_sizes is not None:
            splitter.setSizes(list(self._content_splitter_sizes))

    def configure_panel_sizes(
        self,
        content_sizes: tuple[int, int] | list[int] | None = None,
        external_log_sizes: tuple[int, int] | list[int] | None = None,
    ) -> None:
        if content_sizes is not None:
            self._content_splitter_sizes = (int(content_sizes[0]), int(content_sizes[1]))
        if external_log_sizes is not None:
            self._external_log_splitter_sizes = (int(external_log_sizes[0]), int(external_log_sizes[1]))
        self._apply_splitter_sizes()

    def set_log_sink(self, sink: Optional[Callable[[str], None]]) -> None:
        self._log_sink = sink
        self._using_external_log = sink is not None

        local_log_panel = getattr(self, "_log_panel", None)
        if local_log_panel is not None:
            local_log_panel.setVisible(not self._using_external_log)

        self._apply_splitter_sizes()

    def _log(self, message: str) -> None:
        if callable(self._log_sink):
            self._log_sink(message)

    def get_out_dir(self) -> str:
        return (self._out_dir or "").strip()

    def can_close(self) -> bool:
        return self._worker is None

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QTextEdit,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
    QMessageBox,
)


from smithanatool_qt.tabs.parsers.kakao.shared.auth.session import delete_session, get_session_path

from html import escape as _html_escape

class SharedLogPanel(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._get_out_dir: Optional[Callable[[], str]] = None
        self._append_log: Optional[Callable[[str], None]] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 10, 0)
        layout.setSpacing(6)

        layout.addWidget(QLabel("Лог:"))

        self.text_edit = QTextEdit(self)
        self.text_edit.setReadOnly(True)
        layout.addWidget(self.text_edit, 1)

        self.btn_clear = QPushButton("Очистить лог", self)
        self.btn_delete_session = QPushButton("Удалить сессию", self)

        self.lbl_session_hint = QLabel(
            "С течением времени срок сессии может истечь.\n"
            "Если главу не удаётся скачать, то удалите сессию и авторизуйтесь заново.",
            self,
        )
        self.lbl_session_hint.setWordWrap(True)
        self.lbl_session_hint.setTextFormat(Qt.PlainText)
        self.lbl_session_hint.setProperty("role", "hint")
        self.lbl_session_hint.setMinimumWidth(600)
        self.lbl_session_hint.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(6)
        actions.addWidget(self.lbl_session_hint, 1)
        actions.addStretch(1)
        actions.addWidget(self.btn_delete_session)
        actions.addWidget(self.btn_clear)
        layout.addLayout(actions)

        self.btn_clear.clicked.connect(self.text_edit.clear)
        self.btn_delete_session.clicked.connect(self._delete_session)

    def set_session_context(
        self,
        get_out_dir: Optional[Callable[[], str]],
    ) -> None:
        self._get_out_dir = get_out_dir

    def append_log(self, s: str) -> None:
        msg = _html_escape(s)
        color = self._color_for(s)
        self.text_edit.append(f'<span style="color:{color}">{msg}</span>')

    def _color_for(self, s: str) -> str:
        if s.startswith("[ERROR]") or s.startswith("[CANCEL]"):
            return "#d22"
        if s.startswith("[WARN]"):
            return "#e8a400"
        if s.startswith("[ASK]"):
            return "#a0a"
        if s.startswith("[STOP]"):
            return "#777"
        if s.startswith("[DONE]"):
            return "#06c"
        if s.startswith("[LOGIN]"):
            return "#c60"
        if s.startswith("[INFO]") or s.startswith("[OK]"):
            return "#0a0"
        if s.startswith("[AUTO]"):
            return "#08c"
        if s.startswith("[DEBUG]") or s.startswith("[SKIP]"):
            return "#888"
        if s.startswith("[Загрузка]"):
            return "#fa0"
        return "#888"

    def _log(self, message: str) -> None:
        self.append_log(message)

    @Slot()
    def _delete_session(self) -> None:
        out_dir = self._get_out_dir() if callable(self._get_out_dir) else ""
        out_dir = (out_dir or "").strip()

        if not out_dir:
            QMessageBox.information(
                self,
                "Удалить сессию",
                "Сначала выберите папку сохранения — там хранится файл сессии kakao_auth.json.",
            )
            return

        session_path = get_session_path(out_dir)
        if not session_path.exists():
            QMessageBox.information(
                self,
                "Удалить сессию",
                f"Файл сессии не найден:\n{session_path}",
            )
            return

        ans = QMessageBox.question(
            self,
            "Подтверждение",
            f"Удалить файл сессии?\n\n{session_path}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            return

        ok = delete_session(out_dir)
        if ok:
            self._log(f"[OK] Удалена сессия: {session_path}")
            QMessageBox.information(self, "Удалить сессию", "Файл сессии удалён.")
        else:
            self._log(f"[WARN] Не удалось удалить сессию: {session_path}")
            QMessageBox.warning(self, "Удалить сессию", "Не удалось удалить файл сессии.")
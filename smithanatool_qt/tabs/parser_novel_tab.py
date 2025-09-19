
from __future__ import annotations
import os, re, subprocess, sys
from html import escape as _html_escape

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QLabel, QLineEdit, QTextEdit, QPushButton,
    QSplitter, QRadioButton, QButtonGroup, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt, Slot, QTimer

from .novel_worker import NovelParserWorker, NovelParserConfig

def _open_in_explorer(path: str):
    if not path:
        return
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore
        elif sys.platform == "darwin":
            subprocess.check_call(["open", path])
        else:
            subprocess.check_call(["xdg-open", path])
    except Exception:
        pass

class ParserNovelTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: NovelParserWorker | None = None
        self._out_dir: str = ""

        layout = QHBoxLayout(self); layout.setContentsMargins(8,8,8,8); layout.setSpacing(6)
        splitter = QSplitter(Qt.Horizontal, self); layout.addWidget(splitter)

        # LEFT: controls
        left = QWidget(); gl = QGridLayout(left)
        gl.setHorizontalSpacing(4)
        gl.setVerticalSpacing(9)
        gl.setContentsMargins(8, 8, 8, 20)
        gl.setColumnStretch(0, 0)
        gl.setColumnStretch(1, 1)
        gl.setColumnStretch(2, 0)
        row = 0

        gl.addWidget(QLabel("ID тайтла:"), row, 0, 1, 1, Qt.AlignLeft)
        self.ed_title = QLineEdit(); self.ed_title.setPlaceholderText("например: 123456")
        gl.addWidget(self.ed_title, row, 1, 1, 2); row += 1

        # Mode
        gl.addWidget(QLabel("Режим:"), row, 0)
        self.rb_number = QRadioButton("По номеру"); self.rb_number.setChecked(True)
        self.rb_id = QRadioButton("По ID")
        mbox = QHBoxLayout(); mbox.setContentsMargins(0,0,0,0); mbox.setSpacing(6)
        mbox.addWidget(self.rb_number); mbox.addWidget(self.rb_id); mbox.addStretch(1)
        gl.addLayout(mbox, row, 1, 1, 2); row += 1

        # Spec fields
        self.lbl_spec = QLabel("Глава/ы")
        self.ed_spec = QLineEdit(); self.ed_spec.setPlaceholderText("напримпер: 1-5,8 или 3")  # number mode
        gl.addWidget(self.lbl_spec, row, 0)
        gl.addWidget(self.ed_spec, row, 1, 1, 2); row += 1

        # Volume filter (optional)
        self.lbl_vol = QLabel("Том(а):")
        self.ed_vol = QLineEdit(); self.ed_vol.setPlaceholderText("например: 1,3-5")
        gl.addWidget(self.lbl_vol, row, 0)
        gl.addWidget(self.ed_vol, row, 1, 1, 2); row += 1

                # Output dir (как в манхве)
        gl.addWidget(QLabel("Папка сохранения:"), row, 0, Qt.AlignLeft)
        self.btn_pick_out = QPushButton("Выбрать папку…")
        self.lbl_out = QLabel("— не выбрано —"); self.lbl_out.setStyleSheet("color:#a00")
        from PySide6.QtWidgets import QSizePolicy
        self.btn_pick_out.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.lbl_out.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        hl = QHBoxLayout(); hl.setContentsMargins(0,0,0,0); hl.setSpacing(6)
        hl.addWidget(self.btn_pick_out); hl.addWidget(self.lbl_out, 1)
        gl.addLayout(hl, row, 1, 1, 2); row += 1
        # RIGHT: log
        right = QWidget(); vr = QVBoxLayout(right); vr.setContentsMargins(8,8,8,8); vr.setSpacing(8)
        vr.addWidget(QLabel("Лог:"))
        self.txt_log = QTextEdit(); self.txt_log.setReadOnly(True)
        vr.addWidget(self.txt_log, 1)
        self.btn_clear = QPushButton("Очистить лог")
        al = QHBoxLayout(); al.setContentsMargins(0,0,0,0); al.setSpacing(6); al.addStretch(1); al.addWidget(self.btn_clear); vr.addLayout(al)

        splitter.addWidget(left); splitter.addWidget(right); splitter.setSizes([520, 760])

                # Run controls + Open folder (как в манхве)
        self.btn_run = QPushButton("Запустить"); self.btn_run.setEnabled(False)
        self.btn_stop = QPushButton("Остановить")
        self.btn_continue = QPushButton("Продолжить после входа"); self.btn_continue.setEnabled(False)
        self.btn_open_dir = QPushButton("Открыть папку"); self.btn_open_dir.setEnabled(False)
        rl = QHBoxLayout(); rl.setContentsMargins(0,0,0,0); rl.setSpacing(6)
        rl.addStretch(1)
        rl.addWidget(self.btn_open_dir)
        rl.addWidget(self.btn_continue)
        rl.addWidget(self.btn_stop)
        rl.addWidget(self.btn_run)
        gl.addLayout(rl, row, 0, 1, 3)
        row += 1
        gl.setRowStretch(row, 1)

        # wiring
        self.btn_pick_out.clicked.connect(self._pick_out)
        self.btn_open_dir.clicked.connect(self._open_out_dir)
        self.btn_clear.clicked.connect(lambda: self.txt_log.clear())
        self.btn_run.clicked.connect(self._start)
        self.btn_stop.clicked.connect(self._stop)
        self.btn_continue.clicked.connect(self._continue)
        self.rb_number.toggled.connect(self._update_mode)

        self._update_mode()

    # ---------- UI state ----------
    def _update_mode(self):
        if self.rb_id.isChecked():
            self.lbl_spec.setText("ViewerID:")
            self.ed_spec.setPlaceholderText("например: 123456789,987654321")
            self.lbl_vol.setEnabled(False); self.ed_vol.setEnabled(False)
        else:
            self.lbl_spec.setText("Глава/ы:")
            self.ed_spec.setPlaceholderText("например: 1,2, 5-7")
            self.lbl_vol.setEnabled(True); self.ed_vol.setEnabled(True)

    def _append_log(self, s: str):
        msg = _html_escape(s)
        color = "#888"
        if s.startswith("[ERROR]"):
            color = "#d22"
        elif s.startswith("[WARN]"):
            color = "#e8a400"
        elif s.startswith("[OK]"):
            color = "#0a0"
        elif s.startswith("[DONE]"):
            color = "#06c"
        elif s.startswith("[AUTO]"):
            color = "#08c"
        elif s.startswith("[INFO]"):
            color = "#0a0"
        elif s.startswith("[DEBUG]") or s.startswith("[SKIP]"):
            color = "#888"
        elif s.startswith("[Загрузка]"):
            color = "#fa0"
        self.txt_log.append(f'<span style="color:{color}">{msg}</span>')

    # ---------- Actions ----------
    @Slot()
    def _pick_out(self):
        dlg = QFileDialog(self, "Выберите папку сохранения")
        dlg.setFileMode(QFileDialog.Directory)
        if dlg.exec():
            paths = dlg.selectedFiles()
            if paths:
                self._out_dir = paths[0]
                if hasattr(self, "lbl_out"):
                    self.lbl_out.setText(self._out_dir)
                    self.lbl_out.setStyleSheet("color:#0a0")
                self.btn_run.setEnabled(True)
                if hasattr(self, "btn_open_dir"):
                    self.btn_open_dir.setEnabled(True)

    @Slot()
    def _open_out_dir(self):
        if self._out_dir:
            _open_in_explorer(self._out_dir)

    def _collect_cfg(self) -> NovelParserConfig:
        mode = "id" if self.rb_id.isChecked() else "number"
        return NovelParserConfig(
            title_id=self.ed_title.text().strip(),
            mode=mode,
            spec_text=self.ed_spec.text().strip(),
            out_dir=self._out_dir or "",
            volume_spec=self.ed_vol.text().strip() or None,
            min_width=720,
        )

    @Slot()
    def _start(self):
        if not self._out_dir:
            QMessageBox.warning(self, "Парсер", "Сначала выберите папку сохранения.")
            return
        cfg = self._collect_cfg()
        self.txt_log.clear()
        self._append_log("[DEBUG] Запуск парсера новелл Kakao.")
        self._worker = NovelParserWorker(cfg)
        self._worker.log.connect(self._append_log)
        self._worker.need_login.connect(lambda: self._append_log("[AUTO] Требуется вход на сайте. Войдите в браузере, затем нажмите 'Продолжить после входа'."))
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_finished)
        QTimer.singleShot(0, self._worker.start)
        self._set_running(True)

    @Slot()
    def _stop(self):
        if self._worker:
            self._worker.stop()
            self._append_log("[WARN] Остановка по запросу.")

    @Slot()
    def _continue(self):
        if self._worker:
            self._worker.continue_after_login()
            self._append_log("[AUTO] Продолжение после входа.")

    def _on_error(self, msg: str):
        self._append_log(f"[ERROR] {msg}")
        self._set_running(False)

    def _on_finished(self):
        self._append_log("[DONE] Готово.")
        self._set_running(False)
        QTimer.singleShot(0, lambda: setattr(self, "_worker", None))

    def _set_running(self, running: bool):
        self.btn_run.setEnabled(not running and bool(self._out_dir))
        self.btn_stop.setEnabled(running)
        self.btn_continue.setEnabled(running)

    def can_close(self) -> bool:
        return self._worker is None

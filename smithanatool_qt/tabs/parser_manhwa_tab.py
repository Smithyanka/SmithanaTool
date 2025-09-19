
from __future__ import annotations
from typing import Optional
import os, sys, subprocess
from html import escape as _html_escape

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QLabel, QLineEdit, QTextEdit, QPushButton,
    QSplitter, QRadioButton, QButtonGroup, QFileDialog, QGroupBox, QSpinBox, QCheckBox, QMessageBox,
    QSizePolicy
)
from PySide6.QtCore import Qt, Slot, QTimer

from .manhwa_worker import ManhwaParserWorker, ParserConfig

def _open_in_explorer(path: str):
    try:
        if sys.platform.startswith('win'):
            os.startfile(path)  # type: ignore
        elif sys.platform.startswith('darwin'):
            subprocess.Popen(['open', path])
        else:
            subprocess.Popen(['xdg-open', path])
    except Exception:
        pass

class ParserManhwaTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: Optional[ManhwaParserWorker] = None

        layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal, self)
        layout.addWidget(splitter)

        # LEFT: controls
        left = QWidget()
        gl = QGridLayout(left)
        gl.setHorizontalSpacing(4)
        gl.setVerticalSpacing(9)
        gl.setContentsMargins(8, 8, 8, 20)
        gl.setColumnStretch(0, 0)  # колонка с метками не растягивается
        gl.setColumnStretch(1, 1)  # поля тянут макет
        gl.setColumnStretch(2, 0)

        row = 0
        gl.addWidget(QLabel("ID тайтла:"), row, 0, 1, 1, Qt.AlignLeft)
        self.ed_title = QLineEdit(); self.ed_title.setPlaceholderText("например: 123456")
        gl.addWidget(self.ed_title, row, 1, 1, 2); row += 1

        # Mode
        gl.addWidget(QLabel("Режим:"), row, 0)
        self.rb_number = QRadioButton("По номеру"); self.rb_number.setChecked(True)
        self.rb_id = QRadioButton("По ID")
        self.rb_index = QRadioButton("По индексу")
        mode_box = QHBoxLayout(); mode_box.setContentsMargins(0,0,0,0); mode_box.setSpacing(6)
        mode_box.addWidget(self.rb_number); mode_box.addWidget(self.rb_id); mode_box.addWidget(self.rb_index); mode_box.addStretch(1)
        gl.addLayout(mode_box, row, 1, 1, 2); row += 1

        self.mode_group = QButtonGroup(self)
        for rb in (self.rb_number, self.rb_id, self.rb_index):
            self.mode_group.addButton(rb)

        # Spec label + field
        self.lbl_spec = QLabel("Глава/ы:")
        gl.addWidget(self.lbl_spec, row, 0)
        self.ed_spec = QLineEdit(); self.ed_spec.setPlaceholderText("например: 1,2,5-7")
        gl.addWidget(self.ed_spec, row, 1, 1, 2); row += 1

        # Save dir
        gl.addWidget(QLabel("Папка сохранения:"), row, 0, Qt.AlignLeft)
        self.btn_pick_out = QPushButton("Выбрать папку…")
        self.lbl_out = QLabel("— не выбрано —"); self.lbl_out.setStyleSheet("color:#a00")
        self.btn_pick_out.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.lbl_out.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        hl = QHBoxLayout(); hl.setContentsMargins(0,0,0,0); hl.setSpacing(6)
        hl.addWidget(self.btn_pick_out); hl.addWidget(self.lbl_out, 1)
        gl.addLayout(hl, row, 1, 1, 2); row += 1

        # Min width
        gl.addWidget(QLabel("Мин. ширина (px):"), row, 0)
        self.spin_minw = QSpinBox(); self.spin_minw.setRange(0, 5000); self.spin_minw.setValue(720)
        gl.addWidget(self.spin_minw, row, 1); row += 1

        # Run controls + Open folder
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
        gl.addLayout(rl, row, 0, 1, 3); row += 1

        # Auto concat group
        grp = QGroupBox("Автосклейка")
        v = QVBoxLayout(grp)
        self.chk_auto = QCheckBox("Включить автосклейку"); self.chk_auto.setChecked(True)
        v.addWidget(self.chk_auto)

        rowa = QGridLayout(); v.addLayout(rowa)
        r = 0
        self.chk_no_resize = QCheckBox("Не изменять ширину"); self.chk_no_resize.setChecked(True)
        rowa.addWidget(self.chk_no_resize, r, 0, 1, 2); r += 1
        rowa.addWidget(QLabel("Ширина:"), r, 0); self.spin_width = QSpinBox(); self.spin_width.setRange(50, 20000); self.spin_width.setValue(800); rowa.addWidget(self.spin_width, r, 1); r += 1

        self.chk_same_dir = QCheckBox("Сохранять в той же папке, где и исходники"); rowa.addWidget(self.chk_same_dir, r, 0, 1, 2); r += 1
        self.chk_same_dir.setChecked(True);

        rowa.addWidget(QLabel("Папка для склеек:"), r, 0)
        self.btn_pick_stitch = QPushButton("Выбрать…")
        self.lbl_stitch_dir = QLabel("— не выбрано —")
        self.lbl_stitch_dir.setStyleSheet("color:#a00")

        self.btn_pick_stitch.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.lbl_stitch_dir.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        hl2 = QHBoxLayout(); hl2.setContentsMargins(0,0,0,0); hl2.setSpacing(6)
        hl2.addWidget(self.btn_pick_stitch); hl2.addWidget(self.lbl_stitch_dir, 1)
        rowa.addLayout(hl2, r, 1); r += 1

        self.chk_delete = QCheckBox("Удалять исходники после склейки"); self.chk_delete.setChecked(True); rowa.addWidget(self.chk_delete, r, 0, 1, 2); r += 1

        # PNG options
        rowa.addWidget(QLabel("Опции PNG:"), r, 0); r += 1
        self.chk_opt = QCheckBox("Оптимизировать PNG"); self.chk_opt.setChecked(True)
        self.chk_strip = QCheckBox("Удалять метаданные"); self.chk_strip.setChecked(True)
        self.spin_comp = QSpinBox(); self.spin_comp.setRange(0, 9); self.spin_comp.setValue(6)
        hl3 = QHBoxLayout(); hl3.setContentsMargins(0,0,0,0); hl3.setSpacing(6)
        hl3.addWidget(self.chk_opt); hl3.addWidget(QLabel("Уровень сжатия:")); hl3.addWidget(self.spin_comp); hl3.addWidget(self.chk_strip); hl3.addStretch(1)
        v.addLayout(hl3)

        # per
        hl4 = QHBoxLayout(); hl4.setContentsMargins(0,0,0,0); hl4.setSpacing(6)
        hl4.addWidget(QLabel("По сколько клеить:"))
        self.spin_per = QSpinBox(); self.spin_per.setRange(1, 999); self.spin_per.setValue(12)
        hl4.addWidget(self.spin_per); hl4.addStretch(1)
        v.addLayout(hl4)

        gl.addWidget(grp, row, 0, 1, 3); row += 1

        gl.setRowStretch(row, 1)

        # RIGHT: log
        right = QWidget()
        vr = QVBoxLayout(right); vr.setContentsMargins(8,8,8,8); vr.setSpacing(8)
        vr.addWidget(QLabel("Лог:"))
        self.txt_log = QTextEdit(); self.txt_log.setReadOnly(True)
        vr.addWidget(self.txt_log, 1)
        self.btn_clear = QPushButton("Очистить лог")
        al = QHBoxLayout(); al.setContentsMargins(0,0,0,0); al.setSpacing(6)
        al.addStretch(1); al.addWidget(self.btn_clear); vr.addLayout(al)

        splitter.addWidget(left); splitter.addWidget(right); splitter.setSizes([520, 760])

        # Wiring
        self.btn_pick_out.clicked.connect(self._pick_out)
        self.chk_auto.toggled.connect(self._update_auto_enabled)
        self.chk_no_resize.toggled.connect(self._update_no_resize)
        self.chk_same_dir.toggled.connect(self._update_same_dir)
        self.btn_pick_stitch.clicked.connect(self._pick_stitch_dir)
        self.btn_run.clicked.connect(self._start)
        self.btn_stop.clicked.connect(self._stop)
        self.btn_continue.clicked.connect(self._continue)
        self.btn_open_dir.clicked.connect(self._open_out_dir)
        self.btn_clear.clicked.connect(lambda: self.txt_log.clear())
        self.rb_number.toggled.connect(self._update_mode)
        self.rb_id.toggled.connect(self._update_mode)
        self.rb_index.toggled.connect(self._update_mode)

        self._update_auto_enabled()
        self._update_no_resize()
        self._update_same_dir()
        self._update_mode()

        self._out_dir = ""
        self._stitch_dir = ""

    # ---------- UI helpers ----------
    @Slot()
    def _pick_out(self):
        d = QFileDialog.getExistingDirectory(self, "Папка сохранения")
        if d:
            self._out_dir = d
            self.lbl_out.setText(d)
            self.lbl_out.setStyleSheet("color:#080")
            self.btn_run.setEnabled(True)
            self.btn_open_dir.setEnabled(True)

    @Slot()
    def _open_out_dir(self):
        if self._out_dir:
            _open_in_explorer(self._out_dir)

    @Slot()
    def _pick_stitch_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Папка для склеек")
        if d:
            self._stitch_dir = d
            self.lbl_stitch_dir.setText(d)
            self.lbl_stitch_dir.setStyleSheet("color:#080")

    def _update_auto_enabled(self):
        on = self.chk_auto.isChecked()
        for w in [self.chk_no_resize, self.spin_width, self.chk_same_dir, self.btn_pick_stitch, self.chk_delete, self.chk_opt, self.spin_comp, self.chk_strip, self.spin_per]:
            w.setEnabled(on)
        self._update_same_dir()
        self._update_no_resize()

    def _update_no_resize(self):
        self.spin_width.setEnabled(self.chk_auto.isChecked() and not self.chk_no_resize.isChecked())

    def _update_same_dir(self):
        self.btn_pick_stitch.setEnabled(self.chk_auto.isChecked() and not self.chk_same_dir.isChecked())

    def _update_mode(self):
        if self.rb_number.isChecked():
            self.lbl_spec.setText("Глава(ы):")
            self.ed_spec.setPlaceholderText("например: 1,2,5-7")
        elif self.rb_id.isChecked():
            self.lbl_spec.setText("Viewer ID:")
            self.ed_spec.setPlaceholderText("например: 12801928, 12999192")
        else:
            self.lbl_spec.setText("Индекс:")
            self.ed_spec.setPlaceholderText("например: -1, 1")

    def _collect_cfg(self) -> ParserConfig:
        mode = "number" if self.rb_number.isChecked() else ("id" if self.rb_id.isChecked() else "index")
        return ParserConfig(
            title_id=self.ed_title.text().strip(),
            mode=mode,
            spec_text=self.ed_spec.text().strip(),
            out_dir=self._out_dir,
            min_width=int(self.spin_minw.value()),
            auto_enabled=self.chk_auto.isChecked(),
            no_resize_width=self.chk_no_resize.isChecked(),
            target_width=int(self.spin_width.value()),
            same_dir=self.chk_same_dir.isChecked(),
            stitch_out_dir=self._stitch_dir or self._out_dir,
            delete_sources=self.chk_delete.isChecked(),
            optimize_png=self.chk_opt.isChecked(),
            compress_level=int(self.spin_comp.value()),
            strip_metadata=self.chk_strip.isChecked(),
            per=int(self.spin_per.value()),
        )

    def _append_log(self, s: str):
        # Цветные логи
        msg = _html_escape(s)
        color = "#888"
        if s.startswith("[ERROR]"):
            color = "#d22"
        elif s.startswith("[ASK]"):
            color = "#a0a"
        elif s.startswith("[STOP]"):
            color = "#777"
        elif s.startswith("[DONE]"):
            color = "#06c"
        elif s.startswith("[LOGIN]"):
            color = "#c60"
        elif s.startswith("[INFO]"):
            color = "#0a0"
        elif s.startswith("[OK]"):
            color = "#0a0"
        elif s.startswith("[AUTO]"):
            color = "#08c"
        elif s.startswith("[DEBUG]"):
            color = "#888"
        elif s.startswith("[SKIP]"):
            color = "#888"
        elif s.startswith("[Загрузка]"):
            color = "#fa0"
        self.txt_log.append(f'<span style="color:{color}">{msg}</span>')

    # ---------- Run/Stop/Continue ----------
    @Slot()
    def _start(self):
        if not self._out_dir:
            QMessageBox.warning(self, "Парсер", "Сначала выберите папку сохранения.")
            return
        cfg = self._collect_cfg()
        self._worker = ManhwaParserWorker(cfg)
        self._worker.log.connect(self._append_log)
        self._worker.error.connect(lambda e: self._append_log(f"[ERROR] {e}"))
        self._worker.need_login.connect(self._on_need_login)
        self._worker.finished.connect(self._on_finished)
        # Стартуем поток внутри воркера (он сам грамотно выйдет по finished)
        self._worker.move_to_thread_and_start()
        self._set_running(True)

    @Slot()
    def _stop(self):
        if self._worker:
            self._worker.stop()
            self._append_log("[STOP] Останавливаю…")

    @Slot()
    def _continue(self):
        if self._worker:
            self._worker.resume_after_login()
            self.btn_continue.setEnabled(False)

    def _on_need_login(self):
        self._append_log("[LOGIN] Открылся браузер. Войдите, потом нажмите «Продолжить после входа».")
        self.btn_continue.setEnabled(True)

    def _on_finished(self):
        self._append_log("[DONE] Готово.")
        self._set_running(False)
        # Отложим обнуление, чтобы не провоцировать уничтожение объекта прямо во время обработки сигналов
        QTimer.singleShot(0, lambda: setattr(self, "_worker", None))

    def _set_running(self, running: bool):
        self.btn_run.setEnabled(not running and bool(self._out_dir))
        self.btn_stop.setEnabled(running)
        self.btn_continue.setEnabled(False)

    def can_close(self) -> bool:
        return self._worker is None

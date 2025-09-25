from __future__ import annotations
from typing import Optional
import os, sys
from html import escape as _html_escape

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QLabel, QLineEdit, QTextEdit, QPushButton,
    QSplitter, QRadioButton, QButtonGroup, QFileDialog, QGroupBox, QSpinBox, QCheckBox, QMessageBox,
    QSizePolicy, QScrollArea, QFrame, QApplication, QDialog
)
from PySide6.QtCore import Qt, Slot, QTimer, QStandardPaths

from smithanatool_qt.settings_bind import (
    group,
    bind_line_edit, bind_checkbox, bind_spinbox, bind_radiobuttons,
    try_bind_line_edit, try_bind_checkbox, try_bind_spinbox, bind_attr_string, save_attr_string)


from smithanatool_qt.tabs.manhwa.episode_picker_dialog import EpisodePickerDialog
from smithanatool_qt.parsers.kakao.auth import _load_cookie_raw_from_session
from smithanatool_qt.parsers.kakao.episodes import _safe_list_all
from smithanatool_qt.parsers.kakao.utils import ensure_dir

from smithanatool_qt.widgets.collapsible import CollapsibleSection

from .manhwa_worker import ManhwaParserWorker, ParserConfig
from smithanatool_qt.parsers.auth_session import (
    get_session_path, delete_session,
)

# === Local split modules ===
from smithanatool_qt.tabs.manhwa.manhwa_tab_elided_label import ElidedLabel
from smithanatool_qt.tabs.manhwa.manhwa_tab_utils import open_in_explorer, choose_start_dir
from smithanatool_qt.tabs.manhwa.manhwa_tab_dialogs import show_use_ticket_dialog, show_purchase_ticket_dialog
from smithanatool_qt.tabs.manhwa.manhwa_tab_ids_bank import IdsBankPanel
from smithanatool_qt.tabs.manhwa.manhwa_tab_sections import build_auto_stitch_section, build_extra_settings_section, build_right_log_panel, build_footer


class ParserManhwaTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: Optional[ManhwaParserWorker] = None


        # Timer for debounced saves (used by IdsBankPanel via callback)
        self._ids_save_timer = QTimer(self)
        self._ids_save_timer.setSingleShot(True)
        self._ids_save_timer.setInterval(200)

        layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal, self)
        layout.addWidget(splitter)

        # LEFT: controls (top form)
        left = QWidget()
        gl = QGridLayout(left)
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
        self.rb_index = QRadioButton("По индексу")
        self.rb_ui = QRadioButton("По UI")
        mode_box = QHBoxLayout(); mode_box.setContentsMargins(0, 0, 0, 0); mode_box.setSpacing(6)
        mode_box.addWidget(self.rb_number); mode_box.addWidget(self.rb_id); mode_box.addWidget(self.rb_index); mode_box.addWidget(self.rb_ui); mode_box.addStretch(1)
        gl.addLayout(mode_box, row, 1, 1, 2); row += 1

        self.mode_group = QButtonGroup(self)
        for rb in (self.rb_number, self.rb_id, self.rb_index, self.rb_ui):
            self.mode_group.addButton(rb)

        self.lbl_spec = QLabel("Глава/ы:")
        gl.addWidget(self.lbl_spec, row, 0)
        self.ed_spec = QLineEdit(); self.ed_spec.setPlaceholderText("например: 1,2,5-7")
        gl.addWidget(self.ed_spec, row, 1, 1, 2); row += 1

        self._spec_before_ui: str = ""
        self._last_mode: Optional[str] = None

        # Save dir
        gl.addWidget(QLabel("Папка сохранения:"), row, 0, Qt.AlignLeft)
        self.btn_pick_out = QPushButton("Выбрать папку…")
        self.lbl_out = ElidedLabel("— не выбрано —"); self.lbl_out.setStyleSheet("color:#a00")
        self.btn_pick_out.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.lbl_out.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        hl = QHBoxLayout(); hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(6)
        hl.addWidget(self.btn_pick_out); hl.addWidget(self.lbl_out, 1)
        gl.addLayout(hl, row, 1, 1, 2); row += 1

        # Min width
        gl.addWidget(QLabel("Мин. ширина (px):"), row, 0)
        self.spin_minw = QSpinBox(); self.spin_minw.setRange(0, 5000); self.spin_minw.setValue(720)
        gl.addWidget(self.spin_minw, row, 1); row += 1

        # Threads
        thr = QHBoxLayout(); thr.setContentsMargins(0, 0, 0, 0); thr.setSpacing(6)
        self.chk_auto_threads = QCheckBox("Авто потоки"); self.chk_auto_threads.setChecked(True)
        self.spin_threads = QSpinBox(); self.spin_threads.setRange(1, 32)
        _default_thr = max(2, (os.cpu_count() or 4) // 2)
        self.spin_threads.setValue(min(32, _default_thr))
        thr.addWidget(self.chk_auto_threads)
        thr.addSpacing(8)
        thr.addWidget(QLabel("Потоки:"))
        thr.addWidget(self.spin_threads)
        thr.addStretch(1)
        gl.addLayout(thr, row, 0, 1, 3); row += 1
        self.spin_threads.setEnabled(False)
        self.chk_auto_threads.toggled.connect(lambda checked: self.spin_threads.setEnabled(not checked))

        # Run controls + Open folder
        self.btn_run = QPushButton("Запустить"); self.btn_run.setEnabled(False)
        self.btn_stop = QPushButton("Остановить")
        self.btn_continue = QPushButton("Продолжить после входа"); self.btn_continue.setEnabled(False)
        self.btn_open_dir = QPushButton("Открыть папку"); self.btn_open_dir.setEnabled(False)
        rl = QHBoxLayout(); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(6)
        rl.addStretch(1)
        rl.addWidget(self.btn_open_dir)
        rl.addWidget(self.btn_continue)
        rl.addWidget(self.btn_stop)
        rl.addWidget(self.btn_run)
        gl.addLayout(rl, row, 0, 1, 3); row += 1

        # === Покупки / тикеты ===
        grp_buy = QGroupBox("Покупки / тикеты")
        vb = QVBoxLayout(grp_buy)
        self.chk_auto_buy = QCheckBox("Автопокупка глав (без подтверждения)"); self.chk_auto_buy.setChecked(False)
        self.chk_auto_use_ticket = QCheckBox("Автоматически использовать 대여권 (аренду)"); self.chk_auto_use_ticket.setChecked(False)
        vb.addWidget(self.chk_auto_buy); vb.addWidget(self.chk_auto_use_ticket)
        gl.addWidget(grp_buy, row, 0, 1, 3); row += 1

        # === Автосклейка (секция) ===
        coll_auto = build_auto_stitch_section(self)
        gl.addWidget(coll_auto, row, 0, 1, 3); row += 1

        # === Доп. настройки ===
        coll_extra = build_extra_settings_section(self)
        gl.addWidget(coll_extra, row, 0, 1, 3); row += 1

        # --- Сохранённые ID (банк ID) ---
        self.btn_toggle_ids = QPushButton("Показать сохранённые ID")
        self.btn_toggle_ids.setFixedHeight(24)
        gl.addWidget(self.btn_toggle_ids, row, 0, 1, 3); row += 1

        # Container (slot) for IDs panel
        self._ids_slot = QVBoxLayout()
        gl.addLayout(self._ids_slot, row, 0, 1, 3); row += 1

        # Instantiate IdsBankPanel (lazy UI building)
        self._ids_panel = IdsBankPanel(
            on_copy_to_title=self._on_copy_id_to_title_and_save,
            parent=self
        )
        self.btn_toggle_ids.clicked.connect(self._toggle_ids_panel)

        gl.setRowStretch(row, 1)

        # RIGHT: log
        right = build_right_log_panel(self)

        # Scroll wrapper for left column
        left_scroll = QScrollArea(self)
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setWidget(left)

        left_container = QWidget(self)
        left_outer = QVBoxLayout(left_container)
        left_outer.setContentsMargins(0, 0, 0, 0)
        left_outer.setSpacing(0)
        left_outer.addWidget(left_scroll, 1)

        # Footer (fixed bottom area, outside of scroll)
        build_footer(self, left_outer)

        splitter.addWidget(left_container)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([520, 760])

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
        self.rb_number.toggled.connect(self._persist_mode)
        self.rb_id.toggled.connect(self._persist_mode)
        self.rb_index.toggled.connect(self._persist_mode)
        self.rb_ui.toggled.connect(self._persist_mode)
        self.btn_reset.clicked.connect(self.reset_to_defaults)
        self.btn_del_sess.clicked.connect(self._delete_session_clicked)
        self.chk_opt.toggled.connect(self._update_png_controls)

        # Persist UI changes to INI
        self.ed_title.editingFinished.connect(
            lambda: self._save_str_ini("title", self.ed_title.text().strip())
        )
        self.ed_spec.editingFinished.connect(
            lambda: self._save_str_ini("spec", self.ed_spec.text().strip())
        )
        self.spin_minw.valueChanged.connect(lambda v: self._save_int_ini("min_width", int(v)))
        self.spin_width.valueChanged.connect(lambda v: self._save_int_ini("target_width", int(v)))
        self.spin_comp.valueChanged.connect(lambda v: self._save_int_ini("compress_level", int(v)))
        self.spin_per.valueChanged.connect(lambda v: self._save_int_ini("per", int(v)))
        self.chk_auto.toggled.connect(lambda v: self._save_bool_ini("auto_stitch", bool(v)))
        self.chk_no_resize.toggled.connect(lambda v: self._save_bool_ini("no_resize_width", bool(v)))
        self.chk_same_dir.toggled.connect(lambda v: self._save_bool_ini("same_dir", bool(v)))
        self.chk_delete.toggled.connect(lambda v: self._save_bool_ini("delete_sources", bool(v)))
        self.chk_opt.toggled.connect(lambda v: self._save_bool_ini("optimize_png", bool(v)))
        self.chk_strip.toggled.connect(lambda v: self._save_bool_ini("strip_metadata", bool(v)))
        self.chk_auto_threads.toggled.connect(lambda v: self._save_bool_ini("auto_threads", v))
        self.spin_threads.valueChanged.connect(lambda v: self._save_int_ini("threads", int(v)))

        self._out_dir = ""
        self._stitch_dir = ""

        # Initial availability
        self._update_auto_enabled()
        self._update_no_resize()
        self._update_same_dir()
        self._update_mode()

        app = QApplication.instance()
        if app:
            app.aboutToQuit.connect(self._abort_if_running)



    # ===== Lifecycle =====
    @Slot()
    def _abort_if_running(self):
        try:
            if self._worker:
                self._worker.stop_and_wait(8000)
        except Exception:
            pass

    def showEvent(self, e):
        super().showEvent(e)
        if getattr(self, "_ini_applied", False):
            return
        self._ini_applied = True
        self.setUpdatesEnabled(False)
        try:
            self.blockSignals(True)
            self._apply_settings_from_ini()
        finally:
            self.blockSignals(False)
            self.setUpdatesEnabled(True)

    # ===== IDs Panel =====
    def _toggle_ids_panel(self):
        # Lazy build into slot
        if not self._ids_panel.ui_built:
            self._ids_panel.build_into(self._ids_slot)
        if not self._ids_panel.loaded:
            self._ids_panel.ensure_loaded()
        self._ids_panel.toggle_visibility()
        self.btn_toggle_ids.setText("Скрыть сохранённые ID" if self._ids_panel.visible else "Показать сохранённые ID")

    def _on_copy_id_to_title_and_save(self, id_value: str):
        id_value = (id_value or "").strip()
        if not id_value:
            return
        self.ed_title.setText(id_value)
        self._save_str_ini("title", id_value)

    # ===== Settings helpers =====
    def reset_to_defaults(self):
        default_mode_idx = 0
        defaults = dict(
            title="",
            spec="",
            min_width=720,
            auto_stitch=True,
            no_resize_width=True,
            target_width=800,
            same_dir=True,
            delete_sources=True,
            optimize_png=True,
            compress_level=6,
            strip_metadata=True,
            per=12,
            auto_threads=True,
            threads=max(2, (os.cpu_count() or 4) // 2),
            delete_cache=True,
            scroll_ms=30000,
        )
        self.rb_number.setChecked(default_mode_idx == 0)
        self.rb_id.setChecked(default_mode_idx == 1)
        self.rb_index.setChecked(default_mode_idx == 2)
        self._update_mode()
        self.ed_title.setText(defaults["title"])
        self.ed_spec.setText(defaults["spec"])
        self.spin_minw.setValue(defaults["min_width"])
        self.chk_auto.setChecked(defaults["auto_stitch"])
        self.chk_no_resize.setChecked(defaults["no_resize_width"])
        self.spin_width.setValue(defaults["target_width"])
        self.chk_same_dir.setChecked(defaults["same_dir"])
        self.chk_delete.setChecked(defaults["delete_sources"])
        self.chk_opt.setChecked(defaults["optimize_png"])
        self.spin_comp.setValue(defaults["compress_level"])
        self.chk_strip.setChecked(defaults["strip_metadata"])
        self.spin_per.setValue(defaults["per"])
        self.chk_auto_threads.setChecked(defaults["auto_threads"])
        self.spin_threads.setValue(min(32, defaults["threads"]))
        self.chk_delete_cache.setChecked(defaults["delete_cache"])
        self.spin_scroll_ms.setValue(int(defaults["scroll_ms"]))

        # Save to INI
        self._save_int_ini("mode", default_mode_idx)
        self._save_str_ini("title", defaults["title"])
        self._save_str_ini("spec", defaults["spec"])
        self._save_int_ini("min_width", defaults["min_width"])
        self._save_bool_ini("auto_stitch", defaults["auto_stitch"])
        self._save_bool_ini("no_resize_width", defaults["no_resize_width"])
        self._save_int_ini("target_width", defaults["target_width"])
        self._save_bool_ini("same_dir", defaults["same_dir"])
        self._save_bool_ini("delete_sources", defaults["delete_sources"])
        self._save_bool_ini("optimize_png", defaults["optimize_png"])
        self._save_int_ini("compress_level", defaults["compress_level"])
        self._save_bool_ini("strip_metadata", defaults["strip_metadata"])
        self._save_int_ini("per", defaults["per"])
        self._save_bool_ini("auto_threads", defaults["auto_threads"])
        self._save_int_ini("threads", min(32, defaults["threads"]))
        self._save_bool_ini("delete_cache", defaults["delete_cache"])
        self._save_int_ini("scroll_ms", defaults["scroll_ms"])

    def _save_bool_ini(self, key: str, value: bool):
        try:
            shadow_attr = f"__{key}__shadow"
            setattr(self, shadow_attr, "1" if value else "0")
            with group("ParserManhwa"):
                save_attr_string(self, shadow_attr, key)
        except Exception:
            pass

    def _save_str_ini(self, key: str, value: str):
        try:
            shadow_attr = f"__{key}__shadow"
            setattr(self, shadow_attr, value)
            with group("ParserManhwa"):
                save_attr_string(self, shadow_attr, key)
        except Exception:
            pass

    def _save_int_ini(self, key: str, value: int):
        self._save_str_ini(key, str(int(value)))

    def _persist_mode(self):
        idx = 0 if self.rb_number.isChecked() else (1 if self.rb_id.isChecked() else (2 if self.rb_index.isChecked() else 3))
        self._save_int_ini("mode", idx)
        self._update_mode()

    @Slot()
    def _delete_session_clicked(self):
        if not getattr(self, "_out_dir", ""):
            QMessageBox.information(self, "Удалить сессию",
                                    "Сначала выберите папку сохранения — там хранится файл сессии kakao_auth.json.")
            return
        p = get_session_path(self._out_dir)
        if not p.exists():
            QMessageBox.information(self, "Удалить сессию",
                                    f"Файл сессии не найден:\n{p}")
            return
        ans = QMessageBox.question(
            self, "Подтверждение",
            f"Удалить файл сессии?\n\n{p}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if ans == QMessageBox.Yes:
            ok = delete_session(self._out_dir)
            if ok:
                self._append_log(f"[OK] Удалена сессия: {p}")
                QMessageBox.information(self, "Удалить сессию", "Файл сессии удалён.")
            else:
                self._append_log(f"[WARN] Не удалось удалить сессию: {p}")
                QMessageBox.warning(self, "Удалить сессию", "Не удалось удалить файл сессии.")

    def _start_dir(self, prefer: str) -> str:
        return choose_start_dir(prefer)

    @Slot()
    def _pick_out(self):
        start = self._start_dir(getattr(self, "_out_dir", ""))
        d = QFileDialog.getExistingDirectory(
            self, "Папка сохранения", start, QFileDialog.ShowDirsOnly
        )
        if d:
            self._out_dir = d
            self._save_str_ini("out_dir", d)
            self.lbl_out.set_full_text(d)
            self.lbl_out.setText(d)
            self.lbl_out.setStyleSheet("color:#080")
            self.btn_run.setEnabled(True)
            self.btn_open_dir.setEnabled(True)

    @Slot()
    def _open_out_dir(self):
        if self._out_dir:
            open_in_explorer(self._out_dir)

    @Slot()
    def _pick_stitch_dir(self):
        start = self._start_dir(getattr(self, "_stitch_dir", "") or getattr(self, "_out_dir", ""))
        d = QFileDialog.getExistingDirectory(
            self, "Папка для склеек", start, QFileDialog.ShowDirsOnly
        )
        if d:
            self._stitch_dir = d
            self._save_str_ini("stitch_dir", d)
            self.lbl_stitch_dir.set_full_text(d)
            self.lbl_stitch_dir.setText(d)
            self.lbl_stitch_dir.setStyleSheet("color:#080")

    # ===== UI state updates =====
    def _update_png_controls(self):
        auto_on = self.chk_auto.isChecked()
        enable_comp = auto_on and (not self.chk_opt.isChecked())
        self.spin_comp.setEnabled(enable_comp)
        if hasattr(self, "lbl_comp"):
            self.lbl_comp.setEnabled(enable_comp)

    def _update_auto_enabled(self):
        on = self.chk_auto.isChecked()
        for w in [
            self.chk_no_resize, self.spin_width, self.chk_same_dir, self.btn_pick_stitch,
            self.chk_delete, self.chk_opt, self.spin_comp, self.chk_strip, self.spin_per
        ]:
            w.setEnabled(on)
        self._update_same_dir()
        self._update_no_resize()
        self._update_png_controls()

    def _update_no_resize(self):
        self.spin_width.setEnabled(self.chk_auto.isChecked() and not self.chk_no_resize.isChecked())

    def _update_same_dir(self):
        self.btn_pick_stitch.setEnabled(self.chk_auto.isChecked() and not self.chk_same_dir.isChecked())

    def _update_mode(self):
        new_mode = (
            "number" if self.rb_number.isChecked()
            else "id" if self.rb_id.isChecked()
            else "index" if self.rb_index.isChecked()
            else "ui"
        )
        prev = getattr(self, "_last_mode", None)

        if new_mode == "ui":
            if prev != "ui":
                self._spec_before_ui = self.ed_spec.text()

            self.lbl_spec.setText("—")
            self.ed_spec.clear()
            self.ed_spec.setPlaceholderText("Выбор глав появится после нажатия «Запустить»")
            self.lbl_spec.setEnabled(False)
            self.ed_spec.setEnabled(False)

        else:
            self.lbl_spec.setEnabled(True)
            self.ed_spec.setEnabled(True)
            if new_mode == "number":
                self.lbl_spec.setText("Глава(ы):")
                self.ed_spec.setPlaceholderText("например: 1,2,5-7")
            elif new_mode == "id":
                self.lbl_spec.setText("Viewer ID:")
                self.ed_spec.setPlaceholderText("например: 12801928, 12999192")
            else:  # index
                self.lbl_spec.setText("Индекс:")
                self.ed_spec.setPlaceholderText("например: 1,2,5-7")

            # Восстанавливаем текст ТОЛЬКО при выходе из UI и если поле пустое
            if prev == "ui" and not self.ed_spec.text():
                self.ed_spec.setText(self._spec_before_ui or "")

        # Обновляем «прошлый» режим
        self._last_mode = new_mode

    def _on_auto_toggled(self, checked: bool):
        self._save_bool_ini("auto_stitch", checked)
        self._update_auto_enabled()

    # ===== Dialogs =====
    def _on_ask_purchase(self, price, balance):
        if self.chk_auto_buy.isChecked():
            ans = True
        else:
            ans = show_purchase_ticket_dialog(self, int(price) if price is not None else None,
                                              int(balance) if balance is not None else None)
        if self._worker:
            self._worker.provide_purchase_answer(bool(ans))

    def _on_ask_use_rental(self, rental_count: int, own_count: int, balance, chapter_label: str):
        self._last_ch_label = chapter_label
        if self.chk_auto_use_ticket.isChecked():
            ans = True
        else:
            ans = show_use_ticket_dialog(self, rental_count, own_count, int(balance) if balance is not None else None, chapter_label)
        if self._worker:
            self._worker.provide_use_rental_answer(bool(ans))

    # ===== Worker / run flow =====
    def _collect_cfg(self) -> ParserConfig:
        mode = "number" if self.rb_number.isChecked() else ("id" if self.rb_id.isChecked() else ("index" if self.rb_index.isChecked() else "ui"))
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
            auto_confirm_purchase=self.chk_auto_buy.isChecked(),
            auto_confirm_use_rental=self.chk_auto_use_ticket.isChecked(),
            auto_threads=self.chk_auto_threads.isChecked(),
            threads=int(self.spin_threads.value()),
            cache_episode_map=True,
            delete_cache_after=self.chk_delete_cache.isChecked(),
            scroll_ms=int(self.spin_scroll_ms.value())
        )

    def _append_log(self, s: str):
        msg = _html_escape(s)
        color = "#888"
        if s.startswith("[ERROR]") or s.startswith("[CANCEL]"):
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



    @Slot()
    def _start(self):
        if not self._out_dir:
            QMessageBox.warning(self, "Парсер", "Сначала выберите папку сохранения.")
            return

        cfg = self._collect_cfg()

        self._worker = ManhwaParserWorker(cfg)
        self._worker.log.connect(self._append_log)
        self._worker.error.connect(lambda e: self._append_log(f"[ERROR] {e}"))
        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._worker.need_login.connect(self._on_need_login)
        self._worker.finished.connect(self._on_finished)
        self._worker.ask_purchase.connect(self._on_ask_purchase)
        self._worker.ask_use_rental.connect(self._on_ask_use_rental)
        self._worker.move_to_thread_and_start()
        self._set_running(True)
        self._worker.ui_pick_required.connect(self._on_ui_pick_required)

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
        self.btn_continue.setEnabled(True)

    def _on_finished(self):
        self._append_log("[DONE] Парсер завершил работу.")
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_continue.setEnabled(False)
        self._worker = None

    def _set_running(self, running: bool):
        self.btn_run.setEnabled(not running and bool(self._out_dir))
        self.btn_stop.setEnabled(running)
        self.btn_continue.setEnabled(False)

    def can_close(self) -> bool:
        return self._worker is None

    def _on_ui_pick_required(self, sid: int, rows: object):
        try:
            from smithanatool_qt.tabs.manhwa.episode_picker_dialog import EpisodePickerDialog
            dlg = EpisodePickerDialog(f"ID {sid}", rows, parent=self)
            if dlg.exec() != QDialog.Accepted:
                if self._worker:
                    self._worker.cancel_ui_pick()
                return
            ids = dlg.selected_product_ids()
            if not ids:
                QMessageBox.information(self, "Выбор глав", "Ничего не выбрано.")
                if self._worker:
                    self._worker.cancel_ui_pick()
                return
            if self._worker:
                self._worker.provide_ui_selected_ids([str(x) for x in ids])
        except Exception as e:
            QMessageBox.critical(self, "Выбор глав", f"Ошибка диалога выбора глав: {e}")
            if self._worker:
                self._worker.cancel_ui_pick()

    def _apply_settings_from_ini(self):
        with group("ParserManhwa"):
            bind_attr_string(self, "_out_dir", "out_dir", "")
            bind_attr_string(self, "_stitch_dir", "stitch_dir", "")
            bind_line_edit(self.ed_title, "title", "")
            bind_line_edit(self.ed_spec, "spec", "")
            try_bind_line_edit(self, "ed_vol", "volumes", "")
            try_bind_checkbox(self, "chk_auto_buy", "auto_buy", False)
            try_bind_checkbox(self, "chk_auto_use_ticket", "auto_use_ticket", False)
            bind_spinbox(self.spin_minw, "min_width", 720)
            bind_spinbox(self.spin_width, "target_width", 800)
            bind_spinbox(self.spin_comp, "compress_level", 6)
            bind_spinbox(self.spin_per, "per", 12)
            bind_checkbox(self.chk_delete_cache, "delete_cache", True)
            bind_spinbox(self.spin_scroll_ms, "scroll_ms", 30000)
            bind_radiobuttons([self.rb_number, self.rb_id, self.rb_index, self.rb_ui], "mode", 0)
            bind_checkbox(self.chk_auto, "auto_stitch", True)
            bind_checkbox(self.chk_no_resize, "no_resize_width", True)
            bind_checkbox(self.chk_same_dir, "same_dir", True)
            bind_checkbox(self.chk_delete, "delete_sources", True)
            bind_checkbox(self.chk_opt, "optimize_png", True)
            bind_checkbox(self.chk_strip, "strip_metadata", True)
            bind_checkbox(self.chk_auto_threads, "auto_threads", True)
            bind_spinbox(self.spin_threads, "threads", max(2, (os.cpu_count() or 4) // 2))
            self.spin_threads.setEnabled(not self.chk_auto_threads.isChecked())

        self.lbl_out.set_full_text(self._out_dir or "— не выбрано —")
        self.lbl_out.setStyleSheet("color:#228B22" if self._out_dir else "color:#B32428")
        self.btn_run.setEnabled(bool(self._out_dir))
        self.btn_open_dir.setEnabled(bool(self._out_dir))

        self.lbl_stitch_dir.set_full_text(self._stitch_dir or "— не выбрано —")
        self.lbl_stitch_dir.setStyleSheet("color:#228B22" if self._stitch_dir else "color:#B32428")

        self._update_mode()
        self.chk_auto.toggled.connect(self._on_auto_toggled)
        self._update_no_resize()
        self._update_same_dir()
        self._update_png_controls()

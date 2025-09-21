from __future__ import annotations
import os, re, subprocess, sys, json, pathlib
from html import escape as _html_escape

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QLabel, QLineEdit, QTextEdit, QPushButton,
    QSplitter, QRadioButton, QButtonGroup, QFileDialog, QMessageBox, QSizePolicy,
    QGroupBox, QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QScrollArea, QFrame
)

from PySide6.QtCore import Qt, Slot, QTimer, QStandardPaths

# === INI биндинги ===
from smithanatool_qt.settings_bind import (
    group,
    bind_line_edit, bind_radiobuttons,
    bind_attr_string, save_attr_string
)

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
        self.ed_spec = QLineEdit(); self.ed_spec.setPlaceholderText("например: 1-5,8 или 3")  # number mode
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

        left_scroll = QScrollArea(self)
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setWidget(left)

        splitter.addWidget(left_scroll)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([520, 760])

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

        # === Покупки / тикеты ===
        grp_buy = QGroupBox("Покупки / тикеты")
        vb_buy = QVBoxLayout(grp_buy);
        vb_buy.setContentsMargins(8, 8, 8, 8);
        vb_buy.setSpacing(6)

        self.chk_auto_buy = QCheckBox("Автопокупка глав (без подтверждения)")
        self.chk_auto_buy.setToolTip("Если включено, покупка тикетов/глав подтверждается автоматически.")
        self.chk_auto_buy.setChecked(False)
        vb_buy.addWidget(self.chk_auto_buy)

        self.chk_auto_use_ticket = QCheckBox("Автоматически использовать 대여권 (аренду)")
        self.chk_auto_use_ticket.setToolTip(
            "Если включено, использование доступных тикетов подтверждается автоматически.")
        self.chk_auto_use_ticket.setChecked(False)
        vb_buy.addWidget(self.chk_auto_use_ticket)
        vb_buy.addStretch(1)

        self.chk_auto_buy.toggled.connect(lambda v: self._save_bool_ini("auto_buy", v))
        self.chk_auto_use_ticket.toggled.connect(lambda v: self._save_bool_ini("auto_use_ticket", v))



        # Вставляем в сетку слева отдельной строкой
        gl.addWidget(grp_buy, row, 0, 1, 3);
        row += 1

        # Reset button (right-aligned)
        self.btn_reset = QPushButton("Сброс настроек")
        self.btn_reset.setFixedHeight(28)
        self.btn_reset.setFixedWidth(100)
        hreset = QHBoxLayout();
        hreset.setContentsMargins(0, 0, 0, 0);
        hreset.setSpacing(6)
        hreset.addStretch(1);
        hreset.addWidget(self.btn_reset)
        gl.addLayout(hreset, row, 0, 1, 3);
        row += 1

        # --- Сохранённые ID (банк ID) ---
        self._ids_save_timer = QTimer(self)
        self._ids_save_timer.setSingleShot(True)
        self._ids_save_timer.setInterval(200)
        self._ids_save_timer.timeout.connect(self._refresh_ids_from_table_and_save)

        self.btn_toggle_ids = QPushButton("Показать сохранённые ID")
        self.btn_toggle_ids.setFixedHeight(24)
        gl.addWidget(self.btn_toggle_ids, row, 0, 1, 3);
        row += 1

        self._ids_slot = QVBoxLayout()
        gl.addLayout(self._ids_slot, row, 0, 1, 3);
        row += 1

        self._ids_ui_built = False
        self._ids_loaded = False
        self.btn_toggle_ids.clicked.connect(self._toggle_ids_panel)


        gl.setRowStretch(row, 1)

        # wiring
        self.btn_pick_out.clicked.connect(self._pick_out)
        self.btn_open_dir.clicked.connect(self._open_out_dir)
        self.btn_clear.clicked.connect(lambda: self.txt_log.clear())
        self.btn_run.clicked.connect(self._start)
        self.btn_stop.clicked.connect(self._stop)
        self.btn_continue.clicked.connect(self._continue)
        self.rb_number.toggled.connect(self._on_mode_toggled)
        self.rb_id.toggled.connect(self._on_mode_toggled)
        self.btn_reset.clicked.connect(self.reset_to_defaults)

        # --- persist line edits to INI on change ---
        self.ed_title.editingFinished.connect(
            lambda: self._save_str_ini("title", self.ed_title.text().strip())
        )
        self.ed_spec.editingFinished.connect(
            lambda: self._save_str_ini("spec", self.ed_spec.text().strip())
        )
        self.ed_vol.editingFinished.connect(
            lambda: self._save_str_ini("volumes", self.ed_vol.text().strip())
        )

        # Применяем настройки после инициализации UI
        QTimer.singleShot(0, self._apply_settings_from_ini)

    # ---------- UI state ----------
    def reset_to_defaults(self):
        default_mode_idx = 0  # 0=number, 1=id
        defaults = dict(
            title="",
            spec="",
            volumes="",
            # out_dir не трогаем
        )

        # режим
        self.rb_number.setChecked(default_mode_idx == 0)
        self.rb_id.setChecked(default_mode_idx == 1)
        self._update_mode()

        # поля
        self.ed_title.setText(defaults["title"])
        self.ed_spec.setText(defaults["spec"])
        self.ed_vol.setText(defaults["volumes"])

        # сохранить в INI
        self._save_int_ini("mode", default_mode_idx)
        self._save_str_ini("title", defaults["title"])
        self._save_str_ini("spec", defaults["spec"])
        self._save_str_ini("volumes", defaults["volumes"])

        # пути/кнопки
        self.btn_run.setEnabled(bool(self._out_dir))
        self.btn_open_dir.setEnabled(bool(self._out_dir))

    def _save_str_ini(self, key: str, value: str):
        try:
            shadow_attr = f"__{key}__shadow"
            setattr(self, shadow_attr, value)
            with group("ParserNovel"):
                save_attr_string(self, shadow_attr, key)
        except Exception:
            pass

    def _save_int_ini(self, key: str, value: int):
        self._save_str_ini(key, str(int(value)))

    def _save_bool_ini(self, key: str, value: bool):
        self._save_str_ini(key, str(int(bool(value))))

    def _update_mode(self):
        if self.rb_id.isChecked():
            self.lbl_spec.setText("ViewerID:")
            self.ed_spec.setPlaceholderText("например: 123456789,987654321")
            self.lbl_vol.setEnabled(False); self.ed_vol.setEnabled(False)
        else:
            self.lbl_spec.setText("Глава/ы:")
            self.ed_spec.setPlaceholderText("например: 1,2,5-7")
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

    # ============ Bank of IDs (novel_ids) ============
    def _load_ids_json(self) -> list[dict]:
        blob = self._load_all_values()
        raw = blob.get("novel_ids", [])
        out = []
        if isinstance(raw, list):
            for it in raw:
                name = (it.get("name") or "").strip() if isinstance(it, dict) else ""
                _id = (it.get("id") or "").strip() if isinstance(it, dict) else ""
                if name or _id:
                    out.append({"name": name, "id": _id})
        return out

    def _save_ids_json(self):
        blob = self._load_all_values()
        blob["novel_ids"] = self._ids
        self._save_all_values(blob)

    def _ensure_ids_loaded(self):
        if getattr(self, "_ids_loaded", False):
            return
        self._ids = self._load_ids_json()
        self._rebuild_ids_ui()
        self._ids_loaded = True

    def _build_ids_ui(self):
        if self._ids_ui_built:
            return
        ids_grp = QGroupBox("Сохранённые ID")
        self._ids_grp = ids_grp
        ids_grp.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        ids_v = QVBoxLayout(ids_grp)
        ids_v.setContentsMargins(8, 8, 8, 8)
        ids_v.setSpacing(6)

        self.ids_table = QTableWidget(0, 2)
        self.ids_table.setHorizontalHeaderLabels(["Название", "ID"])
        self.ids_table.setFixedHeight(120)
        self.ids_table.horizontalHeader().setStretchLastSection(True)
        self.ids_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.ids_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.ids_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.ids_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.ids_table.setEditTriggers(QAbstractItemView.AllEditTriggers)
        self.ids_table.setSortingEnabled(False)
        ids_v.addWidget(self.ids_table)

        row_btns = QHBoxLayout()
        row_btns.addStretch(1)
        self.btn_add_id = QPushButton("Добавить")
        self.btn_del_id = QPushButton("Удалить выбранные")
        self.btn_copy_to_title = QPushButton("→ в ID тайтла")
        for b in (self.btn_copy_to_title, self.btn_del_id, self.btn_add_id):
            b.setFixedHeight(24)
        row_btns.addWidget(self.btn_copy_to_title)
        row_btns.addWidget(self.btn_del_id)
        row_btns.addWidget(self.btn_add_id)
        ids_v.addLayout(row_btns)

        # wiring
        self.btn_add_id.clicked.connect(lambda: self._add_id_entry("", ""))
        self.btn_del_id.clicked.connect(self._delete_selected_ids)
        self.btn_copy_to_title.clicked.connect(self._copy_selected_id_to_title)
        self.ids_table.itemChanged.connect(self._on_ids_item_changed)

        self._ids_slot.addWidget(ids_grp)
        ids_grp.setVisible(False)
        self._ids_ui_built = True

    def _toggle_ids_panel(self):
        if not getattr(self, "_ids_ui_built", False):
            self._build_ids_ui()
        if not self._ids_loaded:
            self._ensure_ids_loaded()
        visible = self._ids_grp.isVisible()
        self._ids_grp.setVisible(not visible) # оставил читаемо
        self.btn_toggle_ids.setText("Скрыть сохранённые ID" if not visible else "Показать сохранённые ID")

    def _rebuild_ids_ui(self):
        self.ids_table.setUpdatesEnabled(False)
        self.ids_table.blockSignals(True)
        try:
            self.ids_table.setRowCount(len(self._ids))
            for r, item in enumerate(self._ids):
                self.ids_table.setItem(r, 0, QTableWidgetItem(item.get("name", "")))
                self.ids_table.setItem(r, 1, QTableWidgetItem(item.get("id", "")))
        finally:
            self.ids_table.blockSignals(False)
            self.ids_table.setUpdatesEnabled(True)

    def _table_to_ids(self) -> list[dict]:
        data = []
        rows = self.ids_table.rowCount()
        for r in range(rows):
            it_name = self.ids_table.item(r, 0)
            it_id = self.ids_table.item(r, 1)
            name = it_name.text().strip() if it_name else ""
            _id = it_id.text().strip() if it_id else ""
            if name or _id:
                data.append({"name": name, "id": _id})
        return data

    def _refresh_ids_from_table_and_save(self):
        self._ids = self._table_to_ids()
        self._save_ids_json()

    def _on_ids_item_changed(self, _item: QTableWidgetItem):
        self._ids_save_timer.start()

    def _add_id_entry(self, name: str, id_value: str):
        self.ids_table.blockSignals(True)
        r = self.ids_table.rowCount()
        self.ids_table.insertRow(r)
        self.ids_table.setItem(r, 0, QTableWidgetItem((name or "").strip()))
        self.ids_table.setItem(r, 1, QTableWidgetItem((id_value or "").strip()))
        self.ids_table.blockSignals(False)
        self._refresh_ids_from_table_and_save()

    def _delete_selected_ids(self):
        rows = sorted({i.row() for i in self.ids_table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        self.ids_table.blockSignals(True)
        for r in rows:
            self.ids_table.removeRow(r)
        self.ids_table.blockSignals(False)
        self._refresh_ids_from_table_and_save()

    def _copy_selected_id_to_title(self):
        sel = self.ids_table.selectedItems()
        if not sel:
            return
        row = sel[0].row()
        id_item = self.ids_table.item(row, 1)
        if id_item:
            id_value = (id_item.text() or "").strip()
            if id_value:
                self.ed_title.setText(id_value)
                self._save_str_ini("title", id_value)

    # ============ Values.json (общий для модулей) ============
    def _settings_dir(self) -> str:
        cached = getattr(self, "_settings_dir_cached", None)
        if cached:
            return cached

        def _is_writable(p: str) -> bool:
            try:
                os.makedirs(p, exist_ok=True)
                test = os.path.join(p, ".write_test")
                with open(test, "w", encoding="utf-8") as f:
                    f.write("")
                os.remove(test)
                return True
            except Exception:
                return False

        try:
            if getattr(sys, "frozen", False):
                base = os.path.dirname(sys.executable)
            else:
                cwd = os.getcwd()
                if os.path.exists(os.path.join(cwd, "settings.ini")):
                    base = cwd
                else:
                    p = pathlib.Path(__file__).resolve()
                    base = None
                    for parent in [p.parent, *p.parents]:
                        if (parent / "settings.ini").exists():
                            base = str(parent)
                            break
                    if not base:
                        base = cwd
            if not _is_writable(base):
                app_data = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or ""
                base = app_data if app_data and _is_writable(app_data) else (
                    os.path.expanduser("~") if _is_writable(os.path.expanduser("~")) else os.getcwd())
        except Exception:
            base = os.path.expanduser("~")
            if not _is_writable(base):
                base = os.getcwd()

        self._settings_dir_cached = base
        return base

    def _ids_json_path(self) -> str:
        return os.path.join(self._settings_dir(), "values.json")

    def _load_all_values(self) -> dict:
        path = self._ids_json_path()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {}

    def _save_all_values(self, data: dict):
        path = self._ids_json_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---------- Actions ----------
    @Slot()
    def _pick_out(self):
        dlg = QFileDialog(self, "Выберите папку сохранения")
        dlg.setFileMode(QFileDialog.Directory)
        if dlg.exec():
            paths = dlg.selectedFiles()
            if paths:
                self._out_dir = paths[0]
                # сразу сохраним в INI
                with group("ParserNovel"):
                    save_attr_string(self, "_out_dir", "out_dir")
                # Отразим в UI
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
            auto_confirm_purchase=self.chk_auto_buy.isChecked(),
            auto_confirm_use_rental=self.chk_auto_use_ticket.isChecked(),
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
        self._worker.ask_purchase.connect(self._on_ask_purchase)
        self._worker.ask_use_rental.connect(self._on_ask_use_rental)

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


    # ---------- Persistence (INI) ----------
    def _apply_settings_from_ini(self):
        """Загрузка всех настроек из INI + привязки."""
        with group("ParserNovel"):
            # Пути (как атрибуты)
            bind_attr_string(self, "_out_dir", "out_dir", "")

            # Поля ввода
            bind_line_edit(self.ed_title, "title", "")
            bind_line_edit(self.ed_spec,  "spec",  "")
            bind_line_edit(self.ed_vol,   "volumes", "")

            # Переключатели режима: 0 = number, 1 = id
            bind_radiobuttons([self.rb_number, self.rb_id], "mode", 0)

            try:
                # читаем строки "0/1" как bool
                from smithanatool_qt.settings_bind import try_bind_checkbox
                try_bind_checkbox(self, "chk_auto_buy", "auto_buy", False)
                try_bind_checkbox(self, "chk_auto_use_ticket", "auto_use_ticket", False)
            except Exception:
                pass

        # Отразим пути в подписи (цвет — зелёный если задано)
        self.lbl_out.setText(self._out_dir or "— не выбрано —")
        self.lbl_out.setStyleSheet("color:#080" if self._out_dir else "color:#a00")
        self.btn_run.setEnabled(bool(self._out_dir))
        self.btn_open_dir.setEnabled(bool(self._out_dir))

        # Приведём подписи/плейсхолдеры под выбранный режим
        self._update_mode()



    @Slot(bool)
    def _on_mode_toggled(self, _checked: bool):
        """Сразу досохраняем выбранный режим в INI и обновляем UI."""
        # 0 — по номеру, 1 — по ID
        mode_index = 1 if self.rb_id.isChecked() else 0
        try:
            setattr(self, "__mode_shadow", str(mode_index))
            with group("ParserNovel"):
                save_attr_string(self, "__mode_shadow", "mode")
        except Exception:
            pass
        self._update_mode()

    def _show_purchase_dialog(self, price: int | None, balance: int | None) -> bool:
        price_txt = f"{price} кредитов" if price is not None else "не удалось определить"
        bal_txt = f"{balance} кредитов" if balance is not None else "—"
        msg = (f"Покупка главы\n\n"
               f"Цена: {price_txt}\n"
               f"Баланс: {bal_txt}\n\n"
               f"Продолжить покупку?")
        return QMessageBox.question(
            self, "Покупка главы", msg,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        ) == QMessageBox.Yes

    def _show_use_ticket_dialog(self, rental_count: int, own_count: int, balance: int | None,
                                chapter_label: str) -> bool:
        bal_txt = f"{balance} кредитов" if balance is not None else "—"
        msg = (f"{chapter_label}\n\n"
               f"Доступны тикеты:\n"
               f" • Аренда: {rental_count} шт\n"
               f" • Владение: {own_count} шт\n"
               f"Баланс: {bal_txt}\n\n"
               f"Использовать тикет аренды для этой главы?")
        return QMessageBox.question(
            self, "Использовать тикет?", msg,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        ) == QMessageBox.Yes

    @Slot(object, object)
    def _on_ask_purchase(self, price, balance):
        if self.chk_auto_buy.isChecked():
            ans = True
        else:
            ans = self._show_purchase_dialog(
                int(price) if price is not None else None,
                int(balance) if balance is not None else None
            )
        if self._worker:
            self._worker.provide_purchase_answer(bool(ans))

    @Slot(int, int, object, str)
    def _on_ask_use_rental(self, rental_count: int, own_count: int, balance, chapter_label: str):
        if self.chk_auto_use_ticket.isChecked():
            ans = True
        else:
            ans = self._show_use_ticket_dialog(
                int(rental_count), int(own_count),
                int(balance) if balance is not None else None,
                chapter_label
            )
        if self._worker:
            self._worker.provide_use_rental_answer(bool(ans))


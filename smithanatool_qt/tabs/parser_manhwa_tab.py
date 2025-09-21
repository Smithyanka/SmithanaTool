from __future__ import annotations
from typing import Optional
import os, sys, subprocess, json, pathlib
from html import escape as _html_escape


from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QLabel, QLineEdit, QTextEdit, QPushButton,
    QSplitter, QRadioButton, QButtonGroup, QFileDialog, QGroupBox, QSpinBox, QCheckBox, QMessageBox,
    QSizePolicy, QScrollArea, QFrame, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
)
from PySide6.QtCore import Qt, Slot, QTimer, QStandardPaths

from smithanatool_qt.settings_bind import (
    group,
    bind_line_edit, bind_checkbox, bind_spinbox, bind_radiobuttons,
    try_bind_line_edit, try_bind_checkbox, try_bind_spinbox,
    bind_attr_string, save_attr_string
)

from .manhwa_worker import ManhwaParserWorker, ParserConfig

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

class ElidedLabel(QLabel):
    """QLabel, который автоматически укорачивает длинный текст с многоточием.
    По умолчанию — в середине (ElideMiddle). Хранит полный текст в tooltip.
    """
    def __init__(self, text:str="", mode=Qt.ElideMiddle, parent=None):
        super().__init__(text, parent)
        self._full_text = text or ""
        self._mode = mode
        self.setToolTip(self._full_text if self._full_text else "")
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)

    def set_full_text(self, text: str):
        self._full_text = text or ""
        self.setToolTip(self._full_text if self._full_text else "")
        self._apply_elide()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply_elide()

    def _apply_elide(self):
        # Немного оставим место на отступы
        avail = max(10, self.width() - 8)
        elided = self.fontMetrics().elidedText(self._full_text, self._mode, avail)
        super().setText(elided)


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

        self._ids_save_timer = QTimer(self)
        self._ids_save_timer.setSingleShot(True)
        self._ids_save_timer.setInterval(200)  # мс; можешь 300–500
        self._ids_save_timer.timeout.connect(self._refresh_ids_from_table_and_save)

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
        mode_box = QHBoxLayout(); mode_box.setContentsMargins(0, 0, 0, 0); mode_box.setSpacing(6)
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

        self.chk_auto_buy = QCheckBox("Автопокупка глав (без подтверждения)")
        self.chk_auto_buy.setChecked(False)

        self.chk_auto_use_ticket = QCheckBox("Автоматически использовать 대여권 (аренду)")
        self.chk_auto_use_ticket.setChecked(False)

        vb.addWidget(self.chk_auto_buy)
        vb.addWidget(self.chk_auto_use_ticket)

        gl.addWidget(grp_buy, row, 0, 1, 3);
        row += 1

        # Auto concat group
        grp = QGroupBox("Автосклейка")
        v = QVBoxLayout(grp)
        self.chk_auto = QCheckBox("Включить автосклейку"); self.chk_auto.setChecked(True)
        v.addWidget(self.chk_auto)

        rowa = QGridLayout(); v.addLayout(rowa)
        r = 0
        self.chk_no_resize = QCheckBox("Не изменять ширину"); self.chk_no_resize.setChecked(True)
        rowa.addWidget(self.chk_no_resize, r, 0, 1, 2); r += 1
        rowa.addWidget(QLabel("Ширина:"), r, 0)
        self.spin_width = QSpinBox(); self.spin_width.setRange(50, 20000); self.spin_width.setValue(800)
        rowa.addWidget(self.spin_width, r, 1); r += 1

        self.chk_same_dir = QCheckBox("Сохранять в той же папке, где и исходники")
        rowa.addWidget(self.chk_same_dir, r, 0, 1, 2); r += 1
        self.chk_same_dir.setChecked(True)

        rowa.addWidget(QLabel("Папка для склеек:"), r, 0)
        self.btn_pick_stitch = QPushButton("Выбрать…")
        self.lbl_stitch_dir = ElidedLabel("— не выбрано —"); self.lbl_stitch_dir.setStyleSheet("color:#a00")
        self.btn_pick_stitch.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.lbl_stitch_dir.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        hl2 = QHBoxLayout(); hl2.setContentsMargins(0, 0, 0, 0); hl2.setSpacing(6)
        hl2.addWidget(self.btn_pick_stitch); hl2.addWidget(self.lbl_stitch_dir, 1)
        rowa.addLayout(hl2, r, 1); r += 1

        self.chk_delete = QCheckBox("Удалять исходники после склейки"); self.chk_delete.setChecked(True)
        rowa.addWidget(self.chk_delete, r, 0, 1, 2); r += 1

        # PNG options
        rowa.addWidget(QLabel("Опции PNG:"), r, 0); r += 1
        self.chk_opt = QCheckBox("Оптимизировать PNG"); self.chk_opt.setChecked(True)
        self.chk_strip = QCheckBox("Удалять метаданные"); self.chk_strip.setChecked(True)
        self.spin_comp = QSpinBox(); self.spin_comp.setRange(0, 9); self.spin_comp.setValue(6)
        hl3 = QHBoxLayout(); hl3.setContentsMargins(0, 0, 0, 0); hl3.setSpacing(6)
        hl3.addWidget(self.chk_opt); hl3.addWidget(QLabel("Уровень сжатия (0-9):")); hl3.addWidget(self.spin_comp); hl3.addWidget(self.chk_strip); hl3.addStretch(1)
        v.addLayout(hl3)

        # per
        hl4 = QHBoxLayout(); hl4.setContentsMargins(0, 0, 0, 0); hl4.setSpacing(6)
        hl4.addWidget(QLabel("По сколько клеить:"))
        self.spin_per = QSpinBox(); self.spin_per.setRange(1, 999); self.spin_per.setValue(12)
        hl4.addWidget(self.spin_per); hl4.addStretch(1)
        v.addLayout(hl4)

        gl.addWidget(grp, row, 0, 1, 3); row += 1



        # сохранить в INI при изменении
        self.chk_auto_buy.toggled.connect(lambda v: self._save_bool_ini("auto_buy", v))
        self.chk_auto_use_ticket.toggled.connect(lambda v: self._save_bool_ini("auto_use_ticket", v))

        # Reset button (right-aligned)
        self.btn_reset = QPushButton("Сброс настроек")
        self.btn_reset.setFixedHeight(28)
        self.btn_reset.setFixedWidth(100)
        hr = QHBoxLayout()
        hr.setContentsMargins(0, 0, 0, 0)
        hr.setSpacing(6)
        hr.addStretch(1)
        hr.addWidget(self.btn_reset)
        gl.addLayout(hr, row, 0, 1, 3)
        row += 1

        # --- Сохранённые ID (банк ID) ---
        # КНОПКА-ТОГГЛЕР
        self.btn_toggle_ids = QPushButton("Показать сохранённые ID")
        self.btn_toggle_ids.setFixedHeight(24)
        gl.addWidget(self.btn_toggle_ids, row, 0, 1, 3)
        row += 1

        self._ids_slot = QVBoxLayout()  # место под группу
        gl.addLayout(self._ids_slot, row, 0, 1, 3)
        row += 1
        self._ids_ui_built = False
        self._ids_loaded = False
        self.btn_toggle_ids.clicked.connect(self._toggle_ids_panel)

        gl.setRowStretch(row, 1)

        # RIGHT: log
        right = QWidget()
        vr = QVBoxLayout(right); vr.setContentsMargins(8, 8, 8, 8); vr.setSpacing(8)
        vr.addWidget(QLabel("Лог:"))
        self.txt_log = QTextEdit(); self.txt_log.setReadOnly(True)
        vr.addWidget(self.txt_log, 1)
        self.btn_clear = QPushButton("Очистить лог")
        al = QHBoxLayout(); al.setContentsMargins(0, 0, 0, 0); al.setSpacing(6)
        al.addStretch(1); al.addWidget(self.btn_clear); vr.addLayout(al)

        left_scroll = QScrollArea(self)
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setWidget(left)

        splitter.addWidget(left_scroll)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)  # левая колонка – по содержимому + скролл
        splitter.setStretchFactor(1, 1)  # правая – тянется
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
        self.btn_reset.clicked.connect(self.reset_to_defaults)

        # --- Persist UI changes to INI (explicit wiring) ---
        # Текстовые поля — по окончании редактирования
        self.ed_title.editingFinished.connect(
            lambda: self._save_str_ini("title", self.ed_title.text().strip())
        )
        self.ed_spec.editingFinished.connect(
            lambda: self._save_str_ini("spec", self.ed_spec.text().strip())
        )

        # Режим уже сохраняется в _persist_mode() через rb_number/id/index
        # см. self.rb_number.toggled.connect(self._persist_mode) и т.д.

        # Числа
        self.spin_minw.valueChanged.connect(
            lambda v: self._save_int_ini("min_width", int(v))
        )
        self.spin_width.valueChanged.connect(
            lambda v: self._save_int_ini("target_width", int(v))
        )
        self.spin_comp.valueChanged.connect(
            lambda v: self._save_int_ini("compress_level", int(v))
        )
        self.spin_per.valueChanged.connect(
            lambda v: self._save_int_ini("per", int(v))
        )

        # Чекбоксы автосклейки и опций PNG
        self.chk_auto.toggled.connect(
            lambda v: self._save_bool_ini("auto_stitch", bool(v))
        )  # плюс твой _on_auto_toggled — ок, оба можно оставить
        self.chk_no_resize.toggled.connect(
            lambda v: self._save_bool_ini("no_resize_width", bool(v))
        )
        self.chk_same_dir.toggled.connect(
            lambda v: self._save_bool_ini("same_dir", bool(v))
        )
        self.chk_delete.toggled.connect(
            lambda v: self._save_bool_ini("delete_sources", bool(v))
        )
        self.chk_opt.toggled.connect(
            lambda v: self._save_bool_ini("optimize_png", bool(v))
        )
        self.chk_strip.toggled.connect(
            lambda v: self._save_bool_ini("strip_metadata", bool(v))
        )

        # Папки уже сохраняются внутри _pick_out() / _pick_stitch_dir()
        # (save_attr_string(self, "_out_dir"/"_stitch_dir", ...))

        self._out_dir = ""
        self._stitch_dir = ""



        # Первичная настройка доступности
        self._update_auto_enabled()
        self._update_no_resize()
        self._update_same_dir()
        self._update_mode()

    def showEvent(self, e):
        super().showEvent(e)
        if getattr(self, "_ini_applied", False):
            return
        self._ini_applied = True

        # На время массовых выставлений значений — режем перерисовку и сигналы
        self.setUpdatesEnabled(False)
        try:
            self.blockSignals(True)
            self._apply_settings_from_ini()
        finally:
            self.blockSignals(False)
            self.setUpdatesEnabled(True)

    def _ensure_ids_loaded(self):
        """Ленивая загрузка JSON и построение таблицы один раз."""
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

        # вставляем в плейсхолдер и прячем
        self._ids_slot.addWidget(ids_grp)
        ids_grp.setVisible(False)
        self._ids_ui_built = True

    def _toggle_ids_panel(self):
        if not getattr(self, "_ids_ui_built", False):
            self._build_ids_ui()
        if not self._ids_loaded:
            self._ensure_ids_loaded()
        visible = self._ids_grp.isVisible()
        self._ids_grp.setVisible(not visible)
        self.btn_toggle_ids.setText("Скрыть сохранённые ID" if not visible else "Показать сохранённые ID")

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

    # ============ Bank of IDs (JSON) ============

    def _settings_dir(self) -> str:
        """Кэшируемый поиск папки для settings.ini c единовременной проверкой записи."""
        # 1) Кэш: повторные вызовы — мгновенные
        cached = getattr(self, "_settings_dir_cached", None)
        if cached:
            return cached

        def _is_writable(dir_path: str) -> bool:
            try:
                os.makedirs(dir_path, exist_ok=True)
                test = os.path.join(dir_path, ".write_test")
                with open(test, "w", encoding="utf-8") as f:
                    f.write("")
                os.remove(test)
                return True
            except Exception:
                return False

        # 2) Основная логика определения base
        base: str | None = None
        try:
            if getattr(sys, "frozen", False):  # PyInstaller/exe
                base = os.path.dirname(sys.executable)
            else:
                # 2.1) CWD с settings.ini
                cwd = os.getcwd()
                if os.path.exists(os.path.join(cwd, "settings.ini")):
                    base = cwd
                else:
                    # 2.2) Поднимаемся от текущего файла, ищем settings.ini
                    p = pathlib.Path(__file__).resolve()
                    for parent in [p.parent, *p.parents]:
                        if (parent / "settings.ini").exists():
                            base = str(parent)
                            break
                    # 2.3) Если не нашли — CWD
                    if not base:
                        base = cwd

            # 3) Если выбранная папка не подходит для записи — фоллбэки
            if not _is_writable(base):
                # AppDataLocation (например, C:\Users\<User>\AppData\Roaming\<App>)
                app_data = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or ""
                if app_data and _is_writable(app_data):
                    base = app_data
                else:
                    # Домашняя папка
                    home = os.path.expanduser("~")
                    base = home if _is_writable(home) else os.getcwd()  # на худой конец — CWD
        except Exception:
            # На любой сбой — уходим в домашнюю
            home = os.path.expanduser("~")
            base = home if os.path.isdir(home) else os.getcwd()

        # 4) Закэшировать и вернуть
        self._settings_dir_cached = base
        return base

    def _ids_json_path(self) -> str:
        # JSON всегда рядом с settings.ini / exe
        return os.path.join(self._settings_dir(), "values.json")

    def _load_ids_json(self) -> list[dict]:
        blob = self._load_all_values()
        raw = blob.get("manhwa_ids", [])
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
        blob["manhwa_ids"] = self._ids
        self._save_all_values(blob)

    def _rebuild_ids_ui(self):
        self.ids_table.setUpdatesEnabled(False)
        self.ids_table.blockSignals(True)
        try:
            self.ids_table.setRowCount(len(self._ids))
            for row, item in enumerate(self._ids):
                self.ids_table.setItem(row, 0, QTableWidgetItem(item.get("name", "")))
                self.ids_table.setItem(row, 1, QTableWidgetItem(item.get("id", "")))
        finally:
            self.ids_table.blockSignals(False)
            self.ids_table.setUpdatesEnabled(True)

    def _table_to_ids(self) -> list[dict]:
        data: list[dict] = []
        rows = self.ids_table.rowCount()
        for r in range(rows):
            name_item = self.ids_table.item(r, 0)
            id_item = self.ids_table.item(r, 1)
            name = name_item.text().strip() if name_item else ""
            _id = id_item.text().strip() if id_item else ""
            if name or _id:
                data.append({"name": name, "id": _id})
        return data

    def _refresh_ids_from_table_and_save(self):
        self._ids = self._table_to_ids()
        self._save_ids_json()

    def _on_ids_item_changed(self, item: QTableWidgetItem):
        # только планируем сохранение, если пользователь продолжит редактировать — диск не трогаем
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

    # ---------- UI helpers ----------
    def reset_to_defaults(self):
        # дефолты
        default_mode_idx = 0  # 0=number, 1=id, 2=index
        defaults = dict(
            title="",
            spec="",
            min_width=720,
            auto_stitch=True,
            no_resize_width=True,
            target_width=800,
            same_dir=True,
            # stitch_out_dir НЕ трогаем, чтобы не сбивать путь пользователю
            delete_sources=True,
            optimize_png=True,
            compress_level=6,
            strip_metadata=True,
            per=12,
        )

        # UI без лишних сигналов
        # режим
        self.rb_number.setChecked(default_mode_idx == 0)
        self.rb_id.setChecked(default_mode_idx == 1)
        self.rb_index.setChecked(default_mode_idx == 2)
        self._update_mode()

        # поля
        self.ed_title.setText(defaults["title"])
        self.ed_spec.setText(defaults["spec"])
        self.spin_minw.setValue(defaults["min_width"])

        # автосклейка
        self.chk_auto.setChecked(defaults["auto_stitch"])
        self.chk_no_resize.setChecked(defaults["no_resize_width"])
        self.spin_width.setValue(defaults["target_width"])
        self.chk_same_dir.setChecked(defaults["same_dir"])
        self.chk_delete.setChecked(defaults["delete_sources"])
        self.chk_opt.setChecked(defaults["optimize_png"])
        self.spin_comp.setValue(defaults["compress_level"])
        self.chk_strip.setChecked(defaults["strip_metadata"])
        self.spin_per.setValue(defaults["per"])

        # зависимые состояния
        self._update_auto_enabled()
        self._update_no_resize()
        self._update_same_dir()

        # сохранить в INI
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

    def _save_bool_ini(self, key: str, value: bool):
        # Надёжная запись булева флага в INI как "1"/"0"
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
        # храним как строку
        self._save_str_ini(key, str(int(value)))

    def _persist_mode(self):
        idx = 0 if self.rb_number.isChecked() else (1 if self.rb_id.isChecked() else 2)
        self._save_int_ini("mode", idx)
        self._update_mode()

    @Slot()
    def _pick_out(self):
        d = QFileDialog.getExistingDirectory(self, "Папка сохранения")
        if d:
            self._out_dir = d
            with group("ParserManhwa"):
                self.lbl_out.set_full_text(d)
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
            with group("ParserManhwa"):
                self.lbl_stitch_dir.set_full_text(d)
            self.lbl_stitch_dir.setText(d)
            self.lbl_stitch_dir.setStyleSheet("color:#080")

    def _update_auto_enabled(self):
        on = self.chk_auto.isChecked()
        for w in [
            self.chk_no_resize, self.spin_width, self.chk_same_dir, self.btn_pick_stitch,
            self.chk_delete, self.chk_opt, self.spin_comp, self.chk_strip, self.spin_per
        ]:
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

    def _on_auto_toggled(self, checked: bool):
        self._save_bool_ini("auto_stitch", checked)
        self._update_auto_enabled()

    def _show_purchase_dialog(self, price: int | None, balance: int | None, chapter_label: str | None) -> bool:
        head = chapter_label or "Покупка тикета"
        price_txt = f"{price} кредитов" if price is not None else "не удалось определить"
        bal_txt = f"{balance} кредитов" if balance is not None else "—"
        msg = (f"{head}\n\n"
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
        msg = (f"Глава {chapter_label}\n\n"
               f"Доступны тикеты:\n"
               f" • Аренда: {rental_count} шт\n"
               f" • Владение: {own_count} шт\n"
               f"Баланс: {bal_txt}\n\n"
               f"Использовать тикет аренды для этой главы?")
        return QMessageBox.question(
            self, "Использовать тикет?",
            msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        ) == QMessageBox.Yes

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
            auto_confirm_purchase=self.chk_auto_buy.isChecked(),
            auto_confirm_use_rental=self.chk_auto_use_ticket.isChecked(),
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

        self._worker.ask_purchase.connect(self._on_ask_purchase)
        self._worker.ask_use_rental.connect(self._on_ask_use_rental)

        self._worker.move_to_thread_and_start()
        self._set_running(True)

    @Slot(int, object)
    def _on_ask_purchase(self, price, balance):
        if self.chk_auto_buy.isChecked():
            ans = True
        else:
            head = getattr(self, "_last_ch_label", None) or "Покупка тикета"
            price_txt = f"{int(price)} кредитов" if price is not None else "не удалось определить"
            bal_txt = f"{int(balance)} кредитов" if balance is not None else "—"
            msg = f"{head}\n\nЦена: {price_txt}\nБаланс: {bal_txt}\n\nПродолжить покупку?"
            ans = QMessageBox.question(self, "Покупка главы", msg,
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes
        if self._worker:
            self._worker.provide_purchase_answer(bool(ans))

    @Slot(int, int, object, str)
    def _on_ask_use_rental(self, rental_count: int, own_count: int, balance, chapter_label: str):
        self._last_ch_label = chapter_label
        if self.chk_auto_use_ticket.isChecked():
            ans = True
        else:
            ans = self._show_use_ticket_dialog(
                rental_count, own_count,
                int(balance) if balance is not None else None,
                chapter_label
            )
        if self._worker:
            self._worker.provide_use_rental_answer(bool(ans))

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

    def _apply_settings_from_ini(self):
        # Чтение/привязка всех настроек из INI и отражение их в UI.
        # Для основных контролов используем строгие bind_*,
        # для необязательных/внешних — try_bind_* (не упадёт, если поля нет).
        with group("ParserManhwa"):
            # Пути (как атрибуты, не виджеты)
            bind_attr_string(self, "_out_dir", "out_dir", "")
            bind_attr_string(self, "_stitch_dir", "stitch_dir", "")

            # Текстовые поля
            bind_line_edit(self.ed_title, "title", "")
            bind_line_edit(self.ed_spec, "spec", "")
            try_bind_line_edit(self, "ed_vol", "volumes", "")
            try_bind_checkbox(self, "chk_auto_buy", "auto_buy", False)
            try_bind_checkbox(self, "chk_auto_use_ticket", "auto_use_ticket", False)

            # Числовые поля
            bind_spinbox(self.spin_minw, "min_width", 720)
            bind_spinbox(self.spin_width, "target_width", 800)
            bind_spinbox(self.spin_comp, "compress_level", 6)
            bind_spinbox(self.spin_per, "per", 12)

            # Переключатели режима
            bind_radiobuttons([self.rb_number, self.rb_id, self.rb_index], "mode", 0)

            # Чекбоксы автосклейки и опций PNG
            bind_checkbox(self.chk_auto, "auto_stitch", True)  # ← сохраняем «Включить автосклейку»
            bind_checkbox(self.chk_no_resize, "no_resize_width", True)
            bind_checkbox(self.chk_same_dir, "same_dir", True)
            bind_checkbox(self.chk_delete, "delete_sources", True)
            bind_checkbox(self.chk_opt, "optimize_png", True)
            bind_checkbox(self.chk_strip, "strip_metadata", True)

        # Отразим пути в подписи (цвет — зелёный если задано)
        self.lbl_out.set_full_text(self._out_dir or "— не выбрано —")
        self.lbl_out.setStyleSheet("color:#228B22" if self._out_dir else "color:#B32428")
        self.btn_run.setEnabled(bool(self._out_dir))
        self.btn_open_dir.setEnabled(bool(self._out_dir))

        self.lbl_stitch_dir.set_full_text(self._stitch_dir or "— не выбрано —")
        self.lbl_stitch_dir.setStyleSheet("color:#228B22" if self._stitch_dir else "color:#B32428")

        # Обновим подписи/плейсхолдеры под выбранный режим
        self._update_mode()

        # Приведём доступность контролов к актуальному состоянию
        self.chk_auto.toggled.connect(self._on_auto_toggled)
        self._update_no_resize()
        self._update_same_dir()

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QLabel, QSpinBox, QCheckBox, QPushButton, QHBoxLayout, QSizePolicy, QTextEdit, QGroupBox, QComboBox
)
from PySide6.QtCore import Qt
from smithanatool_qt.widgets.collapsible import CollapsibleSection
from .manhwa_tab_elided_label import ElidedLabel

def build_auto_stitch_section(self):
    auto_panel = QWidget()
    v = QVBoxLayout(auto_panel)
    v.setContentsMargins(8, 8, 8, 8)
    v.setSpacing(10)

    # Переключатель автосклейки
    self.chk_auto = QCheckBox("Включить автосклейку"); self.chk_auto.setChecked(True)
    v.addWidget(self.chk_auto)

    # === Склейка ===
    row_mode = QHBoxLayout()
    self.lbl_mode = QLabel("Режим:")
    self.lbl_mode.setStyleSheet("QLabel:disabled{color:#454545;}")
    row_mode.addWidget(self.lbl_mode)
    self.combo_auto_mode = QComboBox()
    self.combo_auto_mode.addItems(["По количеству фрагментов", "По высоте"])
    row_mode.addWidget(self.combo_auto_mode)
    row_mode.addStretch(1)

    # === Группировка + Нули ===
    row_grouping = QHBoxLayout()
    row_grouping.setContentsMargins(0, 0, 0, 0)
    row_grouping.setSpacing(6)

    self.lbl_per = QLabel("По сколько клеить:")
    self.spin_per = QSpinBox()
    self.spin_per.setRange(2, 999)
    self.spin_per.setValue(12)

    self.lbl_max_h = QLabel("Макс. высота (px):")
    self.spin_max_h = QSpinBox()
    self.spin_max_h.setRange(100, 100000)
    self.spin_max_h.setSingleStep(50)
    self.spin_max_h.setValue(10000)
    self.spin_max_h.setMinimumWidth(60)

    row_grouping.addWidget(self.lbl_per)
    row_grouping.addWidget(self.spin_per)
    row_grouping.addWidget(self.lbl_max_h)
    row_grouping.addWidget(self.spin_max_h)

    row_grouping.addSpacing(16)
    self.lbl_zeros = QLabel("Нули:")
    self.spin_zeros = QSpinBox()
    self.spin_zeros.setRange(1, 6)
    self.spin_zeros.setValue(2)
    row_grouping.addWidget(self.lbl_zeros)
    row_grouping.addWidget(self.spin_zeros)
    row_grouping.addStretch(1)
    # === ГРУППБОКС "Склейка" ===
    self.grp_stitch_opts = QGroupBox("Склейка")
    lay_stitch = QVBoxLayout(self.grp_stitch_opts)
    lay_stitch.setContentsMargins(8, 8, 8, 8)
    lay_stitch.setSpacing(6)

    # Режим
    lay_stitch.addLayout(row_mode)

    # Группировка + Нули
    lay_stitch.addLayout(row_grouping)

    v.addWidget(self.grp_stitch_opts)


    # === Удалять исходники после склейки
    self.chk_delete_sources = QCheckBox("Удалять исходники после склейки")
    self.chk_delete_sources.setChecked(True)

    # === Папка для склеек ===
    self.chk_same_dir = QCheckBox("Сохранять в той же папке, где и исходники");
    self.chk_same_dir.setChecked(True)

    row_pick = QHBoxLayout();
    row_pick.setContentsMargins(0, 0, 0, 0);
    row_pick.setSpacing(6)
    self.lbl_stitch_text = QLabel("Папка для склеек:")
    self.lbl_stitch_text.setStyleSheet("QLabel:disabled{color:#454545;}")
    self.btn_pick_stitch = QPushButton("Выбрать…")
    self.lbl_stitch_dir = ElidedLabel("— не выбрано —")
    self.lbl_stitch_dir.setStyleSheet("color:#a00; QLabel:disabled{color:#454545;}")
    self.btn_pick_stitch.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    self.lbl_stitch_dir.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    row_pick.addWidget(self.lbl_stitch_text)
    row_pick.addWidget(self.btn_pick_stitch)
    row_pick.addWidget(self.lbl_stitch_dir, 1)

    # === ГРУППБОКС "Настройка" ===
    self.grp_setup = QGroupBox("Файлы")
    lay_setup = QVBoxLayout(self.grp_setup)
    lay_setup.setContentsMargins(8, 8, 8, 8)
    lay_setup.setSpacing(6)
    # чекбоксы настройки
    lay_setup.addWidget(self.chk_delete_sources)
    lay_setup.addWidget(self.chk_same_dir)

    pick_row_widget = QWidget()
    pick_row = QHBoxLayout(pick_row_widget)
    pick_row.setContentsMargins(0, 0, 0, 0)
    pick_row.setSpacing(6)
    pick_row.addWidget(self.lbl_stitch_text)
    pick_row.addWidget(self.btn_pick_stitch)
    pick_row.addWidget(self.lbl_stitch_dir, 1)
    lay_setup.addWidget(pick_row_widget)

    # логика включения/отключения выбора папки
    def _apply_save_dir_state():
        enable_dir = not self.chk_same_dir.isChecked()
        self.lbl_stitch_text.setEnabled(enable_dir)
        self.btn_pick_stitch.setEnabled(enable_dir)
        self.lbl_stitch_dir.setEnabled(enable_dir)

    self.chk_same_dir.toggled.connect(_apply_save_dir_state)
    _apply_save_dir_state()

    v.addWidget(self.grp_setup)




    # === РАЗМЕР ===
    self.grp_dim = QGroupBox("Размер")
    row_dim = QHBoxLayout(self.grp_dim)
    self.chk_no_resize = QCheckBox("Не изменять ширину"); self.chk_no_resize.setChecked(True)
    self.lbl_width = QLabel("Ширина (px):")
    self.spin_width = QSpinBox(); self.spin_width.setRange(50, 20000); self.spin_width.setValue(800)
    self.spin_width.setMinimumWidth(60)

    row_dim.addWidget(self.chk_no_resize)
    row_dim.addSpacing(8)
    row_dim.addWidget(self.lbl_width)
    row_dim.addWidget(self.spin_width)
    row_dim.addStretch(1)
    v.addWidget(self.grp_dim)


    # === ОПЦИИ PNG ===
    self.grp_png = QGroupBox("Опции PNG")  # ← сохранить ссылку
    v_png = QVBoxLayout(self.grp_png)

    # строка 1 — оптимизация + уровень сжатия
    row_png1 = QHBoxLayout()
    self.chk_opt = QCheckBox("Оптимизировать PNG"); self.chk_opt.setChecked(True)
    self.lbl_comp = QLabel("Уровень сжатия (0–9):")
    self.spin_comp = QSpinBox(); self.spin_comp.setRange(0, 9); self.spin_comp.setValue(6)
    row_png1.addWidget(self.chk_opt)
    row_png1.addSpacing(12)
    row_png1.addWidget(self.lbl_comp)
    row_png1.addWidget(self.spin_comp)
    row_png1.addStretch(1)
    v_png.addLayout(row_png1)

    # строка 2 — удаление метаданных
    row_png2 = QHBoxLayout()
    self.chk_strip = QCheckBox("Удалять метаданные"); self.chk_strip.setChecked(True)
    row_png2.addWidget(self.chk_strip); row_png2.addStretch(1)
    v_png.addLayout(row_png2)

    v.addWidget(self.grp_png)


    # --- Локальные функции для такого же UX, как в stitch_section ---
    def _apply_dim_state():
        on = not self.chk_no_resize.isChecked()
        self.spin_width.setEnabled(on)
        self.lbl_width.setEnabled(on)

    def _apply_comp_state(optimize_on: bool):
        self.spin_comp.setEnabled(not optimize_on)
        self.lbl_comp.setEnabled(not optimize_on)
        if optimize_on:
            self.spin_comp.setToolTip("Оптимизация PNG включена — изменение уровня даёт умеренный эффект.")
        else:
            self.spin_comp.setToolTip("Уровень DEFLATE 0–9: выше — дольше и немного меньше файл.")

    # Привязываем сигналы и применяем начальное состояние
    self.chk_no_resize.toggled.connect(_apply_dim_state)
    _apply_dim_state()

    self.chk_opt.toggled.connect(_apply_comp_state)
    _apply_comp_state(self.chk_opt.isChecked())

    # --- Переключение режима + видимость полей
    def _apply_group_by():
        by = "count" if self.combo_auto_mode.currentIndex() == 0 else "height"
        show_count = (by == "count")
        self.lbl_per.setVisible(show_count)
        self.spin_per.setVisible(show_count)
        self.lbl_max_h.setVisible(not show_count)
        self.spin_max_h.setVisible(not show_count)

    def _save_group_by():
        by = "count" if self.combo_auto_mode.currentIndex() == 0 else "height"
        if hasattr(self, "_save_str_ini"):
            self._save_str_ini("group_by", by)

    # реагируем на выбор режима
    self.combo_auto_mode.currentIndexChanged.connect(lambda _: (_apply_group_by(), _save_group_by()))
    # сохраняем высоту
    if hasattr(self, "_save_int_ini"):
        self.spin_max_h.valueChanged.connect(lambda v: self._save_int_ini("group_max_height", int(v)))

    # применить начальное состояние из INI (установим позже в parser_manhwa_tab)
    _apply_group_by()


    return CollapsibleSection("Автосклейка", auto_panel, expanded=False)


def build_extra_settings_section(self):
    extra_panel = QWidget()
    ev = QVBoxLayout(extra_panel)
    ev.setContentsMargins(8, 8, 8, 8)
    ev.setSpacing(6)


    # Удаление кэша
    self.chk_delete_cache = QCheckBox("Удалять urls.json после загрузки")
    self.chk_delete_cache.setChecked(True)
    ev.addWidget(self.chk_delete_cache)

    self.chk_delete = self.chk_delete_sources

    # Время прокрутки viewer
    hl = QHBoxLayout()
    hl.setContentsMargins(0, 0, 0, 0)
    hl.setSpacing(6)

    hl.addWidget(QLabel("Время прокрутки (мс):"))

    self.spin_scroll_ms = QSpinBox()
    self.spin_scroll_ms.setRange(3000, 180000)
    self.spin_scroll_ms.setSingleStep(1000)
    self.spin_scroll_ms.setValue(30000)
    self.spin_scroll_ms.setFixedWidth(60)
    hl.addWidget(self.spin_scroll_ms)


    hl.addStretch(1)  # ← лишнее место уходит вправо, поле рядом с подписью
    ev.addLayout(hl)

    note = QLabel(
        "Сколько времени viewer прокручивается, чтобы подгрузились все страницы.\n"
        "Если часть картинок не попадает в загрузку — увеличьте значение."
    )
    note.setWordWrap(True)
    note.setStyleSheet("color:#454545; font-size:12px;")
    ev.addWidget(note)

    ev.addStretch(1)
    return CollapsibleSection("Доп. настройки", extra_panel, expanded=False)


def build_right_log_panel(self):
    from PySide6.QtWidgets import QVBoxLayout, QLabel, QPushButton, QWidget, QHBoxLayout, QSizePolicy
    right = QWidget()
    vr = QVBoxLayout(right); vr.setContentsMargins(0, 15, 15, 0); vr.setSpacing(11)
    vr.addWidget(QLabel("Лог:"))
    self.txt_log = QTextEdit(); self.txt_log.setReadOnly(True)
    vr.addWidget(self.txt_log, 1)
    self.btn_clear = QPushButton("Очистить лог")
    self.btn_del_sess = QPushButton("Удалить сессию")


    self.lbl_session_hint = QLabel(
        "С течением времени срок сессии может истечь.\n"
        "Если главу не удаётся скачать, то удалите сессию и авторизуйтесь заново."
    )
    self.lbl_session_hint.setWordWrap(True)
    self.lbl_session_hint.setStyleSheet("color: #a9a9a9; font-size: 11px;")
    self.lbl_session_hint.setMinimumWidth(400)
    self.lbl_session_hint.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    al = QHBoxLayout(); al.setContentsMargins(0, 0, 0, 0); al.setSpacing(6)
    al.addWidget(self.lbl_session_hint, 1)
    al.addStretch(1)
    al.addWidget(self.btn_del_sess)
    al.addWidget(self.btn_clear)
    vr.addLayout(al)
    return right

def build_footer(self, left_outer_layout):
    from PySide6.QtWidgets import QHBoxLayout, QPushButton
    left_footer = QHBoxLayout()
    left_footer.setContentsMargins(8, 11, 8, 0)
    left_footer.setSpacing(0)
    self.btn_reset = QPushButton("Сброс настроек")
    self.btn_reset.setFixedWidth(100)
    left_footer.addStretch(1)
    left_footer.addWidget(self.btn_reset)
    left_outer_layout.addLayout(left_footer)

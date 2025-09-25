from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QLabel, QSpinBox, QCheckBox, QPushButton, QHBoxLayout, QSizePolicy, QTextEdit
)
from PySide6.QtCore import Qt
from smithanatool_qt.widgets.collapsible import CollapsibleSection
from .manhwa_tab_elided_label import ElidedLabel

def build_auto_stitch_section(self):
    auto_panel = QWidget()
    v = QVBoxLayout(auto_panel)
    v.setContentsMargins(8, 8, 8, 8)
    v.setSpacing(6)

    self.chk_auto = QCheckBox("Включить автосклейку"); self.chk_auto.setChecked(True)
    v.addWidget(self.chk_auto)

    rowa = QGridLayout(); v.addLayout(rowa)
    r = 0
    self.chk_no_resize = QCheckBox("Не изменять ширину"); self.chk_no_resize.setChecked(True)
    rowa.addWidget(self.chk_no_resize, r, 0, 1, 2); r += 1
    rowa.addWidget(QLabel("Ширина:"), r, 0)
    self.spin_width = QSpinBox(); self.spin_width.setRange(50, 20000); self.spin_width.setValue(800)
    rowa.addWidget(self.spin_width, r, 1); r += 1

    self.chk_same_dir = QCheckBox("Сохранять в той же папке, где и исходники"); self.chk_same_dir.setChecked(True)
    rowa.addWidget(self.chk_same_dir, r, 0, 1, 2); r += 1

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

    rowa.addWidget(QLabel("Опции PNG:"), r, 0); r += 1
    self.chk_opt = QCheckBox("Оптимизировать PNG"); self.chk_opt.setChecked(True)
    self.chk_strip = QCheckBox("Удалять метаданные"); self.chk_strip.setChecked(True)
    self.spin_comp = QSpinBox(); self.spin_comp.setRange(0, 9); self.spin_comp.setValue(6)

    hl3 = QHBoxLayout(); hl3.setContentsMargins(0, 0, 0, 0); hl3.setSpacing(6)
    self.lbl_comp = QLabel("Уровень сжатия (0-9):")
    hl3.addWidget(self.chk_opt); hl3.addWidget(self.lbl_comp); hl3.addWidget(self.spin_comp); hl3.addStretch(1)
    v.addLayout(hl3)

    hl3b = QHBoxLayout(); hl3b.setContentsMargins(0, 0, 0, 0); hl3b.setSpacing(6)
    hl3b.addWidget(self.chk_strip); hl3b.addStretch(1)
    v.addLayout(hl3b)

    hl4 = QHBoxLayout(); hl4.setContentsMargins(0, 0, 0, 0); hl4.setSpacing(6)
    hl4.addWidget(QLabel("По сколько клеить:"))
    self.spin_per = QSpinBox(); self.spin_per.setRange(1, 999); self.spin_per.setValue(12)
    hl4.addWidget(self.spin_per); hl4.addStretch(1)
    v.addLayout(hl4)

    return CollapsibleSection("Автосклейка", auto_panel, expanded=False)

def build_extra_settings_section(self):
    extra_panel = QWidget()
    ev = QVBoxLayout(extra_panel)
    ev.setContentsMargins(8, 8, 8, 8)
    ev.setSpacing(6)


    # 1) Удаление кэша
    self.chk_delete_cache = QCheckBox("Удалять urls.json после загрузки")
    self.chk_delete_cache.setChecked(True)
    ev.addWidget(self.chk_delete_cache)

    # 2) Время прокрутки viewer
    row = QGridLayout(); ev.addLayout(row)
    row.addWidget(QLabel("Время прокрутки (мс):"), 0, 0, Qt.AlignLeft)
    self.spin_scroll_ms = QSpinBox()
    self.spin_scroll_ms.setRange(3000, 180000)
    self.spin_scroll_ms.setSingleStep(1000)
    self.spin_scroll_ms.setValue(30000)
    row.addWidget(self.spin_scroll_ms, 0, 1)

    note = QLabel(
        "Сколько времени viewer прокручивается, чтобы подгрузились все страницы.\n"
        "Если часть картинок не попадает в загрузку — увеличьте значение."
    )
    note.setWordWrap(True)
    note.setStyleSheet("color:#888; font-size:12px;")
    ev.addWidget(note)

    ev.addStretch(1)
    return CollapsibleSection("Доп. настройки", extra_panel, expanded=False)


def build_right_log_panel(self):
    from PySide6.QtWidgets import QVBoxLayout, QLabel, QPushButton, QWidget, QHBoxLayout, QSizePolicy
    right = QWidget()
    vr = QVBoxLayout(right); vr.setContentsMargins(8, 8, 8, 8); vr.setSpacing(8)
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
    self.lbl_session_hint.setTextFormat(Qt.PlainText)
    self.lbl_session_hint.setStyleSheet("color: #a9a9a9; font-size: 11px;")
    self.lbl_session_hint.setMinimumWidth(200)
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
    left_footer.setContentsMargins(8, 6, 8, 8)
    left_footer.setSpacing(0)
    self.btn_reset = QPushButton("Сброс настроек")
    self.btn_reset.setFixedHeight(28)
    self.btn_reset.setFixedWidth(100)
    left_footer.addStretch(1)
    left_footer.addWidget(self.btn_reset)
    left_outer_layout.addLayout(left_footer)

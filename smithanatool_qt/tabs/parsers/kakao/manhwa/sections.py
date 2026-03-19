from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from smithanatool_qt.widgets.collapsible import CollapsibleSection
from smithanatool_qt.tabs.parsers.common.parser_defaults import default_thread_count
from smithanatool_qt.tabs.parsers.common.ui_helpers import build_reset_footer
from ...common.widgets import ElidedLabel



def build_auto_stitch_section(self):
    auto_panel = QWidget()
    layout = QVBoxLayout(auto_panel)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(10)

    self.chk_auto = QCheckBox('Автосклейка')
    self.chk_auto.setChecked(True)
    layout.addWidget(self.chk_auto, alignment=Qt.AlignmentFlag.AlignHCenter)

    row_mode = QHBoxLayout()
    self.lbl_mode = QLabel('Режим:')
    self.lbl_mode.setStyleSheet('QLabel:disabled{color:#454545;}')
    self.combo_auto_mode = QComboBox()
    self.combo_auto_mode.addItems(['По количеству фрагментов', 'По высоте', 'SmartStitch'])
    row_mode.addWidget(self.lbl_mode)
    row_mode.addWidget(self.combo_auto_mode)
    row_mode.addStretch(1)

    row_simple = QHBoxLayout()
    row_simple.setContentsMargins(0, 0, 0, 0)
    row_simple.setSpacing(6)
    self.lbl_per = QLabel('По сколько клеить:')
    self.spin_per = QSpinBox()
    self.spin_per.setRange(2, 999)
    self.spin_per.setValue(12)

    self.lbl_max_h = QLabel('Макс. высота (px):')
    self.spin_max_h = QSpinBox()
    self.spin_max_h.setRange(100, 100000)
    self.spin_max_h.setSingleStep(50)
    self.spin_max_h.setValue(10000)
    self.spin_max_h.setMinimumWidth(60)

    row_simple.addWidget(self.lbl_per)
    row_simple.addWidget(self.spin_per)
    row_simple.addWidget(self.lbl_max_h)
    row_simple.addWidget(self.spin_max_h)
    row_simple.addStretch(1)

    smart_grid = QGridLayout()
    smart_grid.setContentsMargins(0, 0, 0, 0)
    smart_grid.setHorizontalSpacing(6)
    smart_grid.setVerticalSpacing(10)
    smart_grid.setColumnMinimumWidth(2, 14)
    smart_grid.setColumnStretch(5, 1)

    self.lbl_smart_height = QLabel('Высота (px):')
    self.spin_smart_height = QSpinBox()
    self.spin_smart_height.setRange(100, 30000)
    self.spin_smart_height.setSingleStep(50)
    self.spin_smart_height.setValue(8000)
    self.spin_smart_height.setMinimumWidth(60)

    self.lbl_smart_sensitivity = QLabel('Чувствительность (%):')
    self.spin_smart_sensitivity = QSpinBox()
    self.spin_smart_sensitivity.setRange(0, 100)
    self.spin_smart_sensitivity.setValue(90)
    self.spin_smart_sensitivity.setMinimumWidth(60)

    self.lbl_smart_scan_step = QLabel('Шаг сканирования:')
    self.spin_smart_scan_step = QSpinBox()
    self.spin_smart_scan_step.setRange(1, 200)
    self.spin_smart_scan_step.setValue(5)
    self.spin_smart_scan_step.setMinimumWidth(60)

    self.lbl_smart_ignore = QLabel('Игнорировать края (px):')
    self.spin_smart_ignore = QSpinBox()
    self.spin_smart_ignore.setRange(0, 5000)
    self.spin_smart_ignore.setValue(5)
    self.spin_smart_ignore.setMinimumWidth(60)

    smart_grid.addWidget(self.lbl_smart_height, 0, 0)
    smart_grid.addWidget(self.spin_smart_height, 0, 1)
    smart_grid.addWidget(self.lbl_smart_sensitivity, 0, 3)
    smart_grid.addWidget(self.spin_smart_sensitivity, 0, 4)

    smart_grid.addWidget(self.lbl_smart_scan_step, 1, 0)
    smart_grid.addWidget(self.spin_smart_scan_step, 1, 1)
    smart_grid.addWidget(self.lbl_smart_ignore, 1, 3)
    smart_grid.addWidget(self.spin_smart_ignore, 1, 4)

    row_misc = QHBoxLayout()
    row_misc.setContentsMargins(0, 0, 0, 0)
    row_misc.setSpacing(6)
    self.lbl_zeros = QLabel('Нули:')
    self.spin_zeros = QSpinBox()
    self.spin_zeros.setRange(1, 6)
    self.spin_zeros.setValue(2)
    row_misc.addWidget(self.lbl_zeros)
    row_misc.addWidget(self.spin_zeros)
    row_misc.addStretch(1)

    self.grp_stitch_opts = QGroupBox('Склейка')
    lay_stitch = QVBoxLayout(self.grp_stitch_opts)
    lay_stitch.setContentsMargins(8, 8, 8, 8)
    lay_stitch.setSpacing(6)
    lay_stitch.addLayout(row_mode)
    lay_stitch.addLayout(row_simple)
    lay_stitch.addLayout(smart_grid)
    layout.addWidget(self.grp_stitch_opts)

    self.chk_delete_sources = QCheckBox('Удалять исходники после склейки')
    self.chk_delete_sources.setChecked(True)
    self.chk_same_dir = QCheckBox('Сохранять в той же папке, где и исходники')
    self.chk_same_dir.setChecked(True)

    self.lbl_stitch_text = QLabel('Папка для склеек:')
    self.lbl_stitch_text.setStyleSheet('QLabel:disabled{color:#454545;}')
    self.btn_pick_stitch = QPushButton('Выбрать…')
    self.lbl_stitch_dir = ElidedLabel('— не выбрано —')
    self.lbl_stitch_dir.setStyleSheet('color:#a00; QLabel:disabled{color:#454545;}')
    self.btn_pick_stitch.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    self.lbl_stitch_dir.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    pick_row_widget = QWidget()
    pick_row = QHBoxLayout(pick_row_widget)
    pick_row.setContentsMargins(0, 0, 0, 0)
    pick_row.setSpacing(6)
    pick_row.addWidget(self.lbl_stitch_text)
    pick_row.addWidget(self.btn_pick_stitch)
    pick_row.addWidget(self.lbl_stitch_dir, 1)

    self.grp_setup = QGroupBox('Файлы')
    lay_setup = QVBoxLayout(self.grp_setup)
    lay_setup.setContentsMargins(8, 8, 8, 8)
    lay_setup.setSpacing(6)
    lay_setup.addWidget(self.chk_delete_sources)
    lay_setup.addWidget(self.chk_same_dir)
    lay_setup.addWidget(pick_row_widget)
    layout.addWidget(self.grp_setup)

    self.grp_dim = QGroupBox('Настройки')
    dim_layout = QVBoxLayout(self.grp_dim)
    dim_layout.setContentsMargins(8, 8, 8, 8)
    dim_layout.setSpacing(6)

    row_dim = QHBoxLayout()
    row_dim.setContentsMargins(0, 0, 0, 0)
    row_dim.setSpacing(6)
    self.chk_no_resize = QCheckBox('Не изменять ширину')
    self.chk_no_resize.setChecked(True)
    self.lbl_width = QLabel('Ширина (px):')
    self.spin_width = QSpinBox()
    self.spin_width.setRange(50, 20000)
    self.spin_width.setValue(800)
    self.spin_width.setMinimumWidth(60)
    row_dim.addWidget(self.chk_no_resize)
    row_dim.addSpacing(8)
    row_dim.addWidget(self.lbl_width)
    row_dim.addWidget(self.spin_width)
    row_dim.addStretch(1)
    dim_layout.addLayout(row_dim)
    dim_layout.addLayout(row_misc)
    layout.addWidget(self.grp_dim)

    self.grp_png = QGroupBox('Опции PNG')
    png_layout = QVBoxLayout(self.grp_png)

    row_png1 = QHBoxLayout()
    self.chk_opt = QCheckBox('Оптимизировать PNG')
    self.chk_opt.setChecked(True)
    self.lbl_comp = QLabel('Уровень сжатия (0–9):')
    self.spin_comp = QSpinBox()
    self.spin_comp.setRange(0, 9)
    self.spin_comp.setValue(6)
    row_png1.addWidget(self.chk_opt)
    row_png1.addSpacing(12)
    row_png1.addWidget(self.lbl_comp)
    row_png1.addWidget(self.spin_comp)
    row_png1.addStretch(1)
    png_layout.addLayout(row_png1)

    row_png2 = QHBoxLayout()
    self.chk_strip = QCheckBox('Удалять метаданные')
    self.chk_strip.setChecked(True)
    row_png2.addWidget(self.chk_strip)
    row_png2.addStretch(1)
    png_layout.addLayout(row_png2)

    layout.addWidget(self.grp_png)
    return CollapsibleSection('Автосклейка', auto_panel, expanded=False)



def build_extra_settings_group(self):
    grp_extra = QGroupBox('Доп. настройки')
    layout = QVBoxLayout(grp_extra)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(6)

    threads_row = QHBoxLayout()
    threads_row.setContentsMargins(0, 0, 0, 0)
    threads_row.setSpacing(6)
    self.chk_auto_threads = QCheckBox('Авто потоки')
    self.chk_auto_threads.setChecked(True)
    self.spin_threads = QSpinBox()
    self.spin_threads.setRange(1, 32)
    self.spin_threads.setValue(default_thread_count())
    self.lbl_threads = QLabel('Потоки:')
    threads_row.addWidget(self.chk_auto_threads)
    threads_row.addSpacing(8)
    threads_row.addWidget(self.lbl_threads)
    threads_row.addWidget(self.spin_threads)
    threads_row.addStretch(1)
    layout.addLayout(threads_row)

    row_scroll = QHBoxLayout()
    row_scroll.setContentsMargins(0, 0, 0, 0)
    row_scroll.setSpacing(6)
    row_scroll.addWidget(QLabel('Время прокрутки (мс):'))
    self.spin_scroll_ms = QSpinBox()
    self.spin_scroll_ms.setRange(3000, 180000)
    self.spin_scroll_ms.setSingleStep(1000)
    self.spin_scroll_ms.setValue(8000)
    self.spin_scroll_ms.setFixedWidth(60)
    row_scroll.addWidget(self.spin_scroll_ms)
    row_scroll.addStretch(1)
    layout.addLayout(row_scroll)

    note = QLabel(
        'Сколько времени viewer прокручивается, чтобы подгрузились все страницы.\n'
        'Если часть картинок не попадает в загрузку — увеличьте значение.'
    )
    note.setWordWrap(True)
    note.setProperty('role', 'hint')
    layout.addWidget(note)
    layout.addStretch(1)
    return grp_extra



def build_footer(self, left_outer_layout):
    build_reset_footer(self, left_outer_layout)

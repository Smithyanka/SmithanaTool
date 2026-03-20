from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)


class StitchSectionUiMixin:
    def _build_mode_row(self, root: QVBoxLayout):
        row = QHBoxLayout()
        row.addStretch(1)

        self.rb_one = QRadioButton("Ручная")
        self.rb_auto = QRadioButton("Пакетная")
        self.rb_smart = QRadioButton("Склейка+Нарезка")

        self._stitch_mode_group = QButtonGroup(self)
        self._stitch_mode_group.addButton(self.rb_one)
        self._stitch_mode_group.addButton(self.rb_auto)
        self._stitch_mode_group.addButton(self.rb_smart)

        row.addWidget(self.rb_one)
        row.addSpacing(24)
        row.addWidget(self.rb_auto)
        row.addSpacing(24)
        row.addWidget(self.rb_smart)
        row.addStretch(1)
        root.addLayout(row)

    def _build_multi_group(self, root: QVBoxLayout):
        self.grp_auto = QGroupBox("Склейка")
        layout = QVBoxLayout(self.grp_auto)

        row_mode = QHBoxLayout()
        row_mode.addWidget(QLabel("Режим:"))
        self.combo_auto_mode = QComboBox()
        self.combo_auto_mode.addItems(["По количеству фрагментов", "По высоте"])
        row_mode.addWidget(self.combo_auto_mode)
        row_mode.addStretch(1)
        layout.addLayout(row_mode)

        row_params = QHBoxLayout()
        self.lbl_group = QLabel("По сколько клеить:")
        self.spin_group = QSpinBox()
        self.spin_group.setRange(2, 999)
        self.spin_group.setValue(12)

        self.lbl_max_h = QLabel("Высота (px):")
        self.spin_max_h = QSpinBox()
        self.spin_max_h.setRange(100, 100000)
        self.spin_max_h.setSingleStep(50)
        self.spin_max_h.setValue(10000)

        row_params.addWidget(self.lbl_group)
        row_params.addWidget(self.spin_group)
        row_params.addWidget(self.lbl_max_h)
        row_params.addWidget(self.spin_max_h)
        row_params.addStretch(1)
        layout.addLayout(row_params)

        row_threads = QHBoxLayout()
        self.chk_auto_threads = QCheckBox("Авто потоки")
        self.chk_auto_threads.setChecked(True)
        self.lbl_threads = QLabel("Потоки:")
        self.spin_threads = QSpinBox()
        self.spin_threads.setRange(1, 32)
        self.spin_threads.setValue(min(32, max(2, (os.cpu_count() or 4) // 2)))
        row_threads.addWidget(self.chk_auto_threads)
        row_threads.addSpacing(12)
        row_threads.addWidget(self.lbl_threads)
        row_threads.addWidget(self.spin_threads)
        row_threads.addStretch(1)
        layout.addLayout(row_threads)

        root.addWidget(self.grp_auto)

    def _build_smart_group(self, root: QVBoxLayout):
        self.grp_smart = QGroupBox("Склейка")
        layout = QVBoxLayout(self.grp_smart)
        layout.setSpacing(8)

        row_mode = QHBoxLayout()
        row_mode.addWidget(QLabel("Режим:"))
        self.combo_smart_detector = QComboBox()
        self.combo_smart_detector.addItems(["SmartStitch", "По высоте"])
        row_mode.addWidget(self.combo_smart_detector)
        row_mode.addStretch(1)
        layout.addLayout(row_mode)

        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(10)
        grid.setColumnMinimumWidth(2, 14)
        grid.setColumnStretch(5, 1)

        self.lbl_smart_height = QLabel("Высота (px):")
        self.spin_smart_height = QSpinBox()
        self.spin_smart_height.setRange(100, 30000)
        self.spin_smart_height.setSingleStep(50)
        self.spin_smart_height.setValue(8000)

        self.lbl_smart_sensitivity = QLabel("Чувствительность (%):")
        self.spin_smart_sensitivity = QSpinBox()
        self.spin_smart_sensitivity.setRange(0, 100)
        self.spin_smart_sensitivity.setValue(90)

        self.lbl_smart_scan_step = QLabel("Шаг сканирования:")
        self.spin_smart_scan_step = QSpinBox()
        self.spin_smart_scan_step.setRange(1, 200)
        self.spin_smart_scan_step.setValue(5)

        self.lbl_smart_ignore = QLabel("Игнорировать края (px):")
        self.spin_smart_ignore = QSpinBox()
        self.spin_smart_ignore.setRange(0, 5000)
        self.spin_smart_ignore.setValue(5)

        grid.addWidget(self.lbl_smart_height, 0, 0)
        grid.addWidget(self.spin_smart_height, 0, 1)
        grid.addWidget(self.lbl_smart_sensitivity, 0, 3)
        grid.addWidget(self.spin_smart_sensitivity, 0, 4)

        grid.addWidget(self.lbl_smart_scan_step, 1, 0)
        grid.addWidget(self.spin_smart_scan_step, 1, 1)
        grid.addWidget(self.lbl_smart_ignore, 1, 3)
        grid.addWidget(self.spin_smart_ignore, 1, 4)

        layout.addLayout(grid)
        root.addWidget(self.grp_smart)

    def _build_common_settings_group(self, root: QVBoxLayout):
        self.grp_settings = QGroupBox("Настройки")
        layout = QVBoxLayout(self.grp_settings)
        layout.setSpacing(8)

        row_dir = QHBoxLayout()
        row_dir.addWidget(QLabel("Направление склейки:"))
        self.cmb_dir = QComboBox()
        self.cmb_dir.addItems(["По вертикали", "По горизонтали"])
        row_dir.addWidget(self.cmb_dir)
        row_dir.addStretch(1)
        layout.addLayout(row_dir)

        row_dim = QHBoxLayout()
        self.chk_no_resize = QCheckBox("Не изменять ширину")
        self.lbl_dim = QLabel("Ширина:")
        self.spin_dim = QSpinBox()
        self.spin_dim.setRange(50, 20000)
        self.spin_dim.setValue(800)
        row_dim.addWidget(self.chk_no_resize)
        row_dim.addSpacing(8)
        row_dim.addWidget(self.lbl_dim)
        row_dim.addWidget(self.spin_dim)
        row_dim.addStretch(1)
        layout.addLayout(row_dim)

        row_zeros = QHBoxLayout()
        self.lbl_common_zeros = QLabel("Нули:")
        self.spin_zeros = QSpinBox()
        self.spin_zeros.setRange(1, 6)
        self.spin_zeros.setValue(2)
        self.spin_smart_zeros = QSpinBox()
        self.spin_smart_zeros.setRange(1, 6)
        self.spin_smart_zeros.setValue(2)
        row_zeros.addWidget(self.lbl_common_zeros)
        row_zeros.addWidget(self.spin_zeros)
        row_zeros.addWidget(self.spin_smart_zeros)
        row_zeros.addStretch(1)
        layout.addLayout(row_zeros)

        root.addWidget(self.grp_settings)

    def _build_png_group(self, root: QVBoxLayout):
        grp = QGroupBox("Опции PNG")
        layout = QVBoxLayout(grp)

        row1 = QHBoxLayout()
        self.chk_opt = QCheckBox("Оптимизировать PNG")
        self.chk_opt.setChecked(True)
        self.lbl_compress = QLabel("Уровень сжатия (0–9):")
        self.spin_compress = QSpinBox()
        self.spin_compress.setRange(0, 9)
        self.spin_compress.setValue(6)
        row1.addWidget(self.chk_opt)
        row1.addSpacing(12)
        row1.addWidget(self.lbl_compress)
        row1.addWidget(self.spin_compress)
        row1.addStretch(1)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        self.chk_strip = QCheckBox("Удалять метаданные")
        self.chk_strip.setChecked(True)
        row2.addWidget(self.chk_strip)
        row2.addStretch(1)
        layout.addLayout(row2)

        root.addWidget(grp)

    def _build_footer_buttons(self, root: QVBoxLayout):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addStretch(1)

        self.btn_run = QPushButton("Склеить")
        self.btn_pick = QPushButton("Выбрать файлы…")

        row.addWidget(self.btn_run)
        row.addWidget(self.btn_pick)
        root.addLayout(row)

    def _connect_signals(self):
        self.cmb_dir.currentIndexChanged.connect(self._update_dim_label)
        self.chk_no_resize.toggled.connect(self._apply_dim_state)
        self.chk_opt.toggled.connect(self._apply_compress_state)
        self.combo_auto_mode.currentIndexChanged.connect(self._on_auto_mode_changed)
        self.combo_smart_detector.currentIndexChanged.connect(self._on_smart_detector_changed)

        self.rb_one.toggled.connect(self._on_stitch_mode_changed)
        self.rb_auto.toggled.connect(self._on_stitch_mode_changed)
        self.rb_smart.toggled.connect(self._on_stitch_mode_changed)

        self.btn_run.clicked.connect(self._on_run_clicked)
        self.btn_pick.clicked.connect(self._on_pick_clicked)

        self.chk_auto_threads.toggled.connect(self._apply_threads_state)

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QRegularExpression, QSignalBlocker, Qt
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ...common.base_page import BaseParserPage
from ...common.parser_defaults import default_thread_count
from ...common.saved_ids_panel import SavedIdsPanel
from ...common.ui_helpers import build_reset_footer
from ...common.widgets import ElidedLabel
from .run import NovelTabRunMixin
from .state import NovelTabStateMixin


class ParserNovelTab(NovelTabStateMixin, NovelTabRunMixin, BaseParserPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._out_dir = ''
        self._is_running = False
        self._awaiting_login = False
        self._had_error = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        splitter = QSplitter(Qt.Horizontal, self)
        self.splitter = splitter
        layout.addWidget(splitter)

        left = QWidget()
        gl = QGridLayout(left)
        gl.setHorizontalSpacing(4)
        gl.setVerticalSpacing(9)
        gl.setContentsMargins(15, 0, 4, 0)
        gl.setColumnStretch(0, 0)
        gl.setColumnStretch(1, 1)
        gl.setColumnStretch(2, 0)
        row = 0

        gl.addWidget(QLabel('ID тайтла:'), row, 0, 1, 1, Qt.AlignLeft)
        self.ed_title = QLineEdit()
        self.ed_title.setPlaceholderText('например: 49248323')
        gl.addWidget(self.ed_title, row, 1, 1, 2)
        row += 1

        gl.addWidget(QLabel('Режим:'), row, 0)
        self.rb_ui = QRadioButton('По UI')
        self.rb_ui.setChecked(True)
        self.rb_id = QRadioButton('По ID')
        mode_row = QHBoxLayout()
        mode_row.setContentsMargins(0, 0, 0, 0)
        mode_row.setSpacing(6)
        mode_row.addWidget(self.rb_ui)
        mode_row.addWidget(self.rb_id)
        mode_row.addStretch(1)
        gl.addLayout(mode_row, row, 1, 1, 2)
        row += 1

        self.lbl_spec = QLabel('Viewer ID:')
        self.ed_spec = QLineEdit()
        self.ed_spec.setPlaceholderText('например: 49248366, 49248367')
        gl.addWidget(self.lbl_spec, row, 0)
        gl.addWidget(self.ed_spec, row, 1, 1, 2)
        row += 1

        self._rx_int = QRegularExpression(r'^[0-9]+$')
        self._rx_csv_ints = QRegularExpression(r'^\s*\d+(?:\s*,\s*\d+)*\s*$')
        self._val_int = QRegularExpressionValidator(self._rx_int, self)
        self._val_csv_ints = QRegularExpressionValidator(self._rx_csv_ints, self)
        self.ed_title.setValidator(self._val_int)
        self._is_valid = self._is_valid_line_edit

        gl.addWidget(QLabel('Папка сохранения:'), row, 0, Qt.AlignLeft)
        self.btn_pick_out = QPushButton('Выбрать…')
        self.lbl_out = ElidedLabel('— не выбрано —')
        self.lbl_out.setStyleSheet('color:#a00')
        self.btn_pick_out.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.lbl_out.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        out_row = QHBoxLayout()
        out_row.setContentsMargins(0, 0, 0, 0)
        out_row.setSpacing(6)
        out_row.addWidget(self.btn_pick_out)
        out_row.addWidget(self.lbl_out, 1)
        gl.addLayout(out_row, row, 1, 1, 2)
        row += 1

        self.btn_run = QPushButton('Запустить')
        self.btn_run.setEnabled(False)
        self.btn_stop = QPushButton('Остановить')
        self.btn_stop.setEnabled(False)
        self.btn_continue = QPushButton('Продолжить после входа')
        self.btn_continue.setEnabled(False)
        self.btn_open_dir = QPushButton('Открыть папку')
        self.btn_open_dir.setEnabled(False)
        run_row = QHBoxLayout()
        run_row.setContentsMargins(0, 8, 0, 8)
        run_row.setSpacing(6)
        run_row.addStretch(1)
        run_row.addWidget(self.btn_open_dir)
        run_row.addWidget(self.btn_continue)
        run_row.addWidget(self.btn_stop)
        run_row.addWidget(self.btn_run)
        gl.addLayout(run_row, row, 0, 1, 3)
        row += 1

        grp_buy = QGroupBox('Покупки / тикеты')
        buy_layout = QVBoxLayout(grp_buy)
        self.chk_auto_buy = QCheckBox('Автопокупка тикета')
        self.chk_auto_buy.setChecked(False)
        self.chk_auto_use_ticket = QCheckBox('Автоматически использовать доступный тикет')
        self.chk_auto_use_ticket.setChecked(False)
        buy_layout.addWidget(self.chk_auto_buy)
        buy_layout.addWidget(self.chk_auto_use_ticket)
        gl.addWidget(grp_buy, row, 0, 1, 3)
        row += 1

        grp_extra = QGroupBox('Доп. настройки')
        extra_layout = QVBoxLayout(grp_extra)
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
        extra_layout.addLayout(threads_row)
        gl.addWidget(grp_extra, row, 0, 1, 3)
        row += 1

        self.btn_toggle_ids = QPushButton('Показать сохранённые ID')
        self.btn_toggle_ids.setFixedHeight(35)
        gl.addWidget(self.btn_toggle_ids, row, 0, 1, 3)
        row += 1

        self._ids_slot = QVBoxLayout()
        gl.addLayout(self._ids_slot, row, 0, 1, 3)
        row += 1

        self._ids_panel = SavedIdsPanel(
            values_key='novel_ids',
            on_copy_to_title=self._on_copy_id_to_title_and_save,
            parent=self,
            settings_dir_provider=self._settings_dir,
        )
        self.btn_toggle_ids.clicked.connect(self._toggle_ids_panel)
        gl.setRowStretch(row, 1)

        left_scroll = QScrollArea(self)
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._left_scroll = left_scroll
        self._left_content = left
        self._left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self._left_scroll.setViewportMargins(0, 0, 0, 0)
        self._left_content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        left_scroll.setWidget(left)

        left_container = QWidget(self)
        left_outer = QVBoxLayout(left_container)
        left_outer.setContentsMargins(0, 15, 0, 0)
        left_outer.setSpacing(0)
        left_outer.addWidget(left_scroll, 1)
        build_reset_footer(self, left_outer)

        splitter.addWidget(left_container)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        self.btn_pick_out.clicked.connect(self._pick_out)
        self.btn_open_dir.clicked.connect(self._open_out_dir)
        self.btn_run.clicked.connect(self._start)
        self.btn_stop.clicked.connect(self._stop)
        self.btn_continue.clicked.connect(self._continue)
        self.rb_ui.toggled.connect(self._persist_mode)
        self.rb_id.toggled.connect(self._persist_mode)
        self.btn_reset.clicked.connect(self._confirm_and_reset)
        self.chk_auto_threads.toggled.connect(self._apply_threads_state)
        self.chk_auto_threads.toggled.connect(lambda v: self._save_bool_ini('auto_threads', bool(v)))
        self.spin_threads.valueChanged.connect(lambda v: self._save_int_ini('threads', int(v)))
        self.chk_auto_buy.toggled.connect(lambda v: self._save_bool_ini('auto_buy', bool(v)))
        self.chk_auto_use_ticket.toggled.connect(lambda v: self._save_bool_ini('auto_use_ticket', bool(v)))
        self._apply_threads_state(self.chk_auto_threads.isChecked())

        self.ed_title.editingFinished.connect(lambda: self._save_str_ini('title', self.ed_title.text().strip()))
        self.ed_spec.editingFinished.connect(lambda: self._save_str_ini('spec', self.ed_spec.text().strip()))
        self.ed_title.textChanged.connect(lambda *_: self._refresh_run_enabled())
        self.ed_spec.textChanged.connect(lambda *_: self._refresh_run_enabled())

    def showEvent(self, e):
        super().showEvent(e)
        if getattr(self, '_ini_applied', False):
            return
        self._ini_applied = True

        self.setUpdatesEnabled(False)
        blockers = [
            QSignalBlocker(self.ed_title),
            QSignalBlocker(self.ed_spec),
            QSignalBlocker(self.rb_ui),
            QSignalBlocker(self.rb_id),
            QSignalBlocker(self.chk_auto_threads),
            QSignalBlocker(self.spin_threads),
            QSignalBlocker(self.chk_auto_buy),
            QSignalBlocker(self.chk_auto_use_ticket),
        ]
        try:
            self._apply_settings_from_ini()
            self._update_mode()
            self._refresh_run_enabled()
        finally:
            del blockers
            self.setUpdatesEnabled(True)

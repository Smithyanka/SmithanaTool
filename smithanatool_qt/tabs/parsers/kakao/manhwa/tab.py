from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QRegularExpression, Qt, Slot
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
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
from ...common.saved_ids_panel import SavedIdsPanel
from ...common.widgets import ElidedLabel
from .run import ManhwaTabRunMixin
from .sections import build_auto_stitch_section, build_extra_settings_group, build_footer
from .state import ManhwaTabStateMixin
from .worker import ManhwaParserWorker


class ParserManhwaTab(ManhwaTabStateMixin, ManhwaTabRunMixin, BaseParserPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: Optional[ManhwaParserWorker] = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Horizontal, self)
        self.splitter = splitter
        layout.addWidget(splitter)

        left = QWidget()
        gl = QGridLayout(left)
        gl.setHorizontalSpacing(4)
        gl.setVerticalSpacing(9)
        gl.setContentsMargins(15, 0, 10, 20)
        gl.setColumnStretch(0, 0)
        gl.setColumnStretch(1, 1)
        gl.setColumnStretch(2, 0)

        row = 0
        gl.addWidget(QLabel('ID тайтла:'), row, 0, 1, 1, Qt.AlignLeft)
        self.ed_title = QLineEdit()
        self.ed_title.setPlaceholderText('например: 123456')
        gl.addWidget(self.ed_title, row, 1, 1, 2)
        row += 1

        gl.addWidget(QLabel('Режим:'), row, 0)
        self.rb_number = QRadioButton('По номеру')
        self.rb_number.setChecked(True)
        self.rb_id = QRadioButton('По ID')
        self.rb_index = QRadioButton('По индексу')
        self.rb_ui = QRadioButton('По UI')
        mode_box = QHBoxLayout()
        mode_box.setContentsMargins(0, 0, 0, 0)
        mode_box.setSpacing(6)
        for rb in (self.rb_number, self.rb_id, self.rb_index, self.rb_ui):
            mode_box.addWidget(rb)
        mode_box.addStretch(1)
        gl.addLayout(mode_box, row, 1, 1, 2)
        row += 1

        self.mode_group = QButtonGroup(self)
        for rb in (self.rb_number, self.rb_id, self.rb_index, self.rb_ui):
            self.mode_group.addButton(rb)

        self.lbl_spec = QLabel('Глава/ы:')
        gl.addWidget(self.lbl_spec, row, 0)
        self.ed_spec = QLineEdit()
        self.ed_spec.setPlaceholderText('например: 1,2,5-7')
        gl.addWidget(self.ed_spec, row, 1, 1, 2)
        row += 1

        self._spec_before_ui: str = ''
        self._last_mode: Optional[str] = None

        self._rx_int = QRegularExpression(r'^[0-9]+$')
        self._rx_csv_ints = QRegularExpression(r'^\s*\d+(?:\s*,\s*\d+)*\s*$')
        self._rx_ranges = QRegularExpression(r'^\s*\d+(?:\s*-\s*\d+)?(?:\s*,\s*\d+(?:\s*-\s*\d+)?)*\s*$')
        self._val_int = QRegularExpressionValidator(self._rx_int, self)
        self._val_csv_ints = QRegularExpressionValidator(self._rx_csv_ints, self)
        self._val_ranges = QRegularExpressionValidator(self._rx_ranges, self)
        self.ed_title.setValidator(self._val_int)
        self._is_valid = self._is_valid_line_edit

        gl.addWidget(QLabel('Папка сохранения:'), row, 0, Qt.AlignLeft)
        self.btn_pick_out = QPushButton('Выбрать…')
        self.lbl_out = ElidedLabel('— не выбрано —')
        self.lbl_out.setStyleSheet('color:#a00')
        self.btn_pick_out.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.lbl_out.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row_out = QHBoxLayout()
        row_out.setContentsMargins(0, 0, 0, 0)
        row_out.setSpacing(6)
        row_out.addWidget(self.btn_pick_out)
        row_out.addWidget(self.lbl_out, 1)
        gl.addLayout(row_out, row, 1, 1, 2)
        row += 1

        gl.addWidget(QLabel('Мин. ширина (px):'), row, 0)
        self.spin_minw = QSpinBox()
        self.spin_minw.setRange(0, 5000)
        self.spin_minw.setValue(720)
        gl.addWidget(self.spin_minw, row, 1, 1, 2)
        row += 1

        self.btn_run = QPushButton('Запустить')
        self.btn_run.setEnabled(False)
        self.btn_stop = QPushButton('Остановить')
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

        grp_extra = build_extra_settings_group(self)
        gl.addWidget(grp_extra, row, 0, 1, 3)
        row += 1

        coll_auto = build_auto_stitch_section(self)
        self._bind_section_expanded(coll_auto, 'expanded_auto', default=False)
        gl.addWidget(coll_auto, row, 0, 1, 3)
        row += 1


        self.btn_toggle_ids = QPushButton('Показать сохранённые ID')
        self.btn_toggle_ids.setFixedHeight(35)
        gl.addWidget(self.btn_toggle_ids, row, 0, 1, 3)
        row += 1

        self._ids_slot = QVBoxLayout()
        gl.addLayout(self._ids_slot, row, 0, 1, 3)
        row += 1

        self._ids_panel = SavedIdsPanel(
            values_key='manhwa_ids',
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
        build_footer(self, left_outer)

        splitter.addWidget(left_container)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        self.btn_pick_out.clicked.connect(self._pick_out)
        self.chk_auto.toggled.connect(self._update_auto_enabled)
        self.chk_no_resize.toggled.connect(self._update_no_resize)
        self.chk_same_dir.toggled.connect(self._update_same_dir)
        self.chk_opt.toggled.connect(self._update_png_controls)
        self.combo_auto_mode.currentIndexChanged.connect(self._update_group_by_visibility)
        self.btn_pick_stitch.clicked.connect(self._pick_stitch_dir)
        self.btn_run.clicked.connect(self._start)
        self.btn_stop.clicked.connect(self._stop)
        self.btn_continue.clicked.connect(self._continue)
        self.btn_open_dir.clicked.connect(self._open_out_dir)
        self.btn_reset.clicked.connect(self._confirm_and_reset)
        self.chk_auto_threads.toggled.connect(self._apply_threads_state)
        self._apply_threads_state(self.chk_auto_threads.isChecked())

        for rb in (self.rb_number, self.rb_id, self.rb_index, self.rb_ui):
            rb.toggled.connect(lambda checked: checked and self._persist_mode())

        self.ed_title.textChanged.connect(self._refresh_run_enabled)
        self.ed_spec.textChanged.connect(self._refresh_run_enabled)

        self.combo_auto_mode.currentIndexChanged.connect(
            lambda idx: self._save_str_ini(
                'group_by',
                'count' if int(idx) == 0 else ('height' if int(idx) == 1 else 'smart')
            )
        )

        self._out_dir = ''
        self._stitch_dir = ''
        self._update_group_by_visibility()
        self._update_auto_enabled()
        self._update_mode()

        app = QApplication.instance()
        if app:
            app.aboutToQuit.connect(self._abort_if_running)

    @Slot()
    def _abort_if_running(self) -> None:
        try:
            if self._worker:
                self._worker.stop_and_wait(8000)
        except Exception:
            pass

    def showEvent(self, e):
        super().showEvent(e)
        if getattr(self, '_ini_applied', False):
            return
        self._ini_applied = True
        self.setUpdatesEnabled(False)
        try:
            self.blockSignals(True)
            self._apply_settings_from_ini()
        finally:
            self.blockSignals(False)
            self.setUpdatesEnabled(True)

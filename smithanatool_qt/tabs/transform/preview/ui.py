from __future__ import annotations

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QFrame,
    QToolButton,
    QLayout,
)

from .widgets import PanZoomLabel

from smithanatool_qt.graphic.foundation.assets import DEFAULT_ICON_SIZE, set_themed_icon, make_sep

def setup_preview_ui(panel: "PreviewPanel") -> None:
    v = QVBoxLayout(panel)
    v.setContentsMargins(0, 0, 0, 0)

    # Область предпросмотра
    panel.scroll = QScrollArea()
    panel.scroll.setWidgetResizable(True)
    panel.scroll.setAlignment(Qt.AlignCenter)
    panel.scroll.setViewportMargins(0, 0, 0, 0)
    panel.scroll.setFrameShape(QFrame.NoFrame)

    panel.scroll.setObjectName("previewScroll")
    panel.scroll.viewport().setObjectName("previewViewport")

    vp = panel.scroll.viewport()
    vp.setAutoFillBackground(False)

    panel.scroll.setAutoFillBackground(False)
    panel.scroll.setAttribute(Qt.WA_StyledBackground, True)
    panel.scroll.viewport().setAttribute(Qt.WA_StyledBackground, True)

    panel.label = PanZoomLabel(panel, "Нет изображения")
    panel.label.setAlignment(Qt.AlignCenter)
    panel.label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
    panel.label.setMinimumSize(QSize(200, 200))
    panel.label.attach_scroll(panel.scroll)
    panel.label.setObjectName("previewCanvas")

    panel.scroll.setWidget(panel.label)

    # Режим UI для зума: 0 = нижняя панель, 1 = оверлей
    panel._zoom_ui_mode = 1

    # ── Оверлейные элементы (живут на viewport ScrollArea)
    panel._overlay_zoom_out = QToolButton(panel.scroll.viewport())
    panel._overlay_zoom_out.setText("−")
    panel._overlay_zoom_out.setAutoRaise(True)
    panel._overlay_zoom_out.setToolTip("Уменьшить масштаб")

    panel._overlay_zoom_in = QToolButton(panel.scroll.viewport())
    panel._overlay_zoom_in.setText("+")
    panel._overlay_zoom_in.setAutoRaise(True)
    panel._overlay_zoom_in.setToolTip("Увеличить масштаб")

    for b in (panel._overlay_zoom_in, panel._overlay_zoom_out):
        b.setProperty("overlay", True)
        b.setFocusPolicy(Qt.NoFocus)
        b.setAttribute(Qt.WA_Hover, True)

    panel._overlay_zoom_out.hide()
    panel._overlay_zoom_in.hide()

    panel._overlay_zoom_out.clicked.connect(lambda: panel._zoom_by(1 / 1.1))
    panel._overlay_zoom_in.clicked.connect(lambda: panel._zoom_by(1.1))

    panel._overlay_info = QLabel(panel.scroll.viewport())
    panel._overlay_info.setObjectName("overlay_info")
    panel._overlay_info.hide()
    panel._overlay_info.setWordWrap(False)
    panel._overlay_info.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    panel._controls_row_widgets = []

    # --- ТОСТ-ЛЕЙБЛ (в левом нижнем углу viewport)
    panel._toast = QLabel(panel.scroll.viewport())
    panel._toast.setObjectName("preview_toast")
    panel._toast.hide()
    panel._toast_timer = QTimer(panel)
    panel._toast_timer.setSingleShot(True)
    panel._toast_timer.timeout.connect(panel._toast.hide)

    # чтобы позиционировать тост при ресайзе viewport
    panel.scroll.viewport().installEventFilter(panel)
    QTimer.singleShot(0, panel._position_overlay_controls)
    QTimer.singleShot(0, panel._position_toast)

    # ------------------------------------------------------------------
    # Vertical panel (icons)
    # ------------------------------------------------------------------
    panel._actions_pinned = bool(getattr(panel, "_actions_pinned", False))

    vp = panel.scroll.viewport()

    panel.actions_panel = QFrame(vp)
    panel.actions_panel.setObjectName("previewActionsPanel")
    panel.actions_panel.setProperty("overlay", True)
    panel.actions_panel.setAttribute(Qt.WA_StyledBackground, True)
    panel.actions_panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    panel.actions_panel.hide()

    panel._actions_layout = QVBoxLayout(panel.actions_panel)
    panel._actions_layout.setSizeConstraint(QLayout.SetFixedSize)
    panel._actions_layout.setContentsMargins(4, 4, 4, 4)
    panel._actions_layout.setSpacing(4)

    def _mk_icon_btn(tooltip: str, *icon_names: str) -> QToolButton:
        tb = QToolButton(panel.actions_panel)
        tb.setProperty("role", "previewAction")
        tb.setAutoRaise(True)
        tb.setToolTip(tooltip)
        set_themed_icon(tb, *icon_names, size=DEFAULT_ICON_SIZE)
        tb.setFixedSize(34, 34)
        tb.setCursor(Qt.PointingHandCursor)
        tb.setFocusPolicy(Qt.NoFocus)

        return tb

    panel.action_btn_frame = _mk_icon_btn(
        "Рамка (C)\nEnter — применить\nEsc — отмена",
        "frame.svg",
    )
    panel.action_btn_cut = _mk_icon_btn("Вырезать (Ctrl+X)",  "cut.svg")

    panel.action_btn_paste_top = _mk_icon_btn(
        "Вставить в начало (Ctrl+D)",
        "paste_up.svg",
    )
    panel.action_btn_paste_bottom = _mk_icon_btn(
        "Вставить в конец (Ctrl+Shift+D)",
        "paste_down.svg",
    )

    panel.action_btn_undo = _mk_icon_btn("Вернуть (Ctrl+Z)", "undo.svg", "arrow_undo.svg", "undo.png")
    panel.action_btn_redo = _mk_icon_btn(
        "Вернуть обратно (Ctrl+Shift+Z)",
        "redo.svg",
    )

    panel.action_btn_save = _mk_icon_btn("Сохранить (Ctrl+S)", "save.svg")
    panel.action_btn_save_as = _mk_icon_btn("Сохранить как… (Ctrl+Shift+S)", "saveas.svg")

    panel.action_btn_ocr_sort = _mk_icon_btn(
        "Сменить порядок рамок",
        "sort_rects.svg",
        "sort_rects.png",
    )
    panel.action_btn_ocr_delete = _mk_icon_btn(
        "Удалить рамки",
        "delete_rects.svg",
        "delete_rects.png",
    )
    panel.action_btn_ocr_undo = _mk_icon_btn(
        "Вернуть (Ctrl+Z)",
        "undo.svg",
        "arrow_undo.svg",
        "undo.png",
    )
    panel.action_btn_ocr_redo = _mk_icon_btn(
        "Вернуть обратно (Ctrl+Shift+Z)",
        "redo.svg",
        "redo.png",
    )
    # Алиас для обратной совместимости со старым именем.
    panel.action_btn_ocr_restore = panel.action_btn_ocr_undo

    panel._transform_action_widgets = [
        panel.action_btn_frame,
        make_sep(panel.actions_panel),
        panel.action_btn_cut,
        make_sep(panel.actions_panel),
        panel.action_btn_paste_top,
        panel.action_btn_paste_bottom,
        make_sep(panel.actions_panel),
        panel.action_btn_undo,
        panel.action_btn_redo,
        make_sep(panel.actions_panel),
        panel.action_btn_save,
        panel.action_btn_save_as,
    ]

    panel._ocr_action_widgets = [
        panel.action_btn_ocr_sort,
        make_sep(panel.actions_panel),
        panel.action_btn_ocr_delete,
        make_sep(panel.actions_panel),
        panel.action_btn_ocr_undo,
        panel.action_btn_ocr_redo,
    ]

    # Порядок важен: сперва обычные действия превью, затем OCR-профиль меню.
    for w in panel._transform_action_widgets:
        panel._actions_layout.addWidget(w)

    for w in panel._ocr_action_widgets:
        panel._actions_layout.addWidget(w)
        w.hide()


    panel.btn_actions_handle = QToolButton(vp)
    panel.btn_actions_handle.setObjectName("previewActionsHandle")
    panel.btn_actions_handle.setProperty("overlay", True)
    panel.btn_actions_handle.setProperty("sideHandle", True)
    panel.btn_actions_handle.setFocusPolicy(Qt.NoFocus)
    panel.btn_actions_handle.setCursor(Qt.PointingHandCursor)

    set_themed_icon(panel.btn_actions_handle, "menu.svg", size=DEFAULT_ICON_SIZE)

    panel.btn_actions_handle.setToolButtonStyle(Qt.ToolButtonIconOnly)


    panel.btn_actions_handle.setAutoRaise(True)
    panel.btn_actions_handle.setFixedSize(25, 40)
    panel.btn_actions_handle.setToolTip("Меню")

    panel.btn_actions_handle.setCheckable(True)

    def _set_actions_pinned(on: bool) -> None:
        # "Pinned" must stay across file switching.
        panel._actions_pinned = bool(on)

        panel.actions_panel.setVisible(panel._actions_pinned)
        if panel._actions_pinned:
            panel.actions_panel.adjustSize()
            try:
                panel._position_overlay_controls()
            except Exception:
                pass
            panel.actions_panel.raise_()

    # Source of truth: the handle checked state.
    panel.btn_actions_handle.toggled.connect(_set_actions_pinned)
    # Apply initial state.
    panel.btn_actions_handle.setChecked(panel._actions_pinned)

    h = QHBoxLayout()
    h.setContentsMargins(0, 0, 0, 0)
    h.addWidget(panel.scroll)
    v.addLayout(h)

    panel.setFocusPolicy(Qt.StrongFocus)
    panel.scroll.setFocusPolicy(Qt.StrongFocus)
    panel.scroll.viewport().setFocusPolicy(Qt.StrongFocus)
    panel.label.setFocusPolicy(Qt.StrongFocus)

    # Панель зума/режимов
    controls = QHBoxLayout()
    controls.setSpacing(6)
    controls.setContentsMargins(0, 0, 0, 0)

    panel.lbl_info = QLabel("—")
    panel.lbl_info.setObjectName("previewInfo")
    controls.addWidget(panel.lbl_info)

    controls.addStretch(1)

    panel.btn_zoom_out = QToolButton()
    panel.btn_zoom_out.setText("−")
    panel.btn_zoom_in = QToolButton()
    panel.btn_zoom_in.setText("+")

    for b in (panel.btn_zoom_out, panel.btn_zoom_in):
        b.setProperty("zoomCtl", True)
        b.setAutoRaise(True)
        b.setFixedSize(22, 22)

    panel.btn_zoom_reset = QPushButton("По ширине")
    panel.lbl_zoom = QLabel("100%")
    panel.btn_fit = QPushButton("По высоте")

    controls.addWidget(panel.lbl_zoom)
    controls.addWidget(panel.btn_zoom_out)
    controls.addWidget(panel.btn_zoom_in)
    controls.addWidget(panel.btn_zoom_reset)
    controls.addWidget(panel.btn_fit)

    panel._controls_row_widgets = [
        panel.lbl_info,
        panel.lbl_zoom,
        panel.btn_zoom_out,
        panel.btn_zoom_in,
        panel.btn_zoom_reset,
        panel.btn_fit,
    ]

    v.addLayout(controls)

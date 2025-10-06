from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QToolButton, QSizePolicy, QMenu
from ..foundation.glyphs import glyph_icon, circular_pixmap

SNAP_THRESHOLD_PX = 6
ENABLE_DRAG_TO_FULLSCREEN = True

class TitleBar(QWidget):
    def __init__(self, window, view_menu: QMenu, *, height: int = 36, small_text: str = ""):
        super().__init__(window)

        self.setObjectName("TitleBar")
        self.setAttribute(Qt.WA_StyledBackground, True)

        self._window = window
        self.setFixedHeight(height)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 8, 0)
        lay.setSpacing(6)

        # ЛЕВО: лого + заголовок
        left = QWidget(self)
        left_lay = QHBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(1)

        self.logo_lbl = QLabel(left)
        self.logo_lbl.setFixedSize(26, 26)
        logo_pm = circular_pixmap(self._window.windowIcon(), 22)
        self.logo_lbl.setPixmap(logo_pm)
        self.logo_lbl.setAlignment(Qt.AlignCenter)

        title_box = QWidget(left)
        title_row = QHBoxLayout(title_box)  # одна строка: Название + серый текст
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)

        self.app_title_lbl = QLabel(self._window.windowTitle(), title_box)
        self.app_title_lbl.setObjectName("appTitleLbl")

        self.app_small_lbl = QLabel(small_text, title_box)  # ← новый маленький серый текст
        self.app_small_lbl.setObjectName("appSmallLbl")
        self.app_small_lbl.setVisible(bool(small_text))

        title_row.addWidget(self.app_title_lbl)
        title_row.addWidget(self.app_small_lbl)
        title_row.addStretch(1)

        left_lay.addWidget(self.logo_lbl, 0, Qt.AlignVCenter)
        left_lay.addWidget(title_box, 0, Qt.AlignVCenter)
        left_lay.addWidget(self.logo_lbl, 0, Qt.AlignVCenter)
        left_lay.addWidget(title_box, 0, Qt.AlignVCenter)

        left.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        lay.addWidget(left)
        lay.addStretch(1)

        # Кнопка меню "Вид"
        self.btn_settings = QToolButton(self)
        self.btn_settings.setAutoRaise(True)
        self.btn_settings.setIcon(glyph_icon("gear", 16))
        self.btn_settings.setPopupMode(QToolButton.InstantPopup)
        self.btn_settings.setMenu(view_menu)
        lay.addWidget(self.btn_settings)

        # Кнопки окна
        self.btn_min = QToolButton(self)
        self.btn_min.setAutoRaise(True)
        self.btn_min.setIcon(glyph_icon("min", 16))
        self.btn_min.clicked.connect(window.showMinimized)
        lay.addWidget(self.btn_min)

        self.btn_max = QToolButton(self)
        self.btn_max.setAutoRaise(True)
        self.btn_max.clicked.connect(self._toggle_max_restore)
        lay.addWidget(self.btn_max)

        self.btn_close = QToolButton(self)
        self.btn_close.setAutoRaise(True)
        self.btn_close.setIcon(glyph_icon("close", 16))
        self.btn_close.clicked.connect(window.close)
        lay.addWidget(self.btn_close)

        self._update_max_icon()

        for b in (self.btn_settings, self.btn_min, self.btn_max, self.btn_close):
            b.setIconSize(QSize(16, 16))

        window.windowTitleChanged.connect(self.app_title_lbl.setText)

        self.setStyleSheet("""
            #TitleBar {
                background: #111111;                
            }

            #TitleBar QLabel { color: #ffffff; }
            #TitleBar #appTitleLbl { font-size: 14px; font-weight: 700; }

            #TitleBar QToolButton { border: none; padding: 6px; }
            #TitleBar QToolButton:hover { background: rgba(255,255,255,0.08); border-radius: 6px; }
        """)

        self.setStyleSheet("""
                    #TitleBar { background: #111111; }
                    #TitleBar QLabel { color: #ffffff; }
                    #appTitleLbl { font-size: 14px; font-weight: 700; }
                    #appSmallLbl { font-size: 12px; color: rgba(255,255,255,0.60); }  /* маленький серый */
                    #TitleBar QToolButton { border: none; padding: 6px; }
                    #TitleBar QToolButton:hover { background: rgba(255,255,255,0.08); border-radius: 6px; }
                """)

    def _toggle_max_restore(self):
        w = self._window
        if w.isFullScreen() or w.isMaximized():
            w.setWindowState(Qt.WindowNoState)
            w.showNormal()
            ng = getattr(w, "_normal_geom", None)
            if ng is not None:
                w.setGeometry(ng)  # <— ключевая строка
        else:
            w.showMaximized()
        self._update_max_icon()

    def _update_max_icon(self):
        # иконка «restore», если окно в полноэкранном или развёрнутом режиме
        self.btn_max.setIcon(glyph_icon("restore" if (self._window.isMaximized() or self._window.isFullScreen()) else "max", 16))

    def _maybe_snap_to_top(self):
        """Разворачиваем/делаем FullScreen при отпускании у верхней кромки — независимо от стартового состояния."""
        win = self._window
        scr = win.screen()
        if not scr:
            return
        top = win.frameGeometry().top()
        top_limit = scr.availableGeometry().top()
        if top <= top_limit + SNAP_THRESHOLD_PX:
            # если тащили, будучи уже развёрнутым/полноэкранным — по желанию уходим в полноэкранный
            if getattr(self, "_press_started_maximized", False) and ENABLE_DRAG_TO_FULLSCREEN:
                win.showFullScreen()
            else:
                win.showMaximized()
            self._update_max_icon()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            w = self._window
            self._dragging = True
            # запомним, начинали ли перетаскивание в Max/FullScreen
            self._press_started_maximized = (w.isMaximized() or w.isFullScreen())

            # если были в FullScreen — выйдем в Normal и пойдём ручным перетаском
            # (некоторые WM не разрешают startSystemMove из полноэкрана)
            if w.isFullScreen():
                w.showNormal()
                self._drag_off = e.globalPosition().toPoint() - w.frameGeometry().topLeft()
            else:
                wh = w.windowHandle()
                if wh and hasattr(wh, "startSystemMove"):
                    wh.startSystemMove()
                else:
                    # фолбэк: ручной перетаск
                    self._drag_off = e.globalPosition().toPoint() - w.frameGeometry().topLeft()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if hasattr(self, "_drag_off"):
            self._window.move(e.globalPosition().toPoint() - self._drag_off)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        # завершение ручного перетаска
        if hasattr(self, "_drag_off"):
            del self._drag_off
        if getattr(self, "_dragging", False):
            self._dragging = False
            self._maybe_snap_to_top()
        # сброс маркера «стартовали развёрнутыми»
        if hasattr(self, "_press_started_maximized"):
            del self._press_started_maximized
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._toggle_max_restore()
        super().mouseDoubleClickEvent(e)


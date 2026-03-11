from __future__ import annotations

from importlib import metadata as importlib_metadata

from PySide6.QtCore import Qt, QSize, QRect, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QFrame,
    QLabel,
    QSizePolicy,
    QWidgetAction,
)

from smithanatool_qt.settings_bind import restore_window_geometry, save_window_geometry, group, get_value, set_value
from smithanatool_qt.graphic.theme import apply_theme, ThemeMode

from smithanatool_qt.graphic.foundation.assets import DEFAULT_ICON_SIZE, set_themed_icon, refresh_themed_icons
from .tab_manager import TabManager
from .window_state import (
    LoadingOverlay,
    reset_window_size,
    restore_persisted_child_states,
    save_persisted_child_states,
)


class MainWindow(QMainWindow):
    # key -> (instance_attr_name, module_path, class_name, title)
    TAB_SPECS = {
        "workshop": (
            "_transform_tab",
            "smithanatool_qt.tabs.workshop.tab",
            "WorkshopTab",
            "Мастерская",
        ),
        "parsers": (
            "_parsers_tab",
            "smithanatool_qt.tabs.parsers.tab",
            "ParsersTab",
            "Парсеры Kakao",
        ),
        "info": ("_info_tab", "smithanatool_qt.tabs.info_tab", "InfoTab", "Инфо"),
    }

    def __init__(self):
        super().__init__()
        self._normal_geom = None

        self.setWindowTitle("SmithanaTool v1.1.1f ")

        # В приложении остаётся только системная шапка (native title bar).
        self.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.setWindowFlag(Qt.WindowSystemMenuHint, True)

        self.setWindowIcon(QIcon(":/assets/smithanatool.ico"))
        self.resize(1400, 800)

        central = QWidget(self)
        self.setCentralWidget(central)
        self.setMouseTracking(True)
        central.setMouseTracking(True)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("mainTabs")
        self.tabs.setIconSize(QSize(18, 18))
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setDrawBase(False)
        self.tabs.setElideMode(Qt.ElideRight)
        self.tabs.setMouseTracking(True)
        layout.addWidget(self.tabs)

        # --- Ленивая загрузка вкладок ---
        self.tab_manager = TabManager(
            owner=self,
            tabs=self.tabs,
            tab_specs=self.TAB_SPECS,
            show_loading=self._show_loading,
            hide_loading=self._hide_loading,
            restore_widget_state=restore_persisted_child_states,
        )
        self.tabs.currentChanged.connect(self.tab_manager.on_current_tab_changed)

        # Применить вкладки (ленивая инициализация)
        self.tab_manager.apply_tabs_from_settings()

        self._apply_theme()


        # Меню "Вид" → "Вкладки"
        menu_view = self.menuBar().addMenu("Вид")
        tabs_menu = menu_view.addMenu("Вкладки")

        def add_tab_toggle(title: str, key: str):
            current = self.tab_manager.tab_enabled(key, True)
            act = tabs_menu.addAction(title)
            act.setCheckable(True)
            act.setChecked(current)

            def on_toggle(checked: bool):
                # Не даём выключить последнюю оставшуюся вкладку,
                # иначе пропадёт и шестерёнка (она в QTabBar).
                if not checked and self.tabs.count() == 1:
                    w0 = self.tabs.widget(0)
                    if w0 is not None and w0.property("tab_key") == key:
                        act.blockSignals(True)
                        act.setChecked(True)
                        act.blockSignals(False)
                        QMessageBox.information(self, "Астанавитесь", "Зачем тебе пустое приложение?")
                        return

                self.tab_manager.set_tab_enabled(key, checked)

            act.toggled.connect(on_toggle)
            return act

        self._act_tab_workshop = add_tab_toggle("Мастерская", "workshop")
        # self._act_tab_transform = add_tab_toggle("Преобразования", "transform")
        # self._act_tab_ai = add_tab_toggle("Извлечение текста", "ai_text")
        self._act_tab_parsers = add_tab_toggle("Парсеры Kakao", "parsers")
        self._act_tab_info = add_tab_toggle("Инфо", "info")

        act_reset_zoom = menu_view.addAction("Сбросить размер окна")
        act_reset_zoom.triggered.connect(lambda: reset_window_size(self, self.tab_manager.iter_realized_tabs()))

        # Шестерёнка (меню "Вид")
        self.btn_settings = QToolButton(self)
        self.btn_settings.setObjectName("btnSettings")
        self.btn_settings.setProperty("cornerButton", True)

        self.btn_settings.setAutoRaise(True)
        set_themed_icon(self.btn_settings, "settings.svg", size=DEFAULT_ICON_SIZE)
        self.btn_settings.setIconSize(DEFAULT_ICON_SIZE)

        self.btn_settings.setPopupMode(QToolButton.InstantPopup)
        self.btn_settings.setMenu(menu_view)
        tab_h = self.tabs.tabBar().sizeHint().height()

        self.btn_settings.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.btn_settings.setFixedSize(tab_h, tab_h)

        # Переключение темы (тёмная/светлая)
        self.btn_theme = QToolButton(self)
        self.btn_theme.setObjectName("btnTheme")
        self.btn_theme.setProperty("cornerButton", True)
        self.btn_theme.setAutoRaise(True)
        self.btn_theme.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.btn_theme.setIconSize(DEFAULT_ICON_SIZE)
        self.btn_theme.setFixedSize(tab_h, tab_h)
        self.btn_theme.clicked.connect(self._toggle_theme)

        corner = QWidget(self.tabs)
        lay = QHBoxLayout(corner)
        lay.setContentsMargins(0, 0, 10, 0)
        lay.setSpacing(4)
        lay.addWidget(self.btn_theme, 0, Qt.AlignVCenter)
        lay.addWidget(self.btn_settings, 0, Qt.AlignVCenter)

        corner.setFixedHeight(tab_h)
        self.tabs.setCornerWidget(corner, Qt.TopRightCorner)

        self._update_theme_button()

        # Меню прячем — доступ через шестерёнку.
        self.menuBar().setVisible(False)

        try:
            restore_window_geometry(self)
        except Exception:
            pass

        self._normal_geom = self.geometry()
        if self.isMaximized():
            g = QRect(0, 0, 1400, 800)
            scr = self.screen()
            if scr:
                g.moveCenter(scr.availableGeometry().center())
            self._normal_geom = g

        # --- ВАЖНО: первый таб "realize" ДО showEvent/первой отрисовки ---
        self.tab_manager.realize_active_tab(sync=True)

    # -------------------- helpers --------------------

    def _theme_mode(self) -> str:
        # Настройка хранится в ini: [MainWindow][Theme] mode = dark|light
        with group("MainWindow"):
            with group("Theme"):
                mode = get_value("mode", ThemeMode.DARK.value, typ=str)

        mode = str(mode).strip().lower()
        if mode not in (ThemeMode.DARK.value, ThemeMode.LIGHT.value):
            mode = ThemeMode.DARK.value
        return mode

    def _set_theme_mode(self, mode: str) -> None:
        mode = str(mode).strip().lower()
        if mode not in (ThemeMode.DARK.value, ThemeMode.LIGHT.value):
            mode = ThemeMode.DARK.value
        with group("MainWindow"):
            with group("Theme"):
                set_value("mode", mode)

    def _toggle_theme(self) -> None:
        cur = self._theme_mode()
        new = ThemeMode.LIGHT.value if cur == ThemeMode.DARK.value else ThemeMode.DARK.value
        self._set_theme_mode(new)
        self._apply_theme()
        self._update_theme_button()

    def _update_theme_button(self) -> None:
        cur = self._theme_mode()
        if cur == ThemeMode.DARK.value:
            self.btn_theme.setToolTip("Светлая тема")
            self.btn_theme.setObjectName("btnLight")
            set_themed_icon(self.btn_theme, "sun.svg", size=DEFAULT_ICON_SIZE)
            self.btn_theme.setToolButtonStyle(Qt.ToolButtonIconOnly)
            self.btn_theme.setText("")
        else:
            self.btn_theme.setToolTip("Тёмная тема")
            self.btn_theme.setObjectName("btnDark")
            set_themed_icon(self.btn_theme, "moon.svg", size=DEFAULT_ICON_SIZE)
            self.btn_theme.setToolButtonStyle(Qt.ToolButtonIconOnly)
            self.btn_theme.setText("")

    def _apply_theme(self):
        app = QApplication.instance()
        g = self.saveGeometry()
        try:
            apply_theme(app, self._theme_mode())
        finally:
            self.restoreGeometry(g)
        refresh_themed_icons(self)

        for w in self.findChildren(QWidget):
            if w.__class__.__name__ == "CollapsibleSection":
                try:
                    w._update_header_icon(w.toggle_button.isChecked())
                except Exception:
                    pass



    def _has_unsaved_changes(self) -> bool:
        for w in self.findChildren(QWidget):
            try:
                if hasattr(w, "_has_unsaved") and callable(w._has_unsaved):
                    if w._has_unsaved():
                        return True
            except Exception:
                pass
        return False

    def _show_loading(self, text):
        self._hide_loading()
        self._loading = LoadingOverlay(self.tabs, text)
        self._loading.start(text)

    def _hide_loading(self):
        ov = getattr(self, "_loading", None)
        if ov:
            ov.stop()
            self._loading = None

    # -------------------- Qt events --------------------

    def showEvent(self, e):
        super().showEvent(e)
        # Fallback: если по какой-то причине не успели “sync realize” (или вкладки пустые)
        self.tab_manager.realize_active_tab_later()

    def closeEvent(self, e):
        current = self.tabs.currentWidget()
        if current is not None and hasattr(current, "can_close") and not current.can_close():
            e.ignore()
            return

        try:
            if self._has_unsaved_changes():
                btn = QMessageBox.warning(
                    self,
                    "Выход",
                    "Есть несохранённые изменения. Выйти?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if btn != QMessageBox.Yes:
                    e.ignore()
                    return
        except Exception:
            pass

        try:
            for w in self.findChildren(QWidget):
                try:
                    if hasattr(w, "discard_changes") and callable(w.discard_changes):
                        w.discard_changes()
                except Exception:
                    pass
        except Exception:
            pass

        try:
            save_persisted_child_states(self)
        except Exception:
            pass

        try:
            save_window_geometry(self)
        except Exception:
            pass

        super().closeEvent(e)
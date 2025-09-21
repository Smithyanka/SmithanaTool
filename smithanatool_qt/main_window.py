
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QTabWidget, QStatusBar, QStyleFactory, QApplication
from PySide6.QtCore import Qt, QSettings, QTimer
from PySide6.QtGui import QIcon, QColor, QActionGroup, QPalette

import sys
import importlib
from pathlib import Path

from smithanatool_qt.tabs.transform import TransformTab
from smithanatool_qt.tabs.parser_manhwa_tab import ParserManhwaTab
from smithanatool_qt.tabs.parser_novel_tab import ParserNovelTab
from smithanatool_qt.tabs.info_tab import InfoTab
from smithanatool_qt.tabs.transform.preview_panel import PreviewPanel
from smithanatool_qt.settings_bind import restore_window_geometry, save_window_geometry



_BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))  # для ресурсов (иконка и пр.)

if getattr(sys, "frozen", False):
    # EXE: пишем рядом с exe (SmithanaTool_QT\settings.ini)
    _APP_ROOT = Path(sys.executable).resolve().parent
else:
    # DEV: корень проекта (SmithanaTool_QT)
    _APP_ROOT = Path(__file__).resolve().parents[1]

SETTINGS_PATH = _APP_ROOT / "settings.ini"

class MainWindow(QMainWindow):
    # key -> (attr_name, module_path, class_name, tab_title)
    TAB_SPECS = {
        "transform":     ("_transform_tab",    "smithanatool_qt.tabs.transform",            "TransformTab",    "Преобразования"),
        "parser_manhwa": ("_parser_manhwa_tab","smithanatool_qt.tabs.parser_manhwa_tab",    "ParserManhwaTab", "Парсер манхв Kakao"),
        "parser_novel":  ("_parser_novel_tab", "smithanatool_qt.tabs.parser_novel_tab",     "ParserNovelTab",  "Парсер новелл Kakao"),
        "info":          ("_info_tab",         "smithanatool_qt.tabs.info_tab",             "InfoTab",         "Инфо"),
    }

    def _reset_window_size(self):
        # 1) Снять максимизацию/фуллскрин, чтобы resize сработал
        self.setWindowState(Qt.WindowNoState)

        # 2) Стереть сохранённую геометрию из INI, чтобы при следующем запуске была «по умолчанию»
        try:
            s = self._settings()
            s.beginGroup("Window")
            s.remove("")  # удалить все ключи внутри группы Window
            s.endGroup()
            s.sync()
        except Exception:
            pass

        # 3) Выставить дефолтный размер и отцентрировать
        self.resize(1400, 800)  # твой базовый размер «по умолчанию»
        scr = self.screen()
        if scr:
            ag = scr.availableGeometry()
            g = self.geometry()
            g.moveCenter(ag.center())
            self.move(g.topLeft())

    def _realize_active_tab_later(self):
        """Однократно подгружает активную вкладку после старта event loop."""
        if getattr(self, "_startup_realized", False):
            return
        self._startup_realized = True

        idx = self.tabs.currentIndex()
        if idx is None or idx < 0:
            return
        w = self.tabs.widget(idx)
        if w is None:
            return
        key = w.property("tab_key")
        if isinstance(key, str):
            self._realize_tab(key)

    def _add_lazy_tab(self, key: str, title: str):
        """Добавляет плейсхолдер-вкладку, реальный виджет создадим при первом входе."""
        from PySide6.QtWidgets import QWidget
        placeholder = QWidget()
        placeholder.setProperty("tab_key", key)
        placeholder.setProperty("realized", False)
        # ВАЖНО: временно кладём плейсхолдер и в атрибут, чтобы _reorder_tabs_to_spec работал
        attr, _module, _cls, _title = self.TAB_SPECS[key]
        setattr(self, attr, placeholder)
        self.tabs.addTab(placeholder, title)

    def _realize_tab(self, key: str):
        """Если вкладка ещё плейсхолдер — заменить его на реальный виджет."""
        if self._in_realize:
            return
        self._in_realize = True
        try:
            attr, module_path, class_name, title = self.TAB_SPECS[key]
            current = getattr(self, attr, None)
            if current is not None and current.property("realized") is True:
                return

            # Найти индекс текущей вкладки (плейсхолдер/реальная)
            idx = -1
            for i in range(self.tabs.count()):
                w = self.tabs.widget(i)
                if w is getattr(self, attr) or (w is not None and w.property("tab_key") == key):
                    idx = i
                    break
            if idx == -1:
                return

            # Создать реальный виджет
            import importlib
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
            inst = cls(self)
            inst.setProperty("tab_key", key)
            inst.setProperty("realized", True)

            # Подмена БЕЗ генерации currentChanged
            self.tabs.blockSignals(True)
            try:
                self.tabs.removeTab(idx)
                self.tabs.insertTab(idx, inst, title)
                self.tabs.setCurrentIndex(idx)
            finally:
                self.tabs.blockSignals(False)

            setattr(self, attr, inst)
        finally:
            self._in_realize = False

    def _on_current_tab_changed(self, idx: int):
        """При первом заходе на вкладку — инициализируем её содержимое (лениво)."""
        if self._in_realize or idx is None or idx < 0:
            return
        w = self.tabs.widget(idx)
        if w is None:
            return
        key = w.property("tab_key")
        if isinstance(key, str):
            self._realize_tab(key)


    def _ini_bool(self, group: str, key: str, default: bool) -> bool:
        s = self._settings()
        s.beginGroup(group)
        val = s.value(key, None)
        s.endGroup()
        if val is None:
            return default
        return str(val).lower() in ("1","true","yes","on")

    def _set_ini_bool(self, group: str, key: str, value: bool) -> None:
        s = self._settings()
        s.beginGroup(group)
        s.setValue(key, "1" if value else "0")
        s.endGroup()

    def _reorder_tabs_to_spec(self):
        """Фиксированный порядок вкладок без пересоздания."""
        desired = []
        for key, (attr, _m, _c, title) in self.TAB_SPECS.items():
            w = getattr(self, attr, None)
            if w is not None:
                desired.append((key, attr, w, title))

        self.tabs.blockSignals(True)
        try:
            for target_index, (_key, attr, w, title) in enumerate(desired):
                cur_index = self.tabs.indexOf(w)
                if cur_index == -1:
                    self.tabs.insertTab(target_index, w, title)
                elif cur_index != target_index:
                    self.tabs.removeTab(cur_index)
                    self.tabs.insertTab(target_index, w, title)
        finally:
            self.tabs.blockSignals(False)

    def _ensure_tab_enabled(self, key: str, enable: bool):
        """Создаёт/удаляет вкладку на лету. При включении — плейсхолдер, контент ленивый."""
        attr, _module_path, _class_name, title = self.TAB_SPECS[key]
        current = getattr(self, attr, None)

        if enable and current is None:
            # добавляем плейсхолдер, контент создадим при первом открытии
            self._add_lazy_tab(key, title)
            return

        if not enable and current is not None:
            idx = self.tabs.indexOf(current)
            if idx != -1:
                self.tabs.removeTab(idx)
            current.deleteLater()
            setattr(self, attr, None)

    def _apply_tabs_from_settings(self):
        """Включает/выключает вкладки согласно INI и выстраивает порядок."""
        self.tabs.blockSignals(True)
        try:
            for key in self.TAB_SPECS.keys():
                self._ensure_tab_enabled(key, self._ini_bool("Tabs", key, True))
            self._reorder_tabs_to_spec()
        finally:
            self.tabs.blockSignals(False)

    def _settings(self) -> QSettings:
        return QSettings(str(SETTINGS_PATH), QSettings.IniFormat)

    # ------- Theme (light/dark/system) -------
    def _read_theme(self) -> str:
        s = self._settings()
        s.beginGroup("UI")
        val = s.value("theme", "light")
        s.endGroup()
        v = str(val).lower()
        return v if v in ("light", "dark") else "light"

    def _write_theme(self, theme: str) -> None:
        s = self._settings()
        s.beginGroup("UI")
        s.setValue("theme", theme)
        s.endGroup()
        s.sync()

    def _apply_theme(self, theme: str):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        g = self.saveGeometry()
        try:
            if theme == "dark":
                QApplication.setStyle("Fusion")
                dark = QPalette()
                dark.setColor(QPalette.Window, QColor(53, 53, 53))
                dark.setColor(QPalette.WindowText, QColor(220, 220, 220))
                dark.setColor(QPalette.Base, QColor(35, 35, 35))
                dark.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
                dark.setColor(QPalette.Text, QColor(220, 220, 220))
                dark.setColor(QPalette.Button, QColor(53, 53, 53))
                dark.setColor(QPalette.ButtonText, QColor(220, 220, 220))
                dark.setColor(QPalette.Highlight, QColor(42, 130, 218))
                dark.setColor(QPalette.HighlightedText, QColor(0, 0, 0))

                # --- подчёркиваем неактивные (disabled) элементы в тёмной теме ---
                dim_txt = QColor(140, 140, 140)  # тусклый текст
                dim_bg = QColor(45, 45, 45)  # слегка светлее Base
                dim_base = QColor(50, 50, 50)  # фон полей ввода (disabled)

                # Текстовые роли (подписи, текст на кнопках, в полях и т.п.)
                dark.setColor(QPalette.Disabled, QPalette.WindowText, dim_txt)
                dark.setColor(QPalette.Disabled, QPalette.Text, dim_txt)
                dark.setColor(QPalette.Disabled, QPalette.ButtonText, dim_txt)
                dark.setColor(QPalette.Disabled, QPalette.ToolTipText, dim_txt)
                dark.setColor(QPalette.Disabled, QPalette.HighlightedText, dim_txt)

                # Фоны
                dark.setColor(QPalette.Disabled, QPalette.Window, dim_bg)
                dark.setColor(QPalette.Disabled, QPalette.Base, dim_base)
                dark.setColor(QPalette.Disabled, QPalette.AlternateBase, dim_bg)
                dark.setColor(QPalette.Disabled, QPalette.Button, dim_bg)

                # Акцент и ссылка тоже приглушённые
                dark.setColor(QPalette.Disabled, QPalette.Highlight, QColor(70, 70, 70))
                dark.setColor(QPalette.Disabled, QPalette.Link, QColor(120, 160, 200))

                QApplication.setPalette(dark)
                app.setStyleSheet("")
                # лёгкая «переполировка» — заставит стиль переложиться
                app.setStyle(app.style().objectName())
                return

            # ---- LIGHT: полный откат к штатным значениям ----
            QApplication.setStyle(self._default_style_name)
            QApplication.setPalette(QPalette())
            app.setStyleSheet("")


            # переполировка, чтобы виджеты гарантированно перечитали палитру
            app.setStyle(app.style().objectName())
        finally:
            self.restoreGeometry(g)

    def __init__(self):
        super().__init__()
        self._in_realize = False
        self.setWindowTitle("SmithanaTool")
        icon_path = _BUNDLE_ROOT / "assets" / "smithanatool.ico"
        self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(1400, 800)

        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._on_current_tab_changed)
        layout.addWidget(self.tabs)

        # === Читаем флаги вкладок из INI ===
        s = self._settings()

        def ini_bool(group: str, key: str, default: bool) -> bool:
            s.beginGroup(group)
            val = s.value(key, None)
            s.endGroup()
            if val is None:
                return default
            return str(val).lower() in ("1", "true", "yes", "on")


        self.setStatusBar(QStatusBar(self))
        # === Флаги из INI ===
        enable_transform = self._ini_bool("Tabs", "transform", True)
        enable_manhwa    = self._ini_bool("Tabs", "parser_manhwa", True)
        enable_novel     = self._ini_bool("Tabs", "parser_novel", True)
        enable_info      = self._ini_bool("Tabs", "info", True)

        # === Применяем сразу (создаём только включённые) ===
        self._apply_tabs_from_settings()



        app = QApplication.instance()
        self._default_style_name = app.style().objectName()
        self._default_palette = app.style().standardPalette()
        self._apply_theme(self._read_theme())

        # === Меню "Вид" → "Вкладки" с «горячим» переключением ===
        menu_view = self.menuBar().addMenu("Вид")


        tabs_menu = menu_view.addMenu("Вкладки")

        def add_tab_toggle(title, key, current):
            act = tabs_menu.addAction(title)
            act.setCheckable(True)
            act.setChecked(current)

            def on_toggle(checked: bool):
                self._set_ini_bool("Tabs", key, checked)
                self._ensure_tab_enabled(key, checked)
                self._reorder_tabs_to_spec()

            act.toggled.connect(on_toggle)
            return act

        # создаём действия- переключатели
        self._act_tab_transform = add_tab_toggle("Преобразования",   "transform",     enable_transform)
        self._act_tab_manhwa    = add_tab_toggle("Парсер манхв",     "parser_manhwa", enable_manhwa)
        self._act_tab_novel     = add_tab_toggle("Парсер новелл",    "parser_novel",  enable_novel)
        self._act_tab_info      = add_tab_toggle("Инфо",             "info",          enable_info)

        #--- Тема ---
        theme_menu = menu_view.addMenu("Тема")
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)

        current_theme = self._read_theme()
        if current_theme not in ("light", "dark"):
            current_theme = "light"  # дефолт

        def mk_theme_action(title: str, key: str):
            act = theme_menu.addAction(title)
            act.setCheckable(True)
            act.setChecked(current_theme == key)
            theme_group.addAction(act)

            def on_toggled(checked: bool):
                if not checked:
                    return
                self._write_theme(key)
                self._apply_theme(key)

            act.toggled.connect(on_toggled)
            return act

        self._act_theme_light = mk_theme_action("Светлая", "light")
        self._act_theme_dark = mk_theme_action("Тёмная", "dark")

        act_reset_zoom = menu_view.addAction("Сбросить масштаб окна")
        act_reset_zoom.triggered.connect(self._reset_window_size)

        # Restore window geometry
        try:
            restore_window_geometry(self)
        except Exception:
            pass

    def _clear_local_styles(self, root: QWidget):
        from PySide6.QtWidgets import QWidget
        from PySide6.QtGui import QPalette

        # ⚠️ ничего не трогаем у помеченных keep_qss
        if not root.property("keep_qss"):
            root.setPalette(QPalette())
            if root.styleSheet():
                root.setStyleSheet("")

        for child in root.findChildren(QWidget):
            if child.property("keep_qss"):
                continue
            child.setPalette(QPalette())
            if child.styleSheet():
                child.setStyleSheet("")


    def closeEvent(self, e):
        current = self.tabs.currentWidget()
        if hasattr(current, "can_close") and not current.can_close():
            e.ignore()
            return

        try:
            for p in self.findChildren(PreviewPanel):
                if hasattr(p, "discard_changes"):
                    p.discard_changes()
        except Exception:
            pass

        try:
            save_window_geometry(self)
        except Exception:
            pass

        super().closeEvent(e)


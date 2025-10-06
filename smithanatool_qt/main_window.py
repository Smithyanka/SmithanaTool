from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QTabWidget, QStatusBar, QApplication, QHBoxLayout, QLabel, QToolButton, QMenu, QSizePolicy, QStyle, QProgressBar, QMessageBox
from PySide6.QtCore import Qt, QSettings, QPoint, QEvent, QSize, QPointF, QRect, QTimer
from PySide6.QtGui import QIcon, QCloseEvent

import sys
from pathlib import Path

from smithanatool_qt.tabs.transform import TransformTab
from smithanatool_qt.tabs.parser_manhwa_tab import ParserManhwaTab
from smithanatool_qt.tabs.parser_novel_tab import ParserNovelTab
from smithanatool_qt.tabs.info_tab import InfoTab
from smithanatool_qt.tabs.transform.preview_panel import PreviewPanel
from smithanatool_qt.settings_bind import restore_window_geometry, save_window_geometry
from smithanatool_qt.theme import apply_dark_theme, BORDER_DIM, BG_BASE
from smithanatool_qt.tabs.transform.gallery.panel import GalleryPanel

# Новые импорты из ваших модулей
from .graphic.foundation.assets import asset_path
from .graphic.foundation.frameless import install_frameless_resize
from .graphic.ui.titlebar import TitleBar


from smithanatool_qt.settings_bind import (
    restore_window_geometry, save_window_geometry,
    group, get_value, set_value, ini_path
)

_BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


class MainWindow(QMainWindow):
    TAB_SPECS = {
        "transform":     ("_transform_tab",    "smithanatool_qt.tabs.transform",            "TransformTab",    "Преобразования"),
        "parser_manhwa": ("_parser_manhwa_tab","smithanatool_qt.tabs.parser_manhwa_tab",    "ParserManhwaTab", "Парсер манхв Kakao"),
        "parser_novel":  ("_parser_novel_tab", "smithanatool_qt.tabs.parser_novel_tab",     "ParserNovelTab",  "Парсер новелл Kakao"),
        "info":          ("_info_tab",         "smithanatool_qt.tabs.info_tab",             "InfoTab",         "Инфо"),
    }

    def _has_unsaved_changes(self) -> bool:
        for g in self.findChildren(GalleryPanel):
            try:
                if g._has_unsaved():
                    return True
            except Exception:
                pass
        return False


    def _show_loading(self, text="Загрузка…"):
        # накрываем именно панель вкладок
        self._loading = _LoadingOverlay(self.tabs, text)
        self._loading.start(text)

    def _hide_loading(self):
        ov = getattr(self, "_loading", None)
        if ov:
            ov.stop()
            self._loading = None
    def _restore_persisted_child_states(self, root: QWidget):
        with group("MainWindow"):
            with group("Widgets"):
                for w in root.findChildren(QWidget):
                    key = w.property("persist_key")
                    if key and hasattr(w, "restoreState"):
                        val = get_value(str(key), None)
                        if val is not None:
                            try:
                                w.restoreState(val)
                            except Exception:
                                pass

    def _save_persisted_child_states(self):
        with group("MainWindow"):
            with group("Widgets"):
                for w in self.findChildren(QWidget):
                    key = w.property("persist_key")
                    if key and hasattr(w, "saveState"):
                        try:
                            set_value(str(key), w.saveState())
                        except Exception:
                            pass

    def _reset_window_size(self):
        self.setWindowState(Qt.WindowNoState)
        try:
            # чистим всю группу MainWindow (включая geometry и Widgets/*)
            q = QSettings(str(ini_path()), QSettings.IniFormat)
            q.beginGroup("MainWindow");
            q.remove("");
            q.endGroup()
            # при необходимости чистим наследие старых групп:
            q.beginGroup("Window");
            q.remove("");
            q.endGroup()
            q.remove("TransformTab")
            q.sync()
        except Exception:
            pass

        self.resize(1400, 800)
        scr = self.screen()
        if scr:
            ag = scr.availableGeometry()
            g = self.geometry()
            g.moveCenter(ag.center());
            self.move(g.topLeft())

        # сброс внутренних layout'ов вкладок — как было
        try:
            for tab in (
                    getattr(self, "_transform_tab", None),
                    getattr(self, "_parser_manhwa_tab", None),
                    getattr(self, "_parser_novel_tab", None),
                    getattr(self, "_info_tab", None),
            ):
                if tab is not None and tab.property("realized") is True:
                    if hasattr(tab, "reset_layout_to_defaults"):
                        tab.reset_layout_to_defaults()
        except Exception:
            pass

    def _realize_active_tab_later(self):
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
        from PySide6.QtWidgets import QWidget
        placeholder = QWidget()
        placeholder.setProperty("tab_key", key)
        placeholder.setProperty("realized", False)
        attr, _module, _cls, _title = self.TAB_SPECS[key]
        setattr(self, attr, placeholder)
        self.tabs.addTab(placeholder, title)

    def _realize_tab(self, key: str):
        # 0) если уже реализована — ничего не делаем и loader не показываем
        try:
            attr, module_path, class_name, title = self.TAB_SPECS[key]
        except Exception:
            attr, title = None, "вкладки…"

        current = getattr(self, attr, None) if attr else None
        if current is not None and current.property("realized") is True:
            return

        if getattr(self, "_in_realize", False):
            return
        self._in_realize = True

        def _do_realize():
            try:
                # найти индекс заглушки
                idx = -1
                for i in range(self.tabs.count()):
                    w = self.tabs.widget(i)
                    if w is getattr(self, attr) or (w is not None and w.property("tab_key") == key):
                        idx = i;
                        break
                if idx == -1:
                    return

                # показываем лоадер ТОЛЬКО когда реально начинаем сборку
                self._show_loading(f"Открываю «{title}»…")

                import importlib
                module = importlib.import_module(module_path)
                cls = getattr(module, class_name)
                inst = cls(self)
                inst.setProperty("tab_key", key)
                inst.setProperty("realized", True)
                self._restore_persisted_child_states(inst)

                self.tabs.blockSignals(True)
                try:
                    self.tabs.removeTab(idx)
                    self.tabs.insertTab(idx, inst, title)
                    self.tabs.setCurrentIndex(idx)
                finally:
                    self.tabs.blockSignals(False)
                setattr(self, attr, inst)
            finally:
                self._hide_loading()
                self._in_realize = False

        QTimer.singleShot(0, _do_realize)

    def _on_current_tab_changed(self, idx: int):
        if getattr(self, "_in_realize", False) or idx is None or idx < 0:
            return
        w = self.tabs.widget(idx)
        if w is None:
            return
        key = w.property("tab_key")
        if isinstance(key, str):
            self._realize_tab(key)

    def _ini_bool(self, group_name: str, key: str, default: bool) -> bool:
        with group("MainWindow"):
            with group(group_name):
                return bool(get_value(key, default, typ=bool))

    def _set_ini_bool(self, group_name: str, key: str, value: bool) -> None:
        with group("MainWindow"):
            with group(group_name):
                set_value(key, bool(value))

    def _reorder_tabs_to_spec(self):
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
        attr, _module_path, _class_name, title = self.TAB_SPECS[key]
        current = getattr(self, attr, None)
        if enable and current is None:
            self._add_lazy_tab(key, title); return
        if not enable and current is not None:
            idx = self.tabs.indexOf(current)
            if idx != -1:
                self.tabs.removeTab(idx)
            current.deleteLater()
            setattr(self, attr, None)

    def _apply_tabs_from_settings(self):
        self.tabs.blockSignals(True)
        try:
            for key in self.TAB_SPECS.keys():
                self._ensure_tab_enabled(key, self._ini_bool("Tabs", key, True))
            self._reorder_tabs_to_spec()
        finally:
            self.tabs.blockSignals(False)

    def _apply_theme(self):
        app = QApplication.instance()
        g = self.saveGeometry()
        try:
            apply_dark_theme(app)
        finally:
            self.restoreGeometry(g)

    def __init__(self):
        super().__init__()
        self._normal_geom = None
        self._in_realize = False
        self.setWindowTitle("SmithanaTool")
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)

        self.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.setWindowFlag(Qt.WindowSystemMenuHint, True)
        icon_path = asset_path("smithanatool.ico")
        self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(1400, 800)

        central = QWidget(self)
        self.setCentralWidget(central)
        self.setMouseTracking(True)
        central.setMouseTracking(True)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)

        # Ресайз по краям (вынесен в helper)
        self._frameless_helper = install_frameless_resize(self, margin=6)

        self.tabs = QTabWidget()
        self._style_tabs()
        self.tabs.setMouseTracking(True)
        self.tabs.currentChanged.connect(self._on_current_tab_changed)
        layout.addWidget(self.tabs)

        # === Флаги вкладок из INI ===
        enable_transform = self._ini_bool("Tabs", "transform", True)
        enable_manhwa    = self._ini_bool("Tabs", "parser_manhwa", True)
        enable_novel     = self._ini_bool("Tabs", "parser_novel", True)
        enable_info      = self._ini_bool("Tabs", "info", True)

        self.setStatusBar(QStatusBar(self))


        self.statusBar().setSizeGripEnabled(False)


        sb = self.statusBar()
        # высота:
        sb.setFixedHeight(15)
        # === Footer ===
        self.statusBar().setStyleSheet(f"""
            QStatusBar {{
                border-top: 1px solid #303030;  
                background: #181818;   
            }}
        """)

        # Применить вкладки (ленивая инициализация)
        self._apply_tabs_from_settings()

        app = QApplication.instance()
        self._default_style_name = app.style().objectName()
        self._default_palette = app.style().standardPalette()
        self._apply_theme()

        # Меню "Вид" → "Вкладки"
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

        self._act_tab_transform = add_tab_toggle("Преобразования",   "transform",     enable_transform)
        self._act_tab_manhwa    = add_tab_toggle("Парсер манхв",     "parser_manhwa", enable_manhwa)
        self._act_tab_novel     = add_tab_toggle("Парсер новелл",    "parser_novel",  enable_novel)
        self._act_tab_info      = add_tab_toggle("Инфо",             "info",          enable_info)

        act_reset_zoom = menu_view.addAction("Сбросить масштаб окна")
        act_reset_zoom.triggered.connect(self._reset_window_size)

        # Вынесенный TitleBar
        self.titlebar = TitleBar(self, view_menu=menu_view, small_text="v1.0.5")
        layout.insertWidget(0, self.titlebar)
        self.menuBar().setVisible(False)

        try:
            restore_window_geometry(self)
        except Exception:
            pass

        self._normal_geom = self.geometry()

        if self.isMaximized() or self.isFullScreen():
            g = QRect(0, 0, 1400, 800)
            scr = self.screen()
            if scr:
                g.moveCenter(scr.availableGeometry().center())
            self._normal_geom = g

    def showEvent(self, e):
        super().showEvent(e)
        self._realize_active_tab_later()

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == QEvent.WindowStateChange:
            # когда окно вернулось в Normal — обновим нормальную геометрию
            if not (self.isMaximized() or self.isFullScreen()):
                g = self.geometry()
                if g.width() >= 200 and g.height() >= 150:
                    self._normal_geom = g


    def _style_tabs(self):
        css = """
        
        QTabWidget::pane {
            border-top: 1px solid #303030;  
            border-left: 0;
            border-right: 0;
            border-bottom: 0;
            padding-top: 0;
            background: transparent;
        }
        QTabBar {
            qproperty-drawBase: 0;
            
        }
        QTabBar::tab {
            background: transparent;
            color: #C8D0D9;
            border: 0;
            border-bottom: 3px solid transparent;
            border-radius: 0;                     
            padding: 8px 14px;                     
            margin: 0 8px;
            font-weight: 600;
            
        }
        QTabBar::tab:hover {
            background: rgba(255,255,255,0.06);
            color: #FFFFFF;
        }
        QTabBar::tab:selected {
            color: #FFFFFF;
            border-bottom-color: #2287d5;  
        }
        """
        self.tabs.setStyleSheet(css)
        self.tabs.setIconSize(QSize(18, 18))
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setDrawBase(False)
        self.tabs.setElideMode(Qt.ElideRight)

    def closeEvent(self, e):
        current = self.tabs.currentWidget()
        if hasattr(current, "can_close") and not current.can_close():
            e.ignore();
            return

        try:
            if self._has_unsaved_changes():
                btn = QMessageBox.warning(
                    self, "Выход",
                    "Есть несохранённые изменения. Выйти?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if btn != QMessageBox.Yes:
                    e.ignore()
                    return
        except Exception:
            pass

        try:
            for p in self.findChildren(PreviewPanel):
                if hasattr(p, "discard_changes"):
                    p.discard_changes()
        except Exception:
            pass
        try:
            self._save_persisted_child_states()
        except Exception:
            pass
        try:
            save_window_geometry(self)
        except Exception:
            pass
        super().closeEvent(e)


class _LoadingOverlay(QWidget):
    def __init__(self, parent, text="Загрузка…"):
        super().__init__(parent)
        self.setObjectName("loadingOverlay")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setContentsMargins(40, 40, 40, 40)

        self._bar = QProgressBar(self)
        self._bar.setRange(0, 0)
        self._bar.setFixedWidth(240)

        self._lbl = QLabel(text, self)
        self._lbl.setObjectName("loaderText")

        lay.addWidget(self._bar)
        lay.addWidget(self._lbl)
        self.hide()

    def start(self, text=None):
        if text: self._lbl.setText(text)
        # перекрываем всю область вкладок
        p = self.parent()
        self.setGeometry(p.rect())
        self.show()
        QApplication.processEvents()  # дать UI прорисоваться

    def stop(self):
        self.hide()
        self.deleteLater()


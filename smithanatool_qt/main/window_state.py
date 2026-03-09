from __future__ import annotations

from typing import Iterable, Optional

from PySide6.QtCore import Qt, QSettings, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QProgressBar, QVBoxLayout, QWidget

from smithanatool_qt.settings_bind import group, get_value, ini_path, save_window_geometry, set_value


def restore_persisted_child_states(root: QWidget) -> None:
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


def save_persisted_child_states(root: QWidget) -> None:
    with group("MainWindow"):
        with group("Widgets"):
            for w in root.findChildren(QWidget):
                key = w.property("persist_key")
                if key and hasattr(w, "saveState"):
                    try:
                        set_value(str(key), w.saveState())
                    except Exception:
                        pass


def reset_window_size(win: QMainWindow, realized_tabs: Optional[Iterable[QWidget]] = None) -> None:
    win.setWindowState(Qt.WindowNoState)
    QApplication.processEvents()

    win.resize(1400, 800)
    scr = win.screen()
    if scr:
        ag = scr.availableGeometry()
        g = win.geometry()
        g.moveCenter(ag.center())
        win.move(g.topLeft())

    try:
        save_window_geometry(win)
    except Exception:
        pass

    if realized_tabs:
        try:
            for tab in realized_tabs:
                if tab is not None and tab.property("realized") is True:
                    if hasattr(tab, "reset_layout_to_defaults"):
                        QTimer.singleShot(0, tab.reset_layout_to_defaults)
        except Exception:
            pass


class LoadingOverlay(QWidget):
    def __init__(self, parent: QWidget, text):
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

    def start(self, text: str | None = None) -> None:
        if text:
            self._lbl.setText(text)
        p = self.parent()
        if p is not None:
            self.setGeometry(p.rect())
        self.show()
        QApplication.processEvents()

    def stop(self) -> None:
        self.hide()
        self.deleteLater()

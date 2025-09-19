
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QTabWidget, QStatusBar
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

import sys
from pathlib import Path

from smithanatool_qt.tabs.transform import TransformTab
from smithanatool_qt.tabs.parser_manhwa_tab import ParserManhwaTab
from smithanatool_qt.tabs.parser_novel_tab import ParserNovelTab
from smithanatool_qt.tabs.info_tab import InfoTab

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SmithanaTool (Qt)")
        icon_path = Path(__file__).resolve().parent / "assets" / "smithanatool.ico"
        self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(1400, 840)

        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Tabs per new structure
        self._transform_tab = TransformTab(self)
        self._parser_manhwa_tab = ParserManhwaTab(self)
        self._parser_novel_tab = ParserNovelTab(self)
        self._info_tab = InfoTab(self)

        self.tabs.addTab(self._transform_tab, "Преобразования")
        self.tabs.addTab(self._parser_manhwa_tab, "Парсер манхв Kakao")
        self.tabs.addTab(self._parser_novel_tab, "Парсер новелл Kakao")
        self.tabs.addTab(self._info_tab,"Инфо")

        self.setStatusBar(QStatusBar(self))

    def closeEvent(self, e):
        current = self.tabs.currentWidget()
        if hasattr(current, "can_close") and not current.can_close():
            e.ignore()
            return
        super().closeEvent(e)



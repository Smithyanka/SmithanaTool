from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QHBoxLayout, QSplitter, QWidget, QSizePolicy

from smithanatool_qt.settings_bind import bind_attr_string, ini_path, save_attr_string

from .common.base_page import BaseParserPage
from .common.modes import MODE_MANHWA, VALID_PARSER_MODES
from .kakao.manhwa.tab import ParserManhwaTab
from .kakao.novel.tab import ParserNovelTab
from .parser_panel import ParsersStackPanel
from .shared_log import SharedLogPanel


LEFT_MIN_W = 520
RIGHT_MIN_W = 400

EXTERNAL_LOG_SPLITTER_SIZES = (1, 0)


class ParsersTab(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._mode = MODE_MANHWA
        self._manhwa_tab: Optional[ParserManhwaTab] = None
        self._novel_tab: Optional[ParserNovelTab] = None

        self._apply_settings_from_ini()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Horizontal, self)
        self.splitter.setChildrenCollapsible(True)
        layout.addWidget(self.splitter)

        self.stack_panel = ParsersStackPanel(
            manhwa_factory=self._build_manhwa_tab,
            novel_factory=self._build_novel_tab,
            parent=self,
        )
        self.stack_panel.modeChanged.connect(self._on_mode_changed)

        self.log_panel = SharedLogPanel(self)

        self.splitter.addWidget(self.stack_panel)
        self.splitter.addWidget(self.log_panel)
        self.splitter.setCollapsible(0, False)  # левая панель
        self.splitter.setCollapsible(1, False)  # правая панель
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([LEFT_MIN_W, RIGHT_MIN_W])

        self.stack_panel.setMinimumWidth(LEFT_MIN_W)
        self.log_panel.setMinimumWidth(RIGHT_MIN_W)

        self.stack_panel.set_mode(self._mode, emit=False)
        self._refresh_shared_log_context()

    def _migrate_ini(self) -> None:
        section = 'ParsersTab'
        try:
            qs = QSettings(str(ini_path()), QSettings.IniFormat)
            for full_key in list(qs.allKeys()):
                parts = str(full_key).split('/')
                if len(parts) < 3 or parts[0] != section or parts[1] != section:
                    continue

                idx = 1
                while idx < len(parts) and parts[idx] == section:
                    idx += 1

                target_key = '/'.join([section] + parts[idx:])
                if qs.value(target_key, None) is None:
                    qs.setValue(target_key, qs.value(full_key))
                qs.remove(full_key)
            qs.sync()
        except Exception:
            pass

    def _apply_settings_from_ini(self) -> None:
        self._migrate_ini()
        try:
            bind_attr_string(self, '_mode', 'ParsersTab/mode', MODE_MANHWA)
        except Exception:
            pass

        self._mode = (self._mode or MODE_MANHWA).strip().lower()
        if self._mode not in VALID_PARSER_MODES:
            self._mode = MODE_MANHWA

    def _build_page(self, page_cls: type[BaseParserPage], attr_name: str) -> BaseParserPage:
        tab = page_cls(self)
        tab.configure_panel_sizes(
            external_log_sizes=EXTERNAL_LOG_SPLITTER_SIZES,
        )
        tab.set_log_sink(self.log_panel.append_log)
        setattr(self, attr_name, tab)
        return tab

    def _build_manhwa_tab(self) -> ParserManhwaTab:
        return self._build_page(ParserManhwaTab, '_manhwa_tab')

    def _build_novel_tab(self) -> ParserNovelTab:
        return self._build_page(ParserNovelTab, '_novel_tab')

    def _on_mode_changed(self, mode: str) -> None:
        self._mode = mode
        try:
            save_attr_string(self, '_mode', 'ParsersTab/mode')
            self._refresh_shared_log_context()
        except Exception:
            pass

    def _current_tab(self) -> Optional[BaseParserPage]:
        return self.stack_panel.current_page()


    def can_close(self) -> bool:
        for tab in (self._manhwa_tab, self._novel_tab):
            if tab is not None and not tab.can_close():
                return False
        return True

    def reset_layout_to_defaults(self) -> None:
        self.splitter.setSizes([LEFT_MIN_W, RIGHT_MIN_W])

    def _refresh_shared_log_context(self) -> None:
        current = self._current_tab()

        if current is None:
            self.log_panel.set_session_context(None)
            return

        self.log_panel.set_session_context(current.get_out_dir)

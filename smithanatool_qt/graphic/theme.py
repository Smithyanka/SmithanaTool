from __future__ import annotations

from enum import Enum
from importlib import resources
from string import Template

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication
from smithanatool_qt.graphic.foundation.assets import refresh_themed_icons

class ThemeMode(str, Enum):
    DARK = "dark"
    LIGHT = "light"


# -------------------- QSS helpers --------------------

QSS_PARTS = [
    "app.qss",
    "main_window.qss",
    "components/conversions_panel.qss",
    "components/gallery_panel.qss",
    "components/busy_overlay.qss",
    "components/preview_panel.qss",
    "components/workshop.qss",
    "components/ai.qss",
]


QSS_TOKENS_DARK = {
    "theme": "white",
    "universal_1": "#2c2c2c",  # qss: app, main_window
    "universal_1_2": "31, 31, 31",  # qss: preview_panel
    "universal_1_3": "44, 44, 44",  # qss: preview_panel
    "universal_1_4": "69, 69, 69",  # qss: preview_panel
    "universal_2": "rgba(255,255,255,0.5)",  # qss: main_window
    "universal_2_2": "255,255,255",  # qss: main_window
}

# Важно: это НЕ “идеальные” цвета, а безопасные дефолты,
# чтобы твой текущий QSS не выглядел странно в светлой теме.
QSS_TOKENS_LIGHT = {
    "theme": "black",
    "universal_1": "#e7e7e7",
    "universal_1_2": "255, 255, 255",
    "universal_1_3": "240, 240, 240",
    "universal_1_4": "210, 210, 210",
    "universal_2": "rgba(0,0,0,0.35)",
    "universal_2_2": "0,0,0",  # qss: main_window
}


def _read_qss(rel_path: str, tokens: dict[str, str]) -> str:
    text = resources.files("smithanatool_qt.styles").joinpath(rel_path).read_text(encoding="utf-8")
    return Template(text).safe_substitute(tokens or {})


def _build_stylesheet(tokens: dict[str, str]) -> str:
    return "\n\n".join(_read_qss(p, tokens) for p in QSS_PARTS)


# -------------------- Palette builders --------------------

def _make_dark_palette() -> QPalette:

    ACCENT = QColor(35, 135, 213)  # выделение / активные акценты (selection, highlight)
    ACCENT_DARK = QColor(35, 135, 213)  # нажатое / посещённые ссылки (сейчас совпадает с ACCENT)
    ACCENT_DIM = QColor(35, 135, 213)  # обводка при наведении (оставлено для совместимости; сейчас совпадает)



    # Поверхности (фоны)
    BG_WINDOW = QColor(24, 24, 24)   # фон главного окна
    BG_BASE = QColor(31, 31, 31)     # фон полей ввода / “утопленных” областей
    BG_ALT = QColor(20, 28, 44)      # альтернативный фон: чередование строк / панели
    BG_BUTTON = QColor(31, 31, 31)   # фон кнопок

    # Текст
    TXT_MAIN = QColor(255, 255, 255)  # основной цвет текста
    TXT_DIM = QColor(64, 64, 64)      # disabled текст

    # Границы / линии
    BORDER_DIM = QColor(69, 69, 69)   # часто используется через palette(mid) в QSS

    pal = QPalette()

    # Основные фоны
    pal.setColor(QPalette.Window, BG_WINDOW)
    pal.setColor(QPalette.Base, BG_BASE)
    pal.setColor(QPalette.AlternateBase, BG_ALT)
    pal.setColor(QPalette.Button, BG_BUTTON)

    # Основные цвета текста
    pal.setColor(QPalette.WindowText, TXT_MAIN)
    pal.setColor(QPalette.Text, TXT_MAIN)
    pal.setColor(QPalette.ButtonText, TXT_MAIN)
    pal.setColor(QPalette.ToolTipText, TXT_MAIN)
    pal.setColor(QPalette.ToolTipBase, BG_ALT)
    pal.setColor(QPalette.PlaceholderText, QColor(200, 210, 220, 120))

    # Акценты
    pal.setColor(QPalette.Highlight, ACCENT)
    pal.setColor(QPalette.HighlightedText, QColor(0, 0, 0))
    pal.setColor(QPalette.Link, ACCENT)
    pal.setColor(QPalette.LinkVisited, ACCENT_DARK)

    # Доп. роли для palette(...)
    pal.setColor(QPalette.Mid, BORDER_DIM)
    pal.setColor(QPalette.Midlight, QColor(80, 80, 80))
    pal.setColor(QPalette.Light, QColor(90, 90, 90))
    pal.setColor(QPalette.Dark, QColor(48, 48, 48))

    # Disabled
    pal.setColor(QPalette.Disabled, QPalette.WindowText, TXT_DIM)
    pal.setColor(QPalette.Disabled, QPalette.Text, TXT_DIM)
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, TXT_DIM)
    pal.setColor(QPalette.Disabled, QPalette.ToolTipText, TXT_DIM)
    pal.setColor(QPalette.Disabled, QPalette.HighlightedText, TXT_DIM)

    pal.setColor(QPalette.Disabled, QPalette.Base, BG_BASE)
    pal.setColor(QPalette.Disabled, QPalette.Highlight, QColor(70, 80, 100))
    pal.setColor(QPalette.Disabled, QPalette.Link, QColor(120, 160, 200))

    return pal


def _make_light_palette() -> QPalette:

    ACCENT = QColor(111,181,236)  # выделение / активные акценты (selection, highlight)
    ACCENT_DARK = QColor(35, 135, 213)  # нажатое / посещённые ссылки (сейчас совпадает с ACCENT)
    ACCENT_DIM = QColor(35, 135, 213)  # обводка при наведении (оставлено для совместимости; сейчас совпадает)



    # Поверхности (фоны)
    BG_WINDOW = QColor(233, 233, 233)   # общий фон окна
    BG_BASE = QColor(255, 255, 255)     # фон инпутов/viewport
    BG_ALT = QColor(240, 244, 250)      # alternate rows / панели
    BG_BUTTON = QColor(255, 255, 255)   # фон кнопок

    # Текст
    TXT_MAIN = QColor(0, 0, 0)       # почти чёрный
    TXT_DIM = QColor(143,143,143)     # disabled текст

    # Границы / линии
    BORDER_DIM = QColor(214,214,214)

    pal = QPalette()

    pal.setColor(QPalette.Window, BG_WINDOW)
    pal.setColor(QPalette.Base, BG_BASE)
    pal.setColor(QPalette.AlternateBase, BG_ALT)
    pal.setColor(QPalette.Button, BG_BUTTON)

    pal.setColor(QPalette.WindowText, TXT_MAIN)
    pal.setColor(QPalette.Text, TXT_MAIN)
    pal.setColor(QPalette.ButtonText, TXT_MAIN)
    pal.setColor(QPalette.ToolTipText, TXT_MAIN)
    pal.setColor(QPalette.ToolTipBase, BG_BASE)
    pal.setColor(QPalette.PlaceholderText, QColor(107, 114, 128, 140))

    pal.setColor(QPalette.Highlight, ACCENT)
    pal.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    pal.setColor(QPalette.Link, ACCENT)
    pal.setColor(QPalette.LinkVisited, ACCENT_DARK)

    pal.setColor(QPalette.Mid, BORDER_DIM)
    pal.setColor(QPalette.Midlight, QColor(225, 228, 232))
    pal.setColor(QPalette.Light, QColor(235, 238, 242))
    pal.setColor(QPalette.Dark, QColor(190, 195, 203))

    pal.setColor(QPalette.Disabled, QPalette.WindowText, TXT_DIM)
    pal.setColor(QPalette.Disabled, QPalette.Text, TXT_DIM)
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, TXT_DIM)
    pal.setColor(QPalette.Disabled, QPalette.ToolTipText, TXT_DIM)
    pal.setColor(QPalette.Disabled, QPalette.HighlightedText, QColor(255, 255, 255))

    pal.setColor(QPalette.Disabled, QPalette.Base, QColor(250, 250, 250))
    pal.setColor(QPalette.Disabled, QPalette.Highlight, QColor(160, 190, 225))
    pal.setColor(QPalette.Disabled, QPalette.Link, QColor(140, 170, 210))

    return pal


# -------------------- Public API --------------------

def apply_theme(app, mode: ThemeMode | str) -> None:
    """Единая точка входа: переключает палитру + QSS."""
    QApplication.setStyle("Fusion")

    # нормализуем mode
    if isinstance(mode, ThemeMode):
        mode_value = mode.value
    else:
        mode_value = str(mode).strip().lower()

    if mode_value == ThemeMode.LIGHT.value:
        pal = _make_light_palette()
        tokens = QSS_TOKENS_LIGHT
    else:
        pal = _make_dark_palette()
        tokens = QSS_TOKENS_DARK

    QApplication.setPalette(pal)
    app.setStyleSheet(_build_stylesheet(tokens))

    # Фикс: иногда стиль “не перерисовывается” до следующего события.

    app.setStyle(app.style().objectName())



def apply_dark_theme(app) -> None:
    """Back-compat: старое имя."""
    apply_theme(app, ThemeMode.DARK)


def apply_light_theme(app) -> None:
    apply_theme(app, ThemeMode.LIGHT)

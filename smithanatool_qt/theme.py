# theme.py
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication

def apply_dark_theme(app):
    # Стиль
    QApplication.setStyle("Fusion")

    # Палитра (взято из текущего _apply_theme)
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

    # Disabled-состояния (как в исходном коде)
    dim_txt = QColor(140, 140, 140)
    dim_bg = QColor(45, 45, 45)
    dim_base = QColor(50, 50, 50)

    dark.setColor(QPalette.Disabled, QPalette.WindowText, dim_txt)
    dark.setColor(QPalette.Disabled, QPalette.Text, dim_txt)
    dark.setColor(QPalette.Disabled, QPalette.ButtonText, dim_txt)
    dark.setColor(QPalette.Disabled, QPalette.ToolTipText, dim_txt)
    dark.setColor(QPalette.Disabled, QPalette.HighlightedText, dim_txt)

    dark.setColor(QPalette.Disabled, QPalette.Window, dim_bg)
    dark.setColor(QPalette.Disabled, QPalette.Base, dim_base)
    dark.setColor(QPalette.Disabled, QPalette.AlternateBase, dim_bg)
    dark.setColor(QPalette.Disabled, QPalette.Button, dim_bg)

    dark.setColor(QPalette.Disabled, QPalette.Highlight, QColor(70, 70, 70))
    dark.setColor(QPalette.Disabled, QPalette.Link, QColor(120, 160, 200))

    QApplication.setPalette(dark)
    app.setStyleSheet("")
    # «Переполировка», чтобы виджеты перечитали палитру
    app.setStyle(app.style().objectName())


def apply_light_theme(app, default_style_name: str | None = None):
    # Полный откат к штатным значениям
    if default_style_name:
        QApplication.setStyle(default_style_name)
    else:
        QApplication.setStyle(QApplication.style().objectName())
    QApplication.setPalette(QPalette())
    app.setStyleSheet("")
    # Переполировка
    app.setStyle(app.style().objectName())

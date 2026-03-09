from PySide6.QtWidgets import QToolBar, QColorDialog
from PySide6.QtGui import QTextCharFormat, QTextCursor, QFont, QAction

class RichTextToolbar(QToolBar):
    def __init__(self, editor):
        super().__init__("Форматирование")
        self.editor = editor
        self._make_actions()

    def _make_actions(self):
        a_bold = self.addAction("B")
        a_bold.triggered.connect(lambda: self._toggle_weight())
        a_italic = self.addAction("I")
        a_italic.triggered.connect(lambda: self._merge(fmt_italic=True))
        a_underline = self.addAction("U")
        a_underline.triggered.connect(lambda: self._merge(fmt_underline=True))
        self.addSeparator()
        a_color = self.addAction("Цвет…")
        a_color.triggered.connect(self._pick_color)

    def _merge(self, fmt_italic=False, fmt_underline=False):
        fmt = QTextCharFormat()
        if fmt_italic:
            fmt.setFontItalic(True)
        if fmt_underline:
            fmt.setFontUnderline(True)
        self.editor.mergeCurrentCharFormat(fmt)

    def _toggle_weight(self):
        cur = self.editor.fontWeight()
        self.editor.setFontWeight(QFont.Normal if cur == QFont.Bold else QFont.Bold)

    def _pick_color(self):
        col = QColorDialog.getColor()
        if col.isValid():
            fmt = QTextCharFormat(); fmt.setForeground(col)
            self.editor.mergeCurrentCharFormat(fmt)

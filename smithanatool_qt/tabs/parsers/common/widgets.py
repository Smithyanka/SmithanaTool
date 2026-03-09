from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt

class ElidedLabel(QLabel):
    """QLabel, который автоматически укорачивает длинный текст с многоточием.
    По умолчанию — в середине (ElideMiddle). Хранит полный текст в tooltip.
    """
    def __init__(self, text: str = "", mode=Qt.ElideMiddle, parent=None):
        super().__init__(text, parent)
        self._full_text = text or ""
        self._mode = mode
        self.setToolTip(self._full_text if self._full_text else "")
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)

    def set_full_text(self, text: str):
        self._full_text = text or ""
        self.setToolTip(self._full_text if self._full_text else "")
        self._apply_elide()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply_elide()

    def _apply_elide(self):
        avail = max(10, self.width() - 8)
        elided = self.fontMetrics().elidedText(self._full_text, self._mode, avail)
        super().setText(elided)

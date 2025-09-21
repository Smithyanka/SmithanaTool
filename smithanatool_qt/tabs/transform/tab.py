from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QSplitter, QMessageBox
from smithanatool_qt.utils import dialogs

from .gallery_panel import GalleryPanel
from .preview_panel import PreviewPanel
from .sections_panel import SectionsPanel

class TransformTab(QWidget):
    """Собирает три панели в QSplitter и связывает их сигналами."""
    def __init__(self, parent=None):
        super().__init__(parent)

        splitter = QSplitter(Qt.Horizontal, self)
        self.gallery = GalleryPanel()
        self.preview = PreviewPanel()
        self.sections = SectionsPanel(self.gallery, self.preview)

        splitter.addWidget(self.gallery)
        splitter.addWidget(self.preview)
        splitter.addWidget(self.sections)
        splitter.setSizes([500, 800, 800])

        lay = QHBoxLayout(self)
        lay.addWidget(splitter)

        # Сигналы: выбор файла -> предпросмотр
        self.gallery.currentPathChanged.connect(self.preview.show_path)

        # Сохранение
        self.preview.btn_save.clicked.connect(self._save)
        self.preview.btn_save_as.clicked.connect(self._save_as)

    def _save(self):
        # Перезапись текущего изображения
        if self.preview.save_current_overwrite():
            QMessageBox.information(self, "Сохранено", "Изображение сохранено (замена файла).")
        else:
            QMessageBox.warning(self, "Ошибка", "Не удалось сохранить изображение.")

    def _save_as(self):
        path, _ = dialogs.ask_save_file(self, "Сохранить изображение как",
                                        "PNG (*.png);;JPEG (*.jpg *.jpeg);;Все файлы (*.*)")
        if not path:
            return
        if self.preview.save_current_as(path):
            QMessageBox.information(self, "Сохранено", f"Сохранено: {path}")
        else:
            QMessageBox.warning(self, "Ошибка", "Не удалось сохранить изображение.")


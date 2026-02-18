from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget, QHBoxLayout

from smithanatool_qt.tabs.gallery_preview_host import GalleryPreviewHost
from smithanatool_qt.tabs.transform.gallery import GalleryPanel
from smithanatool_qt.tabs.transform.preview import PreviewPanel

from .right_panel.panel import OcrRightPanel
from .viewer_controller import ExtractViewerController
from .ocr.ocr_service import ExtractOcrService
from .entries_controller import ExtractEntriesController


class ExtractTextTab(QWidget):
    """
    Вкладка «Извлечение текста» на общем host-е: Gallery | Preview | Right.
    Логика вынесена в контроллеры (без множественного наследования).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ExtractTextTab")

        self.host = GalleryPreviewHost(
            self,
            gallery_factory=GalleryPanel,
            preview_factory=PreviewPanel,
            right_factory=lambda g, p, parent: OcrRightPanel(parent),
            persist_key="ExtractTextTab/splitter",
            sizes=[260, 900, 460],
        )

        self.gallery = self.host.gallery
        self.preview = self.host.preview
        self.right = self.host.right
        self.splitter = self.host.splitter

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 15, 0, 10)
        lay.setSpacing(0)
        lay.addWidget(self.host)

        # Controllers
        self.ocr = ExtractOcrService(right=self.right)
        self.viewer = ExtractViewerController(tab=self, gallery=self.gallery, preview=self.preview, right=self.right)
        self.entries = ExtractEntriesController(tab=self, viewer=self.viewer, right=self.right, ocr=self.ocr)

        # Signals
        self.gallery.currentPathChanged.connect(self.entries.on_path_changed)

        self.right.cmb_zoom_ui.currentIndexChanged.connect(self.viewer.apply_zoom_ui_mode)
        self.right.chk_thumbs.toggled.connect(self.viewer.toggle_thumbs)
        self.right.extractRequested.connect(self.entries.extract_all)

        self.right.saveRequested.connect(self.entries.save_to_file)
        self.right.handwritingRequested.connect(self.entries.open_handwriting_dialog)

        self.right.itemEdited.connect(self.entries.on_item_edited)
        self.right.itemDeleted.connect(self.entries.on_item_deleted)

        # Overlay signals -> entries store
        self.viewer.overlay.rectAdded.connect(self.entries.on_rect_added)
        self.viewer.overlay.rectDeleted.connect(self.entries.on_rect_deleted)
        self.viewer.overlay.rectChanged.connect(self.entries.on_rect_changed)

        # Применяем сохранённые значения UI (комбо масштаба/миниатюры) после подключения сигналов.
        QTimer.singleShot(0, lambda: self.viewer.apply_zoom_ui_mode(self.right.cmb_zoom_ui.currentIndex()))
        QTimer.singleShot(0, lambda: self.viewer.toggle_thumbs(self.right.chk_thumbs.isChecked()))

    def reset_layout_to_defaults(self):
        self.splitter.setSizes([260, 900, 700])

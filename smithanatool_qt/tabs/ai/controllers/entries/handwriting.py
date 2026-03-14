from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QMessageBox

from smithanatool_qt.tabs.ai.adapters.runtime_config import build_ocr_runtime_config
from smithanatool_qt.tabs.ai.ui.widgets.handwriting_input import HandwritingInputDialog


class EntriesHandwritingMixin:
    # -------- handwriting --------
    def open_handwriting_dialog(self):
        dialog = HandwritingInputDialog(self.tab)
        dialog.setWindowModality(Qt.NonModal)
        dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        dialog.aiRequested.connect(self._run_handwriting_ocr)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _run_handwriting_ocr(self, img: QImage):
        if img is None or img.isNull():
            return
        cfg = build_ocr_runtime_config(self.right)
        try:
            png_bytes = self.viewer.qimage_to_png_bytes(img)
            out = self.ai.ocr_images([png_bytes], cfg)
            text = out[0] if out else ""
        except Exception as exc:
            QMessageBox.warning(self.tab, "Ошибка", f"Не удалось распознать рукописный ввод:\n{exc}")
            return
        self._add_handwriting_fragment(text)

    def _add_handwriting_fragment(self, raw_text: str):
        path = self._current_path()
        self._store.ensure_path(path)

        text = (raw_text or "").strip()
        if not text:
            return
        text = " ".join(text.split())

        self._store.add_entry(path, text=text, rect=None)
        self.right.set_items(self._store.texts(path))
        self._ensure_list_item_rect_data(path, force=True)
        self._sync_overlay_labels(path)
        self._remember_rect_state(path)
        self._update_preview_ocr_menu_state(path)

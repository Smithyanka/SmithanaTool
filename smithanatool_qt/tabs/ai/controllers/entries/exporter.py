from __future__ import annotations

import os
from typing import List

from PySide6.QtWidgets import QMessageBox

from smithanatool_qt.tabs.transform.utils.fs import open_in_explorer


class EntriesExporterMixin:
    # -------- save --------
    def _show_done_box(self, out_path: str, message: str) -> None:
        out_dir = os.path.dirname(out_path or "")
        box = QMessageBox(self.tab)
        box.setWindowTitle("Готово")
        box.setText(message)
        btn_open = box.addButton("Открыть папку", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.exec()
        if box.clickedButton() is btn_open and out_dir:
            open_in_explorer(out_dir)

    def _normalized_text_lines(self, path: str) -> List[str]:
        out: List[str] = []
        for line in self._store.texts(path):
            line = (line or "").strip()
            if line:
                out.append(line)
        return out

    def _paths_for_save_all(self) -> List[str]:
        paths: List[str] = []
        seen = set()

        gallery = getattr(self.tab, "gallery", None)
        gallery_files: List[str] = []
        if gallery is not None and hasattr(gallery, "files"):
            try:
                gallery_files = list(gallery.files())
            except Exception:
                gallery_files = []

        for path in gallery_files:
            path = path or ""
            if not path or path in seen:
                continue
            if self._normalized_text_lines(path):
                paths.append(path)
                seen.add(path)

        for path in self._store.paths():
            path = path or ""
            if not path or path in seen:
                continue
            if self._normalized_text_lines(path):
                paths.append(path)
                seen.add(path)

        return paths

    def save_to_file(self, path: str):
        current_path = self._current_path()
        lines = self._normalized_text_lines(current_path)
        if not lines:
            QMessageBox.information(self.tab, "Сохранение", "Нет текста для сохранения.")
            return
        try:
            with open(path, "w", encoding="utf-8") as file:
                file.write("\n".join(lines))
        except Exception as exc:
            QMessageBox.warning(self.tab, "Сохранение", f"Не удалось сохранить файл:\n{exc}")
            return

        self._show_done_box(path, f"Сохранено: {os.path.basename(path) or path}")

    def save_all_to_file(self, path: str):
        paths = self._paths_for_save_all()
        if not paths:
            QMessageBox.information(self.tab, "Сохранение", "Нет распознанного текста для сохранения.")
            return

        chunks: List[str] = []
        for src_path in paths:
            lines = self._normalized_text_lines(src_path)
            if not lines:
                continue
            name = os.path.basename(src_path) or src_path
            chunks.append(f"--- {name} ---")
            chunks.append("\n".join(lines))

        if not chunks:
            QMessageBox.information(self.tab, "Сохранение", "Нет распознанного текста для сохранения.")
            return

        try:
            with open(path, "w", encoding="utf-8") as file:
                file.write("\n".join(chunks))
        except Exception as exc:
            QMessageBox.warning(self.tab, "Сохранение", f"Не удалось сохранить файл:\n{exc}")
            return

        self._show_done_box(
            path,
            f"Сохранено: {os.path.basename(path) or path}",
        )

from __future__ import annotations

from typing import List

from PySide6.QtGui import QImageReader

try:
    from ...preview.utils import memory_image_for
except Exception:
    memory_image_for = None


class StitchSectionHelpersMixin:
    def _ask_selected_paths(self) -> List[str]:
        if self._gallery and hasattr(self._gallery, "selected_files"):
            selected = self._gallery.selected_files()
            if selected:
                return selected
        if self._gallery and hasattr(self._gallery, "files"):
            return self._gallery.files()
        return []

    def _build_output_params(self):
        direction = self.cmb_dir.currentText()
        dim_val = None if self.chk_no_resize.isChecked() else int(self.spin_dim.value())
        return (
            direction,
            dim_val,
            self.chk_opt.isChecked(),
            int(self.spin_compress.value()),
            self.chk_strip.isChecked(),
        )

    def _img_wh(self, path: str) -> tuple[int, int]:
        if isinstance(path, str) and path.startswith("mem://") and callable(memory_image_for):
            try:
                img = memory_image_for(path)
                if img is not None and not img.isNull():
                    return int(img.width()), int(img.height())
            except Exception:
                pass
        try:
            reader = QImageReader(path)
            size = reader.size()
            if size.isValid():
                return int(size.width()), int(size.height())
        except Exception:
            pass
        return (0, 0)

    def _scaled_h(self, wh: tuple[int, int], direction: str, target_dim: int | None) -> int:
        width, height = wh
        if width <= 0 or height <= 0:
            return 0
        if direction == "По вертикали":
            if target_dim is None:
                return height
            return max(1, int(round(height * (float(target_dim) / max(1.0, float(width))))))
        return int(target_dim) if target_dim else height

    def _split_chunks_by_max_height(
        self,
        paths: list[str],
        direction: str,
        target_dim: int | None,
        max_h: int,
    ) -> list[list[str]]:
        chunks: list[list[str]] = []
        current: list[str] = []
        current_metric = 0

        for path in paths:
            height = self._scaled_h(self._img_wh(path), direction, target_dim)
            new_metric = current_metric + height if direction == "По вертикали" else max(current_metric, height)

            if current and new_metric > max_h:
                chunks.append(current)
                current = [path]
                current_metric = height
            else:
                current.append(path)
                current_metric = new_metric

        if current:
            chunks.append(current)
        return chunks

from __future__ import annotations

import os
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageFile
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QPushButton,
    QFileDialog, QMessageBox, QProgressDialog, QApplication,
    QComboBox, QLineEdit, QGroupBox,
)

from smithanatool_qt.tabs.common.bind import apply_bindings, reset_bindings, ini_save_str
from smithanatool_qt.tabs.transform.utils.fs import open_in_explorer


Image.MAX_IMAGE_PIXELS = None
ImageFile.LOAD_TRUNCATED_IMAGES = True

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff", ".tga"}


def _natural_key(name: str):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


def _iter_image_paths(folder: str) -> list[str]:
    items: list[str] = []
    for entry in Path(folder).iterdir():
        if entry.is_file() and entry.suffix.lower() in _IMAGE_EXTS:
            items.append(str(entry))
    items.sort(key=lambda p: _natural_key(Path(p).name))
    return items


def _load_images_rgb(paths: list[str]) -> list[Image.Image]:
    images: list[Image.Image] = []
    for path in paths:
        with Image.open(path) as img:
            img.load()
            if img.width <= 0 or img.height <= 1:
                raise RuntimeError(f"Некорректный размер изображения: {Path(path).name}")
            images.append(img.convert("RGB"))
    return images


def _combine_images_vertically(images: list[Image.Image]) -> Image.Image:
    if not images:
        raise RuntimeError("Нет изображений для склейки")

    max_width = max(img.width for img in images)
    total_height = sum(img.height for img in images)

    combined = Image.new("RGB", (max_width, total_height), (0, 0, 0))

    y = 0
    for img in images:
        combined.paste(img, (0, y))
        y += img.height

    return combined


def _build_bounds_direct(height: int, slice_height: int) -> list[int]:
    bounds = [0]
    row = int(slice_height)

    while row < height:
        bounds.append(row)
        row += int(slice_height)

    if bounds[-1] != height:
        bounds.append(height)

    return bounds


def _build_bounds_smartstitch(
    combined_img: Image.Image,
    slice_height: int,
    sensitivity: int,
    scan_step: int,
    ignore_borders: int,
) -> list[int]:
    """
    Логика максимально близка к SmartStitch PixelComparisonDetector:
    - grayscale
    - проверка соседних пикселей внутри строки
    - поиск вверх, потом вниз
    """

    gray = np.array(combined_img.convert("L"))

    last_row = gray.shape[0]
    scan_step = max(1, int(scan_step))
    ignorable_pixels = max(0, int(ignore_borders))
    sensitivity = max(0, min(100, int(sensitivity)))
    threshold = int(255 * (1 - (sensitivity / 100)))

    slice_locations = [0]
    row = int(slice_height)
    move_up = True

    while row < last_row:
        row_pixels = gray[row]
        can_slice = True

        left = ignorable_pixels + 1
        right = len(row_pixels) - ignorable_pixels

        if right - left < 1:
            left = 1
            right = len(row_pixels)

        for index in range(left, right):
            prev_pixel = int(row_pixels[index - 1])
            next_pixel = int(row_pixels[index])
            value_diff = next_pixel - prev_pixel

            if value_diff > threshold or value_diff < -threshold:
                can_slice = False
                break

        if can_slice:
            slice_locations.append(row)
            row += int(slice_height)
            move_up = True
            continue

        if row - slice_locations[-1] <= 0.4 * int(slice_height):
            row = slice_locations[-1] + int(slice_height)
            move_up = False

        if move_up:
            row -= scan_step
            continue

        row += scan_step

    if slice_locations[-1] != last_row:
        slice_locations.append(last_row)

    return slice_locations


def _save_slices(
    combined_img: Image.Image,
    bounds: list[int],
    out_dir: str,
    base_name: str,
) -> int:
    total_parts = max(1, len(bounds) - 1)
    digits = max(2, len(str(total_parts)))
    saved = 0

    for idx, (top, bottom) in enumerate(zip(bounds, bounds[1:]), start=1):
        if bottom <= top:
            continue

        part = combined_img.crop((0, int(top), combined_img.width, int(bottom)))
        out_name = f"{base_name}_{idx:0{digits}d}.png"
        out_path = os.path.join(out_dir, out_name)
        part.save(out_path, format="PNG")
        saved += 1

    return saved


def _process_folder_as_smartstitch(
    files: list[str],
    out_dir: str,
    detector: str,
    slice_height: int,
    sensitivity: int,
    scan_step: int,
    ignore_borders: int,
    base_name: str,
) -> int:
    if slice_height <= 0:
        raise RuntimeError("Высота нарезки должна быть больше нуля")

    images = _load_images_rgb(files)
    combined = _combine_images_vertically(images)

    if detector == "direct":
        bounds = _build_bounds_direct(combined.height, slice_height)
    else:
        bounds = _build_bounds_smartstitch(
            combined_img=combined,
            slice_height=slice_height,
            sensitivity=sensitivity,
            scan_step=scan_step,
            ignore_borders=ignore_borders,
        )

    return _save_slices(
        combined_img=combined,
        bounds=bounds,
        out_dir=out_dir,
        base_name=base_name,
    )


class SmartStitchSection(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._input_dir_le = QLineEdit(self)
        self._input_dir_le.setVisible(False)
        self._out_dir_le = QLineEdit(self)
        self._out_dir_le.setVisible(False)
        self._detector_le = QLineEdit(self)
        self._detector_le.setVisible(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        root.setAlignment(Qt.AlignTop)

        self.grp_smart = QGroupBox("Настройки")
        root.addWidget(self.grp_smart)

        v_settings = QVBoxLayout(self.grp_smart)
        v_settings.setSpacing(8)
        v_settings.setAlignment(Qt.AlignTop)

        row_detector = QHBoxLayout()
        row_detector.addWidget(QLabel("Режим:"))
        self.combo_detector = QComboBox()
        self.combo_detector.addItems(["SmartStitch", "По высоте"])
        row_detector.addWidget(self.combo_detector)
        row_detector.addStretch(1)
        v_settings.addLayout(row_detector)

        row_height = QHBoxLayout()
        row_height.addWidget(QLabel("Высота (px):"))
        self.spin_height = QSpinBox()
        self.spin_height.setRange(100, 30000)
        self.spin_height.setSingleStep(50)
        self.spin_height.setValue(2000)
        row_height.addWidget(self.spin_height)
        row_height.addStretch(1)
        v_settings.addLayout(row_height)

        self.grp_params = QGroupBox("Параметры")
        root.addWidget(self.grp_params)

        v_params = QVBoxLayout(self.grp_params)
        v_params.setSpacing(8)
        v_params.setAlignment(Qt.AlignTop)

        row_sens = QHBoxLayout()
        self.lbl_sens = QLabel("Чувствительность (%):")
        self.spin_sensitivity = QSpinBox()
        self.spin_sensitivity.setRange(0, 100)
        self.spin_sensitivity.setValue(90)
        row_sens.addWidget(self.lbl_sens)
        row_sens.addWidget(self.spin_sensitivity)
        row_sens.addStretch(1)
        v_params.addLayout(row_sens)

        row_step = QHBoxLayout()
        self.lbl_step = QLabel("Шаг сканирования:")
        self.spin_scan_step = QSpinBox()
        self.spin_scan_step.setRange(1, 200)
        self.spin_scan_step.setValue(5)
        row_step.addWidget(self.lbl_step)
        row_step.addWidget(self.spin_scan_step)
        row_step.addStretch(1)
        v_params.addLayout(row_step)

        row_ignore = QHBoxLayout()
        self.lbl_ignore = QLabel("Игнорировать края (px):")
        self.spin_ignore = QSpinBox()
        self.spin_ignore.setRange(0, 5000)
        self.spin_ignore.setValue(5)
        row_ignore.addWidget(self.lbl_ignore)
        row_ignore.addWidget(self.spin_ignore)
        row_ignore.addStretch(1)
        v_params.addLayout(row_ignore)

        row_buttons = QHBoxLayout()
        row_buttons.setContentsMargins(0, 0, 0, 0)
        row_buttons.addStretch(1)
        self.btn_pick_src = QPushButton("Выбрать папку…")
        row_buttons.addWidget(self.btn_pick_src)
        root.addLayout(row_buttons)

        self.combo_detector.currentIndexChanged.connect(self._on_detector_changed)
        self.btn_pick_src.clicked.connect(self._pick_input_dir)

        QTimer.singleShot(0, self._apply_settings_from_ini)

    def _refresh_parent_geometry(self):
        self.layout().activate()
        self.updateGeometry()

        parent = self.parentWidget()
        while parent is not None:
            parent.updateGeometry()
            refresh = getattr(parent, "_refresh_geometry", None) or getattr(parent, "refresh_stack_geometry", None)
            if callable(refresh):
                QTimer.singleShot(0, refresh)
                break
            parent = parent.parentWidget()

    def _current_detector_key(self) -> str:
        return "direct" if self.combo_detector.currentIndex() == 1 else "smart"

    def _on_detector_changed(self, idx: int):
        detector = self._current_detector_key()
        is_smart = (detector == "smart")
        self.grp_params.setVisible(is_smart)
        self._detector_le.setText(detector)
        ini_save_str("SmartStitchSection", "detector", detector)
        self._refresh_parent_geometry()

    def _pick_input_dir(self):
        start_dir = self._input_dir_le.text().strip() or os.path.expanduser("~")
        src = QFileDialog.getExistingDirectory(self, "Выберите папку с изображениями", start_dir)
        if not src:
            return

        self._input_dir_le.setText(src)
        ini_save_str("SmartStitchSection", "input_dir", src)

        start_out = self._out_dir_le.text().strip() or src
        out_dir = QFileDialog.getExistingDirectory(self, "Папка для сохранения PNG", start_out)
        if not out_dir:
            return

        self._out_dir_le.setText(out_dir)
        ini_save_str("SmartStitchSection", "out_dir", out_dir)
        self._run_batch()

    def reset_to_defaults(self):
        reset_bindings(self, "SmartStitchSection")
        detector = self._detector_le.text().strip() or "smart"
        try:
            self.combo_detector.blockSignals(True)
            self.combo_detector.setCurrentIndex(1 if detector == "direct" else 0)
        finally:
            self.combo_detector.blockSignals(False)
        self._on_detector_changed(self.combo_detector.currentIndex())

    def _apply_settings_from_ini(self):
        apply_bindings(self, "SmartStitchSection", [
            (self.spin_height, "height_px", 2000),
            (self.spin_sensitivity, "sensitivity", 90),
            (self.spin_scan_step, "scan_step", 5),
            (self.spin_ignore, "ignore_borders", 5),
            (self._input_dir_le, "input_dir", ""),
            (self._out_dir_le, "out_dir", ""),
            (self._detector_le, "detector", "smart"),
        ])
        detector = self._detector_le.text().strip() or "smart"
        self.combo_detector.setCurrentIndex(1 if detector == "direct" else 0)
        self._on_detector_changed(self.combo_detector.currentIndex())

    def _run_batch(self):
        src_dir = self._input_dir_le.text().strip()
        out_dir = self._out_dir_le.text().strip()

        if not src_dir:
            QMessageBox.information(self, "Пакетная нарезка", "Сначала выберите папку с изображениями.")
            return
        if not out_dir:
            QMessageBox.information(self, "Пакетная нарезка", "Сначала выберите папку для сохранения.")
            return

        try:
            files = _iter_image_paths(src_dir)
        except Exception as e:
            QMessageBox.critical(self, "Пакетная нарезка", f"Не удалось прочитать папку:\n{e}")
            return

        if not files:
            QMessageBox.information(self, "Пакетная нарезка", "В выбранной папке нет поддерживаемых изображений.")
            return

        detector = self._current_detector_key()
        slice_height = int(self.spin_height.value())
        sensitivity = int(self.spin_sensitivity.value())
        scan_step = int(self.spin_scan_step.value())
        ignore_borders = int(self.spin_ignore.value())

        base_name = Path(src_dir).name.strip() or "slice"

        prog = QProgressDialog("Склеиваю и нарезаю главу…", None, 0, 0, self)
        prog.setWindowTitle("SmartStitch")
        prog.setWindowModality(Qt.ApplicationModal)
        prog.setCancelButton(None)
        prog.setMinimumDuration(0)
        prog.show()
        QApplication.processEvents()

        try:
            total_saved = _process_folder_as_smartstitch(
                files=files,
                out_dir=out_dir,
                detector=detector,
                slice_height=slice_height,
                sensitivity=sensitivity,
                scan_step=scan_step,
                ignore_borders=ignore_borders,
                base_name=base_name,
            )
        except Exception as e:
            prog.close()
            QMessageBox.warning(
                self,
                "Пакетная нарезка",
                f"Не удалось обработать папку:\n{e}",
            )
            return

        prog.close()

        box = QMessageBox(self)
        box.setWindowTitle("Готово")
        box.setText(f"Сохранено фрагментов: {total_saved}")
        btn_open = box.addButton("Открыть папку", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.exec()

        if box.clickedButton() is btn_open:
            open_in_explorer(out_dir)
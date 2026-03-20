from __future__ import annotations

import os
from typing import Iterable, Sequence

import numpy as np
from PIL import Image, ImageFile

Image.MAX_IMAGE_PIXELS = None
ImageFile.LOAD_TRUNCATED_IMAGES = True


def _normalize_rgb_image(
    img: Image.Image,
    *,
    target_width: int = 0,
    strip_metadata: bool = True,
) -> Image.Image:
    if img.width <= 0 or img.height <= 1:
        raise RuntimeError('Некорректный размер изображения.')

    if target_width and target_width > 0 and img.width != target_width:
        new_height = max(1, round(img.height * (target_width / img.width)))
        img = img.resize((int(target_width), int(new_height)), Image.LANCZOS)

    if img.mode != 'RGB':
        img = img.convert('RGB')

    if strip_metadata:
        img = Image.frombytes(img.mode, img.size, img.tobytes())
    else:
        img = img.copy()

    return img


def load_images_rgb(
    paths: Sequence[str],
    *,
    target_width: int = 0,
    strip_metadata: bool = True,
) -> list[Image.Image]:
    images: list[Image.Image] = []
    for path in paths:
        with Image.open(path) as img:
            img.load()
            images.append(
                _normalize_rgb_image(
                    img,
                    target_width=target_width,
                    strip_metadata=strip_metadata,
                )
            )
    return images


def combine_images_vertically(images: Sequence[Image.Image]) -> Image.Image:
    if not images:
        raise RuntimeError('Нет изображений для склейки.')

    max_width = max(img.width for img in images)
    total_height = sum(img.height for img in images)
    if max_width <= 0 or total_height <= 0:
        raise RuntimeError('Не удалось собрать итоговый холст.')

    combined = Image.new('RGB', (max_width, total_height), (255, 255, 255))
    y = 0
    for img in images:
        combined.paste(img, (0, y))
        y += img.height
    return combined


def build_bounds_direct(height: int, slice_height: int) -> list[int]:
    slice_height = max(1, int(slice_height))
    bounds = [0]
    row = slice_height

    while row < height:
        bounds.append(row)
        row += slice_height

    if bounds[-1] != height:
        bounds.append(height)
    return bounds


def build_bounds_smartstitch(
    combined_img: Image.Image,
    *,
    slice_height: int,
    sensitivity: int,
    scan_step: int,
    ignore_borders: int,
) -> list[int]:
    gray = np.array(combined_img.convert('L'))
    last_row = int(gray.shape[0])

    slice_height = max(1, int(slice_height))
    scan_step = max(1, int(scan_step))
    ignorable_pixels = max(0, int(ignore_borders))
    sensitivity = max(0, min(100, int(sensitivity)))
    threshold = int(255 * (1 - (sensitivity / 100.0)))

    slice_locations = [0]
    row = slice_height
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
            row += slice_height
            move_up = True
            continue

        if row - slice_locations[-1] <= 0.4 * slice_height:
            row = slice_locations[-1] + slice_height
            move_up = False

        if move_up:
            row -= scan_step
        else:
            row += scan_step

    if slice_locations[-1] != last_row:
        slice_locations.append(last_row)

    return slice_locations


def save_slices(
    combined_img: Image.Image,
    bounds: Iterable[int],
    out_dir: str,
    *,
    base_name: str = '',
    digits: int = 2,
    optimize_png: bool = True,
    compress_level: int = 6,
) -> int:
    points = list(bounds)
    if len(points) < 2:
        return 0

    digits = max(1, min(6, int(digits)))
    compress_level = max(0, min(9, int(compress_level)))
    os.makedirs(out_dir, exist_ok=True)

    saved = 0
    prefix = f'{base_name}_' if base_name else ''
    for idx, (top, bottom) in enumerate(zip(points, points[1:]), start=1):
        if bottom <= top:
            continue
        part = combined_img.crop((0, int(top), combined_img.width, int(bottom)))
        out_name = f'{prefix}{idx:0{digits}d}.png'
        out_path = os.path.join(out_dir, out_name)
        part.save(
            out_path,
            format='PNG',
            optimize=bool(optimize_png),
            compress_level=compress_level,
        )
        saved += 1
    return saved


def process_as_smartstitch(
    files: Sequence[str],
    out_dir: str,
    *,
    detector: str = 'smart',
    slice_height: int = 8000,
    sensitivity: int = 90,
    scan_step: int = 5,
    ignore_borders: int = 5,
    base_name: str = '',
    digits: int = 2,
    target_width: int = 0,
    strip_metadata: bool = True,
    optimize_png: bool = True,
    compress_level: int = 6,
) -> int:
    if slice_height <= 0:
        raise RuntimeError('Высота нарезки должна быть больше нуля.')

    images = load_images_rgb(
        files,
        target_width=target_width,
        strip_metadata=strip_metadata,
    )
    combined = combine_images_vertically(images)

    detector_key = str(detector or 'smart').lower()
    if detector_key == 'direct':
        bounds = build_bounds_direct(combined.height, slice_height)
    else:
        bounds = build_bounds_smartstitch(
            combined,
            slice_height=slice_height,
            sensitivity=sensitivity,
            scan_step=scan_step,
            ignore_borders=ignore_borders,
        )

    return save_slices(
        combined,
        bounds,
        out_dir,
        base_name=base_name,
        digits=digits,
        optimize_png=optimize_png,
        compress_level=compress_level,
    )

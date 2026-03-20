from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence

from PIL import Image

from smithanatool_qt.tabs.transform.core.stitcher import (
    load_images,
    merge_horizontal,
    merge_vertical,
    save_png,
)

from .smartstitch_engine import process_as_smartstitch


_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff", ".tga"}


def natural_key(name: str):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


def normalize_files(files: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for path in files or []:
        if not isinstance(path, str) or not path:
            continue
        try:
            norm = os.path.abspath(path)
        except Exception:
            continue
        if norm in seen or not os.path.isfile(norm):
            continue
        if Path(norm).suffix.lower() not in _IMAGE_EXTS:
            continue
        seen.add(norm)
        result.append(norm)

    return result


def suggest_base_name(files: Sequence[str]) -> str:
    if not files:
        return "slice"

    try:
        parents = [str(Path(p).resolve().parent) for p in files]
        common_parent = os.path.commonpath(parents)
        base = Path(common_parent).name.strip()
        if base:
            return base
    except Exception:
        pass

    try:
        base = Path(files[0]).parent.name.strip()
        if base:
            return base
    except Exception:
        pass

    try:
        base = Path(files[0]).stem.strip()
        if base:
            return base
    except Exception:
        pass

    return "slice"


def resolve_threads(auto_threads: bool, threads: int) -> int:
    if auto_threads:
        cpu_count = os.cpu_count() or 2
        if cpu_count <= 2:
            auto = 1
        elif cpu_count <= 4:
            auto = 2
        elif cpu_count <= 8:
            auto = 4
        else:
            auto = min(8, cpu_count - 2)
        return max(1, min(8, auto))

    try:
        value = int(threads)
    except Exception:
        value = 1
    return max(1, min(32, value))


def stitch_single_to_file(
    paths: Sequence[str],
    out_path: str,
    *,
    direction: str,
    dim_val: int | None,
    optimize: bool,
    compress: int,
    strip: bool,
) -> str:
    images = load_images(list(paths))
    if not images:
        raise RuntimeError("Нет валидных изображений")

    if direction == "По вертикали":
        merged = merge_vertical(images, target_width=dim_val)
    else:
        merged = merge_horizontal(images, target_height=dim_val)

    try:
        save_png(
            merged,
            out_path,
            optimize=optimize,
            compress_level=compress,
            strip_metadata=strip,
        )
    except MemoryError:
        try:
            save_png(
                merged,
                out_path,
                optimize=False,
                compress_level=min(3, int(compress)),
                strip_metadata=strip,
            )
        except MemoryError as exc:
            raise RuntimeError("Недостаточно памяти для параллельной склейки") from exc

    return out_path


def stitch_chunks_to_dir(
    chunks: Sequence[Sequence[str]],
    out_dir: str,
    *,
    zeros: int,
    direction: str,
    dim_val: int | None,
    optimize: bool,
    compress: int,
    strip: bool,
    workers: int,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> tuple[int, list[tuple[int, str, str]]]:
    total = len(chunks)
    if total == 0:
        return 0, []

    os.makedirs(out_dir, exist_ok=True)

    def _job(index: int, chunk: Sequence[str], out_path: str):
        stitch_single_to_file(
            chunk,
            out_path,
            direction=direction,
            dim_val=dim_val,
            optimize=optimize,
            compress=compress,
            strip=strip,
        )
        return index, out_path

    made = 0
    done = 0
    errors: list[tuple[int, str, str]] = []

    futures = []
    with ThreadPoolExecutor(max_workers=max(1, min(int(workers), total))) as executor:
        for idx, chunk in enumerate(chunks, start=1):
            filename = f"{idx:0{zeros}d}.png"
            out_path = os.path.join(out_dir, filename)
            future = executor.submit(_job, idx, list(chunk), out_path)
            future._stitch_idx = idx
            future._stitch_name = filename
            futures.append(future)

        for future in futures:
            try:
                future.result()
                made += 1
            except Exception as exc:
                idx = getattr(future, "_stitch_idx", 0)
                name = getattr(future, "_stitch_name", "<unknown>")
                errors.append((idx, name, str(exc)))
            finally:
                done += 1
                if progress_callback:
                    progress_callback(done, total)

    return made, errors


def run_smartstitch(
    files: Sequence[str],
    out_dir: str,
    *,
    detector: str,
    slice_height: int,
    digits: int,
    sensitivity: int,
    scan_step: int,
    ignore_borders: int,
    base_name: str,
    target_width: int,
    strip_metadata: bool,
    optimize_png: bool,
    compress_level: int,
) -> int:
    return int(
        process_as_smartstitch(
            files=list(files),
            out_dir=out_dir,
            detector=detector,
            slice_height=slice_height,
            sensitivity=sensitivity,
            scan_step=scan_step,
            ignore_borders=ignore_borders,
            base_name=base_name,
            digits=digits,
            target_width=target_width,
            strip_metadata=strip_metadata,
            optimize_png=optimize_png,
            compress_level=compress_level,
        )
        or 0
    )


def list_chapter_images(chapter_dir: str) -> list[str]:
    files = []
    rx = re.compile(r"^(?:page_)?(\d{3,4})\.[A-Za-z0-9]+$")
    for name in os.listdir(chapter_dir):
        match = rx.match(name)
        if match:
            files.append((int(match.group(1)), name))
    files.sort(key=lambda item: item[0])
    return [os.path.join(chapter_dir, name) for _, name in files]


def stitch_group(
    img_paths: Sequence[str],
    out_path: str,
    *,
    target_width: int,
    optimize_png: bool,
    compress_level: int,
    strip_metadata: bool,
) -> bool:
    images: list[Image.Image] = []
    for path in img_paths:
        img = Image.open(path)
        img.load()
        if target_width and target_width > 0 and img.width != target_width:
            new_height = round(img.height * (target_width / img.width))
            img = img.resize((int(target_width), int(new_height)), Image.LANCZOS)
        if strip_metadata:
            if img.mode not in ("RGB", "RGBA", "L"):
                img = img.convert("RGB")
            img = Image.frombytes(img.mode, img.size, img.tobytes())
        images.append(img)

    total_w = max((img.width for img in images), default=0)
    total_h = sum((img.height for img in images), 0)
    if total_w <= 0 or total_h <= 0:
        return False

    canvas = Image.new("RGB", (total_w, total_h), (255, 255, 255))
    y = 0
    for img in images:
        if img.mode != "RGB":
            img = img.convert("RGB")
        canvas.paste(img, (0, y))
        y += img.height

    canvas.save(
        out_path,
        format="PNG",
        optimize=bool(optimize_png),
        compress_level=max(0, min(9, int(compress_level))),
    )
    return True


def plan_groups_by_count(files: Sequence[str], per: int) -> list[list[str]]:
    per = max(1, int(per))
    return [list(files[i : i + per]) for i in range(0, len(files), per)]


def plan_groups_by_height(files: Sequence[str], max_h: int, target_w: int) -> list[list[str]]:
    max_h = max(100, int(max_h))
    groups: list[list[str]] = []
    current: list[str] = []
    current_h = 0

    for path in files:
        try:
            with Image.open(path) as img:
                width, height = img.size
        except Exception:
            width, height = 0, 0

        if target_w and width and width != target_w:
            height = round(height * (float(target_w) / float(width)))

        if current and (current_h + height) > max_h:
            groups.append(current)
            current, current_h = [path], height
        else:
            current.append(path)
            current_h += height

    if current:
        groups.append(current)
    return groups


def auto_stitch_chapter_simple(
    chapter_dir: str,
    *,
    auto_cfg: dict,
    files: Sequence[str],
    out_dir: str,
    target_width: int,
    strip_metadata: bool,
    optimize_png: bool,
    compress_level: int,
    log=None,
    stop_flag: Optional[Callable[[], bool]] = None,
):
    per = max(1, int(auto_cfg.get("per") or 1))
    auto_threads = bool(auto_cfg.get("auto_threads"))
    threads = int(auto_cfg.get("threads") or 4)
    digits = max(1, min(6, int(auto_cfg.get("zeros") or auto_cfg.get("digits") or 2)))

    stitch_mode = str(auto_cfg.get("stitch_mode") or auto_cfg.get("group_by") or "count").lower()



    group_max_height = int(auto_cfg.get("group_max_height") or 10000)

    groups = (
        plan_groups_by_height(files, group_max_height, target_width)
        if stitch_mode == "height"
        else plan_groups_by_count(files, per)
    )

    def out_name(index: int) -> str:
        return f"{index:0{digits}d}.png"

    def _stitch_one(index: int, group: Sequence[str]):
        if stop_flag and stop_flag():
            return index, False, ""
        out_path = os.path.join(out_dir, out_name(index))
        ok = stitch_group(
            group,
            out_path,
            target_width=target_width,
            optimize_png=optimize_png,
            compress_level=compress_level,
            strip_metadata=strip_metadata,
        )
        return index, ok, out_path

    max_workers = resolve_threads(auto_threads, threads)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_stitch_one, index + 1, group): index
            for index, group in enumerate(groups)
        }
        for future in as_completed(futures):
            if stop_flag and stop_flag():
                break
            index, ok, path = future.result()
            if ok:
                if log:
                    log(f"[OK] Склейка {index:0{digits}d} → {path}")
            elif log:
                log(f"[WARN] Склейка {index:0{digits}d} не удалась.")


def auto_stitch_chapter_smart(
    chapter_dir: str,
    *,
    auto_cfg: dict,
    files: Sequence[str],
    out_dir: str,
    target_width: int,
    strip_metadata: bool,
    optimize_png: bool,
    compress_level: int,
    log=None,
    stop_flag: Optional[Callable[[], bool]] = None,
):
    if stop_flag and stop_flag():
        return

    digits = max(1, min(6, int(auto_cfg.get("zeros") or auto_cfg.get("digits") or 2)))
    detector = str(auto_cfg.get("smart_detector") or "smart").lower()
    saved = process_as_smartstitch(
        list(files),
        out_dir,
        detector=detector,
        slice_height=int(auto_cfg.get("smart_height") or 2000),
        sensitivity=int(auto_cfg.get("smart_sensitivity") or 90),
        scan_step=int(auto_cfg.get("smart_scan_step") or 5),
        ignore_borders=int(auto_cfg.get("smart_ignore_borders") or 5),
        digits=digits,
        target_width=target_width,
        strip_metadata=strip_metadata,
        optimize_png=optimize_png,
        compress_level=compress_level,
    )
    if log:
        log(f"[OK] SmartStitch: сохранено фрагментов {saved} в {out_dir}")


def auto_stitch_chapter(
    chapter_dir: str,
    *,
    auto_cfg: dict,
    log=None,
    stop_flag: Optional[Callable[[], bool]] = None,
):
    if not (auto_cfg and auto_cfg.get("enable")):
        return

    same_dir = bool(auto_cfg.get("same_dir"))
    target_width = int(auto_cfg.get("target_width") or 0)
    strip_metadata = bool(auto_cfg.get("strip_metadata"))
    optimize_png = bool(auto_cfg.get("optimize_png"))
    compress_level = int(auto_cfg.get("compress_level") or 6)
    delete_sources = bool(auto_cfg.get("delete_sources"))
    out_dir_pref = str(auto_cfg.get("out_dir") or "")
    stitch_mode = str(auto_cfg.get("stitch_mode") or auto_cfg.get("group_by") or "count").lower()

    if log:
        if stitch_mode == "smart":
            log(
                "[INFO] Автосклейка: выбран режим SmartStitch: "
                f"Высота={int(auto_cfg.get('smart_height') or 2000)}, "
                f"Чувствительность={int(auto_cfg.get('smart_sensitivity') or 90)}, "
                f"Шаг сканирования={int(auto_cfg.get('smart_scan_step') or 5)}, "
                f"Игнорировать края={int(auto_cfg.get('smart_ignore_borders') or 5)}"
            )
        elif stitch_mode == "height":
            log(
                "[INFO] Автосклейка: выбран режим 'По высоте': "
                f"{int(auto_cfg.get('group_max_height') or 10000)}"
            )
        else:
            log(
                "[INFO] Автосклейка: выбран режим 'По количеству фрагментов': "
                f"{max(1, int(auto_cfg.get('per') or 1))}"
            )


    out_dir = chapter_dir if (same_dir or not out_dir_pref) else out_dir_pref
    os.makedirs(out_dir, exist_ok=True)

    files = list_chapter_images(chapter_dir)
    if not files:
        if log:
            log("[WARN] Автосклейка: нет файлов для склейки.")
        return

    if stitch_mode == "smart":
        auto_stitch_chapter_smart(
            chapter_dir,
            auto_cfg=auto_cfg,
            files=files,
            out_dir=out_dir,
            target_width=target_width,
            strip_metadata=strip_metadata,
            optimize_png=optimize_png,
            compress_level=compress_level,
            log=log,
            stop_flag=stop_flag,
        )
    else:
        auto_stitch_chapter_simple(
            chapter_dir,
            auto_cfg=auto_cfg,
            files=files,
            out_dir=out_dir,
            target_width=target_width,
            strip_metadata=strip_metadata,
            optimize_png=optimize_png,
            compress_level=compress_level,
            log=log,
            stop_flag=stop_flag,
        )

    if delete_sources and not (stop_flag and stop_flag()):
        try:
            for path in files:
                try:
                    os.remove(path)
                except Exception:
                    pass
            if log:
                log("[OK] Исходники удалены после склейки.")
        except Exception:
            if log:
                log("[WARN] Не удалось удалить исходники.")

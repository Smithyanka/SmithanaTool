from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog, QWidget

from smithanatool_qt.tabs.transform.converters.png_gif import convert_png_to_gif
from smithanatool_qt.tabs.transform.converters.png_pdf import (
    filter_images as filter_png_for_pdf,
    convert_png_to_pdf,
    merge_pngs_to_pdf,
    merge_images_to_pdf,
)
from smithanatool_qt.tabs.transform.converters.psd_png import convert_psd_to_png
from smithanatool_qt.tabs.transform.converters.any_png import convert_any_to_png

from smithanatool_qt.tabs.transform.utils.fs import open_in_explorer


def _ensure_unique_path(path: str) -> str:
    """Если файл уже существует, добавляет суффикс (2), (3), ..."""
    root, ext = os.path.splitext(path)
    cand = path
    k = 2
    while os.path.exists(cand):
        cand = f"{root} ({k}){ext}"
        k += 1
    return cand


def _natural_key(path: str):
    """Ключ для «естественной» сортировки: file2 < file10."""
    name = os.path.basename(path)
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def _show_done_box(parent: QWidget, out_dir: str, message: str) -> None:
    box = QMessageBox(parent)
    box.setWindowTitle("Готово")
    box.setText(message)
    btn_open = box.addButton("Открыть папку", QMessageBox.ActionRole)
    box.addButton(QMessageBox.Ok)
    box.exec()
    if box.clickedButton() is btn_open:
        open_in_explorer(out_dir)


def png_convert(parent: QWidget, files: list[str], out_dir: str, *, replace: bool, threads: int, compress: int) -> None:
    total = len(files)
    os.makedirs(out_dir or ".", exist_ok=True)

    threads = max(1, min(32, int(threads)))

    tasks: list[tuple[str, str]] = []
    skipped = 0
    for src in files:
        base = os.path.splitext(os.path.basename(src))[0] + ".png"
        dst = os.path.join(out_dir, base)
        if (not replace) and os.path.exists(dst):
            skipped += 1
            continue
        tasks.append((src, dst))

    if not tasks:
        QMessageBox.information(
            parent,
            "PNG конвертор",
            "Нечего конвертировать (возможно, все выходные файлы уже существуют).", 
        )
        return

    dlg = QProgressDialog("Конвертация в PNG…", None, 0, len(tasks), parent)
    dlg.setWindowTitle("Конвертация")
    dlg.setWindowModality(Qt.ApplicationModal)
    dlg.setCancelButton(None)
    dlg.setMinimumDuration(0)
    dlg.show()
    QApplication.processEvents()

    ok = 0
    errors: list[str] = []

    def _task(src: str, dst: str):
        return convert_any_to_png(src, dst, png_compress_level=compress, optimize=False, strip_metadata=True)

    with ThreadPoolExecutor(max_workers=threads) as ex:
        futs = [ex.submit(_task, src, dst) for (src, dst) in tasks]
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                success, msg = fut.result()
                if success:
                    ok += 1
                else:
                    errors.append(f"{os.path.basename(msg) if os.path.isabs(msg) else msg}")
            except Exception as e:
                errors.append(str(e))
            dlg.setValue(i)
            QApplication.processEvents()

    dlg.close()
    _show_done_box(parent, out_dir, f"→ PNG: успешно {ok}/{len(tasks)}, пропущено {skipped}")
    if errors:
        uniq = list(dict.fromkeys(errors))[:5]
        QMessageBox.warning(parent, "PNG конвертор", "Некоторые файлы не сконвертированы:\n" + "\n".join(uniq))


def gif_convert(parent: QWidget, files: list[str], out_dir: str, *, dither: bool, workers: int) -> None:
    os.makedirs(out_dir, exist_ok=True)
    total = len(files)
    workers = max(1, min(int(workers), total))

    dlg = QProgressDialog("PNG→GIF: выполняется конвертация…", None, 0, total, parent)
    dlg.setWindowTitle("Конвертация")
    dlg.setWindowModality(Qt.ApplicationModal)
    dlg.setCancelButton(None)
    dlg.setMinimumDuration(0)
    dlg.show()
    QApplication.processEvents()

    ok = 0
    errors: list[str] = []

    tasks: list[tuple[str, str]] = []
    for src in files:
        base = os.path.splitext(os.path.basename(src))[0] + ".gif"
        dst = os.path.join(out_dir, base)
        tasks.append((src, dst))

    def _task(src: str, dst: str):
        return convert_png_to_gif(src, dst, dither=dither)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_task, s, d) for (s, d) in tasks]
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                success, msg = fut.result()
                if success:
                    ok += 1
                else:
                    errors.append(f"{os.path.basename(msg) if os.path.isabs(msg) else msg}")
            except Exception as e:
                errors.append(str(e))
            dlg.setValue(i)
            QApplication.processEvents()

    dlg.close()
    _show_done_box(parent, out_dir, f"PNG→GIF: успешно {ok}/{total}")
    if errors:
        uniq = list(dict.fromkeys(errors))[:5]
        QMessageBox.warning(parent, "PNG→GIF", "Некоторые файлы не сконвертированы:\n" + "\n".join(uniq))


def pdf_convert_many(parent: QWidget, files: list[str], out_dir: str, *, jpeg_quality: int, dpi: int) -> None:
    dlg = QProgressDialog("PNG→PDF: выполняется конвертация…", None, 0, len(files), parent)
    dlg.setWindowTitle("Конвертация")
    dlg.setWindowModality(Qt.ApplicationModal)
    dlg.setCancelButton(None)
    dlg.setMinimumDuration(0)
    dlg.show()
    QApplication.processEvents()

    ok = 0
    for i, src in enumerate(files, 1):
        dst = os.path.join(out_dir, os.path.splitext(os.path.basename(src))[0] + ".pdf")
        success, msg = convert_png_to_pdf(src, dst, jpeg_quality=int(jpeg_quality), dpi=int(dpi))
        if success:
            ok += 1
        else:
            QMessageBox.warning(parent, "PNG→PDF", f"{os.path.basename(src)}: {msg}")
        dlg.setValue(i)
        QApplication.processEvents()

    dlg.close()
    _show_done_box(parent, out_dir, f"PNG→PDF: успешно {ok}/{len(files)}")


def pdf_convert_onefile(parent: QWidget, files: list[str], out_path: str, *, jpeg_quality: int, dpi: int) -> None:
    dlg = QProgressDialog("PNG→PDF (один файл): выполняется конвертация…", None, 0, 0, parent)
    dlg.setWindowTitle("Конвертация")
    dlg.setWindowModality(Qt.ApplicationModal)
    dlg.setCancelButton(None)
    dlg.setMinimumDuration(0)
    dlg.show()
    QApplication.processEvents()

    success, msg = merge_pngs_to_pdf(files, out_path, jpeg_quality=int(jpeg_quality), dpi=int(dpi))
    dlg.close()
    if success:
        _show_done_box(parent, os.path.dirname(out_path), f"PNG→PDF: сохранено {os.path.basename(out_path)}")
    else:
        QMessageBox.critical(parent, "PNG→PDF", f"Ошибка: {msg}")


def pdf_convert_dirs(parent: QWidget, dirs: list[str], out_dir: str, *, jpeg_quality: int, dpi: int) -> None:
    """PNG→PDF по папкам (несколько папок → несколько PDF)."""
    # --- ПРОГРЕСС-ДИАЛОГ ---
    dlg = QProgressDialog(parent)
    dlg.setWindowTitle("Конвертация")
    dlg.setLabelText("PNG→PDF (папки): выполняется конвертация…")
    dlg.setCancelButton(None)
    dlg.setWindowModality(Qt.ApplicationModal)
    dlg.setAutoClose(False)
    dlg.setAutoReset(False)
    dlg.setMinimumDuration(0)

    # Показать сразу с занятым состоянием (фикс «белого окна»)
    dlg.setRange(0, 0)
    dlg.setValue(0)
    dlg.resize(dlg.sizeHint())
    dlg.show()
    QApplication.processEvents()
    dlg.repaint()
    QApplication.processEvents()

    dlg.setRange(0, len(dirs))
    dlg.setValue(0)
    QApplication.processEvents()
    # ----------------------------------------------------------------------

    ok = 0
    skipped = 0
    errors: list[str] = []

    def _task_dir(d: str):
        try:
            candidates = [
                os.path.join(d, name)
                for name in os.listdir(d)
                if os.path.isfile(os.path.join(d, name))
            ]
            imgs = filter_png_for_pdf(candidates)
            imgs.sort(key=_natural_key)

            if not imgs:
                return ("skipped", d, None)

            base_name = os.path.basename(os.path.normpath(d)) or "output"
            dst_pdf = _ensure_unique_path(os.path.join(out_dir, f"{base_name}.pdf"))

            success, msg = merge_images_to_pdf(imgs, dst_pdf, jpeg_quality=int(jpeg_quality), dpi=int(dpi))
            return ("ok", d, None) if success else ("error", d, f"{base_name}: {msg}")
        except Exception as e:
            return ("error", d, f"{os.path.basename(d) or d}: {e}")

    workers = min(max(1, (os.cpu_count() or 2) // 2), 8)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_task_dir, d) for d in dirs]
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                status, d, msg = fut.result()
                if status == "ok":
                    ok += 1
                elif status == "skipped":
                    skipped += 1
                elif status == "error" and msg:
                    errors.append(msg)
            except Exception as e:
                errors.append(str(e))
            finally:
                dlg.setValue(i)
                QApplication.processEvents()

    dlg.close()
    _show_done_box(parent, out_dir, f"PNG→PDF (папки): успешно {ok}/{len(dirs)}, пустых {skipped}")
    if errors:
        uniq = list(dict.fromkeys(errors))[:5]
        QMessageBox.warning(parent, "PNG→PDF (папки)", "Некоторые папки не обработаны:\n" + "\n".join(uniq))


def psd_convert(
    parent: QWidget,
    files: list[str],
    out_dir: str | None,
    *,
    replace: bool,
    threads: int | None,
    compress: int,
) -> None:
    total = len(files)
    skipped = 0

    # Автопотоки — как в других местах: не перегружаем диск/CPU
    if threads is None:
        cpu = os.cpu_count() or 4
        threads = max(2, min(8, cpu))

    os.makedirs(out_dir or ".", exist_ok=True)

    def _dst_path(dst: str) -> str | None:
        if replace or not os.path.exists(dst):
            return dst
        return None

    tasks: list[tuple[str, str]] = []
    for src in files:
        base = os.path.splitext(os.path.basename(src))[0] + ".png"
        dst = os.path.join(out_dir or os.path.dirname(src), base)

        dst = _dst_path(dst)
        if dst is None:
            skipped += 1
            continue
        tasks.append((src, dst))

    dlg = QProgressDialog("PSD→PNG: выполняется конвертация…", None, 0, len(tasks), parent)
    dlg.setWindowTitle("Конвертация")
    dlg.setWindowModality(Qt.ApplicationModal)
    dlg.setCancelButton(None)
    dlg.setMinimumDuration(0)
    dlg.show()
    QApplication.processEvents()

    ok = 0
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=int(threads)) as ex:
        futs = [
            ex.submit(
                convert_psd_to_png,
                src,
                dst,
                png_compress_level=int(compress),
                optimize=False,
                strip_metadata=True,
            )
            for (src, dst) in tasks
        ]
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                success, msg = fut.result()
                if success:
                    ok += 1
                else:
                    errors.append(msg)
            except Exception as e:
                errors.append(str(e))
            dlg.setValue(i)
            QApplication.processEvents()

    dlg.close()
    _show_done_box(parent, out_dir or os.path.dirname(files[0]), f"PSD→PNG: успешно {ok}/{total}, пропущено {skipped}")
    if errors:
        err_text = "\n".join(list(dict.fromkeys(errors))[:5])
        QMessageBox.warning(parent, "PSD→PNG", f"Некоторые файлы не сконвертированы:\n{err_text}")

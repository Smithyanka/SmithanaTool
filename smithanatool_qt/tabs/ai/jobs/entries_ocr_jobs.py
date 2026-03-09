from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Tuple

from PySide6.QtCore import QRect

from smithanatool_qt.tabs.ai.core.models import OcrRuntimeConfig


class OcrConfigError(Exception):
    """Проблема конфигурации OCR (ключи/настройки)."""


def _page_png_bytes(viewer) -> Tuple[bytes, str]:
    """Возвращает (png_bytes, first_error)."""
    page = viewer.get_current_qimage()
    if page is None or page.isNull():
        return b"", ""
    try:
        return viewer.qimage_to_png_bytes(page), ""
    except Exception as e:
        return b"", str(e)


def _collect_crops_png_bytes(viewer, rects: List[QRect]) -> Tuple[List[int], List[bytes]]:
    """Собирает PNG-байты кропов. Возвращает (индексы, байты)."""
    valid_idx: List[int] = []
    valid_bytes: List[bytes] = []
    for i, r in enumerate(rects):
        crop = viewer.crop_qimage(r)
        if crop is None:
            continue
        try:
            png_bytes = viewer.qimage_to_png_bytes(crop)
        except Exception:
            png_bytes = b""
        if png_bytes:
            valid_idx.append(i)
            valid_bytes.append(png_bytes)
    return valid_idx, valid_bytes


def prepare_ocr_work(
    *,
    viewer,
    ai,
    rects: List[QRect],
    cfg: OcrRuntimeConfig | None = None,
    # optional overrides:
    model: str | None = None,
    lang: str | None = None,
) -> Tuple[List[QRect], Callable[[], Tuple[List[str], str]]]:
    """Готовит work-функцию для фонового OCR.

    Возвращает:
      - rects_fixed: список QRect (копия входного)
      - work_fn: функция без аргументов -> (texts, first_error)

    Может бросить OcrConfigError с текстом для QMessageBox.

    Предпочтительно передавать cfg (snapshot) — так фоновые задачи
    не зависят от дальнейших изменений UI.
    """

    rects_fixed = list(rects)

    # snapshot конфигурации
    if cfg is None:
        raise OcrConfigError("Не удалось получить конфигурацию OCR (cfg).")

    # allow legacy overrides
    if model:
        cfg = OcrRuntimeConfig(**{**cfg.__dict__, "model": (model or "")})
    if lang is not None:
        cfg = OcrRuntimeConfig(**{**cfg.__dict__, "lang_code": (lang or "")})

    if cfg.kind == "yandex":
        # проверим ключи до запуска, чтобы сразу показать ошибку
        api_key = (cfg.api_key or "").strip()
        folder_id = str((cfg.extra or {}).get("folder_id") or "").strip()
        if not api_key or not folder_id:
            raise OcrConfigError("Не задан YC_OCR_API_KEY и/или YC_FOLDER_ID.")

        page_bytes, first_error_init = _page_png_bytes(viewer)
        rois_xywh = [(r.x(), r.y(), r.width(), r.height()) for r in rects_fixed]

        def work():
            first_error = first_error_init
            if not page_bytes:
                return (["" for _ in rects_fixed], first_error)

            try:
                texts = ai.ocr_page_to_rois(page_bytes, rois_xywh, cfg)
                return (texts, first_error)
            except Exception as e:
                if not first_error:
                    first_error = str(e)
                return (["" for _ in rects_fixed], first_error)

        return rects_fixed, work

    # --- LLM/VLM OCR (openai_compat / anthropic / gemini_native / azure_openai, etc.) ---
    api_key = (cfg.api_key or "").strip()
    allow_no_key = bool((cfg.extra or {}).get("allow_no_key") or False)
    if not api_key and not (cfg.kind == "openai_compat" and allow_no_key):
        raise OcrConfigError("Не задан API key.")

    valid_idx, valid_bytes = _collect_crops_png_bytes(viewer, rects_fixed)
    texts_init = ["" for _ in rects_fixed]

    def work():
        first_error = ""
        texts = list(texts_init)
        if not valid_bytes:
            return (texts, first_error)

        try:
            out_all = ai.ocr_images(list(valid_bytes), cfg)
            for k, t in enumerate(out_all):
                if k < len(valid_idx):
                    texts[valid_idx[k]] = (t or "")
        except Exception as e:
            first_error = str(e)

        return (texts, first_error)

    return rects_fixed, work

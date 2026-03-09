from __future__ import annotations

from typing import Iterable, List, Tuple

from smithanatool_qt.tabs.ai.core.models import OcrRuntimeConfig
from smithanatool_qt.tabs.ai.engines.base import VisionPromptRequest
from smithanatool_qt.tabs.ai.features.ocr.parsers import parse_json_string_array
from smithanatool_qt.tabs.ai.features.ocr.prompts import build_extract_text_prompt


class OcrFeature:
    """Логика OCR как "задачи".

    Здесь живёт:
      - prompt для экстракта
      - разбиение на батчи
      - парсинг результата

    А провайдер-специфика (HTTP/auth/форматы) находится в engines/*.
    """

    def __init__(self, ai_service):
        # ai_service должен предоставлять:
        #   - invoke_vision(req, cfg) -> str
        #   - native_ocr_images(images_bytes, cfg) -> List[str]
        #   - native_ocr_page_to_rois(page_png_bytes, rois_xywh, cfg) -> List[str]
        self._ai = ai_service

    def ocr_images(self, images_bytes: List[bytes], cfg: OcrRuntimeConfig) -> List[str]:
        if cfg.kind == "yandex":
            return self._ai.native_ocr_images(images_bytes, cfg)

        n_total = len(images_bytes or [])
        if n_total == 0:
            return []

        bs = max(1, int(cfg.batch_size or 1))
        out: List[str] = []

        for i in range(0, n_total, bs):
            chunk = list(images_bytes[i : i + bs])
            prompt = build_extract_text_prompt(len(chunk), cfg.lang_code)
            req = VisionPromptRequest(prompt=prompt, images_bytes=chunk)
            raw = self._ai.invoke_vision(req, cfg)
            out.extend(parse_json_string_array(raw, expected_len=len(chunk)))

        return out

    def ocr_page_to_rois(
        self,
        page_png_bytes: bytes,
        rois_xywh: Iterable[Tuple[int, int, int, int]],
        cfg: OcrRuntimeConfig,
    ) -> List[str]:
        if cfg.kind != "yandex":
            raise NotImplementedError("ocr_page_to_rois поддерживается только для yandex OCR")
        return self._ai.native_ocr_page_to_rois(page_png_bytes, rois_xywh, cfg)

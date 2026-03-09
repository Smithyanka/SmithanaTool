from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

from smithanatool_qt.tabs.ai.core.models import OcrRuntimeConfig
from smithanatool_qt.tabs.ai.engines.base import NativeOcrEngineAdapter, VisionEngineAdapter, VisionPromptRequest
from smithanatool_qt.tabs.ai.engines.openai_compat import OpenAICompatAdapter
from smithanatool_qt.tabs.ai.engines.yandex import YandexOcrAdapter

from smithanatool_qt.tabs.ai.engines.anthropic import AnthropicAdapter
from smithanatool_qt.tabs.ai.engines.azure_openai import AzureOpenAIAdapter
from smithanatool_qt.tabs.ai.engines.gemini_native import GeminiNativeAdapter

from smithanatool_qt.tabs.ai.features.ocr.feature import OcrFeature


class AiService:
    """Единая точка выполнения AI-задач (пока только OCR).

    Важно:
      - engines/*: только адаптеры провайдеров (HTTP/форматы)
      - features/ocr/*: логика OCR (prompt, батчинг, парсинг)
    """

    def __init__(self):
        self._vision_adapters: Dict[str, VisionEngineAdapter] = {
            "openai_compat": OpenAICompatAdapter(),
            "anthropic": AnthropicAdapter(),
            "gemini_native": GeminiNativeAdapter(),
            "azure_openai": AzureOpenAIAdapter(),
        }
        self._native_ocr_adapters: Dict[str, NativeOcrEngineAdapter] = {
            "yandex": YandexOcrAdapter(),
        }

        self._ocr = OcrFeature(self)

    # ── Provider invocation ───────────────────────────────────────────────
    def _vision_adapter(self, kind: str) -> VisionEngineAdapter:
        k = (kind or "openai_compat").strip() or "openai_compat"
        if k not in self._vision_adapters:
            raise RuntimeError(f"Unsupported vision engine kind: {k}")
        return self._vision_adapters[k]

    def _native_adapter(self, kind: str) -> NativeOcrEngineAdapter:
        k = (kind or "").strip()
        if k not in self._native_ocr_adapters:
            raise RuntimeError(f"Unsupported native OCR engine kind: {k}")
        return self._native_ocr_adapters[k]

    def invoke_vision(self, req: VisionPromptRequest, cfg: OcrRuntimeConfig) -> str:
        if (cfg.kind or "").strip() == "yandex":
            raise RuntimeError("invoke_vision не поддерживается для yandex")
        return self._vision_adapter(cfg.kind).invoke_vision(req, cfg)

    # ── Native OCR helpers for features ──────────────────────────────────
    def native_ocr_images(self, images_bytes: List[bytes], cfg: OcrRuntimeConfig) -> List[str]:
        return self._native_adapter(cfg.kind).ocr_images(images_bytes, cfg)

    def native_ocr_page_to_rois(
        self,
        page_png_bytes: bytes,
        rois_xywh: Iterable[Tuple[int, int, int, int]],
        cfg: OcrRuntimeConfig,
    ) -> List[str]:
        return self._native_adapter(cfg.kind).ocr_page_to_rois(page_png_bytes, rois_xywh, cfg)

    # ── Public OCR API ───────────────────────────────────────────────────
    def ocr_images(self, images_bytes: List[bytes], cfg: OcrRuntimeConfig) -> List[str]:
        return self._ocr.ocr_images(images_bytes, cfg)

    def ocr_page_to_rois(
        self,
        page_png_bytes: bytes,
        rois_xywh: Iterable[Tuple[int, int, int, int]],
        cfg: OcrRuntimeConfig,
    ) -> List[str]:
        return self._ocr.ocr_page_to_rois(page_png_bytes, rois_xywh, cfg)

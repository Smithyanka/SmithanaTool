from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable, List, Tuple

from smithanatool_qt.tabs.ai.core.models import OcrRuntimeConfig


@dataclass(frozen=True)
class VisionPromptRequest:
    """Универсальный "vision" запрос: текстовый prompt + набор изображений.

    Движки (engines/*) отвечают только за то, КАК отправить этот запрос
    конкретному провайдеру и вернуть сырой текст ответа.
    """

    prompt: str
    images_bytes: List[bytes]
    mime_type: str = "image/png"


class VisionEngineAdapter(ABC):
    """Адаптер LLM/VLM провайдера.

    Возвращает "сырой" текст (обычно content) без парсинга.
    """

    @abstractmethod
    def invoke_vision(self, req: VisionPromptRequest, cfg: OcrRuntimeConfig) -> str:
        raise NotImplementedError


class NativeOcrEngineAdapter(ABC):
    """Нативный OCR движок (например Yandex OCR).

    В отличие от LLM/VLM адаптеров, здесь результат сразу структурный (список строк).
    """

    @abstractmethod
    def ocr_images(self, images_bytes: List[bytes], cfg: OcrRuntimeConfig) -> List[str]:
        raise NotImplementedError

    def ocr_page_to_rois(
        self,
        page_png_bytes: bytes,
        rois_xywh: Iterable[Tuple[int, int, int, int]],
        cfg: OcrRuntimeConfig,
    ) -> List[str]:
        raise NotImplementedError

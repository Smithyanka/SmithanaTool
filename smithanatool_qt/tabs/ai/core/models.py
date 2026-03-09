from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple, Union

# ── Engine specs ─────────────────────────────────────────────────────────────

ModelSpec = Union[str, Tuple[str, str]]


@dataclass
class EngineSpec:
    """Описание движка.

    id:
      Стабильный идентификатор движка. Нужен, чтобы удаление/перестановка
      элементов не приводили к "перетеканию" настроек/ключей.

    kind:
      - openai_compat: OpenAI-compatible endpoint (RouterAI/OpenRouter/свой сервер)
      - yandex: Yandex Cloud OCR
      (в будущем могут появиться другие kind, но пока OCR-логика использует эти)

    provider:
      base_url / endpoint (для openai_compat)

    models:
      - builtin обычно [(title, model_id), ...]
      - custom обычно [model_id, ...]

    extra:
      Свободные параметры. Для yandex сюда кладём folder_id и т.п.
    """

    id: str
    name: str
    kind: str = "openai_compat"
    provider: str = ""
    models: List[ModelSpec] = field(default_factory=list)
    api_key: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)
    builtin: bool = False

    def is_openai_compat(self) -> bool:
        return self.kind == "openai_compat"

    def is_yandex(self) -> bool:
        return self.kind == "yandex"

    def is_editable(self) -> bool:
        return (not self.builtin) and (not self.is_yandex())


@dataclass
class OcrRuntimeConfig:
    """Снимок конфигурации OCR на момент запуска задачи."""

    engine_id: str
    kind: str
    provider: str
    api_key: str
    model: str
    lang_code: str
    batch_size: int = 4
    extra: Dict[str, Any] = field(default_factory=dict)

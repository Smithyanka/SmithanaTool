from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EngineCapabilities:
    """Capabilities used by OCR UI and runtime.

    Keep it OCR-focused for now. Extend later when you add new AI features.
    """

    is_yandex: bool

    # UI toggles
    show_llm_fields: bool
    show_yandex_fields: bool

    # OCR behaviour
    supports_batch: bool


def capabilities_for_engine_kind(kind: str) -> EngineCapabilities:
    k = (kind or "").strip().lower()
    if k == "yandex":
        return EngineCapabilities(
            is_yandex=True,
            show_llm_fields=False,
            show_yandex_fields=True,
            supports_batch=False,
        )

    # Default: treat as LLM-like OCR engine.
    return EngineCapabilities(
        is_yandex=False,
        show_llm_fields=True,
        show_yandex_fields=False,
        supports_batch=True,
    )

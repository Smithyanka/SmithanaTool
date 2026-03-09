from __future__ import annotations

import os
from typing import Any, Dict

from smithanatool_qt.tabs.ai.core.models import OcrRuntimeConfig


def _safe_get_text(widget) -> str:
    try:
        return (widget.text() or "").strip()
    except Exception:
        return ""


def _safe_get_current_data(combo) -> str:
    try:
        return str(combo.currentData() or "").strip()
    except Exception:
        return ""


def _safe_get_current_data_dict(combo) -> Dict[str, Any]:
    try:
        d = combo.currentData()
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _default_provider_for_kind(kind: str) -> str:
    k = (kind or "openai_compat").strip().lower()
    if k == "anthropic":
        return os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com").strip()
    if k == "gemini_native":
        # base without /v1beta; adapter will add /v1beta by default
        return os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com").strip()
    if k == "azure_openai":
        return os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    # openai_compat
    return (os.getenv("BASE_URL", "").strip() or "https://routerai.ru/api/v1").strip()


def _default_api_key_for_kind(kind: str) -> str:
    k = (kind or "openai_compat").strip().lower()
    if k == "anthropic":
        return os.getenv("ANTHROPIC_API_KEY", "").strip()
    if k == "gemini_native":
        return (os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip())
    if k == "azure_openai":
        return os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    # openai_compat
    return os.getenv("API_KEY", "").strip() or os.getenv("GEMINI_API_KEY", "").strip()


def build_ocr_runtime_config(right_panel) -> OcrRuntimeConfig:
    """Снимает "снэпшот" настроек OCR с UI.

    ВАЖНО: возвращаемая структура не зависит от индексов в combobox.
    """
    src = getattr(right_panel, "settings", right_panel)

    eng_data = _safe_get_current_data_dict(getattr(src, "cmb_engine", None))
    engine_id = str(eng_data.get("id") or "").strip()
    kind = str(eng_data.get("kind") or "openai_compat").strip() or "openai_compat"
    provider = str(eng_data.get("provider") or "").strip()

    extra = eng_data.get("extra")
    if not isinstance(extra, dict):
        extra = {}

    # lang
    lang_code = _safe_get_current_data(getattr(src, "cmb_lang", None)).lower()

    if kind == "yandex":
        api_key = _safe_get_text(getattr(src, "ed_yc_api_key", None)) or os.getenv("YC_OCR_API_KEY", "").strip()
        folder_id = _safe_get_text(getattr(src, "ed_yc_folder_id", None)) or os.getenv("YC_FOLDER_ID", "").strip()
        return OcrRuntimeConfig(
            engine_id=engine_id,
            kind="yandex",
            provider="",
            api_key=api_key,
            model="",
            lang_code=lang_code,
            batch_size=1,
            extra={"folder_id": folder_id, **extra},
        )

    # LLM-like OCR engines
    api_key = _safe_get_text(getattr(src, "ed_api_key", None))
    if not api_key:
        api_key = _default_api_key_for_kind(kind)

    if not provider:
        provider = _default_provider_for_kind(kind)
    provider = (provider or "").rstrip("/")

    model = _safe_get_current_data(getattr(src, "cmb_model", None))
    if not model:
        try:
            model = (src.cmb_model.currentText() or "").strip()
        except Exception:
            model = ""

    try:
        bs = int(getattr(src, "spn_gemini_batch").value())
        bs = max(1, bs)
    except Exception:
        bs = 4

    return OcrRuntimeConfig(
        engine_id=engine_id,
        kind=kind,
        provider=provider,
        api_key=api_key,
        model=model,
        lang_code=lang_code,
        batch_size=bs,
        extra=dict(extra),
    )

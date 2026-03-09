from __future__ import annotations

import base64
import json
from typing import Any, Dict, List

import requests

from smithanatool_qt.tabs.ai.core.models import OcrRuntimeConfig
from smithanatool_qt.tabs.ai.engines.base import VisionEngineAdapter, VisionPromptRequest


def _as_data_url(image_bytes: bytes, mime_type: str) -> str:
    return f"data:{mime_type};base64," + base64.b64encode(image_bytes).decode("ascii")


class OpenAICompatAdapter(VisionEngineAdapter):
    """OpenAI-compatible (chat/completions) VLM adapter.

    Подходит для RouterAI/OpenRouter/локальных openai-compatible endpoint.

    cfg.extra supported keys:
      - path: str (default: /chat/completions)
      - timeout_s: int (default: 120)
      - max_tokens: int (default: 1200)
      - headers: dict (merged into request headers)
      - auth_header: str (default: Authorization)
      - auth_prefix: str (default: Bearer)
      - allow_no_key: bool (default: False)  # для локальных эндпоинтов
    """

    def invoke_vision(self, req: VisionPromptRequest, cfg: OcrRuntimeConfig) -> str:
        extra: Dict[str, Any] = dict(cfg.extra or {})

        api_key = (cfg.api_key or "").strip()
        allow_no_key = bool(extra.get("allow_no_key") or False)
        if not api_key and not allow_no_key:
            raise RuntimeError("Не задан API key.")

        base_url = (cfg.provider or "").strip().rstrip("/") or "https://routerai.ru/api/v1"

        path = str(extra.get("path") or "").strip() or "/chat/completions"
        if not path.startswith("/"):
            path = "/" + path
        url = base_url + path

        model = (cfg.model or "").strip() or "google/gemini-2.5-flash"

        content: List[Dict[str, Any]] = [{"type": "text", "text": (req.prompt or "").strip()}]
        for b in (req.images_bytes or []):
            content.append({"type": "image_url", "image_url": {"url": _as_data_url(b, req.mime_type)}})

        max_tokens = int(extra.get("max_tokens") or 1200)
        timeout_s = int(extra.get("timeout_s") or 120)

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0,
            "max_tokens": max_tokens,
        }

        headers: Dict[str, str] = {"content-type": "application/json"}

        auth_header = str(extra.get("auth_header") or "Authorization").strip() or "Authorization"
        auth_prefix = str(extra.get("auth_prefix") or "Bearer").strip()
        if api_key:
            if auth_header.lower() == "authorization":
                headers[auth_header] = f"{auth_prefix} {api_key}".strip()
            else:
                headers[auth_header] = (f"{auth_prefix} {api_key}".strip() if auth_prefix else api_key)

        hdr_extra = extra.get("headers")
        if isinstance(hdr_extra, dict):
            for k, v in hdr_extra.items():
                if k and v is not None:
                    headers[str(k)] = str(v)

        r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=timeout_s)
        try:
            j = r.json()
        except Exception:
            j = None

        if r.status_code >= 400:
            msg = ""
            if isinstance(j, dict):
                msg = ((j.get("error") or {}).get("message") or j.get("message") or j.get("detail") or "")
            raise RuntimeError(f"OpenAI-compatible error HTTP {r.status_code}: {msg or r.text}")

        try:
            content_out = j["choices"][0]["message"]["content"]
        except Exception:
            raise RuntimeError(f"Unexpected OpenAI-compatible response: {j!r}")

        # Некоторые прокси возвращают list частей
        if isinstance(content_out, list):
            parts: List[str] = []
            for part in content_out:
                if isinstance(part, dict):
                    t = part.get("text")
                    if isinstance(t, str):
                        parts.append(t)
                elif isinstance(part, str):
                    parts.append(part)
            content_out = "\n".join(parts)

        return (content_out if isinstance(content_out, str) else str(content_out)).strip()

from __future__ import annotations

import base64
import json
from typing import Any, Dict, List

import requests

from smithanatool_qt.tabs.ai.core.models import OcrRuntimeConfig
from smithanatool_qt.tabs.ai.engines.base import VisionEngineAdapter, VisionPromptRequest


class AnthropicAdapter(VisionEngineAdapter):
    """Anthropic Messages API adapter (vision).

    cfg.extra supported keys:
      - anthropic_version: str (default: "2023-06-01")
      - max_tokens: int (default: 1200)
      - timeout_s: int (default: 120)
      - headers: dict (merged into request headers)
      - path: str (default: /v1/messages)
    """

    def invoke_vision(self, req: VisionPromptRequest, cfg: OcrRuntimeConfig) -> str:
        api_key = (cfg.api_key or "").strip()
        if not api_key:
            raise RuntimeError("Не задан API key.")

        base_url = (cfg.provider or "").strip().rstrip("/") or "https://api.anthropic.com"
        extra: Dict[str, Any] = dict(cfg.extra or {})

        path = str(extra.get("path") or "").strip() or "/v1/messages"
        if not path.startswith("/"):
            path = "/" + path
        url = base_url + path

        model = (cfg.model or "").strip()
        if not model:
            raise RuntimeError("Не задана модель (model).")

        # Anthropic content blocks
        content: List[Dict[str, Any]] = [{"type": "text", "text": (req.prompt or "").strip()}]
        for b in (req.images_bytes or []):
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": req.mime_type,
                        "data": base64.b64encode(b).decode("ascii"),
                    },
                }
            )

        max_tokens = int(extra.get("max_tokens") or 1200)
        timeout_s = int(extra.get("timeout_s") or 120)

        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": 0,
            "messages": [{"role": "user", "content": content}],
        }

        headers: Dict[str, str] = {
            "x-api-key": api_key,
            "anthropic-version": str(extra.get("anthropic_version") or "2023-06-01"),
            "content-type": "application/json",
        }

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
                err = j.get("error")
                if isinstance(err, dict):
                    msg = str(err.get("message") or "")
                msg = msg or str(j.get("message") or j.get("detail") or "")
            raise RuntimeError(f"Anthropic error HTTP {r.status_code}: {msg or r.text}")

        # Extract text
        text_parts: List[str] = []
        if isinstance(j, dict):
            content_out = j.get("content")
            if isinstance(content_out, list):
                for part in content_out:
                    if isinstance(part, dict) and part.get("type") == "text":
                        t = part.get("text")
                        if isinstance(t, str):
                            text_parts.append(t)

        text = "\n".join(text_parts).strip()
        if not text and isinstance(j, dict):
            ot = j.get("output_text")
            if isinstance(ot, str):
                text = ot.strip()
        return text

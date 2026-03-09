from __future__ import annotations

import base64
import json
import os
from typing import Any, Dict, List

import requests

from smithanatool_qt.tabs.ai.core.models import OcrRuntimeConfig
from smithanatool_qt.tabs.ai.engines.base import VisionEngineAdapter, VisionPromptRequest


def _as_data_url(image_bytes: bytes, mime_type: str) -> str:
    return f"data:{mime_type};base64," + base64.b64encode(image_bytes).decode("ascii")


class AzureOpenAIAdapter(VisionEngineAdapter):
    """Azure OpenAI chat completions adapter.

    Expects cfg.provider to be Azure endpoint, cfg.model to be deployment-id.

    cfg.extra supported keys:
      - api_version: str (if missing, uses AZURE_OPENAI_API_VERSION env or a safe default)
      - path: str (override path; default: /openai/deployments/{deployment}/chat/completions)
      - auth_header: str (default: api-key)
      - auth_prefix: str (default: "")
      - timeout_s: int (default: 120)
      - max_tokens: int (default: 1200)
      - headers: dict (merged into request headers)
    """

    def invoke_vision(self, req: VisionPromptRequest, cfg: OcrRuntimeConfig) -> str:
        api_key = (cfg.api_key or "").strip() or os.getenv("AZURE_OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("Не задан API key.")

        endpoint = (cfg.provider or "").strip().rstrip("/")
        if not endpoint:
            endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip().rstrip("/")
        if not endpoint:
            raise RuntimeError("Не задан Azure endpoint (provider).")

        deployment = (cfg.model or "").strip()
        if not deployment:
            raise RuntimeError("Не задан deployment (model).")

        extra: Dict[str, Any] = dict(cfg.extra or {})

        api_version = str(extra.get("api_version") or os.getenv("AZURE_OPENAI_API_VERSION", "").strip() or "2024-02-15-preview")
        api_version = api_version.strip() or "2024-02-15-preview"

        path = str(extra.get("path") or "").strip() or f"/openai/deployments/{deployment}/chat/completions"
        if not path.startswith("/"):
            path = "/" + path

        url = f"{endpoint}{path}?api-version={api_version}"

        content: List[Dict[str, Any]] = [{"type": "text", "text": (req.prompt or "").strip()}]
        for b in (req.images_bytes or []):
            content.append({"type": "image_url", "image_url": {"url": _as_data_url(b, req.mime_type)}})

        max_tokens = int(extra.get("max_tokens") or 1200)
        timeout_s = int(extra.get("timeout_s") or 120)

        payload = {
            "messages": [{"role": "user", "content": content}],
            "temperature": 0,
            "max_tokens": max_tokens,
        }

        # auth
        auth_header = str(extra.get("auth_header") or "api-key").strip() or "api-key"
        auth_prefix = str(extra.get("auth_prefix") or "").strip()

        headers: Dict[str, str] = {"content-type": "application/json"}
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
            raise RuntimeError(f"Azure OpenAI error HTTP {r.status_code}: {msg or r.text}")

        try:
            content_out = j["choices"][0]["message"]["content"]
        except Exception:
            raise RuntimeError(f"Unexpected Azure response: {j!r}")

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

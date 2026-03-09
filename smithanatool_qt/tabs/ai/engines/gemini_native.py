from __future__ import annotations

import base64
import json
import os
from typing import Any, Dict, List

import requests

from smithanatool_qt.tabs.ai.core.models import OcrRuntimeConfig
from smithanatool_qt.tabs.ai.engines.base import VisionEngineAdapter, VisionPromptRequest


def _normalize_model(model: str) -> str:
    m = (model or "").strip()
    if not m:
        return ""
    # allow "google/gemini-..." from openai-compat style
    if "/" in m and not m.startswith("models/"):
        m = m.split("/")[-1]
    if m.startswith("models/"):
        m = m[len("models/") :]
    return m


class GeminiNativeAdapter(VisionEngineAdapter):
    """Google Gemini native API adapter (generativelanguage.generateContent).

    Default auth mode uses query param ?key=API_KEY.

    cfg.extra supported keys:
      - api_version: str ("v1beta" by default)
      - path: str (override full path, default: /{api_version}/models/{model}:generateContent)
      - auth_mode: "query"|"bearer" (default: query)
      - timeout_s: int (default: 120)
      - max_tokens: int (default: 1200)
      - headers: dict (merged into request headers)
    """

    def invoke_vision(self, req: VisionPromptRequest, cfg: OcrRuntimeConfig) -> str:
        api_key = (cfg.api_key or "").strip() or os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("Не задан API key.")

        extra: Dict[str, Any] = dict(cfg.extra or {})
        api_version = str(extra.get("api_version") or "v1beta").strip() or "v1beta"

        base_url = (cfg.provider or "").strip().rstrip("/")
        if not base_url:
            base_url = "https://generativelanguage.googleapis.com"

        model_id = _normalize_model(cfg.model)
        if not model_id:
            raise RuntimeError("Не задана модель (model).")

        parts: List[Dict[str, Any]] = [{"text": (req.prompt or "").strip()}]
        for b in (req.images_bytes or []):
            parts.append(
                {
                    "inline_data": {
                        "mime_type": req.mime_type,
                        "data": base64.b64encode(b).decode("ascii"),
                    }
                }
            )

        max_tokens = int(extra.get("max_tokens") or 1200)
        timeout_s = int(extra.get("timeout_s") or 120)

        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": max_tokens},
        }

        path = str(extra.get("path") or "").strip()
        if not path:
            path = f"/{api_version}/models/{model_id}:generateContent"
        if not path.startswith("/"):
            path = "/" + path

        url = base_url + path

        headers: Dict[str, str] = {"content-type": "application/json"}
        hdr_extra = extra.get("headers")
        if isinstance(hdr_extra, dict):
            for k, v in hdr_extra.items():
                if k and v is not None:
                    headers[str(k)] = str(v)

        auth_mode = str(extra.get("auth_mode") or "query").strip().lower()
        if auth_mode == "bearer":
            headers["authorization"] = f"Bearer {api_key}"
        else:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}key={api_key}"

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
            raise RuntimeError(f"Gemini native error HTTP {r.status_code}: {msg or r.text}")

        # candidates[0].content.parts[].text
        text_parts: List[str] = []
        if isinstance(j, dict):
            cands = j.get("candidates")
            if isinstance(cands, list) and cands:
                cand = cands[0]
                if isinstance(cand, dict):
                    cont = cand.get("content")
                    if isinstance(cont, dict):
                        parts_out = cont.get("parts")
                        if isinstance(parts_out, list):
                            for p in parts_out:
                                if isinstance(p, dict):
                                    t = p.get("text")
                                    if isinstance(t, str):
                                        text_parts.append(t)

        text = "\n".join(text_parts).strip()
        if not text and isinstance(j, dict):
            ot = j.get("text")
            if isinstance(ot, str):
                text = ot.strip()
        return text

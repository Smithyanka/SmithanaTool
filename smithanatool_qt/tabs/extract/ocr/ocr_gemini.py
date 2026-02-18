from __future__ import annotations

import base64
import json
from typing import List

import requests


class GeminiOcrEngine:
    """Gemini OCR через RouterAI (OpenAI-compatible).

    Поддерживает:
      - ocr(): одно изображение -> текст
      - ocr_batch(): несколько изображений -> список текстов в том же порядке

    Важно: RouterAI принимает мультимодальный формат OpenAI chat:
    messages[].content = [ {type:text}, {type:image_url}, ... ]
    """

    def __init__(self):
        pass

    @staticmethod
    def _normalize_model(model: str) -> str:
        m = (model or "").strip()
        if not m:
            return "google/gemini-2.5-flash"
        if "/" in m:
            return m
        # совместимость: если в ini осталось "gemini-2.5-flash"
        if m.startswith("gemini-"):
            return "google/" + m
        return m

    @staticmethod
    def _as_data_url_png(image_bytes: bytes) -> str:
        return "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")

    def ocr(
        self,
        image_bytes: bytes,
        api_key: str,
        model: str = "google/gemini-2.5-flash",
        base_url: str = "https://routerai.ru/api/v1",
        lang_hint: str = "",
        timeout_s: int = 90,
        max_tokens: int = 800,
    ) -> str:
        # Реализация через batch, чтобы единообразно парсить ответы
        res = self.ocr_batch(
            images_bytes=[image_bytes],
            api_key=api_key,
            model=model,
            base_url=base_url,
            lang_hint=lang_hint,
            timeout_s=timeout_s,
            max_tokens=max_tokens,
        )
        return (res[0] if res else "").strip()

    def ocr_batch(
        self,
        images_bytes: List[bytes],
        api_key: str,
        model: str = "google/gemini-2.5-flash",
        base_url: str = "https://routerai.ru/api/v1",
        lang_hint: str = "",
        timeout_s: int = 120,
        max_tokens: int = 1200,
    ) -> List[str]:
        api_key = (api_key or "").strip()
        if not api_key:
            raise RuntimeError("Поле [RouterAI API key] пусто.")

        base_url = (base_url or "https://routerai.ru/api/v1").rstrip("/")
        model = self._normalize_model(model)

        n = len(images_bytes)
        if n == 0:
            return []

        hint = (lang_hint or "").strip().lower()
        hint_line = ""
        if hint and hint != "auto":
            hint_line = f"Language hint: {hint}.\n"

        # Короткий промпт -> меньше токенов.
        # Просим отдать строго JSON-массив строк по порядку изображений.
        prompt = (
            f"{hint_line}"
            f"You will receive {n} images. For EACH image, extract all visible text. "
            "Return ONLY a JSON array of strings (length equals number of images) in the same order. "
            "No markdown, no explanations."
        )

        content = [{"type": "text", "text": prompt}]
        for b in images_bytes:
            content.append({"type": "image_url", "image_url": {"url": self._as_data_url_png(b)}})

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0,
            "max_tokens": int(max_tokens),
        }

        url = f"{base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=timeout_s)
        try:
            j = r.json()
        except Exception:
            j = None

        if r.status_code >= 400:
            msg = ""
            if isinstance(j, dict):
                msg = ((j.get("error") or {}).get("message") or j.get("message") or j.get("detail") or "")
            raise RuntimeError(f"RouterAI OCR error HTTP {r.status_code}: {msg or r.text}")

        try:
            content_out = j["choices"][0]["message"]["content"]
        except Exception:
            raise RuntimeError(f"Unexpected RouterAI response: {j!r}")

        # В большинстве случаев content_out — строка. Иногда может быть list-of-parts.
        if isinstance(content_out, list):
            parts = []
            for part in content_out:
                if isinstance(part, dict):
                    t = part.get("text")
                    if isinstance(t, str):
                        parts.append(t)
                elif isinstance(part, str):
                    parts.append(part)
            content_out = "\n".join(parts)

        if not isinstance(content_out, str):
            content_out = str(content_out)

        text = content_out.strip()

        # Пытаемся распарсить JSON-массив.
        # Подстраховка: выдёргиваем первую JSON-структуру из текста.
        arr = None
        try:
            arr = json.loads(text)
        except Exception:
            m = None
            # ищем самый первый [ ... ] блок
            m = __import__("re").search(r"\[[\s\S]*\]", text)
            if m:
                try:
                    arr = json.loads(m.group(0))
                except Exception:
                    arr = None

        if not isinstance(arr, list):
            # fallback: если модель вернула просто текст (один), размажем на все или в 1-ю?
            # Лучше вернуть 1 результат и пустые остальные.
            out = [""] * n
            out[0] = text
            return out

        # Нормализуем длину
        out = []
        for i in range(n):
            v = arr[i] if i < len(arr) else ""
            if v is None:
                v = ""
            out.append(str(v).strip())
        return out

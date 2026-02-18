from __future__ import annotations

import os
from typing import Iterable, List, Tuple


from .ocr_gemini import GeminiOcrEngine
from .ocr_yandex import yandex_ocr_text, yandex_ocr_full, yandex_ocr_map_rois


class ExtractOcrService:
    """Сервис OCR: читает выбор движка/ключи из right panel и вызывает нужный движок.

    Используется в entries_controller.py:
      - selected_engine() -> "gemini" | "yandex"
      - selected_model_lang() -> (model, lang)
      - ocr(png_bytes, model, lang) -> str
      - yandex_page_to_rois(page_png_bytes, rois_xywh, lang) -> List[str]
    """

    def __init__(self, right):
        self.right = right
        self._gemini = GeminiOcrEngine()

    # ── UI helpers ──────────────────────────────────────────────────────────
    def selected_engine(self) -> str:
        # 0: Gemini (RouterAI), 1: Yandex Cloud
        idx = int(getattr(self.right.cmb_engine, "currentIndex")())
        return "yandex" if idx == 1 else "gemini"

    def selected_model_lang(self) -> Tuple[str, str]:
        # lang hint: prefer ISO code from itemData()
        lang = ""
        try:
            lang = (self.right.cmb_lang.currentData() or "").strip()
        except Exception:
            # fallback для совместимости (если где-то старый cmb_lang без data)
            try:
                lang = (self.right.cmb_lang.currentText() or "").strip()
            except Exception:
                lang = ""

        lang = (lang or "").strip().lower()

        if self.selected_engine() == "gemini":
            # right_panel: display name in currentText(), real model id in currentData()
            model = ""
            try:
                model = (self.right.cmb_model.currentData() or "").strip()
            except Exception:
                model = ""
            if not model:
                try:
                    model = (self.right.cmb_model.currentText() or "").strip()
                except Exception:
                    model = ""
            return model, lang

        # Для Yandex модель выбирается внутри вызова (page/handwritten и т.п.)
        return "", lang

    def selected_batch_size(self) -> int:
        """Размер батча для Gemini (RouterAI) из UI.

        Чем больше батч, тем меньше запросов, но тем больше payload base64 и шанс упереться в лимиты.
        """
        try:
            v = int(getattr(self.right, "spn_gemini_batch").value())
            return max(1, v)
        except Exception:
            return 4


    # ── RouterAI (Gemini) ───────────────────────────────────────────────────
    def _routerai_api_key(self) -> str:
        # 1) UI поле
        try:
            k = (self.right.ed_api_key.text() or "").strip()
            if k:
                return k
        except Exception:
            pass
        # 2) env
        k = os.getenv("ROUTERAI_API_KEY", "").strip()
        if k:
            return k
        # 3) совместимость со старым названием (не обязательно)
        return os.getenv("GEMINI_API_KEY", "").strip()

    def _routerai_base_url(self) -> str:
        return (os.getenv("ROUTERAI_BASE_URL", "").strip() or "https://routerai.ru/api/v1").rstrip("/")

    # ── Yandex Cloud ────────────────────────────────────────────────────────
    def _yc_api_key_folder(self) -> Tuple[str, str]:
        # api_key
        api_key = ""
        try:
            api_key = (self.right.ed_yc_api_key.text() or "").strip()
        except Exception:
            api_key = ""
        if not api_key:
            api_key = os.getenv("YC_OCR_API_KEY", "").strip()

        # folder_id
        folder_id = ""
        try:
            folder_id = (self.right.ed_yc_folder_id.text() or "").strip()
        except Exception:
            folder_id = ""
        if not folder_id:
            folder_id = os.getenv("YC_FOLDER_ID", "").strip()

        return api_key, folder_id

    # ── Public API ──────────────────────────────────────────────────────────
    def ocr(self, image_bytes: bytes, model: str = "", lang: str = "") -> str:
        engine = self.selected_engine()

        if engine == "yandex":
            api_key, folder_id = self._yc_api_key_folder()
            if not api_key or not folder_id:
                raise RuntimeError("Не задан YC_OCR_API_KEY и/или YC_FOLDER_ID (ключ/Folder ID Yandex Cloud).")
            return yandex_ocr_text(
                image_bytes=image_bytes,
                api_key=api_key,
                folder_id=folder_id,
                lang_code=(lang or ""),

            )

        # gemini (RouterAI)
        api_key = self._routerai_api_key()
        if not api_key:
            raise RuntimeError("Не задан ROUTERAI_API_KEY (ключ RouterAI).")

        # Подстрахуемся: если модель пришла как отображаемое имя, возьмём выбранный model id из UI
        if not model or "/" not in model:
            model, _lang = self.selected_model_lang()

        return self._gemini.ocr(
            image_bytes=image_bytes,
            api_key=api_key,
            model=model or "google/gemini-2.5-flash",
            base_url=self._routerai_base_url(),
            lang_hint=(lang or ""),
        )

    def ocr_batch(self, images_bytes: List[bytes], model: str = "", lang: str = "", batch_size: int = 4) -> List[str]:
        """OCR нескольких ROI за меньшее число запросов.

        Сейчас батчинг используется только для gemini (RouterAI). Для Yandex остаётся отдельная логика (1 запрос на страницу).
        """
        engine = self.selected_engine()

        if engine == "yandex":
            # Для Yandex батчинг ROI не нужен: есть yandex_page_to_rois()
            return [self.ocr(b, model=model, lang=lang) for b in images_bytes]

        api_key = self._routerai_api_key()
        if not api_key:
            raise RuntimeError("Не задан ROUTERAI_API_KEY (ключ RouterAI).")

        if not model or "/" not in (model or ""):
            model, _ = self.selected_model_lang()

        # режем на чанки, чтобы не раздувать payload (base64 + токены)
        bs = max(1, int(batch_size or 1))
        out: List[str] = []
        for i in range(0, len(images_bytes), bs):
            chunk = images_bytes[i:i + bs]
            out.extend(
                self._gemini.ocr_batch(
                    images_bytes=list(chunk),
                    api_key=api_key,
                    model=model or "google/gemini-2.5-flash",
                    base_url=self._routerai_base_url(),
                    lang_hint=(lang or ""),
                )
            )
        return out


    def yandex_page_to_rois(self, page_png_bytes: bytes, rois_xywh: Iterable[Tuple[int, int, int, int]], lang: str = "") -> \
    List[str]:
        api_key, folder_id = self._yc_api_key_folder()
        if not api_key or not folder_id:
            raise RuntimeError("Не задан YC_OCR_API_KEY и/или YC_FOLDER_ID (ключ/Folder ID Yandex Cloud).")

        resp = yandex_ocr_full(
            image_bytes=page_png_bytes,
            api_key=api_key,
            folder_id=folder_id,
            lang_code=(lang or ""),
            model="page",
        )
        return yandex_ocr_map_rois(ocr_resp=resp, rois=list(rois_xywh), mode="intersect")

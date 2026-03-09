from __future__ import annotations


def build_extract_text_prompt(n_images: int, lang_hint: str = "") -> str:
    """Промпт для OCR-экстракта через LLM/VLM.

    Требуем строгий формат ответа: JSON-массив строк длиной n_images.
    """

    n = int(n_images or 0)
    if n <= 0:
        return "Return ONLY an empty JSON array []"

    hint = (lang_hint or "").strip().lower()
    hint_line = ""
    if hint and hint != "auto":
        hint_line = f"Language hint: {hint}.\n"

    return (
        f"{hint_line}"
        f"You will receive {n} images. For EACH image, extract all visible text. "
        "Return ONLY a JSON array of strings (length equals number of images) in the same order. "
        "No markdown, no explanations."
    )

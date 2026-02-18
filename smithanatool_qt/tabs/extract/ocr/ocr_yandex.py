from __future__ import annotations

import base64
import json
import time
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from typing import Dict, List, Optional, Tuple, Any


# Yandex Vision OCR quotas can be as low as 1 request/sec on some accounts.
# We enforce a soft rate-limit in-process to avoid HTTP 429.
_lock = threading.Lock()
_next_allowed_ts: float = 0.0


def _rate_limit(min_interval: float = 1.05) -> None:
    global _next_allowed_ts
    with _lock:
        now = time.monotonic()
        wait = _next_allowed_ts - now
        if wait > 0:
            time.sleep(wait)
        _next_allowed_ts = time.monotonic() + float(min_interval)


def _map_lang(lang_code: str) -> Optional[str]:
    hint = (lang_code or "").strip().lower()
    lang_map = {
        "korean": "ko",
        "japan": "ja",
        "english": "en",
        "jp": "ja",
        "en": "en",
        "ru": "ru",
        "auto": None,
        "": None,
    }

    return lang_map.get(hint, hint)


def _line_to_text(ln: Dict) -> str:
    t = (ln.get("text") or "").strip()
    if t:
        return t
    words = ln.get("words") or []
    parts: List[str] = []
    for w in words:
        wt = (w.get("text") or "").strip()
        if wt:
            parts.append(wt)
    return " ".join(parts).strip()


def _extract_text(resp: Dict) -> str:
    root = resp or {}
    if isinstance(root, dict) and "result" in root and isinstance(root["result"], dict):
        root = root["result"]

    ta = (root.get("textAnnotation") or {}) if isinstance(root, dict) else {}
    lines_out: List[str] = []

    pages = ta.get("pages") or []
    if pages:
        for p in pages:
            for b in (p.get("blocks") or []):
                for ln in (b.get("lines") or []):
                    t = _line_to_text(ln)
                    if t:
                        lines_out.append(t)
    else:
        for b in (ta.get("blocks") or []):
            for ln in (b.get("lines") or []):
                t = _line_to_text(ln)
                if t:
                    lines_out.append(t)

    return "\n".join(lines_out).strip()



def _poly_to_rect(poly: Dict) -> Tuple[int, int, int, int]:
    """Polygon(vertices)->(x1,y1,x2,y2) in image pixels."""
    verts = (poly or {}).get("vertices") or []
    xs: List[int] = []
    ys: List[int] = []
    for v in verts:
        try:
            xs.append(int(v.get("x", 0)))
            ys.append(int(v.get("y", 0)))
        except Exception:
            continue
    if not xs or not ys:
        return 0, 0, 0, 0
    return min(xs), min(ys), max(xs), max(ys)


def _iter_words(resp: Dict) -> List[Dict[str, Any]]:
    """Flatten response into word items: {text, bbox=(x1,y1,x2,y2)}."""
    root = resp or {}
    if isinstance(root, dict) and "result" in root and isinstance(root["result"], dict):
        root = root["result"]

    ta = (root.get("textAnnotation") or {}) if isinstance(root, dict) else {}
    out: List[Dict[str, Any]] = []

    # REST recognizeText response for images typically has blocks directly.
    blocks = ta.get("blocks") or []
    for b in blocks:
        for ln in (b.get("lines") or []):
            # prefer words if present, but keep line bbox for fallback
            words = ln.get("words") or []
            if words:
                for w in words:
                    t = (w.get("text") or "").strip()
                    if not t:
                        continue
                    bbox = _poly_to_rect(w.get("boundingBox") or {})
                    if bbox == (0, 0, 0, 0):
                        # fallback to line bbox
                        bbox = _poly_to_rect(ln.get("boundingBox") or {})
                    out.append({"text": t, "bbox": bbox})
            else:
                t = (ln.get("text") or "").strip()
                if not t:
                    continue
                bbox = _poly_to_rect(ln.get("boundingBox") or {})
                out.append({"text": t, "bbox": bbox, "is_line": True})

    return out


def _rect_intersects(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> bool:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    if ax2 <= ax1 or ay2 <= ay1 or bx2 <= bx1 or by2 <= by1:
        return False
    return not (ax2 <= bx1 or bx2 <= ax1 or ay2 <= by1 or by2 <= ay1)


def _rect_inside(inner: Tuple[int, int, int, int], outer: Tuple[int, int, int, int]) -> bool:
    ix1, iy1, ix2, iy2 = inner
    ox1, oy1, ox2, oy2 = outer
    return ix1 >= ox1 and iy1 >= oy1 and ix2 <= ox2 and iy2 <= oy2


def _words_to_text(words: List[Dict[str, Any]]) -> str:
    """Sort by (y,x) and glue into text; approximates line breaks by y-clustering."""
    if not words:
        return ""

    # Expand bbox and compute simple stats
    items = []
    heights: List[int] = []
    for w in words:
        x1, y1, x2, y2 = w.get("bbox", (0, 0, 0, 0))
        t = (w.get("text") or "").strip()
        if not t:
            continue
        h = max(1, y2 - y1)
        heights.append(h)
        items.append({
            "text": t,
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "cx": (x1 + x2) / 2.0,
            "cy": (y1 + y2) / 2.0,
            "h": h,
        })

    if not items:
        return ""

    items.sort(key=lambda it: (it["y1"], it["x1"]))

    # y clustering threshold
    heights.sort()
    med_h = heights[len(heights) // 2] if heights else 12
    thr = max(6.0, float(med_h) * 0.65)

    lines: List[List[Dict[str, Any]]] = []
    cur: List[Dict[str, Any]] = []
    cur_y: Optional[float] = None
    for it in items:
        if cur_y is None:
            cur = [it]
            cur_y = it["cy"]
            continue
        if abs(it["cy"] - cur_y) <= thr:
            cur.append(it)
            # update running center
            cur_y = (cur_y * 0.7) + (it["cy"] * 0.3)
        else:
            lines.append(cur)
            cur = [it]
            cur_y = it["cy"]
    if cur:
        lines.append(cur)

    out_lines: List[str] = []
    for ln in lines:
        ln.sort(key=lambda it: it["x1"])
        out_lines.append(" ".join(it["text"] for it in ln).strip())

    # Keep line breaks (caller may normalize)
    return "\n".join([l for l in out_lines if l]).strip()


def yandex_ocr_full(
    *,
    image_bytes: bytes,
    api_key: str,
    folder_id: str,
    lang_code: str = "auto",
    model: str = "page",
    min_interval: float = 1.05,
    max_retries: int = 5,
) -> Dict[str, Any]:
    """Call Yandex OCR and return full JSON response (for bbox mapping).

    Cache is keyed by sha256(image_bytes + lang + model).
    """
    if not image_bytes:
        return {}

    iso = _map_lang(lang_code)
    payload: Dict[str, Any] = {
        "mimeType": "image/png",
        "content": base64.b64encode(image_bytes).decode("ascii"),
        "model": (model or "page"),
    }

    if iso:
        payload["languageCodes"] = [iso]
    else:
        payload["languageCodes"] = ["ko", "ja", "en", "ru"]


    req = Request(
        "https://ocr.api.cloud.yandex.net/ocr/v1/recognizeText",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Api-Key {api_key}",
            "x-folder-id": folder_id,
        },
        method="POST",
    )

    last_err: Optional[Exception] = None
    for attempt in range(max_retries):
        _rate_limit(min_interval=min_interval)
        try:
            with urlopen(req, timeout=60) as r:
                resp = json.loads(r.read().decode("utf-8"))
            return resp
        except HTTPError as e:
            msg = e.read().decode("utf-8", "ignore")
            if e.code == 429 and attempt < (max_retries - 1):
                time.sleep(1.2 + attempt * 0.8)
                continue
            raise RuntimeError(f"Yandex OCR HTTP {e.code}: {msg}")
        except URLError as e:
            last_err = e
            if attempt < (max_retries - 1):
                time.sleep(0.8 + attempt * 0.4)
                continue
            break

    raise RuntimeError(f"Yandex OCR network error: {last_err}")


def yandex_ocr_map_rois(
    *,
    ocr_resp: Dict[str, Any],
    rois: List[Tuple[int, int, int, int]],
    mode: str = "intersect",
) -> List[str]:
    """Map one OCR response to many ROI rectangles (x,y,w,h).

    mode:
      - "intersect": word bbox intersects ROI
      - "inside": word bbox fully inside ROI
    """
    items = _iter_words(ocr_resp)
    out: List[str] = []
    for (x, y, w, h) in rois:
        roi = (int(x), int(y), int(x + w), int(y + h))
        picked: List[Dict[str, Any]] = []
        for it in items:
            bb = it.get("bbox", (0, 0, 0, 0))
            ok = _rect_intersects(bb, roi) if mode != "inside" else _rect_inside(bb, roi)
            if ok:
                picked.append(it)
        out.append(_words_to_text(picked))
    return out


def yandex_ocr_text(
    *,
    image_bytes: bytes,
    api_key: str,
    folder_id: str,
    lang_code: str = "auto",
    min_interval: float = 1.05,
    max_retries: int = 5,
) -> str:
    """Extract text from image bytes using Yandex Cloud OCR.

    Handles:
      - languageCodes rules (never send 0 codes)
      - response wrapper {"result": ...}
      - soft in-process rate limiting (avoid 429)
      - retry with backoff on 429
    """

    if not image_bytes:
        return ""

    iso = _map_lang(lang_code)

    payload: Dict = {
        "mimeType": "image/png",
        "content": base64.b64encode(image_bytes).decode("ascii"),
    }

    # Yandex OCR требует хотя бы 1 language code
    if iso:
        payload["languageCodes"] = [iso]
    else:
        payload["languageCodes"] = ["ko", "ja", "en", "ru"]

    req = Request(
        "https://ocr.api.cloud.yandex.net/ocr/v1/recognizeText",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Api-Key {api_key}",
            "x-folder-id": folder_id,
        },
        method="POST",
    )

    last_err: Optional[Exception] = None

    for attempt in range(max_retries):
        # enforce rate-limit before every try
        _rate_limit(min_interval=min_interval)

        try:
            with urlopen(req, timeout=60) as r:
                resp = json.loads(r.read().decode("utf-8"))
            return _extract_text(resp)

        except HTTPError as e:
            msg = e.read().decode("utf-8", "ignore")
            # 429: Too Many Requests — backoff and retry
            if e.code == 429 and attempt < (max_retries - 1):
                # progressive backoff (keep >= 1 sec)
                time.sleep(1.2 + attempt * 0.8)
                continue
            raise RuntimeError(f"Yandex OCR HTTP {e.code}: {msg}")

        except URLError as e:
            last_err = e
            # network hiccup: small retry
            if attempt < (max_retries - 1):
                time.sleep(0.8 + attempt * 0.4)
                continue
            break

    raise RuntimeError(f"Yandex OCR network error: {last_err}")

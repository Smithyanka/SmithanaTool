# -*- coding: utf-8 -*-
"""IO-утилиты для новелл Kakao: последовательное сохранение изображений."""

from __future__ import annotations

from pathlib import Path

def _save_images_sequential(context, urls, ch_dir: Path, ref_url: str, pick_ext):
    """
    Download images with Referer header, continuing numbering from the max existing NNN.* in ch_dir.
    Returns (saved, failed).
    """
    import os, re as _re
    request = context.request
    headers = {"Referer": "https://page.kakao.com/"}

    # find current max index
    base_index = 0
    try:
        if ch_dir.exists():
            for f in ch_dir.iterdir():
                if not f.is_file():
                    continue
                m = _re.match(r"^(\d{3})\.[A-Za-z0-9]+$", f.name)
                if m:
                    try:
                        idx = int(m.group(1))
                        if idx > base_index:
                            base_index = idx
                    except Exception:
                        pass
    except Exception:
        base_index = 0

    saved = 0
    failed = 0
    for u in list(urls or []):
        try:
            if not u:
                failed += 1
                continue
            resp = request.get(u, headers=headers, timeout=60000)
            if not resp.ok:
                failed += 1
                continue
            ct = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
            ext = pick_ext(u, ct, default=".img")

            # next free index
            i = base_index + 1
            while (ch_dir / f"{i:03d}{ext}").exists():
                i += 1

            data = resp.body()
            if not ch_dir.exists():
                try:
                    os.makedirs(ch_dir, exist_ok=True)
                except Exception:
                    pass

            with open(ch_dir / f"{i:03d}{ext}", "wb") as f:
                f.write(data)

            base_index = i
            saved += 1
        except Exception:
            failed += 1
    return saved, failed




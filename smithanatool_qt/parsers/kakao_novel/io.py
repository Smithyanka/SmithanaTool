# -*- coding: utf-8 -*-
import os
from pathlib import Path
from io import BytesIO
from typing import Iterable, Tuple, Optional

from PIL import Image, UnidentifiedImageError  # pip install pillow


def ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)


def chapter_has_files(ch_dir: Path) -> bool:
    if not ch_dir.exists():
        return False
    try:
        next(ch_dir.iterdir())
        return True
    except StopIteration:
        return False
    except Exception:
        return False


def resize_bytes_if_needed(
    data: bytes,
    target_w: int,
    content_type: Optional[str],
    ext_lower: str,
) -> bytes:
    """
    Если target_w > 0 и изображение шире — уменьшаем, иначе возвращаем оригинал.
    Безопасно: при любой ошибке возвращаем исходные bytes.
    """
    if not target_w or target_w <= 0:
        return data
    try:
        im = Image.open(BytesIO(data))
        # анимации не трогаем
        if getattr(im, "is_animated", False):
            return data

        w, h = im.size
        if w <= target_w:
            return data

        new_h = int(h * (target_w / float(w)))
        im = im.resize((target_w, new_h), Image.LANCZOS)

        # выбираем формат сохранения
        fmt = None
        if ext_lower in (".jpg", ".jpeg") or (content_type and "jpeg" in content_type):
            fmt = "JPEG"
        elif ext_lower == ".png" or (content_type and "png" in content_type):
            fmt = "PNG"
        elif ext_lower == ".webp" or (content_type and "webp" in content_type):
            fmt = "WEBP"

        if not fmt:
            return data

        buf = BytesIO()
        save_kwargs = {"optimize": True}
        if fmt == "JPEG":
            save_kwargs.update(quality=92)
        im.save(buf, fmt, **save_kwargs)
        return buf.getvalue()
    except UnidentifiedImageError:
        return data
    except Exception:
        return data


def save_images_with_context(
    context,
    urls: Iterable[str],
    ch_dir: Path,
    ref_url: str,
    target_w: int,
    pick_ext,
    log=lambda s: None,
) -> Tuple[int, int]:
    """
    Скачивает urls КОНКУРРЕНТНО через requests.Session с ретраями.
    Куки берём из Playwright context (для доменов Kakao/CloudFront), передаём Referer.
    Имена 001.ext, 002.ext, ... — сохраняем порядок независимо от параллелизма.
    Возвращает (saved, failed).
    """
    import requests
    from requests.adapters import HTTPAdapter
    try:
        # Retry может отсутствовать если старая requests/urllib3
        from urllib3.util.retry import Retry
    except Exception:
        Retry = None

    # Настройки параллелизма
    try:
        workers = int(os.getenv("KAKAO_DL_WORKERS", "8"))
    except Exception:
        workers = 8
    workers = max(2, min(32, workers))

    # Готовим каталог
    if not ch_dir.exists():
        try:
            os.makedirs(ch_dir, exist_ok=True)
        except Exception:
            pass

    # Собираем куки из Playwright
    cookie_header = None
    try:
        ck = context.cookies()
        if ck:
            parts = []
            for c in ck:
                name, value = c.get("name"), c.get("value")
                if name is not None and value is not None:
                    parts.append(f"{name}={value}")
            if parts:
                cookie_header = "; ".join(parts)
    except Exception:
        cookie_header = None

    # Готовим requests.Session с пулами и ретраями
    sess = requests.Session()
    if Retry is not None:
        retry = Retry(
            total=3,
            backoff_factor=0.25,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(pool_connections=workers*2, pool_maxsize=workers*4, max_retries=retry)
    else:
        adapter = HTTPAdapter(pool_connections=workers*2, pool_maxsize=workers*4)
    sess.mount("http://", adapter)
    sess.mount("https://", adapter)

    # Базовые заголовки
    headers = {
        "Referer": ref_url or "https://page.kakao.com/",
        "User-Agent": "Mozilla/5.0",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Language": "ko,en;q=0.9,ru;q=0.8",
        "Connection": "keep-alive",
    }
    if cookie_header:
        headers["Cookie"] = cookie_header

    # Подготовим задания с порядковыми индексами
    url_list = list(dict.fromkeys([u for u in urls if isinstance(u, str) and u.strip()]))  # дедуп + порядок
    tasks = [(idx+1, u) for idx, u in enumerate(url_list)]

    saved = 0
    failed = 0

    # Вложенный воркер
    def _download_one(item):
        idx, u = item
        try:
            r = sess.get(u, headers=headers, timeout=(10, 60), stream=True)
            if r.status_code != 200 or not r.content:
                return (idx, u, None, None, f"HTTP {r.status_code}")
            ct = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
            ext = pick_ext(u, ct, default=".img")
            data = r.content
            # потенциальный ресайз
            data = resize_bytes_if_needed(data, target_w, ct, ext.lower())
            # имя по порядку
            name = f"{idx:03d}{ext}"
            # запись
            with open(ch_dir / name, "wb") as f:
                f.write(data)
            return (idx, u, name, None, None)
        except Exception as e:
            return (idx, u, None, None, str(e))

    # Параллельное выполнение с контролем порядка имён уже обеспечено через idx
    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_download_one, t) for t in tasks]
        for fut in as_completed(futs):
            idx, u, name, _, err = fut.result()
            if name:
                saved += 1
                try: log(f"[Загрузка] {name}")
                except Exception: pass
            else:
                failed += 1
                try: log(f"[WARN] Ошибка скачивания {u}: {err}")
                except Exception: pass

    try:
        sess.close()
    except Exception:
        pass
    return saved, failed

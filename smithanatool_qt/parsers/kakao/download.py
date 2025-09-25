from __future__ import annotations
from typing import Optional, Callable, List, Tuple
from pathlib import Path
import ssl, urllib.request, re, os
from concurrent.futures import ThreadPoolExecutor, as_completed
from .utils import _compute_workers

def _ext_from_url(url: str) -> str:
    try:
        from urllib.parse import urlparse, parse_qs
        p = urlparse(url)
        name = os.path.basename(p.path) or ""
        if "." in name:
            ext = "." + name.split(".")[-1]
            if len(ext) <= 6: return ext.lower()
        qs = parse_qs(p.query)
        fmt = (qs.get("format") or qs.get("f") or [None])[0]
        if fmt: return f".{str(fmt).lower()}"
    except Exception:
        pass
    return ".jpg"

def _try_get_image_size(img_bytes: bytes) -> tuple[int, int] | None:
    try:
        from PIL import Image
        from io import BytesIO
        with Image.open(BytesIO(img_bytes)) as im:
            return int(im.width), int(im.height)
    except Exception:
        return None

def _download_binary(url: str, dest_path: str, *, referer: Optional[str], cookie_raw: Optional[str], origin: Optional[str] = None) -> bool:
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url)
        if referer: req.add_header("Referer", referer)
        if origin:  req.add_header("Origin", origin)
        if cookie_raw: req.add_header("Cookie", cookie_raw)
        req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36")
        req.add_header("Accept", "image/avif,image/webp,image/apng,image/*,*/*;q=0.8")
        with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
            data = resp.read()
        Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(data)
        return True
    except Exception:
        return False

def _get_existing_max_index(dest_dir: str) -> int:
    max_idx = 0
    for p in Path(dest_dir).glob("*.?*"):
        m = re.search(r"(\d{3})\.", p.name)
        if m:
            try: max_idx = max(max_idx, int(m.group(1)))
            except Exception: pass
    return max_idx

def _download_images_from_list(
    urls: List[str], dest_dir: str, *,
    referer: Optional[str], cookie_raw: Optional[str],
    min_width: int = 0, log: Optional[Callable[[str], None]] = None,
    stop_flag: Optional[Callable[[], bool]] = None,
    auto_threads: bool = True, threads: int = 4,
) -> int:
    Path(dest_dir).mkdir(parents=True, exist_ok=True)

    uniq, seen = [], set()
    for u in urls or []:
        if not isinstance(u, str): continue
        u = u.strip()
        if not u or u.startswith("blob:") or u.startswith("data:"): continue
        if u in seen: continue
        seen.add(u); uniq.append(u)
    if not uniq:
        if log: log("[WARN] DOM-список пуст.")
        return 0

    start_idx = _get_existing_max_index(dest_dir)
    jobs = []
    for off, u in enumerate(uniq, 1):
        idx = start_idx + off
        ext = _ext_from_url(u)
        fn  = f"{idx:03d}{ext}"
        jobs.append((idx, u, fn))

    if stop_flag and stop_flag():
        if log: log("[STOP] Остановка перед началом скачивания.")
        return 0

    saved, max_workers = 0, _compute_workers(auto_threads, threads)

    def _task(idx: int, url: str, fn: str) -> tuple[int, bool, str]:
        if stop_flag and stop_flag(): return (idx, False, fn)
        out_path = str(Path(dest_dir) / fn)
        ok = _download_binary(url, out_path, referer=referer, cookie_raw=cookie_raw, origin="https://page.kakao.com")
        if not ok: return (idx, False, fn)
        if min_width and min_width > 0:
            try:
                with open(out_path, "rb") as f: bb = f.read()
                size = _try_get_image_size(bb)
                if size and size[0] < int(min_width):
                    Path(out_path).unlink(missing_ok=True)
                    return (idx, False, fn)
            except Exception: pass
        return (idx, True, fn)

    futures = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for idx, url, fn in jobs:
            if stop_flag and stop_flag(): break
            futures.append(ex.submit(_task, idx, url, fn))
        for fut in as_completed(futures):
            if stop_flag and stop_flag(): break
            try:
                idx, ok, fn = fut.result()
            except Exception:
                ok, fn = False, "<?>"
            if ok:
                saved += 1
                if log: log(f"[IMG] Загрузка → {fn}")
            else:
                if log: log(f"[WARN] Не скачано: {fn}")
    if log: log(f"[OK] DOM: докачано {saved} (из {len(jobs)}), потоки={max_workers}")
    return saved

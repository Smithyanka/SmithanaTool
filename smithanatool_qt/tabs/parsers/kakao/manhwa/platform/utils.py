from __future__ import annotations
import os
from pathlib import Path

def ensure_dir(p: str):
    Path(p).mkdir(parents=True, exist_ok=True)

def _viewer_url(series_id: int, product_id: str) -> str:
    return f"https://page.kakao.com/viewer?product_id={product_id}&series_id={series_id}"

def _compute_workers(auto_threads: bool, threads: int) -> int:
    if auto_threads:
        return max(2, min(32, (os.cpu_count() or 4)))
    return max(1, min(32, int(threads or 1)))

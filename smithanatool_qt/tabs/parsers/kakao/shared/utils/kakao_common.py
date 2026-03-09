from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

import requests


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_name(name: str) -> str:
    s = re.sub(r'[\\/:*?"<>|]+', '_', str(name or '').strip())
    s = re.sub(r'\s+', ' ', s).strip().rstrip('.')
    return s or 'untitled'


def apply_raw_cookie(session: requests.Session, raw_cookie: Optional[str], domain: str = '.kakao.com') -> None:
    if not raw_cookie:
        return
    for part in str(raw_cookie).split(';'):
        if '=' not in part:
            continue
        k, v = part.strip().split('=', 1)
        k = k.strip()
        v = v.strip()
        if not k:
            continue
        try:
            session.cookies.set(k, v, domain=domain)
        except Exception:
            pass


def compute_workers(auto_threads: bool, threads: int) -> int:
    if auto_threads:
        return max(2, min(32, (os.cpu_count() or 4) // 2 or 2))
    return max(1, min(32, int(threads or 1)))


def text_score(s: str) -> int:
    hangul = sum(1 for ch in s if '가' <= ch <= '힣')
    latin1_noise = sum(1 for ch in s if 0x00C0 <= ord(ch) <= 0x017F)
    return hangul * 5 - latin1_noise * 2


def repair_mojibake_text(s: str) -> str:
    if not s:
        return s

    best = s
    best_score = text_score(s)

    for src_enc in ('latin1', 'cp1252'):
        try:
            candidate = s.encode(src_enc).decode('utf-8')
        except Exception:
            continue
        score = text_score(candidate)
        if score > best_score:
            best = candidate
            best_score = score

    return best


def repair_mojibake_obj(obj):
    if isinstance(obj, str):
        return repair_mojibake_text(obj)
    if isinstance(obj, list):
        return [repair_mojibake_obj(x) for x in obj]
    if isinstance(obj, dict):
        return {k: repair_mojibake_obj(v) for k, v in obj.items()}
    return obj


def parse_json_response(resp: requests.Response) -> dict:
    raw = resp.content
    last_error = None

    for enc in ('utf-8-sig', 'utf-8', 'cp949', 'euc-kr'):
        try:
            data = json.loads(raw.decode(enc))
            return repair_mojibake_obj(data)
        except Exception as e:
            last_error = e

    try:
        data = resp.json()
        return repair_mojibake_obj(data)
    except Exception as e:
        raise RuntimeError(f'Не удалось разобрать JSON-ответ: {e}; last_decode_error={last_error}')

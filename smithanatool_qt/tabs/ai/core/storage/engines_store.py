from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, List, Dict


def custom_engines_path(settings_ini_path: Path, filename: str = "custom_engines.json") -> Path:
    """Файл custom_engines.json рядом с settings.ini."""
    try:
        return settings_ini_path.resolve().parent / filename
    except Exception:
        return Path(filename)


def _new_id() -> str:
    return uuid.uuid4().hex


def normalize_custom_engines(data: Any) -> List[Dict]:
    """Нормализовать список движков (валидация + чистка + id)."""
    if not isinstance(data, list):
        return []

    out: List[Dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue

        eng_id = str(item.get("id") or "").strip() or _new_id()
        name = str(item.get("name") or "").strip()
        kind = str(item.get("kind") or "openai_compat").strip() or "openai_compat"
        provider = str(item.get("provider") or "").strip()

        models = item.get("models") or []
        if isinstance(models, str):
            models = [models]
        if not isinstance(models, list):
            models = []
        models = [str(m).strip() for m in models if str(m).strip()]

        api_key = str(item.get("api_key") or "").strip()
        extra = item.get("extra")
        if not isinstance(extra, dict):
            extra = {}

        if not name:
            continue

        out.append(
            {
                "id": eng_id,
                "name": name,
                "kind": kind,
                "provider": provider,
                "models": models,
                "api_key": api_key,
                "extra": extra,
            }
        )

    return out


def read_custom_engines_file(path: Path) -> List[Dict]:
    try:
        if not path.exists() or not path.is_file():
            return []
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return []
        data = json.loads(raw)
        return normalize_custom_engines(data)
    except Exception:
        return []


def write_custom_engines_file(path: Path, engines: List[Dict]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(engines or [], ensure_ascii=False, indent=2)

        # атомарная запись
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)
    except Exception:
        # хранение движков не должно падать приложение
        pass


def parse_custom_engines_ini_raw(raw: str) -> List[Dict]:
    raw = str(raw or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    return normalize_custom_engines(data)

from __future__ import annotations

import uuid
from typing import Iterable, List, Sequence, Tuple, Optional, Dict, Any

from .models import EngineSpec, ModelSpec


def _new_id() -> str:
    return uuid.uuid4().hex


def _norm_kind(kind: str) -> str:
    k = (kind or "openai_compat").strip().lower()
    return k or "openai_compat"


def _ensure_dict(v) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _validate_custom(kind: str, provider: str, models: Sequence[str]) -> None:
    k = _norm_kind(kind)
    provider = (provider or "").strip()
    models_n = [str(m).strip() for m in (models or []) if str(m).strip()]

    if not models_n:
        raise ValueError("models is empty")

    if k in ("openai_compat", "azure_openai") and not provider:
        raise ValueError("provider is empty")

    if k == "yandex":
        raise ValueError("custom yandex engine is not supported")


class EngineManager:
    """Хранит список движков и делает CRUD над кастомными.

    ВАЖНО: EngineManager НЕ читает/не пишет INI.
    """

    BUILTIN_GEMINI_ID = "builtin_gemini_routerai"
    BUILTIN_YANDEX_ID = "builtin_yandex_cloud"

    def __init__(self, engines: Sequence[EngineSpec] | None = None):
        self._engines: List[EngineSpec] = list(engines or [])

    @staticmethod
    def default_builtins(gemini_api_key: str = "") -> List[EngineSpec]:
        builtin_models: List[Tuple[str, str]] = [
            ("Gemini 2.5 Flash Lite", "google/gemini-2.5-flash-lite"),
            ("Gemini 2.5 Flash", "google/gemini-2.5-flash"),
        ]
        return [
            EngineSpec(
                id=EngineManager.BUILTIN_GEMINI_ID,
                name="Gemini (RouterAI)",
                kind="openai_compat",
                provider="",
                models=builtin_models,
                api_key=(gemini_api_key or "").strip(),
                extra={},
                builtin=True,
            ),
            EngineSpec(
                id=EngineManager.BUILTIN_YANDEX_ID,
                name="Yandex Cloud",
                kind="yandex",
                provider="",
                models=[],
                api_key="",
                extra={},
                builtin=True,
            ),
        ]

    @classmethod
    def from_sources(
        cls,
        *,
        custom_engines: Iterable[dict] | None = None,
        gemini_api_key: str = "",
    ) -> "EngineManager":
        builtins = cls.default_builtins(gemini_api_key=gemini_api_key)

        customs: List[EngineSpec] = []
        for e in (custom_engines or []):
            if not isinstance(e, dict):
                continue

            eng_id = str(e.get("id") or "").strip() or _new_id()
            name = str(e.get("name") or "").strip()
            kind = _norm_kind(e.get("kind") or "openai_compat")
            provider = str(e.get("provider") or "").strip()
            models = cls._normalize_models(e.get("models") or [])
            api_key = str(e.get("api_key") or "").strip()
            extra = _ensure_dict(e.get("extra"))

            if not name:
                continue

            # validation for known kinds
            if kind == "yandex":
                # кастомный yandex не поддерживаем (есть builtin)
                continue

            # for all LLM-like kinds require models; provider depends on kind
            try:
                _validate_custom(kind, provider, models)
            except Exception:
                continue

            customs.append(
                EngineSpec(
                    id=eng_id,
                    name=name,
                    kind=kind,
                    provider=provider,
                    models=models,
                    api_key=api_key,
                    extra=extra,
                    builtin=False,
                )
            )

        return cls([*builtins, *customs])

    # ---- access ----

    def list(self) -> List[EngineSpec]:
        return list(self._engines)

    def get(self, index: int) -> EngineSpec | None:
        try:
            return self._engines[int(index)]
        except Exception:
            return None

    def get_by_id(self, engine_id: str) -> EngineSpec | None:
        eid = str(engine_id or "").strip()
        if not eid:
            return None
        for e in self._engines:
            if e.id == eid:
                return e
        return None

    def index_of_id(self, engine_id: str) -> int:
        eid = str(engine_id or "").strip()
        for i, e in enumerate(self._engines):
            if e.id == eid:
                return i
        return -1

    # ---- mutations ----

    def set_api_key(self, index: int, api_key: str) -> None:
        eng = self.get(index)
        if not eng or eng.is_yandex():
            return
        eng.api_key = (api_key or "").strip()

    def set_api_key_by_id(self, engine_id: str, api_key: str) -> None:
        eng = self.get_by_id(engine_id)
        if not eng or eng.is_yandex():
            return
        eng.api_key = (api_key or "").strip()

    def add_custom(
        self,
        *,
        name: str,
        kind: str = "openai_compat",
        provider: str,
        models: Sequence[str],
        extra: Optional[Dict[str, Any]] = None,
    ) -> int:
        name = (name or "").strip()
        kind_n = _norm_kind(kind)
        provider = (provider or "").strip()
        models_n = self._normalize_models(models)
        extra_n = _ensure_dict(extra)

        if not name:
            raise ValueError("name is empty")

        _validate_custom(kind_n, provider, models_n)

        self._engines.append(
            EngineSpec(
                id=_new_id(),
                name=name,
                kind=kind_n,
                provider=provider,
                models=models_n,
                api_key="",
                extra=extra_n,
                builtin=False,
            )
        )
        return len(self._engines) - 1

    def edit_custom(
        self,
        index: int,
        *,
        name: str,
        kind: str = "openai_compat",
        provider: str,
        models: Sequence[str],
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        eng = self.get(index)
        if not eng or not eng.is_editable():
            raise ValueError("engine is not editable")

        name = (name or "").strip()
        kind_n = _norm_kind(kind)
        provider = (provider or "").strip()
        models_n = self._normalize_models(models)
        extra_n = _ensure_dict(extra)

        if not name:
            raise ValueError("name is empty")

        _validate_custom(kind_n, provider, models_n)

        eng.name = name
        eng.kind = kind_n
        eng.provider = provider
        eng.models = models_n
        eng.extra = extra_n

    def remove_custom(self, index: int) -> None:
        eng = self.get(index)
        if not eng or eng.builtin:
            raise ValueError("engine is not removable")
        del self._engines[int(index)]

    # ---- serialization for ini_mixin ----

    def export_custom_payload(self) -> List[dict]:
        out: List[dict] = []
        for e in self._engines:
            if e.builtin or e.is_yandex():
                continue
            out.append(
                {
                    "id": e.id,
                    "name": e.name,
                    "kind": e.kind,
                    "provider": e.provider,
                    "models": [self._model_id(m) for m in (e.models or []) if self._model_id(m)],
                    "api_key": e.api_key,
                    "extra": dict(e.extra or {}),
                }
            )
        return out

    @staticmethod
    def _model_id(m: ModelSpec) -> str:
        if isinstance(m, (list, tuple)) and len(m) >= 2:
            return str(m[1]).strip()
        return str(m).strip()

    @staticmethod
    def _normalize_models(models: Sequence[str] | str | None) -> List[str]:
        if models is None:
            return []
        if isinstance(models, str):
            models = [models]
        out: List[str] = []
        for m in (models or []):
            s = str(m).strip()
            if s:
                out.append(s)
        return out

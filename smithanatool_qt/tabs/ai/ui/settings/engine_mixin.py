from __future__ import annotations

import json

from PySide6.QtWidgets import QMessageBox, QDialog

from smithanatool_qt.tabs.ai.core.engine_manager import EngineManager
from smithanatool_qt.tabs.ai.core.models import EngineSpec
from .custom_engine_dialog import CustomEngineDialog
from smithanatool_qt.tabs.ai.core.capabilities import capabilities_for_engine_kind


class AiSettingsEngineMixin:
    """UI-контроллер движков для блока "Настройки". INI read/write — через AiSettingsIniMixin."""

    def _apply_engine_manager(self, mgr: EngineManager) -> None:
        """Применить готовый EngineManager к UI (GUI-поток)."""
        self._engine_mgr = mgr
        self._rebuild_engine_combo()

        # ВАЖНО: предпочитаем engine_id вместо engine_idx
        saved_id = str(self._get_ini("engine_id", "", typ=str) or "").strip()
        if saved_id:
            idx_by_id = self._index_by_engine_id(saved_id)
            if idx_by_id >= 0:
                self.cmb_engine.setCurrentIndex(idx_by_id)
            else:
                self._restore_engine_idx_fallback()
        else:
            self._restore_engine_idx_fallback()

        # миграция: если был выбран по idx — сохраним engine_id
        try:
            cur = self._current_engine()
            if cur is not None:
                self._save_ini("engine_id", cur.id)
        except Exception:
            pass

        self._last_engine_id = ""
        self._on_engine_changed()

    def _init_engines(self) -> None:
        gemini_key = (self._get_ini("gemini_api_key", "", typ=str) or "").strip()
        try:
            custom = self._load_custom_engines()
        except Exception:
            custom = []

        mgr = EngineManager.from_sources(custom_engines=custom, gemini_api_key=gemini_key)
        self._apply_engine_manager(mgr)


    def _restore_engine_idx_fallback(self) -> None:
        saved_idx = self._get_ini("engine_idx", 0, typ=int)
        try:
            saved_idx = int(saved_idx)
        except Exception:
            saved_idx = 0
        if saved_idx < 0 or saved_idx >= self.cmb_engine.count():
            saved_idx = 0
        self.cmb_engine.setCurrentIndex(saved_idx)

    def _wire_engine_signals(self) -> None:
        self.cmb_engine.currentIndexChanged.connect(self._on_engine_changed)
        self.ed_api_key.editingFinished.connect(self._on_api_key_changed)

    # ---- helpers ----

    def _engine_at(self, index: int) -> EngineSpec | None:
        mgr = getattr(self, "_engine_mgr", None)
        if not isinstance(mgr, EngineManager):
            return None
        return mgr.get(index)

    def _engine_by_id(self, engine_id: str) -> EngineSpec | None:
        mgr = getattr(self, "_engine_mgr", None)
        if not isinstance(mgr, EngineManager):
            return None
        return mgr.get_by_id(engine_id)

    def _index_by_engine_id(self, engine_id: str) -> int:
        mgr = getattr(self, "_engine_mgr", None)
        if not isinstance(mgr, EngineManager):
            return -1
        return mgr.index_of_id(engine_id)

    def _current_engine(self) -> EngineSpec | None:
        return self._engine_at(int(self.cmb_engine.currentIndex()))

    def _rebuild_engine_combo(self) -> None:
        self.cmb_engine.blockSignals(True)
        try:
            self.cmb_engine.clear()
            for eng in self._engine_mgr.list():
                # itemData будет доступен через currentData()
                self.cmb_engine.addItem(
                    eng.name,
                    {
                        "id": eng.id,
                        "name": eng.name,
                        "kind": eng.kind,
                        "provider": eng.provider,
                        "extra": dict(eng.extra or {}),
                        "builtin": eng.builtin,
                    },
                )
        finally:
            self.cmb_engine.blockSignals(False)

    def _update_models_combo(self, eng: EngineSpec) -> None:
        self.cmb_model.blockSignals(True)
        try:
            self.cmb_model.clear()
            for m in (eng.models or []):
                if isinstance(m, (list, tuple)) and len(m) >= 2:
                    title, mid = str(m[0]), str(m[1])
                else:
                    title, mid = str(m), str(m)
                self.cmb_model.addItem(title, mid)
        finally:
            self.cmb_model.blockSignals(False)

    def _refresh_engine_ui(self) -> None:
        eng = self._current_engine()
        kind = (eng.kind if eng is not None else "openai_compat")
        caps = capabilities_for_engine_kind(kind)

        self.lbl_gemini_api_key.setVisible(caps.show_llm_fields)
        self.ed_api_key.setVisible(caps.show_llm_fields)
        self.lbl_gemini_model.setVisible(caps.show_llm_fields)
        self.cmb_model.setVisible(caps.show_llm_fields)
        self.lbl_batch.setVisible(caps.show_llm_fields)
        self.spn_batch.setVisible(caps.show_llm_fields)
        self.lbl_batch_hint.setVisible(caps.show_llm_fields)

        self.lbl_text_lang.setVisible(True)
        self.cmb_lang.setVisible(True)

        self.lbl_yc_api_key.setVisible(caps.show_yandex_fields)
        self.ed_yc_api_key.setVisible(caps.show_yandex_fields)
        self.lbl_yc_folder_id.setVisible(caps.show_yandex_fields)
        self.ed_yc_folder_id.setVisible(caps.show_yandex_fields)

        if caps.show_llm_fields and eng is not None:
            self._update_models_combo(eng)

    def _persist_custom_engines(self) -> None:
        try:
            self._save_custom_engines(self._engine_mgr.export_custom_payload())
        except Exception:
            pass

    # ---- save/load api key on switching ----

    def _save_prev_engine_api_key(self) -> None:
        prev_id = str(getattr(self, "_last_engine_id", "") or "").strip()
        if not prev_id:
            return

        eng = self._engine_by_id(prev_id)
        if not eng or eng.is_yandex():
            return

        key = (self.ed_api_key.text() or "").strip()
        self._engine_mgr.set_api_key_by_id(prev_id, key)

        if eng.builtin:
            if eng.kind == "openai_compat":
                self._save_ini("gemini_api_key", key)
            else:
                self._save_ini(f"builtin_api_key__{eng.kind}", key)
        else:
            self._persist_custom_engines()

    def _load_current_engine_api_key(self) -> None:
        eng = self._current_engine()
        if not eng or eng.is_yandex():
            return
        self.ed_api_key.blockSignals(True)
        try:
            self.ed_api_key.setText((eng.api_key or "").strip())
        finally:
            self.ed_api_key.blockSignals(False)

    # ---- slots ----

    def _on_engine_changed(self, _i: int = 0) -> None:
        self._save_prev_engine_api_key()

        cur = self._current_engine()

        # сохраняем только engine_id (idx оставляем только как fallback для чтения)
        if cur is not None:
            self._save_ini("engine_id", cur.id)
            self._last_engine_id = cur.id
        else:
            self._last_engine_id = ""

        # подгружаем ключ и обновляем UI
        if cur is not None and not cur.is_yandex():
            self._load_current_engine_api_key()
        self._refresh_engine_ui()

        # восстановить модель (после обновления списка моделей)
        # новый формат: model_id (itemData), fallback: model_idx
        model_id = str(self._get_ini("model_id", "", typ=str) or "").strip()
        if model_id:
            ok = self._set_combo_by_data(self.cmb_model, model_id)
            if not ok and self.cmb_model.count() > 0:
                self.cmb_model.setCurrentIndex(0)
        else:
            try:
                model_idx = int(self._get_ini("model_idx", 0, typ=int))
            except Exception:
                model_idx = 0
            if 0 <= model_idx < self.cmb_model.count():
                self.cmb_model.setCurrentIndex(model_idx)
            elif self.cmb_model.count() > 0:
                self.cmb_model.setCurrentIndex(0)

        # миграция: если выставили индексом — сохраним model_id
        try:
            cur_model_id = str(self.cmb_model.currentData() or "").strip()
            if cur_model_id:
                self._save_ini("model_id", cur_model_id)
        except Exception:
            pass

    def _on_api_key_changed(self) -> None:
        eng = self._current_engine()
        if not eng or eng.is_yandex():
            return

        idx = int(self.cmb_engine.currentIndex())
        key = (self.ed_api_key.text() or "").strip()
        self._engine_mgr.set_api_key(idx, key)

        if eng.builtin:
            if eng.kind == "openai_compat":
                self._save_ini("gemini_api_key", key)
            else:
                self._save_ini(f"builtin_api_key__{eng.kind}", key)
        else:
            self._persist_custom_engines()

    # ---- CRUD ----

    @staticmethod
    def _parse_extra_json(raw: str) -> dict:
        s = (raw or "").strip()
        if not s:
            return {}
        try:
            j = json.loads(s)
        except Exception as e:
            raise ValueError(f"Extra JSON некорректный: {e}")
        if not isinstance(j, dict):
            raise ValueError("Extra JSON должен быть объектом { ... }")
        return j

    def _on_add_engine(self) -> None:
        dlg = CustomEngineDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.get_value()

        try:
            extra = self._parse_extra_json(data.get("extra") or "")
            new_idx = self._engine_mgr.add_custom(
                name=(data.get("name") or "").strip(),
                kind=(data.get("kind") or "openai_compat").strip(),
                provider=(data.get("provider") or "").strip(),
                models=data.get("models") or [],
                extra=extra,
            )
        except ValueError as e:
            QMessageBox.warning(self, "Добавить движок", str(e))
            return

        self._persist_custom_engines()
        self._rebuild_engine_combo()
        self.cmb_engine.setCurrentIndex(new_idx)
        self._on_engine_changed()

    def _on_remove_engine(self) -> None:
        idx = int(self.cmb_engine.currentIndex())
        eng = self._engine_at(idx)
        if not eng:
            return
        if eng.builtin:
            QMessageBox.information(self, "Удалить движок", "Встроенный движок нельзя удалить.")
            return

        res = QMessageBox.question(
            self,
            "Удалить движок",
            f"Точно удалить движок «{eng.name or 'движок'}»?\n\nЭто действие нельзя отменить.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if res != QMessageBox.Yes:
            return

        # на время операции сбросим last-id, чтобы ничего не "перетекло" при перестройке UI
        self._last_engine_id = ""

        try:
            self._engine_mgr.remove_custom(idx)
        except Exception:
            return

        self._persist_custom_engines()
        self._rebuild_engine_combo()

        if self.cmb_engine.count() > 0:
            self.cmb_engine.setCurrentIndex(max(0, min(idx, self.cmb_engine.count() - 1)))
        self._on_engine_changed()

    def _on_edit_engine(self) -> None:
        idx = int(self.cmb_engine.currentIndex())
        eng = self._engine_at(idx)
        if not eng:
            return
        if not eng.is_editable():
            QMessageBox.information(self, "Редактировать движок", "Встроенный движок нельзя редактировать.")
            return

        initial = {
            "name": eng.name,
            "kind": eng.kind,
            "provider": eng.provider,
            "models": [
                m[1] if isinstance(m, (list, tuple)) and len(m) >= 2 else str(m)
                for m in (eng.models or [])
            ],
            "extra": dict(eng.extra or {}),
        }

        dlg = CustomEngineDialog(self, title="Редактировать движок", initial=initial)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        data = dlg.get_value()
        try:
            extra = self._parse_extra_json(data.get("extra") or "")
            self._engine_mgr.edit_custom(
                idx,
                name=(data.get("name") or "").strip(),
                kind=(data.get("kind") or "openai_compat").strip(),
                provider=(data.get("provider") or "").strip(),
                models=data.get("models") or [],
                extra=extra,
            )
        except ValueError as e:
            QMessageBox.warning(self, "Редактировать движок", str(e))
            return

        self._persist_custom_engines()
        self._rebuild_engine_combo()
        self.cmb_engine.setCurrentIndex(idx)
        self._on_engine_changed()

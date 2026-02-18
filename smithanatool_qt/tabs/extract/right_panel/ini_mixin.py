from __future__ import annotations

from smithanatool_qt.settings_bind import group, get_value, set_value


class RightPanelIniMixin:
    """INI persistence для правой панели (engine/model/lang/keys/etc.)."""

    INI_GROUP = "ExtractRightPanel"

    def _set_combo_by_data(self, combo, data_value: str) -> bool:
        """Выбрать элемент QComboBox по itemData(). Возвращает True если найдено."""
        if data_value is None:
            return False
        target = str(data_value).strip()
        for i in range(combo.count()):
            if str(combo.itemData(i) or "") == target:
                combo.setCurrentIndex(i)
                return True
        return False

    def _restore_ini(self):
        try:
            with group(self.INI_GROUP):
                m = get_value("model_idx", 0, typ=int)
                l = get_value("lang_idx", 0, typ=int)
                z = get_value("zoom_ui_idx", 0, typ=int)
                t = get_value("thumbs", False, typ=bool)
                k = get_value("gemini_api_key", "", typ=str)
                bs = get_value("gemini_batch_size", 8, typ=int)
                e = get_value("engine_idx", 0, typ=int)
                yk = get_value("yc_api_key", "", typ=str)
                yf = get_value("yc_folder_id", "", typ=str)

                lc = get_value("lang_code", "", typ=str)

            self.cmb_model.setCurrentIndex(
                int(m) if isinstance(m, int) or str(m).isdigit() else 0
            )

            lang_code = (str(lc) if lc is not None else "").strip().lower()

            # алиасы на всякий случай (если где-то сохранено старое)
            if lang_code in ("korean",):
                lang_code = "ko"
            elif lang_code in ("japan", "jp", "jpn"):
                lang_code = "ja"
            elif lang_code == "auto":
                lang_code = ""

            if lang_code:
                ok = self._set_combo_by_data(self.cmb_lang, lang_code)
                if not ok:
                    self.cmb_lang.setCurrentIndex(0)  # fallback на auto
            else:
                # Старый формат: lang_idx (миграция)
                self.cmb_lang.setCurrentIndex(
                    int(l) if isinstance(l, int) or str(l).isdigit() else 0
                )
                # Сразу мигрируем в lang_code
                try:
                    migrated = str(self.cmb_lang.currentData() or "").strip()
                    with group(self.INI_GROUP):
                        set_value("lang_code", migrated)
                except Exception:
                    pass

            self.cmb_zoom_ui.setCurrentIndex(
                int(z) if isinstance(z, int) or str(z).isdigit() else 0
            )
            self.chk_thumbs.setChecked(bool(t))
            self.ed_api_key.setText(str(k) if k is not None else "")
            try:
                self.spn_gemini_batch.setValue(int(bs) if bs is not None else 4)
            except Exception:
                self.spn_gemini_batch.setValue(4)
            self.cmb_engine.setCurrentIndex(
                int(e) if isinstance(e, int) or str(e).isdigit() else 0
            )
            self.ed_yc_api_key.setText(str(yk) if yk is not None else "")
            self.ed_yc_folder_id.setText(str(yf) if yf is not None else "")
        except Exception:
            # если INI ещё не создан или формат не тот — не падаем
            pass

    def _wire_persistence(self):
        self.cmb_engine.currentIndexChanged.connect(
            lambda i: self._save_ini("engine_idx", int(i))
        )
        self.ed_api_key.editingFinished.connect(
            lambda: self._save_ini("gemini_api_key", self.ed_api_key.text().strip())
        )
        self.spn_gemini_batch.valueChanged.connect(
            lambda v: self._save_ini("gemini_batch_size", int(v))
        )
        self.ed_yc_api_key.editingFinished.connect(
            lambda: self._save_ini("yc_api_key", self.ed_yc_api_key.text().strip())
        )
        self.ed_yc_folder_id.editingFinished.connect(
            lambda: self._save_ini("yc_folder_id", self.ed_yc_folder_id.text().strip())
        )
        self.cmb_model.currentIndexChanged.connect(
            lambda i: self._save_ini("model_idx", int(i))
        )
        self.cmb_lang.currentIndexChanged.connect(
            lambda i: self._save_ini("lang_code", str(self.cmb_lang.itemData(i) or ""))
        )
        self.cmb_zoom_ui.currentIndexChanged.connect(
            lambda i: self._save_ini("zoom_ui_idx", int(i))
        )
        self.chk_thumbs.toggled.connect(lambda v: self._save_ini("thumbs", bool(v)))

    def _save_ini(self, key: str, val):
        try:
            with group(self.INI_GROUP):
                set_value(key, val)
        except Exception:
            pass

    def _get_ini_bool(self, key: str, default: bool = False) -> bool:
        try:
            with group(self.INI_GROUP):
                return bool(get_value(key, default, typ=bool))
        except Exception:
            return default

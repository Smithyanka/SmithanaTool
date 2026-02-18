class UndoMixin:
        def _push_undo(self):
            if not (self._current_path and self._current_path in self._images):
                return
            st = self._undo.setdefault(self._current_path, [])
            # новая операция — чистим redo
            self._redo[self._current_path] = []
            st.append(self._images[self._current_path].copy())
    
        def _snap_selection_to_edges(self, h: int, y1: int, y2: int) -> tuple[int, int]:
            # clamp
            y1 = max(0, min(h, y1))
            y2 = max(0, min(h, y2))
            if y1 > y2:
                y1, y2 = y2, y1
            # snap к краям, чтобы не оставался 1px
            if y1 <= 1:
                y1 = 0
            if y2 >= h - 1:
                y2 = h
            return y1, y2
    
    
        def _undo_last(self):
            if not (self._current_path and self._current_path in self._images):
                return
            st = self._undo.get(self._current_path, [])
            if not st:
                return
            cur = self._images[self._current_path].copy()
            rd = self._redo.setdefault(self._current_path, [])
            rd.append(cur)
            prev = st.pop()
            self._images[self._current_path] = prev
            self._recalc_dirty_vs_disk()
            self._update_preview_pixmap()
            self._update_actions_enabled()
    
    
        def _redo_last(self):
            if not (self._current_path and self._current_path in self._images):
                return
            rd = self._redo.get(self._current_path, [])
            if not rd:
                return
            st = self._undo.setdefault(self._current_path, [])
            st.append(self._images[self._current_path].copy())
            nxt = rd.pop()
            self._images[self._current_path] = nxt
            self._recalc_dirty_vs_disk()
            self._update_preview_pixmap()
            self._update_actions_enabled()
    
    
        def _update_actions_enabled(self):
            has_img = self._current_path in self._images if self._current_path else False
            is_psd = self._is_current_psd()
            self.btn_cut.setEnabled(has_img and self._has_selection())
            self.btn_paste_top.setEnabled(has_img and bool(self._clip))
            self.btn_paste_bottom.setEnabled(has_img and bool(self._clip))
            self.btn_undo.setEnabled(has_img and bool(self._undo.get(self._current_path, [])))
            self.btn_redo.setEnabled(has_img and bool(self._redo.get(self._current_path, [])))
            # Сохранение недоступно для PSD
            save_ok = has_img and not is_psd
            self.btn_save.setEnabled(save_ok)
            self.btn_save_as.setEnabled(save_ok)

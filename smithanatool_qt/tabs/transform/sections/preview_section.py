
from __future__ import annotations
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QDoubleSpinBox, QSpinBox, QPushButton, QCheckBox, QComboBox
from PySide6.QtCore import Qt, Signal, QRect, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QLinearGradient, QPolygon

from smithanatool_qt.settings_bind import group, bind_checkbox, get_value, set_value

class LevelsWidget(QWidget):
    changed = Signal(int, float, int)  # black, gamma, white

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(56)
        self._black = 0
        self._white = 255
        self._gamma = 1.0
        self._drag = None  # 'b' | 'g' | 'w' | None

    def values(self):
        return self._black, self._gamma, self._white

    def setValues(self, b: int, g: float, w: int):
        b = max(0, min(254, int(b)))
        w = max(1, min(255, int(w)))
        if w <= b:
            if b >= 254:
                b, w = 254, 255
            else:
                w = b + 1
        g = max(0.10, min(5.00, float(g)))
        changed = (b != self._black) or (abs(g - self._gamma) > 1e-6) or (w != self._white)
        self._black, self._gamma, self._white = b, g, w
        if changed:
            self.changed.emit(self._black, self._gamma, self._white)
            self.update()

    # ---- отрисовка ----
    def _bar_rect(self):
        m = 12
        h = 18
        y = (self.height() - h)//2
        return QRect(m, y, self.width() - 2*m, h)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)

        r = self._bar_rect()
        # фон
        p.fillRect(self.rect(), self.palette().base())

        # градиент от чёрного к белому в пределах бара
        grad = QLinearGradient(r.left(), r.top(), r.right(), r.top())
        grad.setColorAt(0.0, QColor(0,0,0))
        grad.setColorAt(1.0, QColor(255,255,255))
        p.fillRect(r, QBrush(grad))
        p.setPen(QPen(QColor(110,110,110)))
        p.drawRect(r)

        # позиции маркеров
        xb = r.left() + int(self._black / 255.0 * r.width())
        xw = r.left() + int(self._white / 255.0 * r.width())
        # позиция гаммы в долях между b..w
        rel = max(1, self._white - self._black)
        p_rel = (0.5 ** (1.0 / float(self._gamma)))  # 0..1
        xg_val = self._black + p_rel * rel
        xg = r.left() + int((xg_val / 255.0) * r.width())

        # левый (чёрный) — вверх
        p.setBrush(QColor(20,20,20))
        p.setPen(QPen(QColor(20,20,20)))
        pb = QPolygon([
            QPoint(xb-6, r.bottom()+1),
            QPoint(xb+6, r.bottom()+1),
            QPoint(xb, r.bottom()-7),
        ])
        p.drawPolygon(pb)

        # правый (белый) — вверх
        p.setBrush(QColor(230,230,230))
        p.setPen(QPen(QColor(230,230,230)))
        pw = QPolygon([
            QPoint(xw-6, r.bottom()+1),
            QPoint(xw+6, r.bottom()+1),
            QPoint(xw, r.bottom()-7),
        ])
        p.drawPolygon(pw)

        # средний (гамма) — вниз
        p.setBrush(QColor(100,100,100))
        p.setPen(QPen(QColor(100,100,100)))
        pg = QPolygon([
            QPoint(xg-6, r.top()-1),
            QPoint(xg+6, r.top()-1),
            QPoint(xg, r.top()+7),
        ])
        p.drawPolygon(pg)

    # ---- взаимодействие ----
    def _nearest_handle(self, x):
        r = self._bar_rect()
        xb = r.left() + int(self._black / 255.0 * r.width())
        xw = r.left() + int(self._white / 255.0 * r.width())

        # текущая позиция гаммы
        rel = max(1, self._white - self._black)
        p_rel = (0.5 ** (1.0 / float(self._gamma)))
        xg_val = self._black + p_rel * rel
        xg = r.left() + int((xg_val / 255.0) * r.width())

        d = [(abs(x - xb), 'b'), (abs(x - xg), 'g'), (abs(x - xw), 'w')]
        d.sort(key=lambda t: t[0])
        return d[0][1] if d[0][0] <= 12 else None

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton: 
            return super().mousePressEvent(e)
        self._drag = self._nearest_handle(e.position().toPoint().x())
        if self._drag:
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag is None:
            return super().mouseMoveEvent(e)
        r = self._bar_rect()
        x = int(e.position().toPoint().x())
        x = max(r.left(), min(r.right(), x))
        # преобразуем x -> значение 0..255
        val = int(round((x - r.left()) / max(1, r.width()) * 255))

        b, g, w = self._black, self._gamma, self._white
        if self._drag == 'b':
            b = min(val, w-1)
        elif self._drag == 'w':
            w = max(val, b+1)
        elif self._drag == 'g':
            # позиция в долях между b..w
            rel = max(1, w - b)
            u = (val - b) / float(rel)
            u = min(max(u, 0.01), 0.99)
            # gamma = ln(0.5) / ln(u)  -> чтобы при u=0.5 gamma=1
            import math
            g = math.log(0.5) / math.log(u)

        self.setValues(b, g, w)

    def mouseReleaseEvent(self, e):
        if self._drag:
            self.unsetCursor()
            self._drag = None
        super().mouseReleaseEvent(e)


class PreviewSection(QWidget):
    def __init__(self, preview, parent=None):
        super().__init__(parent)
        self._preview = preview

        v = QVBoxLayout(self)
        row_mode = QHBoxLayout();
        row_mode.setSpacing(8)
        self.chk_edit_mode = QCheckBox("Режим вырезки и вставки")
        row_mode.addWidget(self.chk_edit_mode)
        row_mode.addStretch(1)
        v.addLayout(row_mode)

        # ── Комбобокс: расположение кнопок масштаба
        row_zoomui = QHBoxLayout();
        row_zoomui.setSpacing(8)
        lbl_zoomui = QLabel("Кнопки масштаба:")
        cmb_zoomui = QComboBox()
        cmb_zoomui.addItems([
            "Классический",  # index 0
            "Компактный"  # index 1
        ])
        row_zoomui.addWidget(lbl_zoomui)
        row_zoomui.addWidget(cmb_zoomui)
        row_zoomui.addStretch(1)
        v.addLayout(row_zoomui)

        bind_checkbox(self.chk_edit_mode, "PreviewSection/edit_mode", True)

        def _bind_combo_index(combo: QComboBox, key: str, default: int, on_apply=None):
            # Подтягивание из ini
            try:
                with group("PreviewSection"):
                    val = int(get_value(key, default))
            except Exception:
                val = default
            combo.blockSignals(True)
            combo.setCurrentIndex(0 if val not in (0, 1) else val)
            combo.blockSignals(False)
            if callable(on_apply):
                try:
                    on_apply(combo.currentIndex())
                except Exception:
                    pass

            # Сохранение в ini + применение при изменении
            def _save(idx: int):
                try:
                    with group("PreviewSection"):
                        set_value(key, int(idx))
                except Exception:
                    pass
                if callable(on_apply):
                    try:
                        on_apply(int(idx))
                    except Exception:
                        pass

            combo.currentIndexChanged.connect(_save)

        # применяем «как у чекбокса»: ini → UI → превью
        _bind_combo_index(
            cmb_zoomui,
            "zoom_ui_mode",
            0,
            on_apply=lambda idx: (
                self._preview.set_zoom_ui_mode(int(idx))
                if (self._preview is not None and hasattr(self._preview, "set_zoom_ui_mode"))
                else None
            )
        )

        def _apply_edit_mode(on: bool):
            try:
                if self._preview is not None and hasattr(self._preview, "set_cut_paste_mode_enabled"):
                    self._preview.set_cut_paste_mode_enabled(bool(on))
            except Exception:
                pass

        self.chk_edit_mode.toggled.connect(_apply_edit_mode)
        _apply_edit_mode(self.chk_edit_mode.isChecked())



        v.addSpacing(12)
        bind_checkbox(self.chk_edit_mode, "PreviewSection/edit_mode", True)

        # Ползунок уровней
        self.levels = LevelsWidget()
        v.addWidget(self.levels)

        # Поля: 0, 1.00, 255
        row = QHBoxLayout(); row.setSpacing(8)
        self.lbl_b = QLabel("Чёрная:"); self.sb_b = QSpinBox(); self.sb_b.setRange(0,254); self.sb_b.setValue(0)
        self.lbl_g = QLabel("Середина:"); self.sb_g = QDoubleSpinBox(); self.sb_g.setDecimals(2); self.sb_g.setRange(0.10,5.00); self.sb_g.setSingleStep(0.01); self.sb_g.setValue(1.00)
        self.lbl_w = QLabel("Белая:"); self.sb_w = QSpinBox(); self.sb_w.setRange(1,255); self.sb_w.setValue(255)
        row.addWidget(self.lbl_b); row.addWidget(self.sb_b); 
        row.addSpacing(12)
        row.addWidget(self.lbl_g); row.addWidget(self.sb_g);
        row.addSpacing(12)
        row.addWidget(self.lbl_w); row.addWidget(self.sb_w);
        row.addStretch(1)
        v.addLayout(row)

        # "Сбросить" — справа
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        self.btn_reset = QPushButton("Сбросить")
        self.btn_reset.setToolTip("Вернуть уровни: 0 / 1.00 / 255")
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_reset)  # прижим к правому краю
        v.addLayout(btn_row)
        self.btn_reset.clicked.connect(self._on_reset_clicked)

        # связка чекбокса с превью
        def _apply_edit_mode(on: bool):
            try:
                if self._preview is not None and hasattr(self._preview, "set_cut_paste_mode_enabled"):
                    self._preview.set_cut_paste_mode_enabled(bool(on))
            except Exception:
                pass

        self.chk_edit_mode.toggled.connect(_apply_edit_mode)
        _apply_edit_mode(self.chk_edit_mode.isChecked())

        # Синхронизация
        def _push_to_preview(b, g, w):
            try:
                if self._preview is not None and hasattr(self._preview, 'set_levels_preview'):
                    self._preview.set_levels_preview(b, g, w)
            except Exception:
                pass

        def _lvl_changed(b, g, w):
            # обновить поля
            try:
                self.sb_b.blockSignals(True); self.sb_w.blockSignals(True); self.sb_g.blockSignals(True)
                self.sb_b.setValue(int(b)); self.sb_w.setValue(int(w)); self.sb_g.setValue(float(g))
            finally:
                self.sb_b.blockSignals(False); self.sb_w.blockSignals(False); self.sb_g.blockSignals(False)
            _push_to_preview(b, g, w)

        self.levels.changed.connect(_lvl_changed)

        def _spin_changed():
            b = int(self.sb_b.value()); g = float(self.sb_g.value()); w = int(self.sb_w.value())
            self.levels.setValues(b, g, w)
            _push_to_preview(b, g, w)

        self.sb_b.valueChanged.connect(lambda _: _spin_changed())
        self.sb_w.valueChanged.connect(lambda _: _spin_changed())
        self.sb_g.valueChanged.connect(lambda _: _spin_changed())

        # начальное состояние
        self.levels.setValues(0, 1.00, 255)

    def _on_reset_clicked(self):
        # Сброс на дефолтные значения
        self.levels.setValues(0, 1.00, 255)
        try:
            if self._preview is not None and hasattr(self._preview, 'reset_levels_preview'):
                self._preview.reset_levels_preview()
        except Exception:
            pass

# -*- coding: utf-8 -*-
"""
SuperPicky - 结果浏览器左侧过滤面板
FilterPanel: 鸟种 / 评分 / 对焦状态 / 飞行状态 筛选
（曝光筛选已移除）
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QCheckBox, QComboBox, QScrollArea, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from ui.styles import COLORS, FONTS


# 评分按钮的配置 (rating_value, 显示文字, 颜色)
_RATING_CONFIGS = [
    (5,  "★★★★★", "#FFD700"),
    (4,  "★★★★",  "#E8C000"),
    (3,  "★★★",   COLORS['star_gold']),
    (2,  "★★",    COLORS['star_gold']),
    (1,  "★",     COLORS['star_gold']),
    (0,  "0",     COLORS['text_tertiary']),
]

# 对焦状态颜色（与缩略图圆点一致）
_FOCUS_COLORS = {
    "BEST":  COLORS['focus_best'],    # 绿 — 精焦
    "GOOD":  COLORS['focus_good'],    # 琥珀 — 合焦
    "BAD":   COLORS['focus_bad'],     # 近白灰 — 失焦
    "WORST": COLORS['focus_worst'],   # 灰 — 脱焦
}

# 默认勾选的评分（★★★ 和 ★★）
_DEFAULT_CHECKED_RATINGS = {3, 2}

# 默认勾选的对焦状态（BEST 和 GOOD）
_DEFAULT_CHECKED_FOCUS = {"BEST", "GOOD"}


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"""
        QLabel {{
            color: {COLORS['text_tertiary']};
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 1px;
            background: transparent;
        }}
    """)
    return lbl


class FilterPanel(QWidget):
    """
    左侧筛选面板。

    发出信号 filters_changed(dict) 通知外部刷新图片网格。
    """
    filters_changed = Signal(dict)

    def __init__(self, i18n, parent=None):
        super().__init__(parent)
        self.i18n = i18n
        self._rating_counts: dict = {}      # {rating: count}
        self._species_list: list = []        # 鸟种列表

        from advanced_config import get_advanced_config
        self._adv_config = get_advanced_config()

        self.setFixedWidth(220)
        self.setStyleSheet(f"background-color: {COLORS['bg_elevated']}; border-right: 1px solid {COLORS['border_subtle']};")

        self._build_ui()

    # ------------------------------------------------------------------
    #  UI 构建
    # ------------------------------------------------------------------

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 内部可滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        container.setStyleSheet(f"background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(20)

        # --- 鸟种（置顶）---
        layout.addWidget(_section_label(self.i18n.t("browser.section_species")))
        self.species_combo = QComboBox()
        self.species_combo.addItem(self.i18n.t("browser.species_all"), "")
        self.species_combo.currentIndexChanged.connect(self._emit_filters)
        layout.addWidget(self.species_combo)

        layout.addWidget(self._divider())

        # --- 评分筛选 ---
        layout.addWidget(_section_label(self.i18n.t("browser.filter_rating")))
        rating_widget = self._build_rating_buttons()
        layout.addWidget(rating_widget)

        layout.addWidget(self._divider())

        # --- 对焦状态（2×2 网格）---
        layout.addWidget(_section_label(self.i18n.t("browser.section_focus")))
        focus_widget = self._build_focus_checkboxes()
        layout.addWidget(focus_widget)

        layout.addWidget(self._divider())

        # --- 飞行状态（checkbox 模式，2 列）---
        layout.addWidget(_section_label(self.i18n.t("browser.section_flight")))
        flight_widget = self._build_flight_checkboxes()
        layout.addWidget(flight_widget)

        layout.addWidget(self._divider())

        # --- 排序方式 ---
        layout.addWidget(_section_label(self.i18n.t("browser.section_sort")))
        self._sort_combo = QComboBox()
        self._sort_combo.addItem(self.i18n.t("browser.sort_filename"), "filename")
        self._sort_combo.addItem(self.i18n.t("browser.sort_sharpness"), "sharpness_desc")
        self._sort_combo.addItem(self.i18n.t("browser.sort_aesthetic"), "aesthetic_desc")
        # 恢复用户上次选择（默认锐度）
        saved_sort = self._adv_config.get_browser_sort()
        idx = self._sort_combo.findData(saved_sort)
        if idx >= 0:
            self._sort_combo.setCurrentIndex(idx)
        self._sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        layout.addWidget(self._sort_combo)

        layout.addStretch()

        # --- 重置按钮 ---
        reset_btn = QPushButton(self.i18n.t("browser.reset_filter"))
        reset_btn.setObjectName("secondary")
        reset_btn.clicked.connect(self.reset_all)
        layout.addWidget(reset_btn)

        scroll.setWidget(container)
        outer.addWidget(scroll)

    def _build_rating_buttons(self) -> QWidget:
        """构建评分多选按钮组（默认只选 3★ 和 2★）"""
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._rating_btns: dict = {}  # rating -> QPushButton

        for rating, label_text, color in _RATING_CONFIGS:
            btn = QPushButton(label_text)
            btn.setCheckable(True)
            checked = rating in _DEFAULT_CHECKED_RATINGS
            btn.setChecked(checked)
            btn.setProperty("rating", rating)
            btn.setStyleSheet(self._rating_btn_style(color, checked=checked))
            btn.toggled.connect(lambda checked, r=rating, c=color, b=btn:
                                self._on_rating_toggled(r, c, b, checked))
            self._rating_btns[rating] = btn
            layout.addWidget(btn)

        return w

    def _rating_btn_style(self, color: str, checked: bool) -> str:
        if checked:
            return f"""
                QPushButton {{
                    background-color: {COLORS['bg_card']};
                    border: 1px solid {color};
                    border-radius: 6px;
                    padding: 6px 12px;
                    color: {color};
                    font-size: 13px;
                    text-align: left;
                }}
                QPushButton:hover {{ background-color: {COLORS['bg_input']}; }}
            """
        else:
            return f"""
                QPushButton {{
                    background-color: transparent;
                    border: 1px solid {COLORS['border']};
                    border-radius: 6px;
                    padding: 6px 12px;
                    color: {COLORS['text_muted']};
                    font-size: 13px;
                    text-align: left;
                }}
                QPushButton:hover {{ background-color: {COLORS['bg_card']}; }}
            """

    def _build_focus_checkboxes(self) -> QWidget:
        """对焦状态：2×2 网格，默认 BEST 和 GOOD 选中"""
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        grid = QGridLayout(w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)

        self._focus_cbs: dict = {}  # status -> QCheckBox
        # 顺序：BEST(0,0) GOOD(0,1) BAD(1,0) WORST(1,1)
        items = [
            ("BEST",  0, 0),
            ("GOOD",  0, 1),
            ("BAD",   1, 0),
            ("WORST", 1, 1),
        ]

        for status, row, col in items:
            cb = QCheckBox(status)
            checked = status in _DEFAULT_CHECKED_FOCUS
            cb.setChecked(checked)
            color = _FOCUS_COLORS.get(status, COLORS['text_secondary'])
            cb.setStyleSheet(f"""
                QCheckBox {{ color: {color}; font-size: 12px; }}
                QCheckBox::indicator:checked {{ background-color: {color}; border-color: {color}; }}
            """)
            cb.stateChanged.connect(self._emit_filters)
            self._focus_cbs[status] = cb
            grid.addWidget(cb, row, col)

        return w

    def _build_flight_checkboxes(self) -> QWidget:
        """飞行状态：checkbox 模式（2 列），默认全选"""
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        grid = QGridLayout(w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)

        # (value, label, row, col)
        options = [
            (1, self.i18n.t("browser.flying_option"),      0, 0),
            (0, self.i18n.t("browser.non_flying_option"),  0, 1),
        ]

        self._flight_cbs: dict = {}  # value -> QCheckBox
        for value, label_text, row, col in options:
            cb = QCheckBox(label_text)
            cb.setChecked(True)  # 默认全选
            cb.setStyleSheet(f"QCheckBox {{ color: {COLORS['text_secondary']}; font-size: 12px; }}")
            cb.stateChanged.connect(self._emit_filters)
            self._flight_cbs[value] = cb
            grid.addWidget(cb, row, col)

        return w

    def _divider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"background-color: {COLORS['border_subtle']}; max-height: 1px; border: none;")
        return line

    # ------------------------------------------------------------------
    #  数据更新
    # ------------------------------------------------------------------

    def update_rating_counts(self, counts: dict):
        """更新各评分数量徽章。counts: {rating: count}"""
        self._rating_counts = counts
        label_map = {
            5: "★★★★★",
            4: "★★★★",
            3: "★★★",
            2: "★★",
            1: "★",
            0: "0",
            -1: self.i18n.t("browser.rating_nobird"),
        }
        for rating, btn in self._rating_btns.items():
            base = label_map.get(rating, str(rating))
            cnt = counts.get(rating, 0)
            btn.setText(f"{base}  {cnt}")

    def update_species_list(self, species: list):
        """更新鸟种下拉列表。"""
        self._species_list = species
        self.species_combo.blockSignals(True)
        current = self.species_combo.currentData()
        self.species_combo.clear()
        self.species_combo.addItem(self.i18n.t("browser.species_all"), "")
        for sp in species:
            self.species_combo.addItem(sp, sp)
        # 恢复之前的选择
        idx = self.species_combo.findData(current)
        if idx >= 0:
            self.species_combo.setCurrentIndex(idx)
        self.species_combo.blockSignals(False)

    # ------------------------------------------------------------------
    #  筛选状态读取
    # ------------------------------------------------------------------

    def get_filters(self) -> dict:
        """返回当前筛选条件字典。"""
        # 评分
        selected_ratings = [
            r for r, btn in self._rating_btns.items() if btn.isChecked()
        ]

        # 对焦
        selected_focus = [
            s for s, cb in self._focus_cbs.items() if cb.isChecked()
        ]

        # 飞行（list of selected values: [0], [1], [0,1]）
        is_flying = [
            v for v, cb in self._flight_cbs.items() if cb.isChecked()
        ]

        # 鸟种（根据当前语言决定用哪列过滤）
        bird_species = self.species_combo.currentData() or ""
        is_en = self.i18n.current_lang.startswith('en')
        species_key = "bird_species_en" if is_en else "bird_species_cn"

        sort_by = self._sort_combo.currentData() if hasattr(self, '_sort_combo') else "filename"

        return {
            "ratings":         selected_ratings,
            "focus_statuses":  selected_focus,
            "is_flying":       is_flying,
            species_key:       bird_species,
            "sort_by":         sort_by,
        }

    # ------------------------------------------------------------------
    #  重置
    # ------------------------------------------------------------------

    def reset_all(self):
        """重置筛选条件到默认值。"""
        # 评分：默认只选 3★ 和 2★
        for rating, btn in self._rating_btns.items():
            btn.blockSignals(True)
            btn.setChecked(rating in _DEFAULT_CHECKED_RATINGS)
            btn.blockSignals(False)

        # 对焦：默认只选 BEST 和 GOOD
        for status, cb in self._focus_cbs.items():
            cb.blockSignals(True)
            cb.setChecked(status in _DEFAULT_CHECKED_FOCUS)
            cb.blockSignals(False)

        # 飞行：默认全选
        for cb in self._flight_cbs.values():
            cb.blockSignals(True)
            cb.setChecked(True)
            cb.blockSignals(False)

        # 鸟种 -> 全部
        self.species_combo.blockSignals(True)
        self.species_combo.setCurrentIndex(0)
        self.species_combo.blockSignals(False)

        # 排序 -> 锐度（默认）
        self._sort_combo.blockSignals(True)
        idx = self._sort_combo.findData("sharpness_desc")
        self._sort_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._sort_combo.blockSignals(False)

        self._emit_filters()

    def select_all_ratings(self):
        """勾选全部评分（当默认筛选无结果时的回退）。"""
        for rating, btn in self._rating_btns.items():
            btn.blockSignals(True)
            btn.setChecked(True)
            btn.blockSignals(False)
        # 同时勾选全部对焦状态
        for cb in self._focus_cbs.values():
            cb.blockSignals(True)
            cb.setChecked(True)
            cb.blockSignals(False)
        self._emit_filters()

    # ------------------------------------------------------------------
    #  信号
    # ------------------------------------------------------------------

    def _on_rating_toggled(self, rating, color, btn, checked):
        btn.setStyleSheet(self._rating_btn_style(color, checked))
        self._emit_filters()

    def _on_sort_changed(self, *_):
        """排序改变时：保存用户偏好，再发出筛选信号。"""
        sort_val = self._sort_combo.currentData()
        if sort_val:
            self._adv_config.set_browser_sort(sort_val)
            self._adv_config.save()
        self._emit_filters()

    def _emit_filters(self, *_):
        self.filters_changed.emit(self.get_filters())

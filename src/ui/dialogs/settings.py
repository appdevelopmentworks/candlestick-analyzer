from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QLabel,
)

from analysis.patterns import available_pattern_functions
from domain.settings import AnalyzerUISettings


class SettingsDialog(QDialog):
    threshold_changed = Signal(int, int)

    def __init__(self, parent: QWidget | None = None, data: AnalyzerUISettings | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("設定")
        self.setModal(True)
        layout = QFormLayout(self)

        self.input_period = QSpinBox()
        self.input_period.setRange(30, 1000)
        self.input_period.setValue(data.period_days if data else 400)

        self.input_workers = QSpinBox()
        self.input_workers.setRange(1, 32)
        self.input_workers.setValue(data.parallel_workers if data else 5)

        self.input_high_pos = QSpinBox()
        self.input_high_pos.setRange(-5, 5)
        self.input_high_pos.setValue(data.highlight_pos if data else 4)
        self.input_high_pos.valueChanged.connect(self._emit_threshold_change)

        self.input_high_neg = QSpinBox()
        self.input_high_neg.setRange(-5, 5)
        self.input_high_neg.setValue(data.highlight_neg if data else -4)
        self.input_high_neg.valueChanged.connect(self._emit_threshold_change)

        self.input_history = QSpinBox()
        self.input_history.setRange(1, 120)
        self.input_history.setValue(data.history_lookback if data else 20)

        self.checkbox_auto_run = QCheckBox("CSV読み込み後に自動解析")
        if data:
            self.checkbox_auto_run.setChecked(data.auto_run)

        self.checkbox_all_patterns = QCheckBox("全てのパターンを有効化")
        self.pattern_filter = QLineEdit()
        self.pattern_filter.setPlaceholderText("パターン名でフィルタ")
        self.pattern_filter.textChanged.connect(self._apply_pattern_filter)

        self.pattern_list = QListWidget()
        self.pattern_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.pattern_list.setMinimumHeight(200)
        self.pattern_list.setAlternatingRowColors(True)
        self._populate_patterns(data.patterns if data else None)
        self.checkbox_all_patterns.toggled.connect(self._on_all_patterns_toggled)

        pattern_container = QWidget()
        pattern_layout = QVBoxLayout(pattern_container)
        pattern_layout.setContentsMargins(0, 0, 0, 0)
        pattern_layout.addWidget(self.checkbox_all_patterns)
        if self.pattern_list.count():
            pattern_layout.addWidget(self.pattern_filter)
            pattern_layout.addWidget(self.pattern_list)
        else:
            empty_label = QLabel("TA-Libのローソク足パターンが利用できません")
            empty_label.setWordWrap(True)
            pattern_layout.addWidget(empty_label)

        layout.addRow("取得期間(日)", self.input_period)
        layout.addRow("並列数", self.input_workers)
        layout.addRow("強気ハイライト閾値", self.input_high_pos)
        layout.addRow("弱気ハイライト閾値", self.input_high_neg)
        layout.addRow("ヒット履歴日数", self.input_history)
        layout.addRow(self.checkbox_auto_run)
        layout.addRow("ローソク足パターン", pattern_container)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def value(self) -> AnalyzerUISettings:
        return AnalyzerUISettings(
            period_days=self.input_period.value(),
            parallel_workers=self.input_workers.value(),
            highlight_pos=self.input_high_pos.value(),
            highlight_neg=self.input_high_neg.value(),
            history_lookback=self.input_history.value(),
            auto_run=self.checkbox_auto_run.isChecked(),
            patterns=self._selected_patterns(),
        )

    # -- 内部ヘルパー --------------------------------------------------
    def _populate_patterns(self, current: tuple[str, ...] | None) -> None:
        available = sorted(available_pattern_functions())
        if not available:
            self.pattern_list.setEnabled(False)
            self.pattern_filter.setEnabled(False)
            self.checkbox_all_patterns.setChecked(True)
            return
        selected = set(current or [])
        select_all = not current or len(selected) == 0
        self.checkbox_all_patterns.setChecked(select_all)
        for name in available:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            check = Qt.CheckState.Checked if select_all or name in selected else Qt.CheckState.Unchecked
            item.setCheckState(check)
            self.pattern_list.addItem(item)
        self.pattern_list.setEnabled(not select_all)
        self.pattern_filter.setEnabled(not select_all)

    def _on_all_patterns_toggled(self, checked: bool) -> None:
        self.pattern_list.setEnabled(not checked)
        self.pattern_filter.setEnabled(not checked)
        if checked:
            for index in range(self.pattern_list.count()):
                self.pattern_list.item(index).setCheckState(Qt.CheckState.Checked)

    def _apply_pattern_filter(self, text: str) -> None:
        keyword = text.strip().lower()
        for index in range(self.pattern_list.count()):
            item = self.pattern_list.item(index)
            if not keyword:
                item.setHidden(False)
            else:
                item.setHidden(keyword not in item.text().lower())

    def _selected_patterns(self) -> tuple[str, ...] | None:
        if self.checkbox_all_patterns.isChecked() or not self.pattern_list.isEnabled():
            return None
        selected = [
            self.pattern_list.item(index).text()
            for index in range(self.pattern_list.count())
            if self.pattern_list.item(index).checkState() == Qt.CheckState.Checked
        ]
        return tuple(sorted(selected)) if selected else None

    def _emit_threshold_change(self) -> None:
        self.threshold_changed.emit(self.input_high_pos.value(), self.input_high_neg.value())

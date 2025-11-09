from __future__ import annotations

from typing import Sequence, TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QClipboard
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:  # pragma: no cover - UI type hints only
    from ui.viewmodels.main import FailureInfo, MainViewState


class StatusPanel(QWidget):
    """解析ステータス、失敗銘柄、ログをまとめて表示するペイン。"""

    retry_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cancelling = False
        self._status_label = QLabel("待機中")
        bold_font = QFont(self._status_label.font())
        bold_font.setBold(True)
        self._status_label.setFont(bold_font)

        self._counts_label = QLabel("ウォッチリスト: 0 | 失敗: 0")
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setFormat("解析待機中")

        self._retry_button = QPushButton("失敗銘柄を再実行")
        self._retry_button.setEnabled(False)
        self._retry_button.clicked.connect(self.retry_requested.emit)

        header_layout = QHBoxLayout()
        header_layout.addWidget(self._status_label)
        header_layout.addStretch()
        header_layout.addWidget(self._counts_label)

        progress_layout = QHBoxLayout()
        progress_layout.addWidget(self._progress)
        progress_layout.addStretch()
        progress_layout.addWidget(self._retry_button)

        self._fail_table = QTableWidget(0, 2)
        self._fail_table.setHorizontalHeaderLabels(["銘柄", "メッセージ"])
        self._fail_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._fail_table.horizontalHeader().setStretchLastSection(True)
        self._fail_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._fail_table.setVisible(False)

        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setPlaceholderText("解析ログはここに表示されます")
        mono_font = QFont(self._log_view.font())
        mono_font.setStyleHint(QFont.StyleHint.TypeWriter)
        self._log_view.setFont(mono_font)

        self._copy_logs_btn = QPushButton("ログをコピー")
        self._copy_logs_btn.setEnabled(False)
        self._copy_logs_btn.clicked.connect(self._copy_logs_to_clipboard)

        logs_header = QHBoxLayout()
        logs_header.addWidget(QLabel("ログ"))
        logs_header.addStretch()
        logs_header.addWidget(self._copy_logs_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(header_layout)
        layout.addLayout(progress_layout)
        layout.addWidget(self._fail_table)
        layout.addLayout(logs_header)
        layout.addWidget(self._log_view)

    def update_state(self, state: "MainViewState") -> None:
        failure_count = len(state.failures)
        self._counts_label.setText(f"ウォッチリスト: {state.watchlist_total} | 失敗: {failure_count}")
        status_text = "解析中" if state.running else "待機中"
        if self._cancelling and state.running:
            status_text = "キャンセル中"
        self._status_label.setText(status_text)
        self._update_progress(state)
        self._update_failures(state.failures)
        self._update_logs(state.logs)
        self._retry_button.setEnabled(bool(state.failures) and not state.running)

    def set_cancelling(self, value: bool) -> None:
        self._cancelling = value
        if value:
            self._progress.setVisible(True)
            self._progress.setRange(0, 0)
            self._progress.setFormat("キャンセル中...")
        else:
            if self._progress.maximum() == 0:
                self._progress.setRange(0, 1)
                self._progress.setValue(0)
                self._progress.setFormat("")

    def _update_progress(self, state: "MainViewState") -> None:
        if state.running and state.total > 0:
            if not self._cancelling:
                self._progress.setRange(0, state.total)
                self._progress.setValue(min(state.completed, state.total))
                # パーセント表示を追加
                percent = int((state.completed / state.total) * 100) if state.total > 0 else 0
                self._progress.setFormat(f"解析中 {state.completed}/{state.total} ({percent}%)")
            self._progress.setVisible(True)
        else:
            self._progress.setVisible(False)
            self._progress.setValue(0)
            self._progress.setFormat("解析待機中")

    def _update_failures(self, failures: Sequence["FailureInfo"]) -> None:
        self._fail_table.setRowCount(len(failures))
        self._fail_table.setVisible(bool(failures))
        for row, failure in enumerate(failures):
            self._fail_table.setItem(row, 0, QTableWidgetItem(failure.symbol))
            self._fail_table.setItem(row, 1, QTableWidgetItem(failure.message))
        if failures:
            self._fail_table.resizeColumnsToContents()

    def _update_logs(self, lines: Sequence[str]) -> None:
        if lines:
            text = "\n".join(lines)
            self._log_view.setPlainText(text)
            self._log_view.verticalScrollBar().setValue(self._log_view.verticalScrollBar().maximum())
            self._copy_logs_btn.setEnabled(True)
        else:
            self._log_view.clear()
            self._copy_logs_btn.setEnabled(False)

    def _copy_logs_to_clipboard(self) -> None:
        text = self._log_view.toPlainText()
        if not text:
            return
        QApplication.clipboard().setText(text, mode=QClipboard.Mode.Clipboard)

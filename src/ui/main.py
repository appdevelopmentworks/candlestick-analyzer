from __future__ import annotations

from pathlib import Path
from typing import Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QBrush, QColor
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QAbstractItemView,
    QTableWidget,
    QTableWidgetItem,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QComboBox,
    QDialog,
)

from domain.models import SymbolRecord
from analysis.scoring import get_highlight_thresholds, update_highlight_thresholds
from domain.errors import ensure_app_error
from ui.components.detail_panel import DetailPanel
from ui.components.status_panel import StatusPanel
from ui.dialogs.settings import SettingsDialog
from ui.viewmodels.main import MainViewModel
from ui.workers.analyzer_worker import AnalyzerWorker
from export.exporter import export_table


def _make_item(value: str) -> QTableWidgetItem:
    item = QTableWidgetItem(value)
    item.setFlags(item.flags() ^ Qt.ItemIsEditable)
    return item


def _apply_row_highlight(table: QTableWidget, row: int, category: str | None) -> None:
    clear_brush = QBrush()
    color = CATEGORY_COLORS.get(category)
    for col in range(table.columnCount()):
        item = table.item(row, col)
        if item is None:
            continue
        if color is None:
            item.setBackground(clear_brush)
        else:
            item.setBackground(color)


def _populate_table(table: QTableWidget, viewmodel: MainViewModel) -> int:
    rows = list(viewmodel.state.rows)
    table.setRowCount(len(rows))
    for row_index, row in enumerate(rows):
        table.setItem(row_index, 0, _make_item(row.symbol))
        table.setItem(row_index, 1, _make_item(row.name))
        table.setItem(row_index, 2, _make_item(row.market))
        table.setItem(row_index, 3, _make_item(row.sector))
        table.setItem(row_index, 4, _make_item(row.score_display()))
        table.setItem(row_index, 5, _make_item(row.hits_display()))
        table.setItem(row_index, 6, _make_item(row.last_date_display()))
        _apply_row_highlight(table, row_index, row.score_category)
    return len(rows)


def run_app(watchlist: Path | None = None) -> int:
    app = QApplication([])
    window = QMainWindow()
    window.setWindowTitle("TA‑Lib ローソク足アナライザー")

    table = QTableWidget(0, 7)
    table.setHorizontalHeaderLabels(["Symbol", "Name", "Market", "Industry", "Score", "Hits", "Last Date"])
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

    detail_panel = DetailPanel()
    status_panel = StatusPanel()

    right_splitter = QSplitter(Qt.Orientation.Vertical)
    right_splitter.addWidget(detail_panel)
    right_splitter.addWidget(status_panel)
    right_splitter.setStretchFactor(0, 5)
    right_splitter.setStretchFactor(1, 2)
    right_splitter.setSizes([720, 280])

    splitter = QSplitter()
    splitter.addWidget(table)
    splitter.addWidget(right_splitter)
    splitter.setStretchFactor(0, 2)
    splitter.setStretchFactor(1, 3)
    splitter.setSizes([780, 1080])

    central = QWidget()
    layout = QVBoxLayout(central)
    layout.addWidget(splitter)
    window.setCentralWidget(central)

    toolbar = QToolBar()
    window.addToolBar(toolbar)
    status_bar = window.statusBar()

    viewmodel = MainViewModel()
    current_worker: AnalyzerWorker | None = None
    action_analyze = action_refresh = action_cancel = action_csv = action_export = None
    index_menu = None

    def show_error_dialog(title: str, error: Exception, *, critical: bool = True) -> None:
        app_error = ensure_app_error(error)
        message = app_error.ui_header()
        body = app_error.ui_body()
        if body:
            message = f"{message}\n\n{body}"
        if critical:
            QMessageBox.critical(window, title, message)
        else:
            QMessageBox.warning(window, title, message)

    def update_detail_from_row(row: int) -> None:
        if row < 0 or row >= table.rowCount():
            detail_panel.update_detail(None, None)
            return
        symbol_item = table.item(row, 0)
        if symbol_item is None:
            detail_panel.update_detail(None, None)
            return
        symbol = symbol_item.text()
        name_item = table.item(row, 1)
        display_name = name_item.text() if name_item else ""
        summary = viewmodel.get_summary(symbol)
        prices = None
        if summary is not None:
            try:
                prices = viewmodel.load_prices(symbol)
            except Exception as exc:
                show_error_dialog("データ取得エラー", exc, critical=False)
        detail_panel.update_detail(summary, prices, display_name=display_name)

    def refresh_row_highlights() -> None:
        rows = list(viewmodel.state.rows)
        for idx, row in enumerate(rows):
            if idx >= table.rowCount():
                break
            _apply_row_highlight(table, idx, row.score_category)

    def update_status_bar(state) -> None:
        running = getattr(state, "running", False)
        if running:
            total = state.total or 0
            progress = f"{state.completed}/{total}" if total else "—"
            message = f"解析中 | 進捗: {progress} | 失敗: {len(state.failures)}"
        else:
            message = f"待機中 | 銘柄数: {state.watchlist_total} | 失敗: {len(state.failures)}"
        status_bar.showMessage(message)

    def apply_filter_state(state, preserve_selection: bool = False) -> None:
        current_symbol = None
        if preserve_selection:
            current_row = table.currentRow()
            if 0 <= current_row < table.rowCount():
                item = table.item(current_row, 0)
                if item:
                    current_symbol = item.text()

        count = _populate_table(table, viewmodel)
        update_status_bar(state)
        status_panel.update_state(state)
        update_controls(state)
        if count:
            target_row = 0
            if current_symbol:
                for idx in range(table.rowCount()):
                    item = table.item(idx, 0)
                    if item and item.text() == current_symbol:
                        target_row = idx
                        break
            table.setCurrentCell(target_row, 0)
            update_detail_from_row(target_row)
        else:
            detail_panel.update_detail(None, None)

    def open_csv() -> None:
        path, _ = QFileDialog.getOpenFileName(window, "CSVを選択", "", "CSV Files (*.csv)")
        if path:
            load(Path(path))

    def export_table_data() -> None:
        df = viewmodel.export_dataframe()
        if df.empty:
            QMessageBox.information(window, "エクスポート", "エクスポートできるデータがありません。")
            return
        file_path, selected_filter = QFileDialog.getSaveFileName(
            window,
            "エクスポート先を選択",
            "",
            "CSV ファイル (*.csv);;Excel ファイル (*.xlsx);;JSON ファイル (*.json)",
        )
        if not file_path:
            return
        target = _resolve_export_path(Path(file_path), selected_filter)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            show_error_dialog(
                "エクスポート",
                ensure_app_error(
                    exc,
                    code="E-UNEXPECTED",
                    message="保存先フォルダーを作成できませんでした",
                ),
            )
            return
        if target.exists():
            answer = QMessageBox.question(
                window,
                "上書き確認",
                f"既にファイルが存在します。上書きしますか？\n{target}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            export_table(df, str(target))
        except Exception as exc:
            show_error_dialog(
                "エクスポート",
                ensure_app_error(
                    exc,
                    code="E-UNEXPECTED",
                    message="エクスポートに失敗しました",
                ),
            )
            return
        QMessageBox.information(window, "エクスポート", f"エクスポートが完了しました。\n{target}")

    def _resolve_export_path(path: Path, selected_filter: str) -> Path:
        if path.suffix:
            return path
        filter_text = (selected_filter or "").lower()
        if "xlsx" in filter_text:
            return path.with_suffix(".xlsx")
        if "json" in filter_text:
            return path.with_suffix(".json")
        return path.with_suffix(".csv")

    def load(path: Path) -> None:
        try:
            state = viewmodel.load_watchlist(path)
        except Exception as exc:  # UI層で捕捉しダイアログ表示
            show_error_dialog("CSVエラー", exc)
            return
        apply_filter_state(state)
        if viewmodel.get_settings().auto_run:
            start_analysis()

    def run_analysis() -> None:
        start_analysis()

    def refresh_analysis() -> None:
        start_analysis(force=True)

    def retry_failed_symbols() -> None:
        failed_symbols = viewmodel.get_failed_symbols()
        if not failed_symbols:
            QMessageBox.information(window, "再実行", "失敗した銘柄はありません。")
            return
        targets = viewmodel.get_records_for_symbols(failed_symbols)
        if not targets:
            QMessageBox.warning(window, "再実行", "再実行可能な銘柄が見つかりません。")
            return
        start_analysis(force=True, subset=targets)

    status_panel.retry_requested.connect(retry_failed_symbols)

    def load_index(name: str, refresh: bool = False) -> None:
        try:
            state = viewmodel.load_index(name, refresh=refresh)
        except Exception as exc:
            show_error_dialog("指数読み込みエラー", exc)
            return
        apply_filter_state(state)
        if viewmodel.get_settings().auto_run:
            start_analysis(force=refresh)

    def start_analysis(
        force: bool = False,
        subset: Sequence[SymbolRecord] | None = None,
    ) -> None:
        nonlocal current_worker
        if current_worker is not None:
            QMessageBox.information(window, "解析中", "既に解析が進行中です。")
            return
        targets = list(subset or viewmodel.get_watchlist())
        if not targets:
            QMessageBox.warning(window, "解析エラー", "ウォッチリストが空です。")
            return
        status_panel.set_cancelling(False)
        state = viewmodel.begin_async([record.symbol for record in targets])
        apply_filter_state(state)
        worker = AnalyzerWorker(viewmodel.analyzer(), targets, force_refresh=force)
        current_worker = worker
        worker.progress.connect(on_worker_progress)
        worker.failed.connect(on_worker_failed)
        worker.finished.connect(on_worker_finished)
        worker.start()

    def on_worker_progress(summary, completed, total, errors) -> None:
        state = viewmodel.handle_progress(summary, completed, total, errors)
        apply_filter_state(state, preserve_selection=True)

    def on_worker_failed(message: str) -> None:
        if "[E-" in message:
            QMessageBox.critical(window, "解析エラー", message)
            return
        show_error_dialog("解析エラー", ensure_app_error(Exception(message)))

    def on_worker_finished(cancelled: bool, errors: tuple[str, ...]) -> None:
        nonlocal current_worker
        status_panel.set_cancelling(False)
        state = viewmodel.finalize_async(cancelled, errors)
        apply_filter_state(state, preserve_selection=True)
        if current_worker is not None:
            current_worker.deleteLater()
            current_worker = None

    def cancel_analysis() -> None:
        nonlocal current_worker
        if current_worker is None:
            return
        current_worker.cancel()
        status_panel.set_cancelling(True)

    def update_controls(state) -> None:
        running = getattr(state, "running", False)
        if action_analyze is not None:
            action_analyze.setEnabled(not running)
        if action_refresh is not None:
            action_refresh.setEnabled(not running)
        if action_cancel is not None:
            action_cancel.setEnabled(running)
        if action_csv is not None:
            action_csv.setEnabled(not running)
        if action_export is not None:
            action_export.setEnabled(not running and bool(state.rows))
        if index_menu is not None:
            index_menu.setEnabled(not running)
        market_filter.setEnabled(True)
        score_filter.setEnabled(True)

    market_filter = QComboBox()
    market_filter.addItem("市場: 全て", userData=None)
    for code in ("US", "JP", "CA", "UK"):
        market_filter.addItem(f"市場: {code}", userData=code)

    score_filter = QComboBox()
    score_filter.addItem("スコア: 全て", userData=None)
    for value in (0, 1, 2, 3, 4):
        score_filter.addItem(f"スコア ≥ {value}", userData=value)

    def on_market_changed() -> None:
        state = viewmodel.set_market_filter(market_filter.currentData())
        apply_filter_state(state, preserve_selection=True)

    def on_score_changed() -> None:
        state = viewmodel.set_min_score_filter(score_filter.currentData())
        apply_filter_state(state, preserve_selection=True)

    market_filter.currentIndexChanged.connect(lambda _index: on_market_changed())
    score_filter.currentIndexChanged.connect(lambda _index: on_score_changed())

    action_csv = QAction("CSVを開く", window)
    action_csv.triggered.connect(open_csv)
    toolbar.addAction(action_csv)

    action_analyze = QAction("解析を実行", window)
    action_analyze.triggered.connect(run_analysis)
    toolbar.addAction(action_analyze)

    action_refresh = QAction("再取得", window)
    action_refresh.triggered.connect(refresh_analysis)
    toolbar.addAction(action_refresh)

    action_cancel = QAction("解析停止", window)
    action_cancel.setEnabled(False)
    action_cancel.triggered.connect(cancel_analysis)
    toolbar.addAction(action_cancel)

    action_export = QAction("エクスポート", window)
    action_export.triggered.connect(export_table_data)
    toolbar.addAction(action_export)

    toolbar.addSeparator()
    toolbar.addWidget(market_filter)
    toolbar.addWidget(score_filter)

    menu_bar = window.menuBar()
    settings_menu = menu_bar.addMenu("設定")

    def open_settings() -> None:
        current_thresholds = get_highlight_thresholds()
        dialog = SettingsDialog(window, viewmodel.get_settings())

        def preview_thresholds(pos: int, neg: int) -> None:
            update_highlight_thresholds(pos, neg)
            refresh_row_highlights()

        dialog.threshold_changed.connect(preview_thresholds)
        result = dialog.exec()
        if result == QDialog.Accepted:
            new_settings = dialog.value()
            state = viewmodel.apply_settings(new_settings)
            apply_filter_state(state, preserve_selection=True)
        else:
            update_highlight_thresholds(*current_thresholds)
            refresh_row_highlights()

    settings_menu.addAction("アプリ設定", open_settings)

    index_menu = menu_bar.addMenu("指数リスト")
    index_menu.addAction("S&P 500", lambda: load_index("sp500"))
    index_menu.addAction("S&P 500 再取得", lambda: load_index("sp500", refresh=True))
    index_menu.addSeparator()
    index_menu.addAction("日経225", lambda: load_index("nikkei225"))
    index_menu.addAction("日経225 再取得", lambda: load_index("nikkei225", refresh=True))
    index_menu.addSeparator()
    index_menu.addAction("日経500", lambda: load_index("nikkei500"))
    index_menu.addAction("日経500 再取得", lambda: load_index("nikkei500", refresh=True))
    index_menu.addSeparator()
    index_menu.addAction("JPX 400", lambda: load_index("jpx400"))
    index_menu.addAction("JPX 400 再取得", lambda: load_index("jpx400", refresh=True))

    table.currentCellChanged.connect(lambda row, _col, _prev_row, _prev_col: update_detail_from_row(row))

    update_controls(viewmodel.state)

    if watchlist:
        load(watchlist)
    else:
        update_status_bar(viewmodel.state)
        status_panel.update_state(viewmodel.state)

    window.resize(1760, 1040)
    window.show()
    return app.exec()
CATEGORY_COLORS = {
    "Strong＋": QColor(46, 125, 50, 160),
    "Mild＋": QColor(165, 214, 167, 140),
    "Neutral": None,
    "Mild−": QColor(242, 162, 162, 140),
    "Strong−": QColor(229, 115, 115, 180),
}

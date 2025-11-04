from __future__ import annotations

from typing import Iterable

import pandas as pd
from mplfinance.original_flavor import candlestick_ohlc
from matplotlib import dates as mdates
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtWidgets import QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from domain.models import AnalysisSummary, HitTimelineEntry, PatternHit
from analysis.scoring import categorize_score
from ui.style.fonts import apply_matplotlib_preferred_font


class DetailPanel(QWidget):
    """銘柄詳細（チャート + パターン内訳）の表示パネル。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        apply_matplotlib_preferred_font()
        self._figure = Figure(figsize=(5, 3))
        self._canvas = FigureCanvas(self._figure)
        self._info = QLabel("チャートを表示するには銘柄を選択してください")
        self._info.setWordWrap(True)

        self._hits_table = QTableWidget(0, 6)
        self._hits_table.setHorizontalHeaderLabels(
            ["Pattern", "Variant", "Value", "Strength", "Score", "説明"]
        )
        self._hits_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._hits_table.horizontalHeader().setStretchLastSection(True)

        self._history_table = QTableWidget(0, 3)
        self._history_table.setHorizontalHeaderLabels(["Date", "Patterns", "Score"])
        self._history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._history_table.horizontalHeader().setStretchLastSection(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self._canvas)
        layout.addWidget(self._info)
        layout.addWidget(self._hits_table)
        layout.addWidget(self._history_table)

    # ------------------------------------------------------------------
    def update_detail(
        self,
        summary: AnalysisSummary | None,
        prices: pd.DataFrame | None,
        display_name: str | None = None,
    ) -> None:
        self._update_chart(prices, summary, display_name)
        if summary is None:
            self._info.setText("チャートを表示するには銘柄を選択してください")
            self._update_hits([])
            self._update_history([])
        else:
            category, label = categorize_score(summary.total_score)
            score_text = label if category else label
            self._info.setText(
                f"Symbol: {summary.symbol} / Name: {display_name or '—'} / Score: {score_text} / Last Date: {summary.last_date or '—'}"
            )
            self._update_hits(summary.hits)
            self._update_history(summary.history)

    def _update_chart(
        self,
        prices: pd.DataFrame | None,
        summary: AnalysisSummary | None,
        display_name: str | None,
    ) -> None:
        self._figure.clear()
        if prices is None or prices.empty:
            ax = self._figure.add_subplot(111)
            ax.text(0.5, 0.5, "データがありません", ha="center", va="center")
            ax.set_axis_off()
        else:
            price_df = self._normalize_prices(prices)
            grid = self._figure.add_gridspec(2, 1, height_ratios=[3, 1], hspace=0.05)
            ax_price = self._figure.add_subplot(grid[0])
            ax_volume = self._figure.add_subplot(grid[1], sharex=ax_price)
            title_symbol = summary.symbol if summary else ""
            title_name = display_name or ""
            title_text = (f"{title_symbol} {title_name}").strip()
            self._draw_candlestick(ax_price, ax_volume, price_df, title_text)
            ax_volume.set_ylabel("Volume")
            for label in ax_price.get_xticklabels():
                label.set_rotation(0)
            ax_price.tick_params(labelsize=8)
            ax_volume.tick_params(labelsize=8)
        self._canvas.draw()

    @staticmethod
    def _normalize_prices(prices: pd.DataFrame) -> pd.DataFrame:
        plot_df = prices.copy()
        if "date" in plot_df.columns:
            plot_df["date"] = pd.to_datetime(plot_df["date"])
            plot_df.set_index("date", inplace=True)
        elif not isinstance(plot_df.index, pd.DatetimeIndex):
            plot_df.index = pd.to_datetime(plot_df.index)
        plot_df = plot_df.sort_index()
        renamed = plot_df.rename(
            columns={
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "volume": "Volume",
            }
        )
        for col in ("Open", "High", "Low", "Close"):
            if col not in renamed.columns:
                renamed[col] = pd.NA
        if "Volume" not in renamed.columns:
            renamed["Volume"] = 0
        renamed = renamed[["Open", "High", "Low", "Close", "Volume"]]
        renamed = renamed.apply(pd.to_numeric, errors="coerce")
        renamed = renamed.ffill().bfill()
        return renamed

    def _draw_candlestick(self, ax_price, ax_volume, price_df: pd.DataFrame, title: str) -> None:
        index_name = price_df.index.name or "index"
        reset = price_df.reset_index().rename(columns={index_name: "date"})
        reset.sort_values("date", inplace=True)
        reset["date_num"] = mdates.date2num(reset["date"])
        ohlc = reset[["date_num", "Open", "High", "Low", "Close"]].values.tolist()
        try:
            candlestick_ohlc(ax_price, ohlc, colorup="tab:green", colordown="tab:red", width=0.6)
        except Exception:
            ax_price.plot(reset["date"], reset["Close"], label="Close", color="tab:blue")
        for window in (5, 20, 60):
            if len(price_df) >= window:
                ax_price.plot(
                    price_df.index,
                    price_df["Close"].rolling(window).mean(),
                    label=f"MA{window}",
                )
        ax_price.legend(loc="upper left", fontsize=8)
        ax_price.set_title(title or "価格 (MA5/20/60)")
        ax_price.grid(True, alpha=0.3)
        ax_price.xaxis_date()
        ax_price.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
        ax_volume.bar(reset["date"], reset["Volume"], color="#999999", width=0.6)
        ax_volume.grid(True, alpha=0.3)

    def _update_hits(self, hits: Iterable[PatternHit]) -> None:
        hits_list = list(hits)
        self._hits_table.setRowCount(len(hits_list))
        for row, hit in enumerate(hits_list):
            self._hits_table.setItem(row, 0, QTableWidgetItem(hit.display_name()))
            self._hits_table.setItem(row, 1, QTableWidgetItem(hit.variant or ""))
            self._hits_table.setItem(row, 2, QTableWidgetItem(str(hit.value)))
            strength = "" if hit.strength is None else f"{hit.strength:.1f}"
            self._hits_table.setItem(row, 3, QTableWidgetItem(strength))
            score = "" if hit.weighted_score is None else f"{hit.weighted_score:+.2f}"
            self._hits_table.setItem(row, 4, QTableWidgetItem(score))
            self._hits_table.setItem(row, 5, QTableWidgetItem(hit.description or ""))
        self._hits_table.resizeColumnsToContents()

    def _update_history(self, history: Iterable[HitTimelineEntry]) -> None:
        entries = list(history)
        self._history_table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            date_str = entry.date.isoformat() if entry.date else "—"
            patterns = ", ".join(
                f"{hit.display_name()}({hit.base_score:+})" if hit.base_score is not None else hit.display_name()
                for hit in entry.hits
            )
            self._history_table.setItem(row, 0, QTableWidgetItem(date_str))
            self._history_table.setItem(row, 1, QTableWidgetItem(patterns))
            self._history_table.setItem(row, 2, QTableWidgetItem(f"{entry.total_score:+}"))
        self._history_table.resizeColumnsToContents()

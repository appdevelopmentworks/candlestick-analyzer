"""UIとサービス層を仲介するViewModelスタブ。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd

from domain.models import AnalysisSummary, SymbolRecord
from analysis.scoring import categorize_score, get_highlight_thresholds, update_highlight_thresholds
from domain.settings import AnalyzerUISettings
from services.analyzer import AnalyzerService
from services.index_service import IndexService
from services.user_settings import UserSettingsStore
from services.logging_setup import get_ui_log_lines


@dataclass(slots=True)
class TableRow:
    symbol: str
    name: str = ""
    market: str = ""
    sector: str = ""
    score: int | None = None
    hit_count: int | None = None
    last_date: date | None = None
    score_label: str = "—"
    score_category: str | None = None

    def score_display(self) -> str:
        return self.score_label

    def hits_display(self) -> str:
        return "—" if self.hit_count is None else str(self.hit_count)

    def last_date_display(self) -> str:
        return self.last_date.isoformat() if self.last_date else "—"


@dataclass(slots=True)
class FailureInfo:
    symbol: str
    message: str


@dataclass
class MainViewState:
    rows: Sequence[TableRow] = field(default_factory=tuple)
    last_error: str | None = None
    total: int = 0
    completed: int = 0
    errors: Sequence[str] = field(default_factory=tuple)
    running: bool = False
    failures: Sequence[FailureInfo] = field(default_factory=tuple)
    watchlist_total: int = 0
    logs: Sequence[str] = field(default_factory=tuple)


class MainViewModel:
    def __init__(
        self,
        analyzer: AnalyzerService | None = None,
        index_service: IndexService | None = None,
        settings_store: UserSettingsStore | None = None,
    ) -> None:
        self._analyzer = analyzer or AnalyzerService()
        self._index_service = index_service or IndexService(repo=self._analyzer.repo)
        self._settings_store = settings_store or UserSettingsStore()
        self._watchlist: list[SymbolRecord] = []
        self._rows: list[TableRow] = []
        self._state = MainViewState()
        self._summaries: dict[str, AnalysisSummary] = {}
        self._errors: tuple[str, ...] = ()
        self._failures: tuple[FailureInfo, ...] = ()
        self._last_error_msg: str | None = None
        self._completed = 0
        self._market_filter: str | None = None
        self._min_score: int | None = None
        self._running = False
        self._progress_total_override: int | None = None
        pos, neg = get_highlight_thresholds()
        self._ui_settings = AnalyzerUISettings(
            highlight_pos=pos,
            highlight_neg=neg,
        )
        stored_settings = self._settings_store.load()
        if stored_settings is not None:
            self._ui_settings = stored_settings
        self._sync_settings_to_services(self._ui_settings)

    @property
    def state(self) -> MainViewState:
        return self._state

    def load_watchlist(self, path: Path) -> MainViewState:
        try:
            records = self._analyzer.load_watchlist(path)
        except Exception as exc:
            self._state = MainViewState(rows=(), last_error=str(exc))
            raise
        self._watchlist = records
        self._summaries.clear()
        self._errors = ()
        self._failures = ()
        self._last_error_msg = None
        self._completed = 0
        self._market_filter = None
        self._min_score = None
        self._running = False
        self._progress_total_override = None
        self._summaries.clear()
        self._rebuild_rows()
        return self._emit_state()

    def load_index(self, index_name: str, refresh: bool = False) -> MainViewState:
        try:
            df = (
                self._index_service.refresh(index_name)
                if refresh
                else self._index_service.load(index_name)
            )
        except Exception as exc:
            self._state = MainViewState(rows=(), last_error=str(exc))
            raise
        records = [
            SymbolRecord(
                symbol=row.symbol,
                name=row.name or "",
                sector=row.sector or "",
                market=row.market or "",
            )
            for row in df.itertuples(index=False)
        ]
        enriched = self._analyzer.metadata.enrich(tuple(records))
        self._watchlist = list(enriched)
        self._summaries.clear()
        self._errors = ()
        self._failures = ()
        self._last_error_msg = None
        self._completed = 0
        self._market_filter = None
        self._min_score = None
        self._running = False
        self._progress_total_override = None
        self._rebuild_rows()
        return self._emit_state()

    def analyze(self) -> MainViewState:
        if not self._watchlist:
            self._state = MainViewState(rows=(), last_error="ウォッチリストが読み込まれていません")
            return self._state
        self._running = True
        self._completed = 0
        self._errors = ()
        self._failures = ()
        self._summaries.clear()
        self._progress_total_override = len(self._watchlist)
        self._rebuild_rows()
        summaries = self._analyzer.analyze_symbols(self._watchlist)
        self._summaries = {s.symbol: s for s in summaries}
        self._errors = tuple(self._analyzer.errors)
        self._last_error_msg = "\n".join(self._errors) if self._errors else None
        self._completed = len(summaries)
        self._running = False
        self._progress_total_override = None
        self._rebuild_rows()
        return self._emit_state()

    def refresh(self) -> MainViewState:
        if not self._watchlist:
            self._state = MainViewState(rows=(), last_error="ウォッチリストが読み込まれていません")
            return self._state
        self._running = True
        self._completed = 0
        self._errors = ()
        self._failures = ()
        self._summaries.clear()
        self._progress_total_override = len(self._watchlist)
        self._rebuild_rows()
        summaries = self._analyzer.analyze_symbols(self._watchlist, force_refresh=True)
        self._summaries = {s.symbol: s for s in summaries}
        self._errors = tuple(self._analyzer.errors)
        self._last_error_msg = "\n".join(self._errors) if self._errors else None
        self._completed = len(summaries)
        self._running = False
        self._progress_total_override = None
        self._rebuild_rows()
        return self._emit_state()

    def get_summary(self, symbol: str) -> AnalysisSummary | None:
        return self._summaries.get(symbol)

    def load_prices(self, symbol: str) -> "pd.DataFrame":
        return self._analyzer.get_prices(symbol)

    def get_watchlist(self) -> Sequence[SymbolRecord]:
        return tuple(self._watchlist)

    def analyzer(self) -> AnalyzerService:
        return self._analyzer

    def get_settings(self) -> AnalyzerUISettings:
        pos, neg = get_highlight_thresholds()
        patterns = self._analyzer.settings.patterns
        return AnalyzerUISettings(
            period_days=self._analyzer.settings.period_days,
            parallel_workers=self._analyzer.settings.parallel_workers,
            highlight_pos=pos,
            highlight_neg=neg,
            history_lookback=self._analyzer.settings.history_lookback,
            auto_run=self._ui_settings.auto_run,
            patterns=patterns,
        )

    def export_dataframe(self) -> pd.DataFrame:
        """現在のフィルタ状態に基づいた表データを DataFrame へ変換する。"""
        data: list[dict[str, object]] = []
        for row in self._state.rows:
            summary = self._summaries.get(row.symbol)
            data.append(
                {
                    "Symbol": row.symbol,
                    "Name": row.name,
                    "Market": row.market,
                    "Sector": row.sector,
                    "Score": row.score,
                    "Hits": row.hit_count,
                    "LastDate": row.last_date.isoformat() if row.last_date else None,
                    "Close": summary.close_price if summary else None,
                    "Volume": summary.volume if summary else None,
                    "HitPatterns": _format_hit_patterns(summary),
                }
            )
        columns = [
            "Symbol",
            "Name",
            "Market",
            "Sector",
            "Score",
            "Hits",
            "LastDate",
            "Close",
            "Volume",
            "HitPatterns",
        ]
        return pd.DataFrame(data, columns=columns)

    def apply_settings(self, settings: AnalyzerUISettings, persist: bool = True) -> MainViewState:
        self._ui_settings = settings
        self._sync_settings_to_services(settings)
        if persist:
            self._settings_store.save(settings)
        self._rebuild_rows()
        return self._emit_state()

    def _sync_settings_to_services(self, settings: AnalyzerUISettings) -> None:
        self._analyzer.settings.period_days = settings.period_days
        self._analyzer.settings.parallel_workers = settings.parallel_workers
        self._analyzer.settings.history_lookback = settings.history_lookback
        self._analyzer.settings.auto_run = settings.auto_run
        self._analyzer.settings.patterns = settings.patterns
        update_highlight_thresholds(settings.highlight_pos, settings.highlight_neg)

    def get_failed_symbols(self) -> tuple[str, ...]:
        return tuple(f.symbol for f in self._failures)

    def get_records_for_symbols(self, symbols: Sequence[str]) -> Sequence[SymbolRecord]:
        targets = set(symbols)
        if not targets:
            return ()
        return tuple(record for record in self._watchlist if record.symbol in targets)

    def begin_async(self, symbols: Sequence[str] | None = None) -> MainViewState:
        self._running = True
        self._completed = 0
        self._errors = ()
        self._failures = ()
        self._last_error_msg = None
        target_count = len(symbols) if symbols is not None else len(self._watchlist)
        self._progress_total_override = target_count
        self._summaries.clear()
        self._rebuild_rows()
        return self._emit_state()

    def handle_progress(
        self,
        summary: AnalysisSummary | None,
        completed: int,
        total: int,
        errors: tuple[str, ...],
    ) -> MainViewState:
        self._running = True
        if summary:
            self._summaries[summary.symbol] = summary
        self._completed = completed
        self._errors = errors
        self._failures = self._parse_failures(errors)
        self._last_error_msg = "\n".join(errors) if errors else None
        self._rebuild_rows()
        return self._emit_state()

    def finalize_async(self, cancelled: bool, errors: tuple[str, ...]) -> MainViewState:
        self._running = False
        if errors:
            self._errors = errors
            self._last_error_msg = "\n".join(errors)
        if cancelled and "ユーザーによるキャンセル" not in self._errors:
            self._errors = tuple(list(self._errors) + ["ユーザーによってキャンセルされました"])
            self._last_error_msg = "\n".join(self._errors)
        self._failures = self._parse_failures(self._errors)
        self._completed = len(self._summaries)
        self._progress_total_override = None
        self._rebuild_rows()
        return self._emit_state()

    def is_running(self) -> bool:
        return self._running

    # -- ヘルパー -----------------------------------------------------------------
    @staticmethod
    def _to_rows(records: Iterable[SymbolRecord]) -> Sequence[TableRow]:
        return tuple(
            TableRow(
                symbol=r.symbol,
                name=r.name,
                sector=r.sector,
                market=r.market or "",
            )
            for r in records
        )

    @staticmethod
    def _to_rows_with_summary(
        records: Iterable[SymbolRecord], summaries: Iterable[AnalysisSummary]
    ) -> Sequence[TableRow]:
        summary_map = {s.symbol: s for s in summaries}
        rows: list[TableRow] = []
        for r in records:
            summary = summary_map.get(r.symbol)
            score_value = summary.total_score if summary else None
            score_category, score_label = categorize_score(score_value)
            rows.append(
                TableRow(
                    symbol=r.symbol,
                    name=r.name,
                    sector=r.sector,
                    market=r.market or "",
                    score=score_value,
                    hit_count=len(summary.hits) if summary else None,
                    last_date=summary.last_date if summary else None,
                    score_label=score_label,
                    score_category=score_category,
                )
            )
        return tuple(rows)

    def _rebuild_rows(self) -> None:
        summary_map = self._summaries
        rows: list[TableRow] = []
        for record in self._watchlist:
            summary = summary_map.get(record.symbol)
            score_value = summary.total_score if summary else None
            score_category, score_label = categorize_score(score_value)
            rows.append(
                TableRow(
                    symbol=record.symbol,
                    name=record.name,
                    sector=record.sector,
                    market=record.market or "",
                    score=score_value,
                    hit_count=len(summary.hits) if summary else None,
                    last_date=summary.last_date if summary else None,
                    score_label=score_label,
                    score_category=score_category,
                )
            )
        self._rows = rows

    # -- フィルタ制御 -----------------------------------------------------------
    def set_market_filter(self, market: str | None) -> MainViewState:
        self._market_filter = market or None
        return self._emit_state()

    def set_min_score_filter(self, min_score: int | None) -> MainViewState:
        self._min_score = min_score
        return self._emit_state()

    # -- 内部ヘルパー -----------------------------------------------------------
    def _emit_state(self) -> MainViewState:
        filtered = tuple(row for row in self._rows if self._passes_filters(row))
        self._state = MainViewState(
            rows=filtered,
            last_error=self._last_error_msg,
            total=self._current_total(),
            completed=self._completed,
            errors=self._errors,
            running=self._running,
            failures=self._failures,
            watchlist_total=len(self._watchlist),
            logs=get_ui_log_lines(),
        )
        return self._state

    def _passes_filters(self, row: TableRow) -> bool:
        if self._market_filter and row.market != self._market_filter:
            return False
        if self._min_score is not None:
            score = row.score if row.score is not None else float("-inf")
            if score < self._min_score:
                return False
        return True

    @staticmethod
    def _parse_failures(errors: Sequence[str]) -> tuple[FailureInfo, ...]:
        failures: list[FailureInfo] = []
        seen: set[str] = set()
        for raw in errors:
            symbol: str
            detail: str
            if ":" not in raw:
                continue
            symbol, detail = raw.split(":", 1)
            symbol = symbol.strip()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            message = detail.strip() or raw.strip()
            failures.append(FailureInfo(symbol=symbol, message=message))
        return tuple(failures)

    def _current_total(self) -> int:
        if self._progress_total_override is not None:
            return self._progress_total_override
        return len(self._watchlist)


def _format_hit_patterns(summary: AnalysisSummary | None) -> str:
    if summary is None or not summary.hits:
        return ""
    parts: list[str] = []
    for hit in summary.hits:
        label = hit.display_name()
        if hit.weighted_score is not None:
            parts.append(f"{label} ({hit.weighted_score:+.2f})")
        else:
            parts.append(f"{label} ({hit.value:+d})")
    return ", ".join(parts)

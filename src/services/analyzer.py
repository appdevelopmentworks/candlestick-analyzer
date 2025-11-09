"""価格取得とパターン解析を束ねるサービス層。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable, Sequence, Tuple

import pandas as pd
import yfinance as yf
from threading import Event
import yaml

from analysis.patterns import detect_with_history
from analysis.scoring import enrich_hits, total_score_from_hits
from data.store import PricesRepo
from domain.models import AnalysisSummary, HitTimelineEntry, PatternHit, SymbolRecord
from domain.errors import AppError, app_error, ensure_app_error
from services.metadata import MetadataService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AnalyzerSettings:
    period_days: int = 400
    parallel_workers: int = 5
    retry_attempts: int = 2
    retry_backoff: float = 1.6
    history_lookback: int = 20
    auto_run: bool = False
    patterns: Tuple[str, ...] | None = None


def _safe_int(value, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _safe_float(value, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _settings_from_config(config_path: Path = Path("config.yaml")) -> AnalyzerSettings:
    defaults = AnalyzerSettings()
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        logger.debug("Failed to load analyzer settings from %s", config_path)
        return defaults
    if not isinstance(raw, dict):
        return defaults

    fetch_cfg = raw.get("fetch", {}) if isinstance(raw.get("fetch"), dict) else {}
    retry_cfg = fetch_cfg.get("retry", {}) if isinstance(fetch_cfg.get("retry"), dict) else {}
    analysis_cfg = raw.get("analysis", {}) if isinstance(raw.get("analysis"), dict) else {}
    app_cfg = raw.get("app", {}) if isinstance(raw.get("app"), dict) else {}

    period_days = _safe_int(fetch_cfg.get("period_days"), defaults.period_days)
    parallel_workers = _safe_int(fetch_cfg.get("parallel_max"), defaults.parallel_workers)
    retry_attempts = _safe_int(retry_cfg.get("max_attempts"), defaults.retry_attempts)
    retry_backoff = _safe_float(retry_cfg.get("backoff"), defaults.retry_backoff)
    history_lookback = _safe_int(analysis_cfg.get("history_lookback"), defaults.history_lookback)
    auto_run = bool(app_cfg.get("auto_run", defaults.auto_run))

    return AnalyzerSettings(
        period_days=period_days,
        parallel_workers=parallel_workers,
        retry_attempts=retry_attempts,
        retry_backoff=retry_backoff,
        history_lookback=history_lookback,
        auto_run=auto_run,
    )


class AnalyzerService:
    """銘柄集合に対するデータ取得と解析を提供する。"""

    def __init__(
        self,
        repo: PricesRepo | None = None,
        settings: AnalyzerSettings | None = None,
        metadata_service: MetadataService | None = None,
    ) -> None:
        self.repo = repo or PricesRepo.from_config()
        self.settings = settings or _settings_from_config()
        self.metadata = metadata_service or MetadataService(repo=self.repo)
        self._errors: list[AppError] = []

    # -- 公開API -----------------------------------------------------------------
    def load_watchlist(self, path: Path) -> list[SymbolRecord]:
        from io_utils.csv_loader import load_symbols  # 循環依存回避のためローカルインポート

        try:
            records = load_symbols(path)
        except AppError:
            raise
        except Exception as exc:
            raise ensure_app_error(
                exc,
                code="E-CSV-UNKNOWN",
                message="CSVの読み込みに失敗しました",
            ) from exc
        try:
            return self.metadata.enrich(tuple(records))
        except AppError:
            raise
        except Exception as exc:
            raise ensure_app_error(
                exc,
                code="E-META-UNEXPECTED",
                message="銘柄情報の取得に失敗しました",
            ) from exc

    def analyze_symbols(
        self,
        symbols: Iterable[SymbolRecord],
        *,
        force_refresh: bool = False,
        progress_callback: "Callable[[AnalysisSummary | None, int, int, tuple[str, ...]], None]" | None = None,
        cancel_event: "Event" | None = None,
    ) -> list[AnalysisSummary]:
        self._errors.clear()
        results: list[AnalysisSummary] = []
        from concurrent.futures import ThreadPoolExecutor, as_completed

        records = list(symbols)
        total = len(records)
        if total == 0:
            return results
        cancel_event = cancel_event or Event()

        logger.info("Starting analysis for %d symbols (force_refresh=%s)", total, force_refresh)

        with ThreadPoolExecutor(max_workers=self.settings.parallel_workers) as exe:
            future_map = {
                exe.submit(self._analyze_symbol_safe, record, force_refresh): record for record in records
            }
            completed = 0
            for future in as_completed(future_map):
                record = future_map[future]
                if cancel_event.is_set():
                    for f in future_map:
                        if not f.done():
                            f.cancel()
                    break
                summary: AnalysisSummary | None = None
                try:
                    summary = future.result()
                except Exception as exc:
                    app_err = ensure_app_error(
                        exc,
                        code="E-ANL-UNEXPECTED",
                        message="解析中にエラーが発生しました",
                    ).with_symbol(record.symbol)
                    self._record_error(app_err)
                if summary:
                    results.append(summary)
                completed += 1
                if progress_callback:
                    progress_callback(summary, completed, total, self._formatted_errors())
                if cancel_event.is_set():
                    for f in future_map:
                        if not f.done():
                            f.cancel()
                    break
        logger.info(
            "Analysis finished: %d summaries, %d errors", len(results), len(self._errors)
        )
        return results

    @property
    def errors(self) -> Sequence[str]:
        return self._formatted_errors()

    def get_prices(self, symbol: str) -> pd.DataFrame:
        return self.repo.get_range(symbol)

    def analyze_symbol(self, record: SymbolRecord, *, force_refresh: bool = False) -> AnalysisSummary | None:
        df = self._ensure_prices(record.symbol, force_refresh=force_refresh)
        if df is None or df.empty:
            return None
        try:
            hits_raw, history_raw = detect_with_history(
                df,
                lookback=self.settings.history_lookback,
                patterns=self.settings.patterns,
            )
        except Exception as exc:
            app_err = app_error(
                "E-TA-LIB",
                detail=str(exc) or None,
                symbol=record.symbol,
            )
            logger.exception("TA-Lib pattern detection failed for %s", record.symbol)
            raise app_err from exc
        hits = enrich_hits(hits_raw)
        score = total_score_from_hits(hits)
        last_row = df.iloc[-1]
        last_date = last_row.get("date")
        if isinstance(last_date, pd.Timestamp):
            last_date = last_date.date()
        history_entries: list[HitTimelineEntry] = []
        for entry in history_raw:
            entry_date = entry.get("date")
            if isinstance(entry_date, pd.Timestamp):
                entry_date = entry_date.date()
            elif isinstance(entry_date, datetime):
                entry_date = entry_date.date()
            elif entry_date is not None and not isinstance(entry_date, date):
                try:
                    entry_date = pd.Timestamp(entry_date).date()
                except Exception:
                    entry_date = None
            hits_list = enrich_hits(entry.get("hits", []), at=entry_date)  # type: ignore[arg-type]
            history_entries.append(
                HitTimelineEntry(
                    date=entry_date,
                    hits=tuple(hits_list),
                    total_score=total_score_from_hits(hits_list),
                )
            )
        return AnalysisSummary(
            symbol=record.symbol,
            hits=tuple(hits),
            total_score=score,
            last_date=last_date if isinstance(last_date, date) else None,
            close_price=float(last_row.get("close", float("nan"))) if "close" in last_row else None,
            volume=float(last_row.get("volume", float("nan"))) if "volume" in last_row else None,
            history=tuple(history_entries),
        )

    # -- 内部処理 -----------------------------------------------------------------
    def _ensure_prices(self, symbol: str, *, force_refresh: bool = False) -> pd.DataFrame | None:
        cached = self.repo.get_range(symbol)
        if not cached.empty and not force_refresh:
            if self._is_fresh(cached):
                return cached
        try:
            fetched = self._fetch_from_yfinance(symbol)
        except AppError as err:
            if not cached.empty and not force_refresh:
                logger.warning(
                    "Using cached prices for %s after fetch failure: %s",
                    symbol,
                    err.for_log(),
                )
                self._record_error(err.with_symbol(symbol))
                return cached
            raise err
        if fetched is None or fetched.empty:
            if not cached.empty and not force_refresh:
                return cached
            raise app_error("E-YF-404", symbol=symbol)
        self.repo.upsert_prices(symbol, fetched)
        merged = self.repo.get_range(symbol)
        return merged if not merged.empty else cached

    def _fetch_from_yfinance(self, symbol: str) -> pd.DataFrame | None:
        try:
            df = self._download_with_retry(symbol)
        except AppError:
            raise
        except Exception as exc:  # ネットワーク障害等
            logger.exception("yfinance download failed for %s", symbol)
            raise app_error("E-YF-404", detail=str(exc) or None, symbol=symbol) from exc
        if df is None or df.empty:
            logger.info("yfinance returned no data for %s", symbol)
            raise app_error("E-YF-404", symbol=symbol)
        df = df.reset_index()  # Date列を明示化
        # MultiIndexカラムをフラット化
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        # カラムをrenameで確実に文字列化
        df = df.rename(columns={col: str(col) for col in df.columns})
        df = self._sanitize_ohlc(df)
        return df

    def _download_with_retry(self, symbol: str) -> pd.DataFrame | None:
        import time

        attempt = 0
        delay = 1.0
        last_exc: Exception | None = None
        while attempt <= self.settings.retry_attempts:
            try:
                return yf.download(
                    symbol,
                    period=f"{self.settings.period_days}d",
                    interval="1d",
                    auto_adjust=False,
                    progress=False,
                    threads=False,
                )
            except Exception as exc:
                last_exc = exc
                attempt += 1
                if attempt > self.settings.retry_attempts:
                    break
                time.sleep(delay)
                delay *= self.settings.retry_backoff
        if last_exc:
            raise app_error("E-YF-404", detail=str(last_exc) if last_exc else None) from last_exc
        return None

    def _analyze_symbol_safe(self, record: SymbolRecord, force_refresh: bool) -> AnalysisSummary | None:
        try:
            return self.analyze_symbol(record, force_refresh=force_refresh)
        except AppError as err:
            raise err
        except Exception as exc:
            import traceback
            logger.error(f"Full traceback for {record.symbol}:\n{traceback.format_exc()}")
            raise ensure_app_error(
                exc,
                code="E-ANL-UNEXPECTED",
                message="解析中に予期しないエラーが発生しました",
            ) from exc

    def _record_error(self, err: AppError) -> None:
        self._errors.append(err)
        logger.error(err.for_log())

    def _formatted_errors(self) -> tuple[str, ...]:
        formatted: list[str] = []
        for err in self._errors:
            formatted.append(str(err))
        return tuple(formatted)

    @staticmethod
    def _sanitize_ohlc(df: pd.DataFrame) -> pd.DataFrame:
        cols = ["Open", "High", "Low", "Close", "Adj Close", "open", "high", "low", "close"]
        present = [c for c in cols if c in df.columns]
        if not present:
            return df
        ohlc = df[present].copy()
        min_positive = ohlc[ohlc > 0].min().min()
        if pd.isna(min_positive) or min_positive <= 0:
            return df
        # 各カラムに対してnumpyで直接置換（pandasの曖昧性を回避）
        for col in present:
            # numpyのwhere を使用して置換
            df[col] = df[col].where(df[col] > 0, min_positive)
        return df

    @staticmethod
    def _is_fresh(df: pd.DataFrame) -> bool:
        if "date" not in df.columns or df.empty:
            return False
        last = df["date"].iloc[-1]
        if isinstance(last, pd.Timestamp):
            last = last.date()
        if not isinstance(last, (date, datetime)):
            return False
        if isinstance(last, datetime):
            last = last.date()
        today = datetime.utcnow().date()
        return last >= today - timedelta(days=2)

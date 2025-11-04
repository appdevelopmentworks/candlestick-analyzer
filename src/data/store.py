"""DuckDBを利用した価格データ永続化層。"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Optional
from datetime import date, datetime
import numpy as np
from threading import Lock

import duckdb
import pandas as pd
import yaml

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PricesRepo:
    db_path: Path
    _schema_lock: ClassVar[Lock] = Lock()
    _prices_initialized: bool = field(default=False, init=False, repr=False)

    @classmethod
    def from_config(cls, config_path: Path = Path("config.yaml")) -> "PricesRepo":
        try:
            cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed to read config file: %s", config_path)
            raise
        try:
            cache_path = Path(cfg["cache"]["duckdb_path"])
        except (KeyError, TypeError) as exc:
            logger.error("cache.duckdb_path is not set in %s", config_path)
            raise
        return cls(cache_path)

    # ------------------------------------------------------------------
    def _conn(self) -> duckdb.DuckDBPyConnection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            return duckdb.connect(str(self.db_path))
        except Exception:
            logger.exception("Failed to connect to DuckDB: %s", self.db_path)
            raise

    def init_schema(self, schema_path: Path = Path("schema.sql")) -> None:
        con = self._conn()
        try:
            sql = schema_path.read_text(encoding="utf-8")
            con.execute(sql)
        except Exception:
            logger.exception("Failed to initialize schema from %s", schema_path)
            raise
        finally:
            con.close()

    def upsert_prices(self, symbol: str, df: pd.DataFrame, tz: str = "UTC") -> None:
        if df is None or df.empty:
            logger.debug("Skip upsert: empty dataframe for %s", symbol)
            return
        prepared = self._prepare_dataframe(df, symbol, tz)
        con = self._conn()
        try:
            self._ensure_prices_table(con)
            records = tuple(self._iter_price_rows(prepared))
            if not records:
                return
            con.executemany(
                "INSERT OR REPLACE INTO prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                records,
            )
        except Exception:
            logger.exception("Failed to upsert prices for %s", symbol)
            raise
        finally:
            con.close()

    def get_range(self, symbol: str) -> pd.DataFrame:
        con = self._conn()
        try:
            self._ensure_prices_table(con)
            df = con.execute(
                "SELECT date, open, high, low, close, volume FROM prices "
                "WHERE symbol=? ORDER BY date",
                [symbol],
            ).df()
        except Exception:
            logger.exception("Failed to fetch prices for %s", symbol)
            raise
        finally:
            con.close()
        return df

    def get_latest_date(self, symbol: str) -> Optional[str]:
        con = self._conn()
        try:
            self._ensure_prices_table(con)
            row = con.execute(
                "SELECT max(date) FROM prices WHERE symbol=?",
                [symbol],
            ).fetchone()
        except Exception:
            logger.exception("Failed to fetch latest date for %s", symbol)
            raise
        finally:
            con.close()
        return row[0] if row else None

    # ------------------------------------------------------------------
    def upsert_metadata(
        self,
        symbol: str,
        name: str | None,
        sector: str | None,
        market: str | None,
    ) -> None:
        con = self._conn()
        try:
            con.execute(
                "CREATE TABLE IF NOT EXISTS metadata ("
                "symbol TEXT PRIMARY KEY, name TEXT, sector TEXT, market TEXT, last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            )
            con.execute(
                "INSERT INTO metadata(symbol, name, sector, market, last_updated)"
                " VALUES (?, ?, ?, ?, now())"
                " ON CONFLICT(symbol) DO UPDATE SET "
                "name=excluded.name, sector=excluded.sector, market=excluded.market, last_updated=now()",
                [symbol, name, sector, market],
            )
        except Exception:
            logger.exception("Failed to upsert metadata for %s", symbol)
            raise
        finally:
            con.close()

    def get_metadata(self, symbol: str) -> dict[str, Optional[str]] | None:
        con = self._conn()
        try:
            con.execute(
                "CREATE TABLE IF NOT EXISTS metadata ("
                "symbol TEXT PRIMARY KEY, name TEXT, sector TEXT, market TEXT, last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            )
            row = con.execute(
                "SELECT symbol, name, sector, market FROM metadata WHERE symbol=?",
                [symbol],
            ).fetchone()
        except Exception:
            logger.exception("Failed to fetch metadata for %s", symbol)
            raise
        finally:
            con.close()
        if not row:
            return None
        return {
            "symbol": row[0],
            "name": row[1],
            "sector": row[2],
            "market": row[3],
        }

    # ------------------------------------------------------------------
    def replace_index_members(self, index_name: str, df: pd.DataFrame) -> None:
        con = self._conn()
        try:
            con.execute(
                "CREATE TABLE IF NOT EXISTS index_members ("
                "index_name TEXT, symbol TEXT, name TEXT, sector TEXT, market TEXT, "
                "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(index_name, symbol))"
            )
            con.execute(
                "DELETE FROM index_members WHERE index_name=?",
                [index_name],
            )
            if not df.empty:
                staged = df.copy()
                staged["index_name"] = index_name
                staged["updated_at"] = pd.Timestamp.utcnow()
                records = tuple(
                    tuple(row)
                    for row in staged[["index_name", "symbol", "name", "sector", "market", "updated_at"]].itertuples(index=False, name=None)
                )
                con.executemany(
                    "INSERT INTO index_members(index_name, symbol, name, sector, market, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    records,
                )
        except Exception:
            logger.exception("Failed to update index members for %s", index_name)
            raise
        finally:
            con.close()

    def load_index_members(self, index_name: str) -> pd.DataFrame:
        con = self._conn()
        try:
            con.execute(
                "CREATE TABLE IF NOT EXISTS index_members ("
                "index_name TEXT, symbol TEXT, name TEXT, sector TEXT, market TEXT, "
                "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(index_name, symbol))"
            )
            df = con.execute(
                "SELECT symbol, name, sector, market FROM index_members WHERE index_name=? ORDER BY symbol",
                [index_name],
            ).df()
        except Exception:
            logger.exception("Failed to load index members for %s", index_name)
            raise
        finally:
            con.close()
        return df

    # ------------------------------------------------------------------
    @staticmethod
    def _prepare_dataframe(df: pd.DataFrame, symbol: str, tz: str) -> pd.DataFrame:
        prepared = df.copy()
        if "Date" in prepared.columns:
            prepared.rename(columns={"Date": "date"}, inplace=True)
        if "Adj Close" in prepared.columns and "close" not in prepared.columns:
            prepared.rename(columns={"Adj Close": "close"}, inplace=True)
        prepared.rename(
            columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            },
            inplace=True,
        )
        if "date" not in prepared.columns and "index" in prepared.columns:
            prepared.rename(columns={"index": "date"}, inplace=True)
        if "date" not in prepared.columns:
            logger.error("DataFrame missing 'date' column for %s", symbol)
            raise ValueError("date column is required")
        prepared["symbol"] = symbol
        prepared["timezone"] = tz
        prepared = prepared.loc[:, ~prepared.columns.duplicated()]
        cols = [
            "symbol",
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "timezone",
        ]
        missing_cols = [col for col in cols if col not in prepared.columns]
        if missing_cols:
            raise ValueError(f"Missing columns for upsert: {missing_cols}")
        return prepared[cols]

    def _ensure_prices_table(self, con: duckdb.DuckDBPyConnection) -> None:
        if self._prices_initialized:
            return
        with self._schema_lock:
            if self._prices_initialized:
                return
            con.execute(
                "CREATE TABLE IF NOT EXISTS prices ("
                "symbol TEXT, date DATE, open DOUBLE, high DOUBLE, low DOUBLE, "
                "close DOUBLE, volume DOUBLE, timezone TEXT, PRIMARY KEY(symbol, date))"
            )
            self._prices_initialized = True

    @staticmethod
    def _iter_price_rows(df: pd.DataFrame):
        for row in df.itertuples(index=False, name=None):
            values = row if len(row) >= 8 else row + (None,) * (8 - len(row))
            (
                symbol,
                date_value,
                open_value,
                high_value,
                low_value,
                close_value,
                volume_value,
                timezone,
                *_,
            ) = values
            yield (
                symbol,
                _as_date(date_value),
                _to_float(open_value),
                _to_float(high_value),
                _to_float(low_value),
                _to_float(close_value),
                _to_float(volume_value),
                timezone,
            )


def _as_date(value):
    if value is None:
        return None
    if isinstance(value, pd.Series):
        return _as_date(value.iloc[0]) if not value.empty else None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return pd.to_datetime(value).date()
    except Exception:
        return None


def _to_float(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, pd.Series):
        if value.empty:
            return None
        return _to_float(value.iloc[0])
    if isinstance(value, np.generic):
        return float(value)
    try:
        return float(value)
    except Exception:
        return None

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import pandas as pd

from domain.models import SymbolRecord
from services.analyzer import AnalyzerService, AnalyzerSettings


@dataclass
class FakeRepo:
    data: Dict[str, pd.DataFrame]

    def get_range(self, symbol: str) -> pd.DataFrame:
        return self.data.get(symbol, pd.DataFrame())

    def upsert_prices(self, symbol: str, df: pd.DataFrame) -> None:
        self.data[symbol] = df

    # MetadataService compatibility -------------------------------------------------
    def get_metadata(self, symbol: str):
        return None

    def upsert_metadata(self, symbol: str, name: str | None, sector: str | None, market: str | None) -> None:
        pass

    # IndexService compatibility ----------------------------------------------------
    def replace_index_members(self, index_name: str, df: pd.DataFrame) -> None:
        pass

    def load_index_members(self, index_name: str) -> pd.DataFrame:
        return pd.DataFrame()


class SanitizedAnalyzer(AnalyzerService):
    def __init__(self) -> None:
        super().__init__(repo=FakeRepo({}), settings=AnalyzerSettings())

    def _download_with_retry(self, symbol: str) -> pd.DataFrame | None:  # type: ignore[override]
        dates = pd.date_range("2024-01-01", periods=5, freq="D")
        return pd.DataFrame(
            {
                "Date": dates,
                "Open": [0, 100, 110, 120, 130],
                "High": [0, 110, 120, 130, 140],
                "Low": [0, 90, 95, 100, 105],
                "Close": [0, 105, 115, 125, 135],
                "Volume": [1000, 1200, 1100, 1300, 1400],
            }
        )


def test_sanitize_ohlc_replaces_zero_values():
    svc = SanitizedAnalyzer()
    record = SymbolRecord(symbol="TEST", name="", sector="", market="US")

    df = svc._ensure_prices(record.symbol, force_refresh=True)
    assert df is not None
    columns = [c for c in ["Open", "High", "Low", "Close", "open", "high", "low", "close"] if c in df.columns]
    assert columns, "Expected OHLC columns to exist"
    assert (df[columns] > 0).all().all()


def test_analyze_symbols_collects_errors(monkeypatch):
    svc = AnalyzerService(repo=FakeRepo({}), settings=AnalyzerSettings())

    def fake_analyze_symbol(self, record: SymbolRecord, force_refresh: bool = False):
        raise RuntimeError("boom")

    monkeypatch.setattr(AnalyzerService, "analyze_symbol", fake_analyze_symbol)

    record = SymbolRecord(symbol="ERR", name="", sector="", market="US")
    summaries: List = svc.analyze_symbols([record])

    assert summaries == []
    assert svc.errors
    assert "ERR" in svc.errors[0]

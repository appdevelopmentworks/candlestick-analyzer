"""銘柄メタデータの取得とキャッシュ管理。"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Iterable, Sequence

import pandas as pd
import yfinance as yf

from data.store import PricesRepo
from domain.models import SymbolRecord
from io_utils.markets import infer_market

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MetadataService:
    repo: PricesRepo
    max_workers: int = 8

    def enrich(self, records: Sequence[SymbolRecord]) -> list[SymbolRecord]:
        enriched: list[SymbolRecord] = []
        to_fetch: list[SymbolRecord] = []
        for record in records:
            cached = self.repo.get_metadata(record.symbol)
            if cached:
                enriched.append(
                    SymbolRecord(
                        symbol=record.symbol,
                        name=cached.get("name") or record.name,
                        sector=cached.get("sector") or record.sector,
                        market=cached.get("market") or record.market or infer_market(record.symbol),
                    )
                )
            else:
                to_fetch.append(record)
                enriched.append(record)
        if not to_fetch:
            return enriched

        fetched_map = self._fetch_bulk(to_fetch)
        result: list[SymbolRecord] = []
        for record in enriched:
            data = fetched_map.get(record.symbol)
            if data:
                merged = SymbolRecord(
                    symbol=record.symbol,
                    name=data.get("name") or record.name,
                    sector=data.get("sector") or record.sector,
                    market=data.get("market") or record.market,
                )
                result.append(merged)
                self.repo.upsert_metadata(
                    record.symbol,
                    merged.name or None,
                    merged.sector or None,
                    merged.market,
                )
            else:
                # キャッシュのみ/取得失敗は既存値を利用
                result.append(record)
        return result

    # ------------------------------------------------------------------
    def _fetch_bulk(self, records: Iterable[SymbolRecord]) -> dict[str, dict[str, str]]:
        results: dict[str, dict[str, str]] = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as exe:
            future_map = {
                exe.submit(self._fetch_single, record.symbol): record.symbol for record in records
            }
            for future in as_completed(future_map):
                symbol = future_map[future]
                try:
                    data = future.result()
                except Exception:
                    logger.exception("Failed to fetch metadata for %s", symbol)
                    continue
                if data:
                    results[symbol] = data
        return results

    @staticmethod
    def _fetch_single(symbol: str) -> dict[str, str]:
        ticker = yf.Ticker(symbol)
        info = ticker.fast_info if hasattr(ticker, "fast_info") else {}
        result: dict[str, str] = {}
        try:
            info_full = ticker.get_info()
        except Exception:
            info_full = {}
        name = info_full.get("longName") or info_full.get("shortName") or info.get("shortName")
        sector = info_full.get("sector") or info_full.get("industry")
        market = info_full.get("market")
        if name:
            result["name"] = name
        if sector:
            result["sector"] = sector
        if market:
            result["market"] = market
        return result

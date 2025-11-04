"""主要株価指数リストを管理するサービス。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict

import pandas as pd

from data.store import PricesRepo
from io_utils import index_scraper
from domain.errors import AppError, app_error


@dataclass(slots=True)
class IndexService:
    repo: PricesRepo

    _FETCHERS: Dict[str, Callable[[], pd.DataFrame]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self._FETCHERS is None:
            self._FETCHERS = {
                "sp500": index_scraper.fetch_sp500,
                "nikkei225": index_scraper.fetch_nikkei225,
                "nikkei500": index_scraper.fetch_nikkei500,
                "jpx400": index_scraper.fetch_jpx400,
            }

    def list_indices(self) -> list[str]:
        return list(self._FETCHERS.keys())

    def load(self, name: str, use_cache: bool = True) -> pd.DataFrame:
        if use_cache:
            cached = self.repo.load_index_members(name)
            if not cached.empty:
                return cached
        fetcher = self._FETCHERS.get(name)
        if not fetcher:
            raise app_error("E-INDEX-NOTFOUND", detail=name)
        try:
            df = fetcher()
        except Exception as exc:
            raise app_error("E-INDEX-FETCH", detail=str(exc) or None) from exc
        if df.empty:
            raise app_error("E-INDEX-EMPTY", detail=name)
        self.repo.replace_index_members(name, df)
        return df

    def refresh(self, name: str) -> pd.DataFrame:
        return self.load(name, use_cache=False)

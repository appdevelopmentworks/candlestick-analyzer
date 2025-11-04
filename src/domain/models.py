"""共通で利用するドメインモデル定義。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable, Optional, Sequence


@dataclass(slots=True)
class SymbolRecord:
    """CSVや指数リストで定義される銘柄情報。"""

    symbol: str
    name: str = ""
    sector: str = ""
    market: Optional[str] = None

    def as_dict(self) -> dict[str, str | None]:
        """UIやシリアライザ向けに辞書へ変換する。"""
        return {
            "symbol": self.symbol,
            "name": self.name,
            "sector": self.sector,
            "market": self.market,
        }


@dataclass(slots=True)
class PatternHit:
    """TA-Libが返すローソク足パターンの検出結果。"""

    fn: str
    value: int
    strength: float | None = None
    base_score: int | None = None
    weighted_score: float | None = None
    variant: str | None = None
    english: str | None = None
    japanese: str | None = None
    typical_setup: str | None = None
    next_move: str | None = None
    description: str | None = None
    date: date | None = None

    def score_tuple(self) -> tuple[str, int, float | None]:  # pragma: no cover - legacy helper
        return (self.fn, self.value, self.weighted_score)

    def display_name(self) -> str:
        return (self.japanese or self.english or self.fn)


@dataclass(slots=True)
class AnalysisSummary:
    """単一銘柄の解析結果を集約したサマリーモデル。"""

    symbol: str
    hits: Sequence[PatternHit] = field(default_factory=tuple)
    total_score: int = 0
    last_date: Optional[date] = None
    close_price: float | None = None
    volume: float | None = None
    history: Sequence["HitTimelineEntry"] = field(default_factory=tuple)
    errors: Sequence[str] = field(default_factory=tuple)


@dataclass(slots=True)
class FetchJob:
    """価格データ取得の進捗管理に利用するジョブ情報。"""

    symbol: str
    requested_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    status: str = "pending"  # pending / running / completed / failed
    message: str | None = None


@dataclass(slots=True)
class PriceBar:
    """日足データの1レコード。"""

    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    timezone: str | None = None


def ensure_sequence(value: Iterable[PatternHit] | None) -> Sequence[PatternHit]:
    """ヒット情報をタプルに正規化するヘルパー。"""
    if value is None:
        return ()
    if isinstance(value, Sequence):
        return value
    return tuple(value)


@dataclass(slots=True)
class HitTimelineEntry:
    date: date | None
    hits: Sequence[PatternHit] = field(default_factory=tuple)
    total_score: int = 0

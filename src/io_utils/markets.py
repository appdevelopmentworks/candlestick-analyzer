"""市場推定・シンボル正規化ヘルパー。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MarketRule:
    suffix: str
    market: str


_SUFFIX_RULES: tuple[MarketRule, ...] = (
    MarketRule(suffix=".T", market="JP"),
    MarketRule(suffix=".TO", market="CA"),
    MarketRule(suffix=".L", market="UK"),
)


def infer_market(symbol: str, default: str = "US") -> str:
    """Yahoo表記のティッカーから市場コードを推定する。"""
    cleaned = (symbol or "").strip().upper()
    for rule in _SUFFIX_RULES:
        if cleaned.endswith(rule.suffix.upper()):
            return rule.market
    return default


def normalize_symbol(symbol: str) -> str:
    """記号を正規化する。

    - 前後の空白を削除
    - 数字のみの日本株コードは自動で `.T` を付与
    - それ以外は大文字化（ピリオド、ハイフン等は維持）
    """
    cleaned = (symbol or "").strip()
    if not cleaned:
        return cleaned
    if cleaned.isdigit():
        return f"{cleaned}.T"
    return cleaned.upper()

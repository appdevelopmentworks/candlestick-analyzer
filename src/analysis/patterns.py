"""TA-Libのローソク足パターン検出ユーティリティ。"""
from __future__ import annotations

from functools import lru_cache
from typing import Dict, Iterable, List, Tuple

import pandas as pd

try:  # Optional import: TA-Lib が利用できない環境では空結果を返す
    import talib as ta
except Exception:  # pragma: no cover - optional dependency
    ta = None  # type: ignore


@lru_cache()
def available_pattern_functions() -> List[str]:
    if ta is None:
        return []
    return [name for name in dir(ta) if name.startswith("CDL")]


def detect_all(df: pd.DataFrame, patterns: Iterable[str] | None = None) -> List[dict[str, int | str]]:
    hits, _ = detect_with_history(df, lookback=1, patterns=patterns)
    return hits


def detect_with_history(
    df: pd.DataFrame,
    *,
    lookback: int = 20,
    patterns: Iterable[str] | None = None,
) -> Tuple[List[dict[str, int | str]], List[dict[str, object]]]:
    if ta is None or df.empty:
        return [], []
    series_map, dates = _compute_pattern_series(df, patterns=patterns)
    if not series_map:
        return [], []
    last_index = len(dates) - 1
    hits_today: list[dict[str, int | str]] = []
    for fn, series in series_map.items():
        try:
            value = int(series.iloc[last_index])
        except Exception:
            continue
        if value != 0:
            hits_today.append({"fn": fn, "value": value})

    history: list[dict[str, object]] = []
    start = max(0, last_index - lookback + 1)
    for idx in range(start, last_index + 1):
        day_hits: list[dict[str, int | str]] = []
        for fn, series in series_map.items():
            try:
                value = int(series.iloc[idx])
            except Exception:
                continue
            if value != 0:
                day_hits.append({"fn": fn, "value": value})
        if day_hits:
            history.append({
                "date": dates[idx],
                "hits": day_hits,
            })
    return hits_today, history


def _compute_pattern_series(
    df: pd.DataFrame,
    *,
    patterns: Iterable[str] | None = None,
) -> tuple[Dict[str, pd.Series], List[pd.Timestamp]]:
    cols = {c.lower(): c for c in df.columns}
    required = [cols.get(key) for key in ("open", "high", "low", "close")]
    if any(col is None for col in required):
        return {}, []
    open_col, high_col, low_col, close_col = required  # type: ignore
    o = df[open_col]
    h = df[high_col]
    l = df[low_col]
    c = df[close_col]

    series_map: Dict[str, pd.Series] = {}
    all_functions = available_pattern_functions()
    if patterns is not None:
        enabled = set(p.upper() for p in patterns)
        functions = [fn for fn in all_functions if fn.upper() in enabled]
    else:
        functions = all_functions
    for fn in functions:
        try:
            out = getattr(ta, fn)(o, h, l, c)
        except Exception:
            continue
        if isinstance(out, pd.Series):
            series_map[fn] = out
    date_col = cols.get("date") or cols.get("datetime")
    if date_col:
        dates = pd.to_datetime(df[date_col]).tolist()
    else:
        index = df.index
        if isinstance(index, pd.DatetimeIndex):
            dates = list(index.to_pydatetime())
        else:
            dates = list(pd.to_datetime(index).to_pydatetime())
    return series_map, [pd.Timestamp(d) for d in dates]

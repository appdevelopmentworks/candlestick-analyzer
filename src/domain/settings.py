from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass
class AnalyzerUISettings:
    period_days: int = 400
    parallel_workers: int = 5
    highlight_pos: int = 4
    highlight_neg: int = -4
    history_lookback: int = 20
    auto_run: bool = False
    patterns: Tuple[str, ...] | None = None

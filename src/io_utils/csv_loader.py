"""ウォッチリストCSVを読み込むためのユーティリティ。"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List
import csv
import re

from domain.models import SymbolRecord
from io_utils.markets import infer_market, normalize_symbol
from domain.errors import AppError, app_error

TICKER_RE = re.compile(r"^[A-Za-z0-9\.\-_]+$")


def _has_header(first_row: list[str]) -> bool:
    if len(first_row) == 1 and TICKER_RE.match(first_row[0] or ""):
        return False
    headers = [(s or "").strip().lower() for s in first_row]
    if any(h in ("ticker", "symbol", "銘柄コード", "ティッカーコード") for h in headers):
        return True
    if all(TICKER_RE.match(x or "") for x in first_row):
        return False
    return True


def _record(symbol: str, name: str = "", sector: str = "") -> SymbolRecord:
    normalized = normalize_symbol(symbol)
    return SymbolRecord(
        symbol=normalized,
        name=name.strip(),
        sector=sector.strip(),
        market=infer_market(normalized),
    )


def load_symbols(path: Path) -> List[SymbolRecord]:
    """CSVを読み込み `SymbolRecord` のリストとして返す。"""
    rows: list[SymbolRecord] = []
    try:
        fh = path.open("r", encoding="utf-8-sig", newline="")
    except FileNotFoundError as exc:
        raise app_error("E-CSV-NOTFOUND", detail=str(exc)) from exc
    except UnicodeDecodeError as exc:
        raise app_error("E-CSV-ENCODING", detail=str(exc)) from exc

    with fh as f:
        rdr = csv.reader(f)
        first = next(rdr, None)
        if first is None:
            raise app_error("E-CSV-EMPTY")
        header = _has_header(first)
        if header:
            cols = [(c or "").strip().lower() for c in first]
            idx_sym = next((i for i, c in enumerate(cols) if c in ("ticker", "symbol", "銘柄コード", "ティッカーコード")), 0)
            idx_name = next((i for i, c in enumerate(cols) if c in ("name", "銘柄名")), None)
            idx_sec = next((i for i, c in enumerate(cols) if c in ("sector", "セクター")), None)
        else:
            idx_sym, idx_name, idx_sec = 0, 1, 2
            if first and len(first) > 0 and first[0]:
                rows.append(
                    _record(
                        first[0],
                        first[1] if len(first) > 1 else "",
                        first[2] if len(first) > 2 else "",
                    )
                )
        for row in rdr:
            if header:
                sym = (row[idx_sym] if len(row) > idx_sym else "").strip()
                name = (
                    row[idx_name].strip()
                    if (idx_name is not None and len(row) > idx_name)
                    else ""
                )
                sec = (
                    row[idx_sec].strip()
                    if (idx_sec is not None and len(row) > idx_sec)
                    else ""
                )
            else:
                sym = row[0].strip() if len(row) > 0 and row[0] else ""
                name = row[1].strip() if len(row) > 1 and row[1] else ""
                sec = row[2].strip() if len(row) > 2 and row[2] else ""
            if not sym:
                continue
            rows.append(_record(sym, name, sec))
    if not rows:
        raise app_error("E-CSV-EMPTY")
    return rows

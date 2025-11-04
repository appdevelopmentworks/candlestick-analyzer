"""主要指数の構成銘柄を取得するスクレイパ。"""
from __future__ import annotations

import logging
import re
from typing import Iterable, Sequence, Mapping

from io import StringIO

import pandas as pd
import requests
from bs4 import BeautifulSoup

try:  # Cloudflare対策のため任意利用
    import cloudscraper
except Exception:  # pragma: no cover - optional dependency
    cloudscraper = None

from io_utils.markets import infer_market, normalize_symbol

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Referer": "https://indexes.nikkei.co.jp/",
    "Accept-Language": "ja,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

NIKKEI_SECTORS = {
    "水産", "農林", "鉱業", "建設", "食品", "繊維", "パルプ", "紙", "化学", "医薬品",
    "石油", "石炭", "ゴム", "ガラス", "土石", "鉄鋼", "非鉄", "金属", "金属製品", "機械",
    "電気機器", "造船", "輸送用機器", "自動車", "精密機器", "その他製造", "商社", "卸売", "小売",
    "銀行", "証券", "保険", "不動産", "陸運", "海運", "空運", "倉庫", "運輸", "情報・通信",
    "通信", "電力", "ガス", "サービス",
}
NIKKEI_SECTOR_HINTS = tuple(NIKKEI_SECTORS)


def fetch_sp500() -> pd.DataFrame:
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    return _read_html(url, symbol_col="Symbol", name_col="Security", sector_col="GICS Sector")


def fetch_nikkei225() -> pd.DataFrame:
    return _read_first_available(
        (
            {
                "url": "https://indexes.nikkei.co.jp/nkave/index/component?idx=nk225",
                "parser": _scrape_nikkei_components,
                "headers": DEFAULT_HEADERS,
                "suffix": "",
            },
        ),
        suffix=".T",
    )


def fetch_nikkei500() -> pd.DataFrame:
    return _read_first_available(
        (
            {
                "url": "https://indexes.nikkei.co.jp/nkave/index/component?idx=nk500av",
                "parser": _scrape_nikkei_components,
                "headers": DEFAULT_HEADERS,
                "suffix": "",
            },
        ),
        suffix=".T",
    )


def fetch_jpx400() -> pd.DataFrame:
    return _read_first_available(
        (
            {
                "url": "https://indexes.nikkei.co.jp/nkave/index/component?idx=jpxnk400",
                "parser": _scrape_nikkei_components,
                "headers": DEFAULT_HEADERS,
                "suffix": "",
            },
        ),
        suffix=".T",
    )


def _read_first_available(
    candidates: Sequence[Mapping[str, object]],
    *,
    suffix: str | None = None,
) -> pd.DataFrame:
    for candidate in candidates:
        url = str(candidate.get("url"))
        headers = candidate.get("headers") if isinstance(candidate, dict) else None
        parser = candidate.get("parser") if isinstance(candidate, dict) else None
        parser_suffix = candidate.get("suffix") if isinstance(candidate, dict) else None
        try:
            if callable(parser):
                df = parser(url, suffix=parser_suffix or suffix, headers=headers)
            else:
                df = _read_html(
                    url,
                    symbol_col=str(candidate["symbol_col"]),
                    name_col=str(candidate["name_col"]),
                    sector_col=str(candidate["sector_col"]),
                    suffix=suffix,
                    headers=headers if isinstance(headers, dict) else None,
                )
        except Exception:
            logger.exception("Failed to fetch index constituents: %s", url)
            continue
        if not df.empty:
            return df
    logger.warning("All candidate sources failed for index fetch")
    return _empty_frame()


def _read_html(
    url: str,
    *,
    symbol_col: str,
    name_col: str,
    sector_col: str,
    suffix: str | None = None,
    headers: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    try:
        response = _request_html(url, headers)
    except Exception:
        logger.exception("Failed to download index constituents: %s", url)
        return _empty_frame()
    try:
        html_text = response.text
        tables = pd.read_html(StringIO(html_text))
    except ValueError:
        logger.exception("No tables found in %s", url)
        return _empty_frame()

    for table in tables:
        if symbol_col not in table.columns:
            continue
        try:
            df = table[[symbol_col, name_col, sector_col]].copy()
        except KeyError:
            continue
        df.columns = ["symbol", "name", "sector"]
        df["symbol"] = df["symbol"].astype(str)
        if suffix:
            df["symbol"] = df["symbol"].str.strip() + suffix
        df["symbol"] = df["symbol"].apply(normalize_symbol)
        df["name"] = df["name"].astype(str).str.strip()
        df["sector"] = df["sector"].astype(str).str.strip()
        df["market"] = df["symbol"].apply(infer_market)
        return df

    logger.warning("Target columns not found in %s", url)
    return _empty_frame()


def _scrape_nikkei_components(
    url: str,
    *,
    suffix: str | None = None,
    headers: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    response = _request_html(url, headers)
    soup = BeautifulSoup(response.text, "lxml")
    records: list[tuple[str, str, str, str]] = []

    for tbl in soup.find_all("table"):
        _parse_table_block(tbl, sector="", out_rows=records)
    if records:
        return _records_to_frame(records, suffix=suffix)

    for sector, block_nodes in _iter_sector_blocks(soup):
        inner_tables = []
        for node in block_nodes:
            if getattr(node, "name", None) == "table":
                inner_tables.append(node)
            elif hasattr(node, "select"):
                inner_tables.extend(node.select("table"))
        if inner_tables:
            for tbl in inner_tables:
                _parse_table_block(tbl, sector=sector, out_rows=records)
        _parse_text_block(block_nodes, sector=sector, out_rows=records)

    if not records:
        text_all = _norm_text(soup.get_text(" ", strip=True))
        fallback_pat = re.compile(r"(\d{4})\s+([^\s【】\[\]\(\)／/・\|｜]{1,40})")
        for match in fallback_pat.finditer(text_all):
            code, brand = match.group(1), _norm_text(match.group(2))
            records.append((code, brand, "", ""))

    if not records:
        return _empty_frame()
    return _records_to_frame(records, suffix=suffix)


def _iter_sector_blocks(soup: BeautifulSoup):
    for h3 in soup.find_all("h3"):
        sector = _norm_text(h3.get_text(" ", strip=True))
        if not any(hint in sector for hint in NIKKEI_SECTOR_HINTS):
            continue
        block_nodes = []
        for sib in h3.next_siblings:
            if getattr(sib, "name", None) == "h3":
                break
            block_nodes.append(sib)
        yield sector, block_nodes


def _parse_table_block(tbl, sector: str, out_rows: list[tuple[str, str, str, str]]) -> None:
    for tr in tbl.select("tbody tr"):
        cells = [_norm_text(td.get_text(" ", strip=True)) for td in tr.find_all("td")]
        if len(cells) >= 3 and re.fullmatch(r"\d{4}", cells[0]):
            out_rows.append((cells[0], cells[1], cells[2], sector))


def _parse_text_block(block_nodes, sector: str, out_rows: list[tuple[str, str, str, str]]) -> None:
    parts: list[str] = []
    for node in block_nodes:
        if hasattr(node, "get_text"):
            parts.append(node.get_text(" ", strip=True))
        elif isinstance(node, str):
            parts.append(node)
    text = _norm_text(" ".join(parts))
    pattern = re.compile(
        r"(?P<code>\d{4})\s+"
        r"(?P<brand>[^\s【】【\[\]\(\)／/・\|｜]{1,40})\s+"
        r"(?P<company>(?!\d)\S.{0,60}?)(?=\s+\d{4}\s+|$)"
    )
    for match in pattern.finditer(text):
        code = match.group("code")
        brand = _norm_text(match.group("brand"))
        company = _norm_text(re.sub(r"(www\.nikkei\.com|https?://\S+|【.*?】)", "", match.group("company")))
        out_rows.append((code, brand, company, sector))


def _norm_text(value: str) -> str:
    value = (value or "").replace("\u3000", " ")
    value = re.sub(r"[ \t]+", " ", value)
    return value.strip()


def _records_to_frame(records: Iterable[tuple[str, str, str, str]], suffix: str | None) -> pd.DataFrame:
    uniq: dict[tuple[str, str, str], str] = {}
    for code, brand, company, sector in records:
        uniq[(code, brand, company)] = sector
    rows = []
    for (code, brand, company), sector in uniq.items():
        symbol = code.strip()
        if suffix and not symbol.endswith(suffix):
            symbol = f"{symbol}{suffix}"
        rows.append(
            {
                "symbol": normalize_symbol(symbol),
                "name": brand.strip() or company.strip(),
                "sector": sector.strip(),
                "market": infer_market(symbol),
            }
        )
    return pd.DataFrame(rows, columns=["symbol", "name", "sector", "market"])


def _request_html(url: str, headers: Mapping[str, str] | None = None) -> requests.Response:
    merged_headers = DEFAULT_HEADERS.copy()
    if headers:
        merged_headers.update({k: v for k, v in headers.items() if v})
    if cloudscraper is not None:
        try:
            scraper = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "desktop": True})
            response = scraper.get(url, headers=merged_headers, timeout=25)
            response.raise_for_status()
            return response
        except Exception:  # pragma: no cover - fallback path
            logger.exception("cloudscraper failed, falling back to requests for %s", url)
    response = requests.get(url, headers=merged_headers, timeout=25)
    response.raise_for_status()
    return response


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["symbol", "name", "sector", "market"])

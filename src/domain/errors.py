"""アプリ全体で共通利用するエラー定義。"""
from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import yaml


_SUPPORT_DOC = "docs/ta_lib_ローソク足アナライザー｜要件定義_v_1.md"


DEFAULT_ERROR_CATALOG: Mapping[str, dict[str, str]] = {
    "E-CSV-NOTFOUND": {
        "message": "CSVファイルが見つかりません。",
        "guidance": "ファイルパスとアクセス権を確認し、必要に応じてフルパスを指定してください。",
        "support_url": _SUPPORT_DOC,
    },
    "E-CSV-ENCODING": {
        "message": "CSVを読み込めませんでした。",
        "guidance": "UTF-8 (BOM 可) 形式で保存されているか確認してください。Excel から保存する場合は UTF-8 を選択してください。",
        "support_url": _SUPPORT_DOC,
    },
    "E-CSV-EMPTY": {
        "message": "CSVに有効なティッカーがありません。",
        "guidance": "ヘッダー行とティッカー列が含まれているか確認し、サンプル `samples/watchlist_with_header.csv` を参照してください。",
        "support_url": "samples/watchlist_with_header.csv",
    },
    "E-CSV-UNKNOWN": {
        "message": "CSVの読み込みに失敗しました。",
        "guidance": "フォーマットとファイルの整合性を確認してください。",
        "support_url": _SUPPORT_DOC,
    },
    "E-INDEX-NOTFOUND": {
        "message": "指定した指数が存在しません。",
        "guidance": "メニューから提供されている指数名を選択してください。",
        "support_url": _SUPPORT_DOC,
    },
    "E-INDEX-FETCH": {
        "message": "指数の構成銘柄取得に失敗しました。",
        "guidance": "ネットワーク状態や取得元サイトの稼働状況を確認し、数分後に再実行してください。",
        "support_url": _SUPPORT_DOC,
    },
    "E-INDEX-EMPTY": {
        "message": "指数の構成銘柄を取得できませんでした。",
        "guidance": "スクレイピング元の仕様が変わっている可能性があります。ログを確認し、必要に応じて取得ロジックを更新してください。",
        "support_url": _SUPPORT_DOC,
    },
    "E-META-UNEXPECTED": {
        "message": "銘柄情報の取得に失敗しました。",
        "guidance": "外部APIのレート制限や応答変更を確認し、再試行してください。",
        "support_url": _SUPPORT_DOC,
    },
    "E-YF-404": {
        "message": "価格データを取得できませんでした。",
        "guidance": "ティッカーが正しいか確認し、マーケットサフィックス（例: .T）も含めて指定してください。",
        "support_url": "https://pypi.org/project/yfinance/",
    },
    "E-TA-LIB": {
        "message": "ローソク足パターン解析に失敗しました。",
        "guidance": "TA-Lib が正しくインストールされているかと、入力データの欠損が無いかを確認してください。",
        "support_url": "https://ta-lib.org/",
    },
    "E-ANL-UNEXPECTED": {
        "message": "解析中にエラーが発生しました。",
        "guidance": "ログの詳細を確認し、問題のある銘柄を再取得または除外してください。",
        "support_url": _SUPPORT_DOC,
    },
    "E-UNEXPECTED": {
        "message": "予期しないエラーが発生しました。",
        "guidance": "ログを確認し、再実行しても改善しない場合は開発者に問い合わせてください。",
        "support_url": _SUPPORT_DOC,
    },
}


@lru_cache()
def _load_support_links(config_path: Path = Path("config.yaml")) -> dict[str, str]:
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    links = data.get("support_links")
    return {str(k): str(v) for k, v in links.items()} if isinstance(links, dict) else {}


@lru_cache()
def _load_error_support_map(config_path: Path = Path("config.yaml")) -> dict[str, str]:
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    app_cfg = data.get("app")
    mapping = app_cfg.get("error_support") if isinstance(app_cfg, dict) else None
    return {str(k): str(v) for k, v in mapping.items()} if isinstance(mapping, dict) else {}


@dataclass(slots=True)
class AppError(Exception):
    """コード付きのアプリケーションエラー。"""

    code: str
    user_message: str | None = None
    detail: str | None = None
    symbol: str | None = None
    payload: dict[str, Any] | None = None
    guidance: str | None = None
    support_url: str | None = None

    def __post_init__(self) -> None:
        meta = DEFAULT_ERROR_CATALOG.get(self.code, {})
        if not self.user_message:
            self.user_message = meta.get("message", "エラーが発生しました。")
        if self.guidance is None:
            self.guidance = meta.get("guidance")
        if self.support_url is None:
            self.support_url = _resolve_support_url(self.code, meta.get("support_url"))

    def __str__(self) -> str:
        message = self.user_message or "エラーが発生しました。"
        base = f"[{self.code}] {message}"
        if self.symbol:
            base = f"{self.symbol}: {base}"
        if self.detail:
            return f"{base} ({self.detail})"
        return base

    def for_log(self) -> str:
        base = str(self)
        if self.payload:
            return f"{base} | payload={self.payload}"
        return base

    def with_symbol(self, symbol: str) -> "AppError":
        return replace(self, symbol=symbol)

    def ui_header(self) -> str:
        message = self.user_message or "エラーが発生しました。"
        header = f"[{self.code}] {message}"
        if self.symbol:
            header = f"{self.symbol}: {header}"
        return header

    def ui_body(self) -> str:
        parts: list[str] = []
        if self.guidance:
            parts.append(self.guidance)
        if self.support_url:
            parts.append(f"サポート: {self.support_url}")
        if self.detail:
            parts.append(f"詳細情報: {self.detail}")
        return "\n".join(parts)


def app_error(code: str, **kwargs: Any) -> AppError:
    """カタログに基づき AppError を生成する。"""

    return AppError(code=code, **kwargs)


def ensure_app_error(
    exc: Exception,
    *,
    code: str = "E-UNEXPECTED",
    message: str | None = None,
    symbol: str | None = None,
) -> AppError:
    """任意の例外を AppError へ正規化する。"""

    if isinstance(exc, AppError):
        return exc
    info = DEFAULT_ERROR_CATALOG.get(code, {})
    user_message = message or info.get("message", "予期しないエラーが発生しました。")
    return AppError(
        code=code,
        user_message=user_message,
        detail=str(exc) or None,
        symbol=symbol,
        guidance=info.get("guidance"),
        support_url=_resolve_support_url(code, info.get("support_url")),
    )


def _resolve_support_url(code: str, default_url: str | None) -> str | None:
    mapping = _load_error_support_map()
    links = _load_support_links()
    ref = mapping.get(code)
    if ref:
        return links.get(ref, default_url)
    return default_url

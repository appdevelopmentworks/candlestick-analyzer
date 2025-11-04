"""logging設定とUI向けログバッファを初期化するヘルパー。"""
from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from collections import deque
from pathlib import Path
from threading import Lock
from typing import Deque, Iterable

import yaml


_CONFIGURED = False
_UI_HANDLER: "UILogHandler" | None = None
_LOGGER_NAME = "candlestick_analyzer"


class UILogHandler(logging.Handler):
    """UIで利用するログのリングバッファ。"""

    def __init__(self, capacity: int = 200) -> None:
        super().__init__()
        self._capacity = capacity
        self._lock = Lock()
        self._buffer: Deque[str] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - ロギング側で呼ばれる
        message = self.format(record)
        with self._lock:
            self._buffer.append(message)

    def lines(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._buffer)


def configure_logging(config_path: Path = Path("config.yaml")) -> UILogHandler:
    """設定ファイルを元に logging を初期化し、UI用ハンドラを返す。"""

    global _CONFIGURED, _UI_HANDLER
    if _CONFIGURED and _UI_HANDLER is not None:
        return _UI_HANDLER

    config: dict[str, object]
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        config = {}

    # Support link / error support cachesは設定変更に追随できるようクリア
    from domain.errors import _load_support_links, _load_error_support_map

    _load_support_links.cache_clear()
    _load_error_support_map.cache_clear()

    logging_cfg = config.get("logging", {}) if isinstance(config, dict) else {}
    level_name = str(logging_cfg.get("level", "INFO")) if isinstance(logging_cfg, dict) else "INFO"
    level = getattr(logging, level_name.upper(), logging.INFO)
    path_value = logging_cfg.get("path", "logs/app.log") if isinstance(logging_cfg, dict) else "logs/app.log"
    log_path = Path(path_value)
    rotate_keep = logging_cfg.get("rotate_keep", 7) if isinstance(logging_cfg, dict) else 7
    try:
        rotate_keep = int(rotate_keep)
    except (TypeError, ValueError):
        rotate_keep = 7
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        fallback = Path.cwd() / log_path.name
        fallback.parent.mkdir(parents=True, exist_ok=True)
        log_path = fallback

    logger = logging.getLogger()
    logger.setLevel(level)

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    file_handler = TimedRotatingFileHandler(
        filename=str(log_path),
        when="midnight",
        backupCount=max(rotate_keep, 0),
        encoding="utf-8",
        utc=False,
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    ui_handler = UILogHandler()
    ui_handler.setLevel(level)
    ui_handler.setFormatter(formatter)

    # 既存ハンドラを削除して二重登録を防ぐ
    for handler in list(logger.handlers):  # pragma: no cover - 初期化時のみ
        logger.removeHandler(handler)
        handler.close()

    logger.addHandler(file_handler)
    logger.addHandler(ui_handler)

    # プロジェクト用ロガー名を揃える
    logging.getLogger(_LOGGER_NAME).setLevel(level)

    _CONFIGURED = True
    _UI_HANDLER = ui_handler
    return ui_handler


def get_ui_log_lines() -> tuple[str, ...]:
    """UI表示用のログラインを取得する。"""

    if _UI_HANDLER is None:
        return ()
    return _UI_HANDLER.lines()


def iter_handlers() -> Iterable[logging.Handler]:  # pragma: no cover - デバッグ用
    logger = logging.getLogger()
    return tuple(logger.handlers)

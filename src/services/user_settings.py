from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from domain.settings import AnalyzerUISettings


class UserSettingsStore:
    """UI設定の読み書きを行うシンプルな永続化ヘルパー。"""

    def __init__(self, path: Path | None = None) -> None:
        default_path = Path.home() / ".candlestick_analyzer" / "ui_settings.json"
        self._path = path or default_path

    def load(self) -> AnalyzerUISettings | None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except json.JSONDecodeError:
            return None
        return self._deserialize(raw)

    def save(self, settings: AnalyzerUISettings) -> None:
        payload = asdict(settings)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _deserialize(data: dict[str, Any]) -> AnalyzerUISettings:
        defaults = AnalyzerUISettings()
        patterns = data.get("patterns")
        norm_patterns: tuple[str, ...] | None
        if isinstance(patterns, (list, tuple)):
            cleaned = [str(item).upper() for item in patterns if str(item).strip()]
            norm_patterns = tuple(cleaned) if cleaned else None
        else:
            norm_patterns = None
        return AnalyzerUISettings(
            period_days=int(data.get("period_days", defaults.period_days)),
            parallel_workers=int(data.get("parallel_workers", defaults.parallel_workers)),
            highlight_pos=int(data.get("highlight_pos", defaults.highlight_pos)),
            highlight_neg=int(data.get("highlight_neg", defaults.highlight_neg)),
            history_lookback=int(data.get("history_lookback", defaults.history_lookback)),
            auto_run=bool(data.get("auto_run", defaults.auto_run)),
            patterns=norm_patterns,
        )

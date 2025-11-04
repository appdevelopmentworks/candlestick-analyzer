"""アプリ全体で利用するフォント設定ユーティリティ。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Iterable

import yaml
from matplotlib import rcParams
from matplotlib.font_manager import FontProperties, findfont


@lru_cache()
def _load_font_candidates(config_path: Path = Path("config.yaml")) -> tuple[str, ...]:
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except Exception:
        return tuple()
    fonts = config.get("app", {}).get("fonts")
    if isinstance(fonts, Iterable) and not isinstance(fonts, (str, bytes)):
        return tuple(str(f) for f in fonts)
    return tuple()


def apply_matplotlib_preferred_font() -> None:
    """設定ファイルで指定されたフォントをMatplotlibへ適用する。"""
    candidates = _load_font_candidates()
    for family in candidates:
        try:
            findfont(FontProperties(family=family), fallback_to_default=False)
        except Exception:
            continue
        rcParams["font.family"] = family
        rcParams["axes.unicode_minus"] = False
        return
    # 最後のフォールバックとして日本語対応が多いデフォルトフォントを指定
    rcParams.setdefault("font.family", "MS Gothic")
    rcParams["axes.unicode_minus"] = False

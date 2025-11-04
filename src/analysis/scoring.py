from __future__ import annotations

from collections.abc import Iterable, Mapping
from functools import lru_cache
from datetime import date
from pathlib import Path

import pandas as pd
import yaml

from domain.models import PatternHit

try:
    cfg = yaml.safe_load(open("config.yaml", "r", encoding="utf-8"))
    HIGHLIGHT_POS = int(cfg.get("scoring", {}).get("highlight_threshold_pos", 4))
    HIGHLIGHT_NEG = int(cfg.get("scoring", {}).get("highlight_threshold_neg", -4))
    CLIP_MIN = int(cfg.get("scoring", {}).get("clip_min", -5))
    CLIP_MAX = int(cfg.get("scoring", {}).get("clip_max", 5))
except Exception:
    HIGHLIGHT_POS, HIGHLIGHT_NEG, CLIP_MIN, CLIP_MAX = 4, -4, -5, 5

def _load_bias_frame() -> pd.DataFrame:
    candidates = (
        Path("resources/TA-Libロウソクパターン.csv"),
        Path("interact/TA-Libロウソクパターン.csv"),
        Path("resources/cdl_bias_ja.csv"),
    )
    for path in candidates:
        if path.exists():
            return pd.read_csv(path, encoding="utf-8-sig")
    raise FileNotFoundError("ローソク足パターン定義ファイルが見つかりません")


BIAS = _load_bias_frame()


def _base_score(fn: str, value: int) -> int:
    info = _lookup_bias(fn, value)
    try:
        return int(info.get("score", 0))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _extract(hit: PatternHit | Mapping[str, object]) -> tuple[str, int]:
    if isinstance(hit, PatternHit):
        return hit.fn, int(hit.value)
    fn = str(hit.get("fn"))  # type: ignore[arg-type]
    value = int(hit.get("value", 0))  # type: ignore[arg-type]
    return fn, value


def total_score_from_hits(hits: Iterable[PatternHit | Mapping[str, object]]) -> int:
    score = 0.0
    for raw in hits:
        fn, value = _extract(raw)
        base = abs(_base_score(fn, value)) * (1 if value > 0 else -1)
        strength = abs(value) / 100.0
        score += base * strength
    score = max(CLIP_MIN, min(CLIP_MAX, round(score)))
    return int(score)


def update_highlight_thresholds(pos: int, neg: int) -> None:
    global HIGHLIGHT_POS, HIGHLIGHT_NEG
    HIGHLIGHT_POS = pos
    HIGHLIGHT_NEG = neg


def get_highlight_thresholds() -> tuple[int, int]:
    return HIGHLIGHT_POS, HIGHLIGHT_NEG


def enrich_hits(
    hits: Iterable[Mapping[str, object]],
    *,
    at: date | None = None,
) -> list[PatternHit]:
    enriched: list[PatternHit] = []
    for raw in hits:
        fn, value = _extract(raw)
        info = _lookup_bias(fn, value)
        strength = abs(value) / 100 if value else None
        base_score = info.get("score")
        weighted = round(base_score * strength, 2) if strength is not None and base_score is not None else None
        enriched.append(
            PatternHit(
                fn=fn,
                value=value,
                strength=strength,
                base_score=base_score,
                weighted_score=weighted,
                variant=info.get("variant"),
                english=info.get("english"),
                japanese=info.get("japanese"),
                typical_setup=info.get("typical"),
                next_move=info.get("next_move"),
                description=info.get("description"),
                date=at,
            )
        )
    return enriched


def _normalize_variant(value: int) -> str:
    if value > 0:
        return "bullish"
    if value < 0:
        return "bearish"
    return "neutral"


@lru_cache()
def _bias_map() -> dict[str, dict[str, dict[str, str | int]]]:
    mapping: dict[str, dict[str, dict[str, str | int]]] = {}
    for row in BIAS.to_dict(orient="records"):
        fn = str(row.get("Function", "")).strip()
        if not fn:
            continue
        variant = str(row.get("Variant", "")).strip().lower() or "neutral"
        score = row.get("スコア（-5～+5)")
        if score is None:
            score = row.get("score")
        try:
            score = int(score) if score is not None else 0
        except (TypeError, ValueError):
            score = 0
        mapping.setdefault(fn, {})[variant] = {
            "score": score,
            "variant": row.get("Variant") or variant,
            "english": row.get("English"),
            "japanese": row.get("Japanese"),
            "typical": row.get("典型セットアップ"),
            "next_move": row.get("次の動き（傾向）"),
            "description": row.get("次の動き（傾向）") or row.get("典型セットアップ"),
        }
    return mapping


def _lookup_bias(fn: str, value: int) -> dict[str, str | int | None]:
    bias_for_fn = _bias_map().get(fn, {})
    if not bias_for_fn:
        return {"score": 0, "variant": None, "english": None, "japanese": None, "typical": None, "next_move": None, "description": None}
    variant_key = _normalize_variant(value)
    entry = bias_for_fn.get(variant_key) or bias_for_fn.get("neutral")
    if entry is None and bias_for_fn:
        entry = next(iter(bias_for_fn.values()))
    return entry or {"score": 0, "variant": None, "english": None, "japanese": None, "typical": None, "next_move": None, "description": None}


def categorize_score(score: int | None) -> tuple[str | None, str]:
    """スコアを表示用のカテゴリとラベルに変換する。"""

    if score is None:
        return None, "—"
    if score >= 3:
        return "Strong＋", f"↑↑ Strong＋ ({score:+d})"
    if score >= 1:
        return "Mild＋", f"↑ Mild＋ ({score:+d})"
    if score <= -3:
        return "Strong−", f"↓↓ Strong− ({score:+d})"
    if score <= -1:
        return "Mild−", f"↓ Mild− ({score:+d})"
    return "Neutral", "Neutral (0)"

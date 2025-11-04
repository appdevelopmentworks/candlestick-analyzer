from __future__ import annotations

from typing import Any

from domain.models import SymbolRecord
from services.metadata import MetadataService


class DummyRepo:
    def __init__(self, cache: dict[str, dict[str, Any]] | None = None) -> None:
        self._cache = cache or {}
        self.upserts: list[tuple[str, str | None, str | None, str | None]] = []

    def get_metadata(self, symbol: str) -> dict[str, Any] | None:
        return self._cache.get(symbol)

    def upsert_metadata(self, symbol: str, name: str | None, sector: str | None, market: str | None) -> None:
        self.upserts.append((symbol, name, sector, market))
        self._cache[symbol] = {
            "name": name,
            "sector": sector,
            "market": market,
        }


def test_enrich_uses_cached_metadata(monkeypatch):
    repo = DummyRepo({"AAA": {"name": "Cached", "sector": "Tech", "market": "US"}})
    service = MetadataService(repo=repo, max_workers=1)

    monkeypatch.setattr(MetadataService, "_fetch_bulk", lambda self, records: {})

    record = SymbolRecord(symbol="AAA", name="", sector="", market=None)
    enriched = service.enrich((record,))

    assert enriched[0].name == "Cached"
    assert enriched[0].sector == "Tech"
    assert enriched[0].market == "US"
    assert repo.upserts == []  # 取得済みのものは upsert されない


def test_enrich_fetches_and_upserts(monkeypatch):
    repo = DummyRepo()
    service = MetadataService(repo=repo, max_workers=1)

    def fake_fetch(self, records):
        return {
            rec.symbol: {"name": "Fetched", "sector": "Finance", "market": "JP"}
            for rec in records
        }

    monkeypatch.setattr(MetadataService, "_fetch_bulk", fake_fetch)

    record = SymbolRecord(symbol="BBB", name="", sector="", market=None)
    enriched = service.enrich((record,))

    enriched_record = enriched[0]
    assert enriched_record.name == "Fetched"
    assert enriched_record.sector == "Finance"
    assert enriched_record.market == "JP"

    assert repo.upserts == [("BBB", "Fetched", "Finance", "JP")]

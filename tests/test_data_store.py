import pandas as pd

from data.store import PricesRepo


def _prices_df():
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "open": [10.0, 11.0],
            "high": [12.0, 13.0],
            "low": [9.5, 10.5],
            "close": [11.5, 12.5],
            "volume": [1000, 1200],
        }
    )


def test_prices_repo_upsert_and_get_range(tmp_path):
    repo = PricesRepo(db_path=tmp_path / "prices.duckdb")
    repo.upsert_prices("TEST", _prices_df())

    fetched = repo.get_range("TEST")
    assert len(fetched) == 2
    assert list(fetched["close"]) == [11.5, 12.5]


def test_prices_repo_upsert_overwrite(tmp_path):
    repo = PricesRepo(db_path=tmp_path / "prices.duckdb")
    repo.upsert_prices("TEST", _prices_df())

    updated = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-03"]),
            "open": [11.5],
            "high": [13.5],
            "low": [10.0],
            "close": [12.8],
            "volume": [1300],
        }
    )
    repo.upsert_prices("TEST", updated)

    fetched = repo.get_range("TEST")
    assert len(fetched) == 2
    assert float(fetched.iloc[-1]["close"]) == 12.8

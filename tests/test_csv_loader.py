import pytest

from domain.errors import AppError
from io_utils.csv_loader import load_symbols


def test_load_symbols_success(tmp_path):
    csv_path = tmp_path / "watchlist.csv"
    csv_path.write_text("ticker,name,sector\nAAPL,Apple,Technology\n", encoding="utf-8")

    records = load_symbols(csv_path)

    assert len(records) == 1
    record = records[0]
    assert record.symbol == "AAPL"
    assert record.name == "Apple"
    assert record.sector == "Technology"
    assert record.market == "US"


def test_load_symbols_empty_raises(tmp_path):
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("\n", encoding="utf-8")

    with pytest.raises(AppError) as excinfo:
        load_symbols(csv_path)

    assert excinfo.value.code == "E-CSV-EMPTY"


def test_load_symbols_missing_file(tmp_path):
    csv_path = tmp_path / "missing.csv"

    with pytest.raises(AppError) as excinfo:
        load_symbols(csv_path)

    assert excinfo.value.code == "E-CSV-NOTFOUND"

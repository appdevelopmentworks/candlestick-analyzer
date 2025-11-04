import json

import pandas as pd
import pytest

from export.exporter import export_table


def test_export_table_csv(tmp_path):
    df = pd.DataFrame({"A": [1, 2], "B": ["x", "y"]})
    out_path = tmp_path / "output.csv"

    export_table(df, str(out_path))

    content = out_path.read_text(encoding="utf-8-sig")
    assert "A,B" in content
    assert "1,x" in content


def test_export_table_json(tmp_path):
    df = pd.DataFrame({"A": [1], "B": ["z"]})
    out_path = tmp_path / "output.json"

    export_table(df, str(out_path))

    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data == [{"A": 1, "B": "z"}]


def test_export_table_invalid_extension(tmp_path):
    df = pd.DataFrame({"value": [1]})
    out_path = tmp_path / "output.txt"

    with pytest.raises(ValueError):
        export_table(df, str(out_path))

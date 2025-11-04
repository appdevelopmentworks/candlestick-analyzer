import pytest

from domain.errors import AppError, app_error, ensure_app_error


def test_app_error_string_representation():
    err = AppError("E-TEST", "テストメッセージ", detail="detail", symbol="AAA")
    assert str(err) == "AAA: [E-TEST] テストメッセージ (detail)"
    assert "payload" not in err.for_log()


def test_ensure_app_error_wraps_generic_exception():
    original = ValueError("bad value")
    wrapped = ensure_app_error(original, code="E-WRAP", message="ラップエラー")
    assert isinstance(wrapped, AppError)
    assert wrapped.code == "E-WRAP"
    assert wrapped.user_message == "ラップエラー"
    assert "bad value" in str(wrapped)


def test_ensure_app_error_passes_through_app_error():
    err = AppError("E-PASS", "そのまま")
    assert ensure_app_error(err) is err


def test_app_error_catalog_defaults():
    err = app_error("E-CSV-EMPTY")
    assert "CSV" in err.user_message
    assert err.guidance is not None
    assert "サポート" in err.ui_body()

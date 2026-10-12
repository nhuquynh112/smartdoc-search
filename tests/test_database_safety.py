import unittest

import pytest

from tests.database_safety import require_disposable_database


@pytest.mark.parametrize("marker", ["", "smartdoc", "smartdoc_tv3_test_demo"])
def test_missing_or_invalid_runner_marker_skips_without_database_access(monkeypatch, marker):
    monkeypatch.setenv("SMARTDOC_ISOLATED_TEST_DB", marker)
    monkeypatch.setattr("tests.database_safety.database_url", lambda: pytest.fail("Must not read DB config"))
    with pytest.raises(unittest.SkipTest):
        require_disposable_database()


def test_marker_cannot_authorize_demo_database(monkeypatch):
    monkeypatch.setenv("SMARTDOC_ISOLATED_TEST_DB", "smartdoc_tv3_test_" + "a" * 32)
    monkeypatch.setattr("tests.database_safety.database_url", lambda: "dbname=smartdoc")
    with pytest.raises(RuntimeError, match="does not match"):
        require_disposable_database()


def test_exact_isolated_database_is_allowed(monkeypatch):
    name = "smartdoc_tv3_test_" + "a" * 32
    monkeypatch.setenv("SMARTDOC_ISOLATED_TEST_DB", name)
    monkeypatch.setattr("tests.database_safety.database_url", lambda: f"dbname={name}")
    require_disposable_database()

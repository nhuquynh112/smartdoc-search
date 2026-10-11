"""Verify portable exports retain retrieval semantics and safe cell content."""
import csv
from io import StringIO

import pytest

from app.result_utils import ranked_results_csv


def test_csv_preserves_vietnamese_order_scores_and_snapshot_provenance():
    recorded = {"query": "xe điện", "top_k": 10, "response": {
        "status": "ok", "index_version": "rev-235-example", "corpus_revision": 235,
        "results": [{"rank": 1, "document_id": 18, "title": 'Xe điện, "Việt Nam"',
                     "source_uri": "https://example.test/a", "score": 0.7046896896391204},
                    {"rank": 2, "document_id": 2, "title": "Đào tạo", "score": 0.13}]}}
    data = ranked_results_csv(recorded)
    assert data.startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(StringIO(data.decode("utf-8-sig"))))
    assert [row["document_id"] for row in rows] == ["18", "2"]
    assert rows[0]["query"] == "xe điện"
    assert rows[0]["title"] == 'Xe điện, "Việt Nam"'
    assert float(rows[0]["cosine_score"]) == recorded["response"]["results"][0]["score"]
    assert rows[0]["index_version"] == "rev-235-example"
    assert rows[0]["corpus_revision"] == "235"
    assert rows[0]["top_k"] == "10"
    assert rows[1]["source_uri"] == ""


@pytest.mark.parametrize("unsafe", ["=HYPERLINK(\"https://bad.test\")", " +cmd", "-formula", "@SUM(1)", "\t=2+3", "\rpayload"])
def test_csv_neutralizes_formula_cells_without_changing_numeric_rank_or_score(unsafe):
    recorded = {"query": unsafe, "top_k": 5, "response": {"status": "ok", "results": [
        {"rank": 1, "document_id": 7, "title": unsafe, "source_uri": unsafe, "score": 0.25}]}}
    row = next(csv.DictReader(StringIO(ranked_results_csv(recorded).decode("utf-8-sig"))))
    assert row["query"] == "'" + unsafe
    assert row["title"] == "'" + unsafe
    assert row["source_uri"] == "'" + unsafe
    assert row["rank"] == "1"
    assert row["cosine_score"] == "0.25"


def test_csv_rejects_unsuccessful_response():
    with pytest.raises(ValueError, match="successful"):
        ranked_results_csv({"response": {"status": "stale_index", "results": []}})

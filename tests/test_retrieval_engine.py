from __future__ import annotations

import pytest

from smartdoc.index_manager import IndexManager
from smartdoc.retrieval_engine import (
    InvalidRetrievalInputError,
    RetrievalEngine,
)


FINGERPRINT = "test-preprocessing-v1"


def make_snapshot(revision=7, documents=None, fingerprint=FINGERPRINT):
    if documents is None:
        documents = [
            {"document_id": 1, "title": "alpha", "clean_text": "alpha beta"},
            {"document_id": 2, "title": "beta", "clean_text": "beta gamma"},
            {"document_id": 3, "title": "alpha again", "clean_text": "alpha alpha"},
        ]
    return {
        "documents": documents,
        "corpus_revision": revision,
        "corpus_name": None,
        "preprocessing": {"fingerprint": fingerprint, "settings": {}},
    }


def make_engine(tmp_path, snapshot_ref=None, preprocessing_fn=None):
    snapshot_ref = snapshot_ref or {"value": make_snapshot()}
    loader = lambda corpus_name: snapshot_ref["value"]
    manager = IndexManager(
        index_root=tmp_path / "tv2-index",
        snapshot_loader=loader,
    )
    engine = RetrievalEngine(
        index_manager=manager,
        snapshot_loader=loader,
        preprocessing_fn=preprocessing_fn or (lambda text: " ".join(text.lower().split())),
    )
    return engine, manager, snapshot_ref


def test_search_query_returns_contract_and_ranks_results(tmp_path):
    engine, manager, _ = make_engine(tmp_path)
    manager.build_and_activate()
    result = engine.search_query("alpha", 5)

    assert set(result) == {
        "status", "message", "results", "index_version", "corpus_revision"
    }
    assert result["status"] == "ok"
    assert result["corpus_revision"] == 7
    assert result["index_version"].startswith("rev-7-")
    assert result["results"]
    assert all(set(row) == {"document_id", "score", "rank"} for row in result["results"])
    assert [row["rank"] for row in result["results"]] == list(
        range(1, len(result["results"]) + 1)
    )
    assert all(row["score"] > 0 for row in result["results"])


def test_empty_query_does_not_need_database_or_index(tmp_path):
    def broken_loader(_):
        raise RuntimeError("database offline")

    engine = RetrievalEngine(
        index_manager=IndexManager(index_root=tmp_path / "index"),
        snapshot_loader=broken_loader,
        preprocessing_fn=lambda text: "   ",
    )
    result = engine.search_query("  ")
    assert result["status"] == "empty_query"
    assert result["results"] == []


def test_oov_query_has_explicit_status(tmp_path):
    engine, manager, _ = make_engine(tmp_path)
    manager.build_and_activate()
    result = engine.search_query("notinvocabulary")
    assert result["status"] == "oov_query"
    assert result["results"] == []


def test_empty_corpus_status(tmp_path):
    snapshot_ref = {"value": make_snapshot(documents=[])}
    engine, manager, _ = make_engine(tmp_path, snapshot_ref)
    manager.build_and_activate()
    result = engine.search_query("alpha")
    assert result["status"] == "empty_corpus"
    assert result["results"] == []


def test_unavailable_index_status(tmp_path):
    engine, _, _ = make_engine(tmp_path)
    result = engine.search_query("alpha")
    assert result["status"] == "index_unavailable"
    assert result["results"] == []


def test_stale_revision_never_returns_old_results(tmp_path):
    engine, manager, snapshot_ref = make_engine(tmp_path)
    manager.build_and_activate()
    snapshot_ref["value"] = make_snapshot(revision=8)

    result = engine.search_query("alpha")
    assert result["status"] == "stale_index"
    assert result["results"] == []
    assert result["corpus_revision"] == 8


def test_stale_preprocessing_fingerprint_never_returns_old_results(tmp_path):
    engine, manager, snapshot_ref = make_engine(tmp_path)
    manager.build_and_activate()
    snapshot_ref["value"] = make_snapshot(fingerprint="different-fingerprint")

    result = engine.search_query("alpha")
    assert result["status"] == "stale_index"
    assert result["results"] == []



@pytest.mark.parametrize("top_k", [0, -1, 21, True, 1.5, "5"])
def test_invalid_top_k_raises(top_k, tmp_path):
    engine, _, _ = make_engine(tmp_path)
    with pytest.raises(InvalidRetrievalInputError):
        engine.search_query("alpha", top_k)


def test_preprocessing_function_is_used_before_search(tmp_path):
    engine, manager, _ = make_engine(
        tmp_path,
        preprocessing_fn=lambda text: "alpha" if text == "raw Vietnamese query" else text,
    )
    manager.build_and_activate()
    result = engine.search_query("raw Vietnamese query")
    assert result["status"] == "ok"
    assert result["results"]


def test_invalid_query_type_raises(tmp_path):
    engine, _, _ = make_engine(tmp_path)
    with pytest.raises(InvalidRetrievalInputError):
        engine.search_query(None)  # type: ignore[arg-type]


def test_explain_result_returns_term_weights_and_contributions(tmp_path):
    engine, manager, _ = make_engine(tmp_path)
    manager.build_and_activate()

    explanation = engine.explain_result("alpha beta", 1)

    assert explanation["status"] == "ok"
    assert explanation["document_id"] == 1
    assert explanation["query_tokens"] == ["alpha", "beta"]
    assert explanation["score"] == pytest.approx(
        sum(term["contribution"] for term in explanation["matched_terms"])
    )
    assert {term["term"] for term in explanation["matched_terms"]} == {"alpha", "beta"}
    assert all(
        term["contribution"] == pytest.approx(term["query_weight"] * term["document_weight"])
        for term in explanation["matched_terms"]
    )


def test_explain_result_unknown_document_id(tmp_path):
    engine, manager, _ = make_engine(tmp_path)
    manager.build_and_activate()

    explanation = engine.explain_result("alpha", 999)
    assert explanation["status"] == "document_not_found"
    assert explanation["matched_terms"] == []
    assert explanation["score"] is None


def test_explain_result_rejects_invalid_document_id(tmp_path):
    engine, _, _ = make_engine(tmp_path)
    with pytest.raises(InvalidRetrievalInputError):
        engine.explain_result("alpha", True)


def test_explain_result_respects_stale_index_guard(tmp_path):
    engine, manager, snapshot_ref = make_engine(tmp_path)
    manager.build_and_activate()
    snapshot_ref["value"] = make_snapshot(revision=8)

    explanation = engine.explain_result("alpha", 1)
    assert explanation["status"] == "stale_index"
    assert explanation["matched_terms"] == []

"""UI adapter integration against real persisted TF-IDF, without database writes."""
from copy import deepcopy

import pytest

from app.search_service import SearchService
from smartdoc.index_manager import IndexBuildError
from smartdoc.retrieval_engine import InvalidRetrievalInputError


def snapshot(revision=7, fingerprint="test-v1", corpus_name=None, documents=None):
    return {
        "corpus_revision": revision, "corpus_name": corpus_name,
        "preprocessing": {"fingerprint": fingerprint, "settings": {}},
        "documents": documents if documents is not None else [
            {"document_id": 10, "title": "Alpha ten", "category": "Science", "clean_text": "alpha beta"},
            {"document_id": 2, "title": "Alpha two", "category": "Science", "clean_text": "alpha beta"},
            {"document_id": 30, "title": "Gamma", "category": "News", "clean_text": "gamma"},
        ],
    }


@pytest.fixture
def service(tmp_path):
    current = {"value": snapshot(), "reads": 0}

    def load(_):
        current["reads"] += 1
        return deepcopy(current["value"])

    def metadata(ids):
        return [{"document_id": doc_id, "title": f"Metadata {doc_id}",
                 "source_uri": f"https://example.test/{doc_id}", "word_count": 2,
                 "rank": 999, "score": -1}
                for doc_id in reversed(ids)]

    adapter = SearchService(tmp_path / "index", snapshot_loader=load,
                            metadata_loader=metadata,
                            preprocessing_fn=lambda text: " ".join(text.lower().split()))
    return adapter, current


def test_missing_index_and_empty_query(service):
    adapter, current = service
    assert adapter.status()["status"] == "index_unavailable"
    current["reads"] = 0
    assert adapter.search("   ")["status"] == "empty_query"
    assert current["reads"] == 0
    assert adapter.search("alpha")["results"] == []


def test_rebuild_search_preserves_rank_score_and_snapshot_category(service):
    adapter, _ = service
    built = adapter.rebuild()
    assert built["status"] == "ok" and built["rebuilt"]
    assert built["document_count"] == 3
    response = adapter.search("alpha", 5)
    assert response["status"] == "ok"
    assert [hit["document_id"] for hit in response["results"]] == [2, 10]
    assert [hit["rank"] for hit in response["results"]] == [1, 2]
    assert all(hit["score"] > 0 and hit["category"] == "Science" for hit in response["results"])
    assert response["results"][0]["title"] == "Metadata 2"
    assert response["index_version"] == built["index_version"]


@pytest.mark.parametrize("change", [
    {"corpus_revision": 8},
    {"preprocessing": {"fingerprint": "different"}},
    {"corpus_name": "another-corpus"},
    {"documents": [{"document_id": 55, "title": "Other", "clean_text": "alpha"}]},
])
def test_uncached_freshness_rejects_changes(service, change):
    adapter, current = service
    adapter.rebuild()
    current["value"].update(change)
    assert adapter.status()["status"] == "stale_index"
    response = adapter.search("alpha")
    assert response["status"] == "stale_index" and response["results"] == []


def test_database_failure_after_prior_success_does_not_serve_cached_results(service):
    adapter, _ = service
    adapter.rebuild()
    assert adapter.search("alpha")["status"] == "ok"

    def offline(_):
        raise OSError("database offline")

    adapter.snapshot_loader = offline
    response = adapter.search("alpha")
    assert response["status"] == "index_unavailable" and response["results"] == []


def test_oov_and_empty_corpus(service):
    adapter, current = service
    adapter.rebuild()
    assert adapter.search("unseenword")["status"] == "oov_query"
    current["value"] = snapshot(revision=8, documents=[])
    rebuilt = adapter.rebuild()
    assert rebuilt["status"] == "empty_corpus" and rebuilt["rebuilt"]
    assert adapter.search("alpha")["status"] == "empty_corpus"


@pytest.mark.parametrize("top_k", [0, 21, True, "5", 1.5])
def test_invalid_input_rejected_even_without_index(service, top_k):
    adapter, _ = service
    with pytest.raises(InvalidRetrievalInputError):
        adapter.search("alpha", top_k)


@pytest.mark.parametrize("metadata", [[], [{"document_id": 999}],
    [{"document_id": 2}, {"document_id": 2}, {"document_id": 10}]])
def test_missing_unexpected_or_duplicate_metadata_fails_closed(service, metadata):
    adapter, _ = service
    adapter.rebuild()
    adapter.metadata_loader = lambda _: metadata
    response = adapter.search("alpha")
    assert response["status"] == "index_unavailable" and response["results"] == []


def test_change_during_metadata_read_discards_results(service):
    adapter, current = service
    adapter.rebuild()
    original_loader = adapter.metadata_loader

    def changed(ids):
        current["value"]["corpus_revision"] += 1
        return original_loader(ids)

    adapter.metadata_loader = changed
    response = adapter.search("alpha")
    assert response["status"] == "stale_index" and response["results"] == []


def test_rebuild_failure_retains_previous_version(service, monkeypatch):
    adapter, _ = service
    built = adapter.rebuild()

    def failed(_):
        raise IndexBuildError("disk full")

    monkeypatch.setattr(adapter.index_manager, "build_and_activate", failed)
    response = adapter.rebuild()
    assert response["status"] == "rebuild_failed" and not response["rebuilt"]
    assert adapter.status()["index_version"] == built["index_version"]
    assert adapter.search("alpha")["status"] == "ok"


def test_corpus_change_during_rebuild_cannot_report_success(service, monkeypatch):
    adapter, current = service
    build = adapter.index_manager.build_and_activate

    def changed(selector):
        managed = build(selector)
        current["value"]["corpus_revision"] += 1
        return managed

    monkeypatch.setattr(adapter.index_manager, "build_and_activate", changed)
    response = adapter.rebuild()
    assert response["status"] == "stale_index" and not response["rebuilt"]
    assert adapter.search("alpha")["results"] == []


def test_explanation_uses_actual_postings_and_contributions(service):
    adapter, _ = service
    version = adapter.rebuild()["index_version"]
    response = adapter.explain("alpha beta unknown", 2, expected_version=version)
    assert response["status"] == "ok"
    assert response["posting_lists"] == {"alpha": [2, 10], "beta": [2, 10], "unknown": []}
    assert response["candidate_ids"] == [2, 10]
    assert response["score"] == pytest.approx(sum(row["contribution"] for row in response["matched_terms"]))


def test_explanation_rejects_same_revision_new_index_version(service):
    adapter, _ = service
    old_version = adapter.rebuild()["index_version"]
    adapter.rebuild()
    response = adapter.explain("alpha", 2, expected_version=old_version)
    assert response["status"] == "stale_index"
    assert response["score"] is None and response["matched_terms"] == []
    assert response["posting_lists"] == {} and response["candidate_ids"] == []


def test_new_service_can_read_persisted_index_after_restart(service):
    adapter, _ = service
    adapter.rebuild()
    restarted = SearchService(adapter.index_root, snapshot_loader=adapter.snapshot_loader,
                              metadata_loader=adapter.metadata_loader,
                              preprocessing_fn=adapter.preprocessing_fn)
    assert restarted.search("alpha")["results"] == adapter.search("alpha")["results"]
    assert restarted.mutation_lock is adapter.mutation_lock


def test_index_root_can_be_isolated_by_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("SMARTDOC_INDEX_ROOT", str(tmp_path / "configured"))
    assert SearchService().index_root == (tmp_path / "configured").resolve()
    assert SearchService(tmp_path / "explicit").index_root == (tmp_path / "explicit").resolve()

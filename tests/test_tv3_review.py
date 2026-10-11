"""Reviewer workflow uses synthetic labels only and never writes the demo DB."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

import app.evaluation_review as review_module
from app.evaluation_review import ReviewConflictError, ReviewStore
from evaluation import EvaluationInputError, JUDGMENT_FIELDS, QUERY_FIELDS, write_csv
from scripts.prepare_evaluation import prepare


@pytest.fixture
def review(tmp_path):
    snapshot = {"corpus_name": None, "corpus_revision": 3,
                "preprocessing": {"fingerprint": "test-v1", "settings": {}},
                "documents": [
                    {"document_id": 1, "title": "Alpha", "clean_text": "alpha beta", "preprocessing_version": "test-v1"},
                    {"document_id": 2, "title": "Gamma", "clean_text": "gamma delta", "preprocessing_version": "test-v1"},
                ]}
    queries = [{**dict.fromkeys(QUERY_FIELDS, ""), "query_id": f"Q{i:02d}", "query": f"alpha {i}",
                "information_need": f"Find independent information need {i}", "provenance": "Synthetic test fixture"}
               for i in range(20)]
    directory = tmp_path / "kit"
    prepare(snapshot, directory, queries=queries)
    current = {"snapshot": snapshot, "raw_reads": []}
    raw = {1: "Original full text: alpha is NOT beta.", 2: "Original full text: gamma and delta."}

    def text_loader(doc_id):
        current["raw_reads"].append(doc_id)
        return raw[doc_id]

    store = ReviewStore(directory, snapshot_loader=lambda _: deepcopy(current["snapshot"]),
                        text_loader=text_loader, coverage_checker=lambda _snapshot, _queries: {})
    return store, current


def write_protocol(store, **updates):
    path = store.directory / "protocol.json"
    protocol = json.loads(path.read_text(encoding="utf-8"))
    protocol.update(updates)
    path.write_text(json.dumps(protocol), encoding="utf-8")


def judgment(kit, qid="Q00", doc_id=1):
    return next(row for row in kit["judgments"] if row["query_id"] == qid and int(row["document_id"]) == doc_id)


def test_initial_kit_is_blank_and_reads_original_text(review):
    store, current = review
    kit = store.load()
    assert store.progress(kit)["completed_pairs"] == 0
    assert all(not row["relevant"] and not row["assessor_a"] for row in kit["judgments"])
    assert "NOT" in store.read_document(kit, 1)
    assert kit["snapshot"]["documents"][0]["clean_text"] == "alpha beta"
    assert current["raw_reads"] == [1]


def test_explicit_human_save_records_evidence_and_keeps_corpus_manifest(review):
    store, current = review
    before = (store.directory / "corpus_manifest.json").read_bytes()
    corpus_before = deepcopy(current["snapshot"])
    store.save_assessment(store.load()["token"], "Q00", 1,
                          assessor="Synthetic Alice", label="1", evidence="Original says NOT beta.")
    kit = store.load()
    row = judgment(kit)
    assert row["label_a"] == row["relevant"] == "1"
    assert row["assessor_a"] == "Synthetic Alice"
    assert row["evidence"] == "Original says NOT beta."
    assert row["labeled_at"].endswith("+00:00")
    assert store.progress(kit)["completed_pairs"] == 1
    assert (store.directory / "corpus_manifest.json").read_bytes() == before
    assert current["snapshot"] == corpus_before


@pytest.mark.parametrize("assessor,label,evidence", [("", "0", ""), ("Codex", "1", "Text"),
                                                       ("Synthetic Alice", "1", ""), ("Synthetic Alice", "2", "Text")])
def test_incomplete_or_automatic_assessments_are_refused(review, assessor, label, evidence):
    store, _ = review
    before = (store.directory / "relevance_judgments.csv").read_bytes()
    with pytest.raises(EvaluationInputError):
        store.save_assessment(store.load()["token"], "Q00", 1,
                              assessor=assessor, label=label, evidence=evidence)
    assert (store.directory / "relevance_judgments.csv").read_bytes() == before


def test_blank_label_clears_only_explicit_decision(review):
    store, _ = review
    store.save_assessment(store.load()["token"], "Q00", 1, assessor="Synthetic Alice", label="0")
    store.save_assessment(store.load()["token"], "Q00", 1, assessor="", label="")
    row = judgment(store.load())
    assert not row["label_a"] and not row["relevant"] and not row["labeled_at"]


def test_optimistic_conflict_preserves_other_sessions_update(review):
    store, _ = review
    stale = store.load()
    store.save_assessment(stale["token"], "Q00", 1, assessor="Synthetic Alice", label="0")
    with pytest.raises(ReviewConflictError):
        store.save_assessment(stale["token"], "Q00", 2, assessor="Synthetic Bob", label="0")
    assert judgment(store.load(), doc_id=1)["assessor_a"] == "Synthetic Alice"
    assert judgment(store.load(), doc_id=2)["relevant"] == ""


def test_cross_process_lock_does_not_get_deleted_by_losing_session(review):
    store, _ = review
    lock = store.directory / ".evaluation_review.lock"
    lock.write_text("Another process", encoding="utf-8")
    with pytest.raises(ReviewConflictError):
        store.save_assessment(store.load()["token"], "Q00", 1, assessor="Synthetic Alice", label="0")
    assert lock.read_text(encoding="utf-8") == "Another process"


def test_failed_atomic_replace_preserves_old_csv_and_cleans_owned_temp(review, monkeypatch):
    store, _ = review
    old = (store.directory / "relevance_judgments.csv").read_bytes()

    def disk_failed(_source, _target):
        raise OSError("Synthetic disk failure")

    monkeypatch.setattr(review_module.os, "replace", disk_failed)
    with pytest.raises(OSError):
        store.save_assessment(store.load()["token"], "Q00", 1, assessor="Synthetic Alice", label="0")
    assert (store.directory / "relevance_judgments.csv").read_bytes() == old
    assert not list(store.directory.glob(".*.tmp"))
    assert not (store.directory / ".evaluation_review.lock").exists()


def test_live_corpus_change_refuses_all_saves(review):
    store, current = review
    kit = store.load()
    current["snapshot"]["corpus_revision"] += 1
    before = (store.directory / "relevance_judgments.csv").read_bytes()
    with pytest.raises(EvaluationInputError, match="Frozen corpus mismatch"):
        store.save_assessment(kit["token"], "Q00", 1, assessor="Synthetic Alice", label="0")
    assert (store.directory / "relevance_judgments.csv").read_bytes() == before


def test_corpus_change_during_text_read_is_detected(review):
    store, current = review
    kit = store.load()

    def changed(_doc_id):
        current["snapshot"]["corpus_revision"] += 1
        return "Original content"

    store.text_loader = changed
    with pytest.raises(EvaluationInputError, match="Frozen corpus mismatch"):
        store.read_document(kit, 1)


def test_missing_original_text_is_not_replaced_with_index_tokens(review):
    store, _ = review
    store.text_loader = lambda _: ""
    with pytest.raises(EvaluationInputError, match="nội dung gốc"):
        store.save_assessment(store.load()["token"], "Q00", 1, assessor="Synthetic Alice", label="0")
    assert not judgment(store.load())["relevant"]


def test_editing_query_semantics_invalidates_existing_bindings(review):
    store, _ = review
    kit = store.load()
    kit["queries"][0]["information_need"] = "Different need"
    write_csv(store.directory / "evaluation_queries.csv", QUERY_FIELDS, kit["queries"])
    with pytest.raises(EvaluationInputError, match="Nội dung truy vấn"):
        store.load()


def test_independent_full_corpus_expansion_adds_only_explicit_pair(review):
    store, _ = review
    kit = store.load()
    remaining = [row for row in kit["judgments"] if not (row["query_id"] == "Q00" and row["document_id"] == "2")]
    write_csv(store.directory / "relevance_judgments.csv", JUDGMENT_FIELDS, remaining)
    store.save_assessment(store.load()["token"], "Q00", 2, assessor="Synthetic Alice", label="0")
    updated = store.load()
    assert len(updated["judgments"]) == len(kit["judgments"])
    assert judgment(updated, doc_id=2)["query_semantic_sha256"] == judgment(updated)["query_semantic_sha256"]


def test_two_assessors_disagreement_requires_explicit_adjudication(review):
    store, _ = review
    write_protocol(store, assessor_count=2)
    store.save_assessment(store.load()["token"], "Q00", 1, assessor="Synthetic Alice", label="1", evidence="Original answers the need.")
    with pytest.raises(EvaluationInputError, match="hai người"):
        store.adjudicate(store.load()["token"], "Q00", 1, relevant="1", adjudicator="Synthetic Reviewer", resolution="Premature review.")
    with pytest.raises(EvaluationInputError, match="độc lập"):
        store.save_assessment(store.load()["token"], "Q00", 1, assessor="synthetic alice", slot="b", label="0")
    store.save_assessment(store.load()["token"], "Q00", 1, assessor="Synthetic Bob", slot="b", label="0")
    kit = store.load()
    assert judgment(kit)["relevant"] == ""
    assert store.progress(kit)["unresolved_disagreements"] == 1
    store.adjudicate(kit["token"], "Q00", 1, relevant="1", adjudicator="Synthetic Reviewer", resolution="Content answers the stated need.")
    row = judgment(store.load())
    assert row["relevant"] == "1" and row["adjudicator"] == "Synthetic Reviewer"
    assert row["label_a"] == "1" and row["label_b"] == "0"


def test_query_and_protocol_approval_need_explicit_real_names_and_independence(review):
    store, _ = review
    token = store.load()["token"]
    with pytest.raises(EvaluationInputError):
        store.save_query_review(token, "Q00", author="", reviewer="", approved=True)
    store.save_query_review(token, "Q00", author="Synthetic Author", reviewer="Synthetic Reviewer", approved=True)
    query = store.load()["queries"][0]
    assert query["review_status"] == "approved" and query["reviewed_at"].endswith("+00:00")
    with pytest.raises(EvaluationInputError):
        store.save_protocol_review(store.load()["token"], reviewer="Synthetic Reviewer", approved=True,
                                   independent_content_review=False, disagreement_policy="Read full text.")
    store.save_protocol_review(store.load()["token"], reviewer="Synthetic Reviewer", approved=True,
                               independent_content_review=True, disagreement_policy="Read full text.")
    assert store.load()["protocol"]["status"] == "approved"


def approve_synthetic_fixture(store):
    # This intentionally fabricated labeling fixture stays inside tmp_path.
    # It is only for validating code, never written into the project's kit.
    kit = store.load()
    stamp = "2026-10-11T00:00:00+00:00"
    for query in kit["queries"]:
        query.update(author="Synthetic Author", reviewed_by="Synthetic Reviewer",
                     review_status="approved", reviewed_at=stamp)
    for row in kit["judgments"]:
        label = "1" if row["document_id"] == "1" else "0"
        row.update(label_a=label, relevant=label, assessor_a="Synthetic Alice", labeled_at=stamp,
                   evidence="Synthetic test evidence." if label == "1" else "")
    write_csv(store.directory / "evaluation_queries.csv", QUERY_FIELDS, kit["queries"])
    write_csv(store.directory / "relevance_judgments.csv", JUDGMENT_FIELDS, kit["judgments"])
    write_protocol(store, status="approved", independent_of_retrieval_scores=True,
                   reviewed_by="Synthetic Reviewer", reviewed_at=stamp)


def test_readiness_rejects_draft_and_accepts_fully_reviewed_synthetic_fixture(review):
    store, _ = review
    with pytest.raises(EvaluationInputError, match="draft"):
        store.check_readiness(store.load()["token"])
    approve_synthetic_fixture(store)
    result = store.check_readiness(store.load()["token"])
    assert result["approved_queries"] == 20 and result["completed_pairs"] == 40
    assert "precision_at_5" not in result and "mrr_at_20" not in result


def test_readiness_rejects_missing_actual_pooled_coverage(review):
    store, _ = review
    approve_synthetic_fixture(store)
    write_protocol(store, judgment_scope="pooled_top20")
    kit = store.load()
    judgments = [row for row in kit["judgments"] if not (row["query_id"] == "Q00" and row["document_id"] == "2")]
    write_csv(store.directory / "relevance_judgments.csv", JUDGMENT_FIELDS, judgments)
    store.coverage_checker = lambda _snapshot, _queries: {"Q00": [1, 2]}
    with pytest.raises(EvaluationInputError, match="Top-20"):
        store.check_readiness(store.load()["token"])


def test_streamlit_review_does_not_infer_labels_and_saves_an_explicit_decision(review, monkeypatch):
    from streamlit.testing.v1 import AppTest

    store, _ = review
    monkeypatch.setattr(review_module, "ReviewStore", lambda *_args, **_kwargs: store)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app/review.py"), default_timeout=15)
    app.session_state["review_directory"] = str(store.directory)
    app.run()
    assert not app.exception
    assert app.text_input(key="review_assessor").value == ""
    assert any("Original full text" in element.value for element in app.text)
    assert not any("Synthetic Alice" in str(element.value) for element in app.text)
    assert store.progress(store.load())["completed_pairs"] == 0
    app.text_input(key="review_assessor").set_value("Synthetic Alice").run()
    decision = next(widget for widget in app.selectbox if widget.label == "Quyết định của tôi")
    decision.select("1")
    next(widget for widget in app.text_area if widget.label == "Bằng chứng từ nội dung").set_value("Original answers the independent need.")
    next(widget for widget in app.button if widget.label == "Lưu quyết định").click().run()
    assert not app.exception
    assert store.progress(store.load())["completed_pairs"] == 1
    assert judgment(store.load())["assessor_a"] == "Synthetic Alice"


def test_streamlit_submit_keeps_original_form_token_and_refuses_lost_update(review, monkeypatch):
    from streamlit.testing.v1 import AppTest

    store, _ = review
    monkeypatch.setattr(review_module, "ReviewStore", lambda *_args, **_kwargs: store)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app/review.py"), default_timeout=15)
    app.session_state["review_directory"] = str(store.directory)
    app.run()
    store.save_assessment(store.load()["token"], "Q00", 1, assessor="Synthetic Other", label="0")
    app.text_input(key="review_assessor").set_value("Synthetic Alice").run()
    next(widget for widget in app.selectbox if widget.label == "Quyết định của tôi").select("1")
    next(widget for widget in app.text_area if widget.label == "Bằng chứng từ nội dung").set_value("Changed decision")
    next(widget for widget in app.button if widget.label == "Lưu quyết định").click().run()
    assert not app.exception
    assert app.warning and "Dữ liệu đã đổi" in app.warning[0].value
    assert judgment(store.load())["assessor_a"] == "Synthetic Other"


def test_streamlit_hides_other_assessment_until_both_people_have_decided(review, monkeypatch):
    from streamlit.testing.v1 import AppTest

    store, _ = review
    write_protocol(store, assessor_count=2)
    store.save_assessment(store.load()["token"], "Q00", 1, assessor="Synthetic Alice", label="1", evidence="Private first assessment evidence.")
    monkeypatch.setattr(review_module, "ReviewStore", lambda *_args, **_kwargs: store)

    def open_app():
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app/review.py"), default_timeout=15)
        app.session_state["review_directory"] = str(store.directory)
        app.session_state["review_role"] = "b"
        app.session_state["review_pending"] = False
        return app.run()

    app = open_app()
    assert not app.exception
    assert not any(toggle.label == "Mở phần phân xử bất đồng" for toggle in app.toggle)
    assert not app.json
    assert not any("Private first assessment" in str(element.value) for element in app.text)
    assert next(widget for widget in app.selectbox if widget.label == "Quyết định của tôi").value == ""
    store.save_assessment(store.load()["token"], "Q00", 1, assessor="Synthetic Bob", slot="b", label="0")
    app = open_app()
    assert not app.exception
    next(toggle for toggle in app.toggle if toggle.label == "Mở phần phân xử bất đồng").set_value(True).run()
    assert app.json and json.loads(app.json[0].value)["Nhãn A"] == "1"


def test_streamlit_original_text_failure_disables_save_and_redacts_credentials(review, monkeypatch):
    from streamlit.testing.v1 import AppTest

    store, _ = review

    def unavailable(_document_id):
        raise OSError("Original text failed postgresql://user:fakeSecret@localhost/db password='fake\\'Secret'")

    store.text_loader = unavailable
    monkeypatch.setattr(review_module, "ReviewStore", lambda *_args, **_kwargs: store)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app/review.py"), default_timeout=15)
    app.session_state["review_directory"] = str(store.directory)
    app.run()
    assert not app.exception
    assert app.error and "nội dung gốc" in app.error[0].value
    assert "fake" not in app.error[0].value
    assert "postgresql://***" in app.error[0].value and "password=***" in app.error[0].value
    assert next(button for button in app.button if button.label == "Lưu quyết định").disabled
    assert store.progress(store.load())["completed_pairs"] == 0


def test_streamlit_storage_path_respects_project_configuration(review, monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest
    import smartdoc.config as config

    store, _ = review
    expected_root = tmp_path / "configured-storage"
    received = []

    def configured_store(_directory, **kwargs):
        received.append(kwargs["storage_root"])
        return store

    monkeypatch.setattr(config, "storage_root", lambda: expected_root)
    monkeypatch.setattr(review_module, "ReviewStore", configured_store)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app/review.py"), default_timeout=15)
    app.session_state["review_directory"] = str(store.directory)
    app.run()
    assert not app.exception
    assert received == [expected_root]


def test_readiness_keeps_all_negative_pool_query_for_expanded_human_assessment(review):
    store, _ = review
    approve_synthetic_fixture(store)
    write_protocol(store, judgment_scope="pooled_top20")
    kit = store.load()
    for row in kit["judgments"]:
        if row["query_id"] == "Q00":
            row.update(label_a="0", relevant="0", evidence="")
    write_csv(store.directory / "relevance_judgments.csv", JUDGMENT_FIELDS, kit["judgments"])
    with pytest.raises(EvaluationInputError, match="Expand independent content assessment"):
        store.check_readiness(store.load()["token"])
    assert len(store.load()["queries"]) == 20

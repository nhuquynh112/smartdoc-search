"""Headless UI interactions with explicit service doubles, never database writes."""
from copy import deepcopy
from pathlib import Path
from threading import RLock
from unittest.mock import Mock

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest


DOCUMENTS = [
    {"document_id": 2, "title": "Xe điện Việt Nam", "category": "Công nghệ",
     "clean_text": "năng_lượng giao_thông xanh", "word_count": 9,
     "source_uri": "https://example.test/xe-dien"},
    {"document_id": 10, "title": "Giáo dục mới", "category": "Giáo dục",
     "clean_text": "giáo_dục học_sinh", "word_count": 8,
     "source_uri": ""},
]
APP_PATH = Path(__file__).resolve().parents[1] / "app" / "main.py"


class FakeSearchService:
    def __init__(self):
        self.state = {"status": "ok", "message": "ready", "index_version": "test-version-1",
                      "corpus_revision": 7, "document_count": 2}
        self.search_calls = []
        self.rebuild_outcomes = []
        self.mutation_lock = RLock()

    def status(self):
        return deepcopy(self.state)

    def search(self, query, top_k=5):
        self.search_calls.append((query, top_k))
        response = {**self.state, "results": []}
        if not query.strip():
            response["status"] = "empty_query"
        elif query == "ngoaituvung":
            response["status"] = "oov_query"
        elif self.state["status"] == "ok":
            response["results"] = [
                {**deepcopy(DOCUMENTS[0]), "rank": 1, "score": 0.812345},
                {**deepcopy(DOCUMENTS[1]), "rank": 2, "score": 0.123456},
            ][:top_k]
        return response

    def rebuild(self):
        outcome = self.rebuild_outcomes.pop(0) if self.rebuild_outcomes else "ok"
        if outcome == "rebuild_failed":
            return {**self.state, "status": outcome, "rebuilt": False, "message": "disk full"}
        self.state.update(status="ok", index_version="test-version-2")
        return {**self.state, "rebuilt": True}

    def explain(self, query, document_id, expected_version=None):
        assert expected_version == self.state["index_version"]
        return {**self.state, "document_id": document_id, "query_tokens": ["xe_điện"],
                "matched_terms": [{"term": "xe_điện", "query_weight": 1.,
                                   "document_weight": 0.812345, "contribution": 0.812345}],
                "score": 0.812345, "posting_lists": {"xe_điện": [2]}, "candidate_ids": [2]}


@pytest.fixture
def app_environment(monkeypatch):
    # Import real module, then replace only its I/O API functions.
    import app.search_service
    import smartdoc.ingestion

    st.cache_data.clear()
    st.cache_resource.clear()
    snapshot = Mock(return_value={"documents": deepcopy(DOCUMENTS), "corpus_revision": 7})
    metadata = Mock(side_effect=lambda ids: [deepcopy(row) for row in DOCUMENTS if row["document_id"] in ids])
    content = Mock(return_value="Xe điện dùng năng lượng sạch. <script>alert('x')</script>")
    ingest = Mock(side_effect=AssertionError("UI tests must not write to the database"))
    fake_service = FakeSearchService()
    monkeypatch.setattr(smartdoc.ingestion, "load_corpus_snapshot", snapshot)
    monkeypatch.setattr(smartdoc.ingestion, "get_documents_by_ids", metadata)
    monkeypatch.setattr(smartdoc.ingestion, "get_document_text", content)
    monkeypatch.setattr(smartdoc.ingestion, "ingest_document", ingest)
    monkeypatch.setattr(app.search_service, "SearchService", lambda: fake_service)
    yield fake_service, snapshot, content, ingest
    st.cache_data.clear()
    st.cache_resource.clear()
    ingest.assert_not_called()


def open_page(page="Tìm kiếm"):
    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.session_state["active_page"] = page
    at.run()
    assert not at.exception
    return at


def submit_query(at, query="xe điện", top_k=5):
    at.text_input(key="search_text").set_value(query)
    at.selectbox(key="ranked_top_k").set_value(top_k)
    next(button for button in at.button if button.label == "Tìm kiếm").click().run()
    assert not at.exception
    return at


def rendered_text(at):
    return "\n".join(item.value for item in at.markdown)


def all_output_text(at):
    output = [rendered_text(at)]
    for elements in (at.error, at.warning, at.info, at.success, at.caption, at.code):
        output.extend(element.value for element in elements)
    return "\n".join(output)


def test_ranked_search_renders_engine_order_scores_and_sources_without_catalog_read(app_environment):
    service, snapshot, _, _ = app_environment
    at = submit_query(open_page(), top_k=10)
    assert service.search_calls == [("xe điện", 10)]
    assert [button.key for button in at.button if str(button.key).startswith("search_open_")] == ["search_open_2", "search_open_10"]
    text = rendered_text(at)
    assert "Hạng 1 · Cosine 0.812345" in text
    assert "Hạng 2 · Cosine 0.123456" in text
    assert any(button.url == DOCUMENTS[0]["source_uri"] for button in at.get("link_button"))
    snapshot.assert_not_called()


@pytest.mark.parametrize("change", [
    {"status": "stale_index", "corpus_revision": 8},
    {"status": "index_unavailable"},
    {"status": "ok", "index_version": "new-version-same-revision"},
])
def test_stored_results_disappear_on_freshness_or_version_change(app_environment, change):
    service, _, _, _ = app_environment
    at = submit_query(open_page())
    service.state.update(change)
    at.run()
    assert not at.exception
    assert not [button for button in at.button if str(button.key).startswith("search_open_")]
    assert "ranked_search" not in at.session_state
    assert at.warning


@pytest.mark.parametrize("query, expected", [("   ", "Truy vấn rỗng"), ("ngoaituvung", "từ vựng")])
def test_empty_and_oov_have_actionable_feedback_without_result_cards(app_environment, query, expected):
    at = submit_query(open_page(), query)
    assert any(expected in info.value for info in at.info)
    assert not [button for button in at.button if str(button.key).startswith("search_open_")]


def test_rebuild_failure_can_retry_and_recovers_search(app_environment):
    service, _, _, _ = app_environment
    service.state["status"] = "stale_index"
    service.rebuild_outcomes = ["rebuild_failed", "ok"]
    at = open_page()
    at.button(key="rebuild_search").click().run()
    assert not at.exception and at.error
    assert "thử xây lại" in at.error[0].value
    at.button(key="rebuild_search").click().run()
    assert not at.exception and at.success
    submit_query(at)
    assert at.button(key="search_open_2")


def test_favorite_button_and_saved_list_update_in_same_interaction(app_environment):
    at = open_page("Thư viện")
    at.button(key="list_star_2").click().run()
    assert not at.exception
    assert at.session_state["favorites"] == [2]
    assert at.button(key="list_star_2").label == "★"
    at.button(key="nav_Đã lưu").click().run()
    at.button(key="fav_star_2").click().run()
    assert not at.exception
    assert at.session_state["favorites"] == []
    assert not [button for button in at.button if button.key == "fav_open_2"]


def test_reader_loads_only_on_open_and_escapes_raw_html(app_environment):
    _, _, content, _ = app_environment
    at = submit_query(open_page())
    content.assert_not_called()
    at.button(key="search_open_2").click().run()
    assert not at.exception
    assert at.session_state["reading_history"] == [2]
    content.assert_called_once_with(2)
    assert any(item.value == DOCUMENTS[0]["title"] for item in at.subheader)
    text = rendered_text(at)
    assert "&lt;script&gt;" in text
    assert "<script>alert('x')</script>" not in text
    # AppTest reruns the whole script for dialog input; reopen with seeded input
    # to check highlighting without claiming to simulate browser fragment events.
    at.session_state["reader_phrase_2"] = "năng lượng"
    at.button(key="search_open_2").click().run()
    assert not at.exception
    assert "<mark>năng lượng</mark>" in rendered_text(at)


def test_library_finds_natural_phrase_in_segmented_content(app_environment):
    at = open_page("Thư viện")
    at.selectbox(key="library_scope").select("Tiêu đề & nội dung đã xử lý").run()
    at.text_input(key="library_query").set_value("nang luong").run()
    assert not at.exception
    assert [button.key for button in at.button if str(button.key).startswith("list_open_")] == ["list_open_2"]


def test_algorithm_illustration_shows_actual_service_explanation(app_environment):
    at = submit_query(open_page())
    at.toggle(key="show_explanation").set_value(True).run()
    assert not at.exception
    assert at.dataframe
    frame = at.dataframe[0].value
    assert frame.iloc[0]["term"] == "xe_điện"
    assert frame.iloc[0]["contribution"] == pytest.approx(0.812345)
    assert any("1 tài liệu ứng viên" in caption.value for caption in at.caption)


def test_search_exception_has_friendly_feedback_clears_old_results_and_redacts_credentials(app_environment):
    service, _, _, _ = app_environment
    at = submit_query(open_page())
    service.search = Mock(side_effect=RuntimeError(
        "Connection failed: postgresql://secret_user:secret_password@127.0.0.1/db "
        "password='second_secret'"))
    submit_query(at, "another query")
    assert not at.exception
    assert at.error or at.info or at.warning
    assert not [button for button in at.button if str(button.key).startswith("search_open_")]
    assert not any(secret in all_output_text(at) for secret in (
        "secret_user", "secret_password", "second_secret"))


def test_reader_service_failure_is_visible_without_crash_or_credentials(app_environment):
    _, _, content, _ = app_environment
    content.side_effect = RuntimeError(
        "Reader failed: postgresql://reader_user:reader_password@127.0.0.1/db "
        "password=reader_second_secret")
    at = submit_query(open_page())
    at.button(key="search_open_2").click().run()
    assert not at.exception
    assert any("Không đọc được tài liệu" in element.value for element in at.error)
    assert not any(secret in all_output_text(at) for secret in (
        "reader_user", "reader_password", "reader_second_secret"))


def test_explanation_exception_keeps_app_usable_without_credentials(app_environment):
    service, _, _, _ = app_environment
    service.explain = Mock(side_effect=RuntimeError(
        "Explanation failed: postgresql://explain_user:explain_password@127.0.0.1/db"))
    at = submit_query(open_page())
    at.toggle(key="show_explanation").set_value(True).run()
    assert not at.exception
    assert at.error or at.warning or at.info
    assert not any(secret in all_output_text(at) for secret in ("explain_user", "explain_password"))

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
    import smartdoc.favorites

    st.cache_data.clear()
    st.cache_resource.clear()
    snapshot = Mock(return_value={"documents": deepcopy(DOCUMENTS), "corpus_revision": 7})
    metadata = Mock(side_effect=lambda ids: [deepcopy(row) for row in DOCUMENTS if row["document_id"] in ids])
    content = Mock(return_value="Xe điện dùng năng lượng sạch. <script>alert('x')</script>")
    ingest = Mock(side_effect=AssertionError("UI tests must not write to the database"))
    fake_service = FakeSearchService()
    bookmarks = set()
    monkeypatch.setattr(smartdoc.favorites, "load_saved_document_ids", lambda: sorted(bookmarks))
    monkeypatch.setattr(smartdoc.favorites, "set_document_saved",
                        lambda doc_id, desired: bookmarks.add(doc_id) if desired else bookmarks.discard(doc_id))
    monkeypatch.setattr(smartdoc.ingestion, "load_corpus_snapshot", snapshot)
    monkeypatch.setattr(smartdoc.ingestion, "load_corpus_revision", lambda: snapshot.return_value['corpus_revision'])
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


def test_saved_documents_survive_fresh_ui_session(app_environment):
    at = open_page("Thư viện")
    at.button(key="list_star_2").click().run()
    fresh = open_page("Đã lưu")
    assert fresh.session_state["favorites"] == [2]
    assert fresh.button(key="fav_open_2")


def test_new_bookmark_displays_even_when_catalog_was_cached(app_environment, monkeypatch):
    import smartdoc.favorites
    _, snapshot, _, _ = app_environment
    at = open_page('Thư viện')
    added = {**deepcopy(DOCUMENTS[0]), 'document_id': 20, 'title': 'New document'}
    snapshot.return_value = {'documents': [*deepcopy(DOCUMENTS), added], 'corpus_revision': 8}
    monkeypatch.setattr('smartdoc.ingestion.get_documents_by_ids',
                        lambda ids: [row for row in snapshot.return_value['documents'] if row['document_id'] in ids])
    smartdoc.favorites.set_document_saved(20, True)
    at.button(key='nav_Đã lưu').click().run()
    assert not at.exception
    assert at.button(key='fav_open_20')
    assert 'Danh sách yêu thích đang trống' not in rendered_text(at)


def test_catalog_refreshes_on_external_revision_change(app_environment):
    _, snapshot, _, _ = app_environment
    at = open_page('Thư viện')
    snapshot.return_value['corpus_revision'] += 1
    snapshot.return_value['documents'].append({**deepcopy(DOCUMENTS[0]), 'document_id': 20})
    at.run()
    assert not at.exception
    assert at.button(key='list_open_20')
    assert snapshot.call_count == 2


def test_reader_save_keeps_content_and_persists_across_sessions(app_environment):
    at = open_page("Thư viện")
    at.button(key="list_open_2").click().run()
    at.button(key="reader_star_2").click().run()
    assert not at.exception
    assert at.session_state["favorites"] == [2]
    assert "năng lượng sạch" in rendered_text(at)
    assert at.get("download_button")
    fresh = open_page("Đã lưu")
    assert fresh.button(key="fav_open_2")


def test_failed_save_does_not_claim_success_or_lose_reader(app_environment, monkeypatch):
    def fail(*args):
        raise RuntimeError("database unavailable")
    monkeypatch.setattr("smartdoc.favorites.set_document_saved", fail)
    at = open_page("Thư viện")
    at.button(key="list_open_2").click().run()
    at.button(key="reader_star_2").click().run()
    assert not at.exception
    assert at.session_state["favorites"] == []
    assert at.error
    assert "năng lượng sạch" in rendered_text(at)


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


def test_reader_reloads_text_when_backend_updates_same_document_id(app_environment):
    _, _, content, _ = app_environment
    content.return_value = "OLD_BODY_ABC"
    at = open_page("Thư viện")
    at.button(key="list_open_2").click().run()
    assert "OLD_BODY_ABC" in rendered_text(at)
    content.return_value = "NEW_BODY_XYZ"
    at.button(key="list_open_2").click().run()
    assert not at.exception
    assert "NEW_BODY_XYZ" in rendered_text(at)
    assert "OLD_BODY_ABC" not in rendered_text(at)
    assert content.call_count == 2


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


@pytest.mark.parametrize("connection_error, secrets", [
    (r"Reader failed password='fake\'TAIL_SECRET' host=localhost", ("fake", "TAIL_SECRET")),
    (r'Reader failed password="fake\"DOUBLE_TAIL" host=localhost', ("fake", "DOUBLE_TAIL")),
    (r"Reader failed password=FIRST_PASSWORD_SECRET\ SECOND_SECRET host=localhost", ("FIRST_PASSWORD_SECRET", "SECOND_SECRET")),
    ("Reader failed password='unfinished SECRET_SUFFIX", ("unfinished", "SECRET_SUFFIX")),
    ("Reader failed postgresql://secret_user:FIRST_PASSWORD_SECRET@SECOND_SECRET@localhost/db", ("secret_user", "FIRST_PASSWORD_SECRET", "SECOND_SECRET")),
    ("Reader failed postgres://localhost/db?password=QUERY_SECRET&sslmode=require", ("QUERY_SECRET",)),
])
def test_reader_redacts_escaped_conninfo_and_complete_postgresql_urls(app_environment, connection_error, secrets):
    _, _, content, _ = app_environment
    content.side_effect = RuntimeError(connection_error)
    at = submit_query(open_page())
    at.button(key="search_open_2").click().run()
    assert not at.exception
    assert any("Không đọc được tài liệu" in element.value for element in at.error)
    assert not any(secret in all_output_text(at) for secret in secrets)


def test_search_inputs_and_results_survive_page_navigation_without_new_search(app_environment):
    service, _, _, _ = app_environment
    at = submit_query(open_page(), "xe điện", 20)
    at.button(key="nav_Thư viện").click().run()
    assert not at.exception
    at.button(key="nav_Tìm kiếm").click().run()
    assert not at.exception
    assert at.text_input(key="search_text").value == "xe điện"
    assert at.selectbox(key="ranked_top_k").value == 20
    assert service.search_calls == [("xe điện", 20)]
    assert at.button(key="search_open_2")


def test_query_history_replays_top_k_with_fresh_engine_and_deduplicates(app_environment):
    service, _, _, _ = app_environment
    at = submit_query(open_page(), "xe điện", 10)
    submit_query(at, "giáo dục", 5)
    assert at.session_state["query_history"] == [
        {"query": "giáo dục", "top_k": 5}, {"query": "xe điện", "top_k": 10}]
    at.button(key="query_replay_1").click().run()
    assert not at.exception
    assert service.search_calls[-1] == ("xe điện", 10)
    assert at.text_input(key="search_text").value == "xe điện"
    assert at.selectbox(key="ranked_top_k").value == 10
    assert at.session_state["query_history"] == [
        {"query": "xe điện", "top_k": 10}, {"query": "giáo dục", "top_k": 5}]
    at.button(key="clear_query_history").click().run()
    assert not at.exception
    assert at.session_state["query_history"] == []
    assert not [button for button in at.button if str(button.key).startswith("query_replay_")]


def test_query_history_is_bounded_skips_blank_and_can_retry_oov(app_environment):
    at = submit_query(open_page(), "   ")
    assert at.session_state["query_history"] == []
    submit_query(at, "ngoaituvung")
    assert at.session_state["query_history"][0]["query"] == "ngoaituvung"
    at.session_state["query_history"] = [{"query": f"topic {i}", "top_k": 5} for i in range(12)]
    submit_query(at, "xe điện")
    assert len(at.session_state["query_history"]) == 12
    assert at.session_state["query_history"][0]["query"] == "xe điện"


def test_csv_download_and_search_stats_are_only_available_for_current_fresh_results(app_environment):
    service, _, _, _ = app_environment
    at = submit_query(open_page(), top_k=10)
    assert len(at.get("download_button")) == 1
    assert [(item.label, item.value) for item in at.metric] == [
        ("Kết quả trả về", "2 / 10"), ("Thời gian truy vấn", at.metric[1].value),
        ("Cosine cao nhất", "0.812345")]
    assert float(at.metric[1].value.removesuffix(" ms")) >= 0
    service.state.update(index_version="another-version")
    at.run()
    assert not at.exception
    assert not at.get("download_button")
    assert not at.metric


def test_ranked_cards_show_safe_content_excerpt_and_actual_metadata(app_environment):
    at = submit_query(open_page())
    text = rendered_text(at)
    assert "năng lượng giao thông xanh" in text
    assert 'class="sd-doc sd-result sd-result-lead"' in text
    assert "Công nghệ" in text
    assert "Hạng 1 · Cosine 0.812345" in text


def test_reader_rechecks_ready_document_after_external_delete(app_environment, monkeypatch):
    import smartdoc.ingestion

    _, _, content, _ = app_environment
    at = open_page("Thư viện")
    at.button(key="list_open_2").click().run()
    assert not at.exception
    content.assert_called_once_with(2)
    assert at.get("download_button")
    live_metadata = Mock(return_value=[])
    monkeypatch.setattr(smartdoc.ingestion, "get_documents_by_ids", live_metadata)
    at.button(key="list_open_2").click().run()
    assert not at.exception
    live_metadata.assert_called_once_with([2])
    content.assert_called_once_with(2)
    assert any("không còn sẵn sàng" in item.value for item in at.warning)
    assert "Xe điện dùng năng lượng sạch" not in rendered_text(at)
    assert not at.get("download_button")
    # Restoring a ready document triggers a fresh text fetch because deletion
    # invalidated precisely this ID's cached content.
    monkeypatch.setattr(smartdoc.ingestion, "get_documents_by_ids", Mock(return_value=[DOCUMENTS[0]]))
    at.button(key="list_open_2").click().run()
    assert not at.exception
    assert content.call_count == 2


@pytest.mark.parametrize("metadata", [
    [{"document_id": 10}], [{"document_id": 2}, {"document_id": 2}],
    [{"document_id": "2"}], None,
])
def test_reader_refuses_missing_ambiguous_or_wrong_ready_metadata(app_environment, monkeypatch, metadata):
    import smartdoc.ingestion

    _, _, content, _ = app_environment
    at = open_page("Thư viện")
    monkeypatch.setattr(smartdoc.ingestion, "get_documents_by_ids", Mock(return_value=metadata))
    at.button(key="list_open_2").click().run()
    assert not at.exception
    assert at.warning
    content.assert_not_called()
    assert not at.get("download_button")


def test_reader_ready_existence_check_failure_is_redacted_and_never_reads_cached_text(app_environment, monkeypatch):
    import smartdoc.ingestion

    _, _, content, _ = app_environment
    at = open_page("Thư viện")
    monkeypatch.setattr(smartdoc.ingestion, "get_documents_by_ids", Mock(side_effect=RuntimeError(
        "postgresql://READY_CHECK_USER:READY_CHECK_SECRET@127.0.0.1/db password='READY_CONNINFO_SECRET'")))
    at.button(key="list_open_2").click().run()
    assert not at.exception
    assert any("Không đọc được tài liệu" in item.value for item in at.error)
    assert not any(secret in all_output_text(at) for secret in (
        "READY_CHECK_USER", "READY_CHECK_SECRET", "READY_CONNINFO_SECRET"))
    content.assert_not_called()
    assert not at.get("download_button")

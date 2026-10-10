"""SmartDoc Search Pro V3 — premium, interactive Vietnamese document workspace.

Read-only analytics and document browsing use the existing data-service APIs.
New TXT/PDF uploads use the existing ingestion API. Ranked retrieval uses the
shared TF-IDF service and checks index freshness against PostgreSQL.

Run from the repository root:
    python -m streamlit run app/main.py
"""
from __future__ import annotations

from collections import Counter
import html
from pathlib import Path
import re
import sys
from time import perf_counter

# Streamlit adds app/ to sys.path when launched by filename.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import streamlit as st

from app.catalog_utils import categories, category_label, filter_catalog, page_slice
from app.ui_theme import apply_theme
from app.search_service import SearchService
from app.upload_service import process_uploads
from smartdoc.ingestion import (
    get_document_text,
    get_documents_by_ids,
    ingest_document,
    load_corpus_snapshot,
)


st.set_page_config(
    page_title="SmartDoc Pro | Thư viện tài liệu thông minh",
    page_icon="📚", layout="wide", initial_sidebar_state="expanded",
)

NAV = [
    ("Tổng quan", "◈"),
    ("Tìm kiếm", "⌕"),
    ("Thư viện", "▤"),
    ("Đã lưu", "♡"),
    ("Tải lên", "⇧"),
    ("Phân tích", "▥"),
]
for key, default in (
    ("active_page", "Tổng quan"), ("ui_dark", True),
    ("favorites", []), ("reading_history", []),
    ("catalog_page", 1), ("catalog_filters", None),
    ("search_text", ""), ("search_topic", "Tất cả"),
    ("home_query", ""), ("library_query", ""),
    ("reading_view", "Danh sách"),
):
    st.session_state.setdefault(key, default)

# Preserve the currently selected page for users upgrading from V2/V2.1.
_previous_pages = {
    "Thư viện tài liệu": "Thư viện",
    "Tải lên tài liệu": "Tải lên",
    "Thống kê": "Phân tích",
}
_current_page = st.session_state["active_page"]
st.session_state["active_page"] = _previous_pages.get(_current_page, _current_page)
if st.session_state["active_page"] not in {name for name, _ in NAV}:
    st.session_state["active_page"] = "Tổng quan"


def esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


@st.cache_data(ttl=600, show_spinner=False)
def get_catalog() -> tuple[list[dict], int]:
    """Fetch a consistent snapshot; cache between page/filter interactions."""
    snapshot = load_corpus_snapshot(None)
    ids = [int(item["document_id"]) for item in snapshot["documents"]]
    metadata = {int(row["document_id"]): row for row in get_documents_by_ids(ids)}
    docs = [{**row, **metadata.get(int(row["document_id"]), {})} for row in snapshot["documents"]]
    return docs, int(snapshot["corpus_revision"])


@st.cache_data(ttl=600, show_spinner=False)
def cached_content(document_id: int) -> str:
    """Only query raw document text when a reader actually opens a document."""
    return get_document_text(document_id)


@st.cache_resource(show_spinner=False)
def search_service() -> SearchService:
    return SearchService()


def clear_document_cache() -> None:
    get_catalog.clear()
    cached_content.clear()
    st.session_state.pop("ranked_search", None)


def safe_error(exc: object) -> str:
    # Connection exceptions can contain a DSN; never reveal credentials in UI.
    message = re.sub(r"(postgres(?:ql)?://)[^\s@]+@", r"\1***@", str(exc))
    return re.sub(r"(?i)(password\s*=\s*)(?:'[^']*'|\"[^\"]*\"|\S+)", r"\1***", message)


def go(page: str) -> None:
    st.session_state["active_page"] = page
    st.rerun()


def go_search(query: str = "") -> None:
    st.session_state["search_text"] = query
    st.session_state["run_quick_search"] = bool(query.strip())
    go("Tìm kiếm")


def saved(doc_id: int) -> bool:
    return doc_id in st.session_state["favorites"]


def toggle_saved(doc_id: int) -> None:
    items = set(st.session_state["favorites"])
    if doc_id in items:
        items.remove(doc_id)
        st.toast("Đã bỏ khỏi danh sách yêu thích")
    else:
        items.add(doc_id)
        st.toast("Đã lưu tài liệu")
    st.session_state["favorites"] = sorted(items)


def record_read(doc_id: int) -> None:
    history = [int(i) for i in st.session_state["reading_history"] if int(i) != doc_id]
    st.session_state["reading_history"] = [doc_id, *history][:12]


def title(eyebrow: str, heading: str, desc: str = "") -> None:
    st.markdown(
        f'<div class="sd-kicker">{esc(eyebrow)}</div>'
        f'<div class="sd-title">{esc(heading)}</div>'
        f'<div class="sd-subtitle">{esc(desc)}</div>',
        unsafe_allow_html=True,
    )


def section(text: str) -> None:
    st.markdown(f'<div class="sd-section-title">{esc(text)}</div>', unsafe_allow_html=True)


def metric(label: str, value: str, glyph: str, note: str, color: str = "#5b75f8") -> None:
    st.markdown(
        f'<div class="sd-stat" style="--stat-color:{color}">'
        f'<div class="sd-stat-top"><span class="sd-stat-label">{esc(label)}</span>'
        f'<span class="sd-stat-icon">{esc(glyph)}</span></div>'
        f'<div class="sd-stat-value">{esc(value)}</div>'
        f'<div class="sd-stat-note">{esc(note)}</div></div>',
        unsafe_allow_html=True,
    )


def metrics(docs: list[dict], revision: int) -> None:
    all_words = sum(int(doc.get("word_count") or 0) for doc in docs)
    cols = st.columns(4)
    entries = [
        ("Tài liệu", f"{len(docs):,}", "▤", "Có thể mở và đọc ngay", "#6156f2"),
        ("Chủ đề", str(len(categories(docs))), "◈", "Nhóm tài liệu hiện có", "#0ba5d9"),
        ("Tổng số từ", f"{all_words:,}", "✧", "Thống kê từ thư viện", "#22b79d"),
        ("Phiên bản dữ liệu", str(revision), "↻", "Theo dõi lần cập nhật", "#a676ed"),
    ]
    for col, (label, value, glyph, note, color) in zip(cols, entries):
        with col:
            metric(label, value, glyph, note, color)


def snippet(doc: dict) -> str:
    """Safe visual excerpt; never fetch raw document text to populate a card."""
    raw = str(doc.get("clean_text") or "").replace("_", " ").strip()
    if len(raw) > 150:
        raw = raw[:150].rsplit(" ", 1)[0] + "…"
    return raw or "Mở để xem nội dung của tài liệu này."


def doc_html(doc: dict, *, compact: bool = False) -> str:
    doc_id = int(doc["document_id"])
    stars = "★ Đã lưu" if saved(doc_id) else f"#{doc_id}"
    klass = "sd-doc sd-grid-doc" if compact else "sd-doc"
    excerpt = f'<div class="sd-micro">{esc(snippet(doc))}</div>' if compact else ""
    return (
        f'<div class="{klass}"><div class="sd-doc-meta">'
        f'<span class="sd-tag">{esc(stars)}</span>'
        f'<span class="sd-tag">{esc(category_label(doc))}</span>'
        f'<span>{int(doc.get("word_count") or 0):,} từ</span></div>'
        f'<div class="sd-doc-title">{esc(doc.get("title") or "Chưa có tiêu đề")}</div>'
        f'{excerpt}'
        f'</div>'
    )


def highlight_content(text: str, phrase: str) -> tuple[str, int]:
    """Escape text before marking case-insensitive literal matches (no HTML injection)."""
    phrase = phrase.strip()
    if not phrase:
        return esc(text), 0
    matches = list(re.finditer(re.escape(phrase), text, flags=re.IGNORECASE))
    parts = []
    start = 0
    for match in matches[:300]:
        parts.append(esc(text[start:match.start()]))
        parts.append(f"<mark>{esc(match.group())}</mark>")
        start = match.end()
    parts.append(esc(text[start:]))
    return "".join(parts), len(matches)


@st.dialog("Không gian đọc tài liệu", width="large")
def reader(doc: dict) -> None:
    doc_id = int(doc["document_id"])
    st.subheader(str(doc.get("title") or "Tài liệu chưa có tiêu đề"))
    st.caption(f"#{doc_id} · {category_label(doc)} · {int(doc.get('word_count') or 0):,} từ")
    a, b = st.columns([1, 1])
    with a:
        st.button("★ Đã lưu" if saved(doc_id) else "☆ Lưu tài liệu", key=f"reader_star_{doc_id}",
                  width="stretch", on_click=toggle_saved, args=(doc_id,))
    with b:
        src = str(doc.get("source_uri") or "")
        if src.startswith(("https://", "http://")):
            st.link_button("↗ Nguồn tài liệu", src, width="stretch")
    try:
        content = cached_content(doc_id)
    except Exception as exc:
        st.error(f"Không đọc được tài liệu: {safe_error(exc)}")
        return
    tab_read, tab_details = st.tabs(["📖 Nội dung", "ℹ️ Thông tin"])
    with tab_read:
        phrase = st.text_input("Tìm trong bài viết", placeholder="Nhập từ hoặc cụm từ để tô sáng...", key=f"reader_phrase_{doc_id}")
        highlighted, matches = highlight_content(content or "", phrase)
        if phrase.strip():
            st.caption(f"Tìm thấy {matches} vị trí trùng khớp chính xác.")
        # Long documents remain readable; full raw text is always available below.
        st.markdown(f'<div class="sd-article">{highlighted}</div>', unsafe_allow_html=True)
        st.download_button("↓ Tải nội dung TXT", (content or "").encode("utf-8"),
                           file_name=f"smartdoc_{doc_id}.txt", mime="text/plain; charset=utf-8",
                           key=f"reader_download_{doc_id}")
    with tab_details:
        st.write("**Tên tài liệu:**", doc.get("title") or "Chưa có")
        st.write("**Danh mục:**", category_label(doc))
        st.write("**Số từ:**", int(doc.get("word_count") or 0))
        st.write("**Mã tài liệu:**", doc_id)
        st.write("**Nguồn:**", doc.get("source_uri") or "Tài liệu tải lên")
        st.caption("Thông tin được lưu cùng tài liệu trong thư viện.")


def open_reader(doc: dict) -> None:
    record_read(int(doc["document_id"]))
    reader(doc)


def document_item(doc: dict, context: str, *, grid_mode: bool = False) -> None:
    doc_id = int(doc["document_id"])
    st.markdown(doc_html(doc, compact=grid_mode), unsafe_allow_html=True)
    left, right = st.columns([2, 1], gap="small")
    with left:
        if st.button("↗ Đọc tài liệu", key=f"{context}_open_{doc_id}", width="stretch"):
            open_reader(doc)
    with right:
        st.button("★" if saved(doc_id) else "☆", key=f"{context}_star_{doc_id}",
                  help="Bỏ yêu thích" if saved(doc_id) else "Thêm yêu thích", width="stretch",
                  on_click=toggle_saved, args=(doc_id,))


def category_bars(docs: list[dict], *, max_items: int = 5) -> None:
    counts = list(categories(docs).items())[:max_items]
    if not counts:
        st.info("Chưa có danh mục để thống kê.")
        return
    largest = max(n for _, n in counts)
    output = ['<div class="sd-panel">']
    for name, count in counts:
        pct = 100 * count / max(largest, 1)
        output.append(
            f'<div class="sd-bar-meta"><span>{esc(name)}</span><strong>{count} tài liệu</strong></div>'
            f'<div class="sd-progress"><span style="width:{pct:.1f}%"></span></div>'
        )
    output.append('</div>')
    st.markdown("".join(output), unsafe_allow_html=True)


def recent_docs(docs: list[dict]) -> list[dict]:
    by_id = {int(d["document_id"]): d for d in docs}
    return [by_id[i] for i in st.session_state["reading_history"] if i in by_id]


def dashboard(docs: list[dict], revision: int) -> None:
    st.markdown(
        '<div class="sd-topline"><span>WORKSPACE / TỔNG QUAN</span>'
        '<span><span class="sd-led"></span>Thư viện đang hoạt động</span></div>'
        '<div class="sd-hero"><div class="sd-hero-copy">'
        '<span class="sd-pill">✦ KHÔNG GIAN TRI THỨC</span>'
        '<h1>Khám phá ý tưởng.<br><span class="accent">Chạm tới tri thức.</span></h1>'
        '<p>Tất cả tài liệu tiếng Việt trong một không gian trực quan — lưu trữ, khám phá '
        'và đọc theo cách của bạn.</p></div>'
        '<span class="sd-orb">✧ Smart workspace</span></div>',
        unsafe_allow_html=True,
    )
    metrics(docs, revision)
    section("⌕ Bắt đầu với một ý tưởng")
    with st.container():
        qcol, btn = st.columns([4, 1], vertical_alignment="bottom")
        with qcol:
            q = st.text_input("Tìm nhanh trong thư viện", placeholder="Thử: xe điện, công nghệ, giáo dục...", key="home_query", label_visibility="collapsed")
        with btn:
            if st.button("⌕ Khám phá", key="home_go", type="primary", width="stretch"):
                go_search(q.strip())
    chips = ["Xe điện", "Smartphone", "Sức khỏe", "Công nghệ"]
    chipcols = st.columns(len(chips))
    for col, chip in zip(chipcols, chips):
        with col:
            if st.button(f"✧ {chip}", key=f"quick_chip_{chip}", width="stretch"):
                go_search(chip)
    section("✦ Không gian làm việc của bạn")
    l, r = st.columns([1.1, 1], gap="large")
    with l:
        st.markdown('<div class="sd-feature"><div class="sd-feature-icon">📚</div><div class="sd-feature-title">Thư viện của bạn</div>'
                    '<div class="sd-feature-desc">Tìm, lọc, đánh dấu và đọc các tài liệu trong cùng một nơi.</div></div>', unsafe_allow_html=True)
        if st.button("Khám phá toàn bộ tài liệu  →", key="go_lib", width="stretch"):
            go("Thư viện")
        st.markdown('<div class="sd-feature"><div class="sd-feature-icon">♡</div><div class="sd-feature-title">Bộ sưu tập yêu thích</div>'
                    '<div class="sd-feature-desc">Những tài liệu bạn đánh dấu sẽ xuất hiện ở đây trong phiên sử dụng.</div></div>', unsafe_allow_html=True)
        if st.button(f"Xem đã lưu ({len(st.session_state['favorites'])})  →", key="go_saved", width="stretch"):
            go("Đã lưu")
    with r:
        st.markdown('<div class="sd-section-title" style="margin-top:0">▥ Chủ đề nổi bật</div>', unsafe_allow_html=True)
        category_bars(docs)
    section("↗ Vừa mở & gợi ý khám phá")
    history = recent_docs(docs)
    suggestions = history[:2] if history else sorted(docs, key=lambda x: x["document_id"], reverse=True)[:2]
    if suggestions:
        cols = st.columns(len(suggestions))
        for col, doc in zip(cols, suggestions):
            with col:
                document_item(doc, "home", grid_mode=True)
    else:
        st.info("Thư viện hiện chưa có tài liệu.")


def index_controls(context: str) -> dict:
    """Read current index state without the library's ten-minute cache."""
    service = search_service()
    with st.spinner("Đang kiểm tra chỉ mục..."):
        state = service.status()
    status = state["status"]
    if status == "ok":
        st.caption(f"Chỉ mục sẵn sàng · {state.get('document_count', 0)} tài liệu · "
                   f"revision {state.get('corpus_revision')} · {state.get('index_version')}")
    elif status == "empty_corpus":
        st.info("Thư viện chưa có tài liệu để tìm kiếm. Hãy tải lên TXT hoặc PDF có văn bản.")
    else:
        st.warning("Chỉ mục cần được xây lại trước khi tìm kiếm." if status == "stale_index"
                   else "Chưa có chỉ mục hợp lệ hoặc chưa kết nối được dữ liệu.")
        with st.expander("Chi tiết trạng thái"):
            st.code(safe_error(state.get("message", status)), language="text")
    if st.button("Xây lại chỉ mục", key=f"rebuild_{context}", width="stretch"):
        with st.spinner("Đang xây và kiểm tra chỉ mục mới..."):
            result = service.rebuild()
        clear_document_cache()
        st.session_state["rebuild_feedback"] = result
        st.rerun()
    feedback = st.session_state.pop("rebuild_feedback", None)
    if feedback:
        if feedback.get("status") in {"ok", "empty_corpus"} and feedback.get("rebuilt"):
            st.success("Đã xây và kích hoạt chỉ mục. Có thể tìm kiếm lại.")
        else:
            st.error("Chưa thể kích hoạt chỉ mục đồng bộ. Bạn có thể thử xây lại.")
            st.caption(safe_error(feedback.get("message", "")))
    return state


def search_page() -> None:
    title("TRUNG TÂM KHÁM PHÁ", "Tìm đúng điều bạn cần.",
          "Xếp hạng tài liệu theo TF-IDF và cosine, sử dụng chỉ mục đảo để chọn ứng viên.")
    with st.form("ranked_search_form", border=False):
        q = st.text_input("Từ khóa", placeholder="Ví dụ: xe điện, trí tuệ nhân tạo...", key="search_text")
        top_k = st.selectbox("Số kết quả Top-K", [5, 10, 20], key="ranked_top_k")
        submitted = st.form_submit_button("Tìm kiếm", type="primary", width="stretch")
    state = index_controls("search")
    quick_search = st.session_state.pop("run_quick_search", False)
    if submitted or quick_search:
        started = perf_counter()
        with st.spinner("Đang tìm tài liệu liên quan..."):
            try:
                response = search_service().search(q, top_k)
            except Exception as exc:
                response = {"status": "index_unavailable", "results": [], "message": safe_error(exc)}
        st.session_state["ranked_search"] = {
            "query": q, "top_k": top_k, "response": response,
            "latency_ms": (perf_counter() - started) * 1000,
        }
    recorded = st.session_state.get("ranked_search")
    if not recorded:
        st.info("Nhập truy vấn và nhấn Tìm kiếm. Thư viện vẫn hỗ trợ lọc tiêu đề không dấu.")
        return
    response = recorded["response"]
    status = response["status"]
    messages = {
        "empty_query": "Truy vấn rỗng hoặc chỉ còn từ dừng sau xử lý. Hãy nhập từ khóa cụ thể hơn.",
        "oov_query": "Các từ khóa chưa có trong từ vựng của chỉ mục. Hãy thử từ khác và giữ dấu tiếng Việt.",
        "empty_corpus": "Thư viện chưa có tài liệu để tìm kiếm.",
        "index_unavailable": "Chưa có chỉ mục hợp lệ. Kiểm tra dữ liệu và nhấn Xây lại chỉ mục.",
        "stale_index": "Dữ liệu đã thay đổi. Hãy xây lại chỉ mục rồi tìm kiếm lại.",
    }
    if status != "ok":
        st.info(messages.get(status, "Chưa thể tìm kiếm. Hãy kiểm tra chỉ mục rồi thử lại."))
        return
    # A previous result must disappear immediately if a later rerun detects a change.
    if (state["status"] != "ok" or response.get("index_version") != state.get("index_version")
            or response.get("corpus_revision") != state.get("corpus_revision")):
        st.session_state.pop("ranked_search", None)
        st.warning("Chỉ mục hoặc dữ liệu đã thay đổi. Hãy tìm kiếm lại trên phiên bản hiện tại.")
        return
    found = response["results"]
    section(f"{len(found)} kết quả cho “{recorded['query']}”")
    st.caption(f"Top-{recorded['top_k']} · cosine giảm dần, hòa điểm theo mã tăng dần · "
               f"{recorded['latency_ms']:.1f} ms cho API tìm kiếm và metadata, gồm kiểm tra PostgreSQL")
    if not found:
        st.info("Không có tài liệu nào có điểm dương cho truy vấn này.")
        return
    for doc in found:
        st.markdown(f"**Hạng {doc['rank']} · Cosine {doc['score']:.6f}**")
        document_item(doc, "search")
        source = str(doc.get("source_uri") or "")
        if source.startswith(("https://", "http://")):
            st.link_button("Nguồn tài liệu", source)
        else:
            st.caption("Nguồn: tài liệu tải lên hoặc chưa có đường dẫn xác thực.")
    if st.toggle("Minh họa cách xếp hạng", key="show_explanation"):
        chosen = st.selectbox("Tài liệu cần giải thích", [int(d["document_id"]) for d in found],
                              format_func=lambda doc_id: next(str(d.get("title", doc_id)) for d in found
                                                              if int(d["document_id"]) == doc_id))
        with st.spinner("Đang tính đóng góp từ khóa..."):
            try:
                detail = search_service().explain(recorded["query"], chosen,
                                                  expected_version=response["index_version"])
            except Exception:
                st.warning("Chưa thể giải thích truy vấn. Hãy kiểm tra dữ liệu và thử lại.")
                return
        if detail["status"] != "ok":
            st.warning("Chưa thể giải thích trên phiên bản này. Hãy tìm kiếm lại.")
            return
        st.write("Token truy vấn:", detail["query_tokens"])
        st.write("Posting list (mã tài liệu theo token):", detail.get("posting_lists", {}))
        st.caption(f"Hợp posting list: {len(detail.get('candidate_ids', []))} tài liệu ứng viên.")
        st.dataframe(detail["matched_terms"], hide_index=True, width="stretch")
        st.latex(r"\operatorname{cosine}(q,d)=\sum_t q_t d_t\quad(\|q\|_2=\|d\|_2=1)")
        st.caption(f"Tổng đóng góp = {sum(row['contribution'] for row in detail['matched_terms']):.6f}; "
                   f"cosine = {detail['score']:.6f}.")


def library_page(docs: list[dict]) -> None:
    title("BỘ SƯU TẬP", "Thư viện tài liệu", "Chuyển chế độ xem, lọc trực tiếp và lưu những bài viết yêu thích.")
    search = st.text_input("Lọc trong thư viện", key="library_query",
                           placeholder="Tên tài liệu, chủ đề, từ khóa... hỗ trợ không dấu")
    a, b, c = st.columns([1.3, 1, 1])
    with a:
        category = st.selectbox("Chủ đề", ["Tất cả", *categories(docs).keys()], key="library_cat")
    with b:
        scope = st.selectbox("Tìm trong", ["Tiêu đề", "Tiêu đề & nội dung đã xử lý"], key="library_scope")
    with c:
        order = st.selectbox("Sắp xếp", ["Mới nhất", "Tiêu đề A-Z", "Nhiều từ nhất"], key="library_sort")
    m1, m2 = st.columns([2, 1], vertical_alignment="bottom")
    with m1:
        st.radio("Bố cục", ["Danh sách", "Thẻ"], horizontal=True, key="reading_view")
    with m2:
        per_page = st.selectbox("Mỗi trang", [6, 12, 24], index=0, key="library_per_page")
    current_filters = (search, category, scope, order, per_page, st.session_state["reading_view"])
    if current_filters != st.session_state["catalog_filters"]:
        st.session_state["catalog_filters"] = current_filters
        st.session_state["catalog_page"] = 1
    filtered = filter_catalog(docs, query=search, category=category, search_in=scope, sort_by=order)
    section(f"▤ {len(filtered)} tài liệu")
    if scope != "Tiêu đề":
        st.caption("Tìm trong nội dung sử dụng so khớp từ khóa, chưa có xếp hạng độ liên quan.")
    if not filtered:
        st.markdown('<div class="sd-empty"><span class="emoji">📭</span><b>Không có kết quả phù hợp.</b>'
                    '<div>Hãy thử bộ lọc khác hoặc bỏ từ khóa đang nhập.</div></div>', unsafe_allow_html=True)
        return
    visible, page, pages = page_slice(filtered, int(st.session_state["catalog_page"]), per_page)
    st.session_state["catalog_page"] = page
    if st.session_state["reading_view"] == "Thẻ":
        cols = st.columns(2)
        for i, doc in enumerate(visible):
            with cols[i % 2]:
                document_item(doc, "grid", grid_mode=True)
    else:
        for doc in visible:
            document_item(doc, "list")
    left, center, right = st.columns([1, 2, 1], vertical_alignment="center")
    with left:
        if st.button("← Trước", disabled=page <= 1, key="library_prev", width="stretch"):
            st.session_state["catalog_page"] = page - 1
            st.rerun()
    with center:
        st.markdown(f'<div style="text-align:center;color:var(--sd-muted);font-size:12px">Trang <b>{page}</b> / {pages}</div>', unsafe_allow_html=True)
    with right:
        if st.button("Tiếp →", disabled=page >= pages, key="library_next", width="stretch"):
            st.session_state["catalog_page"] = page + 1
            st.rerun()


def favorites_page(docs: list[dict]) -> None:
    title("KHÔNG GIAN CÁ NHÂN", "Đã lưu & vừa đọc", "Giữ những tài liệu quan trọng luôn trong tầm tay trong phiên sử dụng này.")
    indexed = {int(doc["document_id"]): doc for doc in docs}
    favorites = [indexed[doc_id] for doc_id in st.session_state["favorites"] if doc_id in indexed]
    history = recent_docs(docs)
    metrics_cols = st.columns(2)
    with metrics_cols[0]: metric("Yêu thích", str(len(favorites)), "♡", "Danh sách của bạn", "#fb7185")
    with metrics_cols[1]: metric("Vừa đọc", str(len(history)), "↗", "Lịch sử phiên làm việc", "#20b8c6")
    tab_saved, tab_recent = st.tabs(["★ Đã lưu", "◷ Gần đây"])
    with tab_saved:
        if favorites:
            for doc in favorites:
                document_item(doc, "fav")
        else:
            st.markdown('<div class="sd-empty"><span class="emoji">♡</span><b>Danh sách yêu thích đang trống.</b>'
                        '<div>Nhấn ☆ bên cạnh tài liệu để lưu vào đây.</div></div>', unsafe_allow_html=True)
            if st.button("Khám phá thư viện", key="empty_saved", type="primary"):
                go("Thư viện")
    with tab_recent:
        if history:
            for doc in history:
                document_item(doc, "hist")
        else:
            st.info("Chưa có tài liệu nào được mở trong phiên này.")
    st.caption("Yêu thích và lịch sử đọc được giữ trong phiên trình duyệt hiện tại, không lưu vào tài khoản hay database.")


def upload_page() -> None:
    title("BỔ SUNG KIẾN THỨC", "Tài liệu mới, ý tưởng mới.",
          "Kéo thả file văn bản để đưa vào thư viện. Hỗ trợ TXT và PDF có lớp chữ.")
    st.markdown('<div class="sd-hint">Tài liệu mới được thêm vào thư viện. '
                'Sau khi tải lên thành công, hãy xây lại chỉ mục để tìm kiếm nội dung mới.</div>', unsafe_allow_html=True)
    st.markdown('<div class="sd-panel"><div style="font-size:27px">⇧</div>'
                '<div style="font-size:18px;font-weight:850;color:var(--sd-text)">Kéo thả để bắt đầu</div>'
                '<div style="font-size:12px;color:var(--sd-muted)">TXT · PDF có văn bản · tối đa 8 MB mỗi tệp</div></div>', unsafe_allow_html=True)
    uploaded_files = st.file_uploader("Chọn tài liệu", type=["pdf", "txt"], accept_multiple_files=True,
                                      help="PDF ảnh scan không có lớp văn bản sẽ không được hỗ trợ.",
                                      key="upload_files", max_upload_size=8)
    group = st.text_input("Chủ đề cho tài liệu mới", value="Tài liệu cá nhân", max_chars=70)
    if uploaded_files:
        st.caption(f"Đã chọn {len(uploaded_files)} tài liệu. Nhấn nút bên dưới để lưu.")
    if st.button("⇧ Thêm vào thư viện", type="primary", disabled=not uploaded_files, width="stretch"):
        with st.spinner("Đang xử lý tài liệu..."):
            feedback = process_uploads(uploaded_files or [], group,
                                       ingest_fn=ingest_document,
                                       mutation_lock=search_service().mutation_lock)
        st.session_state["upload_feedback"] = feedback
        clear_document_cache()
        st.rerun()
    previous = st.session_state.get("upload_feedback", [])
    if previous:
        section("Kết quả xử lý")
        for name, status, detail in previous:
            message = f"**{name}** — {safe_error(detail)}"
            if status == "ready":
                st.success(message)
            elif status == "duplicate":
                st.warning(message)
            else:
                st.error(message)
    st.caption("Khi nội dung thư viện thay đổi, chỉ số phiên bản dữ liệu cũng sẽ thay đổi.")
    index_controls("upload")


def analytics_page(docs: list[dict], revision: int) -> None:
    title("DỮ LIỆU & INSIGHTS", "Nhìn thư viện ở góc độ khác.",
          "Biểu đồ được tính trực tiếp từ metadata tài liệu, không dùng dữ liệu minh họa.")
    metrics(docs, revision)
    left, right = st.columns([1, 1], gap="large")
    with left:
        section("◈ Chủ đề theo số lượng")
        category_bars(docs, max_items=12)
    with right:
        section("▥ Phân bố tài liệu")
        rows = categories(docs)
        if rows:
            frame = pd.DataFrame({"Chủ đề": list(rows), "Tài liệu": list(rows.values())}).set_index("Chủ đề")
            st.bar_chart(frame, height=320, width="stretch")
        lengths = [int(item.get("word_count") or 0) for item in docs]
        avg = sum(lengths) / len(lengths) if lengths else 0
        st.markdown('<div class="sd-panel"><b>Độ dài trung bình:</b> '
                    f'{avg:,.1f} từ / tài liệu <div style="height:8px"></div>'
                    f'<b>Dài nhất:</b> {max(lengths, default=0):,} từ</div>', unsafe_allow_html=True)
    st.info("Đã tích hợp tìm kiếm TF-IDF. Precision@5 và MRR@20 cần bộ nhãn được nhóm rà soát độc lập; "
            "chưa có kết quả nghiệm thu chất lượng. Xem hướng dẫn đánh giá trong tài liệu dự án.")


# Sidebar controls stay native Streamlit widgets; CSS is presentation only.
with st.sidebar:
    st.markdown('<div class="sd-brand"><div class="sd-logo">✦</div><div>'
                '<div class="sd-brand-name">SmartDoc <em>Pro</em></div>'
                '<div class="sd-brand-desc">Your knowledge space</div></div></div>', unsafe_allow_html=True)
    st.markdown('<div class="sd-side-caption">KHÔNG GIAN LÀM VIỆC</div>', unsafe_allow_html=True)
    for page, glyph in NAV:
        is_active = st.session_state["active_page"] == page
        if st.button(f"{glyph}  {page}", key=f"nav_{page}", width="stretch",
                     type="primary" if is_active else "secondary"):
            go(page)
    st.divider()
    st.markdown('<div class="sd-side-caption">CÁ NHÂN HÓA</div>', unsafe_allow_html=True)
    st.toggle("🌙 Giao diện tối", key="ui_dark")
    if st.button("↻ Làm mới thư viện", key="refresh_sidebar", width="stretch"):
        clear_document_cache()
        st.toast("Đang làm mới dữ liệu...")
        st.rerun()
    st.markdown('<div class="sd-row-gap"></div><div class="sd-side-status">'
                '<span class="sd-led"></span>Không gian tài liệu<br>'
                '<span style="font-size:10px;opacity:.8">Đọc, lưu và khám phá tập trung.</span>'
                '</div>', unsafe_allow_html=True)

apply_theme(st.session_state["ui_dark"])

page = st.session_state["active_page"]
if page == "Tải lên":
    # Upload view does not need a full corpus snapshot on every rerun.
    upload_page()
elif page == "Tìm kiếm":
    # Retrieval handles its own fresh snapshot; do not load a cached full catalog first.
    search_page()
else:
    try:
        with st.spinner("Đang đồng bộ thư viện..."):
            documents, corpus_revision = get_catalog()
    except Exception as exc:
        title("KẾT NỐI", "Chưa thể mở thư viện", "Hãy kiểm tra dịch vụ dữ liệu rồi thử làm mới.")
        st.error(safe_error(exc))
        with st.expander("Hướng dẫn kiểm tra"):
            st.code("docker compose ps\npython -m scripts.check_db", language="bat")
        st.stop()
    if page == "Tổng quan":
        dashboard(documents, corpus_revision)
    elif page == "Thư viện":
        library_page(documents)
    elif page == "Đã lưu":
        favorites_page(documents)
    elif page == "Phân tích":
        analytics_page(documents, corpus_revision)

st.markdown('<div class="sd-footer">SmartDoc Pro · Lưu trữ thông minh, khám phá liền mạch</div>', unsafe_allow_html=True)

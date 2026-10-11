"""Run: python -m streamlit run app/review.py --server.port 8503.

This separate local workspace writes human decisions only. It never displays
retrieval scores or rankings and never modifies PostgreSQL documents.
"""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from app.evaluation_review import ReviewConflictError, ReviewStore
from smartdoc.config import storage_root


st.set_page_config(page_title="SmartDoc | Rà soát đánh giá", page_icon="📋", layout="wide")


@st.cache_resource(show_spinner=False)
def review_store(directory):
    return ReviewStore(directory, storage_root=storage_root())


def safe_message(exc):
    # Data-service exceptions may include a connection string.
    message = re.sub(r"(?i)\bpostgres(?:ql)?://\S+", "postgresql://***", str(exc))
    pattern = r"(?i)(\bpassword\s*=\s*)(?:'(?:\\.|[^'\\])*(?:'|$)|\"(?:\\.|[^\"\\])*(?:\"|$)|(?:\\.|[^\s])+)"
    return re.sub(pattern, r"\1***", message)


def reload_kit():
    st.session_state.pop("review_loaded_kit", None)
    st.session_state.pop("review_loaded_path", None)
    st.rerun()


def save_result(operation):
    try:
        operation()
    except ReviewConflictError as exc:
        st.warning(safe_message(exc))
    except Exception as exc:
        st.error(safe_message(exc))
    else:
        st.session_state["review_notice"] = "Đã lưu quyết định của bạn. Chưa tính hay tạo chỉ số chất lượng."
        reload_kit()


st.title("Rà soát chất lượng tìm kiếm")
st.caption("Đọc nội dung gốc và tự quyết định mức liên quan. Mọi nhãn được lưu khi bạn nhấn nút; hệ thống không tự gán nhãn.")

with st.sidebar:
    st.header("Phiên rà soát")
    directory = st.text_input("Thư mục bộ đánh giá", value=str(ROOT / "evaluation"), key="review_directory")
    assessor = st.text_input("Tên người đang rà soát", key="review_assessor", placeholder="Nhập tên thật của bạn")
    if st.button("Làm mới bộ nhãn", icon=":material/refresh:", width="stretch"):
        reload_kit()
    st.caption("Làm mới để nhận thay đổi từ phiên khác. Nếu corpus đã đổi, tạo bộ đánh giá mới trước khi tiếp tục.")

try:
    store = review_store(directory)
    # Keep the exact version whose values populated the forms. Reloading on
    # submit would incorrectly accept another session's new checksum while
    # retaining this browser's older form values.
    if st.session_state.get("review_loaded_path") != str(store.directory):
        st.session_state["review_loaded_kit"] = store.load()
        st.session_state["review_loaded_path"] = str(store.directory)
    kit = st.session_state["review_loaded_kit"]
except Exception as exc:
    st.error(f"Chưa mở được bộ rà soát: {safe_message(exc)}")
    st.info("Chuẩn bị bộ nhãn bằng scripts.prepare_evaluation và giữ PostgreSQL đang chạy. Bộ nhãn cũ thiếu hash truy vấn cần được tạo lại với nhãn trắng.")
    st.stop()

notice = st.session_state.pop("review_notice", None)
if notice:
    st.success(notice)

progress = store.progress(kit)
columns = st.columns(4)
for column, label, value in zip(columns,
        ["Truy vấn đã duyệt", "Cặp đã hoàn tất", "Cặp liên quan", "Bất đồng chưa xử lý"],
        [f"{progress['approved_queries']}/{progress['query_count']}",
         f"{progress['completed_pairs']}/{progress['pair_count']}",
         str(progress['positive_pairs']), str(progress['unresolved_disagreements'])]):
    column.metric(label, value)
st.progress(progress["completed_pairs"] / max(progress["pair_count"], 1), text="Tiến độ gán nhãn")

queries = {row["query_id"]: row for row in kit["queries"]}
documents = {row["document_id"]: row for row in kit["snapshot"]["documents"]}
with st.sidebar:
    query_id = st.selectbox("Truy vấn đang rà soát", list(queries), key="review_query")
    role_options = ["a", "b"] if kit["protocol"]["assessor_count"] == 2 else ["a"]
    role = st.selectbox("Vai trò gán nhãn", role_options,
                        format_func=lambda value: "Người A" if value == "a" else "Người B", key="review_role")
    st.caption(f"Corpus đã chốt: {kit['manifest']['document_count']} tài liệu. Không hiển thị điểm hoặc thứ hạng tìm kiếm.")

query = queries[query_id]
with st.container(border=True):
    st.subheader(f"{query_id} · Truy vấn")
    st.text(query["query"])
    st.markdown("**Nhu cầu thông tin cần đáp ứng**")
    st.text(query["information_need"])

view = st.segmented_control("Công việc", ["Gán nhãn tài liệu", "Duyệt truy vấn", "Quy trình & kiểm tra"],
                            default="Gán nhãn tài liệu", key="review_view")

if view == "Gán nhãn tài liệu":
    query_rows = [row for row in kit["judgments"] if row["query_id"] == query_id]
    expand = st.toggle("Mở rộng rà soát toàn bộ thư viện", key="review_expand",
                       help="Dùng khi cần tìm tài liệu liên quan nằm ngoài vùng đã chọn. Nhãn mới chỉ được thêm sau khi lưu.")
    document_ids = sorted(documents if expand else {int(row["document_id"]) for row in query_rows})
    pending_only = st.toggle("Chỉ hiện tài liệu chưa được tôi gán nhãn", key="review_pending", value=True)
    by_document = {int(row["document_id"]): row for row in query_rows}
    if pending_only:
        document_ids = [doc_id for doc_id in document_ids
                        if by_document.get(doc_id, {}).get(f"label_{role}") not in {"0", "1"}]
    if not document_ids:
        st.success("Đã rà soát hết các tài liệu trong lựa chọn hiện tại. Tắt bộ lọc để kiểm tra/sửa nhãn đã lưu.")
    else:
        document_id = st.selectbox("Tài liệu theo mã tăng dần", document_ids,
                                  format_func=lambda value: f"#{value} · {documents[value]['title']}",
                                  key=f"review_document_{query_id}_{role}_{expand}_{pending_only}")
        document = documents[document_id]
        row = by_document.get(document_id, {})
        st.subheader(document["title"])
        source = str(document.get("source_uri") or "")
        if source.startswith(("https://", "http://")):
            st.link_button("Mở nguồn tài liệu", source, icon=":material/open_in_new:")
        readable = False
        try:
            with st.spinner("Đang đọc nội dung gốc và kiểm tra corpus..."):
                text = store.read_document(kit, document_id)
            with st.container(height=430, border=True):
                st.text(text)
            readable = True
        except Exception as exc:
            st.error(f"Chưa thể đọc nội dung gốc: {safe_message(exc)}")
        st.caption("1 = nội dung trả lời đáng kể nhu cầu thông tin; 0 = không đáp ứng. Không suy luận nhãn chỉ từ từ khóa trong tiêu đề.")
        form_key = f"assessment_{query_id}_{document_id}_{role}_{kit['token']}"
        with st.form(form_key):
            labels = ["", "0", "1"]
            old_label = row.get(f"label_{role}", "")
            label = st.selectbox("Quyết định của tôi", labels, index=labels.index(old_label) if old_label in labels else 0,
                                 format_func=lambda value: {"": "Chưa gán nhãn", "0": "0 · Không đáp ứng", "1": "1 · Có liên quan"}[value])
            evidence = st.text_area("Bằng chứng từ nội dung", value=row.get("evidence", "") if kit["protocol"]["assessor_count"] == 1 else "",
                                    placeholder="Trích ý hoặc mô tả ngắn đoạn trả lời nhu cầu thông tin; bắt buộc cho nhãn 1.")
            submitted = st.form_submit_button("Lưu quyết định", type="primary", disabled=not readable, icon=":material/save:")
        if submitted:
            save_result(lambda: store.save_assessment(kit["token"], query_id, document_id,
                        assessor=assessor, label=label, evidence=evidence, slot=role))

        both_assessed = row.get("label_a") in {"0", "1"} and row.get("label_b") in {"0", "1"}
        disagreement = both_assessed and row["label_a"] != row["label_b"]
        if kit["protocol"]["assessor_count"] == 2 and disagreement and st.toggle("Mở phần phân xử bất đồng", key="review_adjudicate"):
            st.caption("Chỉ mở sau khi cả hai người đã đưa ra quyết định độc lập.")
            st.write({"Nhãn A": row.get("label_a", ""), "Nhãn B": row.get("label_b", "")})
            st.text(row.get("evidence", ""))
            with st.form(f"adjudication_{query_id}_{document_id}_{kit['token']}"):
                final_label = st.selectbox("Nhãn sau phân xử", ["", "0", "1"])
                adjudicator = st.text_input("Tên người phân xử")
                resolution = st.text_area("Lý do giải quyết bất đồng")
                resolve = st.form_submit_button("Lưu phân xử", disabled=not readable)
            if resolve:
                save_result(lambda: store.adjudicate(kit["token"], query_id, document_id,
                            relevant=final_label, adjudicator=adjudicator, resolution=resolution))

elif view == "Duyệt truy vấn":
    st.info("Nội dung truy vấn và nhu cầu thông tin đã được gắn với bộ nhãn. Nếu cần sửa, tạo bộ nhãn trắng mới và rà soát lại trước khi đánh giá.")
    with st.form(f"query_review_{query_id}_{kit['token']}"):
        author = st.text_input("Người hoàn thiện truy vấn", value=query.get("author", ""))
        reviewer = st.text_input("Người duyệt truy vấn", value=query.get("reviewed_by", ""))
        approve = st.checkbox("Tôi xác nhận truy vấn rõ nghĩa, đúng nhu cầu và có thể đánh giá trên corpus này",
                               value=query.get("review_status") == "approved")
        submit_query = st.form_submit_button("Lưu rà soát truy vấn", type="primary")
    if submit_query:
        save_result(lambda: store.save_query_review(kit["token"], query_id,
                    author=author, reviewer=reviewer, approved=approve))

elif view == "Quy trình & kiểm tra":
    protocol = kit["protocol"]
    st.subheader("Xác nhận quy trình bởi người thật")
    st.caption("Một người có thể gán nhãn theo quy trình hiện tại; nếu dùng hai người, chuẩn bị bộ mới với --assessor-count 2. Không tự sửa số người trên bộ nhãn đang làm.")
    with st.form(f"protocol_review_{kit['token']}"):
        protocol_reviewer = st.text_input("Người duyệt quy trình", value=protocol.get("reviewed_by", ""))
        disagreement_policy = st.text_area("Cách xử lý nhãn và bất đồng", value=protocol.get("disagreement_policy", ""))
        independent = st.checkbox("Tôi xác nhận nhãn dựa trên nội dung đọc, không suy ra từ cosine score hoặc thứ hạng",
                                  value=protocol.get("independent_of_retrieval_scores") is True)
        protocol_approved = st.checkbox("Phê duyệt quy trình đánh giá", value=protocol.get("status") == "approved")
        save_protocol = st.form_submit_button("Lưu duyệt quy trình", type="primary")
    if save_protocol:
        save_result(lambda: store.save_protocol_review(kit["token"], reviewer=protocol_reviewer,
                    approved=protocol_approved, independent_content_review=independent,
                    disagreement_policy=disagreement_policy))
    st.divider()
    st.subheader("Kiểm tra điều kiện tính chỉ số")
    st.caption("Kiểm tra corpus, duyệt truy vấn, nhãn và độ phủ vùng Top-20. Bước này không tính Precision/MRR và không hiển thị điểm xếp hạng.")
    if st.button("Kiểm tra bộ đánh giá", icon=":material/fact_check:"):
        try:
            with st.spinner("Đang kiểm tra tính đầy đủ và nhất quán..."):
                store.check_readiness(kit["token"])
        except Exception as exc:
            st.warning(safe_message(exc))
        else:
            st.success("Bộ nhãn đáp ứng kiểm tra đầu vào. Có thể chạy lệnh đánh giá để tạo số liệu thực nghiệm.")
    st.code('python -m scripts.evaluate_retrieval --source snapshot --rebuild --repeats 5', language="bat")
    st.caption("Lệnh mặc định dùng thư mục evaluation. Nếu mở bộ nhãn khác, thêm --evaluation-dir theo thư mục bạn chọn.")

st.divider()
st.caption("Nhãn, tên người rà soát và thời gian được lưu vào bộ đánh giá tại máy này. Corpus PostgreSQL giữ nguyên. Thay đổi từ phiên khác sẽ được phát hiện trước khi ghi.")

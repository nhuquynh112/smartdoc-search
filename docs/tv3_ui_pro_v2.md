# SmartDoc Pro — giao diện và tích hợp tìm kiếm

Tên file được giữ để các liên kết bàn giao cũ tiếp tục dùng được. Xem thêm [nghiệm thu](tv3_acceptance.md), [demo](tv3_demo.md), [báo cáo](tv3_report.md) và [nguồn slide](tv3_slides.md).

## Phạm vi

Ứng dụng Streamlit có sáu trang: Tổng quan, Tìm kiếm, Thư viện, Đã lưu, Tải lên và Phân tích; có giao diện tối/sáng. Các nhãn thành viên chỉ dùng trong hồ sơ nhóm, không đưa vào luồng sử dụng của ứng dụng.

Trang Tìm kiếm gọi dịch vụ tích hợp để dùng TF-IDF, chỉ mục đảo, cosine và Top-K thật. Trang Thư viện vẫn hỗ trợ lọc chuỗi có/không dấu, chủ đề, sắp xếp và phân trang; kết quả lọc thư viện không phải thứ hạng cosine.

## Cấu trúc

| File | Vai trò |
| --- | --- |
| `app/main.py` | Trang Streamlit, tìm kiếm, reader, yêu thích, upload và trạng thái chỉ mục |
| `app/search_service.py` | Nối dịch vụ dữ liệu với engine; quản lý truy vấn, rebuild và giải thích cho UI |
| `app/upload_service.py` | Kiểm tra biên upload, tên tệp tạm và phản hồi từng tệp trước khi gọi ingestion |
| `app/catalog_utils.py` | Lọc chuỗi, chủ đề, sắp xếp, phân trang; không truy cập DB |
| `app/ui_theme.py` | CSS giao diện tối/sáng |
| `evaluation.py`, `scripts/prepare_evaluation.py`, `scripts/evaluate_retrieval.py` | Chuẩn bị nhãn và chạy đánh giá, tách khỏi UI |
| `requirements_tv3.txt` | Cài phụ thuộc chung và Streamlit |

UI lấy snapshot, metadata, nội dung và nhập tài liệu qua `smartdoc.ingestion`; không chứa SQL trực tiếp. Engine của nhóm nằm trong `smartdoc/tfidf_engine.py`, `inverted_index.py`, `search_engine.py`, `index_manager.py` và `retrieval_engine.py`.

Hợp đồng lớp tích hợp `SearchService`: `status()`, `search(query, top_k=5)`, `rebuild()` và `explain(query, document_id, expected_version=None)`. Mặc định UI dùng toàn corpus (`corpus_name=None`) và index `data/tv2_index`. Search trả trạng thái/message/results/index_version/corpus_revision; từng result được ghép metadata theo ID. Explain giữ phiên bản đã chọn, trả thêm `query_tokens`, `posting_lists`, `candidate_ids`, `matched_terms` và `score`.

## Chạy trên Windows CMD

Từ thư mục gốc của repository, dùng môi trường `.venv` đã có:

```bat
cd /d "E:\VanDat_\CSDL_DPT\smartdoc-search"
.venv\Scripts\activate.bat
python -m pip install -r requirements_tv3.txt
docker compose up -d --wait
python -m scripts.check_db
python -m streamlit run app/main.py
```

Nếu chưa có môi trường Python, tạo trước bằng `py -3.12 -m venv .venv`. Cấu hình `.env` theo `.env.example`; đặt cùng mật khẩu local ở `POSTGRES_PASSWORD` và `DATABASE_URL`. Không đưa `.env` vào Git và không gửi mật khẩu trong minh chứng.

Trên máy Windows này, host `localhost` trong `DATABASE_URL` làm mỗi kết nối mất khoảng 5 giây trong lần đo. Đổi riêng hostname thành `127.0.0.1` đã giảm thời gian kết nối trong phép thử; giữ nguyên user, mật khẩu, port và tên DB. Đây là cấu hình `.env` local được Git ignore, không sửa code dịch vụ dữ liệu của nhóm. Xem số đo đơn lẻ tại [nghiệm thu](tv3_acceptance.md).

Nếu máy đã có corpus, tiếp tục dùng dữ liệu hiện có. Máy mới chưa có corpus cần lấy gói dump/manifest của nhóm theo [hướng dẫn chuyển DB](database_transfer.md). Restore yêu cầu schema rỗng; không chạy `scripts.init_db` trước restore. Dump không nằm trong repository và không chứa tệp gốc. Không xóa volume để giải quyết lỗi restore.

## Luồng tìm kiếm

1. Mở Tìm kiếm và kiểm tra trạng thái chỉ mục. Nếu chưa có bộ hợp lệ hoặc corpus đã đổi, dùng chức năng xây lại chỉ mục.
2. Nhập truy vấn tiếng Việt và chọn Top-K 5, 10 hoặc 20; mặc định 5.
3. Dịch vụ dùng pipeline chung với tài liệu, transform query bằng vectorizer đã fit, lấy hợp posting list rồi tính cosine và xếp hạng.
4. Kết quả có rank, title, document ID, cosine score và nguồn nếu metadata có nguồn. Chỉ trả score dương; đồng điểm theo ID tăng dần; có thể trả ít hơn K.
5. Mở tài liệu để đọc nội dung gốc từ DB, lưu yêu thích, xem metadata, tìm cụm từ trong bài hoặc tải nội dung TXT.
6. Mở phần giải thích để xem token query, posting list/tập ứng viên và đóng góp của từ chung vào score.

Cosine không phải xác suất liên quan. Tìm không dấu trong thư viện là tiện ích riêng; engine giữ dấu và token từ ghép theo cấu hình tiền xử lý. Khi query không có token thuộc vocabulary, ứng dụng báo OOV; không đổi sang tìm tiêu đề và gắn score giả.

## Trạng thái và vòng đời chỉ mục

| Trạng thái engine | Ý nghĩa/hành động |
| --- | --- |
| `ok` | Chỉ mục phù hợp; hiển thị kết quả thực hoặc thông báo không có điểm dương |
| `empty_query` | Query rỗng/không còn token sau xử lý; nhập lại |
| `oov_query` | Không có token thuộc vocabulary; thử query khác |
| `empty_corpus` | Chưa có tài liệu ready để tìm kiếm |
| `index_unavailable` | Chưa có hoặc không đọc được chỉ mục; xem lỗi và xây lại |
| `stale_index` | Revision, fingerprint tiền xử lý hoặc phạm vi corpus không khớp; xây lại |
| `rebuild_failed` | Build/activation lỗi; đọc message, sửa nguyên nhân và thử lại; `rebuilt=False` |

Build tạo phiên bản mới và chỉ kích hoạt sau kiểm tra. Rebuild lỗi không được coi là thành công; bộ cũ chỉ được phục vụ nếu vẫn khớp corpus hiện tại. Luồng demo sửa corpus và rebuild theo thứ tự, không bảo đảm cập nhật đồng thời từ nhiều tiến trình.

Cache danh mục/nội dung dùng TTL 600 giây để giảm đọc DB khi chuyển trang. Nút làm mới và upload làm mất hiệu lực dữ liệu cache; kiểm tra freshness của tìm kiếm thuộc dịch vụ, không dựa riêng vào TTL danh mục. Nếu tiến trình khác thay dữ liệu, nhấn làm mới để cập nhật thẻ thống kê.

## Upload và reader

- TXT hoặc PDF có lớp văn bản; tối đa 8 MiB/tệp. PDF ảnh không có OCR trong phạm vi hiện tại.
- Metadata bắt buộc được sinh bởi pipeline; chủ đề trên UI là thông tin tùy chọn.
- Upload vào corpus `user_uploads`; UI tìm trên toàn thư viện nên bao gồm tài liệu upload sau rebuild. Bộ đánh giá cố định chọn riêng `vietonline_news_200`. Sau upload phải kiểm tra trạng thái và rebuild trước khi tìm lại.
- `user_uploads` là nhãn corpus trong cùng DB, không phải DB thử riêng. Revision thuộc DB, nên upload vẫn có thể làm manifest đánh giá không còn khớp; trong khi gán nhãn/đo hãy giữ DB cố định hoặc dùng snapshot đã đóng băng.
- Mỗi tệp hiển thị ready, duplicate hoặc lỗi. Duplicate không tạo tài liệu ready thứ hai.
- Reader đọc `raw_text` từ PostgreSQL; tải TXT là xuất văn bản UTF-8, không phải tải tệp nguồn ban đầu.
- Yêu thích/lịch sử đọc lưu trong phiên Streamlit; chưa có tài khoản hoặc lưu liên phiên vào PostgreSQL.
- Dump có văn bản/metadata nhưng không có `storage/originals`. Muốn truy xuất tệp nguồn phải nhận thư mục storage phù hợp.

## Kiểm chứng và giới hạn

Test dùng fixture/snapshot giả kiểm tra hợp đồng, ranking và lỗi có kiểm soát; không chứng minh corpus thật đã restore. Test PostgreSQL thật, UI thủ công và đánh giá có nhãn là bằng chứng riêng trong [checklist](tv3_acceptance.md).

Repository có 25 query nháp và mẫu nhãn trống. Nhóm phải đọc corpus, duyệt query và gán nhãn độc lập với cosine trước khi công bố Precision@5/MRR@20. Chưa có metric chất lượng hợp lệ khi nhãn chưa hoàn thành.

Bộ nhãn mặc định gồm pool Top-20 và seed theo query, hiện 500 cặp trống; mọi kết quả Top-20 thực sự trả khi đo phải được gán trước. Pool không cho phép kết luận recall/toàn bộ relevance của corpus. Xem [quy trình gán nhãn](../evaluation/README.md).

Yêu cầu “feed” vẫn chờ xác nhận với giảng viên. Số tài liệu/revision trong bàn giao là mốc lịch sử; dùng `scripts.check_db` và snapshot hiện tại làm bằng chứng cho lần chạy mới.

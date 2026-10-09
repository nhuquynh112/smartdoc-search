# SmartDoc Search Pro V2 — Hướng dẫn TV3

**Phạm vi:** Streamlit UI cho TV3. Không thay thế TF-IDF của TV2, không sửa Python service TV1, PostgreSQL schema hay README chung.

## Cấu trúc bổ sung

- `app/main.py` — 5 trang tương tác: Tổng quan, Tìm kiếm, Thư viện, Tải lên, Thống kê.
- `app/ui_theme.py` — design system dark/light, responsive CSS.
- `app/catalog_utils.py` — chuẩn hóa tiếng Việt, bộ lọc, phân trang, thống kê; không cần DB.
- `tests/test_tv3_catalog.py` — kiểm thử tiện ích lọc và phân trang.
- `requirements_tv3.txt` — thư viện riêng TV3, không sửa `requirements.txt` của TV1.

## Cài đặt trên Windows CMD

```bat
cd /d "E:\VanDat_\CSDL_DPT\smartdoc-search"
git branch --show-current
copy app\main.py "..\main_tv3_v1_backup.py"
.venv\Scripts\activate.bat
python -m pip install -r requirements_tv3.txt
python -m unittest discover -s tests -p "test_tv3_catalog.py" -v
python -m streamlit run app/main.py
```

Chạy từ **thư mục gốc** của repo. Docker Desktop / PostgreSQL phải hoạt động, file `.env` đặt tại thư mục gốc.

Nếu Streamlit đang chạy, dừng trước bằng Ctrl+C tại CMD rồi mở lại. `..\main_tv3_v1_backup.py` là bản lưu nằm ngoài repo nên không bị thêm nhầm vào Git.

## Dữ liệu và kết quả có thật

- Tổng tài liệu, revision, phân bố danh mục, số từ: API `load_corpus_snapshot()` + `get_documents_by_ids()` của TV1.
- Đọc văn bản: `get_document_text()` lấy `raw_text` từ PostgreSQL, không phụ thuộc có `storage/originals` cũ.
- Thư viện lọc theo tiêu đề / `clean_text`, danh mục; hỗ trợ không dấu và phân trang. Đây **không phải retrieval TF-IDF**.
- Tra cứu tiêu đề: khớp chuỗi, sắp xếp theo `document_id` giảm dần; không có Cosine score và không nói đó là Top-K relevance.
- Upload TXT/PDF: gọi `ingest_document()` thật, tự đặt `corpus_name='user_uploads'` tách biệt bộ corpus đánh giá VietOnlineNews. Tối đa 8MB/file; PDF scan có thể không có text để xử lý. Upload thành công làm revision thay đổi, phải rebuild index TV2 sau này.
- Cache đọc DB: 30 giây, có nút `Làm mới dữ liệu`; cache tự xóa khi upload.

## Tích hợp TV2 khi nhận API

Cần xác nhận tên module, chữ ký `search_query(query, top_k)`, cấu trúc `status/results`, quản lý corpus_revision & index_version, xử lý lỗi stale/unavailable. Khi đó thay luồng **Tra cứu tiêu đề** bằng engine thật hoặc giữ hai chế độ riêng. Chỉ hiển thị score/rank khi là output thực từ TV2 và sau khi kiểm tra revision khớp.

## Các giới hạn

- Thống kê Precision@5, MRR, latency chưa hiển thị vì chưa có bộ nhãn/engine thật.
- Sao lưu DB gốc và file `.env` ngoài Git; `.env`, `reports/*`, `storage/originals/*` được `.gitignore` của dự án loại trừ.
- Không push bản backup `smartdoc.dump`, nội dung tài liệu hoặc mật khẩu lên GitHub.

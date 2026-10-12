# SmartDoc Pro — giao diện và tích hợp tìm kiếm

Tên file được giữ để các liên kết bàn giao cũ tiếp tục dùng được. Xem thêm [nghiệm thu](tv3_acceptance.md), [demo](tv3_demo.md) và [việc cần người dùng hoàn tất](tv3_remaining.md). Báo cáo/slide hiện có thuộc bản trước; người dùng sẽ yêu cầu tổng hợp sau khi xong phần triển khai và thực nghiệm.

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
| `app/result_utils.py` | Xuất CSV kết quả theo đúng thứ tự/score engine, định dạng UTF-8 BOM cho Excel |
| `app/review.py`, `app/evaluation_review.py` | Không gian đọc nội dung và lưu quyết định gán nhãn/duyệt của người thật, tách khỏi ứng dụng tìm kiếm |
| `app/ui_theme.py` | CSS giao diện tối/sáng |
| `evaluation.py`, `scripts/prepare_evaluation.py`, `scripts/evaluate_retrieval.py` | Chuẩn bị nhãn và chạy đánh giá, tách khỏi UI |
| `scripts/benchmark_tv3_latency.py` | Đo thời gian API/core trên đầu vào đóng băng, không cần nhãn và không tạo metric relevance |
| `requirements_tv3.txt` | Cài phụ thuộc chung và Streamlit |

UI lấy snapshot, metadata, nội dung và nhập tài liệu qua `smartdoc.ingestion`; không chứa SQL trực tiếp. Engine của nhóm nằm trong `smartdoc/tfidf_engine.py`, `inverted_index.py`, `search_engine.py`, `index_manager.py` và `retrieval_engine.py`.

Hợp đồng lớp tích hợp `SearchService`: `status()`, `search(query, top_k=5)`, `rebuild()` và `explain(query, document_id, expected_version=None)`. Mặc định UI dùng toàn corpus (`corpus_name=None`) và index `data/tv2_index`; biến môi trường `SMARTDOC_INDEX_ROOT` cho phép môi trường thử chỉ định một thư mục index riêng. Search trả trạng thái/message/results/index_version/corpus_revision; từng result được ghép metadata theo ID. Explain giữ phiên bản đã chọn, trả thêm `query_tokens`, `posting_lists`, `candidate_ids`, `matched_terms` và `score`.

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

Nếu chưa có môi trường Python, tạo trước bằng `py -3.12 -m venv .venv`. Cấu hình `.env` theo `.env.example`; đặt cùng mật khẩu local ở `POSTGRES_PASSWORD` và `DATABASE_URL`. Không đưa `.env` vào Git và không gửi mật khẩu trong minh chứng. Để tránh lỗi activation PowerShell, có thể gọi trực tiếp `.venv\Scripts\python.exe` thay `python`.

Trên máy Windows này, host `localhost` trong `DATABASE_URL` làm mỗi kết nối mất khoảng 5 giây trong lần đo. Đổi riêng hostname thành `127.0.0.1` đã giảm thời gian kết nối trong phép thử; giữ nguyên user, mật khẩu, port và tên DB. Đây là cấu hình `.env` local được Git ignore, không sửa code dịch vụ dữ liệu của nhóm. Xem số đo đơn lẻ tại [nghiệm thu](tv3_acceptance.md).

Nếu máy đã có corpus, tiếp tục dùng dữ liệu hiện có. Máy mới chưa có corpus cần lấy gói dump/manifest của nhóm theo [hướng dẫn chuyển DB](database_transfer.md). Restore yêu cầu schema rỗng; không chạy `scripts.init_db` trước restore. Dump không nằm trong repository và không chứa tệp gốc. Không xóa volume để giải quyết lỗi restore. Nếu chỉ cần thử một corpus mới nhỏ, dùng một DB riêng rồi chạy `scripts.init_db` và `scripts.ingest_documents data/samples`; không thay DB demo 200 bài bằng dữ liệu mẫu.

## Luồng tìm kiếm

1. Mở Tìm kiếm và kiểm tra trạng thái chỉ mục. Nếu chưa có bộ hợp lệ hoặc corpus đã đổi, dùng chức năng xây lại chỉ mục.
2. Nhập truy vấn tiếng Việt và chọn Top-K 5, 10 hoặc 20; mặc định 5.
3. Dịch vụ dùng pipeline chung với tài liệu, transform query bằng vectorizer đã fit, lấy hợp posting list rồi tính cosine và xếp hạng.
4. Kết quả có rank, title, document ID, cosine score và nguồn nếu metadata có nguồn. Chỉ trả score dương; đồng điểm theo ID tăng dần; có thể trả ít hơn K.
5. Mở tài liệu để đọc nội dung gốc từ DB, lưu yêu thích, xem metadata, tìm cụm từ trong bài hoặc tải nội dung TXT.
6. Mở phần giải thích để xem token query, posting list/tập ứng viên và đóng góp của từ chung vào score.

## Tiện ích tìm kiếm bổ sung

Query và Top-K giữ khi chuyển trang trong cùng phiên. Lịch sử giữ tối đa 12 cặp query/Top-K gần nhất (từ truy vấn `ok` hoặc OOV), gộp mục trùng và có nút xóa. Chọn lịch sử chạy lại dịch vụ trên chỉ mục hiện tại; không phát lại một score đã lưu để bỏ qua freshness.

Thẻ kết quả thể hiện thứ hạng, score, nguồn và trích đoạn từ `clean_text`; trích đoạn là văn bản đã xử lý, không thay nội dung gốc trong reader. Ba ô thống kê ghi số kết quả, thời gian lần gọi và cosine cao nhất. Thời gian UI gồm API tích hợp, metadata và kiểm tra DB ở một lần gọi; không được dùng làm benchmark. Cosine cao nhất không phải accuracy hoặc xác suất relevant.

Nút **Tải kết quả CSV** xuất đúng thứ tự engine kèm query, Top-K, index version, corpus revision, rank, ID, title, nguồn và cosine. CSV có UTF-8 BOM để mở tiếng Việt trong Excel; các chuỗi có thể được Excel hiểu là công thức được vô hiệu hóa. Download chỉ xuất từ phản hồi `ok` đã qua kiểm tra freshness trên lần render. Đây là bản chụp kết quả có provenance; chỉ mục có thể thay đổi sau khi tệp được tải. CSV tìm kiếm không phải CSV đánh giá Precision@5/MRR@20.

Trạng thái sẵn sàng hiển thị gọn; revision/index version nằm trong mục mở rộng **Thông tin chỉ mục**. CSS có bố cục cửa sổ hẹp và tôn trọng lựa chọn giảm chuyển động; kết quả quan sát ở kích thước cụ thể được ghi trong [nghiệm thu](tv3_acceptance.md), không suy rộng thành chứng nhận mọi thiết bị.

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

Cache danh mục có TTL 600 giây và khóa theo corpus revision đọc mới từ DB, nên upload/delete/reprocess từ tiến trình khác tự làm mất hiệu lực cache ở lần rerun tiếp theo. Trang Đã lưu lấy metadata trực tiếp theo ID bookmark, không phụ thuộc danh mục cũ. Nút làm mới và upload vẫn xóa cache thủ công khi cần.

Reader đọc metadata/raw_text và bookmark hiện tại mỗi lần mở/rerun; ID deleted/non-ready hoặc lỗi DB sẽ chặn đọc thay vì phục vụ text cache cũ. Dialog đang mở ở tab khác cập nhật nút lưu ở lần tương tác tiếp theo, không có push realtime. Khi có hơn 300 vị trí trùng, UI ghi rõ chỉ tô 300 vị trí đầu.

SearchService cache snapshot theo revision/fingerprint và index theo active manifest cùng inode/size/mtime/ctime của artifact. Mỗi lần dùng vẫn kiểm tra revision trực tiếp từ DB; file đổi sẽ được nạp và kiểm tra checksum/số học lại. Không cache kết quả khi DB mất kết nối và vẫn kiểm tra trước/sau query để từ chối stale. Chỉ mục immutable đã kiểm tra được tái sử dụng trong bộ nhớ, giảm deserialize/validate/inverted-index rebuild lặp. Lần đầu sau restart/rebuild vẫn cần nạp/warmup.

Loader giới hạn đầu vào 8 MB, PDF 200 trang và text trích xuất 2.000.000 ký tự, kiểm tra từng trang và dừng khi vượt ngưỡng. Đây chưa phải hard timeout hoặc sandbox bộ nhớ cho parser; một trang PDF phức tạp vẫn có thể xử lý chậm.

## Upload và reader

- TXT hoặc PDF có lớp văn bản; tối đa 8 MiB/tệp. PDF ảnh không có OCR trong phạm vi hiện tại.
- Metadata bắt buộc được sinh bởi pipeline; chủ đề trên UI là thông tin tùy chọn.
- Upload vào corpus `user_uploads`; UI tìm trên toàn thư viện nên bao gồm tài liệu upload sau rebuild. Bộ đánh giá cố định chọn riêng `vietonline_news_200`. Sau upload phải kiểm tra trạng thái và rebuild trước khi tìm lại.
- `user_uploads` là nhãn corpus trong cùng DB, không phải DB thử riêng. Revision thuộc DB, nên upload vẫn có thể làm manifest đánh giá không còn khớp; trong khi gán nhãn/đo hãy giữ DB cố định hoặc dùng snapshot đã đóng băng.
- Mỗi tệp hiển thị ready, duplicate hoặc lỗi. Duplicate không tạo tài liệu ready thứ hai.
- Reader đọc `raw_text` từ PostgreSQL; tải TXT là xuất văn bản UTF-8, không phải tải tệp nguồn ban đầu.
- Từ bản sửa 12/10, danh sách yêu thích lưu trong PostgreSQL (`saved_documents`) và giữ qua reload/restart. Đây là danh sách chung của workspace local, chưa có tài khoản riêng. Lịch sử đọc và truy vấn vẫn theo phiên. Chạy `python -m scripts.init_db` để áp dụng migration khi cập nhật máy khác; thao tác lưu/bỏ lưu không đổi corpus revision hoặc yêu cầu rebuild index.
- Dump có văn bản/metadata nhưng không có `storage/originals`. Muốn truy xuất tệp nguồn phải nhận thư mục storage phù hợp.

## Kiểm chứng và giới hạn

Chạy toàn suite bằng `python -m scripts.test_tv3_isolated_database --all-tests`, không chạy `pytest` toàn bộ trực tiếp trên DB demo. Runner yêu cầu quyền PostgreSQL `CREATEDB`, tạo database/storage thử riêng và kiểm tra demo không đổi. Kiểm chứng chỉ đọc có lệnh `python -m scripts.verify_tv3 --rebuild --repeats 5`; rebuild chỉ ghi index local. Log fixture, log DB thật, thao tác trình duyệt và metric có nhãn là các lớp bằng chứng khác nhau.

Test dùng fixture/snapshot giả kiểm tra hợp đồng, ranking và lỗi có kiểm soát; không chứng minh corpus thật đã restore. Test PostgreSQL thật, UI thủ công và đánh giá có nhãn là bằng chứng riêng trong [checklist](tv3_acceptance.md).

Repository có 25 query nháp và mẫu nhãn trống. Nhóm phải đọc corpus, duyệt query và gán nhãn độc lập với cosine trước khi công bố Precision@5/MRR@20. Chưa có metric chất lượng hợp lệ khi nhãn chưa hoàn thành.

Bộ nhãn mặc định gồm pool Top-20 và seed theo query, hiện 500 cặp trống; mọi kết quả Top-20 thực sự trả khi đo phải được gán trước. Pool không cho phép kết luận recall/toàn bộ relevance của corpus. Xem [quy trình gán nhãn](../evaluation/README.md).

Manifest/protocol ràng buộc nội dung corpus và query. Nếu sửa query/nhu cầu thông tin hoặc tập query, dùng bản CSV sao chép và `prepare_evaluation --queries ... --output evaluation_new` để tạo pool/nhãn trống mới; không sửa tay hash. Evaluation từ chối pipeline tiền xử lý hiện cài không khớp fingerprint của corpus đóng băng.

## Không gian gán nhãn của nhóm

Chạy riêng trên máy local, song song với app tìm kiếm:

```bat
python -m streamlit run app/review.py --server.address 127.0.0.1 --server.port 8503
```

Mở `http://127.0.0.1:8503`, chọn thư mục bộ đánh giá và nhập tên người đang rà soát. Công cụ đọc `raw_text` qua API dữ liệu, kiểm tra DB còn khớp corpus đóng băng và hiển thị tài liệu theo ID, không hiển thị score/rank. Tại **Gán nhãn tài liệu**, đọc bài rồi chọn 0/1, ghi bằng chứng cho nhãn 1 và nhấn **Lưu quyết định**. Có bộ lọc chưa gán, mở rộng đọc ngoài pool và theo dõi tiến độ. Các nút lưu ghi CSV/JSON trong thư mục kit, không thay tài liệu PostgreSQL.

Tại **Duyệt truy vấn**, người thật ghi tác giả/người duyệt và xác nhận query. Tại **Quy trình & kiểm tra**, ghi người duyệt/cách xử lý bất đồng, chỉ xác nhận độc lập/phê duyệt khi đã thực hiện; nhấn **Kiểm tra bộ đánh giá** để kiểm tra đầu vào/độ phủ Top-20. Kiểm tra này không tính P@5/MRR; chạy CLI sau khi hợp lệ. Nếu kit có hai người gán, chọn vai trò A/B; chỉ dùng phần phân xử sau các quyết định độc lập.

Tên người gán và quyết định được lưu khi người dùng nhấn nút. Nếu CSV/JSON đã bị phiên khác đổi, ứng dụng từ chối ghi đè và yêu cầu làm mới. Đây là tiện ích nhập nhãn, không thay thế sự độc lập và chất lượng phán đoán của người đọc. Sau khi đánh giá có nhãn xong, giữ bản kit đã duyệt cùng output thực nghiệm để truy nguồn kết quả.

## Đo thời gian trước khi có nhãn

Thời gian truy vấn có thể đo riêng mà không quyết định relevance:

```bat
python -m scripts.benchmark_tv3_latency --source database --corpus vietonline_news_200 --rebuild --repeats 5 --warmups 1
```

Runner kiểm tra corpus/pipeline đã đóng băng, dùng index riêng `reports/tv3_latency_index`, làm nóng từng query rồi ghi mẫu API và core nạp sẵn vào `reports/tv3_latency.json`/`.csv` (ignored). Build, load, setup core và warmup được ghi riêng, không cộng vào các mẫu query. API là `RetrievalEngine.search_query`, gồm preprocessing, snapshot PostgreSQL, kiểm tra/nạp index và ranking; loại UI, metadata và đọc nội dung. Core loại cả preprocessing/snapshot/nạp index.

Mỗi query được lặp đều nhau; runner chạy tuần tự một client theo thứ tự CSV, không kiểm tra tải đồng thời. File ghi rõ `latency_only_no_relevance_metrics`, số draft/approved và phạm vi. Bộ 25 query nháp chỉ là workload timing tạm thời; đo thời gian không tự duyệt câu hỏi và không tạo Precision@5/MRR@20. Chạy lại trên bộ query cuối đã được duyệt để dùng cùng thí nghiệm chất lượng. `--source snapshot` là đọc JSON, không phải đo PostgreSQL.

Yêu cầu “feed” vẫn chờ xác nhận với giảng viên. Số tài liệu/revision trong bàn giao là mốc lịch sử; dùng `scripts.check_db` và snapshot hiện tại làm bằng chứng cho lần chạy mới.

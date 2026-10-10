# Phần báo cáo thành viên 3 — ứng dụng, đánh giá và tổng hợp

Đây là nguồn Markdown cho phần TV3, chưa phải báo cáo cuối của cả nhóm. Có [PowerPoint nháp 12 slide](tv3_slides.pptx) để chỉnh và luyện trình bày. Phần corpus/PostgreSQL của TV1, lý thuyết/ví dụ tính tay của TV2, nhãn đánh giá và nghiệm thu thủ công cần được ghép/rà soát trước nộp. Nội dung dựa trên phân công, mã hiện tại và bằng chứng được ghi rõ; không chuyển mốc lịch sử thành kết quả mới.

## 1. Mục tiêu và trách nhiệm

TV3 xây UI Streamlit, nối dữ liệu và engine, thể hiện trạng thái nhập/chỉ mục, chuẩn bị nhãn, tính Precision@5/MRR và đo độ trễ. Bàn giao còn gồm hướng dẫn chạy, checklist tích hợp, demo và nguồn slide để hoàn thiện hồ sơ nhóm.

Đầu vào là TXT/PDF có lớp văn bản tiếng Việt. OCR, embedding, chatbot, tìm kiếm ngữ nghĩa và TF-IDF tăng dần nằm ngoài lõi. Ứng dụng dùng PostgreSQL và API nhóm hiện có.

## 2. Kiến trúc tích hợp

```text
Streamlit app/main.py
  ├─ danh mục/reader/upload → smartdoc.ingestion → PostgreSQL + storage adapter
  └─ query/giải thích/rebuild → app.search_service
        ├─ snapshot ready + revision + fingerprint
        ├─ TF-IDF + inverted index + cosine + Top-K
        └─ index phiên bản + manifest

Corpus cố định + query + nhãn người đọc
  → evaluation.py / CLI → metric từng query, tổng hợp, thời gian và manifest
```

UI không chứa SQL. Document ID nối output engine với metadata/text; không dùng vị trí hàng ma trận thay ID. Tìm kiếm chỉ dùng tài liệu ready và phải đối chiếu revision, fingerprint, phạm vi corpus trước khi sử dụng index.

Build tạo bộ mới rồi kích hoạt sau kiểm tra, tránh trộn vectorizer/matrix/IDs khác phiên bản. Demo sửa corpus/rebuild tuần tự. Cache UI không thay thế freshness trong dịch vụ.

## 3. Thiết kế ứng dụng

Sáu trang: Tổng quan, Tìm kiếm, Thư viện, Đã lưu, Tải lên, Phân tích; theme tối/sáng dùng chung. Nhãn thành viên không đưa vào UI sản phẩm.

Tìm kiếm cho nhập query, chọn Top-K 5/10/20 và xem rank/title/score/nguồn/nội dung. Thư viện có lọc chuỗi, chủ đề, sắp xếp, phân trang để duyệt corpus; lọc chuỗi không được gọi là ranking TF-IDF.

Reader lấy raw_text DB khi mở tài liệu, xem metadata/nguồn HTTP(S), tìm và tô sáng cụm chính xác, xuất TXT UTF-8. Nội dung/cụm tìm được escape trước khi tạo HTML. Yêu thích/lịch sử dùng session Streamlit, chưa lưu giữa phiên.

Upload gọi ingestion API, hỗ trợ TXT/PDF text, tối đa 8 MiB/tệp; metadata bắt buộc tự sinh. UI báo kết quả từng tệp; duplicate không được đếm thành ready mới. Upload mang corpus `user_uploads`; thực nghiệm chọn riêng `vietonline_news_200`. Hai tên corpus vẫn dùng cùng DB/revision, nên nhãn corpus riêng không thay thế môi trường thử riêng; trong thực nghiệm phải giữ DB cố định hoặc dùng snapshot đóng băng.

## 4. Minh họa truy xuất

Pipeline mặc định chuẩn hóa NFC, lowercase, tách câu/từ bằng underthesea, giữ dấu/token nhiều âm tiết nối bằng gạch dưới. Stopword removal mặc định tắt; bật cần bộ stopwords rõ và fingerprint tương ứng. Không mô tả stopwords đã bật khi cấu hình thực chưa bật.

TF-IDF dùng raw count, smoothed IDF và L2:

```text
idf(t) = log((1 + N) / (1 + df(t))) + 1
w(t, d) = count(t, d) × idf(t)
v(d) = w(d) / ||w(d)||₂
cosine(q, d) = Σt v(q)[t] × v(d)[t]
```

Query transform với vectorizer fit trên corpus. Hợp postings tạo ứng viên; trả cosine dương, giảm dần, đồng điểm theo ID tăng dần.

Giải thích cho thấy token, posting list/tập ứng viên và contribution `q_t × d_t`; tổng contribution bằng score trong sai số số thực với vector L2. Ví dụ tính tay/sai số chi tiết cần nhận từ TV2; minh họa UI không thay thế tính tay.

## 5. Thiết kế đánh giá

Đóng băng corpus trước khi gán nhãn. Manifest giữ corpus identity, hash đầu vào retrieval, IDs/revision/fingerprint; protocol ghi quy tắc. Bộ 25 query từ tiêu đề thật là **draft**, chưa phải 25 query đã nghiệm thu. Đọc corpus để sửa query, duyệt ≥20 query chính và tách query không có relevant ra bộ kiểm thử hành vi.

Mặc định prepare tạo pool từ hợp Top-20 thật và seed ID theo tiêu đề, chỉ hiện ID sắp tăng dần để người gán không thấy score/rank. Bộ hiện tại có 500 cặp nhãn trống cho 25 query. Truy xuất chỉ chọn ứng viên cần đọc, không quyết định relevance. Người gán đọc nội dung theo information need, độc lập với điểm engine; người duyệt rà soát query/protocol và nhãn. Mỗi cặp cần `label_a/assessor_a`, nhãn cuối `relevant`, ngày giờ ISO8601 và evidence cho nhãn dương. Nếu đổi nhãn cuối, ghi adjudicator/resolution. Tùy chọn hai người gán yêu cầu thêm `label_b/assessor_b` và phân xử bất đồng.

Protocol ghi `judgment_scope=pooled_top20`, `assessor_count=1` mặc định; có thể tạo bộ mới với `--exhaustive` hoặc `--assessor-count 2`. Mọi tài liệu thực sự trong Top-20 của lần đo phải có nhãn trước tính metric; ô trống không tự bằng 0. Pool chỉ xác nhận P@5/MRR@20 cho bộ query đã chọn, không cho phép tuyên bố recall hoặc xác định relevance toàn corpus. Protocol draft/nhãn chưa đủ bị CLI từ chối.

Quy ước:

```text
P@5(q) = số relevant trong 5 vị trí đầu / 5
RR@20(q) = 1 / rank của relevant đầu tiên trong top 20; không có thì 0
MRR@20 = trung bình RR@20 trên các query metric
```

Khi ít hơn 5 kết quả, P@5 vẫn chia 5. CLI hiện tại ghi **MRR@20**, không phải MRR toàn bộ kết quả dương. Query không có nhãn dương bị loại khỏi bộ metric chính sau rà soát. Không thấy nhãn dương trong pool chưa chứng minh cả corpus không có tài liệu liên quan; nhóm cần đọc thêm/mở rộng pool hoặc ghi rõ đây là ca kiểm thử hành vi.

CLI tách build/load/warmup khỏi lặp query. API latency gồm đường gọi engine/tiền xử lý/snapshot/kiểm tra freshness/đọc index; chưa gồm UI hoặc lấy metadata/nội dung. `search_core` dùng engine đã nạp và query đã xử lý, loại preprocessing/snapshot/load index. Chế độ snapshot đọc JSON mỗi lần và không đo PostgreSQL latency; chế độ database dùng dịch vụ DB thật. Không lấy thời gian nạp snapshot hoặc toàn rerun Streamlit làm query latency. Ghi môi trường, warmup/lặp và corpus/index với kết quả.

Lệnh tái lập sau khi nhãn/protocol hoàn chỉnh:

```bat
python -m scripts.evaluate_retrieval --source snapshot --snapshot reports/tv2_news_corpus.json --rebuild --repeats 5
```

Có thể chọn nguồn DB bằng `--source database --corpus vietonline_news_200`. JSON/CSV mặc định ở `reports/tv3_evaluation.*`, không commit dữ liệu riêng hoặc nhãn kèm corpus text khi chưa thống nhất chia sẻ.

## 6. Kiểm thử và bằng chứng

| Lớp | Chứng minh được | Chưa chứng minh được |
| --- | --- | --- |
| Unit catalog/metric | Công thức, lọc, sort, phân trang trên fixture | Corpus thật/chất lượng ranking |
| Engine snapshot giả | Thuật toán, ID/tie, lifecycle, lỗi | DB/storage máy demo |
| PostgreSQL thật | Corpus/metadata/text/query hiện tại | P@5/MRR khi thiếu nhãn |
| UI thủ công | Theme, thao tác, reader/upload/thông báo | Toàn bộ tính đúng số học |
| Đánh giá có nhãn | Chất lượng trên bộ đã đóng băng | Ngữ nghĩa tổng quát ngoài bộ thử |

Ngày 10/10/2026, PostgreSQL thật healthy, có 200 ready, revision 235. Văn bản thật đầu snapshot đọc được 3.405 ký tự. Query “Xe điện” trả #18 hạng 1, cosine 0,7046896896391204; token `xe_điện`, tổng contribution khớp score. Query rỗng/OOV có trạng thái đúng. Đây là smoke test chức năng trên DB thật, chưa là đánh giá relevance.

Phép đo kết nối đơn lẻ trên Windows cho `localhost` 5,0398 giây và `127.0.0.1` 0,0309 giây. Đổi riêng host trong `.env` local, không sửa dịch vụ dữ liệu, cho snapshot 0,0541 giây và search “xe điện”, K=5 trong 0,4541 giây ở mẫu tiếp theo. Snapshot trước đó khoảng 5,076 giây. Các mẫu có phạm vi khác nhau, chưa warmup/lặp có kiểm soát nên không gọi là benchmark hoặc suy ra mức tăng tốc chung.

Lần nghiệm thu toàn repository qua `scripts.test_tv3_isolated_database --all-tests` đạt **147 tests PASS và 20 subtests PASS trong 11,48 giây**. Runner tạo DB/storage thử riêng rồi dọn; demo trước/sau đều 200 ready, revision 235. Nhóm năm test DB đã kiểm tra ingestion/recovery, TXT/PDF text nhập ready, duplicate, đọc text, TXT rỗng và PDF trống/hỏng failed. PDF được tạo để thử extraction, chưa thay thế kiểm tra PDF scan thực tế.

Trong toàn suite có test fixture engine/service, 14 UI AppTest, 4 upload boundary và 24 evaluation tổng hợp. [Nhật ký](tv3_acceptance.md) ghi phạm vi/lệnh. AppTest dùng service doubles, không thay kiểm tra trình duyệt với DB thật; test thay corpus không ghi vào DB demo.

Script `verify_tv3` PASS trên DB thật với bốn query cố định, đối chiếu ranking/score với cosine toàn corpus, kiểm tra raw_text, postings/contribution và nạp lại cùng index qua một đối tượng SearchService mới; corpus hash không đổi. Kiểm tra trình duyệt riêng đã mở sáu trang, tối/sáng, kết quả “Xe điện”, reader23matches, giải thích, lưu/bỏ lưu và lọc không dấu “xe dien”. Sau dừng/chạy lại tiến trình Streamlit, query vẫn #18 cosine 0,704690 với index đã lưu. Restart PostgreSQL, upload thực trên trình duyệt, tải TXT và responsive còn chờ; object reload trong script không tự chứng minh các bước đó.

Ca thêm/xóa/upload lỗi/rebuild lỗi chạy với DB/storage/index thử riêng, không để test suite ghi vào corpus đánh giá. UI thủ công vẫn cần người dùng xác nhận checklist.

## 7. Kết quả hiện có và phần chưa kết luận

Đã bổ sung tích hợp UI với ranking, freshness/rebuild và giải thích; duy trì reader/yêu thích/upload/thư viện. Đã chuẩn bị CLI, query draft, mẫu nhãn và tài liệu tái lập. Đây là phần triển khai, không thay bằng chứng nghiệm thu từng lớp.

Chưa công bố Precision@5/MRR@20 corpus thật vì cần hoàn tất nhãn độc lập. Không đưa metric fixture thành kết quả thực nghiệm. Sau đánh giá cần đọc query P@5/MRR thấp, tài liệu relevant bị bỏ sót và phân loại nguyên nhân: OOV, tách từ, thiếu ngữ cảnh hoặc query quá chung.

## 8. Hạn chế và việc cần hoàn tất

- Duyệt ≥20 query có relevant, hoàn thành nhãn pool và rà soát, approve protocol rồi chạy metric/latency thật; chọn gán đôi nếu nhóm có điều kiện.
- Hoàn tất UI thủ công, ca tích hợp DB thử và chạy theo hướng dẫn từ môi trường sạch.
- Dump có text/metadata nhưng không có file gốc; cần storage riêng nếu yêu cầu tải nguồn. Reference có trong DB không chứng minh file còn trên máy.
- “Feed” chờ xác nhận; local storage adapter là phương án hiện tại cần ghi rõ.
- Favorites/history theo phiên; tìm không dấu là tiện ích thư viện; TF-IDF chưa xử lý đồng nghĩa/ngữ nghĩa; PDF ảnh chưa OCR.
- Nhận phần TV1/TV2, tính tay, schema, nguồn corpus; ghép báo cáo Word/PDF/PPT cuối, luyện bảo vệ toàn luồng.

# Kịch bản demo SmartDoc Search

Mục tiêu: trình bày dữ liệu thật → chỉ mục → query → ranking → reader/giải thích, cùng cách tái lập đánh giá. Kịch bản dự kiến 7–10 phút; thời lượng là kế hoạch trình bày, không phải số đo hiệu năng.

## Chuẩn bị

1. Mở Docker Desktop, chờ engine chạy. CMD tại root repo: kích hoạt `.venv`, chạy `docker compose up -d --wait` và `python -m scripts.check_db`.
2. Ghi counts/revision và corpus dùng demo. Phiên kiểm tra ngày 10/10/2026 xác nhận 200 ready, revision 235; chạy kiểm tra lại trước bảo vệ nếu dữ liệu có thay đổi.
3. Chạy `python -m streamlit run app/main.py`. Kiểm tra trạng thái index và rebuild trước demo nếu cần.
4. Chọn trước 2–3 query từ corpus thực và mở thử tài liệu trả về. Query trình diễn không thay thế tập đánh giá có nhãn.
5. Nếu đã có nhãn, chuẩn bị CSV metric/môi trường. Nếu chưa, trình bày đúng là query nháp và mẫu nhãn đang hoàn thiện.
6. Demo thay corpus/upload/lỗi rebuild trên DB/storage/index thử riêng; giữ nguyên corpus đánh giá.

## Luồng trình bày

| Thời lượng dự kiến | Thao tác | Điểm cần nói |
| --- | --- | --- |
| 1 phút | Tổng quan, đổi theme | Thống kê từ metadata; revision không phải số tài liệu |
| 2 phút | Query, chọn K, xem kết quả | Pipeline chung; score dương; cosine; ít hơn K hợp lệ |
| 1 phút | Reader, nguồn, tải TXT | Tra metadata/text bằng ID; TXT là xuất text DB |
| 1–2 phút | Giải thích | Token từ ghép; hợp postings; tổng `q_t × d_t` bằng cosine với L2 |
| 1 phút | Query rỗng/OOV, trạng thái index | OOV là hạn chế từ vựng; freshness phải kiểm tra |
| 1–2 phút | CSV đánh giá/checklist | P@5 luôn chia 5; MRR@20; retrieval time tách build |

Có thể thêm Thư viện/Đã lưu nếu còn thời gian. Nêu favorites/history chỉ trong phiên, chưa có hệ thống tài khoản.

## Demo upload trên môi trường thử

1. Upload TXT nhỏ có tiếng Việt; không nhập metadata bắt buộc. Quan sát ID/ready.
2. Kiểm tra index cần rebuild; tìm để chứng minh không phục vụ chỉ mục stale.
3. Rebuild rồi tìm token có trong tệp mới, mở đúng ID/nội dung.
4. Upload lại cùng byte: duplicate, không thêm ready.
5. PDF ảnh/tệp lỗi báo rõ; không mô tả là OCR.

Thao tác này đổi revision DB thử. Không đưa query tổng hợp từ tệp vừa tạo vào metric corpus tin tức.

## Tái lập đánh giá sau khi nhóm gán nhãn

Nếu dùng bộ `evaluation/` đã có và snapshot còn khớp manifest, tiếp tục gán nhãn bộ đó. Khi cần tạo bộ mới, xuất snapshot và chọn thư mục mới:

```bat
python -m scripts.export_corpus --corpus vietonline_news_200 --output reports/tv2_news_corpus.json
python -m scripts.prepare_evaluation --snapshot reports/tv2_news_corpus.json --output reports/tv3_labeling
```

Mặc định script tạo pool gồm hợp Top-20 thật và seed ID theo tiêu đề, sắp ID và bỏ score/rank khỏi phiếu. Bộ hiện tại có 25 query draft và 500 cặp nhãn trống. Người gán đọc nội dung độc lập với điểm tìm kiếm; người duyệt rà soát query/protocol và quyết định nhãn. Duyệt ≥20 query, điền `label_a/assessor_a`, `relevant`, ngày giờ và evidence cho nhãn dương, rồi approve theo [hướng dẫn](../evaluation/README.md). Có thể chọn `--assessor-count 2` để gán đôi/phân xử bất đồng hoặc `--exhaustive` để gán toàn corpus. Prepare từ chối ghi đè; `--force` đặt lại toàn bộ nhãn.

```bat
python -m scripts.evaluate_retrieval --source snapshot --snapshot reports/tv2_news_corpus.json --evaluation-dir reports/tv3_labeling --rebuild --repeats 5
```

Có thể dùng DB thật với `--source database --corpus vietonline_news_200`. Nếu dùng bộ `evaluation/` hiện có, bỏ `--evaluation-dir reports/tv3_labeling`. JSON/CSV mặc định ở `reports/tv3_evaluation.*`, được Git ignore, chứa từng query, macro metric, API/core timing và build/load/warmup. Mọi document thực sự trả trong Top-20 phải có nhãn; thiếu nhãn bị từ chối, không tự tính là 0. Pool chỉ phục vụ P@5/MRR@20, không chứng minh recall hoặc relevance toàn corpus. Snapshot mode đọc JSON, không đo PostgreSQL latency; database mode dùng DB thật.

## Câu hỏi bảo vệ

- **Vì sao query không fit lại?** Fit độc lập làm khác vocabulary/IDF; query phải transform cùng không gian tài liệu.
- **Vì sao hợp postings?** Tài liệu chứa một phần query vẫn có cosine dương; giao postings loại mất ứng viên đó.
- **Score 0,8 có phải 80% liên quan?** Không; đó là cosine TF-IDF, relevance do người đọc gán.
- **Vì sao thiếu K?** Chỉ trả score dương; có thể ít hơn K tài liệu phù hợp theo mô hình.
- **Thiếu tệp gốc vẫn đọc được?** Dump có raw_text DB; muốn tệp nguồn cần storage riêng.
- **Upload ảnh hưởng đánh giá?** Corpus/manifest đánh giá cố định; demo thay corpus chạy riêng.
- **Chưa có P@5/MRR?** Query nháp và script chưa thay thế nhãn người thật.
- **Feed đã đáp ứng?** Nêu câu trả lời giảng viên hoặc trạng thái đang chờ; local adapter hiện tại chưa thay việc xác nhận.

## Dự phòng

Nếu DB lỗi, log/ảnh có ngày chỉ là bằng chứng lần chạy trước; nói rõ đang trình bày bản ghi. Index stale thì rebuild trước query. Thiếu storage gốc thì demo raw_text/tải TXT, không hứa mở tệp nguồn. Không dùng thứ hạng hoặc metric giả để duy trì demo.

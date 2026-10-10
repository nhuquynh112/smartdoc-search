# Nguồn nội dung slide bảo vệ — SmartDoc Search

Đây là **dàn ý nguồn Markdown**. [PowerPoint nháp 12 slide](tv3_slides.pptx) đã triển khai các chủ điểm dưới đây thành trang riêng, với text và bảng chỉnh sửa được. Bản nháp chưa phải hồ sơ nộp cuối: cần nhãn thật, metric và phần viết TV1/TV2. Thay mục chờ bằng bằng chứng thật, không dùng số ước đoán.

## Slide 1 — Bài toán và phạm vi

- Query tiếng Việt → TF-IDF → cosine → Top-K.
- TXT/PDF text; PostgreSQL, storage adapter, Streamlit.
- Tên/mã sinh viên của ba thành viên đúng danh sách nhóm.

Minh họa: query và ảnh ranking thật; không dùng mock thay ảnh chạy.

## Slide 2 — Kiến trúc

- Nhập → trích text → tiền xử lý → ready snapshot.
- Vectorizer + matrix + ordered IDs + inverted index + manifest.
- UI qua dịch vụ; metadata/text tra theo ID.

Minh họa: sơ đồ đã hợp nhất báo cáo.

## Slide 3 — Corpus và lưu trữ

- Chủ đề/nguồn/loại bỏ: **chờ báo cáo TV1**.
- Lần kiểm tra 10/10/2026: 200 ready, revision 235; kiểm tra lại trước bảo vệ.
- Metadata/SHA-256/status; DB dump và storage gốc chuyển riêng.
- Tình trạng xác nhận yêu cầu “feed”.

## Slide 4 — Tiền xử lý và TF-IDF

- NFC, lowercase, tách từ; giữ dấu/token từ ghép.
- Stopwords theo cấu hình, mặc định hiện tắt.
- TF raw count, IDF smoothing, L2; query transform cùng vectorizer.

Minh họa: trước/sau và tính tay 3–5 tài liệu TV2 kiểm chứng.

## Slide 5 — Chỉ mục đảo và ranking

- Token → postings; hợp postings tạo ứng viên.
- Cosine > 0, giảm dần, hòa điểm ID tăng dần; có thể thiếu K.
- Đóng góp `q_t × d_t` giải thích score.

Minh họa: giải thích thật và đối chiếu cosine toàn corpus từ TV2.

## Slide 6 — Giao diện

- Top-K 5/10/20, rank/title/score/nguồn/nội dung.
- Reader/tải TXT, lưu phiên, thư viện, tối/sáng.
- Upload TXT/PDF, metadata sinh tự động, phản hồi từng tệp.

Minh họa: ảnh sáng/tối/reader, không có nhãn TV1/TV2/TV3 trong UI.

## Slide 7 — Nhất quán và phục hồi

- Corpus đổi → stale → rebuild trước phục vụ.
- Chỉ kích hoạt bộ mới sau kiểm tra.
- Empty/OOV/index lỗi báo rõ.
- Thay corpus/lỗi thử trên DB riêng.

Nêu rõ log nào fixture, log nào PostgreSQL thật.

## Slide 8 — Thiết kế thực nghiệm

- 25 query draft; duyệt ≥20 query chính.
- Pool Top-20 + seed có 500 cặp trống; người gán đọc độc lập với score/rank, người duyệt rà soát. Có thể chọn hai người gán.
- P@5 luôn /5, MRR@20; query không relevant tách riêng.
- Corpus manifest, protocol, warmup/lặp và môi trường.

Minh họa: một hàng nhãn đã được người đọc xác nhận, không dùng ô trống như label 0.

## Slide 9 — Kết quả và phân tích lỗi

- **Chờ** CSV query, P@5/MRR@20 trung bình, latency và môi trường.
- **Chờ** 2–3 query thất bại, relevant bị bỏ sót và nguyên nhân.
- Toàn repository qua runner DB riêng: 147 tests và 20 subtests PASS trong 11,48 giây; demo trước/sau 200 ready, revision 235. Năm test DB riêng có TXT/PDF ingestion, duplicate, lỗi và recovery.
- Trình duyệt thật đã kiểm tra sáu trang, sáng/tối, reader23matches/giải thích, lưu/bỏ lưu, lọc không dấu và restart Streamlit; upload thực/tải TXT/responsive còn chờ.

Nếu chưa có nhãn, đặt tên “Tiến độ thực nghiệm” và nói phần còn thiếu; không thêm bảng số giả.

## Slide 10 — Hạn chế và bàn giao

- Khớp từ vựng/OOV/đồng nghĩa; PDF ảnh chưa OCR.
- File gốc cần storage; favorites/history theo phiên.
- Feed: câu trả lời giảng viên hoặc còn chờ.
- Hướng dẫn, test/checklist, CLI đánh giá, báo cáo/demo; ghép hồ sơ nhóm.

Chuyển sang demo thật và câu hỏi; không khẳng định nghiệm thu các ô còn trống.

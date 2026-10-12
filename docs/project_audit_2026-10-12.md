# Rà soát đồ án ngày 12/10/2026

Phạm vi: nhánh `Dat`, commit `29efffc`; đối chiếu README, checklist TV1, báo cáo nghiệm thu TV2, nghiệm thu/kế hoạch còn lại TV3 và mã nguồn. Chưa có bản đề gốc hoặc bảng phân công bên ngoài repo, nên yêu cầu chưa được giảng viên xác nhận được ghi là cần làm rõ.

Kết luận: đủ chạy demo chức năng; chưa đủ kết luận nghiệm thu toàn đồ án hoặc chất lượng truy xuất. Không sửa mã sản phẩm, nhãn hay protocol trong lần rà này.

Theo yêu cầu sửa sau audit, phần triển khai tiếp theo đã bổ sung kiểm tra số học/cấu hình và checksum artifact, bỏ cache raw_text reader, bảo vệ các test mutation bằng DB isolated, cập nhật checklist TV1/trạng thái storage và tạo kit trắng mới khớp DB tại thời điểm xuất. Các phần bên dưới giữ bằng chứng và trạng thái **trước sửa**. Bộ `evaluation/` cũ, nhãn người thật và yêu cầu “feed” không bị thay đổi. Kết quả xác minh sau sửa được ghi trong `docs/project_fixes_2026-10-12.md`.

## 1. Bằng chứng mới

- Kiểm tra tích hợp trước lần audit: 200 ready, revision 249; ranking so với exhaustive cosine, đọc text, postings/contributions và nạp lại index PASS (`reports/tv3_integration.json`). Đây là bốn query kiểm tra cơ chế, không phải metric relevance.
- Audit chỉ đọc hiện tại: 200 bản ghi ready, tất cả TXT, 112.432 token trước stopword removal; không thiếu source DB; không có lỗi file gốc/hash/kích thước/cache (`reports/data_quality_summary.json`, `reports/data_quality_report.csv`). Không suy ra chất lượng ngôn ngữ, quyền chia sẻ hoặc nguồn xuất bản từ kết quả này.
- Toàn suite qua `python -m scripts.test_tv3_isolated_database --all-tests`: **236 tests + 38 subtests PASS trong 47,31 giây**. DB/storage thử được dọn; demo trước/sau đều 200 ready, revision 249 (`reports/tv3_database_tests.json`).
- Bộ `evaluation/`: 25 query, 0 query approved; 500 judgment, 0 nhãn cuối; protocol draft.
- DB news hiện revision 249; manifest nhãn revision 235; identity hash vẫn trùng. `validate_frozen_corpus` từ chối với `Frozen corpus mismatch: corpus_revision`.

Các report trong `reports/` là đầu ra local bị Git ignore và có thể được lệnh sau ghi đè; giữ bản sao riêng khi chốt hồ sơ nghiệm thu.

## 2. Đối chiếu phân công và kế hoạch

| Phần việc | Trạng thái có bằng chứng | Còn thiếu/điều kiện |
| --- | --- | --- |
| TV1: DB, metadata, TXT/PDF, preprocessing, storage, export | Mã và test đã có; corpus thật 200 TXT, storage audit đạt | Duyệt nội dung mẫu, provenance/điều kiện chia sẻ dataset, chốt “feed”; PDF scan thực tế và chuyển gói dữ liệu sang máy khác |
| TV2: TF-IDF, inverted index, cosine, Top-K, explain, version | Fixture test và tích hợp DB đạt; có ví dụ tính tay trong báo cáo TV2 | Gia cố validation số học artifact; đưa ví dụ tính tay vào test end-to-end làm bằng chứng liên kết nếu cần |
| TV3: UI, upload/rebuild, reader, lịch sử, CSV | AppTest và nhật ký browser đã có; các test hiện tại đạt | Sửa cache reader; hoàn tất cửa sổ hẹp/PDF scan thật theo checklist |
| TV3: query, relevance, P@5, MRR@20, phân tích lỗi | Có công cụ/kiểm tra tính đầy đủ, chưa có nhãn thật | Khôi phục môi trường gán nhãn khớp kit hoặc tạo kit mới; duyệt ít nhất 20 query, gán/duyệt nhãn và chạy metric |
| Cả nhóm: tái lập, báo cáo/slide, nghiệm thu | Có hướng dẫn và bản nháp | Chốt bản bàn giao; chuyển DB/storage sang máy khác; ghép báo cáo TV1/TV2/TV3 với số đo thật và tập luyện |

Không thêm chatbot, OCR, embedding hoặc tài khoản trước khi hoàn tất các điều kiện baseline. Tìm không dấu/đồng nghĩa là hướng thử nghiệm riêng, chưa phải lỗi nếu nằm ngoài yêu cầu đã thống nhất.

## 3. Phát hiện và ưu tiên

### P1 — Bộ gán nhãn live hiện bị chặn bởi revision

`evaluation.py:150–157` kiểm tra revision tuyệt đối; `app/evaluation_review.py` áp dụng khi mở/lưu kit. Manifest 235 không khớp DB 249 dù identity còn giống. Đây là kiểm tra an toàn hoạt động đúng, nhưng quy trình demo và đánh giá chưa tách đủ: mọi thay đổi corpus khác cũng tăng revision global, làm kit news mất khớp.

Lượt kiểm tra trước của trợ lý đã chạy test mutation trên DB demo, làm revision 245 → 249; số ready giữ 200. Không giảm revision hoặc sửa hash thủ công để vượt kiểm tra. Kit đã ở revision 235 trước lượt đó.

Hướng xử lý: giữ kit cũ; dùng bản DB/snapshot đóng băng tương ứng nếu có. Hoặc xuất snapshot hiện tại và tạo kit mới ở thư mục mới, giữ query đã rà soát và bắt đầu gán nhãn thật. Hiện nhãn cũ đều trống. Công cụ gán nhãn live cần DB khớp kit; CLI snapshot một mình không làm trang review live dùng snapshot. Về lâu dài cân nhắc revision theo corpus hoặc backend đọc snapshot cho review, kèm kiểm tra text/identity đầy đủ.

Điều kiện đạt: mở/lưu nhãn trên đúng corpus được chốt; mutation sandbox không làm mất hiệu lực kit; evaluator vẫn từ chối dữ liệu khác.

### P1 — Chưa có bằng chứng chất lượng tìm kiếm

500 nhãn trống và protocol draft nên chưa có P@5/MRR@20 hợp lệ. 236 test PASS xác nhận logic, không xác nhận tài liệu trả về thực sự relevant. Query gợi ý từ tiêu đề cũng có thể thuận lợi cho TF-IDF; cần người duyệt chọn nhu cầu thông tin đủ đa dạng, giữ query khó và kết quả 0 theo protocol, đọc ngoài pool nếu cần.

Điều kiện đạt: ít nhất 20 query được duyệt; nhãn người thật và bằng chứng; metric mỗi query và tổng hợp; timing có phạm vi/môi trường; 2–3 ca phân tích lỗi từ kết quả thật. Không tự tạo nhãn hoặc coi nhãn trống là 0.

### P2 — Loader chấp nhận artifact sai số học

`smartdoc/tfidf_engine.py:197–242` xác minh shape/count/type nhưng chưa xác minh giá trị hữu hạn, không âm, chuẩn L2 hoặc tính toàn vẹn từng file. Thử với artifact tạm một tài liệu `xe_điện`, nhân trọng số ma trận lên ba: loader vẫn nạp, search trả score **3,0**. Thay ma trận bằng NaN: loader cũng chấp nhận. Không thay artifact demo trong phép thử này.

Hướng sửa TV2: từ chối NaN/Inf/âm, kiểm tra chuẩn L2 hàng khác zero trong tolerance, IDF/vocabulary/config tương thích; bổ sung checksum artifact để phát hiện thay đổi vẫn giữ shape. Không chỉ clamp score vì sẽ che dữ liệu sai.

Điều kiện đạt: test tái hiện artifact hỏng bị từ chối; active index tốt trước đó vẫn dùng được khi rebuild lỗi; index hợp lệ vẫn cho ranking/explain đúng.

### P2 — Reader giữ text cũ khi tài liệu cùng ID được cập nhật ngoài UI

`app/main.py:90–93,276–304`: text cache 600 giây chỉ theo document ID. Reader kiểm tra tài liệu còn ready nhưng không kiểm tra version text. `reprocess_corpus` có thể cập nhật raw_text cùng ID, còn cache chỉ bị xóa bởi thao tác UI làm mới/rebuild/upload.

Tái hiện bằng AppTest với service doubles: mở reader nhận `OLD_BODY_ABC`; đổi backend sang `NEW_BODY_XYZ` cùng ID; mở lại vẫn thấy OLD, không thấy NEW; text API chỉ được gọi một lần, không có UI exception. Đây là tái hiện cache trên fixture, không ghi DB demo.

Hướng sửa TV3/TV1: khóa cache theo revision/content version được đọc nhất quán với text; hoặc bỏ cache raw_text và đọc theo yêu cầu. Thư viện/thống kê cũng cache 600 giây nên mutation từ CLI có thể chưa hiện cho tới refresh/TTL.

Điều kiện đạt: cập nhật cùng ID ở backend, mở lại reader nhận text mới; xóa/non-ready vẫn bị chặn; metadata/text không thuộc hai phiên bản khác nhau.

### P2 — Hồ sơ bàn giao chưa đồng bộ

`docs/tv1_checklist.md` còn bỏ trống cả DB/extraction/preprocessing dù đã có bằng chứng. README và báo cáo TV3 ghi các mốc cũ; `docs/tv3_remaining.md` còn nói máy thiếu original, trong khi audit mới xác nhận 200 file gốc hiện có và hash đạt. Giữ mốc lịch sử nhưng thêm trạng thái hiện tại theo máy/ngày, không thay tất cả con số cũ thành số mới.

`main` chưa có bản tích hợp; chỉ `Dat` chứa cả TV1/TV2/TV3. README đã chỉ rõ Dat nên đây chưa phải bug clone theo hướng dẫn, nhưng nhóm cần chốt branch/tag bàn giao hoặc PR hợp nhất sau review. Không tự merge/push trong lần audit.

### P3 — Giới hạn upload chưa giới hạn chi phí giải nén/xử lý PDF

`app/upload_service.py` giới hạn 8 MB đầu vào; `smartdoc/document_loader.py:33–36` trích xuất mọi trang rồi ghép toàn text, chưa giới hạn trang, output text hoặc timeout. File nén nhỏ nhưng text lớn có thể tốn RAM/CPU, giữ corpus lock lâu trong ingestion và chặn tìm kiếm. Đây là rủi ro từ đọc mã, chưa stress test hoặc tái hiện treo.

Hướng cải thiện: cap số trang/text và thời gian xử lý ở tầng loader/service, thông báo rõ; thử PDF scan thật và PDF nhiều trang trong sandbox. Không cần triển khai OCR cho baseline.

### P3 — Chi phí snapshot/index lặp ở mỗi query

`SearchService.search` gọi inspect trước/sau, public retrieval còn đọc snapshot; mỗi inspect lại nạp artifact và dựng inverted index. Cơ chế freshness hiện bảo thủ và đã đạt kiểm tra, nhưng khóa chung tuần tự hóa search/rebuild nên tải nhiều phiên hoặc corpus lớn có thể chậm. Chưa có bằng chứng lỗi hiệu năng với 200 tài liệu ở lần audit này.

Hướng cải thiện sau baseline: đo API/core trên bộ query cuối; đọc metadata revision nhẹ cho freshness và cache immutable index theo version, giữ kiểm tra trước/sau và tests race/stale. Chưa tối ưu nếu không có số đo chứng minh cần.

## 4. Các điểm nghiệp vụ cần diễn đạt đúng

- Source của news là trang dataset, không phải URL bài báo gốc. Không gọi “0 missing source” là đã truy đủ nhà xuất bản hoặc quyền chia sẻ. Nút nguồn nên thể hiện nguồn dataset khi phù hợp.
- Corpus thật hiện là 200 TXT; hỗ trợ PDF có test/nhật ký riêng, không chứng minh corpus thật có PDF hay đã có OCR.
- “Phân tích” UI là thống kê corpus; chất lượng ranking phải có relevance labels và thực nghiệm riêng.
- Local storage có DB text và original không tự chứng minh đáp ứng chữ “feed” trong đề. Cần bản yêu cầu/xác nhận của giảng viên.
- Favorites/history ở session hiện phù hợp demo; không hứa lưu qua restart hoặc tài khoản dùng chung.

## 5. Thứ tự hoàn thiện đề xuất

1. Chốt đề gốc/“feed”, corpus và branch bàn giao; tách DB demo, test và đánh giá. Dùng runner isolated cho mọi test mutation.
2. Sửa validation artifact và cache reader, thêm regression tests cho các ca đã tái hiện; chạy lại suite isolated và verify chỉ đọc.
3. Chuẩn bị kit khớp corpus được đóng băng; người thật duyệt/gán nhãn; chạy P@5/MRR@20, timing và phân tích lỗi.
4. Cập nhật checklist TV1, ghi trạng thái original hiện tại, giữ report minh chứng; tổng duyệt PDF scan/cửa sổ hẹp và chuyển gói sang máy khác.
5. Ghép báo cáo/slide dựa trên kết quả thật, rồi chốt bản nộp qua quy trình nhóm.

# Nghiệm thu phần ứng dụng và đánh giá

Tài liệu này tách **chức năng đã có trong mã**, **test tự động**, **PostgreSQL thật** và **UI thủ công**. Có mã/checklist không đồng nghĩa đã nghiệm thu. Ngày chạy, output và ảnh cần được giữ cùng lần nghiệm thu; không dùng số liệu lịch sử làm kết quả mới.

Lần rà soát cuối bắt đầu ngày **11/10/2026**. Xem [các bước còn lại](tv3_remaining.md) để hoàn tất đúng phạm vi TV3. Báo cáo và slide cuối được hoãn theo yêu cầu người dùng; không xem tài liệu nháp là hồ sơ nộp đã duyệt.

## Đối chiếu nhiệm vụ

| Yêu cầu TV3 | Bàn giao | Điều kiện còn phải kiểm tra |
| --- | --- | --- |
| Query, Top-K, rank/title/score/nguồn/nội dung | `app/main.py`, `app/search_service.py` | DB thật PASS, UI query/reader đã quan sát; còn tổng duyệt đầy đủ |
| Upload và trạng thái index | Ingestion API + freshness + rebuild trong UI | Upload TXT/PDF/duplicate/lỗi qua trình duyệt DB tách biệt PASS ngày 11/10; stale bị chặn; các bước rebuild/lifecycle theo nhật ký |
| Minh họa thuật toán | Token, postings/ứng viên, trọng số/đóng góp | DB thật PASS, tổng contribution khớp cosine; đã xem bảng trên UI |
| Tập đánh giá | `evaluation/` và CLI chuẩn bị nhãn | ≥20 query được duyệt, nhãn người thật, giải quyết bất đồng |
| Precision@5, MRR, thời gian | `evaluation.py`, CLI đánh giá | Corpus cố định, kết quả từng query, môi trường và số lần đo |
| Hồ sơ/demo | Hướng dẫn, báo cáo TV3, demo, nguồn slide | Ghép TV1/TV2, số liệu thật, hoàn thiện slide và luyện bảo vệ |

## Test tự động không cần PostgreSQL

CMD tại root repo, sau khi kích hoạt `.venv`:

```bat
python -m pytest tests/test_tv3_catalog.py tests/test_tv3_search_service.py tests/test_tv3_app.py tests/test_tv3_result_utils.py tests/test_tv3_review.py tests/test_tv3_evaluation.py tests/test_tv3_latency.py tests/test_tv3_upload.py tests/test_tfidf_engine.py tests/test_inverted_index.py tests/test_search_engine.py tests/test_index_manager.py tests/test_retrieval_engine.py -q
```

Lệnh trên chọn test engine, tích hợp, UI, upload boundary và đánh giá dùng fixture/doubles. Muốn chạy toàn bộ repository, dùng runner DB tách biệt ở dưới.

Engine test dùng corpus nhỏ/snapshot được tiêm vào để kiểm tra thuật toán, ID, persistence và lỗi. Đây là bằng chứng logic trên fixture, không phải chất lượng ranking với 200 bài báo thật.

Không chạy toàn bộ `unittest discover` hoặc toàn bộ suite trên DB demo mặc định: test ingestion/recovery của nhóm có thao tác ghi/xóa và có thể tăng revision. Các ca thay corpus chỉ chạy trên database/storage/index tách biệt dành cho thử nghiệm.

## PostgreSQL thật — chỉ đọc

```bat
docker compose ps
python -m scripts.check_db
python -c "import time; from smartdoc.ingestion import load_corpus_snapshot; t=time.perf_counter(); s=load_corpus_snapshot(None); print('documents=',len(s['documents'])); print('revision=',s['corpus_revision']); print('snapshot_seconds=',round(time.perf_counter()-t,4))"
```

Ghi rõ corpus của lần chạy. Toàn thư viện có thể khác `vietonline_news_200` nếu đã upload; không dùng lẫn số lượng. Build index từ UI tạo artifact local, không thêm/xóa tài liệu DB.

## Checklist UI thủ công

Ô đã đánh dấu có bằng chứng quan sát trình duyệt ở ngày ghi kèm hoặc nhật ký tương ứng. Mốc 10/10 dùng corpus demo thật; mốc 11/10 dùng sandbox PostgreSQL và fixture tổng hợp khi có ghi rõ. Các ô còn lại cần tổng duyệt; unit test không tự đánh dấu UI thủ công.

- [x] Chạy app từ root repo; đã mở sáu trang trên trình duyệt thật, ngày 10/10/2026.
- [x] Chuyển tối/sáng trên trình duyệt thật, ngày 10/10/2026; bản nâng cấp quan sát lại trên sandbox 11/10 tại 1280×720, nội dung đọc được.
- [ ] Kiểm tra kỹ cửa sổ hẹp: yêu cầu viewport 390px trong công cụ không được áp dụng, DOM vẫn 1280×720; chưa có bằng chứng mobile.
- [x] Query “Xe điện” hiển thị tài liệu #18 và score thật trên trình duyệt.
- [x] Top-K sandbox 11/10: “xe điện” Top-5/10 có đúng 1/5 rồi 1/10, rank/score/ID không đổi; “giáo dục” Top-20 trả #1 cosine 0,333333 và đúng 1/20 sau restart.
- [x] Sandbox 11/10: query rỗng và `!!!` có thông báo empty, không kết quả; “xe điện” sau xóa tài liệu liên quan có OOV, không score giả.
- [x] Ít hơn K điểm dương chỉ hiển thị kết quả thực: sandbox ngày 11/10, query “xe điện” có đúng 1/5 kết quả, ID #2 cosine 0,21878120990146813.
- [x] Reader từ kết quả đọc được tiếng Việt; nhập “xe điện” thấy 23 vị trí tô sáng.
- [x] Reader từ thư viện sandbox 11/10: sau restart DB/app, mở PDF tổng hợp #3 và đọc đúng raw_text tiếng Anh đã trích xuất.
- [x] Reader kết quả sandbox ngày 11/10 hiển thị raw_text tiếng Việt đúng, metadata ID/title/source của #2; tải `smartdoc_2.txt` thành công.
- [x] Lưu tài liệu, Đã lưu hiển thị 1; bỏ lưu trở về rỗng trên trình duyệt thật.
- [x] Thư viện lọc không dấu “xe dien” ra tài liệu #18 trên trình duyệt thật.
- [x] Thư viện corpus thật 200 bài ngày 11/10, chỉ đọc: trang 1/34 → 2 bắt đầu #211; chủ đề Giáo dục có 40 bài và reset trang 1/7; sort nhiều từ giảm dần, A–Z và lọc “xe dien” ra riêng #18. Đây là các ca đã quan sát, không bao phủ mọi tổ hợp filter/sort/page.
- [x] Bản nâng cấp 11/10: query “xe điện”/Top-10 và kết quả giữ khi sang Thư viện rồi trở lại; replay lịch sử Top-5 gọi lại engine (UI ghi 124,3 ms ở lần đó, không benchmark).
- [x] Xóa lịch sử trên trình duyệt sandbox 11/10 làm mục lịch sử biến mất; giới hạn tối đa 12 mục được kiểm tra bằng AppTest.
- [x] Bản nâng cấp 11/10: tải CSV thật từ sandbox, kiểm tra query/Top-K, score đầy đủ và version `rev-3-a8378b96a863`/revision 3; đầu ra chỉ từ response đã qua freshness, stale sau upload bị chặn trước rebuild. UTF-8 BOM/formula test được kiểm tra riêng bằng unit test.
- [x] Không gian gán nhãn riêng được mở trên trình duyệt: 0/25 query duyệt, 0/500 nhãn, raw_text thật #18 hiển thị; không tạo nhãn/duyệt giả trên kit thật. Lưu quyết định/CAS xung đột được kiểm tra bằng fixture, việc gán nhãn thật là bước người dùng tiếp theo.
- [x] Giải thích trên trình duyệt có bảng contribution và posting `xe_điện:[18]`, khớp output engine.
- [x] Dừng rồi khởi động lại tiến trình Streamlit; trang chủ tải được, query “xe điện” vẫn #18 cosine 0,704690 và dùng index đã lưu.
- [x] Sandbox 11/10: ngắt DB báo index unavailable thân thiện, detail timeout không lộ credentials và ẩn kết quả; nối lại trả #2 cùng cosine.
- [x] Upload TXT/PDF text hợp lệ, trùng TXT/PDF, TXT rỗng, PDF hỏng và PDF trắng đã quan sát qua trình duyệt sandbox ngày 11/10; ready/duplicate/lỗi đúng, không thêm ready cho tệp lỗi/trùng.
- [x] Sau upload đổi corpus, query bị chặn bởi stale trước rebuild trên trình duyệt sandbox ngày 11/10.
- [x] Rebuild từ trình duyệt sandbox ngày 11/10 kích hoạt bộ revision 3 cho 3 ready; query mới đọc được tài liệu TXT đã upload.
- [x] Sandbox 11/10: xóa ID #2 qua API riêng tăng revision 4, giữ IDs #1/#3; thao tác reader cũ loại kết quả và báo corpus đổi. Rebuild có 2 ready, query “xe điện” trở thành OOV đúng.
- [x] Sandbox 11/10: restart PostgreSQL và Streamlit vẫn 2 ready/revision 4, reader #3 đọc đúng, “giáo dục” Top-20 trả #1 bằng chỉ mục đã lưu, không rebuild sau restart.
- [x] Sandbox cũ đã `quit` và dọn đúng container/volume thử do runner tạo; corpus demo giữ riêng.

## Ca thay đổi corpus — chỉ trên môi trường thử tách biệt

Runner trình duyệt riêng dùng image `postgres:16` đã có ở Docker; không tải image mới và không dùng container/DB demo:

```bat
python -m scripts.tv3_browser_sandbox
```

Giữ terminal mở và vào **đúng URL `Isolated UI` được runner in ra**, có dạng `http://127.0.0.1:8504/tv3-qa-<mã-ngẫu-nhiên>`; không dùng riêng URL gốc port 8504. Runner kiểm tra port/readiness, in đường dẫn các fixture TXT/PDF tổng hợp để upload, tự đặt PostgreSQL riêng ở port 55433 cùng storage/index/thư mục tạm. Trong terminal có thể nhập `status`, `restart_app`, `restart_db`, `disconnect`, `reconnect` hoặc `delete ID` để thử lifecycle trên dữ liệu thử. Nhập `quit` để dừng app và dọn đúng container/volume tạm mà runner đã tạo. Nếu port đang dùng, chọn `--port`/`--database-port` khác. Đây là runner tái lập thao tác, không tự đánh dấu PASS thay người quan sát.

Dùng DB thử với `DATABASE_URL`, `STORAGE_ROOT` và index root riêng. Không reset volume hoặc đổi `.env` của corpus đánh giá. Ghi rõ fixture/tệp tổng hợp trong kết quả.

| Ca thử | Kết quả mong đợi | Trạng thái |
| --- | --- | --- |
| Upload TXT hợp lệ | Ready và đọc lại text | Ingestion DB thử PASS; upload, ready, query sau rebuild và reader raw_text/TXT download qua trình duyệt sandbox PASS ngày 11/10 |
| PDF có lớp chữ | Ready và đọc lại text | Ingestion DB thử và upload qua trình duyệt sandbox PASS ngày 11/10; PDF tổng hợp có text |
| Trùng SHA-256 | Duplicate; không thêm ready | PASS TXT/PDF trên DB thử và trình duyệt sandbox ngày 11/10 |
| Quá 8 MiB/tên tệp/batch lỗi | Chặn biên đúng, tệp tạm được dọn | PASS ingestion stub |
| TXT rỗng, PDF trống/lỗi | Failed, không ready giả | PASS DB thử và trình duyệt sandbox ngày 11/10; PDF trắng mô phỏng không có text, scan thật còn cần thử |
| Thêm/xóa ready và index stale | ID cũ ổn định; không phục vụ bộ lệch | Ingestion/delete PASS DB thử; sandbox 11/10 upload đổi revision bị chặn; delete #2 giữ #1/#3, ẩn kết quả cũ, rebuild rồi “xe điện” OOV |
| Build lỗi/snapshot đổi | Không công bố bộ dở; thử lại được | PASS index/service fixture; lỗi đĩa thật không được gây ra |
| Corpus rỗng | Empty corpus | PASS fixture/AppTest |
| Restart và index persistence | Đọc metadata/text/index lại | Service object reload PASS; Streamlit demo restart ngày 10/10 PASS. Sandbox ngày 11/10 restart PostgreSQL/app giữ 2 ready/revision 4, reader #3 đúng và query #1 dùng index đã lưu không rebuild |

UI không bắt buộc có nút xóa; ca delete dùng API dữ liệu trong DB thử. Không xóa corpus thật để chỉ chứng minh stale.

## Nhật ký bằng chứng

| Loại | Kết quả ghi nhận trong hồ sơ này |
| --- | --- |
| Toàn bộ repository 10/10/2026 | **147 tests PASS, 20 subtests PASS trong 11,48 giây** qua runner `--all-tests` trên DB/storage tách biệt |
| Rà soát lại trước nâng cấp 11/10/2026 | **147 tests PASS, 20 subtests PASS trong 13,66 giây** trên DB/storage tách biệt; `verify_tv3` chỉ đọc PASS với demo 200 ready, revision 235. Đây là mốc trước các thay đổi của lần nâng cấp cuối |
| Toàn suite sau nâng cấp 11/10/2026 | **204 tests PASS, 28 subtests PASS trong 56,02 giây** bằng `.venv` và runner DB tách biệt, trước khi thêm các test runner latency mới; demo 200 ready, revision 235 giữ nguyên |
| Môi trường Python mới, mốc đầu 11/10/2026 | Tạo venv mới, cài `requirements_tv3.txt` thành công, `pip check` PASS; toàn suite trên DB tách biệt **204 tests PASS, 28 subtests PASS trong 84,55 giây**, trước guard/test bổ sung |
| Toàn suite cuối cùng 11/10/2026 | Môi trường venv mới với toàn bộ fix/test cuối: **236 tests PASS, 38 subtests PASS trong 65,80 giây**, sau chỉnh tương phản badge; lần liền trước 51,09 giây. Chạy qua runner DB/storage tách biệt; demo giữ **200 ready, revision 235**, DB thử được dọn. Chứng minh dependency/schema/test trên máy này; không tự chứng minh restore gói corpus trên máy khác |
| Nhóm catalog/service/engine trước đó | 84 PASS trên fixture; là một phần được chạy lại trong toàn suite |
| UI AppTest 10/10/2026 | 14 PASS, service doubles; không ghi DB và không thay kiểm tra ảnh/theme thủ công |
| UI/CSV sau nâng cấp 11/10/2026 | **39 PASS trong 40,41 giây**, gồm 31 AppTest và 8 CSV test thuần; query/Top-K phiên, lịch sử/replay/xóa, freshness trước xuất, UTF-8 BOM, vô hiệu công thức và chặn reader/cache cũ khi ID không còn ready. AppTest dùng service doubles, không chứng minh trình duyệt/DB thật |
| Runner latency không cần nhãn | Mốc ban đầu 15 test tổng hợp PASS; test guard bổ sung nằm trong lần chạy toàn suite sau. Chỉ kiểm thử phép đo, đồng nhất kết quả API/core và điều kiện đầu vào; không phải metric corpus thật |
| Runner browser sandbox sau guard | 12 test helper PASS; kiểm tra port/readiness/đường dẫn và điều kiện runner, tách khỏi kết quả thao tác trình duyệt |
| Smoke runner browser sau guard 11/10 | Chạy bằng venv mới, chờ health của URL path ngẫu nhiên, mở đúng app sandbox và thấy 1 seed/9 từ/revision 1. Sau `quit`, runner xác nhận dọn đúng container/volume do nó tạo, demo không đổi |
| Không gian rà soát nhãn | Trình duyệt đọc raw_text thật #18, tiến độ 0/25 query duyệt và 0/500 nhãn. 25 test fixture kiểm tra lưu/quy trình/CAS; không ghi quyết định giả lên kit thật |
| Evaluation unit test 10/10/2026 | 24 PASS với dữ liệu tổng hợp; chưa là metric corpus thật |
| Upload boundary test 10/10/2026 | 4 PASS với ingestion stub; giới hạn tệp, tên tệp tạm, lỗi/duplicate không ghi DB |
| PostgreSQL thử tách biệt | Nhóm DB riêng 5 PASS trong 4,34 giây; gồm ingestion/recovery và TXT/PDF upload. Toàn suite cũng đã chạy lại trên DB thử; demo trước/sau vẫn 200 ready, revision 235 |
| PostgreSQL 10/10/2026 | Container healthy; 200 ready, revision 235; raw_text tài liệu đầu đọc được 3.405 ký tự |
| Live ranking/explain 10/10/2026 | Query “Xe điện” có #18 hạng 1, cosine 0,7046896896391204; token `xe_điện`, tổng contribution khớp; query “trí tuệ nhân tạo” điểm đầu 0,10410627136419519; empty/OOV đúng trạng thái |
| Snapshot toàn thư viện trước chỉnh host | 200 tài liệu, revision 235; một lần đọc khoảng 5,076 giây, không phải benchmark retrieval |
| Kết nối Windows trước/sau chỉnh host | Một mẫu `localhost`: 5,0398 giây; một mẫu `127.0.0.1`: 0,0309 giây. Chỉ đổi host trong `.env` local |
| Sau chỉnh host sang `127.0.0.1` | Snapshot 0,0541 giây; search “xe điện”, K=5: 0,4541 giây. Mỗi số là một mẫu đơn lẻ, chưa benchmark |
| UI corpus demo ngày 10/10 | Sáu trang, tối/sáng, query/reader23matches/explain, lưu/bỏ lưu, lọc không dấu và restart Streamlit đã kiểm tra; bằng chứng nâng cấp ngày 11/10 ghi riêng |
| Thư viện corpus demo ngày 11/10 | Primary app, 200 bài, chỉ đọc: next từ trang 1/34 sang 2 bắt đầu #211; Giáo dục có 40 bài, reset 1/7. Sort nhiều từ có sáu giá trị đầu 1.867/1.249/1.220/1.186/1.022/993; A–Z bắt đầu “Cây cam”, “Mùng ba”. Chọn tất cả rồi lọc “xe dien” chỉ #18, 508 từ. Chỉ kết luận các tổ hợp đã thử |
| UI upload sandbox ngày 11/10 | TXT/PDF text ready; duplicate TXT/PDF không thêm ready; TXT rỗng/PDF hỏng/PDF trắng bị từ chối; corpus đổi làm stale và chặn search trước rebuild. Đây là fixture tổng hợp trong PostgreSQL riêng, không đổi corpus demo |
| UI rebuild/reader/export sandbox ngày 11/10 | Rebuild revision 3, 3 ready; query “xe điện” trả đúng 1/5 result #2 cosine 0,21878120990146813. Reader raw_text/metadata đúng; TXT download thành công. CSV tải thật và kiểm tra query/Top-K/score đầy đủ/version/revision đúng |
| UI navigation/lifecycle sandbox ngày 11/10 | Top-10 giữ query/kết quả khi chuyển trang; history replay gọi engine; explain token `xe_điện:[2]`, query weight 1 và contribution tổng bằng cosine. Ngắt/nối DB ẩn và phục hồi kết quả đúng; delete #2 làm stale, rebuild về 2 ready và query thành OOV. Sáng/tối đọc được ở 1280×720; cửa sổ hẹp chưa xác minh |
| UI sau restart sandbox ngày 11/10 | PostgreSQL/app restart giữ 2 ready, revision 4; reader thư viện PDF tổng hợp #3 raw_text đúng, “giáo dục” Top-20 trả #1 cosine 0,333333 bằng index đã lưu; query rỗng/`!!!` empty và clear history hoạt động. Container/volume thử cũ đã được dọn đúng qua `quit` |
| Sau restart Streamlit | Query “xe điện” giữ #18 cosine 0,704690; UI ghi 487,8 ms ở một lần, chỉ chẩn đoán đơn lẻ |
| Script tích hợp DB thật cuối 11/10 | `verify_tv3` chỉ đọc PASS trên 200 ready/revision 235: bốn query, cosine exhaustive agreement, raw_text, postings/contributions, service object reload và corpus hash không đổi |
| Precision@5/MRR@20 thật | Chưa có vì query/nhãn chưa được duyệt |
| Latency PostgreSQL thật 11/10 | `benchmark_tv3_latency` trên 25 query **draft**, Top-20, 1 warmup và 5 lần đo/query (125 mẫu): API mean **115,924 ms**, p95 **174,303 ms**; core nạp sẵn mean **4,584 ms**, p95 **5,513 ms**. Một client chạy tuần tự, không đo UI/metadata/content hay tải đồng thời; không có quality metric |

Lệnh nghiệm thu toàn bộ repository đã chạy (Python `.venv`, pytest 9.1.1):

```bat
.venv\Scripts\python.exe -X utf8 -m scripts.test_tv3_isolated_database --all-tests
```

Môi trường: Windows 11, Python 3.12.6, Streamlit 1.65.0, scikit-learn 1.9.1, SciPy 1.18.1, joblib 1.6.0. Lệnh runner cần quyền PostgreSQL `CREATEDB` và ghi thư mục tạm Windows; không dùng `pytest` toàn bộ trực tiếp trên DB demo.

Phép đo latency trên DB thật dùng lệnh `python -m scripts.benchmark_tv3_latency --source database --corpus vietonline_news_200 --rebuild --repeats 5 --warmups 1`. JSON/CSV ignored ở `reports/tv3_latency.*` có môi trường, manifest, hash query và từng mẫu. API là `RetrievalEngine.search_query` gồm tiền xử lý/snapshot/kiểm tra và nạp index/ranking; core dùng index/query đã chuẩn bị. Build **358,621 ms**, load **48,668 ms**, setup/warmup ghi riêng và không cộng vào mẫu query. 25/25 query vẫn draft; đo này không duyệt workload, không tính Precision/MRR và chưa thay thí nghiệm cuối có nhãn. Mốc đo này trên working tree trước commit cuối, nên `environment.git_commit` trong log vẫn là commit nền `c7ea489`.

Kiểm chứng DB thật có thể tái lập bằng lệnh sau; `--rebuild` chỉ tạo artifact local, không thêm/xóa tài liệu:

```bat
python -m scripts.verify_tv3 --rebuild --repeats 5
python -m scripts.test_tv3_isolated_database
```

Lệnh thứ hai cần quyền PostgreSQL `CREATEDB`, tự tạo DB `smartdoc_tv3_test_*` ngẫu nhiên và storage tạm, chỉ xóa chính DB thử do nó tạo. Báo cáo ignored tại `reports/tv3_integration.json` và `reports/tv3_database_tests.json`. `verify_tv3` chỉ kiểm tra object reload; restart tiến trình Streamlit demo được xác nhận riêng ngày 10/10. Restart PostgreSQL/app đã kiểm tra riêng trong sandbox ngày 11/10, không restart DB demo để thử. Timing của bốn query cố định (có empty/OOV) chỉ là chẩn đoán, không đại diện workload hay metric relevance.

Chỉ nghiệm thu cuối khi có bằng chứng lõi, đủ query có nhãn và số liệu thực nghiệm, hướng dẫn tái lập và tình trạng feed được ghi rõ. Báo cáo/slide tổng hợp cuối sẽ làm sau theo yêu cầu người dùng; phần triển khai không thể tự hoàn thành nhãn người thật.

[Slide nháp 12 trang](tv3_slides.pptx) trình bày phạm vi, kiến trúc, bằng chứng hiện có và các mục chờ. Đây là bản để nhóm chỉnh tiếp, chưa phải bản báo cáo cuối có metric relevance.

## Phần chưa được kết luận

Nhãn người thật, duyệt ≥20 query và P@5/MRR@20 chưa hoàn thành. Cửa sổ hẹp chưa được kiểm tra ở viewport thực. PDF trắng đã kiểm tra nhưng PDF scan thực tế chưa dùng trong phiên này. Cài venv/schema thử đã PASS, còn chuyển đúng gói corpus/storage sang máy bảo vệ cần bằng chứng riêng. Bộ 200 bài trên máy hiện thiếu file gốc được tham chiếu; reader/tải TXT dùng DB hoạt động, không coi đó là đã khôi phục download PDF nguồn. Yêu cầu “feed” chờ nhóm xác nhận với giảng viên. Báo cáo/slide cuối giữ lại làm sau theo yêu cầu người dùng.

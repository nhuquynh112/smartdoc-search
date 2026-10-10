# Nghiệm thu phần ứng dụng và đánh giá

Tài liệu này tách **chức năng đã có trong mã**, **test tự động**, **PostgreSQL thật** và **UI thủ công**. Có mã/checklist không đồng nghĩa đã nghiệm thu. Ngày chạy, output và ảnh cần được giữ cùng lần nghiệm thu; không dùng số liệu lịch sử làm kết quả mới.

## Đối chiếu nhiệm vụ

| Yêu cầu TV3 | Bàn giao | Điều kiện còn phải kiểm tra |
| --- | --- | --- |
| Query, Top-K, rank/title/score/nguồn/nội dung | `app/main.py`, `app/search_service.py` | DB thật PASS, UI query/reader đã quan sát; còn tổng duyệt đầy đủ |
| Upload và trạng thái index | Ingestion API + freshness + rebuild trong UI | Upload DB thử PASS, lifecycle fixture PASS; upload trên trình duyệt chưa thử |
| Minh họa thuật toán | Token, postings/ứng viên, trọng số/đóng góp | DB thật PASS, tổng contribution khớp cosine; đã xem bảng trên UI |
| Tập đánh giá | `evaluation/` và CLI chuẩn bị nhãn | ≥20 query được duyệt, nhãn người thật, giải quyết bất đồng |
| Precision@5, MRR, thời gian | `evaluation.py`, CLI đánh giá | Corpus cố định, kết quả từng query, môi trường và số lần đo |
| Hồ sơ/demo | Hướng dẫn, báo cáo TV3, demo, nguồn slide | Ghép TV1/TV2, số liệu thật, hoàn thiện slide và luyện bảo vệ |

## Test tự động không cần PostgreSQL

CMD tại root repo, sau khi kích hoạt `.venv`:

```bat
python -m pytest tests/test_tv3_catalog.py tests/test_tv3_search_service.py tests/test_tv3_app.py tests/test_tv3_evaluation.py tests/test_tv3_upload.py tests/test_tfidf_engine.py tests/test_inverted_index.py tests/test_search_engine.py tests/test_index_manager.py tests/test_retrieval_engine.py -q
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

Ô đã đánh dấu có bằng chứng quan sát trình duyệt ngày 10/10/2026. Các ô còn lại cần tổng duyệt; unit test không tự đánh dấu UI thủ công.

- [x] Chạy app từ root repo; đã mở sáu trang trên trình duyệt thật, ngày 10/10/2026.
- [x] Chuyển tối/sáng trên trình duyệt thật, ngày 10/10/2026.
- [ ] Kiểm tra kỹ tương phản và cửa sổ hẹp.
- [x] Query “Xe điện” hiển thị tài liệu #18 và score thật trên trình duyệt.
- [ ] Tổng duyệt Top-K 5/10/20, rank/thứ tự và nguồn trên nhiều query.
- [ ] Query rỗng/dấu câu nhận thông báo; OOV không có score giả.
- [ ] Ít hơn K điểm dương chỉ hiển thị kết quả thực.
- [x] Reader từ kết quả đọc được tiếng Việt; nhập “xe điện” thấy 23 vị trí tô sáng.
- [ ] Reader từ thư viện và tải TXT được kiểm tra thủ công.
- [x] Lưu tài liệu, Đã lưu hiển thị 1; bỏ lưu trở về rỗng trên trình duyệt thật.
- [x] Thư viện lọc không dấu “xe dien” ra tài liệu #18 trên trình duyệt thật.
- [ ] Tổng duyệt lịch sử, lọc chủ đề, sắp xếp và phân trang trên trình duyệt.
- [x] Giải thích trên trình duyệt có bảng contribution và posting `xe_điện:[18]`, khớp output engine.
- [x] Dừng rồi khởi động lại tiến trình Streamlit; trang chủ tải được, query “xe điện” vẫn #18 cosine 0,704690 và dùng index đã lưu.
- [ ] DB không kết nối trên môi trường thử: UI báo rõ và phục hồi khi kết nối lại.

## Ca thay đổi corpus — chỉ trên môi trường thử tách biệt

Dùng DB thử với `DATABASE_URL`, `STORAGE_ROOT` và index root riêng. Không reset volume hoặc đổi `.env` của corpus đánh giá. Ghi rõ fixture/tệp tổng hợp trong kết quả.

| Ca thử | Kết quả mong đợi | Trạng thái |
| --- | --- | --- |
| Upload TXT hợp lệ | Ready và đọc lại text | PASS trên DB thử, không phải upload qua trình duyệt |
| PDF có lớp chữ | Ready và đọc lại text | PASS PDF tạo bằng chương trình trên DB thử |
| Trùng SHA-256 | Duplicate; không thêm ready | PASS TXT/PDF trên DB thử |
| Quá 8 MiB/tên tệp/batch lỗi | Chặn biên đúng, tệp tạm được dọn | PASS ingestion stub |
| TXT rỗng, PDF trống/lỗi | Failed, không ready giả | PASS DB thử; PDF trống mô phỏng không có text, scan thật còn cần thử |
| Thêm/xóa ready và index stale | ID cũ ổn định; không phục vụ bộ lệch | Ingestion/delete PASS DB thử; stale PASS service fixture |
| Build lỗi/snapshot đổi | Không công bố bộ dở; thử lại được | PASS index/service fixture; lỗi đĩa thật không được gây ra |
| Corpus rỗng | Empty corpus | PASS fixture/AppTest |
| Restart và index persistence | Đọc metadata/text/index lại | Service object reload PASS; tiến trình Streamlit restart đã xác nhận; restart PostgreSQL còn chờ |

UI không bắt buộc có nút xóa; ca delete dùng API dữ liệu trong DB thử. Không xóa corpus thật để chỉ chứng minh stale.

## Nhật ký bằng chứng

| Loại | Kết quả ghi nhận trong hồ sơ này |
| --- | --- |
| Toàn bộ repository 10/10/2026 | **147 tests PASS, 20 subtests PASS trong 11,48 giây** qua runner `--all-tests` trên DB/storage tách biệt |
| Nhóm catalog/service/engine trước đó | 84 PASS trên fixture; là một phần được chạy lại trong toàn suite |
| UI AppTest 10/10/2026 | 14 PASS, service doubles; không ghi DB và không thay kiểm tra ảnh/theme thủ công |
| Evaluation unit test 10/10/2026 | 24 PASS với dữ liệu tổng hợp; chưa là metric corpus thật |
| Upload boundary test 10/10/2026 | 4 PASS với ingestion stub; giới hạn tệp, tên tệp tạm, lỗi/duplicate không ghi DB |
| PostgreSQL thử tách biệt | Nhóm DB riêng 5 PASS trong 4,34 giây; gồm ingestion/recovery và TXT/PDF upload. Toàn suite cũng đã chạy lại trên DB thử; demo trước/sau vẫn 200 ready, revision 235 |
| PostgreSQL 10/10/2026 | Container healthy; 200 ready, revision 235; raw_text tài liệu đầu đọc được 3.405 ký tự |
| Live ranking/explain 10/10/2026 | Query “Xe điện” có #18 hạng 1, cosine 0,7046896896391204; token `xe_điện`, tổng contribution khớp; query “trí tuệ nhân tạo” điểm đầu 0,10410627136419519; empty/OOV đúng trạng thái |
| Snapshot toàn thư viện trước chỉnh host | 200 tài liệu, revision 235; một lần đọc khoảng 5,076 giây, không phải benchmark retrieval |
| Kết nối Windows trước/sau chỉnh host | Một mẫu `localhost`: 5,0398 giây; một mẫu `127.0.0.1`: 0,0309 giây. Chỉ đổi host trong `.env` local |
| Sau chỉnh host sang `127.0.0.1` | Snapshot 0,0541 giây; search “xe điện”, K=5: 0,4541 giây. Mỗi số là một mẫu đơn lẻ, chưa benchmark |
| UI trình duyệt thật | Sáu trang, tối/sáng, query/reader23matches/explain, lưu/bỏ lưu, lọc không dấu và restart Streamlit đã kiểm tra; upload thực/download/responsive chưa thử |
| Sau restart Streamlit | Query “xe điện” giữ #18 cosine 0,704690; UI ghi 487,8 ms ở một lần, chỉ chẩn đoán đơn lẻ |
| Script tích hợp DB thật | `verify_tv3` PASS: bốn query, cosine exhaustive agreement, raw_text, postings/contributions, service object reload và corpus hash không đổi |
| Precision@5/MRR@20 thật | Chưa có vì query/nhãn chưa được duyệt |
| Latency retrieval thật | Chỉ ghi từ lần đo có môi trường/index/query/số lần lặp |

Lệnh nghiệm thu toàn bộ repository đã chạy (Python `.venv`, pytest 9.1.1):

```bat
.venv\Scripts\python.exe -X utf8 -m scripts.test_tv3_isolated_database --all-tests
```

Môi trường: Windows 11, Python 3.12.6, Streamlit 1.65.0, scikit-learn 1.9.1, SciPy 1.18.1, joblib 1.6.0. Lệnh runner cần quyền PostgreSQL `CREATEDB` và ghi thư mục tạm Windows; không dùng `pytest` toàn bộ trực tiếp trên DB demo.

Kiểm chứng DB thật có thể tái lập bằng lệnh sau; `--rebuild` chỉ tạo artifact local, không thêm/xóa tài liệu:

```bat
python -m scripts.verify_tv3 --rebuild --repeats 5
python -m scripts.test_tv3_isolated_database
```

Lệnh thứ hai cần quyền PostgreSQL `CREATEDB`, tự tạo DB `smartdoc_tv3_test_*` ngẫu nhiên và storage tạm, chỉ xóa chính DB thử do nó tạo. Báo cáo ignored tại `reports/tv3_integration.json` và `reports/tv3_database_tests.json`. `verify_tv3` chỉ kiểm tra object reload; restart tiến trình Streamlit được xác nhận riêng trên trình duyệt. Restart PostgreSQL chưa thử. Timing của bốn query cố định (có empty/OOV) chỉ là chẩn đoán, không đại diện workload hay metric relevance.

Chỉ nghiệm thu cuối khi có bằng chứng lõi, đủ query có nhãn, báo cáo/slide có số liệu thật và tình trạng feed được ghi rõ.

[Slide nháp 12 trang](tv3_slides.pptx) trình bày phạm vi, kiến trúc, bằng chứng hiện có và các mục chờ. Đây là bản để nhóm chỉnh tiếp, chưa phải bản báo cáo cuối có metric relevance.

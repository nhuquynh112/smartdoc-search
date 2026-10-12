# Sửa sau rà soát ngày 12/10/2026

## Thay đổi

- Artifact TF-IDF format 2 ghi SHA-256 cho vectorizer, ma trận và ID mapping; kiểm tra bytes trước khi deserialize. Validation từ chối NaN/Inf/âm, vector khác chuẩn L2, IDF không hợp lệ, vocabulary/config không khớp baseline. Format 1 vẫn được kiểm tra số học và đọc tương thích; rebuild tạo bản có checksum. Checksum phát hiện hỏng dữ liệu, không xác thực nguồn cung cấp joblib; chỉ dùng artifact local đáng tin cậy.
- Reader bỏ cache raw_text theo ID. Mỗi lần mở đọc lại từ DB, nên reprocess cùng ID không còn hiển thị text cũ. Kiểm tra ready/deleted và escape HTML vẫn giữ. Catalog/thống kê vẫn có TTL 600 giây và nút làm mới.
- Các test ingestion/recovery/upload có chốt kiểm tra tên DB tạm chính xác và marker runner trước khi truy cập DB. Chạy trực tiếp sẽ skip, marker trỏ nhầm DB sẽ fail; không tự đổi dữ liệu demo. Runner `scripts.test_tv3_isolated_database --all-tests` vẫn chạy đầy đủ các ca này.
- Cập nhật checklist TV1 theo bằng chứng đã có; đính chính tình trạng original theo máy/ngày thay vì dùng ghi chú cũ.
- Tạo snapshot và kit trắng mới trong `reports/`, giữ nguyên kit cũ. Trang review cho phép chọn đường dẫn thư mục mới; người thật vẫn phải đọc/duyệt/gán nhãn. Output local bị Git ignore, cần đóng gói riêng khi bàn giao.

## Tái lập

Xác minh sau sửa: **258 tests + 38 subtests PASS trong 34,78 giây** qua runner DB tách biệt. DB demo trước/sau giữ **201 ready, revision 250**; DB thử đã được dọn. So với lần audit 200/249, thư viện đã có thêm một tài liệu ngoài corpus news; không xóa hoặc ghi đè tài liệu đó. Corpus news dùng kit mới vẫn 200 tài liệu, revision lúc xuất là 250. `ReviewStore.load()` mở kit mới thành công, 25 query/500 nhãn trắng. Kit cũ không đổi.

`scripts.verify_tv3 --rebuild` PASS với 201 ready, revision 250: ranking đối chiếu exhaustive cosine, đọc text, postings/contributions và nạp lại index đúng. Chạy trực tiếp unittest ingestion/recovery skip trước khi kết nối DB. Đã restart Streamlit, quan sát trang tổng quan 201 tài liệu/revision 250 và search “Xe điện” trả #18 với score thật trên trình duyệt. Kiểm tra UI reader cuối không hoàn tất do công cụ approval review lỗi 429; regression reader cùng ID có text mới đã PASS bằng AppTest. Không coi lượt browser này là bằng chứng nghiệm thu reader thủ công mới.

```bash
python -m scripts.test_tv3_isolated_database --all-tests
python -m scripts.verify_tv3 --rebuild
python -m streamlit run app/review.py --server.address 127.0.0.1 --server.port 8503
```

Trong review, chọn `reports/tv3_labeling_2026_10_12` bằng đường dẫn tuyệt đối của checkout. Không upload/delete/reprocess DB đánh giá trong thời gian gán nhãn. Lệnh metric sau khi đủ nhãn được ghi trong `tv3_remaining.md`.

## Sửa lưu tài liệu theo phản hồi người dùng

Migration `004_saved_documents.sql` bổ sung bookmark PostgreSQL, khóa ngoại tự dọn bookmark khi tài liệu bị xóa. API chỉ lưu tài liệu ready, insert/delete idempotent và không tăng corpus revision. Không có tài khoản nên danh sách dùng chung workspace local. Đã áp dụng migration additive trên DB máy này, revision giữ 250.

Reader lưu `active_reader` để giữ dialog sau rerun, dọn state khi đóng/chuyển trang. Callback nút lưu chỉ ghi DB/state; thông báo được render ở body, không gọi toast từ fragment callback. Khi DB lỗi, UI giữ nội dung và không báo lưu thành công. AppTest kiểm tra mở session mới, lưu trong reader và lỗi DB; integration DB riêng kiểm tra ghi/đọc qua connection mới, idempotency, FK cascade và revision.

Lượt kiểm tra browser thật sau sửa bị approval review lỗi 429 chặn trước khi reload; không dùng cách khác để vượt chặn và không tuyên bố đã xác nhận reader bằng browser trong lượt này.

Toàn suite sau sửa bookmark: **264 tests + 38 subtests PASS trong 52,19 giây** qua runner isolated; demo trước/sau vẫn 201 ready, revision 250, DB thử đã dọn. Streamlit đã khởi động lại tại cổng 8501.

## Phần còn lại sau sửa bookmark

Các phát hiện dưới đây là trạng thái trước lượt sửa tối ưu kế tiếp; kết quả xử lý mới được ghi ở cuối tài liệu.

Rà thêm sau phản hồi tiếp theo của người dùng phát hiện một lỗi mới, chưa sửa: catalog dùng cache 600 giây nhưng danh sách bookmark đọc DB mới. Nếu tab/CLI khác thêm tài liệu và lưu nó, tab đang giữ catalog cũ có thể có ID trong `favorites` nhưng trang Đã lưu loại ID vì chưa có metadata trong catalog, rồi báo danh sách trống. AppTest với backend doubles tái hiện được: bookmark ID 20 tồn tại trong state, không có nút `fav_open_20`, hiện thông báo trống; hết cache hoặc làm mới catalog thì dữ liệu có thể xuất hiện. Không ghi DB demo trong phép thử. Hướng sửa: trang Đã lưu lấy metadata theo IDs hiện tại trực tiếp hoặc cache catalog theo corpus revision, không phụ thuộc snapshot display cũ.

Các rủi ro từ đọc mã, chưa stress test: trạng thái nút lưu trong dialog ở tab khác có thể cũ đến khi rerun toàn trang; PDF chưa có cap output/page/timeout và có thể giữ khóa corpus lâu; search/rebuild tuần tự qua khóa chung có thể chậm với nhiều phiên. Reader đếm tất cả vị trí trùng nhưng chỉ tô 300 vị trí đầu (`highlight_content`), nên cần ghi rõ giới hạn trên UI khi số trùng vượt 300. Không kết luận đã có hỏng dữ liệu hoặc treo production từ các rủi ro này.

Nhãn người thật/P@5/MRR@20, xác nhận yêu cầu “feed”, quyền chia sẻ dataset, nghiệm thu PDF scan/cửa sổ hẹp, chuyển gói sang máy khác và chốt branch/report/slide cần thực hiện theo kế hoạch. Lần sửa này chưa thêm hard timeout/worker cho PDF hoặc tối ưu snapshot/index đa phiên; đây là các rủi ro/hướng cải thiện đã ghi trong audit, chưa có bằng chứng làm demo 200 bài thất bại.

## Sửa cache và tối ưu theo phản hồi tải chậm

- Trang Đã lưu tra metadata trực tiếp theo bookmark/history IDs; không đọc full catalog hoặc bỏ mất ID do cache cũ. Catalog các trang còn lại khóa cache theo revision đọc mới từ DB. Regression ca ID mới được thêm/lưu ở phiên khác đã PASS.
- Reader đồng bộ bookmark ở mỗi lần mở/rerun fragment. Không tự push thay đổi vào tab chưa có tương tác. UI nói rõ giới hạn tô sáng 300 vị trí.
- SearchService tái sử dụng snapshot theo revision/pipeline fingerprint, nhưng luôn đọc live revision trước khi dùng. IndexManager tái sử dụng immutable index đã kiểm tra khi manifest và file signatures không đổi; file thay đổi/thiếu/hỏng vẫn bị từ chối, rebuild cùng revision nhưng khác version vẫn nạp lại. Kiểm tra trước/sau query, lỗi DB và ranking/explain được giữ.
- Giảm lặp tạo danh sách vocabulary trong search/explain; cache package-version lookups theo vòng đời tiến trình, vẫn tạo manifest/settings riêng mỗi lần. Sau cập nhật dependency cần restart app.
- Loader chặn >8 MB, >200 trang PDF, >2.000.000 ký tự text, dừng khi output cộng dồn vượt ngưỡng. Chưa có hard timeout/RAM sandbox cho mỗi trang PDF.

Đo chẩn đoán API trên máy local, query `xe điện`, K=5, bốn lượt trước/sau và median ba lượt đã làm nóng, cùng DB 201 ready/revision 250:

| Phạm vi | Trước (ms) | Sau (ms) |
| --- | ---: | ---: |
| Kiểm tra trạng thái chỉ mục | 170,35 | 24,92 |
| SearchService.search gồm metadata/freshness | 513,44 | 127,79 |

Các mẫu ở `reports/performance_before.json` và `reports/performance_after.json`, local/ignored. Đây là một query, một client, số mẫu nhỏ, chưa đo render/browser hoặc tải đồng thời; không suy ra tốc độ cho mọi truy vấn. Search warm khoảng 4 lần nhanh hơn trong phép đo này; cold load/warmup vẫn tốn thời gian.

Xác minh cuối: **278 tests + 38 subtests PASS trong 27,83 giây** qua DB/storage isolated; demo trước/sau 201 ready/revision 250, DB thử đã dọn. `scripts.verify_tv3` PASS ranking/exhaustive cosine, live text, postings/contributions và index reload. Không tạo relevance metrics hoặc nhãn người thật.

# Việc còn lại để nghiệm thu thành viên 3

Phần triển khai gồm UI, tích hợp engine, upload/rebuild, reader, giải thích và công cụ đánh giá. Điều kiện nghiệm thu vẫn cần **nhãn do người thật đọc nội dung**, metric thực nghiệm, tổng duyệt môi trường và quyết định của nhóm. Báo cáo/slide cuối được làm sau theo yêu cầu người dùng; các bản nháp hiện có chưa phải hồ sơ nộp cuối.

## 1. Hoàn tất bộ đánh giá có nhãn

1. Giữ cố định `reports/tv2_news_corpus.json` và môi trường tiền xử lý tương ứng với `evaluation/corpus_manifest.json`. Không upload/xóa/reprocess vào DB đánh giá trong lúc gán nhãn hoặc đo. Có thể chạy từ snapshot đã đóng băng để tránh phụ thuộc các thao tác demo.
2. Đọc 25 query nháp trong `evaluation/evaluation_queries.csv`, chốt nhu cầu thông tin cho rõ và giữ ít nhất 20 query có tài liệu relevant. ID/tiêu đề nguồn ý tưởng không tự là nhãn dương. Truy vấn không có relevant chỉ dùng kiểm thử hành vi riêng; không tìm thấy relevant trong pool chưa chứng minh toàn corpus không có relevant. Nếu sửa query, information need hoặc bỏ query, làm trên một bản CSV sao chép rồi tạo kit mới theo lệnh dưới; nội dung query đã bị ràng buộc hash nên không sửa trực tiếp hash/protocol để làm cho hợp lệ.
3. Người gán đọc nội dung cho từng cặp của pool Top-20 + seed (bộ nháp hiện có 500 dòng trống), không xem score/rank. Điền nhãn và tên người gán, thời gian, bằng chứng nội dung cho nhãn dương. Mỗi kết quả Top-20 thực trả khi đo phải có nhãn; dòng trống không tương đương 0. Xem [quy trình và tên trường](../evaluation/README.md).
4. Người duyệt rà soát query/nhãn, ghi quyết định sửa và phân xử khi cần. Chỉ đánh dấu protocol/query `approved` sau khi thật sự hoàn tất. Công cụ không tự thay người đọc quyết định relevance.
5. Chạy thực nghiệm, giữ JSON/CSV có provenance và các mẫu thời gian:

Để đọc và gán nhãn thuận tiện, mở một terminal khác trong repo:

```bat
python -m streamlit run app/review.py --server.address 127.0.0.1 --server.port 8503
```

Mở `http://127.0.0.1:8503`, chọn kit và điền tên thật. Dùng **Gán nhãn tài liệu** để đọc raw_text và lưu 0/1/bằng chứng; **Duyệt truy vấn** để ghi người soạn/duyệt; **Quy trình & kiểm tra** để duyệt quy trình và kiểm tra độ phủ. Công cụ không hiện cosine/thứ hạng và không tự quyết định nhãn. PostgreSQL phải đang chạy, còn khớp kit; những thay đổi được lưu vào CSV/JSON của kit tại máy này.

Khi bộ đã đủ nhãn và được duyệt, chạy:

```bat
python -m scripts.evaluate_retrieval --source snapshot --snapshot reports/tv2_news_corpus.json --rebuild --repeats 5
```

Lệnh sẽ từ chối khi kit còn draft, thiếu nhãn hoặc corpus/pipeline không khớp. Precision@5 luôn chia 5; MRR@20 dùng relevant đầu tiên trong 20 kết quả. Báo cáo pooled không chứng minh recall toàn corpus. `reports/tv3_evaluation.*` là đầu ra ignored; chỉ chia sẻ sau khi thống nhất dữ liệu được phép chia sẻ.

Nếu cần sửa bộ câu hỏi, ví dụ bản sao `reports/queries_reviewed.csv`:

```bat
python -m scripts.prepare_evaluation --snapshot reports/tv2_news_corpus.json --queries reports/queries_reviewed.csv --output evaluation_new --pool-top20
python -m scripts.evaluate_retrieval --source snapshot --snapshot reports/tv2_news_corpus.json --evaluation-dir evaluation_new --rebuild --repeats 5
```

Lệnh prepare tạo pool và **nhãn trống mới**, không suy ra nhãn và không tự chuyển nhãn cũ sang câu hỏi đã đổi. Chỉ chạy evaluate sau khi gán/duyệt kit mới. Giữ bản kit cũ làm dấu vết; tránh `--force` vì tùy chọn đó đặt lại toàn bộ nhãn.

Thời gian có runner riêng `scripts.benchmark_tv3_latency`, đã đo trên 25 query nháp với PostgreSQL thật ngày 11/10: 1 warmup + 5 lần/query, tổng 125 mẫu. Số đo/phạm vi ở [nghiệm thu](tv3_acceptance.md); đây là workload tạm, không tạo Precision/MRR. Khi đổi sang bộ query cuối, đo lại trên cùng bộ đã duyệt và giữ phạm vi API/core/build/load/warmup rõ ràng.

## 2. Phân tích lỗi từ kết quả thật

Sau khi có kết quả, sắp query theo P@5 tăng dần, rồi RR@20 tăng dần. Chọn 2–3 trường hợp để đọc lại query, kết quả và tài liệu relevant đã xác nhận. Với mỗi trường hợp, ghi ID được trả/ID bị bỏ sót, bằng chứng nội dung và nguyên nhân có thể kiểm chứng: OOV, tách từ, từ đồng nghĩa, query quá chung, thiếu từ khóa hoặc nhiễu trích xuất.

Nếu đề xuất sửa pipeline/ranking, tạo thí nghiệm mới trên cùng corpus/query/nhãn đã duyệt, chỉ đổi một yếu tố. Không dùng cosine để điều chỉnh nhãn nhằm tăng điểm. Thử so sánh tách khoảng trắng/tách từ chỉ sau khi baseline có nhãn và cấu hình được đóng băng.

## 3. Tổng duyệt kỹ thuật

- Chạy `python -m scripts.test_tv3_isolated_database --all-tests`: các test ghi/xóa chỉ chạy trong DB/storage thử riêng, không tăng revision demo.
- Chạy `python -m scripts.verify_tv3 --rebuild --repeats 5`: kiểm tra DB thật, index, ranking/explain và đọc text; timing này là chẩn đoán, không thay metric có nhãn.
- Thực hiện các ô còn trống trong [checklist nghiệm thu](tv3_acceptance.md), đặc biệt upload → stale → rebuild → query mới, duplicate/lỗi, tải TXT, Top-K và cửa sổ hẹp. Ghi rõ việc nào dùng fixture, DB thử và trình duyệt thật.
- Để thử upload/delete/disconnect/restart qua trình duyệt mà giữ demo nguyên vẹn, dùng `python -m scripts.tv3_browser_sandbox` và đúng URL `Isolated UI` được runner in ra (gồm đường dẫn ngẫu nhiên `tv3-qa-*`, không chỉ port 8504). Cần Docker và image `postgres:16` đã có. Runner dùng DB/storage/index riêng; terminal có `status`, `restart_app`, `restart_db`, `disconnect`, `reconnect`, `delete ID`, `quit`. Chi tiết và điều kiện quan sát nằm trong checklist, không lấy việc có runner làm bằng chứng mọi ca đã PASS.
- Trên môi trường mới, dùng Python 3.12, cài `requirements_tv3.txt`, chạy Docker và restore gói dump/manifest vào schema rỗng theo [hướng dẫn](database_transfer.md). Không init schema trước restore và không xóa volume hiện tại. Clone Git chỉ có code; muốn tải tệp nguồn phải nhận storage gốc riêng. Một lần test trên máy đã cấu hình không tự chứng minh cài từ đầu thành công.

Ngày 11/10 đã kiểm tra cài dependency từ venv mới (`pip check` PASS). Lần chạy cuối với toàn bộ fix/test đạt **236 tests + 38 subtests PASS trong 65,80 giây** trên DB/storage thử; demo giữ 200 ready/revision 235. `verify_tv3` chỉ đọc cũng PASS. Phần chuyển gói dump/storage sang máy khác và tổng duyệt đúng corpus bảo vệ vẫn cần giữ bằng chứng riêng; kiểm tra venv mới không tự bao gồm chuyển corpus.

Những thao tác thủ công chưa có kết luận trong lần cuối:

- Cửa sổ hẹp trên kích thước thật: công cụ yêu cầu 390px nhưng DOM vẫn 1280×720; không coi ảnh desktop là bằng chứng mobile.
- PDF scan thực tế: PDF trắng/hỏng đã được từ chối, nhưng lần này chưa thử một bản scan thật.

Upload/rebuild/search/reader/TXT và CSV download, Top-5/10/20, query rỗng/OOV, lịch sử, ngắt/nối DB, delete và restart đã có bằng chứng sandbox chi tiết trong checklist; các container/volume thử đã được dọn đúng. Thư viện cũng đã thử chỉ đọc trên 200 bài thật: chuyển trang, lọc Giáo dục 40 bài/reset page, sort nhiều từ/A–Z và lọc không dấu “xe dien” ra #18; chỉ kết luận các ca đã quan sát. Không cần thay corpus demo chỉ để lặp các ca thay đổi dữ liệu đó. Công cụ nhãn đã mở raw_text thật; quyết định gán nhãn đầu tiên phải do người dùng đọc và lưu, không tạo nhãn thử vào bộ thật.

## 4. Những việc cần nhóm quyết định

Xác nhận với giảng viên nghĩa của “feed” và ghi đúng trạng thái yêu cầu lưu trữ. Nhận báo cáo corpus/nguồn/schema từ thành viên 1 và ví dụ tính tay/đối chiếu thuật toán từ thành viên 2. Sau khi có metric và bằng chứng cuối, người dùng sẽ yêu cầu ghép báo cáo/slide; cả nhóm luyện demo và chuẩn bị backup dữ liệu/index phù hợp với corpus đã đóng băng.

Máy hiện đọc được text/metadata của 200 bài từ PostgreSQL nhưng thiếu các file gốc được tham chiếu. Tải TXT từ reader đã kiểm tra; nếu bảo vệ cần tải PDF nguồn, phải lấy `storage/originals` tương ứng từ nhóm và kiểm tra hash/reference theo hướng dẫn chuyển dữ liệu. Không mô tả việc này đã được sửa bằng UI.

Ưu tiên hiện tại là nhãn đúng, tái lập được, bằng chứng rõ và demo ổn định. OCR, chatbot, embedding, tài khoản hoặc tìm kiếm ngữ nghĩa chưa cần cho nghiệm thu TV3 theo phân công; chỉ cân nhắc khi có thời gian và cách đo lợi ích trên tập đánh giá thật.

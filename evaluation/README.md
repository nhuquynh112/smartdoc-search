# Bộ đánh giá TV3

Đây là **bộ nháp, chưa có kết quả thực nghiệm**. 25 truy vấn được soạn dựa trên tiêu đề thật trong `reports/tv2_news_corpus.json`: 200 tài liệu, ID 18–217, revision 235. Mỗi truy vấn ghi tiêu đề/ID gợi ý để truy nguồn ý tưởng; ID gợi ý **không phải nhãn liên quan**. Nhóm cần sửa và duyệt câu hỏi theo nhu cầu thông tin trước khi gán nhãn.

## Các tệp

| Tệp | Vai trò |
|---|---|
| `evaluation_queries.csv` | 25 câu hỏi nháp, nhu cầu thông tin, chủ đề, nguồn ý tưởng và người duyệt |
| `relevance_judgments.csv` | 500 cặp query–document trong pool Top-20 + seed, toàn bộ nhãn để trống |
| `corpus_manifest.json` | Danh sách corpus cố định, revision, fingerprint và hai hash |
| `protocol.json` | Quy ước đánh giá và xác nhận cách gán nhãn của nhóm; hiện `draft` |
| `judging_documents.csv` | Bản nội dung tiện đọc, tạo cục bộ; không cần đưa lên Git |

`corpus_identity_sha256` chỉ hash ID, tiêu đề, nguồn, dataset ID và chủ đề, độc lập với `clean_text`, revision và tiền xử lý. `retrieval_input_sha256` đóng băng chính xác ID, tiêu đề, nguồn, `clean_text`, revision và cấu hình tiền xử lý. Một số tệp gốc chưa có tại máy này nên không tuyên bố đã xác minh byte của toàn bộ tệp gốc. Nếu tệp gốc có khi chuẩn bị bộ, SHA-256 của chúng cũng được ghi và kiểm tra.

## Người thật cần làm

Chạy trang gán nhãn riêng, dùng DB đang chứa đúng corpus đã chốt:

```powershell
python -m streamlit run app/review.py --server.address 127.0.0.1 --server.port 8503
```

Trang này đọc nguyên văn qua API dữ liệu, hiển thị tài liệu theo ID và ẩn cosine/thứ hạng/seed. Người dùng tự ghi tên, nhãn và bằng chứng; lưu bằng nút rõ ràng. Có thể dùng CSV nếu cần. Không gán nhãn trong trang tìm kiếm có điểm/thứ hạng.

1. Duyệt nội dung `query`/`information_need`, điền `author`, `reviewed_by`, `reviewed_at` và đổi `review_status=approved`. Ngày giờ dùng ISO 8601 có múi giờ, ví dụ `2026-10-11T10:00:00+07:00`. Nếu muốn sửa nội dung hoặc bỏ câu hỏi, sửa **bản sao** CSV truy vấn rồi tạo bộ mới bằng `prepare_evaluation --queries ... --output evaluation_new --pool-top20`; bộ mới bắt đầu với nhãn trống và phải còn ít nhất 20 câu hỏi. Không sửa thủ công hash và không tái sử dụng nhãn cũ cho câu hỏi đã đổi nghĩa.
2. Mặc định `assessor_count=1`: một thành viên đọc nội dung từng tài liệu theo `information_need`, **không xem điểm cosine hoặc thứ hạng**. Điền `label_a`/`assessor_a`: `1` nếu nội dung trả lời thực chất nhu cầu; `0` nếu không. Người duyệt được ghi ở query/protocol. Pool được engine chọn trước để giới hạn lượng đọc nhưng **không chứa nhãn, score hoặc rank**; tài liệu gợi ý theo tiêu đề cũng không mặc nhiên là relevant. Không mặc định dòng trống là `0`; không chỉ dựa trên tiêu đề/từ trùng.
3. Điền `relevant` là nhãn cuối và `labeled_at`; ghi `evidence` ngắn từ nội dung cho nhãn dương (ghi chú nhãn âm tùy chọn). Nếu reviewer đổi nhãn, ghi `adjudicator` và `resolution`. Có thể chọn `assessor_count=2` trong protocol để hai người gán độc lập: khi đó cần thêm `label_b`/`assessor_b`, nhãn đồng ý phải khớp nhãn cuối, bất đồng phải được giải quyết và ghi lại.
4. Mỗi câu hỏi giữ lại phải có ít nhất một tài liệu đã được người đọc xác nhận liên quan. Nếu cả pool âm, **mở rộng đọc ngoài Top-20**, tìm độc lập và bổ sung nhãn; không loại query chỉ vì engine bỏ sót tài liệu liên quan. Query có relevant nằm ngoài danh sách trả về vẫn giữ trong bộ metric và nhận 0 nếu không có hit. Chỉ tách thành kiểm thử hành vi khi đã xác nhận không có relevant trong toàn corpus. Bộ mặc định `judgment_scope=pooled_top20`: mọi **kết quả Top-20 thực trả về** phải có nhãn trước tính metric; không coi tài liệu chưa gán là âm. Chỉ kết luận P@5/MRR@20 của bộ query/index hiện tại, **không tuyên bố recall hay đầy đủ relevance trên toàn corpus**. Có thể dùng `--exhaustive` để đánh giá toàn bộ cặp nếu nhóm cần.
5. Khi thực sự hoàn tất, trong `protocol.json` đổi `status` thành `approved`, đặt `independent_of_retrieval_scores=true`, điền người và thời gian duyệt. Giữ nguyên các hash. Công cụ chỉ kiểm tra tính đầy đủ và lời xác nhận; trách nhiệm chất lượng nhãn vẫn thuộc người gán và người duyệt.

## Chuẩn bị hoặc chạy lại

Chạy từ thư mục gốc repo; dùng Python trong môi trường đã cài `requirements_tv3.txt`.

```powershell
python -m scripts.prepare_evaluation --snapshot reports/tv2_news_corpus.json --output evaluation_new --pool-top20
python -m scripts.evaluate_retrieval --source snapshot --snapshot reports/tv2_news_corpus.json --rebuild --repeats 5
python -m scripts.evaluate_retrieval --source database --corpus vietonline_news_200 --rebuild --repeats 5
python -m unittest tests.test_tv3_evaluation -v
```

`prepare_evaluation` từ chối ghi đè bộ đã có; `--force` đặt lại **toàn bộ nhãn**. Mặc định tạo pool bằng IndexManager/RetrievalEngine thật trên export với index tạm, không thay DB hay index của UI. `--exhaustive` tạo mọi cặp; `--assessor-count 2` chọn hai người gán. Với corpus khác, truyền `--queries` tới CSV câu hỏi tự soạn và chọn thư mục đầu ra mới. Khi dùng thư mục mới để đánh giá, thêm `--evaluation-dir evaluation_new`. Không đổi corpus, pipeline hay nội dung trong thời gian gán nhãn và đo; bộ hiện tại sẽ từ chối snapshot/revision/fingerprint không khớp.

Đầu ra mặc định `reports/tv3_evaluation.json` và `.csv` được Git bỏ qua, gồm từng query và trung bình, `judgment_scope`, số tài liệu đã gán và giới hạn kết luận. **Precision@5 luôn chia 5**, kể cả chỉ trả một tài liệu. **MRR@20** dùng nghịch đảo vị trí tài liệu liên quan đầu tiên trong 20 kết quả; không có thì 0. Mỗi câu hỏi đóng góp một lần vào trung bình, độc lập số lần đo thời gian. `relevant_document_count` trong chế độ pooled chỉ là số relevant đã biết trong pool.

Chỉ mục được nạp trước và làm nóng; `index_load_ms`, `warmup_ms` và `rebuild_ms` được ghi riêng. Độ trễ API đo toàn bộ `RetrievalEngine.search_query` gồm tiền xử lý, snapshot và xác minh/nạp chỉ mục trên đĩa; chưa gồm render UI/lấy metadata/nội dung. `search_core` đo `search()` với chỉ mục và truy vấn đã chuẩn bị, loại thời gian tiền xử lý/snapshot/nạp chỉ mục. Chế độ snapshot đọc lại JSON ở mỗi lần gọi và **không đo PostgreSQL**; chế độ database dùng dịch vụ TV1 thật. Báo cáo ghi môi trường, cấu hình, hash đầu vào, số lần đo và từng mẫu thời gian.

Mỗi dòng nhãn có `query_semantic_sha256` gắn với đúng `query_id`, câu hỏi và nhu cầu thông tin. Công cụ từ chối nhãn khi câu hỏi đã đổi. Mỗi tài liệu cũng phải có `preprocessing_version` khớp fingerprint của export. Đường dẫn `--output` phải là `.json`, nằm ngoài thư mục bộ nhãn/chỉ mục và không trùng snapshot; CSV đi kèm có tên riêng.

JSON thực nghiệm có `failure_analysis` nhóm query không có relevant trong Top-20, relevant đầu tiên sau hạng 5, hoặc ít hơn 5 kết quả. Đây là gợi ý chọn ca phân tích, không tự suy diễn nguyên nhân thất bại. Đọc nhu cầu thông tin, nội dung và term overlap rồi viết nhận xét; lưu query khó và kết quả 0 trong trung bình.

Các fixture trong `tests/test_tv3_evaluation.py` là **dữ liệu tổng hợp để kiểm thử**, không phải minh chứng chất lượng truy xuất corpus thật. Khi bộ còn nháp/chưa đủ nhãn, công cụ báo `Evaluation refused` và không sinh điểm thực nghiệm.

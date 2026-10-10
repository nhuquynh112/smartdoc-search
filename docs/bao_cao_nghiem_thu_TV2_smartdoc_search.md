# Báo cáo nghiệm thu TV2 – SmartDoc Search
## Kiểm chứng TF-IDF, Cosine Similarity, Inverted Index và kiểm thử

**Phạm vi:** phần TV2 (lập chỉ mục và truy hồi tài liệu).  
**Căn cứ:** mã nguồn và test files được cung cấp gồm `tfidf_engine.py`, `search_engine.py`, `inverted_index.py`, `index_manager.py`, `retrieval_engine.py` và các test tương ứng; kết quả chạy `python -m pytest -q` do người thực hiện cung cấp ngày 10/10/2026.

> **Lưu ý về bằng chứng:** ví dụ tính tay bên dưới là bộ dữ liệu kiểm chứng nhỏ, tái tạo cấu hình TF-IDF của mã nguồn. Kết quả số được đối chiếu với `scikit-learn` bằng cùng cấu hình. Kết quả pytest là log thực tế người thực hiện cung cấp. Ba test liên quan PostgreSQL bị chặn do chưa cấu hình `DATABASE_URL`; không ghi nhận chúng là test pass.

---

## 1. Mục tiêu và phạm vi nghiệm thu

TV2 chịu trách nhiệm xây dựng và sử dụng chỉ mục phục vụ tìm kiếm văn bản. Các nội dung được kiểm chứng trong báo cáo:

1. Huấn luyện vector TF-IDF từ `clean_text` đã được TV1 tiền xử lý.
2. Chuẩn hóa vector và tính độ tương đồng cosine giữa truy vấn và tài liệu.
3. Dùng inverted index để lấy tập tài liệu ứng viên có chứa ít nhất một từ truy vấn.
4. Xếp hạng theo điểm số giảm dần, áp dụng `top_k` và quy tắc phá hòa theo `document_id` tăng dần.
5. Lưu/nạp artifact, quản lý phiên bản index và kiểm tra tính nhất quán.
6. Tổng hợp bằng chứng test hiện có và các giới hạn môi trường.

## 2. Thuật toán theo mã nguồn

### 2.1. TF-IDF

`smartdoc/tfidf_engine.py` sử dụng `sklearn.feature_extraction.text.TfidfVectorizer` với cấu hình:

```python
TfidfVectorizer(
    tokenizer=str.split,
    token_pattern=None,
    preprocessor=None,
    lowercase=False,
    norm="l2",
    use_idf=True,
    smooth_idf=True,
    sublinear_tf=False,
)
```

Điều này có nghĩa:

- Văn bản đầu vào là `clean_text` do TV1 cung cấp; TV2 không tiền xử lý lại văn bản tài liệu.
- Tách token bằng khoảng trắng (`str.split`), giữ nguyên chữ hoa/chữ thường (`lowercase=False`).
- Dùng IDF có smoothing (`smooth_idf=True`).
- Không dùng sublinear TF (`sublinear_tf=False`).
- Chuẩn hóa vector theo L2 (`norm="l2"`).

Với \(N\) tài liệu và \(df(t)\) là số tài liệu chứa từ \(t\), IDF có smoothing của cấu hình này là:

\[
idf(t)=\ln\left(\frac{1+N}{1+df(t)}\right)+1
\]

Trọng số TF-IDF thô tương ứng là:

\[
w(t,d)=tf(t,d)\times idf(t)
\]

Với `TfidfVectorizer` mặc định về TF, \(tf(t,d)\) là số lần xuất hiện của từ trong tài liệu. Sau đó vector được chuẩn hóa L2:

\[
\widehat{\mathbf{v}}_d =
\frac{\mathbf{v}_d}{\|\mathbf{v}_d\|_2}
\]

Do cấu hình `norm="l2"`, các vector tài liệu và vector truy vấn không rỗng được chuẩn hóa trước khi tính điểm.

### 2.2. Cosine Similarity

Cosine similarity đo mức tương đồng giữa vector truy vấn \(\widehat{\mathbf{q}}\) và vector tài liệu \(\widehat{\mathbf{d}}\):

\[
\operatorname{cos}(\mathbf{q},\mathbf{d}) =
\frac{\mathbf{q}\cdot\mathbf{d}}
{\|\mathbf{q}\|_2\|\mathbf{d}\|_2}
\]

Khi cả hai vector đã được chuẩn hóa L2, công thức rút gọn thành:

\[
\operatorname{cos}(\mathbf{q},\mathbf{d}) =
\widehat{\mathbf{q}}\cdot\widehat{\mathbf{d}}
\]

Trong `smartdoc/search_engine.py`, phép tính được triển khai bằng tích ma trận thưa:

```python
query_vector = engine.vectorizer.transform([normalized_query])
candidate_matrix = engine.matrix[candidate_rows]
scores = (candidate_matrix @ query_vector.T).toarray().ravel()
```

Các điểm số không dương bị loại bỏ. Kết quả được sắp xếp theo điểm giảm dần; nếu bằng điểm thì `document_id` tăng dần.

### 2.3. Inverted Index

`smartdoc/inverted_index.py` xây dựng ánh xạ:

`term -> tuple(document_id, ...)`

Một tài liệu xuất hiện trong posting list của từ nếu ô TF-IDF tương ứng khác 0. `get_candidates()` lấy hợp các posting list của các từ truy vấn, loại trùng và sắp xếp ID tăng dần.

`search()` chỉ tính cosine trên các tài liệu ứng viên thay vì toàn bộ corpus. Hàm `search_brute_force()` là cách tham chiếu tính điểm trên mọi tài liệu, được dùng trong test để đối chiếu tính đúng đắn của kết quả tìm kiếm tối ưu.

### 2.4. Quản lý và kiểm tra chỉ mục

Theo `smartdoc/index_manager.py`, quy trình xây dựng index:

1. Lấy snapshot corpus từ nguồn TV1.
2. Fit TF-IDF và tạo inverted index.
3. Ghi artifact vào thư mục staging.
4. Nạp lại artifact từ đĩa và kiểm tra tính hợp lệ.
5. Chuyển staging thành thư mục phiên bản bất biến.
6. Cập nhật `active_index.json` sau khi các bước trước thành công.

Các artifact TF-IDF gồm `vectorizer.joblib`, `tfidf_matrix.npz`, `ordered_document_ids.json` và `manifest.json`. Mã nguồn kiểm tra thứ tự ID, số hàng/cột, số lượng tài liệu và metadata phiên bản khi nạp lại.

---

## 3. Ví dụ tính tay TF-IDF và Cosine Similarity

### 3.1. Dữ liệu kiểm chứng

Sử dụng đúng kiểu văn bản đã tiền xử lý: các token được phân tách bằng khoảng trắng.

| Document ID | Nội dung `clean_text` |
|---:|---|
| 30 | `apple fresh sweet` |
| 10 | `banana fresh` |
| 20 | `apple rotten` |

Truy vấn: **`apple`**

Corpus có \(N=3\) tài liệu. Vocabulary theo thứ tự cột của vectorizer là:

`apple`, `banana`, `fresh`, `rotten`, `sweet`.

### 3.2. Tính IDF

Công thức:

\[
idf(t)=\ln\left(\frac{1+N}{1+df(t)}\right)+1
\]

| Từ | \(df(t)\) | Thay số | IDF (xấp xỉ) |
|---|---:|---|---:|
| `apple` | 2 | \(\ln(4/3)+1\) | 1.287682 |
| `banana` | 1 | \(\ln(4/2)+1\) | 1.693147 |
| `fresh` | 2 | \(\ln(4/3)+1\) | 1.287682 |
| `rotten` | 1 | \(\ln(4/2)+1\) | 1.693147 |
| `sweet` | 1 | \(\ln(4/2)+1\) | 1.693147 |

Ví dụ, `apple` xuất hiện trong 2/3 tài liệu, nên:

\[
idf(\text{apple})=\ln\left(\frac{1+3}{1+2}\right)+1
=\ln(4/3)+1\approx1.287682
\]

### 3.3. Vector TF-IDF và chuẩn hóa L2

Mỗi từ xuất hiện một lần trong tài liệu có chứa nó nên TF thô bằng 1. Trọng số thô là IDF của từ đó. Sau đó chuẩn hóa L2 trên từng vector tài liệu.

Với D30 (`apple fresh sweet`), vector trọng số thô theo vocabulary là:

\[
[1.287682,\;0,\;1.287682,\;0,\;1.693147]
\]

Độ dài L2:

\[
\|\mathbf{v}_{30}\|_2 =
\sqrt{1.287682^2+1.287682^2+1.693147^2}
\]

Xấp xỉ \(2.486\). Sau chuẩn hóa, vector của D30 xấp xỉ:

\[
[0.517856,\;0,\;0.517856,\;0,\;0.680919]
\]

Tương tự, các vector đã chuẩn hóa (số làm tròn 6 chữ số) là:

| Document ID | apple | banana | fresh | rotten | sweet |
|---:|---:|---:|---:|---:|---:|
| 30 | 0.517856 | 0 | 0.517856 | 0 | 0.680919 |
| 10 | 0 | 0.795961 | 0.605349 | 0 | 0 |
| 20 | 0.605349 | 0 | 0 | 0.795961 | 0 |

### 3.4. Vector truy vấn và cosine

Truy vấn `apple` chỉ chứa một từ trong vocabulary. Sau khi biến đổi và chuẩn hóa, vector truy vấn là:

\[
\widehat{\mathbf{q}}=[1,\;0,\;0,\;0,\;0]
\]

Do cả vector truy vấn và vector tài liệu đã được chuẩn hóa L2, cosine bằng tích vô hướng:

- D30: \(0.517856\times1 = 0.517856\)
- D10: \(0\times1 = 0\)
- D20: \(0.605349\times1 = 0.605349\)

D10 không có từ `apple`, nên điểm cosine bằng 0 và bị loại khỏi kết quả vì TV2 chỉ giữ điểm số lớn hơn 0.

### 3.5. Kết quả xếp hạng dự kiến

Với `top_k=3`, kết quả dự kiến theo đúng quy tắc trong `search_engine.py`:

| Rank | Document ID | Cosine score (xấp xỉ) | Lý do |
|---:|---:|---:|---|
| 1 | 20 | 0.605349 | Có `apple`; trọng số tương đối của từ này cao hơn trong tài liệu |
| 2 | 30 | 0.517856 | Có `apple`, nhưng vector còn chứa `fresh` và `sweet` |
| — | 10 | 0 | Không chứa `apple`; điểm không dương nên bị loại |

---

## 4. Đối chiếu với code TV2

Đoạn kiểm chứng dưới đây sử dụng cùng cấu hình `TfidfVectorizer` được khai báo trong `fit_tfidf()` và các test TV2. Chạy trong môi trường dự án có `scikit-learn`, `scipy` và `numpy`.

```python
from sklearn.feature_extraction.text import TfidfVectorizer

texts = [
    "apple fresh sweet",  # document_id 30
    "banana fresh",       # document_id 10
    "apple rotten",       # document_id 20
]
document_ids = [30, 10, 20]

vectorizer = TfidfVectorizer(
    tokenizer=str.split,
    token_pattern=None,
    preprocessor=None,
    lowercase=False,
    norm="l2",
    use_idf=True,
    smooth_idf=True,
    sublinear_tf=False,
)

matrix = vectorizer.fit_transform(texts).tocsr()
query_vector = vectorizer.transform(["apple"])
scores = (matrix @ query_vector.T).toarray().ravel()

results = [
    (document_ids[i], float(scores[i]))
    for i in range(len(document_ids))
    if scores[i] > 0.0
]
results.sort(key=lambda item: (-item[1], item[0]))

print("Vocabulary:", vectorizer.get_feature_names_out().tolist())
print("IDF:", vectorizer.idf_.tolist())
print("Scores by input row:", scores.tolist())
print("Ranked results:", results)
```

Kết quả mong đợi khi chạy với đúng phiên bản `scikit-learn` và cấu hình nêu trên:

- Vocabulary: `['apple', 'banana', 'fresh', 'rotten', 'sweet']`
- IDF xấp xỉ: `[1.287682, 1.693147, 1.287682, 1.693147, 1.693147]`
- Điểm theo thứ tự đầu vào (D30, D10, D20) xấp xỉ: `[0.517856, 0.0, 0.605349]`
- Xếp hạng: D20 trước D30; D10 bị loại do điểm bằng 0.

Đây là phép kiểm chứng trực tiếp bằng `TfidfVectorizer` với cùng cấu hình. Để tạo thêm bằng chứng tích hợp toàn luồng `IndexManager`/`search()`, có thể đưa chính corpus mẫu này vào test riêng và so sánh document ID, rank và score với kết quả tính tay.

---

## 5. Minh chứng kiểm thử từ bộ test TV2

Các test files được cung cấp có những kiểm tra sau:

| Thành phần | Bằng chứng trong test | Ý nghĩa |
|---|---|---|
| TF-IDF | `test_fit_10_documents_and_order_ids` | Fit corpus mẫu, kiểm tra số tài liệu và thứ tự ID |
| TF-IDF | `test_fit_does_not_preprocess_clean_text_again` | Xác nhận giữ nguyên token đã tiền xử lý như `trí_tuệ` |
| TF-IDF | `test_save_and_load_round_trip` | Kiểm tra artifact sau lưu/nạp không đổi |
| TF-IDF | `test_duplicate_ids_rejected`, `test_bad_clean_text_rejected` | Từ chối ID trùng hoặc `clean_text` không hợp lệ |
| Inverted index | `test_build_index_maps_terms_to_document_ids` | Kiểm tra posting list theo từ |
| Inverted index | `test_candidates_are_union_sorted_and_unique` | Hợp candidate, loại trùng và sắp xếp ID |
| Search engine | `test_search_returns_exact_contract_and_ranks_best_first` | Kiểm tra kết quả và xếp hạng |
| Search engine | `test_ties_are_broken_by_document_id_ascending` | Kiểm tra quy tắc phá hòa |
| Search engine | `test_candidate_search_matches_brute_force` | Đối chiếu kết quả tối ưu với cách tính brute force |
| Index manager | `test_build_activates_and_can_reload` | Kiểm tra xây dựng, kích hoạt và nạp lại index |
| Index manager | `test_failed_build_does_not_replace_previous_active_index` | Kiểm tra index đang hoạt động không bị thay khi build mới lỗi |
| Retrieval integration | `test_stale_revision_never_returns_old_results`, `test_stale_preprocessing_fingerprint_never_returns_old_results` | Chặn kết quả khi index không còn đồng bộ với snapshot |

### Kết quả pytest được cung cấp

Lệnh đã chạy:

```powershell
python -m pytest -q
```

Log tổng kết:

```text
3 failed, 73 passed, 9 subtests passed in 8.51s
```

Ba test lỗi đều dừng tại phần cấu hình database do thiếu `DATABASE_URL`:

1. `tests/test_ingestion_integration.py::IngestionIntegrationTests::test_ready_duplicate_failed_and_delete`
2. `tests/test_recovery.py::RecoveryTests::test_quarantine_preserves_files`
3. `tests/test_recovery.py::RecoveryTests::test_storage_failure_retry_keeps_id`

Thông báo lỗi:

```text
RuntimeError: Set DATABASE_URL in the local .env file.
```

**Diễn giải đúng kết quả:** 73 test pass và 9 subtests pass theo log. Ba test trên chưa xác minh được hành vi nghiệp vụ vì môi trường chưa có `DATABASE_URL` hợp lệ. Không nên ghi chúng là “pass”; nên ghi là **bị chặn bởi cấu hình PostgreSQL, cần chạy lại khi database được cấu hình**. Các lỗi này không phải bằng chứng rằng thuật toán TF-IDF/Cosine của TV2 sai, nhưng cũng không thể dùng tổng kết hiện tại để tuyên bố toàn bộ suite pass.

---

## 6. Tiêu chí nghiệm thu TV2

| Tiêu chí | Đánh giá theo bằng chứng hiện có |
|---|---|
| Cấu hình TF-IDF trong code xác định rõ | Đạt |
| Có ví dụ tính tay TF-IDF và cosine | Đạt trong báo cáo |
| Có phép đối chiếu số bằng cùng cấu hình `TfidfVectorizer` | Đạt ở mức ví dụ kiểm chứng; cần chạy snippet và lưu output nếu yêu cầu minh chứng thực thi |
| Có test so sánh tìm kiếm candidate với brute force | Có test; kết quả suite cho thấy phần lớn test pass, nhưng log không tách kết quả từng test |
| Có test cho inverted index và vòng đời index | Có trong bộ test đã cung cấp |
| Toàn bộ test suite pass | Chưa đạt/chưa xác nhận: 3 test bị chặn bởi thiếu cấu hình database |
| Xác minh end-to-end với PostgreSQL thật | Chưa thực hiện theo thông tin hiện có |

## 7. Kết luận

Mã nguồn TV2 thể hiện pipeline: **fit TF-IDF từ `clean_text` → lưu matrix thưa và metadata → xây inverted index → lấy candidate theo từ truy vấn → tính cosine similarity → lọc điểm không dương → sắp xếp và trả về top-k**. Các test được cung cấp có kiểm tra những hành vi cốt lõi như lưu/nạp artifact, posting list, xếp hạng, phá hòa và đối chiếu candidate search với brute force.

Dựa trên log hiện có, có thể báo cáo **73 test pass và 9 subtests pass; 3 test liên quan database chưa chạy thành công vì thiếu `DATABASE_URL`**. Vì vậy, báo cáo không tuyên bố toàn bộ suite đã pass. Để đóng nghiệm thu hoàn toàn, cần chạy lại ba test bị chặn sau khi cấu hình PostgreSQL; đồng thời lưu output thực tế của snippet kiểm chứng để làm minh chứng số đính kèm nếu giảng viên yêu cầu.

---

## Phụ lục A – Các lệnh có thể dùng khi trình bày nghiệm thu

Chạy test TF-IDF:

```powershell
python -m pytest -q tests/test_tfidf_engine.py
```

Chạy test inverted index:

```powershell
python -m pytest -q tests/test_inverted_index.py
```

Chạy test search engine:

```powershell
python -m pytest -q tests/test_search_engine.py
```

Chạy test quản lý index:

```powershell
python -m pytest -q tests/test_index_manager.py
```

Chạy test retrieval integration:

```powershell
python -m pytest -q tests/test_retrieval_engine.py
```

Chạy toàn bộ test suite:

```powershell
python -m pytest -q
```

*Lưu ý: tên đường dẫn test ở trên theo cấu trúc module trong dự án; nếu tên file thực tế khác, thay bằng đúng tên file trong thư mục `tests/`.*

"""Freeze an exported corpus and create a blank, auditable human labeling kit."""
from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from evaluation import (
    JUDGMENT_FIELDS, QUERY_FIELDS, MIN_QUERIES, MRR_DEPTH, EvaluationInputError,
    corpus_manifest, read_csv, write_csv,
)

ROOT = Path(__file__).resolve().parents[1]

# These are question drafts based on actual corpus titles, not judgments.
# Matching the title keeps seed provenance correct when database IDs change.
DRAFTS = (
    ("GrabCar Xe Điện", "Grab thử nghiệm dịch vụ xe điện như thế nào?", "Tìm bài mô tả thử nghiệm GrabCar dùng ô tô điện."),
    ("Gmail không thông báo", "Gmail trên Android không báo thư mới thì sửa thế nào?", "Tìm cách khắc phục thông báo email Gmail trên Android."),
    ("Google vá khẩn cấp", "Google sửa lỗ hổng bảo mật nguy hiểm trên Chrome", "Tìm thông tin về bản vá khẩn cấp lỗ hổng trên trình duyệt Chrome."),
    ("QR đa năng", "Giải pháp mã QR đa năng của ZaloPay", "Tìm bài giải thích mã QR đa năng và thanh toán của ZaloPay."),
    ("đẩy mạnh thương mại hóa 5G", "Việt Nam thúc đẩy thương mại hóa 5G và vệ tinh viễn thông", "Tìm chỉ đạo hoặc kế hoạch phát triển 5G và vệ tinh viễn thông tại Việt Nam."),
    ("Giáo viên nước ngoài tham gia", "Giáo viên nước ngoài giúp đưa tiếng Anh thành ngôn ngữ thứ hai", "Tìm điều kiện hoặc vai trò giáo viên nước ngoài trong đề xuất tiếng Anh là ngôn ngữ thứ hai."),
    ("đăng ký xét tuyển ĐH năm 2025", "Cách đăng ký xét tuyển đại học năm 2025 theo quy định mới", "Tìm hướng dẫn đăng ký xét tuyển đại học năm 2025."),
    ("quyết liệt nghiêm cấm giáo viên dạy thêm", "Bà Rịa Vũng Tàu cấm giáo viên dạy thêm", "Tìm thông tin về quy định hoặc việc cấm giáo viên dạy thêm ở Bà Rịa - Vũng Tàu."),
    ("Học phí 100 trường", "Học phí đại học năm 2025 chênh lệch ra sao?", "Tìm thống kê, so sánh học phí nhiều trường đại học năm 2025; loại học phí phổ thông."),
    ("điểm IELTS được quy đổi", "Điểm IELTS quy đổi khi xét tuyển đại học", "Tìm ngưỡng và quy tắc quy đổi chứng chỉ IELTS sang điểm xét tuyển đại học."),
    ("Sốt xuất huyết ngày càng", "Vì sao sốt xuất huyết ngày càng nguy hiểm?", "Tìm nguyên nhân hoặc cảnh báo mức độ nguy hiểm của bệnh sốt xuất huyết."),
    ("Hút thuốc lá thụ động", "Hút thuốc thụ động có làm trẻ dậy thì sớm?", "Tìm mối liên hệ giữa tiếp xúc khói thuốc thụ động và dậy thì sớm ở trẻ."),
    ("tác dụng của chạy bộ", "Chạy bộ có lợi gì cho sức khỏe và tinh thần?", "Tìm các lợi ích thể chất hoặc tinh thần của chạy bộ."),
    ("tiền ung thư đại trực tràng", "Dấu hiệu cảnh báo sớm ung thư đại trực tràng", "Tìm dấu hiệu tiền ung thư hoặc cảnh báo sớm ung thư đại trực tràng."),
    ("thiếu nữ 16 tuổi bị suy gan", "Suy gan sau khi dùng thuốc giảm cân mua trên mạng", "Tìm ca bệnh hoặc nguy cơ suy gan do thuốc giảm cân mua trực tuyến."),
    ("Trình Quốc hội giảm thuế VAT", "Đề xuất kéo dài giảm thuế VAT đến hết năm 2026", "Tìm đề xuất giảm thuế giá trị gia tăng tới cuối năm 2026 và tác động thu ngân sách."),
    ("3,5 km đường Vành đai 2", "Chi phí xây dựng đoạn Vành đai 2 tại TP HCM", "Tìm thông tin chi phí dự án hoặc đoạn đường Vành đai 2 TP.HCM; phân biệt Vành đai 3."),
    ("người trẻ cần tích cóp", "Người trẻ phải tiết kiệm bao lâu để mua nhà 3 đến 4 tỷ?", "Tìm tính toán thời gian tích lũy để mua nhà khoảng 3-4 tỷ đồng của người trẻ."),
    ("Giá xăng RON95 giảm mạnh", "Giá xăng RON95 giảm về khoảng 19000 đồng mỗi lít", "Tìm đợt điều chỉnh giảm giá xăng RON95 về mức 19.000 đồng/lít."),
    ("Gạo Ông Cua ở Hà Nội", "Phát hiện gạo nghi giả thương hiệu Gạo Ông Cua", "Tìm vụ phát hiện gạo nghi giả thương hiệu Gạo Ông Cua tại Hà Nội."),
    ("FPT Play chính thức sở hữu", "FPT Play có bản quyền Ngoại hạng Anh từ khi nào?", "Tìm thời điểm FPT Play bắt đầu sở hữu bản quyền Giải Ngoại hạng Anh."),
    ("Việt Nam vượt Indonesia 13 bậc", "Thứ hạng FIFA của tuyển Việt Nam so với Indonesia và Thái Lan", "Tìm bài so sánh thứ hạng FIFA giữa Việt Nam, Indonesia và Thái Lan."),
    ("U.23 Việt Nam hội quân", "U23 Việt Nam hội quân và thay đổi sau SEA Games", "Tìm thông tin đợt tập trung U23 Việt Nam và thay đổi nhân sự hoặc cách tập sau SEA Games."),
    ("cơ thủ Việt Nam bị liên đoàn", "Vì sao cơ thủ billiards Việt Nam bị cấm thi đấu quốc tế?", "Tìm lý do hoặc quy định dẫn đến lệnh cấm thi đấu của liên đoàn billiards thế giới."),
    ("Olympic 2024 hôm nay 8/8", "Bảng huy chương Olympic Paris ngày 8 tháng 8 năm 2024", "Tìm bảng tổng sắp huy chương Olympic 2024 cập nhật ngày 8/8; phân biệt các ngày khác."),
)


def draft_queries(snapshot):
    queries = []
    for number, (title_hint, text, need) in enumerate(DRAFTS, 1):
        matches = [row for row in snapshot["documents"] if title_hint.casefold() in row["title"].casefold()]
        if len(matches) != 1:
            raise EvaluationInputError(
                f"Expected one title matching {title_hint!r}; use --queries with this corpus's own query drafts."
            )
        doc = matches[0]
        queries.append({
            "query_id": f"Q{number:02d}", "query": text, "information_need": need,
            "category": doc.get("category", ""), "seed_document_ids": str(doc["document_id"]),
            "provenance": f"AI-assisted draft from corpus title: {doc['title']}; seed is provenance, not a relevance label.",
            "author": "", "review_status": "draft", "reviewed_by": "", "reviewed_at": "",
        })
    return queries


def top20_pool(snapshot, queries):
    """Select review candidates with the real engine, never infer relevance.

    Returned IDs are sorted to hide ranking/score from the judging CSV. The
    pool also includes independent title-based seed IDs without labeling them.
    """
    from smartdoc.index_manager import IndexManager
    from smartdoc.preprocessing import pipeline_manifest, preprocess_text
    from smartdoc.retrieval_engine import RetrievalEngine

    if pipeline_manifest()["fingerprint"] != snapshot["preprocessing"]["fingerprint"]:
        raise EvaluationInputError("Current preprocessing differs from the frozen export; cannot prepare a trustworthy Top-20 pool.")
    document_ids = {row["document_id"] for row in snapshot["documents"]}
    pools = {}
    with tempfile.TemporaryDirectory(prefix="smartdoc-pool-") as directory:
        loader = lambda _name=None: snapshot
        manager = IndexManager(directory, snapshot_loader=loader)
        manager.build_and_activate(snapshot.get("corpus_name"))
        engine = RetrievalEngine(manager, snapshot_loader=loader, preprocessing_fn=preprocess_text,
                                 corpus_name=snapshot.get("corpus_name"))
        for query in queries:
            response = engine.search_query(query["query"], 20)
            if response["status"] not in {"ok", "oov_query"}:
                raise EvaluationInputError(f"Pool search failed for {query['query_id']}: {response['status']}.")
            seeds = {int(value) for value in query.get("seed_document_ids", "").split(";") if value.strip()}
            if not seeds <= document_ids:
                raise EvaluationInputError(f"Unknown seed document ID for {query['query_id']}.")
            pools[query["query_id"]] = sorted(seeds | {row["document_id"] for row in response["results"]})
    return pools


def prepare(snapshot, output, *, storage_root=None, queries=None, source="", force=False,
            pool_top20=False, assessor_count=1):
    output = Path(output)
    filenames = ("corpus_manifest.json", "protocol.json", "evaluation_queries.csv",
                 "relevance_judgments.csv", "judging_documents.csv")
    existing = [name for name in filenames if (output / name).exists()]
    if existing and not force:
        raise EvaluationInputError(
            f"Existing labeling kit would be overwritten: {', '.join(existing)}. "
            "Use a new --output directory; --force explicitly resets ALL labels."
        )
    manifest = corpus_manifest(snapshot, storage_root=storage_root)
    queries = queries if queries is not None else draft_queries(snapshot)
    if not MIN_QUERIES <= len(queries) <= 30:
        raise EvaluationInputError("Prepare 20 to 30 query drafts.")
    qids = [row.get("query_id") for row in queries]
    if not all(qids) or len(qids) != len(set(qids)):
        raise EvaluationInputError("Query drafts need unique nonempty query_id values.")
    if assessor_count not in {1, 2}:
        raise EvaluationInputError("assessor_count must be 1 or 2.")
    pools = (top20_pool(snapshot, queries) if pool_top20 else
             {qid: sorted(row["document_id"] for row in snapshot["documents"]) for qid in qids})
    output.mkdir(parents=True, exist_ok=True)
    for row in queries:
        row["review_status"] = "draft"
        row["reviewed_by"] = ""
        row["reviewed_at"] = ""
    protocol = {
        "format_version": 1, "status": "draft", "labeling_method": "human_content_review",
        "independent_of_retrieval_scores": False,
        "minimum_queries": MIN_QUERIES, "mrr_depth": MRR_DEPTH,
        "precision_denominator": 5,
        "judgment_scope": "pooled_top20" if pool_top20 else "exhaustive",
        "assessor_count": assessor_count,
        "corpus_identity_sha256": manifest["corpus_identity_sha256"],
        "retrieval_input_sha256": manifest["retrieval_input_sha256"],
        "snapshot_source": str(source), "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
        "reviewed_by": "", "reviewed_at": "",
        "disagreement_policy": "Human assessor reads content without scores/ranks. Named query/protocol reviewer reviews decisions; record adjudicator and resolution for changed labels. With two assessors, resolve disagreements before final relevance.",
        "relevance_policy": "1 = document substantively answers information_need; 0 = does not. Title keywords alone are insufficient. Read full content; record brief evidence for positives (negative notes optional).",
        "judgment_coverage": (
            "Pool = actual Top-20 plus independent draft seed IDs, sorted by document ID with no scores/ranks. Every returned Top-20 must be judged before metrics. No recall/full-corpus relevance claim."
            if pool_top20 else "All query-document pairs."
        ),
        "pool_document_ids": pools if pool_top20 else None,
        "pool_provenance": "real RetrievalEngine/IndexManager on frozen export; retrieval selects candidates only, never relevance labels" if pool_top20 else None,
    }
    for name, payload in (("corpus_manifest.json", manifest), ("protocol.json", protocol)):
        (output / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(output / "evaluation_queries.csv", QUERY_FIELDS, queries)
    empty_judgments = ({**dict.fromkeys(JUDGMENT_FIELDS, ""), "query_id": qid,
                        "document_id": doc_id}
                       for qid in qids for doc_id in pools[qid])
    write_csv(output / "relevance_judgments.csv", JUDGMENT_FIELDS, empty_judgments)
    write_csv(output / "judging_documents.csv", ("document_id", "title", "source_uri", "category", "text_kind", "text"), (
        {"document_id": row["document_id"], "title": row["title"], "source_uri": row.get("source_uri"),
         "category": row.get("category"), "text_kind": "preprocessed_text_from_frozen_export",
         "text": row["clean_text"]} for row in snapshot["documents"]
    ))
    return manifest, sum(map(len, pools.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=ROOT / "reports/tv2_news_corpus.json")
    parser.add_argument("--storage-root", type=Path, default=ROOT / "storage")
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation")
    parser.add_argument("--queries", type=Path, help="Own query CSV for a different corpus; generated labels remain blank.")
    parser.add_argument("--force", action="store_true", help="Explicitly reset ALL existing labels in --output.")
    parser.add_argument("--pool-top20", action="store_true", default=True, help="Default: review Top-20 plus seed IDs; does not generate labels.")
    parser.add_argument("--exhaustive", dest="pool_top20", action="store_false", help="Review every query-document pair instead of a Top-20 pool.")
    parser.add_argument("--assessor-count", type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    try:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        manifest, pairs = prepare(snapshot, args.output, storage_root=args.storage_root,
                                  queries=read_csv(args.queries) if args.queries else None,
                                  source=args.snapshot, force=args.force, pool_top20=args.pool_top20,
                                  assessor_count=args.assessor_count)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Preparation refused: {exc}\n")
    print(f"Created draft labeling kit: {args.output}")
    print(f"Documents: {manifest['document_count']}; blank query-document pairs: {pairs}")
    print("No relevance judgments or experimental scores have been generated.")
    print(manifest["limitation"])


if __name__ == "__main__":
    main()

"""SYNTHETIC unit/integration fixtures; never evidence of real retrieval quality."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from evaluation import (
    EvaluationInputError, ValidatedJudgments, corpus_manifest, latency_summary, precision_at_5,
    reciprocal_rank_at_20, summarize_metrics, validate_evaluation_inputs,
    validate_frozen_corpus,
)
from scripts.evaluate_retrieval import benchmark, validate_response
from scripts.prepare_evaluation import prepare


class MetricTests(unittest.TestCase):
    def test_precision_always_divides_by_five(self):
        self.assertEqual(precision_at_5([], {7}), 0)
        self.assertEqual(precision_at_5([7], {7}), 0.2)
        self.assertEqual(precision_at_5([7, 8, 9], {7, 8, 9}), 0.6)
        self.assertEqual(precision_at_5([1, 2, 3, 4, 5, 7], {7}), 0)

    def test_reciprocal_rank_depth_is_twenty(self):
        self.assertEqual(reciprocal_rank_at_20([], {7}), 0)
        self.assertEqual(reciprocal_rank_at_20([8, 7, 9], {7, 9}), 0.5)
        self.assertEqual(reciprocal_rank_at_20(range(1, 22), {20}), 0.05)
        self.assertEqual(reciprocal_rank_at_20(range(1, 22), {21}), 0)

    def test_duplicate_ranked_ids_are_invalid(self):
        for metric in (precision_at_5, reciprocal_rank_at_20):
            with self.assertRaises(EvaluationInputError):
                metric([1, 1], {1})

    def test_macro_average_and_nearest_rank_latency(self):
        result = summarize_metrics([
            {"precision_at_5": 0.2, "reciprocal_rank_at_20": 1},
            {"precision_at_5": 0, "reciprocal_rank_at_20": 0.5},
        ])
        self.assertEqual(result, {"query_count": 2, "precision_at_5": 0.1, "mrr_at_20": 0.75})
        self.assertEqual(latency_summary([5, 1, 3, 2, 4])["p95_ms"], 5)
        self.assertEqual(latency_summary([5, 1, 3, 2, 4])["p50_ms"], 3)
        for samples in ([], [float("nan")], [-1]):
            with self.assertRaises(EvaluationInputError):
                latency_summary(samples)


class SyntheticAuditTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = {
            "corpus_name": "SYNTHETIC_UNIT_TEST_ONLY", "corpus_revision": 3,
            "preprocessing": {"fingerprint": "synthetic-fingerprint", "settings": {"synthetic": True}},
            "documents": [
                {"document_id": 1, "title": "Synthetic A", "clean_text": "alpha beta",
                 "source_uri": "synthetic://unit-test/a", "dataset_id": "test-a"},
                {"document_id": 7, "title": "Synthetic B", "clean_text": "beta gamma",
                 "source_uri": "synthetic://unit-test/b", "dataset_id": "test-b"},
            ],
        }
        self.manifest = corpus_manifest(self.snapshot)
        self.protocol = {
            "status": "approved", "labeling_method": "human_content_review",
            "independent_of_retrieval_scores": True, "minimum_queries": 20, "mrr_depth": 20,
            "precision_denominator": 5,
            "judgment_scope": "exhaustive", "assessor_count": 2,
            "corpus_identity_sha256": self.manifest["corpus_identity_sha256"],
            "retrieval_input_sha256": self.manifest["retrieval_input_sha256"],
            "reviewed_by": "Synthetic test reviewer (not real evidence)",
            "reviewed_at": "2026-10-10T00:00:00+00:00", "disagreement_policy": "Synthetic test policy",
        }
        self.queries = [{
            "query_id": f"Q{i:02d}", "query": f"alpha synthetic question {i}",
            "information_need": "SYNTHETIC ONLY", "provenance": "unittest generated synthetic fixture",
            "author": "Synthetic fixture author", "reviewed_by": "Synthetic fixture reviewer",
            "review_status": "approved", "reviewed_at": "2026-10-10T00:00:00+00:00",
            "seed_document_ids": "1",
        } for i in range(1, 21)]
        self.judgments = [{
            "query_id": query["query_id"], "document_id": str(doc_id),
            "label_a": "1" if doc_id == 1 else "0", "label_b": "1" if doc_id == 1 else "0",
            "relevant": "1" if doc_id == 1 else "0", "assessor_a": "Synthetic assessor A",
            "assessor_b": "Synthetic assessor B", "evidence": "SYNTHETIC TEST FIXTURE ONLY",
            "labeled_at": "2026-10-10T00:00:00+00:00", "adjudicator": "", "resolution": "",
        } for query in self.queries for doc_id in (1, 7)]

    def validate(self):
        return validate_evaluation_inputs(self.snapshot, self.manifest, self.protocol, self.queries, self.judgments)

    def test_complete_synthetic_collection_validates(self):
        labels = self.validate()
        self.assertEqual(len(labels), 20)
        self.assertEqual(labels["Q01"], {1})

    def test_clean_text_and_revision_do_not_change_identity_hash(self):
        changed = copy.deepcopy(self.snapshot)
        changed["documents"][0]["clean_text"] = "another tokenizer variant"
        changed["corpus_revision"] += 1
        changed["preprocessing"]["fingerprint"] = "variant"
        actual = corpus_manifest(changed)
        self.assertEqual(actual["corpus_identity_sha256"], self.manifest["corpus_identity_sha256"])
        self.assertNotEqual(actual["retrieval_input_sha256"], self.manifest["retrieval_input_sha256"])
        with self.assertRaises(EvaluationInputError):
            validate_frozen_corpus(changed, self.manifest)

    def test_snapshot_row_order_is_canonical(self):
        changed = copy.deepcopy(self.snapshot)
        changed["documents"].reverse()
        self.assertEqual(corpus_manifest(changed)["retrieval_input_sha256"], self.manifest["retrieval_input_sha256"])

    def test_modified_content_revision_fingerprint_or_manifest_fails(self):
        mutations = (
            lambda value: value["documents"][0].update(clean_text="tampered"),
            lambda value: value["documents"][0].update(title="tampered"),
            lambda value: value.update(corpus_revision=4),
            lambda value: value["preprocessing"].update(fingerprint="tampered"),
        )
        for mutate in mutations:
            changed = copy.deepcopy(self.snapshot)
            mutate(changed)
            with self.subTest(changed=changed), self.assertRaises(EvaluationInputError):
                validate_frozen_corpus(changed, self.manifest)
        self.manifest["documents"][0]["title"] = "tampered"
        with self.assertRaises(EvaluationInputError):
            self.validate()

    def test_draft_protocol_and_queries_fail(self):
        self.protocol["status"] = "draft"
        with self.assertRaisesRegex(EvaluationInputError, "draft"):
            self.validate()
        self.protocol["status"] = "approved"
        self.queries[0]["review_status"] = "draft"
        with self.assertRaisesRegex(EvaluationInputError, "draft"):
            self.validate()

    def test_less_than_twenty_queries_fail(self):
        self.queries.pop()
        with self.assertRaisesRegex(EvaluationInputError, "20"):
            self.validate()

    def test_declared_minimum_above_twenty_is_respected(self):
        self.protocol["minimum_queries"] = 21
        with self.assertRaisesRegex(EvaluationInputError, "21"):
            self.validate()
        query = {**self.queries[0], "query_id": "Q21", "query": "new synthetic query 21"}
        self.queries.append(query)
        self.judgments.extend([{**row, "query_id": "Q21"} for row in self.judgments[:2]])
        self.assertEqual(len(self.validate()), 21)

    def test_single_assessor_pool_is_valid_and_negative_notes_optional(self):
        self.protocol.update(assessor_count=1, judgment_scope="pooled_top20")
        self.judgments = [row for row in self.judgments if row["document_id"] == "1"]
        for row in self.judgments:
            row.update(label_b="", assessor_b="")
        labels = self.validate()
        self.assertEqual(labels.judgment_scope, "pooled_top20")
        self.assertEqual(labels.judged_document_ids["Q01"], {1})
        self.judgments.extend([{**row, "document_id": "7", "label_a": "0", "relevant": "0", "evidence": ""}
                               for row in self.judgments])
        self.assertEqual(self.validate().judged_document_ids["Q01"], {1, 7})

    def test_duplicate_query_text_cannot_inflate_query_count(self):
        self.queries[1]["query"] = self.queries[0]["query"].upper()
        with self.assertRaisesRegex(EvaluationInputError, "duplicate query text"):
            self.validate()

    def test_invalid_snapshot_structure_fails_cleanly(self):
        for snapshot in ([], {**self.snapshot, "preprocessing": []},
                         {**self.snapshot, "documents": ["bad"]}):
            with self.subTest(snapshot=snapshot), self.assertRaises(EvaluationInputError):
                corpus_manifest(snapshot)

    def test_missing_or_duplicate_judgment_fails(self):
        row = self.judgments.pop()
        with self.assertRaisesRegex(EvaluationInputError, "Incomplete judgments"):
            self.validate()
        self.judgments.extend([row, row])
        with self.assertRaisesRegex(EvaluationInputError, "duplicate judgment"):
            self.validate()

    def test_blank_label_or_unknown_document_fails(self):
        self.judgments[0]["label_a"] = ""
        with self.assertRaisesRegex(EvaluationInputError, "incomplete labels"):
            self.validate()
        self.judgments[0]["label_a"] = "1"
        self.judgments[0]["document_id"] = "999"
        with self.assertRaisesRegex(EvaluationInputError, "unknown query or document"):
            self.validate()

    def test_human_provenance_and_blinding_required(self):
        self.protocol["independent_of_retrieval_scores"] = False
        with self.assertRaisesRegex(EvaluationInputError, "without cosine"):
            self.validate()
        self.protocol["independent_of_retrieval_scores"] = True
        self.judgments[0]["assessor_a"] = "ChatGPT"
        with self.assertRaisesRegex(EvaluationInputError, "human assessor"):
            self.validate()
        self.judgments[0]["assessor_a"] = self.judgments[0]["assessor_b"]
        with self.assertRaisesRegex(EvaluationInputError, "independent"):
            self.validate()

    def test_disagreement_requires_recorded_resolution(self):
        self.judgments[0]["label_b"] = "0"
        with self.assertRaisesRegex(EvaluationInputError, "adjudicator"):
            self.validate()
        self.judgments[0].update(adjudicator="Synthetic adjudicator", resolution="Synthetic resolved reason")
        self.assertEqual(self.validate()["Q01"], {1})

    def test_zero_relevant_query_must_be_behavior_test(self):
        for row in self.judgments[:2]:
            row.update(label_a="0", label_b="0", relevant="0")
        with self.assertRaisesRegex(EvaluationInputError, "behavior tests"):
            self.validate()

    def test_seed_ids_and_review_timestamps_are_checked(self):
        self.queries[0]["seed_document_ids"] = "999"
        with self.assertRaisesRegex(EvaluationInputError, "unknown seed"):
            self.validate()
        self.queries[0]["seed_document_ids"] = "1"
        self.queries[0]["reviewed_at"] = "2026-10-10"
        with self.assertRaisesRegex(EvaluationInputError, "UTC offset"):
            self.validate()

    def test_original_hash_when_available_is_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "one.txt").write_text("SYNTHETIC raw fixture", encoding="utf-8")
            self.snapshot["documents"][0]["storage_ref"] = "one.txt"
            manifest = corpus_manifest(self.snapshot, storage_root=root)
            self.assertIn("original_sha256", manifest["documents"][0])
            (root / "one.txt").write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(EvaluationInputError, "Original file missing/changed"):
                validate_frozen_corpus(self.snapshot, manifest, storage_root=root)

    def test_prepare_never_fabricates_labels_and_preserves_existing_kit(self):
        with tempfile.TemporaryDirectory() as directory:
            prepare(self.snapshot, directory, queries=copy.deepcopy(self.queries), source="SYNTHETIC_ONLY")
            from evaluation import read_csv
            queries = read_csv(Path(directory) / "evaluation_queries.csv")
            judgments = read_csv(Path(directory) / "relevance_judgments.csv")
            protocol = json.loads((Path(directory) / "protocol.json").read_text(encoding="utf-8"))
            self.assertTrue(all(query["review_status"] == "draft" for query in queries))
            self.assertTrue(all(not row["label_a"] and not row["label_b"] and not row["relevant"] for row in judgments))
            self.assertEqual(len(judgments), 40)
            self.assertEqual(protocol["status"], "draft")
            with self.assertRaisesRegex(EvaluationInputError, "overwritten"):
                prepare(self.snapshot, directory, queries=copy.deepcopy(self.queries))


class RealEngineSyntheticSmokeTests(unittest.TestCase):
    def test_public_api_benchmark_uses_real_engine_on_synthetic_documents(self):
        from smartdoc.index_manager import IndexManager
        from smartdoc.retrieval_engine import RetrievalEngine
        snapshot = {
            "documents": [{"document_id": 7, "clean_text": "alpha beta"},
                          {"document_id": 12, "clean_text": "gamma delta"}],
            "corpus_revision": 1, "corpus_name": "SYNTHETIC_ENGINE_TEST_ONLY",
            "preprocessing": {"fingerprint": "SYNTHETIC"},
        }
        loader = lambda _name=None: snapshot
        with tempfile.TemporaryDirectory() as directory:
            manager = IndexManager(directory, snapshot_loader=loader)
            managed = manager.build_and_activate()
            engine = RetrievalEngine(manager, snapshot_loader=loader, preprocessing_fn=str.lower)
            result = benchmark(engine, managed, [{"query_id": "SYNTHETIC", "query": "ALPHA"}],
                               {"SYNTHETIC": {7}}, str.lower, repeats=2, warmups=1)
            self.assertEqual(result["summary"]["precision_at_5"], 0.2)
            self.assertEqual(result["summary"]["mrr_at_20"], 1)
            self.assertEqual(result["per_query"][0]["ranked_document_ids"], [7])
            self.assertEqual(result["latency"]["api"]["count"], 2)
            # A relevant seed does not permit treating other retrieved hits
            # as negative when their judgment is missing.
            pooled = ValidatedJudgments({"SYNTHETIC": {7}}, {"SYNTHETIC": {7}}, "pooled_top20")
            with self.assertRaisesRegex(EvaluationInputError, "unjudged document IDs"):
                benchmark(engine, managed, [{"query_id": "SYNTHETIC", "query": "alpha gamma"}],
                          pooled, str.lower, repeats=1, warmups=1)

    def test_failed_service_or_invalid_ranking_cannot_be_scored(self):
        with self.assertRaises(EvaluationInputError):
            validate_response({"status": "stale_index", "results": []}, {7})
        for rows in (
            [{"document_id": 7, "score": float("nan"), "rank": 1}],
            [{"document_id": 999, "score": 1, "rank": 1}],
            [{"document_id": 7, "score": 0, "rank": 1}],
            [{"document_id": 7, "score": 0.2, "rank": 1}, {"document_id": 12, "score": 0.3, "rank": 2}],
        ):
            with self.subTest(rows=rows), self.assertRaises(EvaluationInputError):
                validate_response({"status": "ok", "results": rows}, {7, 12})


if __name__ == "__main__":
    unittest.main()

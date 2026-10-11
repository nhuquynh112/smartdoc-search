"""Measure query latency on frozen inputs without requiring relevance labels."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from time import perf_counter

from evaluation import (
    MIN_QUERIES, MRR_DEPTH, EvaluationInputError, canonical_sha256,
    latency_summary, read_csv, validate_frozen_corpus, write_csv,
)
from scripts.evaluate_retrieval import environment_info, validate_report_output, validate_response

ROOT = Path(__file__).resolve().parents[1]


def validate_queries(queries):
    """A draft workload is valid for timing; it never becomes human approval."""
    if not isinstance(queries, list) or len(queries) < MIN_QUERIES:
        raise EvaluationInputError(f"Latency workload requires at least {MIN_QUERIES} distinct nonempty queries.")
    ids, texts = set(), set()
    for row in queries:
        if not isinstance(row, dict):
            raise EvaluationInputError("Each query must be a mapping.")
        qid, text = row.get("query_id"), row.get("query")
        if not isinstance(qid, str) or not qid.strip() or qid in ids:
            raise EvaluationInputError("Query IDs must be unique nonempty strings.")
        if not isinstance(text, str) or not text.strip():
            raise EvaluationInputError("Query text must be nonempty.")
        normalized = " ".join(text.casefold().split())
        if normalized in texts:
            raise EvaluationInputError("Latency workload contains duplicate query text.")
        ids.add(qid)
        texts.add(normalized)
    return queries


def benchmark_latency(engine, managed_index, queries, preprocessing_fn, *, repeats=5, warmups=1):
    """Time API and loaded core separately and compare every timed/warmup result."""
    from smartdoc.search_engine import create_search_engine, search

    validate_queries(queries)
    if (type(repeats) is not int or type(warmups) is not int
            or repeats < 1 or warmups < 1):
        raise EvaluationInputError("repeats and warmups must be integers >=1.")
    start = perf_counter()
    core = create_search_engine(managed_index.artifacts, managed_index.inverted_index)
    core_setup_ms = (perf_counter() - start) * 1000
    document_ids = set(managed_index.artifacts.ordered_document_ids)
    all_api, all_core, rows = [], [], []
    warmup_ms = 0.0
    for query in queries:
        start = perf_counter()
        processed = preprocessing_fn(query["query"])
        preprocessing_ms = (perf_counter() - start) * 1000
        if not isinstance(processed, str) or not processed.strip():
            raise EvaluationInputError(f"{query['query_id']}: query is empty after preprocessing; choose a useful timing workload.")
        expected = None
        api_samples, core_samples = [], []
        for iteration in range(warmups + repeats):
            warmup_start = perf_counter()
            start = perf_counter()
            response = engine.search_query(query["query"], MRR_DEPTH)
            api_ms = (perf_counter() - start) * 1000
            ranked_ids = validate_response(response, document_ids)
            if (response.get("index_version") != managed_index.version_id
                    or response.get("corpus_revision") != managed_index.artifacts.corpus_revision):
                raise EvaluationInputError("Index version/revision changed during latency benchmark.")
            start = perf_counter()
            loaded = search(core, processed, MRR_DEPTH)
            core_ms = (perf_counter() - start) * 1000
            if ([row["document_id"] for row in loaded] != ranked_ids
                    or any(not math.isclose(api["score"], item["score"], rel_tol=1e-10, abs_tol=1e-12)
                           for api, item in zip(response["results"], loaded))):
                raise EvaluationInputError(f"{query['query_id']}: API and loaded core disagree.")
            signature = [(row["document_id"], row["score"]) for row in response["results"]]
            if expected is not None and signature != expected:
                raise EvaluationInputError(f"{query['query_id']}: ranking/scores changed across repetitions.")
            expected = signature
            if iteration < warmups:
                warmup_ms += (perf_counter() - warmup_start) * 1000
            else:
                api_samples.append(api_ms)
                core_samples.append(core_ms)
        all_api.extend(api_samples)
        all_core.extend(core_samples)
        rows.append({
            "query_id": query["query_id"], "query": query["query"],
            "review_status": query.get("review_status", "unspecified") or "unspecified",
            "status": response["status"], "returned_count": len(ranked_ids),
            "preprocessing_for_core_ms": preprocessing_ms,
            "api_samples_ms": api_samples, "search_core_samples_ms": core_samples,
            "api_latency": latency_summary(api_samples), "search_core_latency": latency_summary(core_samples),
        })
    reviews = Counter(row["review_status"] for row in rows)
    return {
        "format_version": 1, "benchmark_type": "latency_only_no_relevance_metrics",
        "workload": {"query_count": len(queries), "top_k": MRR_DEPTH,
                     "review_status_counts": {"draft": reviews.pop("draft", 0),
                                               "approved": reviews.pop("approved", 0), **dict(reviews)},
                     "status_counts": dict(Counter(row["status"] for row in rows)),
                     "note": "Draft queries are a provisional timing workload. Timing neither approves queries nor establishes retrieval quality; final experiments require human review and relevance judgments."},
        "latency": {
            "api": latency_summary(all_api), "search_core": latency_summary(all_core),
            "core_setup_ms": core_setup_ms, "warmup_ms": warmup_ms,
            "repeats_per_query": repeats, "warmups_per_query": warmups,
            "percentile_method": "nearest rank",
            "aggregation": "Equal repetitions per query; pooled request samples. Queries run sequentially in CSV order; single client, no concurrent load.",
            "api_scope": "RetrievalEngine.search_query: preprocessing + freshness snapshot + load_active disk validation + ranking; excludes UI rendering, metadata and document content fetch",
            "search_core_scope": "search() on preloaded index and preprocessed query; excludes preprocessing, snapshot, load_active, UI, metadata and document content fetch",
            "warmup_scope": "API + loaded core calls and validation; excluded from measured request samples. Per-query preprocessing for core, core setup, index load and rebuild are recorded separately.",
        },
        "per_query": rows,
    }


def validate_index_root(index_root, *, protected_directories=(), protected_files=()):
    from smartdoc.index_manager import ACTIVE_MANIFEST_NAME

    root = Path(index_root).resolve()
    if root == ROOT.resolve() or any(root.is_relative_to(Path(value).resolve())
                                     or Path(value).resolve().is_relative_to(root)
                                     for value in protected_directories):
        raise EvaluationInputError("Latency index must use a separate directory outside corpus, source code and labeling inputs.")
    if any(Path(value).resolve().is_relative_to(root) for value in protected_files):
        raise EvaluationInputError("Latency index directory cannot contain an input file.")
    if (root / ACTIVE_MANIFEST_NAME).exists() and not (root / "latency_provenance.json").is_file():
        raise EvaluationInputError("This directory already contains a different index; select a separate latency index directory.")
    return root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("snapshot", "database"), default="snapshot")
    parser.add_argument("--snapshot", type=Path, default=ROOT / "reports/tv2_news_corpus.json")
    parser.add_argument("--corpus", help="Optional live database corpus selector.")
    parser.add_argument("--evaluation-dir", type=Path, default=ROOT / "evaluation")
    parser.add_argument("--storage-root", type=Path, default=ROOT / "storage")
    parser.add_argument("--index-root", type=Path, default=ROOT / "reports/tv3_latency_index")
    parser.add_argument("--rebuild", action="store_true", help="Build a separate latency index; never use the UI index.")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/tv3_latency.json")
    args = parser.parse_args()
    if args.repeats < 1 or args.warmups < 1:
        parser.error("--repeats and --warmups must be >=1.")
    try:
        protected_dirs = (args.evaluation_dir, args.storage_root, ROOT / "data", ROOT / "app",
                          ROOT / "smartdoc", ROOT / "scripts", ROOT / "tests")
        validate_report_output(args.output, protected_files=(args.snapshot,),
                               protected_directories=(*protected_dirs, args.index_root))
        validate_index_root(args.index_root, protected_directories=protected_dirs,
                            protected_files=(args.snapshot, args.output, args.output.with_suffix(".csv")))
        kit = args.evaluation_dir
        manifest = json.loads((kit / "corpus_manifest.json").read_text(encoding="utf-8"))
        queries = validate_queries(read_csv(kit / "evaluation_queries.csv"))
        if args.source == "snapshot":
            def loader(_corpus_name=None):
                return json.loads(args.snapshot.read_text(encoding="utf-8"))
        else:
            from smartdoc.ingestion import load_corpus_snapshot
            loader = load_corpus_snapshot
        snapshot = loader(args.corpus)
        validate_frozen_corpus(snapshot, manifest, storage_root=args.storage_root)
        from smartdoc.index_manager import IndexManager
        from smartdoc.preprocessing import PreprocessingConfig, pipeline_manifest, preprocess_text
        from smartdoc.retrieval_engine import RetrievalEngine

        settings = snapshot["preprocessing"]["settings"]
        config = PreprocessingConfig(segment_words=settings["segment_words"],
                                     remove_stopwords=settings["remove_stopwords"],
                                     stopwords=frozenset(settings["stopwords"]))
        if pipeline_manifest(config)["fingerprint"] != manifest["preprocessing_fingerprint"]:
            raise EvaluationInputError("Installed preprocessing differs from frozen inputs.")
        preprocess = lambda text: preprocess_text(text, config)
        manager = IndexManager(args.index_root, snapshot_loader=loader)
        provenance_path = args.index_root / "latency_provenance.json"
        rebuild_ms = None
        if args.rebuild:
            start = perf_counter()
            built = manager.build_and_activate(args.corpus)
            rebuild_ms = (perf_counter() - start) * 1000
            validate_frozen_corpus(loader(args.corpus), manifest, storage_root=args.storage_root)
            provenance_path.write_text(json.dumps({"index_version": built.version_id,
                                                  "retrieval_input_sha256": manifest["retrieval_input_sha256"]}) + "\n", encoding="utf-8")
        start = perf_counter()
        managed = manager.load_active()
        index_load_ms = (perf_counter() - start) * 1000
        if not provenance_path.is_file():
            raise EvaluationInputError("Latency index has no frozen-input provenance. Run with --rebuild.")
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        artifacts = managed.artifacts
        if (provenance.get("index_version") != managed.version_id
                or provenance.get("retrieval_input_sha256") != manifest["retrieval_input_sha256"]
                or artifacts.corpus_revision != snapshot["corpus_revision"]
                or artifacts.preprocessing_fingerprint != manifest["preprocessing_fingerprint"]
                or artifacts.corpus_name != snapshot.get("corpus_name")
                or set(artifacts.ordered_document_ids) != {row["document_id"] for row in snapshot["documents"]}):
            raise EvaluationInputError("Latency index differs from frozen inputs. Run with --rebuild.")
        engine = RetrievalEngine(manager, snapshot_loader=loader, preprocessing_fn=preprocess, corpus_name=args.corpus)
        result = benchmark_latency(engine, managed, queries, preprocess, repeats=args.repeats, warmups=args.warmups)
        validate_frozen_corpus(loader(args.corpus), manifest, storage_root=args.storage_root)
        # Also reject query/manifest edits during measurement before publishing.
        if (canonical_sha256(read_csv(kit / "evaluation_queries.csv")) != canonical_sha256(queries)
                or canonical_sha256(json.loads((kit / "corpus_manifest.json").read_text(encoding="utf-8"))) != canonical_sha256(manifest)):
            raise EvaluationInputError("Frozen workload inputs changed during measurement.")
        result.update({
            "measured_at_utc": datetime.now(timezone.utc).isoformat(), "source": args.source,
            "source_scope": ("Frozen JSON export reread per API request; excludes PostgreSQL/network latency."
                             if args.source == "snapshot" else "Live PostgreSQL snapshot through the public data service."),
            "corpus_manifest": manifest, "index_version": managed.version_id,
            "input_provenance": {"queries_sha256": canonical_sha256(queries), "manifest_sha256": canonical_sha256(manifest)},
            "environment": environment_info(), "index_load_ms": index_load_ms, "rebuild_ms": rebuild_ms,
            "tfidf_configuration": {key: artifacts.vectorizer.get_params().get(key) for key in (
                "norm", "use_idf", "smooth_idf", "sublinear_tf", "lowercase", "max_df", "min_df", "ngram_range")},
        })
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        fields = ("query_id", "query", "review_status", "status", "returned_count", "api_mean_ms", "api_p95_ms",
                  "search_core_mean_ms", "search_core_p95_ms", "api_samples_ms", "search_core_samples_ms")
        flat = []
        for row in result["per_query"]:
            flat.append({**{key: row.get(key) for key in fields},
                         "api_mean_ms": row["api_latency"]["mean_ms"], "api_p95_ms": row["api_latency"]["p95_ms"],
                         "search_core_mean_ms": row["search_core_latency"]["mean_ms"],
                         "search_core_p95_ms": row["search_core_latency"]["p95_ms"],
                         "api_samples_ms": json.dumps(row["api_samples_ms"]),
                         "search_core_samples_ms": json.dumps(row["search_core_samples_ms"])})
        write_csv(args.output.with_suffix(".csv"), fields, flat)
    except EvaluationInputError as exc:
        parser.exit(2, f"Latency benchmark refused: {exc}\n")
    except (OSError, ValueError, RuntimeError, ImportError, KeyError, TypeError) as exc:
        # Unexpected database/file exceptions must not print connection DSNs.
        parser.exit(2, f"Latency benchmark refused ({type(exc).__name__}). Check frozen inputs, paths and database connection.\n")
    print(f"Queries: {result['workload']['query_count']}; review status: {result['workload']['review_status_counts']}")
    print(f"API mean={result['latency']['api']['mean_ms']:.3f} ms; loaded core mean={result['latency']['search_core']['mean_ms']:.3f} ms")
    print("Timing only; no relevance metrics generated. Draft workloads remain provisional.")
    print(f"Reports: {args.output} and {args.output.with_suffix('.csv')}")


if __name__ == "__main__":
    main()

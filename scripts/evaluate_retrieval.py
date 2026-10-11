"""Run audited Precision@5 / MRR@20 through the actual TV2 retrieval service."""
from __future__ import annotations

import argparse
import csv
import hashlib
from io import StringIO
import json
import math
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from time import perf_counter

from evaluation import (
    EvaluationInputError, MRR_DEPTH, canonical_sha256, latency_summary,
    precision_at_5, reciprocal_rank_at_20, summarize_metrics,
    validate_evaluation_inputs, validate_frozen_corpus, write_csv,
)

ROOT = Path(__file__).resolve().parents[1]


def validate_report_output(path, *, protected_files=(), protected_directories=()):
    path = Path(path)
    if path.suffix.lower() != ".json":
        raise EvaluationInputError("--output must end in .json; the CSV companion uses a separate .csv path.")
    if path.resolve() == path.with_suffix(".csv").resolve():
        raise EvaluationInputError("JSON and CSV report paths must differ.")
    protected = {Path(value).resolve() for value in protected_files}
    directories = [Path(value).resolve() for value in protected_directories]
    for output in (path.resolve(), path.with_suffix(".csv").resolve()):
        if output in protected or any(output.is_relative_to(directory) for directory in directories):
            raise EvaluationInputError("Report output would overwrite evaluation inputs or index artifacts; choose a separate reports path.")
    return path


def validate_index_root(index_root, *, protected_directories=(), protected_files=()):
    """Only build in a separate empty directory or an evaluation-owned index."""
    from smartdoc.index_manager import ACTIVE_MANIFEST_NAME

    root = Path(index_root).resolve()
    directories = [Path(value).resolve() for value in protected_directories]
    if root == ROOT.resolve() or any(root.is_relative_to(value) or value.is_relative_to(root)
                                     for value in directories):
        raise EvaluationInputError("Evaluation index must use a separate directory outside corpus, source code and labeling inputs.")
    if any(Path(value).resolve().is_relative_to(root) for value in protected_files):
        raise EvaluationInputError("Evaluation index directory cannot contain an input or report file.")
    if (root / ACTIVE_MANIFEST_NAME).exists() and not (root / "evaluation_provenance.json").is_file():
        raise EvaluationInputError("This directory already contains a different index; select a separate evaluation index directory.")
    return root


def validate_response(response, doc_ids):
    if response.get("status") not in {"ok", "oov_query"}:
        raise EvaluationInputError(f"Retrieval did not succeed: {response.get('status')}: {response.get('message')}")
    rows = response.get("results")
    if not isinstance(rows, list) or len(rows) > MRR_DEPTH:
        raise EvaluationInputError("Retrieval response must contain at most 20 results.")
    ids = []
    previous = None
    for rank, row in enumerate(rows, 1):
        doc_id, score = row.get("document_id"), row.get("score")
        if isinstance(doc_id, bool) or doc_id not in doc_ids or doc_id in ids or row.get("rank") != rank:
            raise EvaluationInputError("Retrieval returned unknown/duplicate IDs or invalid ranks.")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or score <= 0:
            raise EvaluationInputError("Retrieval returned a nonpositive/nonfinite score.")
        key = (-score, doc_id)
        if previous is not None and key < previous:
            raise EvaluationInputError("Retrieval ranking is not score descending / ID ascending on ties.")
        previous = key
        ids.append(doc_id)
    if response["status"] == "oov_query" and rows:
        raise EvaluationInputError("OOV response cannot contain results.")
    return ids


def benchmark(engine, managed_index, queries, relevance, preprocessing_fn, *, repeats=5, warmups=1):
    """Use public API for relevance; time the already-loaded search core separately."""
    from smartdoc.search_engine import create_search_engine, search

    core = create_search_engine(managed_index.artifacts, managed_index.inverted_index)
    doc_ids = set(managed_index.artifacts.ordered_document_ids)
    all_api, all_core, per_query = [], [], []
    warmup_ms = 0.0
    judgment_scope = getattr(relevance, "judgment_scope", "exhaustive")
    judged_ids = getattr(relevance, "judged_document_ids", None)
    if judgment_scope == "pooled_top20" and judged_ids is None:
        raise EvaluationInputError("Pooled metrics require explicit human-judged document coverage.")
    for query in queries:
        qid, text = query["query_id"], query["query"]
        start = perf_counter()
        processed = preprocessing_fn(text)
        for _ in range(warmups):
            validate_response(engine.search_query(text, MRR_DEPTH), doc_ids)
            search(core, processed, MRR_DEPTH)
        warmup_ms += (perf_counter() - start) * 1000
        api_samples, core_samples = [], []
        expected_ids = None
        response = None
        for _ in range(repeats):
            start = perf_counter()
            response = engine.search_query(text, MRR_DEPTH)
            api_samples.append((perf_counter() - start) * 1000)
            ranked_ids = validate_response(response, doc_ids)
            if judged_ids is not None:
                missing = set(ranked_ids) - judged_ids[qid]
                if missing:
                    raise EvaluationInputError(
                        f"{qid}: returned Top-20 contains unjudged document IDs {sorted(missing)}. "
                        "Read and label these documents before metrics; unjudged is never nonrelevant."
                    )
            if response.get("index_version") != managed_index.version_id:
                raise EvaluationInputError("Active index changed during evaluation; rerun on a fixed corpus/index.")
            if expected_ids is not None and ranked_ids != expected_ids:
                raise EvaluationInputError(f"Nondeterministic ranking for {qid} across repetitions.")
            expected_ids = ranked_ids
            start = perf_counter()
            core_rows = search(core, processed, MRR_DEPTH)
            core_samples.append((perf_counter() - start) * 1000)
            if [row["document_id"] for row in core_rows] != ranked_ids:
                raise EvaluationInputError(f"Public API and loaded core disagree for {qid}.")
            if any(not math.isclose(api["score"], loaded["score"], rel_tol=1e-10, abs_tol=1e-12)
                   for api, loaded in zip(response["results"], core_rows)):
                raise EvaluationInputError(f"Public API and loaded core scores disagree for {qid}.")
        all_api.extend(api_samples)
        all_core.extend(core_samples)
        first = next((rank for rank, doc_id in enumerate(expected_ids, 1) if doc_id in relevance[qid]), None)
        per_query.append({
            "query_id": qid, "query": text, "status": response["status"],
            "information_need": query.get("information_need", ""), "category": query.get("category", ""),
            "relevant_document_count": len(relevance[qid]), "returned_count": len(expected_ids),
            "judgment_scope": judgment_scope,
            "judged_document_count": len(judged_ids[qid]) if judged_ids is not None else len(doc_ids),
            "ranked_document_ids": expected_ids,
            "ranked_results": [{"document_id": row["document_id"], "rank": row["rank"], "score": row["score"]}
                               for row in response["results"]],
            "relevant_document_ids": sorted(relevance[qid]), "first_relevant_rank_at_20": first,
            "precision_at_5": precision_at_5(expected_ids, relevance[qid]),
            "reciprocal_rank_at_20": reciprocal_rank_at_20(expected_ids, relevance[qid]),
            "api_latency": latency_summary(api_samples), "api_samples_ms": api_samples,
            "search_core_latency": latency_summary(core_samples), "search_core_samples_ms": core_samples,
        })
    return {
        "summary": summarize_metrics(per_query), "per_query": per_query,
        "failure_analysis": {
            "no_relevant_hit_at_20": [row["query_id"] for row in per_query if row["first_relevant_rank_at_20"] is None],
            "first_relevant_after_5": [row["query_id"] for row in per_query
                                       if row["first_relevant_rank_at_20"] is not None and row["first_relevant_rank_at_20"] > 5],
            "fewer_than_5_results": [row["query_id"] for row in per_query if row["returned_count"] < 5],
            "note": "Diagnostic groups, not inferred causes. A short list alone does not prove a retrieval defect. Inspect query needs, judged content and term overlap before explaining errors.",
        },
        "judgment_scope": judgment_scope,
        "coverage_note": ("All actual returned Top-20 IDs have human judgments. Relevance is known within the judged pool; no recall or full-corpus relevance completeness is claimed."
                          if judgment_scope == "pooled_top20" else "All query-document pairs were human judged."),
        "latency": {"api": latency_summary(all_api), "search_core": latency_summary(all_core),
                    "warmup_ms": warmup_ms, "repeats_per_query": repeats, "warmups_per_query": warmups,
                    "percentile_method": "nearest rank",
                    "api_scope": "RetrievalEngine.search_query: preprocessing + freshness snapshot + load_active disk validation + ranking; no UI rendering/metadata/content fetch",
                    "search_core_scope": "search() on preloaded index and preprocessed query; excludes preprocessing, snapshot, load_active, UI, metadata/content fetch"},
    }


def environment_info():
    packages = {}
    for package in ("numpy", "scipy", "scikit-learn", "underthesea", "underthesea_core", "psycopg"):
        try:
            packages[package] = version(package)
        except PackageNotFoundError:
            packages[package] = "unavailable"
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                                text=True, check=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        commit = None
    return {
        "python": sys.version, "platform": platform.platform(), "machine": platform.machine(),
        "processor": platform.processor(), "logical_cpus": os.cpu_count(), "packages": packages,
        "git_commit": commit,
        "thread_environment": {key: os.environ.get(key) for key in (
            "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
        )},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("snapshot", "database"), default="snapshot")
    parser.add_argument("--snapshot", type=Path, default=ROOT / "reports/tv2_news_corpus.json")
    parser.add_argument("--corpus", help="Database corpus selector, e.g. vietonline_news_200.")
    parser.add_argument("--evaluation-dir", type=Path, default=ROOT / "evaluation")
    parser.add_argument("--storage-root", type=Path, default=ROOT / "storage")
    parser.add_argument("--index-root", type=Path, default=ROOT / "reports/tv3_evaluation_index")
    parser.add_argument("--rebuild", action="store_true", help="Build the isolated evaluation index; measured separately.")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/tv3_evaluation.json")
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
    except EvaluationInputError as exc:
        parser.error(str(exc))
    try:
        kit = args.evaluation_dir
        # Parse exactly the bytes whose digest is retained for the final guard.
        input_bytes = {name: (kit / name).read_bytes() for name in (
            "corpus_manifest.json", "protocol.json", "evaluation_queries.csv", "relevance_judgments.csv")}
        input_file_sha256 = {name: hashlib.sha256(value).hexdigest() for name, value in input_bytes.items()}
        manifest = json.loads(input_bytes["corpus_manifest.json"])
        protocol = json.loads(input_bytes["protocol.json"])
        queries = list(csv.DictReader(StringIO(input_bytes["evaluation_queries.csv"].decode("utf-8-sig"), newline="")))
        judgments = list(csv.DictReader(StringIO(input_bytes["relevance_judgments.csv"].decode("utf-8-sig"), newline="")))
        if args.source == "snapshot":
            def loader(_corpus_name=None):
                return json.loads(args.snapshot.read_text(encoding="utf-8"))
        else:
            from smartdoc.ingestion import load_corpus_snapshot
            loader = load_corpus_snapshot
        snapshot = loader(args.corpus)
        relevance = validate_evaluation_inputs(snapshot, manifest, protocol, queries, judgments,
                                              storage_root=args.storage_root)
        # Index mutation occurs only after human labels and frozen inputs pass.
        from smartdoc.index_manager import IndexManager
        from smartdoc.preprocessing import PreprocessingConfig, pipeline_manifest, preprocess_text
        from smartdoc.retrieval_engine import RetrievalEngine

        settings = snapshot["preprocessing"]["settings"]
        config = PreprocessingConfig(segment_words=settings["segment_words"],
                                     remove_stopwords=settings["remove_stopwords"],
                                     stopwords=frozenset(settings["stopwords"]))
        if pipeline_manifest(config)["fingerprint"] != manifest["preprocessing_fingerprint"]:
            raise EvaluationInputError("Installed preprocessing differs from the frozen corpus; use the frozen environment or reprocess/review a new experiment.")
        preprocess = lambda text: preprocess_text(text, config)
        manager = IndexManager(args.index_root, snapshot_loader=loader)
        rebuild_ms = None
        provenance_path = args.index_root / "evaluation_provenance.json"
        if args.rebuild:
            start = perf_counter()
            built = manager.build_and_activate(args.corpus)
            rebuild_ms = (perf_counter() - start) * 1000
            validate_frozen_corpus(loader(args.corpus), manifest, storage_root=args.storage_root)
            provenance_path.write_text(json.dumps({
                "index_version": built.version_id,
                "retrieval_input_sha256": manifest["retrieval_input_sha256"],
            }) + "\n", encoding="utf-8")
        start = perf_counter()
        managed = manager.load_active()
        index_load_ms = (perf_counter() - start) * 1000
        if not provenance_path.is_file():
            raise EvaluationInputError("Evaluation index has no frozen-input provenance. Run with --rebuild.")
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        if (provenance.get("index_version") != managed.version_id
                or provenance.get("retrieval_input_sha256") != manifest["retrieval_input_sha256"]):
            raise EvaluationInputError("Evaluation index was built for different frozen inputs. Run with --rebuild.")
        artifacts = managed.artifacts
        if (artifacts.corpus_revision != snapshot["corpus_revision"]
                or artifacts.preprocessing_fingerprint != manifest["preprocessing_fingerprint"]
                or artifacts.corpus_name != snapshot.get("corpus_name")
                or set(artifacts.ordered_document_ids) != {row["document_id"] for row in snapshot["documents"]}):
            raise EvaluationInputError("Evaluation index differs from the frozen corpus. Run with --rebuild.")
        engine = RetrievalEngine(manager, snapshot_loader=loader, preprocessing_fn=preprocess,
                                 corpus_name=args.corpus)
        results = benchmark(engine, managed, queries, relevance, preprocess,
                            repeats=args.repeats, warmups=args.warmups)
        validate_frozen_corpus(loader(args.corpus), manifest, storage_root=args.storage_root)
        results.update({
            "format_version": 1, "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
            "evaluation_type": "human_labeled_real_corpus",
            "source": args.source,
            "source_scope": (
                "Frozen export; API rereads the JSON snapshot per request. No PostgreSQL/network latency measured."
                if args.source == "snapshot" else "Live PostgreSQL snapshot through TV1's public service."
            ),
            "corpus_manifest": manifest,
            "input_provenance": {"queries_sha256": canonical_sha256(queries),
                                 "judgments_sha256": canonical_sha256(judgments),
                                 "protocol_sha256": canonical_sha256(protocol),
                                 "file_sha256": input_file_sha256},
            "protocol": protocol, "environment": environment_info(), "index_version": managed.version_id,
            "tfidf_configuration": {key: artifacts.vectorizer.get_params().get(key) for key in (
                "norm", "use_idf", "smooth_idf", "sublinear_tf", "lowercase", "max_df", "min_df", "ngram_range",
            )},
            "index_load_ms": index_load_ms, "rebuild_ms": rebuild_ms,
            "metric_definitions": {"precision_at_5": "relevant retrieved in first 5 / 5, including short result lists",
                                   "mrr_at_20": "macro mean of 1 / first relevant rank within first 20; no hit = 0",
                                   "averaging": "one metric value per query, regardless of timing repetitions"},
        })
        for name, expected_digest in input_file_sha256.items():
            if hashlib.sha256((kit / name).read_bytes()).hexdigest() != expected_digest:
                raise EvaluationInputError(f"Frozen evaluation input changed during measurement: {name}. Rerun on an unchanged approved kit.")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        fields = ("query_id", "query", "status", "judgment_scope", "judged_document_count", "returned_count", "relevant_document_count",
                  "ranked_document_ids", "first_relevant_rank_at_20", "precision_at_5",
                  "reciprocal_rank_at_20", "api_mean_ms", "api_p95_ms", "search_core_mean_ms", "search_core_p95_ms")
        flat_rows = []
        for row in results["per_query"]:
            flat = {key: row.get(key) for key in fields}
            flat["ranked_document_ids"] = ";".join(map(str, row["ranked_document_ids"]))
            for prefix, source in (("api", "api_latency"), ("search_core", "search_core_latency")):
                flat[f"{prefix}_mean_ms"] = row[source]["mean_ms"]
                flat[f"{prefix}_p95_ms"] = row[source]["p95_ms"]
            flat_rows.append(flat)
        write_csv(args.output.with_suffix(".csv"), fields, flat_rows)
    except (OSError, ValueError, RuntimeError, ImportError, KeyError) as exc:
        parser.exit(2, f"Evaluation refused: {exc}\n")
    print(f"Queries: {results['summary']['query_count']}; P@5={results['summary']['precision_at_5']:.6f}; MRR@20={results['summary']['mrr_at_20']:.6f}")
    print(f"Reports: {args.output} and {args.output.with_suffix('.csv')}")


if __name__ == "__main__":
    main()

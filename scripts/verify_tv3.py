"""Read-only live PostgreSQL integration checks; optional local index rebuild.

This checks mechanics on real data. It does not measure Precision@5 or MRR:
those require the independently reviewed judgments in evaluation/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from app.search_service import DEFAULT_INDEX_ROOT, SearchService
from evaluation import corpus_manifest, latency_summary
from scripts.evaluate_retrieval import environment_info
from smartdoc.ingestion import get_document_text, load_corpus_snapshot
from smartdoc.inverted_index import get_candidates, get_postings
from smartdoc.preprocessing import preprocess_text
from smartdoc.search_engine import create_search_engine, search, search_brute_force

ROOT = Path(__file__).resolve().parents[1]
QUERIES = (
    ("electric_vehicle", "xe điện", "ok"),
    ("artificial_intelligence", "trí tuệ nhân tạo", "ok"),
    ("empty_query", "   ", "empty_query"),
    ("out_of_vocabulary", "zzqvtxsmartdocoov987654321", "oov_query"),
)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def timed(call):
    start = perf_counter()
    value = call()
    return value, (perf_counter() - start) * 1000


def check_results(response, expected_status, allowed_ids, top_k):
    require(response.get("status") == expected_status,
            f"Expected status {expected_status}; received {response.get('status')}.")
    rows = response.get("results")
    require(isinstance(rows, list) and len(rows) <= top_k, "Malformed result list/Top-K.")
    if expected_status == "ok":
        require(bool(rows), "The real-corpus example query returned no results.")
    else:
        require(not rows, "Empty/OOV query unexpectedly returned results.")
    seen, previous = set(), None
    for rank, row in enumerate(rows, 1):
        doc_id, score = row.get("document_id"), row.get("score")
        require(isinstance(doc_id, int) and not isinstance(doc_id, bool)
                and doc_id in allowed_ids and doc_id not in seen, "Unknown/duplicate result ID.")
        require(row.get("rank") == rank, "Ranks are not consecutive from one.")
        require(isinstance(score, (int, float)) and not isinstance(score, bool)
                and math.isfinite(score) and score > 0, "Score is not finite and positive.")
        require(bool(row.get("title")), "SearchService did not enrich title metadata.")
        key = (-score, doc_id)
        require(previous is None or key >= previous, "Ranking is not score descending / ID ascending for ties.")
        seen.add(doc_id)
        previous = key
    return rows


def compare_rankings(actual, reference, context):
    require([row["document_id"] for row in actual] == [row["document_id"] for row in reference],
            f"{context}: document order differs.")
    require(all(math.isclose(left["score"], right["score"], rel_tol=1e-10, abs_tol=1e-12)
                for left, right in zip(actual, reference)), f"{context}: scores differ.")


def compact_results(rows):
    return [{key: row.get(key) for key in ("document_id", "rank", "score", "title", "source_uri")}
            for row in rows]


def verify(args):
    service = SearchService(index_root=args.index_root, corpus_name=args.corpus)
    snapshot, snapshot_ms = timed(lambda: load_corpus_snapshot(args.corpus))
    frozen = corpus_manifest(snapshot)
    ids = {row["document_id"] for row in snapshot["documents"]}
    require(bool(ids), "No ready documents in the selected live corpus.")
    rebuild_ms = None
    if args.rebuild:
        rebuilt, rebuild_ms = timed(service.rebuild)
        require(rebuilt.get("rebuilt") is True and rebuilt.get("status") == "ok",
                f"Local index rebuild failed: {rebuilt.get('status')}.")
    state, status_ms = timed(service.status)
    require(state.get("status") == "ok",
            f"Search index is {state.get('status')}; rerun with --rebuild for a local index rebuild.")
    managed, index_load_ms = timed(service.index_manager.load_active)
    require(managed.version_id == state["index_version"], "Index changed during initialization.")
    require(managed.artifacts.corpus_revision == snapshot["corpus_revision"], "Index revision differs from live snapshot.")
    require(managed.artifacts.preprocessing_fingerprint == snapshot["preprocessing"]["fingerprint"],
            "Index preprocessing fingerprint differs from live snapshot.")
    require(set(managed.artifacts.ordered_document_ids) == ids, "Index IDs differ from live snapshot.")
    core = create_search_engine(managed.artifacts, managed.inverted_index)
    query_results, baselines = [], {}
    warmup_samples, api_samples, core_samples, snapshot_samples = [], [], [], []
    for query_id, text, expected in QUERIES:
        processed = preprocess_text(text)
        warm, warmup_ms = timed(lambda: service.search(text, args.top_k))
        warmup_samples.append(warmup_ms)
        rows = check_results(warm, expected, ids, args.top_k)
        baselines[query_id] = rows
        if expected == "ok":
            require(warm["index_version"] == managed.version_id, "Public service used another index version.")
        reference = search_brute_force(core, processed, args.top_k)
        compare_rankings(rows, reference, f"{query_id}: public API versus exhaustive cosine")
        indexed = search(core, processed, args.top_k)
        compare_rankings(rows, indexed, f"{query_id}: public API versus loaded inverted-index search")
        result = {
            "query_id": query_id, "query": text, "expected_status": expected,
            "status": warm["status"], "preprocessed_query": processed,
            "results": compact_results(rows), "exhaustive_cosine_matches": True,
            "indexed_core_matches": True, "warmup_ms": warmup_ms,
        }
        if rows:
            first = rows[0]
            raw, raw_read_ms = timed(lambda: get_document_text(first["document_id"]))
            require(isinstance(raw, str) and bool(raw.strip()), "First result raw text is unavailable from PostgreSQL.")
            explanation, explain_ms = timed(lambda: service.explain(text, first["document_id"], managed.version_id))
            require(explanation.get("status") == "ok", "Live result explanation failed.")
            postings = {term: list(get_postings(managed.inverted_index, term))
                        for term in dict.fromkeys(explanation["query_tokens"])}
            require(explanation["posting_lists"] == postings, "Explanation postings differ from actual active inverted index.")
            candidates = list(get_candidates(managed.inverted_index, explanation["query_tokens"]))
            require(explanation["candidate_ids"] == candidates, "Explanation candidates differ from the union of postings.")
            require(first["document_id"] in candidates, "First hit is absent from actual posting-list candidates.")
            terms = explanation["matched_terms"]
            require(bool(terms), "Positive score has no term contributions.")
            for term in terms:
                require(math.isclose(term["query_weight"] * term["document_weight"], term["contribution"],
                                     rel_tol=1e-10, abs_tol=1e-12), "Term contribution differs from q_t × d_t.")
            contribution_sum = sum(term["contribution"] for term in terms)
            require(math.isclose(contribution_sum, explanation["score"], rel_tol=1e-10, abs_tol=1e-12),
                    "Term contributions do not sum to explained cosine.")
            require(math.isclose(explanation["score"], first["score"], rel_tol=1e-10, abs_tol=1e-12),
                    "Explanation score differs from displayed search score.")
            result.update({
                "first_hit_text": {"document_id": first["document_id"], "characters": len(raw),
                                   "sha256_utf8": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                                   "read_ms": raw_read_ms},
                "explanation": {"score": explanation["score"], "contribution_sum": contribution_sum,
                                "matched_terms": terms, "posting_lists": postings, "candidate_ids": candidates,
                                "actual_postings_verified": True, "elapsed_ms": explain_ms},
            })
        if args.repeats:
            local_api, local_core, local_snapshot = [], [], []
            for _ in range(args.repeats):
                repeated, elapsed = timed(lambda: service.search(text, args.top_k))
                repeated_rows = check_results(repeated, expected, ids, args.top_k)
                compare_rankings(repeated_rows, rows, f"{query_id}: repeated public ranking")
                local_api.append(elapsed)
                core_rows, elapsed = timed(lambda: search(core, processed, args.top_k))
                compare_rankings(core_rows, rows, f"{query_id}: repeated loaded core")
                local_core.append(elapsed)
                sampled, elapsed = timed(lambda: load_corpus_snapshot(args.corpus))
                require(corpus_manifest(sampled)["retrieval_input_sha256"] == frozen["retrieval_input_sha256"],
                        "Live corpus changed during diagnostic repetitions.")
                local_snapshot.append(elapsed)
            api_samples.extend(local_api)
            core_samples.extend(local_core)
            snapshot_samples.extend(local_snapshot)
            result["diagnostic_latency"] = {
                "public_search_api_plus_metadata": latency_summary(local_api),
                "loaded_search_core": latency_summary(local_core),
                "snapshot_only": latency_summary(local_snapshot),
                "public_search_api_plus_metadata_samples_ms": local_api,
                "loaded_search_core_samples_ms": local_core, "snapshot_only_samples_ms": local_snapshot,
            }
        query_results.append(result)
    # A fresh service instance proves persisted artifacts can be loaded again.
    # This is an object restart, not a new OS process or PostgreSQL restart.
    restarted = SearchService(index_root=args.index_root, corpus_name=args.corpus)
    restarted_state = restarted.status()
    require(restarted_state.get("status") == "ok" and restarted_state["index_version"] == managed.version_id,
            "Fresh SearchService did not reload the same persisted index.")
    for query_id, text, expected in QUERIES:
        rows = check_results(restarted.search(text, args.top_k), expected, ids, args.top_k)
        compare_rankings(rows, baselines[query_id], f"{query_id}: fresh service reload")
    after = corpus_manifest(load_corpus_snapshot(args.corpus))
    require(after["retrieval_input_sha256"] == frozen["retrieval_input_sha256"], "Corpus changed during verification.")
    latency = {
        "initial_snapshot_ms": snapshot_ms, "initial_status_ms": status_ms, "index_load_ms": index_load_ms,
        "rebuild_ms": rebuild_ms, "warmup_total_ms": sum(warmup_samples),
        "warmups_per_query": 1, "repeats_per_query": args.repeats,
        "interpretation": "Diagnostic mechanics/timing only: four fixed queries include empty and OOV; this is not a labeled retrieval-quality experiment or representative load benchmark.",
        "public_api_scope": "SearchService.search including live freshness snapshots, preprocessing, index validation/loading and result metadata; excludes UI render and reader text fetch",
        "loaded_core_scope": "search() with loaded artifacts and preprocessed query; excludes PostgreSQL, preprocessing, index loading, metadata and UI",
        "snapshot_scope": "one direct TV1 load_corpus_snapshot database call per diagnostic sample; measured separately, not subtracted from API timing",
        "percentile_method": "nearest rank",
    }
    if args.repeats:
        latency.update(public_search_api_plus_metadata=latency_summary(api_samples),
                       loaded_search_core=latency_summary(core_samples), snapshot_only=latency_summary(snapshot_samples))
    return {
        "format_version": 1, "status": "passed", "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "verification_type": "live_read_only_postgresql_integration",
        "database_mutations": False, "local_index_rebuilt": args.rebuild,
        "corpus": {key: frozen[key] for key in ("corpus_name", "corpus_revision", "document_count",
                                                 "preprocessing_fingerprint", "corpus_identity_sha256", "retrieval_input_sha256")},
        "index_version": managed.version_id, "top_k": args.top_k, "queries": query_results,
        "restart": {"type": "fresh SearchService instance loading persisted artifacts", "same_rankings": True},
        "corpus_unchanged_after_checks": True, "latency": latency, "environment": environment_info(),
        "quality_metrics": "Not computed: independent human relevance labels are required.",
    }


def safe_error(exc):
    message = str(exc)
    connection = os.getenv("DATABASE_URL")
    if connection:
        message = message.replace(connection, "[redacted connection]")
    message = re.sub(r"(?i)postgres(?:ql)?://\S+", "[redacted connection]", message)
    message = re.sub(r"(?i)(password\s*[=:]\s*)[^\s,;]+", r"\1[redacted]", message)
    return f"{type(exc).__name__}: {message}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", help="Optional corpus selector; default uses all ready documents like the UI.")
    parser.add_argument("--index-root", type=Path, default=DEFAULT_INDEX_ROOT)
    parser.add_argument("--rebuild", action="store_true", help="Rebuild local index artifacts only; never modifies the database.")
    parser.add_argument("--top-k", type=int, choices=range(1, 21), default=5)
    parser.add_argument("--repeats", type=int, default=0, help="Diagnostic repetitions per fixed query; 0 skips repeats, 5 is useful.")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/tv3_integration.json")
    args = parser.parse_args()
    if args.repeats < 0:
        parser.error("--repeats must be nonnegative.")
    try:
        report = verify(args)
    except Exception as exc:
        error = safe_error(exc)
        failure = {"format_version": 1, "status": "failed", "checked_at_utc": datetime.now(timezone.utc).isoformat(),
                   "verification_type": "live_read_only_postgresql_integration", "database_mutations": False,
                   "error": error, "quality_metrics": "Not computed."}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(failure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        parser.exit(1, f"TV3 integration failed: {error}\nFailure report: {args.output}\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"TV3 integration PASS: {report['corpus']['document_count']} ready documents, revision {report['corpus']['corpus_revision']}, 4 fixed queries.")
    print("Verified real rankings against exhaustive cosine, live text, actual postings/contributions and persisted-index reload.")
    print(f"Report: {args.output}; no P@5/MRR was computed.")


if __name__ == "__main__":
    main()

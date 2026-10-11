"""Synthetic label-free timing fixtures; never real-corpus quality evidence."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from evaluation import EvaluationInputError, QUERY_FIELDS, corpus_manifest, write_csv
from scripts.benchmark_tv3_latency import benchmark_latency, main, validate_index_root, validate_queries


@pytest.fixture
def timing_queries():
    return [{"query_id": f"SYNTHETIC_{i}", "query": f"alpha synthetic request {i}",
             "review_status": "draft"} for i in range(20)]


@pytest.fixture
def engine_fixture(tmp_path):
    from smartdoc.index_manager import IndexManager
    from smartdoc.retrieval_engine import RetrievalEngine

    snapshot = {"corpus_name": "SYNTHETIC_LATENCY_ONLY", "corpus_revision": 1,
                "preprocessing": {"fingerprint": "synthetic"}, "documents": [
                    {"document_id": 7, "clean_text": "alpha beta"},
                    {"document_id": 12, "clean_text": "gamma delta"}]}
    loader = lambda _name=None: snapshot
    manager = IndexManager(tmp_path / "synthetic_index", snapshot_loader=loader)
    managed = manager.build_and_activate()
    engine = RetrievalEngine(manager, snapshot_loader=loader, preprocessing_fn=str.lower)
    return engine, managed, snapshot


def test_real_synthetic_engine_timings_need_no_labels_and_exclude_warmups(engine_fixture, timing_queries):
    engine, managed, _ = engine_fixture
    engine.search_query = Mock(wraps=engine.search_query)
    result = benchmark_latency(engine, managed, timing_queries, str.lower, repeats=2, warmups=1)
    assert result["benchmark_type"] == "latency_only_no_relevance_metrics"
    assert result["workload"]["query_count"] == 20
    assert result["workload"]["review_status_counts"] == {"draft": 20, "approved": 0}
    assert result["latency"]["api"]["count"] == 40
    assert result["latency"]["search_core"]["count"] == 40
    assert engine.search_query.call_count == 60
    assert result["latency"]["warmup_ms"] >= 0
    assert all(len(row["api_samples_ms"]) == 2 for row in result["per_query"])
    text = json.dumps(result)
    assert "precision_at_5" not in text and "mrr_at_20" not in text
    assert "relevant_document" not in text


def test_oov_is_explicitly_counted_without_relevance_inference(engine_fixture, timing_queries):
    engine, managed, _ = engine_fixture
    timing_queries[0]["query"] = "zzzzz_unseen"
    result = benchmark_latency(engine, managed, timing_queries, str.lower, repeats=1, warmups=1)
    assert result["workload"]["status_counts"] == {"oov_query": 1, "ok": 19}
    assert result["per_query"][0]["returned_count"] == 0


@pytest.mark.parametrize("mutation", [
    lambda rows: rows.pop(),
    lambda rows: rows[0].update(query="   "),
    lambda rows: rows[1].update(query=rows[0]["query"].upper() + "   "),
    lambda rows: rows[1].update(query_id=rows[0]["query_id"]),
])
def test_invalid_workload_is_rejected_before_any_search(timing_queries, mutation):
    mutation(timing_queries)
    with pytest.raises(EvaluationInputError):
        validate_queries(timing_queries)


@pytest.mark.parametrize("repeats,warmups", [(0, 1), (1, 0), (True, 1), (1, 1.5)])
def test_invalid_repetition_settings_are_rejected(engine_fixture, timing_queries, repeats, warmups):
    engine, managed, _ = engine_fixture
    with pytest.raises(EvaluationInputError, match="integers"):
        benchmark_latency(engine, managed, timing_queries, str.lower, repeats=repeats, warmups=warmups)


def test_version_change_and_api_core_score_disagreement_are_refused(engine_fixture, timing_queries, monkeypatch):
    import smartdoc.search_engine

    engine, managed, _ = engine_fixture
    real_api = engine.search_query
    engine.search_query = lambda *args: {**real_api(*args), "index_version": "changed"}
    with pytest.raises(EvaluationInputError, match="version/revision changed"):
        benchmark_latency(engine, managed, timing_queries, str.lower, repeats=1, warmups=1)
    engine.search_query = real_api
    real_core = smartdoc.search_engine.search

    def wrong_score(*args):
        rows = deepcopy(real_core(*args))
        rows[0]["score"] /= 2
        return rows

    monkeypatch.setattr(smartdoc.search_engine, "search", wrong_score)
    with pytest.raises(EvaluationInputError, match="disagree"):
        benchmark_latency(engine, managed, timing_queries, str.lower, repeats=1, warmups=1)


def test_protected_index_paths_are_rejected(tmp_path):
    protected = tmp_path / "kit"
    protected.mkdir()
    for path in (protected, protected / "nested", tmp_path):
        with pytest.raises(EvaluationInputError, match="separate directory"):
            validate_index_root(path, protected_directories=(protected,))


@pytest.fixture
def cli_inputs(tmp_path, timing_queries):
    from smartdoc.preprocessing import PreprocessingConfig, pipeline_manifest

    config = PreprocessingConfig(segment_words=False, remove_stopwords=False, stopwords=frozenset())
    preprocessing = pipeline_manifest(config)
    snapshot = {"corpus_name": "SYNTHETIC_CLI_ONLY", "corpus_revision": 3,
                "preprocessing": preprocessing, "documents": [
                    {"document_id": 7, "title": "Synthetic A", "clean_text": "alpha beta",
                     "source_uri": "synthetic://a", "dataset_id": "a", "preprocessing_version": preprocessing["fingerprint"]},
                    {"document_id": 12, "title": "Synthetic B", "clean_text": "gamma delta",
                     "source_uri": "synthetic://b", "dataset_id": "b", "preprocessing_version": preprocessing["fingerprint"]}]}
    kit = tmp_path / "kit"
    kit.mkdir()
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    (kit / "corpus_manifest.json").write_text(json.dumps(corpus_manifest(snapshot)), encoding="utf-8")
    write_csv(kit / "evaluation_queries.csv", QUERY_FIELDS, timing_queries)
    output = tmp_path / "latency.json"
    argv = ["benchmark_tv3_latency", "--snapshot", str(snapshot_path), "--evaluation-dir", str(kit),
            "--storage-root", str(tmp_path / "storage"), "--index-root", str(tmp_path / "index"),
            "--output", str(output), "--repeats", "1", "--warmups", "1", "--rebuild"]
    return argv, output, snapshot_path, kit


def test_cli_writes_separate_json_csv_with_draft_status_and_frozen_provenance(cli_inputs, monkeypatch, capsys):
    argv, output, _, _ = cli_inputs
    monkeypatch.setattr("sys.argv", argv)
    main()
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["source"] == "snapshot"
    assert result["workload"]["review_status_counts"]["draft"] == 20
    assert result["rebuild_ms"] >= 0 and result["index_load_ms"] >= 0
    assert result["input_provenance"]["queries_sha256"]
    assert output.with_suffix(".csv").exists()
    assert "no relevance metrics generated" in capsys.readouterr().out
    # A latency-owned persisted index remains reusable without rebuilding.
    monkeypatch.setattr("sys.argv", [arg for arg in argv if arg != "--rebuild"])
    main()
    repeated = json.loads(output.read_text(encoding="utf-8"))
    assert repeated["index_version"] == result["index_version"]
    assert repeated["rebuild_ms"] is None


def test_cli_refuses_real_existing_foreign_index_before_any_write(cli_inputs, engine_fixture, monkeypatch, capsys):
    from smartdoc.index_manager import ACTIVE_MANIFEST_NAME

    argv, output, _, _ = cli_inputs
    engine, managed, _ = engine_fixture
    foreign = engine.index_manager.index_root
    assert (foreign / ACTIVE_MANIFEST_NAME).is_file()
    before = {path.relative_to(foreign): path.read_bytes() for path in foreign.rglob("*") if path.is_file()}
    argv[argv.index("--index-root") + 1] = str(foreign)
    monkeypatch.setattr("sys.argv", argv)
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    assert "different index" in capsys.readouterr().err
    after = {path.relative_to(foreign): path.read_bytes() for path in foreign.rglob("*") if path.is_file()}
    assert after == before
    assert engine.index_manager.load_active().version_id == managed.version_id
    assert not output.exists() and not output.with_suffix(".csv").exists()


def test_cli_refuses_invalid_output_and_stale_frozen_corpus_without_reports(cli_inputs, monkeypatch):
    argv, output, snapshot_path, kit = cli_inputs
    bad_output = argv.copy()
    bad_output[bad_output.index("--output") + 1] = str(kit / "corpus_manifest.json")
    monkeypatch.setattr("sys.argv", bad_output)
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    snapshot = json.loads(snapshot_path.read_text())
    snapshot["documents"][0]["clean_text"] = "changed retrieval content"
    snapshot_path.write_text(json.dumps(snapshot))
    monkeypatch.setattr("sys.argv", argv)
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    assert not output.exists() and not output.with_suffix(".csv").exists()


def test_cli_refuses_corpus_change_during_measurement_before_writing(cli_inputs, monkeypatch):
    import scripts.benchmark_tv3_latency as module

    argv, output, snapshot_path, _ = cli_inputs
    real_benchmark = module.benchmark_latency

    def change_after_measurement(*args, **kwargs):
        result = real_benchmark(*args, **kwargs)
        snapshot = json.loads(snapshot_path.read_text())
        snapshot["corpus_revision"] += 1
        snapshot_path.write_text(json.dumps(snapshot))
        return result

    monkeypatch.setattr(module, "benchmark_latency", change_after_measurement)
    monkeypatch.setattr("sys.argv", argv)
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    assert not output.exists() and not output.with_suffix(".csv").exists()

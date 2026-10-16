"""Tests for TV2 index lifecycle management."""
import json

import pytest

from smartdoc.index_manager import (
    IndexBuildError,
    IndexManager,
    NoActiveIndexError,
    SnapshotLoadError,
)


def snapshot(revision=7, fingerprint="prep-v1", corpus_name="news", documents=None):
    return {
        "documents": documents if documents is not None else [
            {"document_id": 3, "clean_text": "trí_tuệ nhân_tạo"},
            {"document_id": 1, "clean_text": "kinh_tế thị_trường"},
            {"document_id": 2, "clean_text": "trí_tuệ kinh_tế"},
        ],
        "corpus_revision": revision,
        "corpus_name": corpus_name,
        "preprocessing": {"fingerprint": fingerprint, "settings": {}},
    }


def test_build_activates_and_can_reload(tmp_path):
    manager = IndexManager(tmp_path, snapshot_loader=lambda name: snapshot())
    built = manager.build_and_activate("news")
    loaded = manager.load_active()

    assert loaded.version_id == built.version_id
    assert loaded.artifacts.corpus_revision == 7
    assert loaded.artifacts.preprocessing_fingerprint == "prep-v1"
    assert loaded.artifacts.ordered_document_ids == (1, 2, 3)
    assert manager.is_active_for(
        corpus_revision=7,
        preprocessing_fingerprint="prep-v1",
        corpus_name="news",
    )


def test_no_active_index_raises(tmp_path):
    manager = IndexManager(tmp_path, snapshot_loader=lambda name: snapshot())
    with pytest.raises(NoActiveIndexError):
        manager.load_active()


def test_failed_build_does_not_replace_previous_active_index(tmp_path):
    current = {"value": snapshot()}
    manager = IndexManager(tmp_path, snapshot_loader=lambda name: current["value"])
    first = manager.build_and_activate("news")
    old_manifest = json.loads(manager.active_manifest_path.read_text(encoding="utf-8"))

    current["value"] = {
        "documents": [{"document_id": 1, "clean_text": None}],
        "corpus_revision": 8,
        "corpus_name": "news",
        "preprocessing": {"fingerprint": "prep-v1"},
    }
    with pytest.raises(IndexBuildError):
        manager.build_and_activate("news")

    new_manifest = json.loads(manager.active_manifest_path.read_text(encoding="utf-8"))
    assert new_manifest == old_manifest
    assert manager.load_active().version_id == first.version_id


def test_changed_revision_or_fingerprint_is_not_current(tmp_path):
    manager = IndexManager(tmp_path, snapshot_loader=lambda name: snapshot())
    manager.build_and_activate("news")
    assert manager.is_active_for(
        corpus_revision=7, preprocessing_fingerprint="prep-v1", corpus_name="news"
    )
    assert not manager.is_active_for(
        corpus_revision=8, preprocessing_fingerprint="prep-v1", corpus_name="news"
    )
    assert not manager.is_active_for(
        corpus_revision=7, preprocessing_fingerprint="prep-v2", corpus_name="news"
    )


def test_snapshot_contract_is_validated(tmp_path):
    manager = IndexManager(
        tmp_path,
        snapshot_loader=lambda name: {"documents": [], "corpus_revision": "bad", "preprocessing": {}},
    )
    with pytest.raises(SnapshotLoadError):
        manager.build_and_activate()


def test_empty_snapshot_can_be_indexed(tmp_path):
    manager = IndexManager(
        tmp_path,
        snapshot_loader=lambda name: snapshot(documents=[], revision=0),
    )
    result = manager.build_and_activate("news")
    assert result.artifacts.document_count == 0
    assert result.inverted_index.postings == {}


def test_invalid_weights_during_rebuild_preserve_active_index(tmp_path, monkeypatch):
    import smartdoc.index_manager as module

    manager = IndexManager(tmp_path, snapshot_loader=lambda name: snapshot())
    first = manager.build_and_activate("news")
    manifest = manager.active_manifest_path.read_bytes()
    real_fit = module.fit_tfidf

    def corrupt_fit(*args, **kwargs):
        artifacts = real_fit(*args, **kwargs)
        artifacts.matrix.data *= 3
        return artifacts

    monkeypatch.setattr(module, "fit_tfidf", corrupt_fit)
    with pytest.raises(IndexBuildError):
        manager.build_and_activate("news")
    assert manager.active_manifest_path.read_bytes() == manifest
    assert manager.load_active().version_id == first.version_id
    assert not list(manager.versions_root.glob(".staging-*"))


def test_cached_index_reused_and_disk_changes_still_rejected(tmp_path, monkeypatch):
    import smartdoc.index_manager as module
    from unittest.mock import Mock

    manager = IndexManager(tmp_path, snapshot_loader=lambda name: snapshot())
    manager.build_and_activate()
    loader = Mock(wraps=module.load_tfidf_artifacts)
    monkeypatch.setattr(module, "load_tfidf_artifacts", loader)
    first = manager.load_active()
    assert manager.load_active() is first
    assert loader.call_count == 1
    with (first.directory / 'tfidf_matrix.npz').open('ab') as stream:
        stream.write(b'changed')
    with pytest.raises(IndexBuildError, match='checksum mismatch'):
        manager.load_active()


def test_rebuild_replaces_cached_index_even_with_same_revision(tmp_path):
    manager = IndexManager(tmp_path, snapshot_loader=lambda name: snapshot())
    first = manager.build_and_activate()
    manager.load_active()
    second = manager.build_and_activate()
    assert first.version_id != second.version_id
    assert manager.load_active().version_id == second.version_id


@pytest.mark.parametrize("count", [999, True, "3", None, -1])
def test_active_manifest_rejects_invalid_document_count(tmp_path, count):
    manager = IndexManager(tmp_path, snapshot_loader=lambda name: snapshot())
    manager.build_and_activate()
    manager.load_active()  # A cached valid load must not hide manifest corruption.
    payload = json.loads(manager.active_manifest_path.read_text())
    payload["document_count"] = count
    manager.active_manifest_path.write_text(json.dumps(payload))
    with pytest.raises(IndexBuildError, match="document count"):
        manager.load_active()


def test_active_manifest_rejects_directory_of_another_version(tmp_path):
    manager = IndexManager(tmp_path, snapshot_loader=lambda name: snapshot())
    first = manager.build_and_activate()
    manager.build_and_activate()
    manager.load_active()
    payload = json.loads(manager.active_manifest_path.read_text())
    payload["version_id"] = first.version_id
    manager.active_manifest_path.write_text(json.dumps(payload))
    with pytest.raises(IndexBuildError, match="version_id"):
        manager.load_active()

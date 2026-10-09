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

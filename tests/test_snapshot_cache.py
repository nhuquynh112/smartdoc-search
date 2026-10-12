from unittest.mock import Mock

import pytest

from app.snapshot_cache import RevisionSnapshotCache


def cache_fixture():
    state = {'revision': 7, 'fingerprint': 'v1'}
    revision = Mock(side_effect=lambda: state['revision'])
    snapshot = Mock(side_effect=lambda name: {'corpus_revision': state['revision'],
                                             'documents': [], 'corpus_name': name})
    cache = RevisionSnapshotCache(snapshot, revision, lambda: state['fingerprint'])
    return state, revision, snapshot, cache


def test_text_reused_but_database_checked_on_every_read():
    _, revision, snapshot, cache = cache_fixture()
    cache('news')
    cache('news')
    assert snapshot.call_count == 1
    assert revision.call_count == 2


def test_revision_fingerprint_and_selector_changes_invalidate_text():
    state, _, snapshot, cache = cache_fixture()
    cache('news')
    state['revision'] += 1
    cache('news')
    state['fingerprint'] = 'v2'
    cache('news')
    cache('uploads')
    assert snapshot.call_count == 4


def test_database_disconnect_never_returns_cached_snapshot():
    _, revision, snapshot, cache = cache_fixture()
    cache()
    revision.side_effect = OSError('offline')
    with pytest.raises(OSError):
        cache()
    assert snapshot.call_count == 1


def test_change_between_revision_check_and_snapshot_uses_actual_snapshot_revision():
    state, _, snapshot, cache = cache_fixture()
    def changed(name):
        state['revision'] = 8
        return {'corpus_revision': 8, 'documents': [], 'corpus_name': name}
    snapshot.side_effect = changed
    assert cache()['corpus_revision'] == 8
    cache()
    assert snapshot.call_count == 1

"""Reuse corpus text only while the live database revision remains unchanged."""
from threading import RLock


class RevisionSnapshotCache:
    def __init__(self, snapshot_loader=None, revision_loader=None, fingerprint_loader=None):
        from smartdoc.ingestion import load_corpus_snapshot, load_corpus_revision
        from smartdoc.preprocessing import pipeline_manifest
        self.snapshot_loader = snapshot_loader or load_corpus_snapshot
        self.revision_loader = revision_loader or load_corpus_revision
        self.fingerprint_loader = fingerprint_loader or (lambda: pipeline_manifest()['fingerprint'])
        self._cached = None
        self._lock = RLock()

    def __call__(self, corpus_name=None):
        with self._lock:
            # Never return cached results when PostgreSQL is unreachable.
            revision = self.revision_loader()
            fingerprint = self.fingerprint_loader()
            key = (corpus_name, revision, fingerprint)
            if self._cached is not None and self._cached[0] == key:
                return self._cached[1]
            snapshot = self.snapshot_loader(corpus_name)
            # The loader's transactional snapshot may be newer than the first check.
            actual_key = (corpus_name, snapshot['corpus_revision'], fingerprint)
            self._cached = (actual_key, snapshot)
            return snapshot

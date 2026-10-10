"""Build, validate, and activate versioned TV2 retrieval indexes.

Database access is delegated to TV1's ``load_corpus_snapshot``. Index builds
happen in a new version directory; the active pointer is replaced only after
the artifacts and inverted index have been validated.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .inverted_index import InvertedIndex, build_inverted_index
from .tfidf_engine import (
    TfidfArtifacts,
    TfidfEngineError,
    fit_tfidf,
    load_tfidf_artifacts,
    save_tfidf_artifacts,
)


INDEX_MANAGER_FORMAT_VERSION = 1
ACTIVE_MANIFEST_NAME = "active_index.json"


class IndexManagerError(RuntimeError):
    """Base error for index lifecycle failures."""


class SnapshotLoadError(IndexManagerError):
    """TV1 corpus snapshot could not be loaded or validated."""


class IndexBuildError(IndexManagerError):
    """A new index could not be built and validated."""


class NoActiveIndexError(IndexManagerError):
    """No activated index exists."""


@dataclass(frozen=True)
class ManagedIndex:
    artifacts: TfidfArtifacts
    inverted_index: InvertedIndex
    version_id: str
    directory: Path


def _load_snapshot_default(corpus_name: str | None = None) -> Mapping[str, Any]:
    """Import TV1 integration only when a database-backed build is requested."""
    try:
        from .ingestion import load_corpus_snapshot
    except Exception as exc:
        raise SnapshotLoadError(
            "Could not import TV1 load_corpus_snapshot from smartdoc.ingestion"
        ) from exc

    try:
        snapshot = load_corpus_snapshot(corpus_name=corpus_name)
    except Exception as exc:
        raise SnapshotLoadError(f"TV1 corpus snapshot failed: {exc}") from exc

    if not isinstance(snapshot, Mapping):
        raise SnapshotLoadError("load_corpus_snapshot() must return a mapping")
    return snapshot


def _validate_snapshot(snapshot: Mapping[str, Any]) -> tuple[list[Mapping[str, Any]], int, str | None, str | None]:
    required = ("documents", "corpus_revision", "preprocessing")
    missing = [key for key in required if key not in snapshot]
    if missing:
        raise SnapshotLoadError(f"Snapshot is missing required keys: {', '.join(missing)}")

    documents = snapshot["documents"]
    if isinstance(documents, (str, bytes, Mapping)):
        raise SnapshotLoadError("snapshot['documents'] must be an iterable of document mappings")
    try:
        documents = list(documents)
    except TypeError as exc:
        raise SnapshotLoadError("snapshot['documents'] must be iterable") from exc

    revision = snapshot["corpus_revision"]
    if isinstance(revision, bool) or not isinstance(revision, int):
        raise SnapshotLoadError("snapshot corpus_revision must be an integer")

    preprocessing = snapshot["preprocessing"]
    if not isinstance(preprocessing, Mapping):
        raise SnapshotLoadError("snapshot preprocessing metadata must be a mapping")
    fingerprint = preprocessing.get("fingerprint")
    if fingerprint is not None and not isinstance(fingerprint, str):
        raise SnapshotLoadError("preprocessing fingerprint must be a string or None")

    corpus_name = snapshot.get("corpus_name")
    if corpus_name is not None and not isinstance(corpus_name, str):
        raise SnapshotLoadError("corpus_name must be a string or None")

    return documents, revision, fingerprint, corpus_name


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


class IndexManager:
    """Manage persisted, versioned TF-IDF and inverted indexes.

    ``snapshot_loader`` is injectable for unit tests. In production the default
    is TV1's ``load_corpus_snapshot``. Each successful build creates an
    immutable version directory and atomically updates ``active_index.json``.
    """

    def __init__(
        self,
        index_root: str | Path = "data/tv2_index",
        *,
        snapshot_loader: Callable[[str | None], Mapping[str, Any]] | None = None,
    ) -> None:
        self.index_root = Path(index_root)
        self.index_root.mkdir(parents=True, exist_ok=True)
        self.versions_root = self.index_root / "versions"
        self.versions_root.mkdir(parents=True, exist_ok=True)
        self._snapshot_loader = snapshot_loader or _load_snapshot_default

    @property
    def active_manifest_path(self) -> Path:
        return self.index_root / ACTIVE_MANIFEST_NAME

    def build_and_activate(self, corpus_name: str | None = None) -> ManagedIndex:
        """Build from one TV1 snapshot and activate only after validation."""
        try:
            snapshot = self._snapshot_loader(corpus_name)
            if not isinstance(snapshot, Mapping):
                raise SnapshotLoadError("snapshot loader must return a mapping")
            documents, revision, fingerprint, resolved_corpus_name = _validate_snapshot(snapshot)

            artifacts = fit_tfidf(
                documents,
                corpus_revision=revision,
                preprocessing_fingerprint=fingerprint,
                corpus_name=resolved_corpus_name or corpus_name,
            )
            inverted_index = (
                build_inverted_index(artifacts)
                if artifacts.matrix.shape[1] > 0
                else InvertedIndex(postings={}, ordered_document_ids=artifacts.ordered_document_ids, terms=())
            )

            version_id = f"rev-{revision}-{uuid.uuid4().hex[:12]}"
            final_dir = self.versions_root / version_id
            staging_dir = self.versions_root / f".staging-{version_id}"
            staging_dir.mkdir(parents=False, exist_ok=False)
            try:
                save_tfidf_artifacts(artifacts, staging_dir)
                # Validate serialized artifacts from disk, not just in-memory state.
                loaded_artifacts = load_tfidf_artifacts(staging_dir)
                loaded_index = (
                    build_inverted_index(loaded_artifacts)
                    if loaded_artifacts.matrix.shape[1] > 0
                    else InvertedIndex(postings={}, ordered_document_ids=loaded_artifacts.ordered_document_ids, terms=())
                )
                if loaded_artifacts.ordered_document_ids != artifacts.ordered_document_ids:
                    raise IndexBuildError("Persisted document ordering failed validation")
                if loaded_artifacts.corpus_revision != revision:
                    raise IndexBuildError("Persisted corpus revision failed validation")
                if loaded_artifacts.preprocessing_fingerprint != fingerprint:
                    raise IndexBuildError("Persisted preprocessing fingerprint failed validation")

                # Rename a fully validated directory into its immutable final name.
                os.replace(staging_dir, final_dir)
            except Exception:
                shutil.rmtree(staging_dir, ignore_errors=True)
                raise

            active_payload = {
                "format_version": INDEX_MANAGER_FORMAT_VERSION,
                "version_id": version_id,
                "corpus_revision": revision,
                "preprocessing_fingerprint": fingerprint,
                "corpus_name": resolved_corpus_name or corpus_name,
                "document_count": loaded_artifacts.document_count,
                "artifact_directory": str(Path("versions") / version_id),
            }
            try:
                _write_json_atomic(self.active_manifest_path, active_payload)
            except Exception:
                # Leave the previous active pointer untouched if activation fails.
                # The validated but unreferenced version directory is safe to clean up.
                shutil.rmtree(final_dir, ignore_errors=True)
                raise

            return ManagedIndex(
                artifacts=loaded_artifacts,
                inverted_index=loaded_index,
                version_id=version_id,
                directory=final_dir,
            )
        except IndexManagerError:
            raise
        except Exception as exc:
            raise IndexBuildError(f"Index build/activation failed: {exc}") from exc

    def load_active(self) -> ManagedIndex:
        """Load and validate the currently activated index."""
        if not self.active_manifest_path.is_file():
            raise NoActiveIndexError(
                f"No active index found at {self.active_manifest_path}; build one first"
            )
        try:
            payload = json.loads(self.active_manifest_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("active manifest must be a JSON object")
            if payload.get("format_version") != INDEX_MANAGER_FORMAT_VERSION:
                raise ValueError("unsupported active manifest format_version")
            version_id = payload.get("version_id")
            if not isinstance(version_id, str) or not version_id or Path(version_id).name != version_id:
                raise ValueError("invalid version_id in active manifest")
            relative_dir = payload.get("artifact_directory")
            if not isinstance(relative_dir, str):
                raise ValueError("missing artifact_directory")
            version_dir = (self.index_root / relative_dir).resolve()
            if version_dir.parent != self.versions_root.resolve():
                raise ValueError("artifact directory escapes versions directory")

            artifacts = load_tfidf_artifacts(version_dir)
            if artifacts.corpus_revision != payload.get("corpus_revision"):
                raise ValueError("active manifest revision does not match artifacts")
            if artifacts.preprocessing_fingerprint != payload.get("preprocessing_fingerprint"):
                raise ValueError("active manifest preprocessing fingerprint does not match artifacts")
            if artifacts.corpus_name != payload.get("corpus_name"):
                raise ValueError("active manifest corpus name does not match artifacts")
            inverted_index = (
                build_inverted_index(artifacts)
                if artifacts.matrix.shape[1] > 0
                else InvertedIndex(postings={}, ordered_document_ids=artifacts.ordered_document_ids, terms=())
            )
            return ManagedIndex(
                artifacts=artifacts,
                inverted_index=inverted_index,
                version_id=version_id,
                directory=version_dir,
            )
        except NoActiveIndexError:
            raise
        except Exception as exc:
            raise IndexBuildError(f"Active index is invalid or unreadable: {exc}") from exc

    def is_active_for(
        self,
        *,
        corpus_revision: int,
        preprocessing_fingerprint: str | None,
        corpus_name: str | None = None,
    ) -> bool:
        """Check active metadata against known current corpus metadata."""
        try:
            payload = json.loads(self.active_manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return False
        if not isinstance(payload, dict):
            return False
        return (
            payload.get("corpus_revision") == corpus_revision
            and payload.get("preprocessing_fingerprint") == preprocessing_fingerprint
            and payload.get("corpus_name") == corpus_name
        )

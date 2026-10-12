"""TF-IDF fitting and artifact persistence for SmartDoc Search TV2.

Responsibilities:
- Fit TF-IDF from already-preprocessed TV1 ``clean_text`` values.
- Keep the document-row order explicit and stable.
- Persist/load the vectorizer, sparse matrix and ordered document IDs together.
- Validate artifacts when loading.

This module deliberately does not load a database, preprocess document text, build
the inverted index, or rank search results.
"""
from __future__ import annotations

import json
import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import joblib
import numpy as np
from scipy.sparse import load_npz, save_npz
from sklearn.feature_extraction.text import TfidfVectorizer


ARTIFACT_FORMAT_VERSION = 2
ARTIFACT_FILES = ("vectorizer.joblib", "tfidf_matrix.npz", "ordered_document_ids.json")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class TfidfEngineError(RuntimeError):
    """Base error for TF-IDF engine failures."""


class InvalidTrainingCorpusError(TfidfEngineError):
    """Training corpus does not match the expected TV1 document contract."""


class InvalidTfidfArtifactError(TfidfEngineError):
    """Saved TF-IDF artifact is missing, incompatible or corrupt."""


def _validate_weights(vectorizer: TfidfVectorizer, matrix) -> None:
    """Reject weights that cannot represent the baseline L2 TF-IDF model."""
    expected = {"tokenizer": str.split, "token_pattern": None, "preprocessor": None,
                "lowercase": False, "norm": "l2", "use_idf": True,
                "smooth_idf": True, "sublinear_tf": False,
                "analyzer": "word", "ngram_range": (1, 1), "binary": False,
                "stop_words": None}
    if not isinstance(vectorizer, TfidfVectorizer) or any(
        vectorizer.get_params().get(key) != value for key, value in expected.items()
    ):
        raise InvalidTfidfArtifactError("Vectorizer configuration differs from baseline TF-IDF.")
    if matrix.dtype.kind != "f" or not np.isfinite(matrix.data).all() or (matrix.data < 0).any():
        raise InvalidTfidfArtifactError("TF-IDF matrix must contain finite, nonnegative real weights.")
    try:
        matrix.check_format(full_check=True)
        # sklearn may emit valid CSR rows with unsorted column indices.
        checked = matrix.copy()
        checked.sort_indices()
        if not checked.has_canonical_format:
            raise ValueError("duplicate sparse matrix entries")
        squared_norms = np.asarray(matrix.multiply(matrix).sum(axis=1)).ravel()
        nonempty = np.diff(matrix.indptr) > 0
        if not np.allclose(squared_norms[nonempty], 1.0, rtol=1e-7, atol=1e-9):
            raise ValueError("document vectors are not L2 normalized")
        if matrix.shape[1]:
            vocabulary = vectorizer.vocabulary_
            indices = list(vocabulary.values())
            if (any(isinstance(index, bool) or not isinstance(index, (int, np.integer)) for index in indices)
                    or sorted(indices) != list(range(matrix.shape[1]))):
                raise ValueError("vocabulary indices do not match matrix columns")
            idf = np.asarray(vectorizer.idf_)
            if idf.shape != (matrix.shape[1],) or not np.isfinite(idf).all() or (idf < 1).any():
                raise ValueError("invalid smoothed IDF weights")
    except (AttributeError, TypeError, ValueError) as exc:
        raise InvalidTfidfArtifactError(f"Invalid TF-IDF weights or vocabulary: {exc}") from exc


@dataclass(frozen=True)
class TfidfArtifacts:
    vectorizer: TfidfVectorizer
    matrix: Any
    ordered_document_ids: tuple[int, ...]
    corpus_revision: int
    preprocessing_fingerprint: str | None
    corpus_name: str | None = None

    @property
    def document_count(self) -> int:
        return len(self.ordered_document_ids)


def _validate_documents(
    documents: Iterable[Mapping[str, Any]],
) -> tuple[list[Mapping[str, Any]], tuple[int, ...]]:
    try:
        rows = list(documents)
    except TypeError as exc:
        raise InvalidTrainingCorpusError("documents must be an iterable.") from exc

    ids: list[int] = []
    for pos, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise InvalidTrainingCorpusError(f"Document at position {pos} must be a mapping.")
        if "document_id" not in row:
            raise InvalidTrainingCorpusError(f"Document at position {pos} is missing document_id.")
        if "clean_text" not in row:
            raise InvalidTrainingCorpusError(
                f"Document {row.get('document_id')!r} is missing clean_text."
            )
        doc_id = row["document_id"]
        if isinstance(doc_id, bool) or not isinstance(doc_id, int):
            raise InvalidTrainingCorpusError("document_id must be an integer (bool is invalid).")
        if not isinstance(row["clean_text"], str):
            raise InvalidTrainingCorpusError(f"clean_text for document {doc_id} must be a string.")
        ids.append(doc_id)

    if len(ids) != len(set(ids)):
        raise InvalidTrainingCorpusError("Duplicate document_id values are not allowed.")

    sorted_rows = sorted(zip(ids, rows), key=lambda pair: pair[0])
    return [row for _, row in sorted_rows], tuple(doc_id for doc_id, _ in sorted_rows)


def fit_tfidf(
    documents: Iterable[Mapping[str, Any]],
    *,
    corpus_revision: int,
    preprocessing_fingerprint: str | None = None,
    corpus_name: str | None = None,
) -> TfidfArtifacts:
    """Fit TF-IDF using TV1's already-preprocessed clean_text.

    Empty corpus and all-whitespace corpus are represented as a valid empty
    matrix with zero columns. A non-empty corpus containing only whitespace
    cannot be fit by sklearn, so it is handled explicitly.
    """
    if isinstance(corpus_revision, bool) or not isinstance(corpus_revision, int):
        raise InvalidTrainingCorpusError("corpus_revision must be an integer.")

    rows, ordered_ids = _validate_documents(documents)
    texts = [row["clean_text"] for row in rows]

    vectorizer = TfidfVectorizer(
        tokenizer=str.split,
        token_pattern=None,
        preprocessor=None,
        lowercase=False,
        norm="l2",
        use_idf=True,
        smooth_idf=True,
        sublinear_tf=False,
    )

    if not texts or not any(text.strip() for text in texts):
        # No vocabulary exists. Keep a correctly shaped sparse matrix.
        from scipy.sparse import csr_matrix
        matrix = csr_matrix((len(texts), 0), dtype="float64")
    else:
        try:
            matrix = vectorizer.fit_transform(texts).tocsr()
        except ValueError as exc:
            raise InvalidTrainingCorpusError(
                "TF-IDF fitting failed; check that clean_text contains valid tokens."
            ) from exc

    return TfidfArtifacts(
        vectorizer=vectorizer,
        matrix=matrix,
        ordered_document_ids=ordered_ids,
        corpus_revision=corpus_revision,
        preprocessing_fingerprint=preprocessing_fingerprint,
        corpus_name=corpus_name,
    )


def save_tfidf_artifacts(artifacts: TfidfArtifacts, directory: str | Path) -> Path:
    """Persist artifacts in a directory using temp files then atomic replacements.

    Files:
      - vectorizer.joblib
      - tfidf_matrix.npz
      - ordered_document_ids.json
      - manifest.json
    """
    target = Path(directory)
    _validate_weights(artifacts.vectorizer, artifacts.matrix)
    target.mkdir(parents=True, exist_ok=True)

    payload = {
        "format_version": ARTIFACT_FORMAT_VERSION,
        "corpus_revision": artifacts.corpus_revision,
        "preprocessing_fingerprint": artifacts.preprocessing_fingerprint,
        "corpus_name": artifacts.corpus_name,
        "document_count": artifacts.document_count,
        "matrix_shape": list(artifacts.matrix.shape),
        "ordered_document_ids": list(artifacts.ordered_document_ids),
    }

    temp_paths: list[tuple[Path, Path]] = []
    try:
        with tempfile.TemporaryDirectory(prefix=".tfidf-tmp-", dir=target) as tmp_dir:
            tmp = Path(tmp_dir)
            vectorizer_tmp = tmp / "vectorizer.joblib"
            matrix_tmp = tmp / "tfidf_matrix.npz"
            ids_tmp = tmp / "ordered_document_ids.json"
            manifest_tmp = tmp / "manifest.json"

            joblib.dump(artifacts.vectorizer, vectorizer_tmp)
            save_npz(matrix_tmp, artifacts.matrix)
            ids_tmp.write_text(
                json.dumps(list(artifacts.ordered_document_ids), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            payload["sha256"] = {name: _file_sha256(tmp / name) for name in ARTIFACT_FILES}
            manifest_tmp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            # Replacements are atomic per file. Manifest is replaced last, so
            # readers can treat it as the commit marker for this artifact set.
            for src, name in (
                (vectorizer_tmp, "vectorizer.joblib"),
                (matrix_tmp, "tfidf_matrix.npz"),
                (ids_tmp, "ordered_document_ids.json"),
            ):
                dst = target / name
                os.replace(src, dst)
            os.replace(manifest_tmp, target / "manifest.json")
    except Exception as exc:
        raise TfidfEngineError(f"Failed to save TF-IDF artifacts to {target}: {exc}") from exc

    return target


def load_tfidf_artifacts(directory: str | Path) -> TfidfArtifacts:
    """Load and validate a persisted TF-IDF artifact set."""
    target = Path(directory)
    try:
        manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or manifest.get("format_version") not in (1, ARTIFACT_FORMAT_VERSION):
            raise InvalidTfidfArtifactError("Unsupported or missing artifact format_version.")
        # Check bytes before loading joblib. Checksums detect accidental corruption;
        # these local artifacts still must come from a trusted source.
        if manifest["format_version"] == ARTIFACT_FORMAT_VERSION:
            checksums = manifest.get("sha256")
            if not isinstance(checksums, dict) or set(checksums) != set(ARTIFACT_FILES):
                raise InvalidTfidfArtifactError("Artifact checksums are missing or incomplete.")
            for name in ARTIFACT_FILES:
                if checksums[name] != _file_sha256(target / name):
                    raise InvalidTfidfArtifactError(f"Artifact checksum mismatch: {name}.")
        ids = json.loads((target / "ordered_document_ids.json").read_text(encoding="utf-8"))
        vectorizer = joblib.load(target / "vectorizer.joblib")
        matrix = load_npz(target / "tfidf_matrix.npz").tocsr()
    except (OSError, ValueError, json.JSONDecodeError, EOFError, ImportError) as exc:
        raise InvalidTfidfArtifactError(f"Could not load TF-IDF artifacts: {exc}") from exc
    except Exception as exc:
        raise InvalidTfidfArtifactError(f"Could not deserialize TF-IDF artifacts: {exc}") from exc

    if not isinstance(ids, list) or any(
        isinstance(doc_id, bool) or not isinstance(doc_id, int) for doc_id in ids
    ):
        raise InvalidTfidfArtifactError("ordered_document_ids.json must contain integer IDs.")
    if len(ids) != len(set(ids)):
        raise InvalidTfidfArtifactError("Duplicate IDs found in saved artifacts.")
    if tuple(ids) != tuple(sorted(ids)):
        raise InvalidTfidfArtifactError("Saved document IDs must be sorted ascending.")
    if matrix.shape[0] != len(ids):
        raise InvalidTfidfArtifactError("Matrix row count does not match document ID count.")
    if list(matrix.shape) != manifest.get("matrix_shape"):
        raise InvalidTfidfArtifactError("Matrix shape does not match manifest.")
    if len(ids) != manifest.get("document_count"):
        raise InvalidTfidfArtifactError("Document count does not match manifest.")
    if not isinstance(vectorizer, TfidfVectorizer):
        raise InvalidTfidfArtifactError("Saved vectorizer has an unexpected type.")
    _validate_weights(vectorizer, matrix)

    revision = manifest.get("corpus_revision")
    if isinstance(revision, bool) or not isinstance(revision, int):
        raise InvalidTfidfArtifactError("Manifest corpus_revision must be an integer.")

    return TfidfArtifacts(
        vectorizer=vectorizer,
        matrix=matrix,
        ordered_document_ids=tuple(ids),
        corpus_revision=revision,
        preprocessing_fingerprint=manifest.get("preprocessing_fingerprint"),
        corpus_name=manifest.get("corpus_name"),
    )

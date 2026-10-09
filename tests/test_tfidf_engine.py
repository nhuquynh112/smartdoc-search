import pytest

from smartdoc.tfidf_engine import (
    InvalidTrainingCorpusError,
    InvalidTfidfArtifactError,
    fit_tfidf,
    load_tfidf_artifacts,
    save_tfidf_artifacts,
)


def sample_docs():
    # Ten tiny documents are a development fixture, not production corpus data.
    return [
        {"document_id": 10, "clean_text": "trí_tuệ nhân_tạo"},
        {"document_id": 2, "clean_text": "trí_tuệ dữ_liệu"},
        {"document_id": 8, "clean_text": "học_máy dữ_liệu"},
        {"document_id": 1, "clean_text": "mạng máy_tính"},
        {"document_id": 9, "clean_text": "bảo_mật mạng"},
        {"document_id": 4, "clean_text": "trí_tuệ học_máy"},
        {"document_id": 3, "clean_text": "cơ_sở dữ_liệu"},
        {"document_id": 7, "clean_text": "nhân_tạo ứng_dụng"},
        {"document_id": 6, "clean_text": "an_toàn bảo_mật"},
        {"document_id": 5, "clean_text": "ứng_dụng dữ_liệu"},
    ]


def test_fit_10_documents_and_order_ids():
    artifacts = fit_tfidf(
        sample_docs(),
        corpus_revision=3,
        preprocessing_fingerprint="test-fingerprint",
        corpus_name="sample",
    )
    assert artifacts.document_count == 10
    assert artifacts.ordered_document_ids == tuple(range(1, 11))
    assert artifacts.matrix.shape[0] == 10
    assert artifacts.matrix.shape[1] > 0


def test_fit_does_not_preprocess_clean_text_again():
    artifacts = fit_tfidf(
        [{"document_id": 1, "clean_text": "trí_tuệ nhân_tạo"}],
        corpus_revision=1,
    )
    assert "trí_tuệ" in artifacts.vectorizer.vocabulary_
    assert "nhân_tạo" in artifacts.vectorizer.vocabulary_


def test_save_and_load_round_trip(tmp_path):
    original = fit_tfidf(
        sample_docs(),
        corpus_revision=14,
        preprocessing_fingerprint="fp-1",
        corpus_name="sample",
    )
    save_tfidf_artifacts(original, tmp_path / "index")
    loaded = load_tfidf_artifacts(tmp_path / "index")

    assert loaded.ordered_document_ids == original.ordered_document_ids
    assert loaded.corpus_revision == 14
    assert loaded.preprocessing_fingerprint == "fp-1"
    assert loaded.corpus_name == "sample"
    assert loaded.matrix.shape == original.matrix.shape
    assert (loaded.matrix != original.matrix).nnz == 0
    assert loaded.vectorizer.vocabulary_ == original.vectorizer.vocabulary_


def test_duplicate_ids_rejected():
    with pytest.raises(InvalidTrainingCorpusError):
        fit_tfidf(
            [
                {"document_id": 1, "clean_text": "alpha"},
                {"document_id": 1, "clean_text": "beta"},
            ],
            corpus_revision=1,
        )


def test_bad_clean_text_rejected():
    with pytest.raises(InvalidTrainingCorpusError):
        fit_tfidf([{"document_id": 1, "clean_text": None}], corpus_revision=1)


def test_empty_corpus_has_zero_row_matrix():
    artifacts = fit_tfidf([], corpus_revision=0)
    assert artifacts.matrix.shape == (0, 0)
    assert artifacts.document_count == 0


def test_corrupt_manifest_rejected(tmp_path):
    artifacts = fit_tfidf(sample_docs(), corpus_revision=1)
    directory = save_tfidf_artifacts(artifacts, tmp_path / "index")
    (directory / "manifest.json").write_text('{"format_version": 999}', encoding="utf-8")
    with pytest.raises(InvalidTfidfArtifactError):
        load_tfidf_artifacts(directory)

"""Tests for SmartDoc TV2 inverted-index utilities."""
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer

from smartdoc.inverted_index import (
    InvertedIndex,
    InvalidInvertedIndexInputError,
    build_inverted_index,
    get_candidates,
    get_postings,
)


def make_artifacts(texts, document_ids):
    vectorizer = TfidfVectorizer(
        tokenizer=str.split,
        token_pattern=None,
        preprocessor=None,
        lowercase=False,
        norm="l2",
        smooth_idf=True,
        sublinear_tf=False,
    )
    if texts:
        matrix = vectorizer.fit_transform(texts).tocsr()
    else:
        # sklearn cannot fit an empty corpus; model the empty artifacts shape.
        vectorizer.fit(["placeholdertoken"])
        vectorizer = TfidfVectorizer(
            tokenizer=str.split,
            token_pattern=None,
            preprocessor=None,
            lowercase=False,
            norm="l2",
            smooth_idf=True,
            sublinear_tf=False,
        )
        matrix = sparse.csr_matrix((0, 0), dtype=np.float64)
        vectorizer = SimpleNamespace(get_feature_names_out=lambda: np.array([], dtype=str))
    return SimpleNamespace(
        vectorizer=vectorizer,
        matrix=matrix,
        ordered_document_ids=tuple(document_ids),
    )


def test_build_index_maps_terms_to_document_ids():
    artifacts = make_artifacts(
        ["apple fresh", "banana fresh", "apple rotten"],
        [30, 10, 20],
    )
    index = build_inverted_index(artifacts)

    assert get_postings(index, "apple") == (20, 30)
    assert get_postings(index, "banana") == (10,)
    assert get_postings(index, "fresh") == (10, 30)
    assert get_postings(index, "missing") == ()


def test_candidates_are_union_sorted_and_unique():
    index = build_inverted_index(
        make_artifacts(["apple fresh", "banana fresh", "apple rotten"], [30, 10, 20])
    )

    assert get_candidates(index, ["apple", "fresh"]) == (10, 20, 30)
    assert get_candidates(index, ["apple", "apple"]) == (20, 30)


def test_unknown_terms_return_no_candidates():
    index = build_inverted_index(make_artifacts(["apple fresh"], [7]))
    assert get_candidates(index, ["unknown", "absent"]) == ()


def test_empty_query_terms_return_no_candidates():
    index = build_inverted_index(make_artifacts(["apple fresh"], [7]))
    assert get_candidates(index, []) == ()


def test_empty_corpus_builds_empty_index():
    index = build_inverted_index(make_artifacts([], []))
    assert index.postings == {}
    assert index.ordered_document_ids == ()
    assert index.terms == ()
    assert get_candidates(index, ["anything"]) == ()


def test_invalid_row_count_is_rejected():
    artifacts = make_artifacts(["apple fresh"], [7, 8])
    with pytest.raises(InvalidInvertedIndexInputError, match="length"):
        build_inverted_index(artifacts)


def test_duplicate_document_ids_are_rejected():
    artifacts = make_artifacts(["apple fresh", "banana fresh"], [7, 7])
    with pytest.raises(InvalidInvertedIndexInputError, match="unique"):
        build_inverted_index(artifacts)


def test_dense_matrix_is_rejected():
    artifacts = make_artifacts(["apple fresh"], [7])
    artifacts.matrix = artifacts.matrix.toarray()
    with pytest.raises(InvalidInvertedIndexInputError, match="sparse"):
        build_inverted_index(artifacts)


def test_posting_lists_contain_only_terms_with_nonzero_weights():
    index = build_inverted_index(make_artifacts(["apple", "banana"], [2, 1]))
    assert set(index.postings) == {"apple", "banana"}
    assert all(ids for ids in index.postings.values())


def test_index_dataclass_copies_postings_mapping():
    source = {"apple": (1,)}
    index = InvertedIndex(source, (1,), ("apple",))
    source["apple"] = (2,)
    assert index.postings["apple"] == (1,)


def test_non_string_query_term_is_rejected():
    index = build_inverted_index(make_artifacts(["apple fresh"], [7]))
    with pytest.raises(InvalidInvertedIndexInputError, match="strings"):
        get_candidates(index, ["apple", 123])

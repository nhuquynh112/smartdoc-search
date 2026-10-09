"""Tests for query-time TF-IDF retrieval and ranking."""
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer

from smartdoc.inverted_index import build_inverted_index
from smartdoc.search_engine import (
    InvalidSearchInputError,
    create_search_engine,
    search,
    search_brute_force,
)


def make_engine(texts, ids):
    vectorizer = TfidfVectorizer(
        tokenizer=str.split,
        token_pattern=None,
        preprocessor=None,
        lowercase=False,
        norm="l2",
        smooth_idf=True,
        sublinear_tf=False,
    )
    matrix = vectorizer.fit_transform(texts).tocsr()
    artifacts = SimpleNamespace(
        vectorizer=vectorizer,
        matrix=matrix,
        ordered_document_ids=tuple(ids),
    )
    index = build_inverted_index(artifacts)
    return create_search_engine(artifacts, index)


def test_search_returns_exact_contract_and_ranks_best_first():
    engine = make_engine(["apple fresh sweet", "banana fresh", "apple rotten"], [30, 10, 20])
    results = search(engine, "apple", top_k=3)
    assert all(set(row) == {"document_id", "score", "rank"} for row in results)
    assert [row["rank"] for row in results] == [1, 2]
    assert [row["document_id"] for row in results] == [20, 30]
    assert results[0]["score"] > results[1]["score"]


def test_ties_are_broken_by_document_id_ascending():
    engine = make_engine(["apple", "apple", "banana"], [30, 10, 20])
    results = search(engine, "apple", top_k=5)
    assert [row["document_id"] for row in results] == [10, 30]


def test_top_k_limits_results():
    engine = make_engine(["apple", "apple fresh", "apple sweet"], [3, 1, 2])
    results = search(engine, "apple", top_k=2)
    assert len(results) == 2
    assert [row["rank"] for row in results] == [1, 2]


@pytest.mark.parametrize("query", ["", "   ", "unknownword"])
def test_empty_or_oov_query_returns_empty_list(query):
    engine = make_engine(["apple fresh", "banana fresh"], [1, 2])
    assert search(engine, query) == []


def test_query_with_no_matching_document_returns_empty_list():
    engine = make_engine(["apple", "banana"], [1, 2])
    assert search(engine, "orange") == []


def test_candidate_search_matches_brute_force():
    engine = make_engine(
        ["apple fresh sweet", "banana fresh", "apple rotten",
         "orange fresh sweet", "banana rotten sweet"],
        [50, 10, 40, 20, 30],
    )
    for query in ["apple", "fresh sweet", "banana rotten", "sweet unknown", "missing"]:
        fast = search(engine, query, top_k=10)
        reference = search_brute_force(engine, query, top_k=10)
        assert [item["document_id"] for item in fast] == [
            item["document_id"] for item in reference
        ]
        assert [item["rank"] for item in fast] == [item["rank"] for item in reference]
        assert [item["score"] for item in fast] == pytest.approx(
            [item["score"] for item in reference], abs=1e-12
        )


@pytest.mark.parametrize("top_k", [0, -1, True, 1.5])
def test_invalid_top_k_is_rejected(top_k):
    engine = make_engine(["apple", "banana"], [1, 2])
    with pytest.raises(InvalidSearchInputError, match="top_k"):
        search(engine, "apple", top_k=top_k)


def test_non_string_query_is_rejected():
    engine = make_engine(["apple", "banana"], [1, 2])
    with pytest.raises(InvalidSearchInputError, match="query"):
        search(engine, None)


def test_empty_corpus_search_returns_empty_results():
    vectorizer = SimpleNamespace(
        get_feature_names_out=lambda: np.array([], dtype=str)
    )
    artifacts = SimpleNamespace(
        vectorizer=vectorizer,
        matrix=sparse.csr_matrix((0, 0)),
        ordered_document_ids=(),
    )
    index = build_inverted_index(artifacts)
    engine = create_search_engine(artifacts, index)
    assert search(engine, "apple") == []

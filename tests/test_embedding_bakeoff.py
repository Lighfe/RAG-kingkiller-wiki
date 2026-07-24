"""Unit tests for ingest.embedding_bakeoff - no live API calls, no ONNX model load."""

from __future__ import annotations

import numpy as np
import pytest

from ingest.embedding_bakeoff import (
    compute_ranks,
    estimate_openai_tokens,
    get_local_embeddings,
    get_openai_embeddings,
    hit_rate_at_k,
    mrr_at,
    rank_of_target,
    run_local_candidate,
    run_openai_candidate,
    score_ranks,
    stratum_scores,
    to_markdown,
)

# -- ranking -------------------------------------------------------------------


def test_rank_of_target_best_match_is_rank_1():
    sims = np.array([0.9, 0.5, 0.1])
    assert rank_of_target(sims, 0) == 1


def test_rank_of_target_counts_strictly_better_items():
    sims = np.array([0.1, 0.9, 0.5, 0.8])
    assert rank_of_target(sims, 0) == 4  # three items strictly better


def test_rank_of_target_ties_are_tied_for_best():
    sims = np.array([0.5, 0.5, 0.1])
    assert rank_of_target(sims, 0) == 1
    assert rank_of_target(sims, 1) == 1


def test_compute_ranks_matches_manual_similarity():
    # 2 questions, 3 chunks, 2-dim embeddings (already unit vectors)
    chunk_vecs = np.array([[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]])
    question_vecs = np.array([[1.0, 0.0], [0.0, 1.0]])
    ranks = compute_ranks(question_vecs, chunk_vecs, target_indices=[0, 1])
    assert ranks == [1, 1]


def test_compute_ranks_when_target_is_not_top_match():
    chunk_vecs = np.array([[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]])
    question_vecs = np.array([[1.0, 0.0]])
    # target is index 2 (orthogonal, worst match) -> rank 3
    ranks = compute_ranks(question_vecs, chunk_vecs, target_indices=[2])
    assert ranks == [3]


# -- hit rate / MRR --------------------------------------------------------------


def test_hit_rate_at_k_counts_within_cutoff():
    ranks = [1, 2, 5, 11]
    assert hit_rate_at_k(ranks, 1) == pytest.approx(0.25)
    assert hit_rate_at_k(ranks, 5) == pytest.approx(0.75)
    assert hit_rate_at_k(ranks, 10) == pytest.approx(0.75)


def test_hit_rate_at_k_empty_is_zero():
    assert hit_rate_at_k([], 5) == 0.0


def test_mrr_at_reciprocal_rank_with_cutoff():
    ranks = [1, 2, 4, 20]
    # 1/1 + 1/2 + 1/4 + 0 (beyond cutoff 10) = 1.75, /4 = 0.4375
    assert mrr_at(ranks, cutoff=10) == pytest.approx(1.75 / 4)


def test_mrr_at_empty_is_zero():
    assert mrr_at([], cutoff=10) == 0.0


def test_score_ranks_reports_n_and_all_ks():
    ranks = [1, 1, 3, 10, 50]
    scores = score_ranks(ranks, ks=(1, 3, 10))
    assert scores["n"] == 5
    assert scores["hit_rate@1"] == pytest.approx(2 / 5)
    assert scores["hit_rate@3"] == pytest.approx(3 / 5)
    assert scores["hit_rate@10"] == pytest.approx(4 / 5)
    assert "mrr@10" in scores


# -- stratum grouping ------------------------------------------------------------


def test_stratum_scores_groups_by_key():
    questions = [
        {"book_level": 1}, {"book_level": 1}, {"book_level": 2},
    ]
    ranks = [1, 2, 1]
    grouped = stratum_scores(questions, ranks, "book_level")
    assert set(grouped.keys()) == {"1", "2"}
    assert grouped["1"]["n"] == 2
    assert grouped["2"]["n"] == 1
    assert grouped["2"]["hit_rate@1"] == 1.0


# -- OpenAI embedding fetcher (mocked client) ------------------------------------


class FakeEmbeddingData:
    def __init__(self, embedding):
        self.embedding = embedding


class FakeEmbeddingUsage:
    def __init__(self, total_tokens):
        self.total_tokens = total_tokens


class FakeEmbeddingResponse:
    def __init__(self, vectors, total_tokens):
        self.data = [FakeEmbeddingData(v) for v in vectors]
        self.usage = FakeEmbeddingUsage(total_tokens)


class FakeEmbeddingsClient:
    def __init__(self, vectors_by_call):
        self._queue = list(vectors_by_call)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        vectors = self._queue.pop(0)
        return FakeEmbeddingResponse(vectors, total_tokens=len(vectors) * 10)


class FakeOpenAIClient:
    def __init__(self, vectors_by_call):
        self.embeddings = FakeEmbeddingsClient(vectors_by_call)


def test_get_openai_embeddings_batches_and_normalizes():
    client = FakeOpenAIClient([[[3.0, 4.0], [1.0, 0.0]]])  # one batch, two texts
    vecs, tokens = get_openai_embeddings(client, ["a", "b"], model="text-embedding-3-small", batch_size=100)
    assert vecs.shape == (2, 2)
    assert np.allclose(np.linalg.norm(vecs, axis=1), 1.0)
    assert tokens == 20


def test_get_openai_embeddings_splits_into_multiple_batches():
    client = FakeOpenAIClient([[[1.0, 0.0]], [[0.0, 1.0]]])
    vecs, tokens = get_openai_embeddings(client, ["a", "b"], model="text-embedding-3-small", batch_size=1)
    assert len(client.embeddings.calls) == 2
    assert vecs.shape == (2, 2)
    assert tokens == 20


def test_run_openai_candidate_sums_chunk_and_question_tokens():
    client = FakeOpenAIClient([[[1.0, 0.0], [0.0, 1.0]], [[1.0, 1.0]]])
    chunk_vecs, q_vecs, total = run_openai_candidate(
        client, "text-embedding-3-small", ["c1", "c2"], ["q1"]
    )
    assert chunk_vecs.shape == (2, 2)
    assert q_vecs.shape == (1, 2)
    assert total == 30  # (2 + 1) * 10


# -- local embedding fetcher (fake embedder, no ONNX load) -----------------------


class FakeLocalEmbedder:
    def __init__(self):
        self.calls: list[list[str]] = []

    def encode_batch(self, texts, normalize=True):
        self.calls.append(list(texts))
        return np.array([[float(len(t)), 0.0] for t in texts])


def test_get_local_embeddings_concatenates_batches():
    embedder = FakeLocalEmbedder()
    vecs = get_local_embeddings(embedder, ["a", "bb", "ccc", "dddd"], batch_size=2)
    assert vecs.shape == (4, 2)
    assert len(embedder.calls) == 2


def test_run_local_candidate_prefixes_only_questions():
    embedder = FakeLocalEmbedder()
    run_local_candidate(embedder, ["chunk text"], ["a question"])
    chunk_call, question_call = embedder.calls
    assert chunk_call == ["chunk text"]
    assert question_call[0].startswith("Represent this sentence for searching relevant passages: ")
    assert question_call[0].endswith("a question")


# -- dry-run token estimate -------------------------------------------------------


def test_estimate_openai_tokens_scales_with_text():
    few = estimate_openai_tokens(["short"])
    more = estimate_openai_tokens(["short", "a much longer piece of text with many more tokens in it"])
    assert more > few


# -- markdown report ---------------------------------------------------------------


def test_to_markdown_includes_every_candidate_and_stratum():
    results = {
        "generated_at": "2026-07-24T00:00:00Z",
        "corpus_chunks_total": 10,
        "questions_total": 4,
        "candidates": {
            "model-a": {
                "overall": {"n": 4, "hit_rate@1": 0.5, "hit_rate@3": 0.75, "hit_rate@5": 1.0, "hit_rate@10": 1.0, "mrr@10": 0.6},
                "by_book_level": {"1": {"n": 2, "hit_rate@1": 0.5, "hit_rate@3": 1.0, "hit_rate@5": 1.0, "hit_rate@10": 1.0, "mrr@10": 0.75}},
                "by_chunk_type": {"prose": {"n": 4, "hit_rate@1": 0.5, "hit_rate@3": 0.75, "hit_rate@5": 1.0, "hit_rate@10": 1.0, "mrr@10": 0.6}},
                "tokens": 1000,
                "cost_usd_est": 0.02,
            },
        },
    }
    md = to_markdown(results)
    assert "model-a" in md
    assert "book_level=1" in md
    assert "chunk_type=prose" in md
    assert "0.5" in md

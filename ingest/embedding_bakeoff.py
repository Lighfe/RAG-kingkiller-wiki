"""Task 8 Part C (rerun by task 8a Part D): embedding-model bake-off
(offline, Stage 1 - no Elasticsearch, no hybrid search, no reranking).

Candidates: text-embedding-3-small, text-embedding-3-large (OpenAI API),
bge-small-en-v1.5 (ONNX Runtime, local — ingest/local_embedder.py,
ingest/download_model.py). Embeds every corpus chunk
(data/chunks_labeled.jsonl, all 1,761 — excluded-from-sourcing chunks
stay indexable per D31) plus every generated question
(data/eval/questions.jsonl, D31/D40's 148). Ground truth is binary
(D40): the question's source chunk_id, ranked against the whole corpus
by cosine similarity. Reports hit rate@{1,3,5,10} and MRR@10 (approved
2026-07-24), per book_level and chunk_type stratum plus overall — no
NDCG, no graded credit (D40).

Task 8a (D41): task 8's original questions.jsonl had real generation
defects (wiki-metatextual leakage, compound/quiz-style questions, a
pool-exclusion gap) — that run's embedding_baking_off_results is void.
This rerun scores the same three candidates/k-values against the fixed,
regenerated question set only; results here supersede task 8's, not a
silent overwrite (see the "supersedes" field below and D41).

Run: ``uv run python -m ingest.embedding_bakeoff --dry-run`` (OpenAI
token/cost estimate; the local candidate has no API cost to estimate) or
``uv run python -m ingest.embedding_bakeoff`` (live run, writes
data/eval/embedding_baking_off_results.{json,md}).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import tiktoken

from ingest.local_embedder import BGE_QUERY_PREFIX, Embedder

OPENAI_EMBED_MODELS = ["text-embedding-3-small", "text-embedding-3-large"]
LOCAL_MODEL_NAME = "bge-small-en-v1.5"
LOCAL_MODEL_PATH = "models/Xenova/bge-small-en-v1.5"

# Approximate: OpenAI's pricing page was unreachable (403) while writing
# this script. These are the long-standing public per-1M-token rates for
# the text-embedding-3 family (unchanged since their 2024 launch as of
# this writing) — used only for the --dry-run estimate; the live run's
# reported cost instead sums real `usage.total_tokens` from each response
# and applies these same rates, so re-check them before trusting either
# figure for actual spend.
PRICE_PER_1M_TOKENS = {
    "text-embedding-3-small": 0.02,
    "text-embedding-3-large": 0.13,
}
TOKENIZER_ENCODING = "cl100k_base"

K_VALUES = (1, 3, 5, 10)
MRR_CUTOFF = 10
OPENAI_BATCH_SIZE = 100
LOCAL_BATCH_SIZE = 32
TOOL_VERSION = "0.2"

log = logging.getLogger(__name__)


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# -- ranking + metrics (pure) -------------------------------------------------


def rank_of_target(sim_row: np.ndarray, target_idx: int) -> int:
    """1-indexed rank of target_idx in descending similarity order.
    Ties count as tied-for-best: rank = 1 + count of strictly-better items."""
    return int(1 + np.sum(sim_row > sim_row[target_idx]))


def compute_ranks(question_vecs: np.ndarray, chunk_vecs: np.ndarray, target_indices: list[int]) -> list[int]:
    sims = question_vecs @ chunk_vecs.T  # cosine, since both sides are unit-normalized
    return [rank_of_target(sims[i], target_indices[i]) for i in range(len(target_indices))]


def hit_rate_at_k(ranks: list[int], k: int) -> float:
    if not ranks:
        return 0.0
    return sum(1 for r in ranks if r <= k) / len(ranks)


def mrr_at(ranks: list[int], cutoff: int) -> float:
    if not ranks:
        return 0.0
    return sum(1.0 / r if r <= cutoff else 0.0 for r in ranks) / len(ranks)


def score_ranks(ranks: list[int], ks: tuple[int, ...] = K_VALUES, mrr_cutoff: int = MRR_CUTOFF) -> dict:
    return {
        "n": len(ranks),
        **{f"hit_rate@{k}": round(hit_rate_at_k(ranks, k), 4) for k in ks},
        f"mrr@{mrr_cutoff}": round(mrr_at(ranks, mrr_cutoff), 4),
    }


def stratum_scores(questions: list[dict], ranks: list[int], key: str) -> dict:
    groups: dict = {}
    for q, r in zip(questions, ranks):
        groups.setdefault(q[key], []).append(r)
    return {str(k): score_ranks(v) for k, v in sorted(groups.items(), key=lambda kv: str(kv[0]))}


# -- embedding fetchers --------------------------------------------------------


def get_openai_embeddings(
    client, texts: list[str], model: str, batch_size: int = OPENAI_BATCH_SIZE
) -> tuple[np.ndarray, int]:
    vectors: list[list[float]] = []
    total_tokens = 0
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = client.embeddings.create(model=model, input=batch)
        vectors.extend(d.embedding for d in response.data)
        total_tokens += response.usage.total_tokens
    arr = np.array(vectors, dtype=np.float32)
    arr = arr / np.linalg.norm(arr, axis=1, keepdims=True)
    return arr, total_tokens


def get_local_embeddings(embedder: Embedder, texts: list[str], batch_size: int = LOCAL_BATCH_SIZE) -> np.ndarray:
    batches = [embedder.encode_batch(texts[i : i + batch_size]) for i in range(0, len(texts), batch_size)]
    return np.concatenate(batches, axis=0)


def estimate_openai_tokens(texts: list[str]) -> int:
    enc = tiktoken.get_encoding(TOKENIZER_ENCODING)
    return sum(len(enc.encode(t)) for t in texts)


# -- per-candidate runners -----------------------------------------------------


def run_openai_candidate(client, model: str, chunk_texts: list[str], question_texts: list[str]) -> tuple[np.ndarray, np.ndarray, int]:
    chunk_vecs, chunk_tokens = get_openai_embeddings(client, chunk_texts, model)
    q_vecs, q_tokens = get_openai_embeddings(client, question_texts, model)
    return chunk_vecs, q_vecs, chunk_tokens + q_tokens


def run_local_candidate(embedder: Embedder, chunk_texts: list[str], question_texts: list[str]) -> tuple[np.ndarray, np.ndarray]:
    chunk_vecs = get_local_embeddings(embedder, chunk_texts)
    prefixed = [BGE_QUERY_PREFIX + q for q in question_texts]
    q_vecs = get_local_embeddings(embedder, prefixed)
    return chunk_vecs, q_vecs


# -- reporting ------------------------------------------------------------------


def to_markdown(results: dict) -> str:
    candidates = list(results["candidates"].keys())
    lines = [
        "# Embedding-model bake-off — task 8 Part C",
        "",
        f"Generated {results['generated_at']}. Corpus: {results['corpus_chunks_total']} chunks "
        f"(data/chunks_labeled.jsonl). Questions: {results['questions_total']} "
        "(data/eval/questions.jsonl, D31 floor-stratified draw). Ground truth: binary, "
        "exact chunk_id (D40). Metrics: hit rate@{1,3,5,10}, MRR@10.",
    ]
    if results.get("supersedes"):
        lines += ["", f"**Supersedes a prior run** — {results['supersedes']}"]
    lines += [
        "",
        "## Overall",
        "",
        "| model | n | hit_rate@1 | hit_rate@3 | hit_rate@5 | hit_rate@10 | mrr@10 |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in candidates:
        o = results["candidates"][c]["overall"]
        lines.append(
            f"| {c} | {o['n']} | {o['hit_rate@1']} | {o['hit_rate@3']} | "
            f"{o['hit_rate@5']} | {o['hit_rate@10']} | {o['mrr@10']} |"
        )

    for label, key in (("book_level", "by_book_level"), ("chunk_type", "by_chunk_type")):
        lines += ["", f"## By {label}", ""]
        strata = sorted({s for c in candidates for s in results["candidates"][c][key]})
        for s in strata:
            lines += [
                f"### {label}={s}",
                "",
                "| model | n | hit_rate@1 | hit_rate@3 | hit_rate@5 | hit_rate@10 | mrr@10 |",
                "|---|---|---|---|---|---|---|",
            ]
            for c in candidates:
                st = results["candidates"][c][key].get(s)
                if st is None:
                    continue
                lines.append(
                    f"| {c} | {st['n']} | {st['hit_rate@1']} | {st['hit_rate@3']} | "
                    f"{st['hit_rate@5']} | {st['hit_rate@10']} | {st['mrr@10']} |"
                )
            lines.append("")

    lines += [
        "## Cost / runtime",
        "",
        "| model | tokens | cost_usd_est |",
        "|---|---|---|",
    ]
    for c in candidates:
        r = results["candidates"][c]
        tokens = r["tokens"] if r["tokens"] is not None else "—"
        lines.append(f"| {c} | {tokens} | {r['cost_usd_est']} |")

    lines += [
        "",
        "## Notes",
        "",
        "- Not a model-selection decision (task 8 non-goal) — this produces the "
        "numbers; picking a winner is a follow-up read of this output.",
        "- bge-small-en-v1.5 uses CLS-token pooling (its own `1_Pooling/config.json`: "
        "`pooling_mode_cls_token=true`), not the mean pooling the reused course "
        "embedder.py pattern defaults to for MiniLM — applied correctly here "
        "(`ingest/local_embedder.py`), not left as a silent mismatch.",
        "- bge-small-en-v1.5's queries are prefixed with its model-card-recommended "
        "instruction (`\"Represent this sentence for searching relevant passages: \"`), "
        "passages are not — both OpenAI candidates get the question text unprefixed.",
        "- bge-small-en-v1.5 truncates at 512 tokens (its own max_seq_length); a "
        "handful of oversized chunks (D16: unsplit paragraphs up to 1,114 words) "
        "exceed that and are silently truncated for this candidate only — the "
        "OpenAI candidates' 8191-token limit isn't reached by anything in this corpus.",
        "- Embedding cost prices are approximate publicly-known rates, not fetched live "
        "for this run (see PRICE_PER_1M_TOKENS in ingest/embedding_bakeoff.py) — re-check "
        "before trusting cost figures for real spend at production scale.",
    ]

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Embedding-model bake-off (task 8 Part C).")
    parser.add_argument("--chunks", type=Path, default=Path("data/chunks_labeled.jsonl"))
    parser.add_argument("--questions", type=Path, default=Path("data/eval/questions.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/eval/embedding_baking_off_results"))
    parser.add_argument(
        "--dry-run", action="store_true",
        help="estimate OpenAI tokens/cost only; no API calls, no local model load",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    chunks = load_jsonl(args.chunks)
    questions = load_jsonl(args.questions)
    chunk_ids = [c["chunk_id"] for c in chunks]
    chunk_id_to_idx = {cid: i for i, cid in enumerate(chunk_ids)}
    chunk_texts = [c["text"] for c in chunks]
    question_texts = [q["question"] for q in questions]

    missing = [q["chunk_id"] for q in questions if q["chunk_id"] not in chunk_id_to_idx]
    if missing:
        sys.exit(f"error: {len(missing)} question ground-truth chunk_id(s) not in corpus: {missing[:5]}")
    target_indices = [chunk_id_to_idx[q["chunk_id"]] for q in questions]

    if args.dry_run:
        all_texts = chunk_texts + question_texts
        tokens = estimate_openai_tokens(all_texts)
        print(f"corpus chunks: {len(chunks)}, questions: {len(questions)}")
        print(f"estimated tokens per OpenAI candidate: {tokens:,} (tokenised with {TOKENIZER_ENCODING})")
        for model in OPENAI_EMBED_MODELS:
            cost = tokens / 1_000_000 * PRICE_PER_1M_TOKENS[model]
            print(f"  {model}: ~${cost:.4f} (${PRICE_PER_1M_TOKENS[model]}/1M tokens)")
        print(f"  {LOCAL_MODEL_NAME}: local ONNX inference, no API cost")
        return 0

    from dotenv import load_dotenv
    load_dotenv()
    from openai import OpenAI

    client = OpenAI()
    candidates: dict = {}

    for model in OPENAI_EMBED_MODELS:
        log.info("embedding with %s ...", model)
        t0 = time.monotonic()
        chunk_vecs, q_vecs, tokens = run_openai_candidate(client, model, chunk_texts, question_texts)
        ranks = compute_ranks(q_vecs, chunk_vecs, target_indices)
        candidates[model] = {
            "overall": score_ranks(ranks),
            "by_book_level": stratum_scores(questions, ranks, "book_level"),
            "by_chunk_type": stratum_scores(questions, ranks, "chunk_type"),
            "tokens": tokens,
            "cost_usd_est": round(tokens / 1_000_000 * PRICE_PER_1M_TOKENS[model], 4),
            "duration_s": round(time.monotonic() - t0, 1),
        }
        log.info("%s: overall %s", model, candidates[model]["overall"])

    log.info("embedding with %s (local) ...", LOCAL_MODEL_NAME)
    t0 = time.monotonic()
    embedder = Embedder(path=LOCAL_MODEL_PATH)
    chunk_vecs, q_vecs = run_local_candidate(embedder, chunk_texts, question_texts)
    ranks = compute_ranks(q_vecs, chunk_vecs, target_indices)
    candidates[LOCAL_MODEL_NAME] = {
        "overall": score_ranks(ranks),
        "by_book_level": stratum_scores(questions, ranks, "book_level"),
        "by_chunk_type": stratum_scores(questions, ranks, "chunk_type"),
        "tokens": None,
        "cost_usd_est": 0.0,
        "duration_s": round(time.monotonic() - t0, 1),
    }
    log.info("%s: overall %s", LOCAL_MODEL_NAME, candidates[LOCAL_MODEL_NAME]["overall"])

    results = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "supersedes": "task 8's original embedding_baking_off_results.{json,md} (D41: void because that "
                      "run scored against a defective question set - wiki-metatextual leakage, "
                      "compound/quiz-style questions, a pool-exclusion gap) - not a silent overwrite. "
                      "Same three candidates, same k-values/MRR cutoff, rerun against task 8a's fixed, "
                      "regenerated data/eval/questions.jsonl only.",
        "tool_version": TOOL_VERSION,
        "corpus_chunks_total": len(chunks),
        "questions_total": len(questions),
        "k_values": list(K_VALUES),
        "mrr_cutoff": MRR_CUTOFF,
        "candidates": candidates,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix(".json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(to_markdown(results), encoding="utf-8")
    print(f"wrote {args.output.with_suffix('.json')} and {args.output.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

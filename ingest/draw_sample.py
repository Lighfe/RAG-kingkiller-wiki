"""Draw the stratified adversarial sample for labeler validation (D13).

Samples 80 chunks from the LLM-governed frame (label_provenance null,
is_speculation false): ~60% from the audit-named book-2 clusters (the
only slice that measures book-2 recall = spoiler leakage in the
direction that matters), ~40% uniform from the rest. The output file
carries chunk_ids and strata only — no wiki text, no labels — so it is
committed and the sample stays reproducible and reviewable.

Run: ``uv run python -m ingest.draw_sample [--input FILE] [--output FILE]``
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path

# The sample must come from the frozen chunk set (D14).
FROZEN_SHA256_PREFIX = "a988ed70"

SAMPLE_SIZE = 80
CLUSTER_TARGET = 48  # ~60% (D13)
SEED = 20260719

# Audit-named book-2 clusters (dataset-notes §5). Reviewable list; matched
# with word boundaries against page_title, section_heading, and categories
# ("Adem" must not fire on "Academy"). First match in list order wins.
CLUSTER_KEYWORDS = [
    "Ademre",
    "Ademic",
    "Adem",
    "Shehyn",
    "Rethe",
    "Vaevin",
    "sign language",
    "Faen",
    "Felurian",
    "Maer",
    "Alveron",
    "Severen",
    "Vintas",
]
_PATTERNS = [
    (kw, re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE)) for kw in CLUSTER_KEYWORDS
]


def verify_frozen(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if not digest.startswith(FROZEN_SHA256_PREFIX):
        sys.exit(
            f"error: {path} sha256 {digest[:12]}… does not start with "
            f"{FROZEN_SHA256_PREFIX} — not the frozen chunk set; re-check "
            "before sampling (the ground truth must reference frozen chunks)"
        )
    return digest


def matched_keyword(chunk: dict) -> str | None:
    fields = [chunk["page_title"], chunk["section_heading"], *chunk["categories"]]
    for kw, pattern in _PATTERNS:
        if any(pattern.search(f) for f in fields):
            return kw
    return None


def draw_sample(chunks: list[dict]) -> tuple[list[dict], dict]:
    """Returns (sample records, stats). Deterministic: fixed seed, and
    pool order comes from the (deterministic) chunks.jsonl order."""
    frame = [
        c for c in chunks
        if c["label_provenance"] is None and not c["is_speculation"]
    ]
    cluster_pool: list[tuple[dict, str]] = []
    other_pool: list[dict] = []
    for c in frame:
        kw = matched_keyword(c)
        if kw:
            cluster_pool.append((c, kw))
        else:
            other_pool.append(c)

    rng = random.Random(SEED)
    if len(cluster_pool) >= CLUSTER_TARGET:
        cluster_drawn = rng.sample(cluster_pool, CLUSTER_TARGET)
    else:
        cluster_drawn = list(cluster_pool)
    shortfall = CLUSTER_TARGET - len(cluster_drawn)
    random_target = SAMPLE_SIZE - len(cluster_drawn)  # backfill lands here
    random_drawn = rng.sample(other_pool, min(random_target, len(other_pool)))

    records = sorted(
        (
            {"chunk_id": c["chunk_id"], "stratum": "cluster", "matched_keyword": kw}
            for c, kw in cluster_drawn
        ),
        key=lambda r: r["chunk_id"],
    ) + sorted(
        ({"chunk_id": c["chunk_id"], "stratum": "random"} for c in random_drawn),
        key=lambda r: r["chunk_id"],
    )

    keyword_hits: dict[str, int] = {}
    for _, kw in cluster_pool:
        keyword_hits[kw] = keyword_hits.get(kw, 0) + 1
    stats = {
        "frame_size": len(frame),
        "cluster_pool": len(cluster_pool),
        "keyword_hits": {kw: keyword_hits[kw] for kw in CLUSTER_KEYWORDS if kw in keyword_hits},
        "cluster_drawn": len(cluster_drawn),
        "random_drawn": len(random_drawn),
        "shortfall_backfilled": max(shortfall, 0),
    }

    # self-checks: one record per id, all in frame, sizes as specified
    ids = [r["chunk_id"] for r in records]
    frame_ids = {c["chunk_id"] for c in frame}
    assert len(ids) == len(set(ids)), "duplicate chunk_ids in sample"
    assert set(ids) <= frame_ids, "sampled chunk outside the frame"
    assert len(records) == min(SAMPLE_SIZE, len(frame)), "wrong sample size"
    return records, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Draw the adversarial validation sample (D13).")
    parser.add_argument("--input", type=Path, default=Path("data/chunks.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/adversarial_sample.jsonl"))
    args = parser.parse_args(argv)

    verify_frozen(args.input)
    with args.input.open(encoding="utf-8") as f:
        chunks = [json.loads(line) for line in f if line.strip()]

    records, stats = draw_sample(chunks)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
        encoding="utf-8",
    )

    print(f"frame: {stats['frame_size']} chunks (null provenance, non-speculation)")
    print(f"cluster pool: {stats['cluster_pool']} chunks; per-keyword (first match wins):")
    for kw, n in stats["keyword_hits"].items():
        print(f"  {kw:15} {n}")
    print(
        f"drawn: {stats['cluster_drawn']} cluster + {stats['random_drawn']} random "
        f"= {stats['cluster_drawn'] + stats['random_drawn']}"
    )
    if stats["shortfall_backfilled"]:
        print(
            f"NOTE: cluster stratum underfilled by {stats['shortfall_backfilled']} "
            "— backfilled from the random stratum (finding, not silently fixed)"
        )
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

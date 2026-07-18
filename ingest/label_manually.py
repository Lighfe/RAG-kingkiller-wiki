"""Blind manual-labeling CLI for the adversarial sample (D13).

Deliberately dumb: shows chunk text, records keystrokes. No model
calls, no label suggestions, no stratum shown — labeling is blind.
Chunks arrive in a fixed-seed randomized order so cluster chunks don't
cluster. Appends to ``data/manual_labels.jsonl`` (chunk_ids + labels
only, no text — the file is committed); resumable, last record per
chunk_id wins, so "back" simply appends a corrected record.

Run: ``uv run python -m ingest.label_manually``
Keys: 1 / 2 / 3 = book_level · u = unsure · b = back · q = save and quit
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from ingest.draw_sample import verify_frozen

SHUFFLE_SEED = 71119
VALID_LABELS = {"1": 1, "2": 2, "3": 3, "u": "u"}


def load_labels(path: Path) -> dict[str, dict]:
    """Last record per chunk_id wins (the file is an append-only log)."""
    labels: dict[str, dict] = {}
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line)
                    labels[rec["chunk_id"]] = rec
    return labels


def display_order(sample_ids: list[str]) -> list[str]:
    ordered = list(sample_ids)
    random.Random(SHUFFLE_SEED).shuffle(ordered)
    return ordered


def _fmt_elapsed(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def run_session(
    order: list[str],
    chunks_by_id: dict[str, dict],
    labels_path: Path,
    input_fn=input,
    print_fn=print,
    clock=time.monotonic,
    now_fn=lambda: datetime.now(timezone.utc),
) -> dict[str, dict]:
    done = load_labels(labels_path)
    todo = [cid for cid in order if cid not in done]
    total = len(order)
    session_start = clock()

    i = 0
    while i < len(todo):
        chunk = chunks_by_id[todo[i]]
        labeled_so_far = total - (len(todo) - i)
        print_fn("")
        print_fn(f"[{labeled_so_far + 1}/{total} · elapsed {_fmt_elapsed(clock() - session_start)}]")
        print_fn("")
        heading = chunk["section_heading"]
        title = chunk["page_title"] + (f" § {heading}" if heading else "")
        print_fn(f"{title}   ({chunk['chunk_type']})")
        print_fn(chunk["page_url"])
        print_fn("")
        print_fn(chunk["text"])
        print_fn("")

        t0 = clock()
        while True:
            key = input_fn("[1/2/3 = book level · u = unsure · b = back · q = save and quit] > ").strip().lower()
            if key in VALID_LABELS or key in ("b", "q"):
                break
            print_fn("unrecognized key")

        if key == "q":
            print_fn("saved — resume anytime; already-labeled chunks are skipped")
            break
        if key == "b":
            if i == 0:
                print_fn("nothing to go back to in this session")
            else:
                i -= 1
            continue

        record = {
            "chunk_id": chunk["chunk_id"],
            "manual_book_level": VALID_LABELS[key],
            "seconds_spent": round(clock() - t0, 1),
            "timestamp": now_fn().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        with labels_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        i += 1

    return load_labels(labels_path)


def print_summary(labels: dict[str, dict], sample: list[dict], print_fn=print) -> None:
    stratum_by_id = {r["chunk_id"]: r["stratum"] for r in sample}
    counts: dict[str, int] = {}
    per_stratum: dict[str, dict[str, int]] = {}
    for cid, rec in labels.items():
        label = str(rec["manual_book_level"])
        counts[label] = counts.get(label, 0) + 1
        stratum = stratum_by_id.get(cid, "?")
        per_stratum.setdefault(stratum, {})
        per_stratum[stratum][label] = per_stratum[stratum].get(label, 0) + 1

    print_fn("")
    print_fn(f"== summary: {len(labels)}/{len(sample)} labeled ==")
    for label in ("1", "2", "3", "u"):
        if label in counts:
            print_fn(f"  level {label}: {counts[label]}")
    for stratum in sorted(per_stratum):
        parts = ", ".join(f"{k}: {v}" for k, v in sorted(per_stratum[stratum].items()))
        print_fn(f"  {stratum}: {parts}")
    total_s = sum(r["seconds_spent"] for r in labels.values())
    print_fn(f"  total labeling time: {_fmt_elapsed(total_s)}")
    unsure = sorted(cid for cid, r in labels.items() if r["manual_book_level"] == "u")
    if unsure:
        print_fn(f"  unsure ({len(unsure)}): {', '.join(unsure)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Blind manual labeling of the adversarial sample.")
    parser.add_argument("--chunks", type=Path, default=Path("data/chunks.jsonl"))
    parser.add_argument("--sample", type=Path, default=Path("data/adversarial_sample.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/manual_labels.jsonl"))
    args = parser.parse_args(argv)

    verify_frozen(args.chunks)
    with args.chunks.open(encoding="utf-8") as f:
        chunks_by_id = {c["chunk_id"]: c for c in map(json.loads, filter(str.strip, f))}
    with args.sample.open(encoding="utf-8") as f:
        sample = [json.loads(line) for line in f if line.strip()]

    order = display_order([r["chunk_id"] for r in sample])
    labels = run_session(order, chunks_by_id, args.output)
    print_summary(labels, sample)
    return 0


if __name__ == "__main__":
    sys.exit(main())

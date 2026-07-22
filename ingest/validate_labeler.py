"""Labeler validation gate (D13) - gold + adversarial, pre-registered thresholds.

Runs ingest.label_llm blind against two known-label sets and reports
whether the pre-registered acceptance gate (book-2 recall >= 0.80 on the
adversarial set, accuracy >= 0.90 on the gold chapter set) passes. This
gate must pass before a full labeling pass is authorized (D13); it makes
the only live API calls allowed outside of Part 3's --dry-run.

Run: ``uv run python -m ingest.validate_labeler``
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from pathlib import Path

from ingest.draw_sample import verify_frozen
from ingest.label_llm import label_chunks

log = logging.getLogger(__name__)

Z_95 = 1.96


def load_chunks(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def gold_chunks(chunks: list[dict]) -> list[dict]:
    return [c for c in chunks if c["label_provenance"] == "gold"]


def adversarial_chunks(chunks_by_id: dict[str, dict], sample: list[dict]) -> list[dict]:
    return [chunks_by_id[r["chunk_id"]] for r in sample]


def load_manual_labels(path: Path) -> dict[str, dict]:
    labels: dict[str, dict] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rec = json.loads(line)
                labels[rec["chunk_id"]] = rec
    return labels


# -- metrics ------------------------------------------------------------------


def wilson_interval(k: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score CI for a binomial proportion k/n (small-n safe)."""
    if n == 0:
        return (0.0, 0.0)
    phat = k / n
    denom = 1 + z**2 / n
    center = (phat + z**2 / (2 * n)) / denom
    margin = z * math.sqrt(phat * (1 - phat) / n + z**2 / (4 * n**2)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def accuracy(pairs: list[tuple[int, int]]) -> tuple[float, int, int]:
    """pairs: list of (actual, predicted). Returns (rate, correct, total)."""
    if not pairs:
        return (0.0, 0, 0)
    correct = sum(1 for actual, pred in pairs if actual == pred)
    return (correct / len(pairs), correct, len(pairs))


def book2_recall(pairs: list[tuple[int, int]]) -> tuple[float, int, int]:
    """Among actual==2 chunks, fraction NOT under-labeled as 1 (the
    dangerous spoiler-leak direction, dataset-notes SS4) - predicted 2 or 3
    both count as a "catch". Returns (rate, caught, total_actual_2)."""
    actual_2 = [pred for actual, pred in pairs if actual == 2]
    if not actual_2:
        return (0.0, 0, 0)
    caught = sum(1 for pred in actual_2 if pred >= 2)
    return (caught / len(actual_2), caught, len(actual_2))


def confusion_matrix(pairs: list[tuple[int, int]]) -> dict[int, dict[int, int]]:
    matrix: dict[int, dict[int, int]] = {a: {p: 0 for p in (1, 2, 3)} for a in (1, 2, 3)}
    for actual, pred in pairs:
        matrix[actual][pred] += 1
    return matrix


def format_confusion_matrix(matrix: dict[int, dict[int, int]]) -> str:
    lines = ["         pred=1  pred=2  pred=3"]
    for actual in (1, 2, 3):
        row = matrix[actual]
        lines.append(f"actual={actual}   {row[1]:5d}   {row[2]:5d}   {row[3]:5d}")
    return "\n".join(lines)


def disagreements(records: list[dict]) -> list[dict]:
    """records: [{chunk_id, actual, predicted, rationale}, ...]."""
    return [r for r in records if r["actual"] != r["predicted"]]


# -- orchestration --------------------------------------------------------


def run_gold_validation(client, chunks: list[dict]) -> dict:
    gold = gold_chunks(chunks)
    labeled = label_chunks(client, gold)
    labeled_by_id = {r["chunk_id"]: r for r in labeled}
    chunk_by_id = {c["chunk_id"]: c for c in gold}

    records = [
        {
            "chunk_id": cid,
            "chunk_type": chunk_by_id[cid]["chunk_type"],
            "actual": chunk_by_id[cid]["book_level"],
            "predicted": labeled_by_id[cid]["book_level"],
            "rationale": labeled_by_id[cid]["rationale"],
        }
        for cid in labeled_by_id
    ]
    pairs = [(r["actual"], r["predicted"]) for r in records]
    # Infobox gold chunks carry the raw |book= code verbatim in the
    # harvested "book: TNOTW" param (D07) - the LLM can read it off
    # directly, so accuracy on that subset is not a real test of judgment.
    non_infobox_pairs = [(r["actual"], r["predicted"]) for r in records if r["chunk_type"] != "infobox"]

    return {
        "records": records,
        "n": len(records),
        "accuracy_all": accuracy(pairs),
        "accuracy_non_infobox": accuracy(non_infobox_pairs),
        "confusion_matrix": confusion_matrix(pairs),
        "disagreements": disagreements(records),
    }


def run_adversarial_validation(client, chunks_by_id: dict[str, dict], sample: list[dict], manual: dict[str, dict]) -> dict:
    usable_sample = [r for r in sample if manual.get(r["chunk_id"], {}).get("manual_book_level") != "u"]
    excluded_unsure = len(sample) - len(usable_sample)

    to_label = [chunks_by_id[r["chunk_id"]] for r in usable_sample]
    labeled = label_chunks(client, to_label)
    labeled_by_id = {r["chunk_id"]: r for r in labeled}

    records = [
        {
            "chunk_id": r["chunk_id"],
            "actual": manual[r["chunk_id"]]["manual_book_level"],
            "predicted": labeled_by_id[r["chunk_id"]]["book_level"],
            "rationale": labeled_by_id[r["chunk_id"]]["rationale"],
        }
        for r in usable_sample
    ]
    pairs = [(r["actual"], r["predicted"]) for r in records]

    return {
        "records": records,
        "n": len(records),
        "excluded_unsure": excluded_unsure,
        "accuracy": accuracy(pairs),
        "book2_recall": book2_recall(pairs),
        "confusion_matrix": confusion_matrix(pairs),
        "disagreements": disagreements(records),
    }


D13_RECALL_THRESHOLD = 0.80
D13_ACCURACY_THRESHOLD = 0.90


def print_report(gold_report: dict, adv_report: dict) -> bool:
    print("\n== Gold chapter set (blind re-derivation) ==")
    rate, correct, n = gold_report["accuracy_all"]
    print(f"accuracy (all chunk types): {correct}/{n} = {rate:.3f}")
    rate_ni, correct_ni, n_ni = gold_report["accuracy_non_infobox"]
    print(
        f"accuracy (prose+quote only, excludes infobox with verbatim |book= "
        f"code leakage): {correct_ni}/{n_ni} = {rate_ni:.3f}"
    )
    lo, hi = wilson_interval(correct, n)
    print(f"95% CI (all chunks): [{lo:.3f}, {hi:.3f}]  (small n)")
    print(format_confusion_matrix(gold_report["confusion_matrix"]))
    print(f"disagreements: {len(gold_report['disagreements'])}")
    for d in gold_report["disagreements"]:
        print(f"  {d['chunk_id']} ({d['chunk_type']}): gold={d['actual']} model={d['predicted']} - {d['rationale']}")

    print("\n== Adversarial sample (vs. blind manual labels) ==")
    print(f"excluded as 'u' (unsure): {adv_report['excluded_unsure']}")
    rate, hits, total = adv_report["book2_recall"]
    lo, hi = wilson_interval(hits, total)
    print(f"book-2 recall (predicted>=2 among manual==2): {hits}/{total} = {rate:.3f}  95% CI [{lo:.3f}, {hi:.3f}]")
    rate_acc, correct, n = adv_report["accuracy"]
    print(f"overall accuracy: {correct}/{n} = {rate_acc:.3f}")
    print(format_confusion_matrix(adv_report["confusion_matrix"]))
    print(f"disagreements: {len(adv_report['disagreements'])}")
    for d in adv_report["disagreements"]:
        print(f"  {d['chunk_id']}: manual={d['actual']} model={d['predicted']} - {d['rationale']}")

    recall_pass = adv_report["book2_recall"][0] >= D13_RECALL_THRESHOLD
    accuracy_pass = gold_report["accuracy_all"][0] >= D13_ACCURACY_THRESHOLD
    print("\n== D13 verdict ==")
    print(
        f"book-2 recall {adv_report['book2_recall'][0]:.3f} >= {D13_RECALL_THRESHOLD}: "
        f"{'PASS' if recall_pass else 'FAIL'}"
    )
    print(
        f"gold accuracy {gold_report['accuracy_all'][0]:.3f} >= {D13_ACCURACY_THRESHOLD}: "
        f"{'PASS' if accuracy_pass else 'FAIL'}"
    )
    print(f"note: small-n sample (gold n={gold_report['n']}, adversarial book-2 n={total}) - CIs are wide.")
    overall = recall_pass and accuracy_pass
    print(f"OVERALL: {'PASS' if overall else 'FAIL'} - {'full pass authorized to proceed' if overall else 'full pass NOT authorized'}")
    return overall


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the LLM labeler against gold + adversarial sets (D13).")
    parser.add_argument("--chunks-path", type=Path, default=Path("data/chunks.jsonl"))
    parser.add_argument("--sample-path", type=Path, default=Path("data/adversarial_sample.jsonl"))
    parser.add_argument("--manual-labels-path", type=Path, default=Path("data/manual_labels.jsonl"))
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    from dotenv import load_dotenv
    load_dotenv()
    from openai import OpenAI
    client = OpenAI()

    verify_frozen(args.chunks_path)
    chunks = load_chunks(args.chunks_path)
    chunks_by_id = {c["chunk_id"]: c for c in chunks}
    sample = load_chunks(args.sample_path)
    manual = load_manual_labels(args.manual_labels_path)

    log.info("gold set: %d chunks", len(gold_chunks(chunks)))
    gold_report = run_gold_validation(client, chunks)

    log.info("adversarial set: %d chunks in sample", len(sample))
    adv_report = run_adversarial_validation(client, chunks_by_id, sample, manual)

    passed = print_report(gold_report, adv_report)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())

"""Data-quality checks for pipeline artifacts.

Covers the raw page cache (``data/pages.jsonl``) and the chunk set
(``data/chunks.jsonl``); the artifact kind is inferred from the file
name (override with ``--kind``). Runs automatically after full pipeline
runs; standalone: ``uv run python -m ingest.checks [path]``
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# Expected corpus shape per the 2026-07 label audit. The wiki is live:
# drift up to DRIFT_FAIL is a warning, beyond it a failure.
EXPECTED_PAGES = {0: 438, 112: 26}
DRIFT_FAIL = 0.05
STUB_CHARS = 200

BOOK_PARAM_RE = re.compile(r"\|\s*book", re.IGNORECASE)

log = logging.getLogger(__name__)


@dataclass
class Report:
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    infos: list[str] = field(default_factory=list)
    passes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    def lines(self) -> list[str]:
        out = [f"PASS  {m}" for m in self.passes]
        out += [f"INFO  {m}" for m in self.infos]
        out += [f"WARN  {m}" for m in self.warnings]
        out += [f"FAIL  {m}" for m in self.failures]
        return out


def check_pages(pages: list[dict]) -> Report:
    report = Report()
    _check_counts(pages, report)
    _check_duplicates(pages, report)
    _check_wikitext_present(pages, report)
    _check_ns112_is_raw_wikitext(pages, report)
    return report


def _check_counts(pages: list[dict], report: Report) -> None:
    counts: dict[int, int] = {}
    for p in pages:
        counts[p["ns"]] = counts.get(p["ns"], 0) + 1

    for ns, expected in EXPECTED_PAGES.items():
        actual = counts.pop(ns, 0)
        drift = abs(actual - expected) / expected
        msg = f"namespace {ns}: {actual} pages (expected ~{expected}, drift {drift:.1%})"
        if drift == 0:
            report.passes.append(msg)
        elif drift <= DRIFT_FAIL:
            report.warnings.append(msg + " — live wiki, tolerated")
        else:
            report.failures.append(msg + f" — beyond {DRIFT_FAIL:.0%} tolerance")

    for ns, n in sorted(counts.items()):
        report.failures.append(f"unexpected namespace {ns}: {n} pages")


def _check_duplicates(pages: list[dict], report: Report) -> None:
    seen: set[int] = set()
    dups: set[int] = set()
    for p in pages:
        if p["pageid"] in seen:
            dups.add(p["pageid"])
        seen.add(p["pageid"])
    if dups:
        report.failures.append(f"duplicate pageids: {sorted(dups)}")
    else:
        report.passes.append(f"no duplicate pageids ({len(seen)} unique)")


def _check_wikitext_present(pages: list[dict], report: Report) -> None:
    empty = [p["title"] for p in pages if not p["wikitext"].strip()]
    if empty:
        report.failures.append(f"{len(empty)} pages with empty wikitext: {empty[:10]}")
    else:
        report.passes.append("wikitext non-empty on every page")

    stubs = sum(1 for p in pages if len(p["wikitext"]) < STUB_CHARS)
    # Stubs are expected and kept; content-length filtering happens downstream.
    report.infos.append(f"{stubs} pages under {STUB_CHARS} chars (stubs — kept)")


def _check_ns112_is_raw_wikitext(pages: list[dict], report: Report) -> None:
    """Chapter pages must look like wikitext, not rendered HTML.

    The rendered page lies about the source: the infobox displays
    "The Name of the Wind" where the wikitext says ``|book = TNOTW``.
    If this fails, it is a fetch bug — fix the fetch, don't relax the check.
    """
    chapters = [p for p in pages if p["ns"] == 112]
    if not chapters:
        report.failures.append("no namespace-112 (Chapter:) pages present")
        return

    with_templates = sum(1 for p in chapters if "{{" in p["wikitext"])
    msg = f"{with_templates}/{len(chapters)} chapter pages contain {{{{ template markup"
    if with_templates * 2 > len(chapters):
        report.passes.append(msg)
    else:
        report.failures.append(msg + " — content looks rendered, not raw wikitext")

    if any(BOOK_PARAM_RE.search(p["wikitext"]) for p in chapters):
        report.passes.append("at least one chapter page carries a |book infobox param")
    else:
        report.failures.append(
            "no chapter page contains a |book param — content looks rendered, "
            "not raw wikitext"
        )


# --- chunk checks -------------------------------------------------------

CHUNK_FIELDS = {
    "chunk_id": str,
    "page_id": int,
    "page_title": str,
    "page_url": str,
    "ns": int,
    "revid": int,
    "section_heading": str,
    "chunk_type": str,
    "text": str,
    "content_hash": str,
    "book_level": (int, type(None)),
    "label_provenance": (str, type(None)),
    "citation_codes": list,
    "is_speculation": bool,
    "quality_flags": list,
    "categories": list,
    "word_count": int,
}
CHUNK_TYPES = {"prose", "infobox", "quote"}
PROVENANCES = {"gold", "citation", None}
MARKUP_PATTERNS = ("{{", "}}", "{|", "|}", "[[", "]]", "<!--", "<ref")
# Worst strip_code-residue pages per reports/exploration.md — must come
# out clean.
GARBAGE_PAGES = (
    "Chandrian (children's song)", "Maple, Maypole", "Lackless poem",
    "Tinker Tanner", "Viari",
)
EXPECTED_GOLD_PAGES = 26
CHUNK_WORD_BUCKETS = [(0, 50), (50, 100), (100, 230), (230, 380), (380, 500), (500, None)]


def label_coverage(chunks: list[dict]) -> dict:
    """% of chunks and of words per provenance tier, plus speculation.

    The null tier re-derives the dataset-notes "~81% needs LLM" figure
    at chunk level.
    """
    total_chunks = len(chunks) or 1
    total_words = sum(c["word_count"] for c in chunks) or 1
    tiers = {}
    for tier in ("gold", "citation", None):
        subset = [c for c in chunks if c["label_provenance"] == tier]
        tiers["null" if tier is None else tier] = {
            "chunks": len(subset),
            "chunks_pct": round(100 * len(subset) / total_chunks, 1),
            "words": sum(c["word_count"] for c in subset),
            "words_pct": round(100 * sum(c["word_count"] for c in subset) / total_words, 1),
        }
    spec = [c for c in chunks if c["is_speculation"]]
    return {
        "tiers": tiers,
        "speculation_chunks": len(spec),
        "speculation_pages": len({c["page_id"] for c in spec}),
    }


def word_histogram(chunks: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for lo, hi in CHUNK_WORD_BUCKETS:
        label = f"{lo}+" if hi is None else f"{lo}–{hi}"
        out[label] = sum(
            1 for c in chunks if c["word_count"] >= lo and (hi is None or c["word_count"] < hi)
        )
    return out


def check_chunks(chunks: list[dict]) -> Report:
    report = Report()
    _check_chunk_schema(chunks, report)
    _check_chunk_markup(chunks, report)
    _check_chunk_spots(chunks, report)
    _report_chunk_coverage(chunks, report)
    _report_chunk_distribution(chunks, report)
    return report


def _check_chunk_schema(chunks: list[dict], report: Report) -> None:
    bad: list[str] = []
    for c in chunks:
        if set(c) != set(CHUNK_FIELDS):
            bad.append(f"{c.get('chunk_id', '?')}: fields {sorted(set(c) ^ set(CHUNK_FIELDS))}")
        elif not all(isinstance(c[k], t) for k, t in CHUNK_FIELDS.items()):
            bad.append(f"{c['chunk_id']}: type mismatch")
        elif (
            c["chunk_type"] not in CHUNK_TYPES
            or c["label_provenance"] not in PROVENANCES
            or c["book_level"] not in (1, 2, 3, None)
            or not c["text"].strip()
            or c["word_count"] <= 0
        ):
            bad.append(f"{c['chunk_id']}: bad enum/empty value")
        elif c["content_hash"] != hashlib.sha256(c["text"].encode("utf-8")).hexdigest():
            bad.append(f"{c['chunk_id']}: content_hash does not match text")
    if bad:
        report.failures.append(f"{len(bad)} schema violations: {bad[:5]}")
    else:
        report.passes.append(f"schema + content hashes valid on all {len(chunks)} chunks")

    ids = Counter(c.get("chunk_id") for c in chunks)
    dups = [i for i, n in ids.items() if n > 1]
    if dups:
        report.failures.append(f"duplicate chunk_ids: {dups[:5]}")
    else:
        report.passes.append("chunk_ids unique")


def _check_chunk_markup(chunks: list[dict], report: Report) -> None:
    offenders = []
    for c in chunks:
        hit = next((p for p in MARKUP_PATTERNS if p in c["text"]), None)
        if hit:
            offenders.append(f"{c['chunk_id']} ({hit!r})")
    if offenders:
        report.failures.append(
            f"{len(offenders)} chunks contain leftover markup: {offenders[:10]}"
        )
    else:
        report.passes.append("no template/table/link markup in any chunk text")

    present = {c["page_title"] for c in chunks}
    missing = [t for t in GARBAGE_PAGES if t not in present]
    if missing:
        report.warnings.append(f"known garbage pages missing from chunks: {missing}")
    else:
        report.passes.append("all 5 known garbage pages chunked (and covered by markup check)")


def _check_chunk_spots(chunks: list[dict], report: Report) -> None:
    kvothe = [c for c in chunks if c["page_title"] == "Kvothe" and c["chunk_type"] == "infobox"]
    if kvothe:
        report.passes.append("Kvothe has an infobox chunk (from {{Character}})")
    else:
        report.failures.append("no infobox chunk for Kvothe — structural detection broke")

    currency = [
        c for c in chunks
        if c["page_title"] == "Cealdish Currency" and c["chunk_type"] == "quote"
    ]
    if currency:
        report.passes.append("Cealdish Currency has ≥1 quote chunk")
    else:
        report.failures.append("no quote chunk for Cealdish Currency")

    ns112 = [c for c in chunks if c["ns"] == 112]
    not_gold = [c["chunk_id"] for c in ns112 if c["label_provenance"] != "gold"]
    if not_gold:
        report.failures.append(f"{len(not_gold)} ns-112 chunks not gold-labeled: {not_gold[:5]}")
    elif ns112:
        report.passes.append(f"all {len(ns112)} ns-112 chunks are gold-labeled")
    else:
        report.failures.append("no ns-112 chunks at all")

    gold_pages = len({c["page_id"] for c in ns112})
    drift = abs(gold_pages - EXPECTED_GOLD_PAGES) / EXPECTED_GOLD_PAGES
    msg = f"{gold_pages} gold (ns-112) pages (expected ~{EXPECTED_GOLD_PAGES})"
    if drift == 0:
        report.passes.append(msg)
    elif drift <= DRIFT_FAIL:
        report.warnings.append(msg + " — within tolerance (skeleton pages get dropped)")
    else:
        report.failures.append(msg + f" — beyond {DRIFT_FAIL:.0%} tolerance")


def _report_chunk_coverage(chunks: list[dict], report: Report) -> None:
    cov = label_coverage(chunks)
    for tier, s in cov["tiers"].items():
        report.infos.append(
            f"label coverage — {tier}: {s['chunks']} chunks ({s['chunks_pct']}%), "
            f"{s['words']} words ({s['words_pct']}%)"
        )
    report.infos.append(
        f"needs LLM pass (null tier): {cov['tiers']['null']['words_pct']}% of words "
        "— compare dataset-notes' ~81% estimate"
    )
    report.infos.append(
        f"speculation: {cov['speculation_chunks']} chunks on {cov['speculation_pages']} pages"
    )


def _report_chunk_distribution(chunks: list[dict], report: Report) -> None:
    hist = ", ".join(f"{k}: {v}" for k, v in word_histogram(chunks).items())
    report.infos.append(f"{len(chunks)} chunks; word histogram: {hist}")

    split_sections = sum(
        1
        for (page, slug), n in Counter(
            (c["page_id"], c["chunk_id"].rsplit(":", 1)[0])
            for c in chunks
            if c["chunk_type"] == "prose"
        ).items()
        if n > 1
    )
    msg = f"{split_sections} sections were max-size split (exploration expected ~15–30)"
    if split_sections == 0:
        report.warnings.append(msg + " — splitter suspiciously idle")
    else:
        report.infos.append(msg)


def load_pages(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Data-quality checks for pipeline artifacts (pages or chunks)."
    )
    parser.add_argument(
        "path", nargs="?", type=Path, default=Path("data/pages.jsonl"),
        help="artifact to check (default: data/pages.jsonl)",
    )
    parser.add_argument(
        "--kind", choices=("pages", "chunks"), default=None,
        help="artifact kind (default: inferred from file name)",
    )
    args = parser.parse_args(argv)

    if not args.path.exists():
        print(f"FAIL  {args.path} does not exist", file=sys.stderr)
        return 1

    kind = args.kind or ("chunks" if "chunk" in args.path.name else "pages")
    records = load_pages(args.path)
    report = check_chunks(records) if kind == "chunks" else check_pages(records)
    print(f"== data-quality report ({kind}): {args.path} ==")
    for line in report.lines():
        print(line)
    verdict = "OK" if report.ok else "FAILED"
    print(
        f"result: {verdict} "
        f"({len(report.failures)} failures, {len(report.warnings)} warnings)"
    )
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())

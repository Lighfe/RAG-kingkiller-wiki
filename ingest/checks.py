"""Data-quality checks for the raw page cache (``data/pages.jsonl``).

Runs automatically after a full fetch; standalone:
``uv run python -m ingest.checks [data/pages.jsonl]``
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
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


def load_pages(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Data-quality checks for a fetched pages.jsonl."
    )
    parser.add_argument(
        "pages", nargs="?", type=Path, default=Path("data/pages.jsonl"),
        help="path to pages.jsonl (default: data/pages.jsonl)",
    )
    args = parser.parse_args(argv)

    if not args.pages.exists():
        print(f"FAIL  {args.pages} does not exist", file=sys.stderr)
        return 1

    report = check_pages(load_pages(args.pages))
    print(f"== data-quality report: {args.pages} ==")
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

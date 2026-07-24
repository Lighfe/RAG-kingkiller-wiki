"""Task 6: entity co-mention graph for multi-hop question candidates.

Surfaces a ranked, filterable set of page-pair + chunk-pair candidates for
hand-picking the multi-hop/synthesis question set (D32/D33). Not a runtime
dependency: production retrieval never reads this file.

Stage A (page-to-page): parse each page's raw wikitext for [[...]]
wikilinks BEFORE strip_code() runs (D03 principle — strip_code() flattens
links to display text and discards the target), resolve link targets
against the known 464 page titles, and build the page-level link graph
(flagging bidirectional pairs as higher-confidence).

Stage B (chunk-level): for each Stage-A pair, in both directions, localize
the actual link occurrence(s) to a chunk via its display text, then
recover any further chunks mentioning the target's title as plain text
(word-boundary, not substring) — this is what a reader following the link
alone would miss, since only the first mention is typically wikilinked.

Redirect resolution (D36, amended by task 6b): pages.jsonl was fetched
with apfilterredir=nonredirects (ingest/fetch_pages.py), so no redirect
mapping exists locally at all — not even the list of redirect titles.
resolve_target()'s first three tiers are mechanical normalization only
(underscore/whitespace, MediaWiki first-letter capitalization, a casefold
fallback used only when it resolves uniquely) — never a semantic guess
(no honorific/article stripping, no fuzzy matching). A fourth tier accepts
a cached redirect map (data/redirects.json, built once by
ingest/fetch_redirects.py via a live, batched, polite MediaWiki
`redirects=1` lookup) — everything in THIS module still runs offline
against that cache; only fetch_redirects.py touches the network, and only
once. Whatever the cache doesn't cover is logged as unresolved for manual
review rather than silently dropped or guessed at (typos, true redlinks,
non-wiki references); see the --dry-run report.

Run:
    uv run python -m ingest.fetch_redirects          # one-time: cache the
                                                       # redirect map (task 6b)
    uv run python -m ingest.entity_graph --dry-run   # Stage A report only
    uv run python -m ingest.entity_graph             # full run, writes
                                                       # data/eval/entity_links.jsonl
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import mwparserfromhell as mwph

from ingest.fetch_pages import _write_atomic

TOOL_VERSION = "0.1"

# Non-content MediaWiki namespaces that show up as [[Prefix:...]] wikilink
# targets but are never entity pages. Category is harvested separately by
# the chunker (D03); the rest are wiki housekeeping. "Chapter" is NOT here
# — it's ns=112, a real content namespace in this corpus.
NAMESPACE_SKIP_PREFIXES = {
    "category", "category talk", "file", "image", "template", "template talk",
    "user", "user talk", "talk", "help", "mediawiki", "special", "portal",
    "forum", "board", "thread", "module",
}

# Interwiki prefixes observed in this corpus (wikipedia/wiktionary link
# templates) plus a conservative set of ISO 639-1 codes for other-language
# wiki interlinks (Fandom wikis commonly cross-link language editions).
INTERWIKI_PREFIXES = {"wikipedia", "wiktionary", "commons", "meta", "w"} | {
    "en", "es", "de", "fr", "pl", "pt", "it", "ru", "nl", "ja", "zh", "ko",
    "sv", "no", "fi", "da", "cs", "hu", "tr", "ar", "he", "uk", "el", "ro",
    "bg", "hr", "sr", "sk", "sl", "lt", "lv", "et", "vi", "th", "id", "ms",
    "fa", "hi",
}

# Coarse page "type" from categories, used only to cross-tabulate Stage-A
# pairs in the report (not part of the output schema) — surfaces
# type-diverse pairs (Character x Location x Magic) for hand-picking,
# not just same-category pairs. First match wins; best-effort/heuristic.
COARSE_TYPE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("Character", ("character",)),
    ("Location", ("location", "place", "cit", "kingdom", "region", "geograph", "town")),
    ("Magic", ("magic", "sympathy", "naming", "alchemy", "sygaldry", "artificing")),
    ("Group", ("group", "organi", "guild", "order", "faction")),
    ("Object", ("object", "item", "artifact")),
    ("Book/Chapter", ("chapter", "book")),
    ("Event", ("event", "war")),
]

log = logging.getLogger(__name__)


# -- Stage A: page-to-page link resolution --------------------------------


def _norm_ws(text: str) -> str:
    """MediaWiki underscore/space equivalence, collapsed whitespace."""
    return " ".join(text.replace("_", " ").split())


def _cap_first(text: str) -> str:
    """MediaWiki title normalization: first character is capitalized."""
    return text[0].upper() + text[1:] if text else text


def build_title_index(pages: list[dict]) -> tuple[dict[str, dict], dict[str, list[dict]]]:
    """Exact-title lookup, plus a casefold lookup (list — used only when
    it resolves to a single page, to avoid silently picking one of two
    same-cased-but-different titles, e.g. "Seth (farmer)"/"Seth (townsfolk)")."""
    exact: dict[str, dict] = {}
    casefold: dict[str, list[dict]] = defaultdict(list)
    for p in pages:
        exact[p["title"]] = p
        casefold[p["title"].casefold()].append(p)
    return exact, dict(casefold)


@dataclass
class LinkOccurrence:
    raw_target: str
    display: str


def extract_link_occurrences(wikitext: str) -> list[LinkOccurrence]:
    """Wikilinks in document order, parsed BEFORE strip_code() (D03)."""
    code = mwph.parse(wikitext)
    occurrences = []
    for link in code.filter_wikilinks():
        raw_target = str(link.title).strip()
        display = str(link.text).strip() if link.text is not None else raw_target
        occurrences.append(LinkOccurrence(raw_target, display))
    return occurrences


def classify_target(raw_target: str) -> tuple[str, str]:
    """(action, cleaned_target); action in {"skip", "candidate"}.

    Strips a #anchor suffix. Skips same-page anchors, and namespace/
    interwiki-prefixed targets that are never entity pages in this corpus.
    A leading colon (``[[:File:X]]``, ``[[:Category:X]]``) is MediaWiki
    syntax for "link to this page, don't trigger the namespace's special
    behavior" — it doesn't change what namespace the target is in, so it's
    stripped before the prefix check rather than left to fall through as
    an unresolved candidate (task 6b: found via a live redirect lookup
    reporting it "missing" instead of ever proposing a real target).
    """
    target = raw_target.split("#", 1)[0].strip().lstrip(":").strip()
    if not target:
        return "skip", target
    if ":" in target:
        prefix = target.split(":", 1)[0].strip().casefold()
        if prefix in NAMESPACE_SKIP_PREFIXES or prefix in INTERWIKI_PREFIXES:
            return "skip", target
    return "candidate", target


@dataclass
class Resolution:
    page: dict | None
    method: str | None  # "exact" | "normalized" | "casefold" | None


def resolve_target(
    target: str,
    exact: dict[str, dict],
    casefold: dict[str, list[dict]],
    redirects: dict[str, str] | None = None,
) -> Resolution:
    """Tiers, in order: exact -> case/underscore normalization -> unique
    casefold -> cached redirect map (task 6b, D36 amendment) -> unresolved.

    The first three are mechanical only — see module docstring. The
    redirect tier is the one semantic hop, but it's resolved offline
    against a map fetched once and cached (``data/redirects.json``,
    ``ingest/fetch_redirects.py``), never guessed at here.
    """
    if target in exact:
        return Resolution(exact[target], "exact")
    normalized = _cap_first(_norm_ws(target))
    if normalized in exact:
        return Resolution(exact[normalized], "normalized")
    matches = casefold.get(_norm_ws(target).casefold(), [])
    if len(matches) == 1:
        return Resolution(matches[0], "casefold")
    if redirects:
        redirect_target = redirects.get(_norm_ws(target))
        if redirect_target is not None and redirect_target in exact:
            return Resolution(exact[redirect_target], "redirect")
    return Resolution(None, None)


@dataclass
class StageAResult:
    # (source_page_id, target_page_id) -> [display_text, ...] in document order
    edges: dict[tuple[int, int], list[str]] = field(default_factory=dict)
    unresolved: Counter = field(default_factory=Counter)  # normalized target -> occurrence count
    unresolved_samples: dict[str, list[str]] = field(default_factory=dict)  # -> sample source titles
    resolution_methods: Counter = field(default_factory=Counter)
    skipped_namespace: int = 0
    skipped_selfanchor: int = 0
    self_links_skipped: int = 0


def stage_a(pages: list[dict], redirects: dict[str, str] | None = None) -> StageAResult:
    exact, casefold = build_title_index(pages)
    edges: dict[tuple[int, int], list[str]] = defaultdict(list)
    unresolved: Counter = Counter()
    unresolved_samples: dict[str, list[str]] = defaultdict(list)
    resolution_methods: Counter = Counter()
    skipped_namespace = 0
    skipped_selfanchor = 0
    self_links_skipped = 0

    for page in pages:
        for occ in extract_link_occurrences(page["wikitext"]):
            action, target = classify_target(occ.raw_target)
            if action == "skip":
                if target:
                    skipped_namespace += 1
                else:
                    skipped_selfanchor += 1
                continue

            res = resolve_target(target, exact, casefold, redirects)
            if res.page is None:
                key = _norm_ws(target)
                unresolved[key] += 1
                if len(unresolved_samples[key]) < 5:
                    unresolved_samples[key].append(page["title"])
                continue

            resolution_methods[res.method] += 1
            if res.page["pageid"] == page["pageid"]:
                self_links_skipped += 1
                continue
            edges[(page["pageid"], res.page["pageid"])].append(occ.display)

    return StageAResult(
        edges=dict(edges),
        unresolved=unresolved,
        unresolved_samples=dict(unresolved_samples),
        resolution_methods=resolution_methods,
        skipped_namespace=skipped_namespace,
        skipped_selfanchor=skipped_selfanchor,
        self_links_skipped=self_links_skipped,
    )


def pair_directions(edges: dict[tuple[int, int], list[str]]) -> dict[frozenset, set[tuple[int, int]]]:
    grouped: dict[frozenset, set[tuple[int, int]]] = defaultdict(set)
    for source, target in edges:
        grouped[frozenset((source, target))].add((source, target))
    return dict(grouped)


def pair_stats(edges: dict[tuple[int, int], list[str]]) -> dict:
    grouped = pair_directions(edges)
    bidirectional = sum(1 for dirs in grouped.values() if len(dirs) == 2)
    one_directional = len(grouped) - bidirectional
    return {
        "pairs_total": len(grouped),
        "pairs_bidirectional": bidirectional,
        "pairs_one_directional": one_directional,
    }


def coarse_type(categories: list[str]) -> str:
    cats_cf = [c.casefold() for c in categories]
    for label, keywords in COARSE_TYPE_KEYWORDS:
        if any(kw in c for c in cats_cf for kw in keywords):
            return label
    return "Other"


def types_by_page(chunks: list[dict]) -> dict[int, str]:
    cats_by_page: dict[int, list[str]] = {}
    for c in chunks:
        cats_by_page.setdefault(c["page_id"], c["categories"])
    return {pid: coarse_type(cats) for pid, cats in cats_by_page.items()}


def category_crosstab(edges: dict[tuple[int, int], list[str]], types: dict[int, str]) -> Counter:
    grouped = pair_directions(edges)
    tab: Counter = Counter()
    for pair in grouped:
        a, b = tuple(pair)
        key = tuple(sorted((types.get(a, "Other"), types.get(b, "Other"))))
        tab[key] += 1
    return tab


# -- Stage B: chunk-level localization -------------------------------------


def flatten_display(text: str) -> str:
    """Reduce a link's display text to plain words the same way chunk text
    was produced (strip_code()), so it can be searched for in chunk text."""
    return mwph.parse(text).strip_code().strip()


def word_boundary_pattern(phrase: str) -> re.Pattern:
    return re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE)


@dataclass
class LinkRow:
    chunk_id: str
    source_page_id: int
    target_page_id: int
    target_page_title: str
    direction: str  # "forward" (a literal wikilink exists this direction) | "reverse"
    match_type: str  # "link" (localized to the chunk holding the wikilink) | "text"


def _match_direction(
    source: int, target: int, link_displays: list[str], source_chunks: list[dict], target_title: str
) -> list[LinkRow]:
    """One Stage-A pair, one direction: localize each real wikilink
    occurrence to a chunk via its display text (chunk text shows display
    text, not the target — D03), then recover any further chunk mentioning
    the target's title in plain text, word-boundary matched."""
    rows: list[LinkRow] = []
    localized: set[str] = set()

    for display in link_displays:
        clean = flatten_display(display)
        if not clean:
            continue
        pattern = word_boundary_pattern(clean)
        chunk = next(
            (c for c in source_chunks if c["chunk_id"] not in localized and pattern.search(c["text"])),
            None,
        )
        if chunk is not None:
            localized.add(chunk["chunk_id"])
            rows.append(LinkRow(chunk["chunk_id"], source, target, target_title, "forward", "link"))

    title_pattern = word_boundary_pattern(target_title)
    direction = "forward" if link_displays else "reverse"
    for c in source_chunks:
        if c["chunk_id"] in localized:
            continue
        if title_pattern.search(c["text"]):
            localized.add(c["chunk_id"])
            rows.append(LinkRow(c["chunk_id"], source, target, target_title, direction, "text"))

    return rows


def stage_b(
    edges: dict[tuple[int, int], list[str]],
    chunks_by_page: dict[int, list[dict]],
    title_by_id: dict[int, str],
) -> list[LinkRow]:
    rows: list[LinkRow] = []
    for pair in pair_directions(edges):
        a, b = tuple(pair)
        for source, target in ((a, b), (b, a)):
            rows.extend(
                _match_direction(
                    source, target, edges.get((source, target), []),
                    chunks_by_page.get(source, []), title_by_id[target],
                )
            )
    return rows


def spot_check_sample(rows: list[LinkRow], n: int) -> list[LinkRow]:
    """Shortest-title text matches first — the false-positive risk the
    task flags (generic/short names matching unrelated prose)."""
    text_rows = [r for r in rows if r.match_type == "text"]
    return sorted(text_rows, key=lambda r: len(r.target_page_title))[:n]


# -- I/O + CLI ---------------------------------------------------------------


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def print_stage_a_report(result: StageAResult, crosstab: Counter, redirects_loaded: int = 0) -> None:
    stats = pair_stats(result.edges)
    edge_occurrences = sum(len(v) for v in result.edges.values())
    print(f"\n== Stage A: page-to-page link graph ==")
    print(f"directional edges (unique source->target pairs): {len(result.edges)}")
    print(f"  resolved link occurrences behind those edges: {edge_occurrences} "
          f"(+{result.self_links_skipped} self-link, resolved but excluded from the graph "
          f"= {edge_occurrences + result.self_links_skipped} total resolved — "
          f"the {edge_occurrences - len(result.edges)} gap vs. unique edges is repeat "
          f"same-pair links, e.g. a page linking the same target more than once; "
          f"D36 Step 3)")
    print(f"unordered pairs: {stats['pairs_total']}  "
          f"(bidirectional: {stats['pairs_bidirectional']}, "
          f"one-directional: {stats['pairs_one_directional']})")
    print(f"resolution methods: {dict(result.resolution_methods)}"
          + (f" (of which {redirects_loaded} cached redirects loaded)" if redirects_loaded else ""))
    print(f"skipped — namespace/interwiki prefix: {result.skipped_namespace}")
    print(f"skipped — self-page anchor only: {result.skipped_selfanchor}")
    print(f"skipped — self-links (page links to itself): {result.self_links_skipped}")

    total_unresolved = sum(result.unresolved.values())
    print(f"\nunresolved targets: {len(result.unresolved)} unique / {total_unresolved} occurrences "
          + ("(after redirect-map resolution, task 6b)" if redirects_loaded
             else "(likely redirects — not resolved offline yet, see module docstring / task 6b)"))
    for target, n in result.unresolved.most_common(25):
        samples = ", ".join(result.unresolved_samples.get(target, [])[:3])
        print(f"  {n:4d}  {target!r}  (seen on: {samples})")

    print(f"\ncategory cross-tab of pairs (coarse type, best-effort):")
    for (a, b), n in crosstab.most_common(20):
        print(f"  {n:4d}  {a} x {b}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Entity co-mention graph: page-link + chunk-text candidates for hand-picking multi-hop questions (task 6)."
    )
    parser.add_argument("--pages", type=Path, default=Path("data/pages.jsonl"))
    parser.add_argument("--chunks", type=Path, default=Path("data/chunks_labeled.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/eval/entity_links.jsonl"))
    parser.add_argument(
        "--redirects", type=Path, default=Path("data/redirects.json"),
        help="cached redirect map (task 6b, ingest/fetch_redirects.py); "
             "used as a resolution tier if present, skipped otherwise",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Stage A only: report pair/unresolved-target stats, write nothing",
    )
    parser.add_argument(
        "--spot-check", type=int, default=15, metavar="N",
        help="sample size for the Stage-B false-positive review (default: 15)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    for path in (args.pages, args.chunks):
        if not path.exists():
            sys.exit(f"error: {path} not found")

    redirects: dict[str, str] = {}
    if args.redirects.exists():
        redirects = json.loads(args.redirects.read_text(encoding="utf-8"))
        log.info("loaded %d cached redirects from %s", len(redirects), args.redirects)
    else:
        log.info(
            "%s not found — run `uv run python -m ingest.fetch_redirects` first "
            "for full redirect resolution (task 6b); continuing without it",
            args.redirects,
        )

    t0 = time.monotonic()
    pages = load_jsonl(args.pages)
    chunks = load_jsonl(args.chunks)

    result = stage_a(pages, redirects=redirects)
    types = types_by_page(chunks)
    crosstab = category_crosstab(result.edges, types)
    print_stage_a_report(result, crosstab, redirects_loaded=len(redirects))

    if args.dry_run:
        log.info("dry-run: stopping after Stage A (%.1fs)", time.monotonic() - t0)
        return 0

    title_by_id = {p["pageid"]: p["title"] for p in pages}
    chunks_by_page: dict[int, list[dict]] = defaultdict(list)
    for c in chunks:
        chunks_by_page[c["page_id"]].append(c)

    rows = stage_b(result.edges, dict(chunks_by_page), title_by_id)
    duration_s = time.monotonic() - t0

    match_type_counts = Counter(r.match_type for r in rows)
    direction_counts = Counter(r.direction for r in rows)
    print(f"\n== Stage B: chunk-level mentions ==")
    print(f"{len(rows)} rows — match_type {dict(match_type_counts)}, direction {dict(direction_counts)}")

    sample = spot_check_sample(rows, args.spot_check)
    print(f"\nfalse-positive spot check ({len(sample)} shortest-title text matches — eyeball these):")
    chunk_text_by_id = {c["chunk_id"]: c["text"] for c in chunks}
    for r in sample:
        snippet = chunk_text_by_id[r.chunk_id].replace("\n", " ")[:160]
        print(f"  {r.target_page_title!r} in {r.chunk_id}: {snippet}...")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    output_text = "".join(
        json.dumps(
            {
                "chunk_id": r.chunk_id,
                "source_page_id": r.source_page_id,
                "target_page_id": r.target_page_id,
                "target_page_title": r.target_page_title,
                "direction": r.direction,
                "match_type": r.match_type,
            },
            ensure_ascii=False,
        )
        + "\n"
        for r in rows
    )
    _write_atomic(args.output, output_text)

    manifest = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pages_input": str(args.pages),
        "chunks_input": str(args.chunks),
        "tool_version": TOOL_VERSION,
        "duration_s": round(duration_s, 1),
        "stage_a": {
            "directional_edges": len(result.edges),
            "resolved_link_occurrences": sum(len(v) for v in result.edges.values()),
            **pair_stats(result.edges),
            "resolution_methods": dict(result.resolution_methods),
            "redirects_cached_loaded": len(redirects),
            "unresolved_targets_unique": len(result.unresolved),
            "unresolved_targets_occurrences": sum(result.unresolved.values()),
            "skipped_namespace_or_interwiki": result.skipped_namespace,
            "skipped_self_or_anchor": result.skipped_selfanchor,
            "self_links_skipped": result.self_links_skipped,
        },
        "stage_b": {
            "rows_total": len(rows),
            "match_type_counts": dict(match_type_counts),
            "direction_counts": dict(direction_counts),
        },
        "category_crosstab": {f"{a} x {b}": n for (a, b), n in crosstab.items()},
    }
    _write_atomic(
        args.output.with_name(args.output.stem + "_manifest.json"),
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
    )
    log.info("wrote %d rows to %s (%.1fs)", len(rows), args.output, duration_s)
    return 0


if __name__ == "__main__":
    sys.exit(main())

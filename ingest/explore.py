"""Corpus exploration for chunking decisions — read-only analysis.

Reads the raw-wikitext cache (``data/pages.jsonl``) and writes
``reports/exploration.md`` plus ``reports/exploration_stats.json``:
template inventory & strip_code() behavior, section structure and
length distributions, ref behavior, and a garbage watch. Produces
recommendations only — no pipeline code lives here.

Run: ``uv run python -m ingest.explore [--input FILE] [--output DIR]``
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import mwparserfromhell as mwph

# Target chunk size 300–500 tokens ≈ 230–380 words.
WORDS_SPLIT_THRESHOLD = 500
WORDS_TINY_THRESHOLD = 50
NEAR_EMPTY_WORDS = 20
NONTRIVIAL_WIKITEXT_CHARS = 300

SECTION_BUCKETS = [(0, 50), (50, 100), (100, 230), (230, 380), (380, 500), (500, 1000), (1000, None)]
REF_BUCKETS = [(0, 1), (1, 2), (2, 3), (3, 6), (6, 11), (11, None)]

# Headings that plausibly mark speculative/non-canon content (case-insensitive).
SPECULATION_RE = re.compile(
    r"speculat|theor(y|ies)|trivia|predict|rumou?r|unconfirmed|mysteri|unanswered"
    r"|possib|spoiler|book three|doors of stone|fan[\s-]?art",
    re.IGNORECASE,
)

INFOBOX_RE = re.compile(r"infobox", re.IGNORECASE)
QUOTE_RE = re.compile(r"quot", re.IGNORECASE)

# Markup artifacts that should not survive strip_code().
RESIDUE_RE = re.compile(r"\{\{|\}\}|\{\||\|\}|\[\[|\]\]|<!--|\|\||^\s*\|", re.MULTILINE)


def percentile(values: list, q: float):
    if not values:
        return 0
    s = sorted(values)
    return s[min(int(q * len(s)), len(s) - 1)]


def histogram(values: list[int], buckets) -> dict[str, int]:
    out: dict[str, int] = {}
    for lo, hi in buckets:
        label = f"{lo}+" if hi is None else f"{lo}–{hi}"
        out[label] = sum(1 for v in values if v >= lo and (hi is None or v < hi))
    return out


def dist_stats(values: list[int]) -> dict:
    return {
        "n": len(values),
        "p50": percentile(values, 0.50),
        "p90": percentile(values, 0.90),
        "p99": percentile(values, 0.99),
        "max": max(values) if values else 0,
    }


def words(text: str) -> int:
    return len(text.split())


def norm_template_name(name: str) -> str:
    return name.replace("_", " ").strip()


def truncate(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rstrip() + " …[truncated]"


class PageAnalysis:
    """Everything extracted from one page in a single parse pass."""

    def __init__(self, record: dict):
        self.title = record["title"]
        self.ns = record["ns"]
        self.wikitext = record["wikitext"]
        self.code = mwph.parse(self.wikitext)
        self.stripped = self.code.strip_code()
        self.templates = self.code.filter_templates()
        self.sections = self._split_sections()

    def _split_sections(self) -> list[dict]:
        """Split on level-2/3 headings; the lede is the span before the first.

        Level-4+ headings stay inside their parent section — they are
        sub-structure, not chunk boundaries.
        """
        sections: list[dict] = []
        current: list = []
        heading = None  # None = lede
        level = None

        def flush():
            text = "".join(str(n) for n in current)
            sec_code = mwph.parse(text)
            stripped = sec_code.strip_code()
            tag_refs = [
                t for t in sec_code.filter_tags()
                if str(t.tag).strip().lower() == "ref"
            ]
            # this wiki cites mostly via a {{ref}} TEMPLATE, not <ref> tags
            tpl_refs = [
                t for t in sec_code.filter_templates()
                if str(t.name).strip().casefold() == "ref"
            ]
            sections.append(
                {
                    "heading": heading,
                    "level": level,
                    "words": words(stripped),
                    "tag_refs": len(tag_refs),
                    "tpl_refs": len(tpl_refs),
                }
            )

        for node in self.code.nodes:
            if isinstance(node, mwph.nodes.Heading) and node.level in (2, 3):
                flush()
                heading = node.title.strip_code().strip()
                level = node.level
                current = []
            else:
                current.append(node)
        flush()
        return sections


def load_pages(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                sys.exit(f"error: {path}:{i} is not valid JSON ({e}) — refusing to continue")
            missing = {"title", "ns", "wikitext"} - set(rec)
            if missing:
                sys.exit(f"error: {path}:{i} lacks fields {sorted(missing)} — refusing to continue")
            records.append(rec)
    if not records:
        sys.exit(f"error: {path} contains no records")
    return records


# --- analyses -----------------------------------------------------------


def template_inventory(pages: list[PageAnalysis]) -> dict:
    occurrences: Counter[str] = Counter()
    page_use: dict[str, set[str]] = defaultdict(set)
    display: dict[str, Counter] = defaultdict(Counter)
    example: dict[str, dict] = {}

    for page in pages:
        for tpl in page.templates:
            raw_name = norm_template_name(str(tpl.name))
            key = raw_name.casefold()
            occurrences[key] += 1
            page_use[key].add(page.title)
            display[key][raw_name] += 1
            if key not in example or len(str(tpl)) > len(example[key]["raw"]):
                example[key] = {"page": page.title, "raw": str(tpl)}

    inventory = []
    for key, occ in occurrences.most_common():
        name = display[key].most_common(1)[0][0]
        inventory.append(
            {
                "name": name,
                "pages": len(page_use[key]),
                "occurrences": occ,
                "is_infobox": bool(INFOBOX_RE.search(name)),
                "is_quote": bool(QUOTE_RE.search(name)),
            }
        )

    # examples: top 10 by occurrence + every infobox/quote-named template
    example_keys = [t["name"].casefold() for t in inventory[:10]]
    example_keys += [
        t["name"].casefold()
        for t in inventory
        if (t["is_infobox"] or t["is_quote"]) and t["name"].casefold() not in example_keys
    ]
    examples = []
    for key in example_keys:
        ex = example[key]
        stripped = mwph.parse(ex["raw"]).strip_code()
        name = display[key].most_common(1)[0][0]
        examples.append(
            {
                "name": name,
                "page": ex["page"],
                "raw": ex["raw"],
                "stripped": stripped,
            }
        )

    # {{ref}}'s first positional param is a book code — the labeling signal
    ref_first_params: Counter[str] = Counter()
    for page in pages:
        for tpl in page.templates:
            if str(tpl.name).strip().casefold() == "ref" and tpl.params:
                ref_first_params[str(tpl.params[0].value).strip()] += 1

    return {
        "inventory": inventory,
        "examples": examples,
        "ref_first_params": dict(ref_first_params.most_common(10)),
    }


def section_structure(pages: list[PageAnalysis]) -> dict:
    heading_occ: Counter[str] = Counter()
    heading_pages: dict[str, set[str]] = defaultdict(set)
    heading_display: dict[str, Counter] = defaultdict(Counter)
    heading_levels: dict[str, Counter] = defaultdict(Counter)

    section_words_all: list[int] = []
    section_words_ns: dict[int, list[int]] = defaultdict(list)
    lede_words: list[int] = []
    lede_only_pages: list[str] = []

    for page in pages:
        for sec in page.sections:
            if sec["heading"] is None:
                lede_words.append(sec["words"])
                if len(page.sections) == 1:
                    lede_only_pages.append(page.title)
                continue
            key = sec["heading"].casefold()
            heading_occ[key] += 1
            heading_pages[key].add(page.title)
            heading_display[key][sec["heading"]] += 1
            heading_levels[key][sec["level"]] += 1
            section_words_all.append(sec["words"])
            section_words_ns[page.ns].append(sec["words"])

    inventory = [
        {
            "heading": heading_display[key].most_common(1)[0][0],
            "levels": dict(heading_levels[key]),
            "occurrences": occ,
            "pages": len(heading_pages[key]),
            "is_speculative": bool(SPECULATION_RE.search(key)),
        }
        for key, occ in heading_occ.most_common()
    ]
    speculative = [h for h in inventory if h["is_speculative"]]

    return {
        "heading_inventory": inventory,
        "speculative_headings": speculative,
        "speculative_pages_total": len(
            set().union(*(heading_pages[h["heading"].casefold()] for h in speculative))
            if speculative else set()
        ),
        "section_words": {
            "overall": dist_stats(section_words_all)
            | {"histogram": histogram(section_words_all, SECTION_BUCKETS)},
            "ns0": dist_stats(section_words_ns[0])
            | {"histogram": histogram(section_words_ns[0], SECTION_BUCKETS)},
            "ns112": dist_stats(section_words_ns[112])
            | {"histogram": histogram(section_words_ns[112], SECTION_BUCKETS)},
        },
        "sections_over_split_threshold": sum(
            1 for w in section_words_all if w > WORDS_SPLIT_THRESHOLD
        ),
        "sections_under_tiny_threshold": sum(
            1 for w in section_words_all if w < WORDS_TINY_THRESHOLD
        ),
        "lede": dist_stats(lede_words) | {"histogram": histogram(lede_words, SECTION_BUCKETS)},
        "lede_only_pages": len(lede_only_pages),
        "lede_only_examples": lede_only_pages[:10],
    }


def ref_behavior(pages: list[PageAnalysis]) -> dict:
    refs_per_section: list[int] = []  # tag refs + {{ref}} templates combined
    with_tag_ref = 0
    with_tpl_ref = 0
    with_any_ref = 0
    total_sections = 0
    ref_contents_total = 0
    ref_contents_survived = 0
    example = None

    for page in pages:
        for sec in page.sections:
            total_sections += 1
            refs_per_section.append(sec["tag_refs"] + sec["tpl_refs"])
            with_tag_ref += bool(sec["tag_refs"])
            with_tpl_ref += bool(sec["tpl_refs"])
            with_any_ref += bool(sec["tag_refs"] or sec["tpl_refs"])
        for tag in page.code.filter_tags():
            if str(tag.tag).strip().lower() != "ref" or tag.contents is None:
                continue
            plain = mwph.parse(str(tag.contents)).strip_code().strip()
            if len(plain) < 5:
                continue
            ref_contents_total += 1
            if plain in page.stripped:
                ref_contents_survived += 1
            if example is None:
                example = {
                    "page": page.title,
                    "raw": str(tag),
                    "stripped_result": mwph.parse(str(tag)).strip_code(),
                }

    def pct(n: int) -> float:
        return round(100 * n / total_sections, 1)

    return {
        "total_sections": total_sections,
        "sections_with_tag_ref_pct": pct(with_tag_ref),
        "sections_with_tpl_ref_pct": pct(with_tpl_ref),
        "sections_with_any_ref": with_any_ref,
        "sections_with_any_ref_pct": pct(with_any_ref),
        "refs_per_section_histogram": histogram(refs_per_section, REF_BUCKETS),
        "refs_per_section": dist_stats(refs_per_section),
        "ref_contents_total": ref_contents_total,
        "ref_contents_survived_strip": ref_contents_survived,
        "tag_ref_contents_survive": ref_contents_total > 0
        and ref_contents_survived / ref_contents_total > 0.5,
        "example": example,
    }


def garbage_watch(pages: list[PageAnalysis]) -> dict:
    scored = []
    near_empty = []
    category_leak_pages = 0
    for page in pages:
        if re.search(r"\bCategory:", page.stripped):
            category_leak_pages += 1
        matches = list(RESIDUE_RE.finditer(page.stripped))
        if matches:
            pos = matches[0].start()
            excerpt = page.stripped[max(0, pos - 80) : pos + 160]
            scored.append(
                {
                    "title": page.title,
                    "ns": page.ns,
                    "residue_count": len(matches),
                    "excerpt": excerpt,
                }
            )
        if (
            words(page.stripped) < NEAR_EMPTY_WORDS
            and len(page.wikitext) >= NONTRIVIAL_WIKITEXT_CHARS
        ):
            near_empty.append(
                {
                    "title": page.title,
                    "ns": page.ns,
                    "wikitext_chars": len(page.wikitext),
                    "stripped_words": words(page.stripped),
                }
            )
    scored.sort(key=lambda s: s["residue_count"], reverse=True)
    return {
        "pages_with_residue": len(scored),
        "worst": scored[:10],
        "near_empty": sorted(near_empty, key=lambda p: p["stripped_words"]),
        "category_leak_pages": category_leak_pages,
    }


# --- report -------------------------------------------------------------


def implications(tpl: dict, sec: dict, refs: dict, garbage: dict) -> list[str]:
    bullets = []

    infoboxes = [t for t in tpl["inventory"] if t["is_infobox"]]
    if infoboxes:
        names = ", ".join(f"{{{{{t['name']}}}}} ({t['pages']} pages)" for t in infoboxes)
        bullets.append(
            f"Infobox templates — {names} — strip to nothing with strip_code(), "
            "so their structured params (incl. `|book=` on chapter pages) are lost "
            "unless extracted BEFORE stripping. Decision to confirm: drop infoboxes "
            "from chunk text, harvest their params into chunk metadata in a "
            "pre-strip pass."
        )

    quotes = [t for t in tpl["inventory"] if t["is_quote"] and t["occurrences"] >= 5]
    for t in quotes:
        ex = next((e for e in tpl["examples"] if e["name"] == t["name"]), None)
        if ex is not None and not ex["stripped"].strip():
            bullets.append(
                f"{{{{{t['name']}}}}} ({t['pages']} pages, {t['occurrences']} uses) is "
                "stripped ENTIRELY — quote text is silently lost. Decision to confirm: "
                "extract quote text + attribution from the template params pre-strip "
                "and inline them as regular prose."
            )
        else:
            bullets.append(
                f"{{{{{t['name']}}}}} ({t['pages']} pages): strip_code keeps some of its "
                "text — verify what survives and whether attribution context is kept."
            )

    n = sec["section_words"]["overall"]["n"]
    over = sec["sections_over_split_threshold"]
    under = sec["sections_under_tiny_threshold"]
    bullets.append(
        f"Only {over} of {n} sections ({100 * over / n:.1f}%) exceed "
        f"{WORDS_SPLIT_THRESHOLD} words → max-size splitting is a rare fallback, "
        "not the main mechanism; section-aware chunking fits this corpus."
        if over / n < 0.05
        else f"{over} of {n} sections ({100 * over / n:.1f}%) exceed "
        f"{WORDS_SPLIT_THRESHOLD} words → max-size splitting is load-bearing, "
        "not an edge case."
    )
    bullets.append(
        f"{under} sections ({100 * under / n:.1f}%) are under {WORDS_TINY_THRESHOLD} "
        "words → confirms the tiny-section policy (keep as-is) matters; consider "
        "prepending page title + heading to every chunk so tiny chunks stay "
        "self-describing."
    )

    bullets.append(
        f"The lede (p50 {sec['lede']['p50']} words, p90 {sec['lede']['p90']}) is a "
        f"de-facto section, and {sec['lede_only_pages']} pages are lede-only → the "
        "chunker must treat pre-heading text as a first-class section."
    )

    spec_names = ", ".join(
        f"\"{h['heading']}\" ({h['pages']}p)" for h in sec["speculative_headings"]
    )
    bullets.append(
        f"Speculative-content headings found: {spec_names} — "
        f"{sec['speculative_pages_total']} pages total. Decision to confirm: "
        "is_speculation flag on chunks from these sections (case-insensitive match)."
    )

    survived = refs["ref_contents_survived_strip"]
    codes = ", ".join(f"{k}×{v}" for k, v in tpl["ref_first_params"].items())
    if refs["tag_ref_contents_survive"]:
        bullets.append(
            f"<ref> tag contents SURVIVE strip_code() ({survived}/"
            f"{refs['ref_contents_total']} ref bodies remain, often as bare URLs "
            "inlined mid-sentence) → remove ref tags pre-strip, harvesting their "
            "book signals first."
        )
    else:
        bullets.append(
            f"strip_code() removes <ref> content ({survived}/"
            f"{refs['ref_contents_total']} ref bodies survive) → ref-to-book "
            "signals must be harvested pre-strip."
        )
    bullets.append(
        f"The dominant citation mechanism is the {{{{ref}}}} TEMPLATE, whose first "
        f"param is a closed book-code vocabulary ({codes}) — dropped by strip_code, "
        "so harvest it pre-strip. "
        f"{refs['sections_with_any_ref_pct']}% of sections carry ≥1 citation "
        f"(tag or template; tags alone {refs['sections_with_tag_ref_pct']}%) → "
        "section-level ref-to-chunk association is feasible for that slice."
    )
    if garbage["category_leak_pages"]:
        bullets.append(
            f"[[Category:…]] links survive strip_code() as literal “Category:X” text "
            f"on {garbage['category_leak_pages']} pages → remove category links "
            "pre-strip and harvest them as chunk metadata (they are the planned "
            "retrieval-filter facets)."
        )

    if garbage["near_empty"]:
        bullets.append(
            f"{len(garbage['near_empty'])} pages strip to <{NEAR_EMPTY_WORDS} words "
            "despite non-trivial wikitext (pure-infobox pages) → apply a minimum "
            "stripped-length filter before chunking (consistent with the gold-seed "
            "skeleton filtering in the dataset notes)."
        )
    if garbage["pages_with_residue"]:
        bullets.append(
            f"{garbage['pages_with_residue']} pages leave markup residue after "
            "strip_code (tables, bare params, comments) → add a residue-cleanup "
            "regex pass after stripping; re-run this garbage watch to verify."
        )
    return bullets


def render_report(meta: dict, tpl: dict, sec: dict, refs: dict, garbage: dict, bullets: list[str]) -> str:
    L: list[str] = []
    add = L.append

    add("# Corpus exploration report")
    add("")
    add(
        f"Generated {meta['generated_at']} from `{meta['input']}` "
        f"({meta['pages']} pages: {meta['ns_counts']}). "
        f"Parser: mwparserfromhell {meta['mwparserfromhell']}."
    )
    add("")
    add(
        "> Excerpts below are from the [Kingkiller Chronicle Fandom wiki]"
        "(https://kingkiller.fandom.com), CC BY-SA 3.0."
    )
    add("")

    add("## 1. Template inventory")
    add("")
    total_occ = sum(t["occurrences"] for t in tpl["inventory"])
    add(f"{len(tpl['inventory'])} distinct templates, {total_occ} total occurrences.")
    add("")
    add("| template | pages | occurrences | class |")
    add("|---|--:|--:|---|")
    for t in tpl["inventory"][:30]:
        cls = "infobox" if t["is_infobox"] else ("quote" if t["is_quote"] else "")
        add(f"| `{{{{{t['name']}}}}}` | {t['pages']} | {t['occurrences']} | {cls} |")
    if len(tpl["inventory"]) > 30:
        add("")
        add(f"(long tail of {len(tpl['inventory']) - 30} more templates in the stats JSON)")
    add("")

    infoboxes = [t["name"] for t in tpl["inventory"] if t["is_infobox"]]
    quotes = [t["name"] for t in tpl["inventory"] if t["is_quote"]]
    add(f"**Infobox templates:** {', '.join(f'`{{{{{n}}}}}`' for n in infoboxes) or 'none found'}.")
    add(f"**Quote templates:** {', '.join(f'`{{{{{n}}}}}`' for n in quotes) or 'none found'}.")
    add("")
    codes = ", ".join(f"`{k}`×{v}" for k, v in tpl["ref_first_params"].items())
    add(
        f"**`{{{{ref}}}}` first-parameter values** (the book-code signal): {codes}."
    )
    add("")

    add("### strip_code() behavior — top templates and all infobox/quote templates")
    for ex in tpl["examples"]:
        add("")
        add(f"#### `{{{{{ex['name']}}}}}` — example from “{ex['page']}”")
        add("")
        add("Raw wikitext:")
        add("```wikitext")
        add(truncate(ex["raw"], 600))
        add("```")
        stripped = ex["stripped"].strip()
        add(f"strip_code() leaves: {'**nothing**' if not stripped else ''}")
        if stripped:
            add("```")
            add(truncate(stripped, 300))
            add("```")
    add("")

    add("## 2. Section structure")
    add("")
    add("### Heading inventory (level 2–3, case-insensitive groups)")
    add("")
    add("| heading | levels | occurrences | pages | speculative? |")
    add("|---|---|--:|--:|---|")
    for h in sec["heading_inventory"]:
        levels = ", ".join(f"h{lv}×{c}" for lv, c in sorted(h["levels"].items()))
        add(
            f"| {h['heading']} | {levels} | {h['occurrences']} | {h['pages']} "
            f"| {'**yes**' if h['is_speculative'] else ''} |"
        )
    add("")
    add(
        f"**Speculative headings** ({sec['speculative_pages_total']} pages total): "
        + (
            "; ".join(
                f"“{h['heading']}” on {h['pages']} pages"
                for h in sec["speculative_headings"]
            )
            or "none found"
        )
        + "."
    )
    add("")

    add("### Section length (words after strip_code, lede excluded)")
    add("")
    add("| scope | n | p50 | p90 | p99 | max |")
    add("|---|--:|--:|--:|--:|--:|")
    for label, key in [("all", "overall"), ("ns 0", "ns0"), ("ns 112", "ns112")]:
        s = sec["section_words"][key]
        add(f"| {label} | {s['n']} | {s['p50']} | {s['p90']} | {s['p99']} | {s['max']} |")
    add("")
    add("Histogram (all sections):")
    add("")
    add("| words | sections |")
    add("|---|--:|")
    for bucket, count in sec["section_words"]["overall"]["histogram"].items():
        add(f"| {bucket} | {count} |")
    add("")
    add(
        f"Sections over {WORDS_SPLIT_THRESHOLD} words (need max-size splitting): "
        f"**{sec['sections_over_split_threshold']}**. "
        f"Sections under {WORDS_TINY_THRESHOLD} words (kept as-is per tiny-section "
        f"policy): **{sec['sections_under_tiny_threshold']}**."
    )
    add("")
    add("### The lede (text before the first heading)")
    add("")
    s = sec["lede"]
    add(
        f"Words: p50 {s['p50']}, p90 {s['p90']}, p99 {s['p99']}, max {s['max']} "
        f"across {s['n']} pages. **{sec['lede_only_pages']} pages have no headings "
        "at all** (lede = whole page), e.g. "
        + ", ".join(f"“{t}”" for t in sec["lede_only_examples"][:5])
        + "."
    )
    add("")

    add("## 3. Refs and strip behavior")
    add("")
    verdict = (
        "**survive strip_code()** — ref bodies (often bare URLs) are inlined "
        "into the stripped text"
        if refs["tag_ref_contents_survive"]
        else "**are removed by strip_code()**"
    )
    add(
        f"Of {refs['ref_contents_total']} `<ref>` tags with non-trivial content, "
        f"{refs['ref_contents_survived_strip']} {verdict}. Note that most citations "
        "on this wiki use the `{{ref}}` template instead, which strip_code drops "
        "entirely (see section 1)."
    )
    if refs["example"]:
        add("")
        add(f"Example (from “{refs['example']['page']}”):")
        add("```wikitext")
        add(truncate(refs["example"]["raw"], 300))
        add("```")
        add(
            "strip_code() leaves: "
            + (f"`{refs['example']['stripped_result'].strip()}`" if refs["example"]["stripped_result"].strip() else "**nothing**")
        )
    add("")
    add(
        f"Citations per section (`<ref>` tags + `{{{{ref}}}}` templates): "
        f"p50 {refs['refs_per_section']['p50']}, "
        f"p90 {refs['refs_per_section']['p90']}, max {refs['refs_per_section']['max']}. "
        f"**{refs['sections_with_any_ref_pct']}% of sections have ≥1 citation** "
        f"({refs['sections_with_any_ref']}/{refs['total_sections']}; "
        f"`<ref>` tags alone {refs['sections_with_tag_ref_pct']}%, "
        f"`{{{{ref}}}}` templates alone {refs['sections_with_tpl_ref_pct']}%)."
    )
    add("")
    add("| citations/section | sections |")
    add("|---|--:|")
    for bucket, count in refs["refs_per_section_histogram"].items():
        add(f"| {bucket} | {count} |")
    add("")

    add("## 4. Garbage watch")
    add("")
    add(
        f"`[[Category:…]]` links survive strip_code() as literal text on "
        f"**{garbage['category_leak_pages']} pages**."
    )
    add("")
    add(
        f"{garbage['pages_with_residue']} pages retain markup residue after "
        "strip_code(). Worst 10 by residue count:"
    )
    add("")
    for g in garbage["worst"]:
        add(f"- **{g['title']}** (ns {g['ns']}, {g['residue_count']} artifacts)")
        add("  ```")
        add("  " + truncate(g["excerpt"].replace("\n", " ⏎ "), 220))
        add("  ```")
    add("")
    add("Near-empty after stripping despite non-trivial wikitext (pure-infobox pages):")
    add("")
    if garbage["near_empty"]:
        add("| page | ns | wikitext chars | stripped words |")
        add("|---|--:|--:|--:|")
        for p in garbage["near_empty"]:
            add(f"| {p['title']} | {p['ns']} | {p['wikitext_chars']} | {p['stripped_words']} |")
    else:
        add("None found.")
    add("")

    add("## 5. Implications for chunking")
    add("")
    add("Decisions to confirm (recommendations, not implementations):")
    add("")
    for b in bullets:
        add(f"- {b}")
    add("")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Explore the cached wiki corpus for chunking decisions.")
    parser.add_argument("--input", type=Path, default=Path("data/pages.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("reports"))
    args = parser.parse_args(argv)

    if not args.input.exists():
        sys.exit(f"error: {args.input} not found — run `uv run python -m ingest.fetch_pages` first")

    records = load_pages(args.input)
    pages = [PageAnalysis(r) for r in records]
    ns_counts = Counter(p.ns for p in pages)

    meta = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "input": str(args.input),
        "pages": len(pages),
        "ns_counts": {str(k): v for k, v in sorted(ns_counts.items())},
        "mwparserfromhell": mwph.__version__,
    }
    tpl = template_inventory(pages)
    sec = section_structure(pages)
    refs = ref_behavior(pages)
    garbage = garbage_watch(pages)
    bullets = implications(tpl, sec, refs, garbage)

    args.output.mkdir(parents=True, exist_ok=True)
    report_path = args.output / "exploration.md"
    stats_path = args.output / "exploration_stats.json"
    report_path.write_text(
        render_report(meta, tpl, sec, refs, garbage, bullets), encoding="utf-8"
    )
    stats = {
        "meta": meta,
        "templates": tpl,
        "sections": sec,
        "refs": refs,
        "garbage": garbage,
        "implications": bullets,
        "thresholds": {
            "split_words": WORDS_SPLIT_THRESHOLD,
            "tiny_words": WORDS_TINY_THRESHOLD,
            "near_empty_words": NEAR_EMPTY_WORDS,
        },
    }
    stats_path.write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {report_path} and {stats_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

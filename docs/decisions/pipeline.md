# Decision log — pipeline (D01–D16)

Part of the decision log, split by topic 2026-07-22. Index:
docs/decisions/index.md. Append-only. One entry per settled decision;
date, decision, one-line why. Corpus/licensing/labeling-signal
background: docs/kingkiller-dataset-notes.md.

**D01 · 2026-07-18 · Ingestion tool: plain Python script (no dlt).**
Rubric-equivalent to a framework; MediaWiki continuation pagination fits
requests-based code better; fewer deps in the reproducibility story.

**D02 · 2026-07-18 · Extraction: parse cached wikitext locally
(mwparserfromhell); no explaintext API pass.** Labeling signals and chunk
text must come from one representation so refs map to chunks positionally;
keeps all experiments offline against data/pages.jsonl.

**D03 · 2026-07-18 · Pre-strip harvesting (order matters):** infobox
params → {{ref}} codes + <ref> bodies (with positions) → {{quote}} text +
attribution → [[Category:…]] links → strip_code() → residue-cleanup regex
→ min-stripped-length filter. Exploration showed strip_code() drops all
templates (incl. quotes) and leaks <ref> bodies + category links as text.

**D04 · 2026-07-18 · Chunk unit: section-aware; lede is a first-class
section.** 127 pages are lede-only; only 15/1082 sections exceed 500
words. Tiny sections kept as-is; every chunk gets page title + section
heading prepended so short chunks stay self-describing.

**D05 · 2026-07-18 · Max chunk size 500 tokens; split at paragraph
boundaries.** Rare fallback by the data (p99 section ≈ 588 words).

**D06 · 2026-07-18 · Overlap: none across sections; ~50 tokens between
parts of a max-size split only.** Sections are label boundaries;
cross-section overlap would smear content across spoiler-gate boundaries.

**D07 · 2026-07-18 · Infoboxes: separate chunks (chunk_type=infobox),
params serialized as "key: value" lines, own book_level.** Detect
structurally (template w/ named params, no prose body); the 13 known
infobox names (incl. {{Character}}, missed by name-matching) are the
verification set. Chapter-infobox |book= harvested as gold page signal.

**D08 · 2026-07-18 · Quotes: included as chunk_type=quote chunks with
attribution.** Retrievable content (198 uses/176 pages) otherwise silently
lost. Licensing posture (verbatim excerpts, fair-use-style, mirrors the
wiki's own) documented in the writeup.

**D09 · 2026-07-18 · Speculation: boolean is_speculation, separate from
book_level; gate treats it as level 3 by default.** Matcher: headings
Speculation/Speculations + explicit spoiler headings (Spoilers about Book
Three; Book Three; Possible Seven Word Combinations; Spoilers for The
Doors of Stone) + {{conjecture}}-tagged pages. Trivia NOT flagged — it
flows through normal labeling, which catches book-specific content.

**D10 · 2026-07-18 · Chunk ID: positional (pageid:section-slug:ordinal)
as identity; content hash stored alongside for change detection.**
Monitoring records reference chunk IDs; IDs must survive wiki edits.

**D11 · 2026-07-18 · Labels are chunk-level; signal cascade: chapter
|book= (gold) → citation codes in-chunk, max wins ({{ref}} templates —
closed vocab TNOTW/TWMF/TLT/TSROST — and <ref> bodies) → LLM pass.**
No-citation chunks on citation-bearing pages fall to the LLM tier (no
page inheritance). Plain textual mentions are features, never labels.
Supersedes dataset-notes ref-tier sizing: the {{ref}} template (225
pages, 843 uses) is the dominant citation mechanism, not <ref> tags.

**D12 · 2026-07-18 · LLM labeler: gpt-5.4-mini, Pydantic structured
output (book_level, confidence, rationale); sees page title + section
heading + chunk text; prompt versioned in-repo; uncertain → conservative
default (highest level); --dry-run cost estimate before full pass.**

**D13 · 2026-07-18 · refined in D24 · Labeler acceptance (pre-registered): book-2 recall
≥ 0.80 on the adversarial set (with manual miss review), accuracy ≥ 0.90
on the gold chapter set.** Adversarial sample: ~50–100 chunks, stratified
~60% from audit-named book-2 clusters / ~40% random from no-signal +
mention tiers. Hand-labeling is done blind (no heuristic/LLM labels
shown). Small-n caveat reported with results.

**D14 · 2026-07-18 · Pipeline staging: artifact per stage
(pages.jsonl → chunks.jsonl → chunks_labeled.jsonl), each gitignored,
each with a run manifest.** Stages inspectable and independently
re-runnable; labeling experiments run against a frozen chunk set.

**D15 · 2026-07-19 · Maintenance banners ({{orphan}}, {{underlinked}})
match structural infobox detection; date param added to skipped set so
they emit no chunk.** Logged as detections, not silently dropped.

**D16 · 2026-07-19 · Single paragraphs > 380 words (6 chunks, max
1,109w) stay unsplit; paragraph is the smallest split unit.** Worst
cases are lists; arbitrary sub-paragraph cuts help nothing. Revisit at
retrieval eval if these chunks misbehave.

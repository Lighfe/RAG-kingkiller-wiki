# Task: corpus exploration for chunking decisions

Read-only analysis of the cached corpus. Produces a report; builds NO
pipeline code. Purpose: settle the open chunking parameters (template
handling, section-aware splitting, max chunk size) with data instead of
guesses.

Input: data/pages.jsonl (raw wikitext, one record per page — produced by
ingest/fetch_pages.py). Read docs/kingkiller-dataset-notes.md first (Corpus shape,
Ingestion gotchas).

## Deliverable

A single script `ingest/explore.py` (argparse: --input, --output) that
writes `reports/exploration.md` plus `reports/exploration_stats.json`.
Parse wikitext with mwparserfromhell (add via one `uv add` call,
pinned via lockfile).

## The report must answer

### 1. Template inventory
- All template names with frequency (pages using, total occurrences),
  sorted by frequency.
- For the top ~10 templates and EVERY template whose name suggests
  infobox or quote usage: one real example showing (a) raw wikitext,
  (b) what mwparserfromhell strip_code() leaves behind.
- Explicitly identify: which template(s) are the character/location
  infoboxes, and which are quote templates.

### 2. Section structure
- Full inventory of section headings (level-2 and level-3) with
  frequencies, grouped case-insensitively.
- Specifically list every heading that plausibly marks speculative
  content: variants of Speculation(s), Theor(y|ies), Trivia,
  Predictions, and anything else judgment suggests. Report per-variant
  page counts — this defines the is_speculation matcher.
- Section length distribution: words per section (histogram buckets +
  p50/p90/p99/max), overall and split by namespace (0 vs 112). Note:
  target chunk size is 300–500 tokens ≈ 230–380 words; report how many
  sections exceed ~500 words (need splitting) and how many are under
  ~50 words (tiny-section policy: keep as-is, per decision).
- How much text lives BEFORE the first heading (the lede) — distribution.
  The lede is a de-facto section and often the whole page for stubs.

### 3. Refs and strip behavior
- Confirm whether strip_code() removes <ref> content and what remains.
- Refs per section: distribution, and % of sections with ≥1 ref
  (feasibility check for section-level ref-to-chunk association).

### 4. Garbage watch
- The 10 worst pages by strip_code residue (leftover braces, pipes,
  bare template params, HTML comments, tables). Show short excerpts.
- Any page whose stripped text is empty or near-empty despite
  non-trivial wikitext (pure-infobox pages).

### 5. Summary section
End the report with "Implications for chunking": 5-10 bullet findings
phrased as decisions-to-confirm (e.g. "template X should be dropped
because...", "N sections need max-size splitting"). Recommendations,
not implementations.

## Hard rules
- Do not modify data/pages.jsonl or any pipeline code.
- Do not build the chunker, "just as a prototype" included.
- If pages.jsonl is missing/malformed, stop and report.
- Runtime sanity: full corpus is ~464 pages; this should run in seconds
  to low minutes. No LLM calls, no network.
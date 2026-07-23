# Task 6 — Entity co-mention graph for multi-hop question candidates

## Goal
Surface a small, ranked set of page-pair + chunk-pair candidates for
hand-picking the multi-hop/synthesis question set (D32/D33). Not a
runtime dependency — production retrieval never reads this file.

## Inputs
- data/pages.jsonl (cached wikitext — already fetched, read-only)
- data/chunks_labeled.jsonl (chunk_id, page_id, page_title, text,
  categories — read-only, NOT modified)

## Output
- data/eval/entity_links.jsonl — new, separate artifact. Not merged into
  chunks_labeled.jsonl (frozen per D29); joined by chunk_id at use time.
  One row per confirmed chunk-level mention:
  {chunk_id, source_page_id, target_page_id, target_page_title,
   direction, match_type: "link" | "text"}

## Method

### Stage A — page-to-page candidates (wikilinks)
- Parse each page's wikitext with mwparserfromhell; extract [[...]] link
  nodes with position, BEFORE strip_code() runs (same pre-strip principle
  as D03 — strip_code() will otherwise flatten links to display text and
  discard the target).
- Resolve link targets against the known 464 page titles. Explicit
  redirect-resolution step required: D01 excludes redirect pages from
  ingestion, but wikitext elsewhere may still link to a redirect title
  rather than the canonical one. Log unresolved targets for review rather
  than silently dropping them — this is the likely first bug, matching
  prior gotchas in this project (apnamespace, strip_code()).
- Build the page-level link graph. Flag bidirectional pairs (A→B and B→A)
  as higher-confidence than one-directional.
- Cross-reference with `categories` to keep type-diverse pairs visible
  (Character×Location×Magic), not just same-category pairs.

### Stage B — chunk-level localization (text matching)
- For each Stage-A candidate pair, take the target page's title plus any
  redirect/alias titles resolving to it.
- Word-boundary match (not substring) against every chunk's `text` on the
  source page. Record every matching chunk_id, both directions — this is
  what recovers mentions beyond the single first-occurrence chunk a link
  would catch.

## Non-goals / scope guardrails
- No runtime use — feeds only the one-time multi-hop question set
  (D32/D33: single fixed measurement, not compared across configs).
- Does not modify or re-open chunks_labeled.jsonl.
- Not full automated pair selection — surface ranked/filterable
  candidates (bidirectional + category-diverse first); ~15–30 final
  questions get hand-picked from this downstream, not generated wholesale.

## Open parameters — propose via dry-run, don't hand-specify
- Count of Stage-A pairs, split bidirectional vs. one-directional —
  report before Stage B runs.
- Redirect targets that fail to resolve — count and sample, for review.
- Stage-B false-positive spot check — sample a handful of text matches
  for short/generic-sounding entity names before trusting the full run.
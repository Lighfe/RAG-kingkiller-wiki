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

# Task 6b — Redirect resolution for entity graph (follow-up to task 6)

## Goal
Close the redirect gap flagged in D36: resolve the 120 unresolved Stage-A
targets via one cached API call, then re-run Stage A/B with the resolved
mapping. Extends the fetch-once-cache-forever pattern already used for
data/pages.jsonl — doesn't reopen the offline-afterward principle, closes
the one gap that wasn't actually covered by it.

## Inputs
- The 120 unique unresolved targets from the task-6 run (dry-run output /
  manifest)
- data/pages.jsonl, data/eval/entity_links.jsonl (read-only until the
  re-run step)

## Method

### Step 1 — fetch & cache the redirect map
- `action=query&titles={batch}&redirects=1&format=json`, batched ≤50
  titles per call (3 calls for 120 targets). Reuse the fetcher's existing
  session/User-Agent/rate-limit conventions — no new polling pattern.
- Persist to data/redirects.json: {from_title: to_title}, built only from
  titles the API actually reports under `redirects`. Titles that come
  back missing/unmodified are genuinely unresolved (typo, non-wiki
  reference, etc.) — keep those in the logged-unresolved list rather than
  assuming every original 120 was a redirect.
- One-time fetch. Everything downstream of this step runs offline against
  the cached file, same as the rest of the pipeline.

### Step 2 — re-run Stage A / Stage B
- Add the redirect map as a resolution tier after
  exact/case-normalization/casefold, before "unresolved."
- Re-run Stage B chunk-level localization only for newly-resolved pairs —
  no need to redo pairs that already resolved cleanly.
- Regenerate data/eval/entity_links.jsonl + manifest with updated counts.

### Step 3 — reconcile the open count question from review
- Task-6 reported 3,491 directional edges but a resolution breakdown
  summing to 4,318 (3,945 + 360 + 13). Confirm and state the cause
  (expected dedup of repeated same-pair links, presumably) in the
  manifest or D36 update rather than leaving the gap unexplained.

## Output
- data/redirects.json (new, cached, gitignored like other corpus
  artifacts)
- data/eval/entity_links.jsonl + manifest — updated in place
- D36 amended, not superseded (same decision, corrected scope): redirect
  resolution is closed via a cached one-time fetch, not accepted as an
  offline-only gap. State before/after unresolved counts.

## Non-goals
- No change to Stage A/B matching logic — same algorithm, better-populated
  resolution tier.
- Still no automatic pair ranking/selection (task 6's guardrail stands).

## Open parameters — propose via dry-run
- Post-fix unresolved count and sample. Expect it well under 120; report
  what's left and why (likely genuine typos or non-wiki references, not
  more redirects).

# Task 6c — Multi-hop candidate shortlist (rollup + filter)

## Goal
Roll up chunk-level entity_links.jsonl into page-pair candidates for
hand-picking the D32/D33 multi-hop question set. Output a ranked,
readable markdown shortlist — not automatic selection (task 6's
guardrail stands: surface candidates, don't pick them).

## Inputs (read-only)
- data/eval/entity_links.jsonl (chunk-level rows, task 6/6b)
- data/chunks_labeled.jsonl (page_title, ns, categories, text,
  book_level — frozen per D29, do not modify)
- The category-bucketing logic already in entity_graph.py that produced
  entity_links_manifest.json's category_crosstab. Reuse it directly
  (import or factor into a shared helper) — do not reimplement from raw
  `categories` text. This must reproduce the manifest's crosstab exactly
  when re-run over the same data, not approximately.

## Output
- data/eval/multihop_shortlist.md

## Method

### Rollup
Group entity_links.jsonl rows into unordered page-pairs
(source_page_id, target_page_id). Per pair, compute:
- bidirectional: both forward and reverse rows present with
  match_type=="link"
- num_chunks: count of distinct corroborating chunk_ids
- match_type mix: count of link vs. text
- category_pair: via the reused categorize() logic
- book_level(s) present on each side, for context only

### Filtering
- Hard-exclude Book/Chapter x Book/Chapter (chapter-nav previous/next
  structural pattern, established in task 6b — not a narrative
  relationship). This is the only exclusion; everything else is ranked,
  not decided.
- Split output into two sections: cross-category pairs, and
  same-category pairs listed after — deprioritized, not dropped (a
  same-category pair like Character x Character can still be a
  legitimate multi-hop candidate, e.g. two characters whose relationship
  spans both their pages).
- Sort within each bucket: bidirectional first, then by num_chunks.
- Flag known collision-prone short names (Ben, Iax, Tak, Jot, Eld, Tim —
  from task 6's spot check) inline. Flag, don't auto-include or
  auto-exclude.
- Cap at N candidates per category-pair bucket (default ~3) so the full
  shortlist lands around 50–80 total, to read down to a final 15–30 by
  hand.

### Output format
Markdown, grouped by category-pair bucket, cross-category first. Per
candidate: both page titles + category buckets, bidirectional/
short-name flags, chunk/match-type counts, and the actual chunk text
(cap a few chunks shown per pair, note "+N more" beyond that) — review
shouldn't require going back to the raw jsonl.

## Validation
Check against entity_links_manifest.json:
- total pairs found == stage_a.pairs_total (3,178)
- computed bidirectional-pair count == stage_a.pairs_bidirectional (782)
- computed category_crosstab == the manifest's, exactly, since the real
  categorize() logic is reused rather than reimplemented — any mismatch
  here is a bug to fix, not a caveat to document.

## Non-goals
- No automatic final selection.
- Read-only against entity_links.jsonl / chunks_labeled.jsonl — new
  output file only, nothing frozen gets touched.

## Tests
Cover: pair rollup/grouping, bidirectional detection, category-pair
labeling (exact match against manifest), Book/Chapter x Book/Chapter
exclusion, short-name flagging, top-per-bucket capping. Match this
repo's existing test-per-task convention.

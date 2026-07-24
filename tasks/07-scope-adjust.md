# Task 7 — Retire entity-graph multi-hop sourcing; scope one-shot vs. agentic-loop eval

Adjust the task number to wherever it actually lands in your sequence.

## Before making any edits
Read the current, real state of these — don't assume the text from prior
summaries in this project's chat history is exact:
- docs/decisions/evaluation.md (D17, D30–D36)
- docs/decisions/index.md
- Any task briefs referencing multi-hop sourcing (06-entity-graph or
  similar, plus any 6b/6c-equivalent)
- data/eval/multihop_shortlist.md and whatever script produced it
  (confirm which one actually ran — don't assume)
- project_instructions.md, kingkiller-dataset-notes.md — for stray
  "hop" terminology (see Part A, item 7)

## Part A — Documentation (append-only, matching existing convention)

1. **Do not delete or edit D30, D33, D34, D35 in place.** All four stand
   unchanged — none of this scope change touches single-hop eval design,
   the leakage-prompt comparison, trap+control pools, or multi-chunk
   composition.

2. **Add a superseded/refined-by note to D32's existing entry** (same
   style already used for "SUPERSEDED by D21" and "refined in D24") —
   don't rewrite D32's body, just point forward.

3. **New entry (next sequential D-number, read the file to confirm it —
   don't assume D37)** capturing:
   - D32's single-hop design (graded ground truth, NDCG@k/hit-rate@k)
     stands unchanged.
   - Multi-hop/synthesis questions (no fixed ground truth, judge-only)
     are deferred/out-of-scope, not deleted as a concept. If ever
     revisited: optional direction is synthetic Q&A generated from the
     complete Wikipedia articles for book 1/2, not entity-graph-driven
     page-pair sourcing.
   - Terminology fix: "hop" was overloaded between (a) a property of a
     question's ground truth — one correct chunk vs. no fixed correct
     chunk — and (b) a property of the retrieval mechanism — one
     retrieval pass vs. several actions in a loop. Keep "single-hop
     question" (still real, still backs D31/D32). Stop using "hop" for
     what the loop does — use "loop action" / "retrieval step" instead.

4. **New entry (next number after that)** for the one-shot vs.
   agentic-loop comparison design:
   - Baseline: existing one-shot retrieve-then-generate pipeline.
   - Loop: retrieve → self-assess sufficiency → act (same-page
     expansion / cross-page link-follow / query rephrase) → repeat, max
     hop cap + visited-chunk tracking (the link graph can cycle).
   - Runs on the existing single-hop question set (D31) — no new
     questions needed for this comparison.
   - Ablation: link-following only, rephrasing only, both, vs. baseline.
   - Two signals per question: (1) deterministic — did final context
     include the known correct chunk_id (reuses D31/D32 ground truth,
     no LLM call); (2) judge — are the final answer's claims grounded in
     what was actually retrieved (D17's shared harness). Comparing (1)
     vs. (2) on the same set is a judge-accuracy/calibration byproduct —
     note explicitly that this calibration is specific to
     grounded-in-single-chunk-context judging and doesn't automatically
     transfer to synthesis-style claim-traceability judging later.
   - Hard constraint, stated explicitly: every loop action re-applies
     `book_level <= clearance` identically to the initial retrieval
     filter. A loop is a second retrieval surface and must carry the
     same access-control guarantee as the first — no exceptions.
   - Cross-page hop selection is an LLM call conditioned on the live
     query, not a static highest-link-degree pick — specifically to
     avoid defaulting to the most-connected/most-mentioned entities
     regardless of relevance ("main character trap").

5. **Add a short pointer note to D36** (redirect resolution): its
   original stated purpose (supporting hand-picked multi-hop question
   sourcing) is superseded by item 4 above. The underlying artifact
   (entity_links.jsonl + redirect map) is retained and repurposed as the
   loop's runtime link-traversal index — no extraction work is
   invalidated, only its consumer changes.

6. **Update index.md**: add rows for the new entries; mark D32's row
   "refined by D3X", matching how D18/D21 and D13/D24 already appear.

7. **Sweep, don't silently rewrite**: grep project_instructions.md,
   kingkiller-dataset-notes.md, and task briefs for "multi-hop" /
   "single-hop" / "hop". Flag hits where item 3's disambiguation should
   apply, for review before editing.

## Part B — Repo cleanup

- Remove `data/eval/multihop_shortlist.md` and whichever rollup/filter
  script actually generated it (this may be the task-6c script, or the
  standalone one delivered earlier in chat — confirm, don't assume both
  exist). The decision log now carries the record of what was tried and
  why; these were single-purpose scratch artifacts for the abandoned
  approach, not a reusable pipeline stage or part of the frozen corpus —
  nothing is lost removing them.
- Leave entity_links.jsonl, redirects.json, and both manifests
  untouched — still valid, repurposed per item 5.
- Don't touch chunks_labeled.jsonl or any earlier frozen artifact.

## Non-goals
- Do not build the agentic loop itself here — documentation + scoping +
  cleanup only.
- Do not implement the Wikipedia-synthetic-QA idea — noted as optional/
  deferred only.

## Output
- Updated evaluation.md, index.md
- Shortlist script + output removed
- A short report of what the terminology sweep (item 7) found, for your
  review before any further edits
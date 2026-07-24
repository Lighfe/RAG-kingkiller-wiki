# Task 8 — Single-hop question set + embedding-model bake-off

Adjust the task number — read index.md for the actual next slot, don't
assume 8. Same for the next D-number in evaluation.md, don't assume D40.

## Part A — Decision log
Add a new entry documenting the grading-scheme decision (binary vs.
graded same-page-sibling scoring), using this reasoning verbatim/adapted,
not reinvented:

- Considered graded scoring (exact=2, same-page sibling=1 via a
  lexical/keyword-overlap "pertinent check," chunk_type=prose-only
  eligibility, boost weights on page_title/chunk_type held constant
  across compared configs) — motivated by wanting compatibility with
  later field-boost tuning without same-page credit mechanically
  favoring a page_title-boosted config.
- Dropped in favor of binary (exact chunk_id only): binary grading is
  structurally immune to that confound by construction (the target
  chunk is itself on the titled page, so page_title-driven signal
  toward it is legitimate, not exploited) — no mitigation layer needed.
  Also more reliable at this project's deliberately low/toy question
  volume, where a heuristic's false positives (same collision risk as
  the Ben/Iax/Tak matches from the entity graph) aren't averaged out.
- Consequence: NDCG not used this round (needs graded labels to earn
  its cost) — hit rate@k and MRR are the metrics.
- Graded same-page scoring is a documented, deferred upgrade path, not
  deleted — revisit if/when the eval needs finer resolution than binary
  gives.

## Part B — Question generation (D31)
- LLM-generates one question per eligible chunk from
  chunks_labeled.jsonl. Ground truth: binary, that chunk_id only
  (per Part A).
- Floor-stratified (not parity) across book_level and chunk_type, per
  D31's existing design. Low total volume — deliberately toy-scale, not
  statistical power — but propose a per-stratum floor of at least ~5 via
  dry-run; below that a stratum's rate isn't informative even loosely.
  Propose floors + resulting total from real pool sizes, for approval —
  don't hand-pick a number in the brief.
- Exclude the same structurally-uninformative chunk class as D24
  (chapter infoboxes, atmospheric sub-headings) from the source pool.

## Part C — Embedding-model bake-off (offline, Stage 1 — no Elasticsearch)
- Candidates: text-embedding-3-small, text-embedding-3-large (OpenAI
  API), bge-small-en-v1.5 (ONNX Runtime, local — reuse the course's
  download.py/embedder.py pattern rather than reimplementing).
- One-time setup: `uv add onnxruntime tokenizers numpy` in a single
  batched call.
- Embed all chunks + all generated questions under each candidate.
  Score hit rate@k and MRR against Part B's ground truth.
- Report per book_level and chunk_type stratum, not just aggregate
  (D31's standing principle), plus an overall number.
- Propose which k values to report via dry-run (e.g. a small standard
  sweep) rather than me fixing them here.

## Non-goals
- No Elasticsearch, no hybrid search, no reranking — Stage 2, later.
- No graded/pertinent-check machinery — deferred per Part A.
- Model selection itself isn't made here — this produces the numbers;
  picking the winner is a follow-up read of the output.

## Output
- data/eval/questions.jsonl (question, source chunk_id, book_level,
  chunk_type)
- data/eval/embedding_baking_off_results.{json,md} — per-stratum +
  overall hit rate@k / MRR per candidate model
- New decision-log entry (Part A) + index.md row

# Task 8a — Fix question-generation defects, regenerate, rerun bake-off

Read evaluation.md and index.md for the actual next D-number — don't
assume. Task 8's outputs (questions.jsonl, embedding bake-off results)
are entirely void as of this task — do not compare against them, use
them as a prior, or tune anything relative to them. Treating them as
a baseline risks overtuning to a defective question set.

## Part A — Decision log
One new entry covering all of the below (bundle, don't split into
several tiny entries — matches D38's economy):
- Human review of the 148-question set (task 8) surfaced three real
  generation defects, not sampling noise. Cite the actual examples from
  review, not a paraphrase.
- Wiki-metatextual leakage: questions referencing the source's own
  document structure ("infobox," "listed as," "stated," "section," "the
  wiki says") rather than the world/story. Fix: explicit negative
  constraint in the generation prompt.
- Speculation-sourced questions: initially proposed excluding
  is_speculation=true chunks from the pool entirely — WRONG, corrected
  on review. The actual bug is the same wiki-metatextual-leakage pattern
  (chunks under a heading literally named "Speculation" leaking that
  framing into the question), not that speculative content is
  inherently unaskable. Fix is generation-level, not pool-exclusion:
  ban structural cross-references, explicitly permit topical vocabulary
  ("theory," "speculation," "mystery," "unresolved") as ordinary
  language a reader would use. Pool stays as originally scoped — no
  exclusion added. Reason this mattered: book_level=3 is already the
  smallest, most concentrated pool (32 chunks, D23), excluding
  speculation-flagged material would have gutted it further.
- Compound/quiz-style questions: not fixed via a syntactic "and" ban
  (too narrow, mistargets the actual problem). Fix is a persona/intent
  instruction — write as a curious reader asking one thing they
  genuinely want to know, not as someone testing exhaustive recall of a
  specific passage's stated facts.
- Separately, a pool-exclusion gap: navigational/index-shaped sections
  (e.g. a chapter's "characters list") carry no checkable content, same
  category D24 already named and flagged for revisiting ("Title,"
  "Silence" headings) if more turned up. This is that revisit.

## Part B — Prompt fixes (generate_questions.py)
1. Negative constraint: no references to the source's own structure —
   "infobox," "listed," "stated," "section," "according to the
   page/wiki," or equivalent. Applies regardless of chunk_type.
2. Do NOT exclude is_speculation chunks. Explicitly permit topical
   uncertainty vocabulary; the constraint in (1) already blocks the
   actual leakage pattern without needing a pool change.
3. Style/persona instruction replacing any "generate a question this
   chunk answers"-style framing: write as a real reader's single,
   genuine curiosity — one focused question, not an exhaustive-recall
   quiz question covering multiple stated facts from the passage.
4. Extend the D24-style exclusion: audit section slugs across the
   corpus for other navigational/index-shaped sections beyond
   "characters list" (the one instance found) before regenerating —
   don't patch just the one instance, check whether the pattern
   recurs.

## Part C — Regenerate and validate
- Recompute the eligible pool size after Part B.4's extended exclusion;
  confirm or adjust the 60/60/28 book_level floors against the updated
  pool (likely near-unchanged, but confirm rather than assume).
- Regenerate the full question set at the same target volume as task 8,
  same dry-run-cost-estimate-first pattern as before.
- Automated gate before any human review: grep the new set for the
  Part B.1 banned terms — zero tolerance, regenerate any hit rather
  than hand-editing around it.
- Present the full regenerated set (only 148 questions, small enough
  to not need sampling) for a human pass — last round's ad hoc partial
  review is what caught these bugs; don't rely on the automated gate
  alone to catch the style-level issues (compound/quiz-style-ness isn't
  greppable).

## Part D — Rerun the bake-off
- Same three candidates, same k-values (1/3/5/10 hit rate, MRR@10),
  against the new question set only.
- Manifest should note explicitly that this run supersedes task 8's,
  and why (defective question set) — same transparency standard as
  D24/D38, not a silent overwrite.

## Non-goals
- No change to embedding candidates or metric choice — orthogonal to
  what's being fixed here.
- No retrieval/system-prompt behavior work (the "don't keyword-match
  section_heading for 'speculation'" point) — noted for later, not
  built here.
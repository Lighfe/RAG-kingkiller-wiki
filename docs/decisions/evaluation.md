# Decision log — evaluation (D17)

Part of the decision log, split by topic 2026-07-22. Index:
docs/decisions/index.md. Append-only. One entry per settled decision;
date, decision, one-line why. Corpus/licensing/labeling-signal
background: docs/kingkiller-dataset-notes.md.

**D17 · 2026-07-19 · Evaluation hierarchy: groundedness is the primary
property; the spoiler gate is a specialization of it, not a separate
goal.** Three eval layers, in priority order: (1) retrieval quality —
does the right chunk come back (hit rate / MRR on a generated question
set; where hybrid search + reranking are compared); (2) faithfulness —
is every claim supported by the retrieved chunks, including
out-of-corpus trap questions where the correct answer is "the wiki
doesn't cover this"; (3) spoiler leakage — faithfulness with the judge
criterion specialized to book_level, compared across prompt variants.
Layers 2 and 3 share one judge harness with different judge prompts;
spoiler leakage and hallucination are the same failure channel
(unfiltered parametric memory). Per-answer citations double as the
user-facing groundedness contract alongside CC BY-SA attribution.
Writeup reports "grounded, measured at X%", never "doesn't
hallucinate".

**D30 · 2026-07-23 · Retrieval-config eval uses unfiltered ground truth; filter
correctness verified separately.** The embedding-model / hybrid-vs-vector-only
comparison runs against ground truth at full clearance (no book_level filter),
so the metric isolates ranking quality. `book_level <= clearance` is a
deterministic check, verified independently — conflating the two makes a low
score ambiguous between "weak retriever" and "filter correctly excluded
content."

**D31 · 2026-07-23 · Retrieval question-set generation: chunk-grounded,
floor-stratified (not parity) across chunk_type and book_level; low-signal
chunks excluded.** Ground truth questions are LLM-generated per chunk — a
general technique, not FAQ-specific (project.md confirms non-Q&A datasets
are the norm). book_level=1/2 are each sampled to a floor large enough that
neither can hide a weak score inside the 67.5%-majority aggregate;
book_level=3 (32 chunks, mostly prologue/speculation per D23) is
deliberately NOT inflated to equal-N parity — the pool is too small and too
speculative in nature to support the same volume without repetition. All
metrics are reported per book_level stratum, not just as one aggregate, so
a weak stratum can't hide inside a strong one; book-3 numbers carry the
same small-n caveat D13 already applies to the gold chapter set.
chunk_type gets the same floor treatment (prose dominant at 74.8%;
infobox/quote guaranteed minimum coverage, not forced parity). Chunks
structurally incapable of supporting a unique question (chapter infoboxes,
atmospheric sub-headings — same exclusion class as D24) are excluded from
the question-source pool; they remain indexable and retrievable.

**D32 · 2026-07-23 · refines D17 · Graded, scope-split ground truth for
single-hop; no fixed ground truth for multi-hop.** Single-hop questions get
graded, pre-registered ground truth (source chunk > same-page sibling >
everything else), scored with NDCG@k (rank + grade aware) and hit rate@k
(cheap sanity check). Supersedes D17's named metric of hit rate/MRR: MRR is
dropped as redundant with NDCG once graded labels exist; precision@k is
deferred to a context-noise diagnostic rather than the config-selection
metric. Multi-hop/synthesis questions have no boundable correct-chunk set, so
get no pre-registered ground truth — an LLM judge instead scores whether the
generated answer's claims are traceable to whatever was actually retrieved.

**D33 · 2026-07-23 · operationalizes D17 · LLM-evaluation rubric point
anchored on spoiler-refusal prompt comparison.** D17 already specified
leakage rate "compared across prompt variants" as the layer-3 metric; this
makes it concrete: ≥2 refusal-instruction variants (e.g. plain "use only
retrieved context" vs. an explicit "if context doesn't cover this, say so
rather than drawing on prior knowledge of the books") are compared on leakage
rate, winner ships. The multi-hop groundedness judge (D32) is a single fixed
measurement of the production config and doesn't need to carry this
requirement separately.

**D34 · 2026-07-23 · refines D17 · Spoiler leakage eval: trap + control
pools, dual-sourced traps.** Leakage eval uses two pools scored by the same
judge: trap questions (book_level>=2 content, correct = refuse), sourced both
from own-wiki book_level>=2 chunks (reuses D31's generation machinery) and
from the real book's independent Wikipedia article (probes raw parametric
knowledge independent of corpus phrasing); and control questions (legitimate,
well-grounded book-1 questions, correct = answer). Reporting both catches
over-refusal, not just leakage — a prompt tuned only against traps could pass
by refusing indiscriminately.

**D35 · 2026-07-23 · Production answers compose multiple chunks, possibly
multiple pages.** Answers are built from top-K retrieved chunks (K set from
D32's single-hop hit-rate@k results), not a single chunk — this is what makes
cross-page synthesis possible at all. The spoiler filter applies before
composition, so nothing unfiltered reaches the context window regardless of
how many chunks/pages are combined. Per-chunk `page_title`/`section_heading`
(already in `text`, per the chunk schema) carries through composition for
per-answer citation.

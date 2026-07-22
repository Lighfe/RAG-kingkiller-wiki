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

# Task: LLM labeler — build, validate, STOP before full pass

Read first: docs/decisions.md (D11–D14, D17), docs/manual-labeling-guide.md,
docs/dataset-notes.md. .env has OPENAI_API_KEY — do not print or log it.

## Part 0 — wrap-up + diagnostic + decisions

- Commit data/manual_labels.jsonl (force-add).
- Diagnostic (read-only, report only, no code changes to the chunker):
  among label_provenance=null chunks, count those under a heading
  matching /reference/i whose content (after removing the page/section
  header line) is ≤15 words. Report the count and print 10 examples.
  This number informs Part 1's prompt; it does NOT trigger a chunker
  change in this task.
- Append to docs/decisions.md:
  **D18 · 2026-07-22 · Infobox spoiler judgment: static facts (region,
  government type, currency, species) never escalate book_level;
  relational facts (e.g. ruler/affiliation) escalate only if the
  pairing itself is a story disclosure, not background lore.** Informs
  the LLM labeler prompt and the manual-labeling guide.
  **D19 · 2026-07-22 · Bare book-title mentions unconnected to any
  claim (e.g. plain-text "References" sections without templates) do
  not escalate book_level — reinforces D11's mentions-aren't-labels for
  a shape the harvester doesn't catch.** Chunker NOT patched to filter
  these (would invalidate the frozen sample); handled in the labeler
  prompt instead. Revisit as a retrieval-quality filter if eval shows
  them as noise.
- Add both cases (Severen-shape, Four-plate-door-shape) as short
  examples in docs/manual-labeling-guide.md, for consistency if
  labeling ever resumes or is redone.

## Part 1 — labeler (ingest/label_llm.py)

- Model: gpt-5.4-mini. Pydantic output schema: book_level (1|2|3),
  confidence ("low"|"medium"|"high" — categorical, not a fabricated
  float; LLM numeric confidence isn't meaningfully calibrated),
  rationale (one sentence).
- Input per chunk: page_title, section_heading, chunk_type, chunk text.
  Do NOT show harvested citation codes or provenance (those chunks
  don't reach this labeler anyway, but keep the function pure).
- Prompt encodes: the reveal-vs-mention rule (from the guide), D18
  (static vs. relational infobox facts), D19 (bare title mentions don't
  escalate), the book-code levels (1/2/3), and side-story mapping.
- Post-processing: confidence="low" → override to conservative default
  (book_level=3) regardless of the model's raw label; log both the raw
  and the applied value.
- CLI: --dry-run (estimate cost from token counts × current pricing,
  no API calls), --chunks (limit, for the validation runs below),
  --output.

## Part 2 — validation (per D13 — gates the full pass)

- Run the labeler on: (a) chunks belonging to the 26 gold chapter
  pages' non-infobox content [wait — gold pages are already fully
  labeled; instead validate on a held-out check: re-derive gold labels
  blind and compare], and (b) the 80 adversarial chunks, comparing
  against data/manual_labels.jsonl ("u" entries excluded from the
  denominator).
- Report: book-2 recall on the adversarial set, overall accuracy on
  gold, a confusion matrix, and every disagreement with a manual label
  (chunk_id, manual, model, model's rationale) for manual review.
- Compare against D13 thresholds (recall ≥0.80, accuracy ≥0.90).
  State pass/fail explicitly. Note the small-n confidence interval.

## Part 3 — cost estimate, then STOP

- Run --dry-run against the full 1,258-chunk null-provenance set.
  Report estimated tokens and cost.
- STOP here. Do not run the full labeling pass. Report Part 0's
  diagnostic number, Part 2's validation verdict, and Part 3's cost
  estimate, and wait for explicit go-ahead before spending money.

## Tests
Pydantic schema validation; conservative-default override logic;
prompt-construction unit tests (no live API calls in the test suite —
mock the client).

## Hard rules
- No live API calls except the explicit validation runs in Part 2 and
  the dry-run in Part 3 (which makes no API calls at all).
- Never proceed to a full labeling pass in this task, regardless of
  how good validation looks.
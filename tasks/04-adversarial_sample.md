# Task: adversarial sample + manual labeling CLI

Build the ground-truth tooling for labeler validation (D13): draw the
stratified adversarial sample and provide a CLI for blind hand-labeling.
No LLM calls anywhere in this task.

Read first: docs/decisions.md (D13, D14), docs/dataset-notes.md §5.

Input: data/chunks.jsonl — verify sha256 starts a988ed70 before
sampling; abort if not (the sample must come from the frozen set).

## Part 0 — decision log

Append to docs/decisions.md:
**D15 · 2026-07-19 · Maintenance banners ({{orphan}}, {{underlinked}})
match structural infobox detection; date param added to skipped set so
they emit no chunk.** Logged as detections, not silently dropped.
**D16 · 2026-07-19 · Single paragraphs > 380 words (6 chunks, max
1,109w) stay unsplit; paragraph is the smallest split unit.** Worst
cases are lists; arbitrary sub-paragraph cuts help nothing. Revisit at
retrieval eval if these chunks misbehave.

## Part 1 — sampling script (ingest/draw_sample.py)

Frame: chunks with label_provenance null AND is_speculation false
(the population the LLM labeler governs; speculation is gated
deterministically per D09).

Draw 80 chunks, fixed seed, two strata (D13):
- ~48 (60%) "cluster" stratum: chunks whose page_title, section_heading,
  or categories match the audit-named book-2 clusters — Ademre, Shehyn,
  Rethe, Vaevin, Adem / Ademic / sign language, Faen / Felurian,
  Maer / Alveron / Severen / Vintas arc. Implement as a reviewable
  keyword list in code; report per-keyword hit counts. If matches
  exceed 48, sample within; if under, backfill from the random stratum
  and report the shortfall.
- ~32 (40%) "random" stratum: uniform over the rest of the frame.

Output data/adversarial_sample.jsonl: chunk_id, stratum, and the
matched keyword (cluster stratum only). NO chunk text, NO labels —
this file is committed (it contains no wiki content), so the sample
is reproducible and reviewable.

Checks: exactly one record per sampled chunk_id; all in frame; strata
counts as specified; deterministic across two runs.

## Part 2 — labeling CLI (ingest/label_manually.py)

Loop over the sample in RANDOMIZED order (fixed seed, so cluster chunks
don't arrive in runs that prime expectations). Per chunk display:
- page_title § section_heading, chunk_type, the full chunk text, and
  the page_url (for checking edge cases against the wiki)
- NOTHING else: no citation codes, no heuristic hints, no stratum, no
  progress-by-stratum — labeling is blind (D13).

Keys: 1 / 2 / 3 = book_level ·  u = unsure ·  b = back (redo previous)
·  q = save and quit. Progress line: "n/80 · elapsed mm:ss".

Output data/manual_labels.jsonl (append-only, resumable — on restart,
skip already-labeled chunk_ids): chunk_id, manual_book_level (1|2|3|
"u"), seconds_spent, timestamp. Committed file — chunk_ids and labels
only, no text.

On completion print a summary: counts per label, per stratum (looked
up post-hoc from the sample file), total time, and the "u" list.

## Part 3 — labeling guide (docs/manual-labeling-guide.md, ~half page)

Written for the labeler (Julian). Core rule: label the HIGHEST book
whose content the chunk reveals — 1 if everything stated is
established in The Name of the Wind; 2 if anything requires The Wise
Man's Fear (side stories count as 2 per the D11 mapping); 3 if
anything reveals Doors of Stone / unpublished material. Judge what the
text REVEALS, not what it mentions: a chunk saying "she reappears
later" without saying what happens reveals nothing book-2. When torn
between two levels after checking the page_url, choose the HIGHER and
note it via "u" only if genuinely undecidable — "u" chunks are
excluded from recall metrics and reported separately. Include 3 short
invented examples (one clear 1, one clear 2, one mention-vs-reveal
trap). Do not quote real wiki text in the guide.

## Tests

Sampling: frame filter (null + non-speculation only), strata sizes,
determinism, backfill path. CLI: resume skips labeled ids; "b" rewrites
the previous record; output schema. Use synthetic chunk fixtures.

## Hard rules

- chunks.jsonl read-only; hash-check before anything.
- The CLI must be dumb: no model calls, no label suggestions, no
  auto-anything. Its entire job is showing text and recording keys.
- If the cluster stratum underfills, that's a finding to report, not
  a reason to loosen the keyword list silently.
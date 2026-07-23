# Decision log — labeling (D18–D28)

Part of the decision log, split by topic 2026-07-22. Index:
docs/decisions/index.md. Append-only. One entry per settled decision;
date, decision, one-line why. Corpus/licensing/labeling-signal
background: docs/kingkiller-dataset-notes.md.

**D18 · 2026-07-22 · SUPERSEDED by D21 · Infobox spoiler judgment: static facts (region,
government type, currency, species) never escalate book_level;
relational facts (e.g. ruler/affiliation) escalate only if the
pairing itself is a story disclosure, not background lore.** Informs
the LLM labeler prompt and the manual-labeling guide.

**D19 · 2026-07-22 · refined in D21 · Bare book-title mentions unconnected to any
claim (e.g. plain-text "References" sections without templates) do
not escalate book_level — reinforces D11's mentions-aren't-labels for
a shape the harvester doesn't catch.** Chunker NOT patched to filter
these (would invalidate the frozen sample); handled in the labeler
prompt instead. Revisit as a retrieval-quality filter if eval shows
them as noise.

**D20 · 2026-07-22 · Frame-story clarification for the LLM labeler.**
The present-day frame (Kote/Bast/Chronicler) runs through all three
books; its presence alone is not a book_level=3 signal. Judge from
what backstory/plot content the scene discloses, not the frame device
itself. Added after gold-set validation showed frame narration driving
false book-3 labels (accuracy 0.789 vs. the 0.90 gate).

**D21 · 2026-07-22 · Infobox spoiler judgment (replaces D18): the
static/relational split only applies to entities already knowable from
Book 1.** For entities first introduced in Book 2+, ALL fields —
including mundane categorical ones — inherit that book_level as a
floor, since a Book-1-only reader doesn't know the entity exists at
all. For entities reachable from Book 1 (e.g. Severen, visible on the
TNOTW map), the original split holds: static facts don't escalate;
relational facts escalate only if the pairing is itself a story
disclosure. Revised after adversarial validation showed the unscoped
rule misapplied to Book-2-introduced companions (recall 0.630 vs. the
0.80 gate).

**D22 · 2026-07-22 · D19 scope refinement: direct self-identification
of book membership escalates; incidental mentions don't.** A chunk
stating that ITS OWN content belongs to a specific book (e.g. "is the
Nth chapter of The Wise Man's Fear") functions as a citation-equivalent
signal, unlike Four-plate-door's untethered reference list. Mostly
moot for chapter pages (already gold via D11) but the principle
generalizes to any content — ns-0 included — where a book title names
the direct source of the specific claim being made.

**D23 · 2026-07-22 · Book-level-3 confidence calibration: true Doors
of Stone content is rare and concentrated (is_speculation-flagged
material, explicit TDOS references, the TDOS prologue page), not a
default for content that merely feels unresolved.** Unresolved mystery
and suspense run through Books 1 and 2 as a core device — refines D20
to cover frame-story SUSPENSE, not just frame-story presence. When the
model can't ground book_level=3 in something specific, it should
register LOW confidence (triggers the D12 conservative default) rather
than a confident, ungrounded guess. Added after gold-set validation
showed the labeler confidently mislabeling an established Book-1 scene
(the Scrael attack in "Halfway to Newarre") as unpublished.

**D24 · 2026-07-22 · Gold-set accuracy denominator excludes chunks
that cannot carry content-level book signal by construction: chapter
infobox chunks (chunk_type=infobox on ns-112 pages — D07 always
serializes a literal book-code field, leaked verbatim or artificially
stripped, unlike any real non-gold infobox) and chunks under
atmospheric/bibliographic sub-headings verified to carry no checkable
plot claim (starting list: "Title"; "The first/second/third silence"
— revisit if more are found).** Refines D13: the 0.80 recall / 0.90
accuracy thresholds are unchanged; only which gold chunks are eligible
for the accuracy test. Exclusion is category-defined, not outcome-
defined — the same chunks would be excluded regardless of whether they
scored correctly. Both the original (D13) and refined (D24)
denominators are reported on every run. The adversarial/recall set is
unaffected: it's drawn from the null-provenance tier by construction
(same population the labeler sees in production), so it never had
this mismatch.

**D25 · 2026-07-22 · Book-level judges DISCLOSURE, not narrative
significance.** Introducing an unresolved mystery, object, or ominous
detail is establishing content at whatever book_level it first
appears — it does not itself imply a later book, even when the
mystery's ultimate resolution lies further along or unpublished.
Escalate only when a chunk actually RESOLVES, EXPLAINS, or EXTENDS a
previously-established mystery with new information beyond its book
of introduction — not because content is dramatic, dangerous, or
thematically important. Added after repeated high-confidence
misclassification of Book-1/2 mystery-INTRODUCTION scenes (the sealed
chest's first appearance; the Cthaeh's specific revelations) as
unpublished — D23's confidence-calibration fix didn't catch this
because these chunks contain genuine, specific, correctly-grounded
claims; the error is in what the grounding is taken to mean, not a
lack of grounding.

**D26 · 2026-07-22 · D21's entity-introduction floor is chunk-type-
agnostic:** it applies to trivia, description, and any other prose on
a Book-2+-introduced entity's page, not only infobox chunks. The
mandatory page-title/section-heading prefix (D04) discloses the
entity's existence via any chunk, regardless of content genre.

**D27 · 2026-07-22 · Manual ground-truth corrections to
data/manual_labels.jsonl: 9 adversarial labels revised after model-
disagreement review surfaced reasoning gaps in the original blind
labeling.** 2151/3037/4502 (Maer/Tinuë/Severen — Book-1-reachable
background geography, Severen-shape per D18/D21); 2230:in-the-
chronicle-the-university:6 (fall-term content is genuinely Book 2,
originally missed); 2267/2349/2454/2456/2458 (University-arc characters
correctly Book-2-introduced, originally under-labeled — 2456/Inyssa
attends Elodin's lessons with Kvothe, a Book-2 setting). Each
correction carries an independent reason, not model agreement alone —
noted here since post-hoc ground-truth revision after seeing model
output carries inherent confirmation-bias risk even when well-reasoned.

**D28 · 2026-07-22 · Labeler schema: `rationale` generated before
`book_level`/`confidence`**, not after — verified case where the
model's own stated reasoning argued for a different label than it
output. Forces the label to follow from generated reasoning. Confirmed
against the raw stored structured-output record (not just the printed
report) for chunk `2049:lede:0` (Ambrose Jakis): rationale read "...
established by the first novel's plot and does not require later
books" while the emitted `book_level` was 2 with `confidence: high` —
a direct self-contradiction between the model's own stated reasoning
and its label, consistent with the field-order theory rather than a
one-off content misjudgment.

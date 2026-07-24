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

**D32 · 2026-07-23 · refines D17 · refined in D38 · Graded, scope-split ground truth for
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

**D36 · 2026-07-23 · Entity co-mention graph (task 6) built; redirect
resolution closed via one cached, one-time API fetch (task 6b amendment
— same decision, corrected scope).** `ingest/entity_graph.py` parses raw
wikitext for `[[...]]` wikilinks (pre-strip, same D03 principle), resolves
targets against the known 464 page titles, and localizes matches to
chunks — `data/eval/entity_links.jsonl` (5,714 rows; 4,493 link-localized,
1,221 text-recovered), feeding D32/D33's multi-hop question hand-picking,
not production retrieval. `pages.jsonl` was fetched with
`apfilterredir=nonredirects` (D01), so no redirect mapping exists locally
at all. Originally (task 6) this was accepted as an offline-only gap —
120 unique unresolved targets / 682 occurrences, merely logged for
review. Task 6b closed it instead: `ingest/fetch_redirects.py` runs one
cached, batched (≤50 titles) `action=query&redirects=1` lookup (3 requests
total) through the existing polite `WikiFetcher`, caching the result to
`data/redirects.json` (99 entries) — everything downstream still runs
offline against that cache, so this doesn't reopen D02's offline-afterward
principle, it just moves the one-time network cost to its own explicit
stage, same shape as `pages.jsonl` itself. `resolve_target`'s tiers are
now exact → case/underscore normalization → unique casefold → cached
redirect map → unresolved; the redirect tier only accepts a title the API
actually reports under `redirects` (not a bare re-casing) and only if it
maps to one of the 464 known pages, so it stays mechanical, not a guess.
**Result: 120 unique/682 occurrences → 20 unique/24 occurrences
unresolved** (657 occurrences resolved via the redirect tier — Kote→Kvothe,
Chronicler→Devan Lochees, University→The University, Adem, Fae, Amyr,
Eolian, Tehlin, Cthaeh among them). The remaining 20 are genuine
non-redirects the live lookup itself confirmed as missing/unmodified:
typos (`The Arcanumm`), true redlinks (`Shane Tyree`, `Belen`, `Duke of
Gibea`), and — a distinct, real gap on the wiki itself, not a tool
limitation — chapter-navigation infobox links that omit the `Chapter:`
prefix their own target requires (`Locks`, `Thieves, Heretics, and
Whores`, `A Silence of Three Parts (epilogue of The Wise Man's Fear)`).
Along the way, fixed a related parsing gap in `classify_target`: a
leading colon (`[[:File:X]]`, MediaWiki's "link to this page directly"
syntax) wasn't stripped before the namespace-prefix check, so it fell
through as a fake "unresolved" candidate instead of being recognized as a
non-entity File: link — caught by the live lookup reporting it "missing"
rather than proposing any real target.

Reconciles task 6's open count question: 3,491 directional edges
(now 3,960) vs. a resolution-method breakdown summing to 4,318 (now
4,975) is NOT a bug — `edges` counts unique (source, target) pairs, while
resolution counts every resolved link *occurrence*; confirmed via
`sum(len(v) for v in edges.values())` = 4,971 (now) + `self_links_skipped`
(4, resolved but excluded since a page can't link to itself) = 4,975,
matching the resolution-method sum exactly. The remaining gap versus the
edge count (4,971 − 3,960 = 1,011) is repeat same-pair links: a source
page linking/mentioning the same target more than once, collapsed into
one edge key with a multi-entry display list.

Stage-B's false-positive spot check still surfaces genuine short-name
collisions worth caution when hand-picking pairs — e.g. "Ben" (pageid
2753) is a real page distinct from both "Ben Bentley" and "Abenthy"
(whose alias is "Ben"), so bare-word matches for it need a human read
before use.

Pointer (2026-07-24, D38): the multi-hop hand-picking use case this
entity graph originally supported is retired — see D38. The artifact
itself (`entity_links.jsonl`, `redirects.json`, both manifests) is
retained and repurposed as D39's loop-time link-traversal index; no
extraction work done here is invalidated, only its consumer changes.

**D38 · 2026-07-24 · refines D32 · Entity-graph-driven multi-hop question
sourcing retired; multi-hop stays a deferred concept, not a deleted one;
"hop" terminology disambiguated.** Task 6/6b/6c built `entity_links.jsonl`
and a rollup shortlist (`data/eval/multihop_shortlist.md`, 99 candidates,
task 6c) to hand-pick multi-hop/synthesis questions from co-mention
page-pairs. Manual review of that shortlist
(`data/eval/multihop_shortlist_annotation.md`) found the hand-picking
process itself too difficult to execute reliably: most category-pair
buckets' top-3 candidates surfaced the same main-character (chiefly
Kvothe, also Auri) connections regardless of which categories were
paired, yielding few genuinely distinguishing questions. Domination wasn't
the only failure mode, and fixing it wouldn't have been enough on its own:
cross-category pairs with no main-character involvement
failed independently too — e.g. a Location x Object pair the annotation
called "meaningful" still proved "hard to come up with specific questions"
for. Link co-occurrence alone doesn't imply a synthesizable question exists,
regardless of sampling diversity — the deeper reason the sourcing method
is retired, not just the visible symptom. Annotation
concludes "the process is too difficult to execute." Multi-hop/synthesis
questions are not deleted as a concept — D32's no-fixed-ground-truth,
judge-only design is still the right shape for them — but sourcing
candidates by hand-picking entity-graph page-pairs is dropped. If ever
revisited, the proposed alternative is synthetic Q&A generated from the
complete Wikipedia articles for books 1/2 (continuous prose, not sparse
wiki co-mention pairs), not entity-graph-driven page-pair sourcing —
noted as optional/deferred, not built here.

Separately: "hop" was overloaded between (a) a property of a question's
ground truth — single-hop has one correct chunk, multi-hop has no fixed
correct chunk (D32) — and (b) a property of the retrieval mechanism — one
retrieval pass vs. several actions in a loop (D39). "single-hop question"
keeps its existing meaning and still backs D31/D32. "hop" is no longer
used for loop mechanics — say "loop action" / "retrieval step" instead.

**D39 · 2026-07-24 · One-shot vs. agentic-loop retrieval comparison
design.** A new eval axis, orthogonal to D32's single-hop/multi-hop
ground-truth split: compares the existing one-shot retrieve-then-generate
pipeline (baseline) against an agentic loop — retrieve → self-assess
sufficiency → act (same-page expansion / cross-page link-follow / query
rephrase) → repeat, bounded by a max loop-action cap plus visited-chunk
tracking (the link graph can cycle). Runs on the existing single-hop
question set (D31) — no new question generation needed for this
comparison. Ablation cells: link-following only, rephrasing only, both,
vs. baseline. Two signals per question: (1) deterministic — did the final
retrieved context include the known correct chunk_id, reusing D31/D32's
graded ground truth directly with no LLM call; (2) judge — are the final
answer's claims grounded in what was actually retrieved, via D17's shared
judge harness. Comparing (1) vs. (2) on the same set is a
judge-accuracy/calibration byproduct, not the headline metric — that
calibration is specific to grounded-in-single-chunk-context judging and
doesn't automatically transfer to synthesis-style claim-traceability
judging later. Hard constraint, stated explicitly: every loop action
re-applies `book_level <= clearance` identically to the initial retrieval
filter — a loop is a second retrieval surface and must carry the same
access-control guarantee as the first, no exceptions. Cross-page hop
selection (which linked page to follow) is an LLM call conditioned on the
live query, not a static highest-link-degree pick — specifically to avoid
a "main character trap" where the loop defaults to the
most-connected/most-mentioned entities regardless of relevance, the same
failure mode D38's annotation review surfaced in the abandoned
hand-picking approach.

**D40 · 2026-07-24 · refines D32 · Single-hop ground truth for the
embedding-model bake-off is binary (exact chunk_id only), not D32's
graded same-page-sibling scheme; NDCG dropped in favor of hit rate@k +
MRR.** Considered graded scoring (exact=2, same-page sibling=1 via a
lexical/keyword-overlap "pertinent check," chunk_type=prose-only
eligibility, boost weights on `page_title`/`chunk_type` held constant
across compared configs) — motivated by wanting compatibility with later
field-boost tuning without same-page credit mechanically favoring a
page_title-boosted config. Dropped in favor of binary: binary grading is
structurally immune to that confound by construction (the target chunk
is itself on the titled page, so page_title-driven signal toward it is
legitimate, not exploited) — no mitigation layer needed. Also more
reliable at this project's deliberately low/toy question volume (task 8:
148 questions), where a heuristic's false positives (the same short-name-
collision risk D36's entity-graph spot check flagged, e.g. "Ben") aren't
averaged out. Consequence: NDCG isn't used this round — it needs graded
labels to earn its cost — so hit rate@k and MRR are the metrics,
reverting to D17's originally named pair for Stage 1. Graded same-page
scoring is a documented, deferred upgrade path, not deleted: revisit if
and when the eval needs finer resolution than binary gives (e.g. once
field-boost tuning is actually in scope, Stage 2+).

**D41 · 2026-07-24 · Human review of task 8's 148-question set found
three real question-generation defects (not sampling noise); task 8's
questions.jsonl and embedding_baking_off_results are void, fixed and
regenerated under task 8a.** Cites the actual review findings, not a
paraphrase:

1. **Wiki-metatextual leakage** — questions referencing the source's own
   document structure rather than the world/story, e.g. "Who is listed
   as Meluan Lackless's husband in the infobox?" (2291:infobox-0:0), "How
   many pages is The Slow Regard of Silent Things listed as having in its
   infobox?" (5281:infobox-0:0), and "Which characters are listed in the
   chapter's characters list?" (12385:characters-list:0). Fix: an
   explicit negative constraint in the generation prompt (`ingest/
   generate_questions.py` `INSTRUCTIONS`), enforced by an automated
   post-generation gate (`has_banned_reference`) that regenerates any hit
   rather than hand-editing around it — bare terms "infobox"/"listed"/
   "stated"/"section", plus the phrase "according to the
   wiki/page/article/chapter/entry/infobox/section/speculation/text/
   list". In-world attribution by name (e.g. "According to Kvothe...",
   "According to the Cthaeh...") is explicitly exempted — the ban targets
   referencing the document, not the story's own voices.
2. **Speculation-sourced questions initially misdiagnosed** — first
   proposed excluding `is_speculation=true` chunks from the source pool
   entirely; WRONG, corrected on review. The actual bug is case 1's same
   leakage pattern surfacing on a "Speculation"-headed chunk: "According
   to the speculation, which person is suggested as a possible Amyr
   member because he guards the door?" (2045:speculation:0) — the
   heading's own literal name leaking into the question, not that
   speculative content is inherently unaskable. Fix is generation-level
   (case 1's constraint + phrase list explicitly covering "the
   speculation"), not pool-exclusion — the pool keeps every
   `is_speculation` chunk. This mattered because book_level=3 is already
   the smallest, most concentrated pool (32 chunks pre-exclusion, D23);
   excluding speculation-flagged material would have gutted it further.
   Regenerated speculation questions now read naturally: "Who do fans
   think Kvothe may already have met under a different alias as Master
   Ash?", "What clue makes fans think Auri might be connected to the
   Amyr?" — topical vocabulary ("theory", "speculation", "fans think"),
   not document-structure reference.
3. **Compound/quiz-style questions** — joining two distinct asks with
   "and" instead of one focused question, e.g. "What was the object
   Mauthen had found buried under the house, and why was Nina afraid the
   Chandrian might come after her?" (2099:in-the-chronicle:0). Measured
   at 41/148 (28%) of task 8's set via a `", and (what|how|why|which|
   who|where|when)"` grep — a real, systemic rate, not noise. Not fixed
   via a syntactic "and"-ban (too narrow, mistargets the actual problem:
   a listing-style compound like the Tak external-links question below
   has no "and… what" join at all). Fix is a persona/intent instruction:
   write as a curious reader asking one thing they genuinely want to
   know, not an exhaustive-recall quiz question covering multiple stated
   facts. Reduced task 8a's regenerated set to 6/148 (4%) on the same
   grep — better, not eliminated; compound/quiz-style-ness isn't reliably
   greppable (a listing style can dodge any fixed conjunction pattern),
   so residual cases are a human-review finding, not an automated-gate
   failure.
4. **Pool-exclusion gap, found while investigating case 1**: bare
   navigational/index sections carry no checkable content, the same
   category D24 already named and flagged for revisiting ("Title",
   "Silence" headings) if more turned up — this is that revisit.
   `12385:characters-list:0` (a bare name list on a ns=112 chapter page)
   produced case 1's characters-list example. Auditing every
   `section_heading` leaf corpus-wide for the pattern's recurrence (not
   patching just the one instance) found it recurs twice more: "external
   links" (4 chunks — bare link/website-name lists, e.g. "DAW Books
   Website"; one of these, `3770:external-links:0`, produced task 8's
   compound "which official Tak resources include..." listing question)
   and "list of appearances" (1 chunk, Elodin — a bare chapter+page
   index). Checked and NOT excluded, same "verify before excluding"
   discipline as D24's "Title" precedent: "see also" (2 chunks, each
   carrying a real one-line relationship claim, e.g. "Tak - A modern game
   that arose from Kaen") and "appearances in the books" (1 chunk,
   Gerrek — real descriptive content); several other "list"-named
   headings (List of languages, List of songs, List of editions by
   country, Siaru's grammar "Lists" section) were also checked and kept
   for the same reason — heading text alone doesn't determine exclusion,
   content does.

**Consequence**: eligible pool for question-sourcing moved from
1,719/1,761 (task 8) to 1,696/1,761 (task 8a, 23 more excluded) —
confirmed near-unchanged rather than assumed; the D31 60/60/28
book_level floors were unaffected (none of the newly-excluded chunks are
book_level=3). The question set was regenerated at the same target
volume (148) and the embedding bake-off (D40) was rerun against it —
task 8's original questions.jsonl and embedding_baking_off_results are
superseded, not silently overwritten (both manifests say so explicitly).
No change to the embedding candidates or hit-rate@k/MRR metric choice —
orthogonal to what this entry fixes.

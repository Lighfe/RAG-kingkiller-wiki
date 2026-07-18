# Kingkiller Wiki Dataset Notes

Knowledge file for the LLM Zoomcamp capstone (RAG-kingkiller-wiki).
Status: dataset decisions settled, backed by the label-signal audit
(`scripts/label_audit.py`, run 2026-07-17 against the live wiki).
Supersedes all Coppermind-era assumptions — update the project
instructions accordingly.

## 1. Source & licensing

- **Corpus: the Kingkiller Chronicle Fandom wiki** (`kingkiller.fandom.com`),
  text only, via the MediaWiki API.
- **License: CC BY-SA 3.0** (stated in every article footer and on the
  wiki's Copyrights page). Obligations:
  - *Attribution*: credit the wiki + link source pages — in the app UI
    (per-answer citations) and the README.
  - *Share-alike*: don't redistribute the corpus. The repo ships the
    ingestion pipeline, not the data; `data/` is gitignored.
- **Do NOT mix in `kingkiller.wiki`** — a separate, independent wiki under
  CC BY-NC-SA 4.0 (non-commercial clause; license-incompatible). The
  ingestion code asserts host == `kingkiller.fandom.com`.
- **Excluded**: images (Fandom license covers text; media is per-file),
  Pat Rothfuss's blog (all-rights-reserved, and wrong content shape).
- **History**: first choice was the Coppermind, dropped because its
  policy prohibits scraping/ML use without express permission; a
  permission email went unanswered, and silence ≠ consent.

## 2. Corpus shape (audit numbers)

- **464 content pages** in two content namespaces: **0 (main, 438 pages)**
  and **112 (`Chapter:`, 26 pages)**. Redirects excluded via
  `apfilterredir`. (`Map` ns 2900 exists; ignored.)
- **~157k words of wikitext** total — small enough to re-ingest/re-embed
  freely (pennies per full run), large enough that retrieval ranking is
  a real problem (low thousands of chunks at 300–500 tokens).
- **Categories are thematic, not book-scoped**: Characters (190),
  Minor Characters (160), Locations (65), Ademre (27), Magic (16)…
  Useful as retrieval-filter metadata; useless for book attribution.
- **Quality flags to carry as metadata**: `Articles needing help` (140
  pages), `Article stubs` (62). Expect skeleton pages even among chapter
  pages (`Chapter:Fingers and Strings` = infobox + empty headers).
- Real-world/meta pages (the novels, Adaptations, Pairs) are in scope:
  users will ask publication questions.

## 3. Spoiler model

The distinguishing feature of the project: **access-controlled retrieval
dressed as spoiler protection**. Target user story: "I finished book 1
and want things explained using only book-1 knowledge."

- Every chunk gets an integer **`book_level`**: 1 (The Name of the Wind),
  2 (The Wise Man's Fear), 3 (The Doors of Stone — unpublished; wiki
  carries a prologue page and speculation).
- **Side stories map to the trilogy level they presuppose**, not their
  own levels: The Slow Regard of Silent Things → 2, The Lightning Tree /
  The Narrow Road Between Desires → 2, How Old Holly Came to Be → 2
  (conservative; revisit if it grates). No partial-order system unless a
  real need appears.
- User declares clearance; **Elasticsearch hard-filters
  `book_level <= clearance` before ranking**. Deterministic, testable.
- **Two-layer threat model**, honestly stated:
  - *Retrieval layer* (strong): the filter above. Can be made
    near-watertight up to label quality.
  - *Generation layer* (leaky): the LLM knows these books parametrically;
    system-prompt constraints reduce but cannot eliminate leakage.
    Leakage rate is a first-class eval metric (trap questions +
    LLM-as-judge, compared across prompt variants → the rubric's
    "multiple LLM approaches evaluated").
- Calibration: **harm reduction, not a guarantee** — and the writeup says
  so explicitly.

## 4. Labeling pipeline

Signal reliability, measured (share of text volume):

| Signal | Coverage | Verdict |
|---|---|---|
| Chapter infobox `\|book=` codes | 26 pages, 5.2% | Gold. Closed vocabulary: `TNOTW` (21), `TWMF` (3+1 via title), `TDOS` (1). One chapter page has no infobox (book in title). |
| Book-scoped categories | 2 pages, 0.8% | Dead. |
| Infobox appearance params | none beyond `\|book=` | Dead — no `appears`/`debut` fields on this wiki. |
| Book-bearing `<ref>`s | 26 pages, 13.2%, median 7.5 refs/1k words | Silver. Chunk-adjacent; a chunk can cite NotW while stating a WMF fact. |
| Plain mentions | ~67% | **Not labels.** Features for the LLM pass ("she reappears in WMF" ≠ book-2 content). |
| No lexical signal | 14.3% | Includes heavily book-2 pages (Adem cluster). |

**Decision: LLM labeling pass over everything below the ref tier**
(~81% of text volume), with **conservative default (treat-as-highest-
level) for chunks the LLM flags as uncertain**.

Note on the pre-registered threshold (15% no-signal → LLM pass): the
first audit run measured 43.8% no-signal; after pattern broadening the
same tier reads 14.3%. That drop is an instrument change, not a data
change — the added patterns (side-story short names, infobox codes)
reclassified pages into the mention tier, which was never label-grade.
The decision stands on the honest quantity: **only ~19% of text
(chapter + refs + category) is reliably labeled.**

Rejected approaches, kept for the writeup:
- *kNN to chapter summaries*: similarity captures topic, not provenance;
  reference set is tiny and book-1-skewed → systematically mislabels
  book-2 content as book-1 (the worst failure direction for spoilers).
- *Absolute similarity to the WMF book page*: fires on shared-universe
  topicality; misses summary-omitted book-2 facts.
- *Differential similarity* `sim(chunk, WMF) − sim(chunk, NotW)`:
  targets the right quantity; kept as a cheap baseline to compare
  against the LLM pass, not load-bearing.

## 5. Ground truth & validation

- **Gold seed (free)**: the 26 chapter pages — 21 book-1 / 4 book-2 /
  1 book-3. Skeleton pages filtered by minimum content length before
  their chunks count. Skew stated honestly: strong for book-1 precision,
  nearly blind to book-2.
- **Silver**: ref-tier pages (13.2% of text) with per-ref book signal.
- **Adversarial gold set (manual, ~50–100 chunks, book-2-heavy)**: the
  audit already named the candidates — Ademre, Shehyn, Rethe, Vaevin,
  Adem sign language, plus Faen and Maer-arc material. This is the only
  set that measures book-2 recall = spoiler leakage in the direction
  that matters. Budget: ~1 hour of hand-labeling.
- Validation protocol: LLM labeler is judged against gold + adversarial
  sets *before* its labels are trusted; chapter pages are never both
  trainer and judge.

## 6. Ingestion gotchas (hard-won)

- **Read wikitext for labeling, `explaintext` for chunks** — every
  labeling signal (templates, refs, categories) is markup that
  explaintext strips. The rendered page lies about the source: the
  infobox displays "The Name of the Wind" while the wikitext says
  `|book = TNOTW`.
- **`apnamespace` is single-valued** — loop namespaces (0, 112); no
  pipe-syntax multi-value on `list=allpages`.
- Chapter pages: title prefix `Chapter:` arrives with the namespace;
  fallback chain for book: infobox code → title match → first 1.5k chars.
- Side stories have **no infobox codes**; they're referenced by name
  ("Slow Regard" 37×, "Lightning Tree" 34×, "Old Holly" 10× — which is
  also a character name; abbreviations statistically absent).
- Be a polite API citizen: descriptive User-Agent, ~0.5s between
  requests, batched `pageids` (≤50), continuation handled.
- Cache raw pages to `data/pages.jsonl` (gitignored); all labeling
  experiments run offline against it.

## 7. Open questions (deliberately not settled here)

- Chunking strategy (section-aware vs fixed-size; how infobox and
  quote templates are handled in explaintext).
- Embedding model (OpenAI vs sentence-transformers) — decide with the
  retrieval eval, not before it.
- The evaluation question set for retrieval + end-to-end QA (separate
  from the spoiler-leakage set).
- Whether ns-2900 Map pages contain anything worth keeping (assumed no).
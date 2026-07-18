# Task: chunker — pages.jsonl → chunks.jsonl

Build the second pipeline stage: parse cached wikitext, harvest labeling
signals, produce clean chunks with deterministic labels where signals
exist. Production code, peer-reviewable.

Read first:
- docs/decisions.md — D02–D11 are the spec; this task implements them.
  Do not re-litigate settled decisions.
- docs/dataset-notes.md (Ingestion gotchas)
- reports/exploration.md — empirical ground for every rule below.

Input: data/pages.jsonl. Output: data/chunks.jsonl + data/chunks_manifest.json.
Module: ingest/chunk_pages.py (CLI: --input, --output, --limit for smoke
runs). Reuse mwparserfromhell (already a dep).

## Pre-strip harvesting (D03 — order matters, all BEFORE strip_code)

1. Infobox templates: detect STRUCTURALLY (template whose params are
   named key=value pairs and which contributes no prose body), not by
   name list. Verification set (must all be detected): character infobox,
   Location infobox, Chapter infobox, object infobox, group infobox,
   book infobox, product infobox, song infobox, species infobox,
   Person infobox, Game infobox, Play infobox, Character.
   Harvest params; remove from wikitext. On ns-112 pages, capture
   |book= (vocab: TNOTW, TWMF, TDOS).
2. Citations, with wikitext positions retained:
   - {{ref}} templates: first param is a book code — closed vocab
     TNOTW, TWMF, TLT, TSROST (log any unknown value, don't guess).
   - <ref> tags: extract body, scan for book-title strings
     ("The Name of the Wind", "The Wise Man's Fear", etc.).
   Remove both from wikitext after harvesting (exploration: <ref>
   bodies otherwise leak into prose as bare URLs).
3. {{quote}} templates: extract quote text + attribution params;
   remove from wikitext; re-emit later as quote chunks.
4. [[Category:...]] links: harvest names, remove (they survive
   strip_code as literal text on 455 pages).
5. Page quality flags: presence of {{stub}}, {{needhelp}},
   {{conjecture}} → booleans.

Then strip_code(), then residue cleanup (targeted regex for {| ... |}
table markup, bare params, HTML comments — the 5 known garbage pages
in reports/exploration.md are the test cases), then drop pages whose
stripped text is under ~20 words (pure-infobox shells; log which).

## Chunking (D04–D06)

- Split by section (h2/h3). Text before the first heading is the lede —
  a first-class section with heading "" (127 pages are lede-only).
- Section > ~380 words (≈500-token proxy): split at paragraph
  boundaries into parts; consecutive parts share the LAST ~40 words of
  the previous part as overlap. NO overlap across section boundaries.
- Tiny sections: keep as-is, no merging.
- Chunk text = "«Page title» § «Section heading»\n\n«content»"
  (self-describing chunks; lede omits the § part).
- Sections whose stripped content is empty (e.g. fan-art galleries):
  emit nothing, count them in the manifest.

Additional chunk types:
- Infobox chunks (D07): one per harvested infobox; text = page-title
  header + params as "key: value" lines (skip image/file params);
  chunk_type="infobox".
- Quote chunks (D08): text = quote body + attribution line;
  chunk_type="quote"; associated with the section it appeared in.

## Chunk schema (every record)

chunk_id            "«pageid»:«section-slug»:«ordinal»" (D10); infobox/
                    quote chunks use slugs "infobox-N" / "quote-N"
page_id, page_title, page_url, ns, revid
section_heading     full path, e.g. "History > Creation War"; "" for lede
chunk_type          "prose" | "infobox" | "quote"
text                final chunk text
content_hash        sha256 of text (change detection, D10)
book_level          1 | 2 | 3 | null
label_provenance    "gold" | "citation" | null   (null → LLM tier later)
citation_codes      list of harvested codes in this chunk, possibly []
is_speculation      bool (D09)
quality_flags       subset of ["stub", "needhelp", "conjecture"]
categories          page categories
word_count          int

## Deterministic labeling (D11)

Code → level: TNOTW→1; TWMF, TLT, TSROST→2; TDOS→3.
1. Gold: ns-112 pages — book from |book= code, else title match, else
   first ~1.5k chars (fallback chain per dataset-notes). ALL chunks of
   that page: that level, provenance "gold".
2. Citation: chunks containing ≥1 harvested citation (template code, or
   <ref> body with a recognized title) → max level among them,
   provenance "citation". Association is positional: a citation belongs
   to the chunk whose source span contained it.
3. Everything else: book_level=null, provenance=null. NO page-level
   inheritance. Plain textual mentions of book titles in prose are NOT
   labels — do not implement a mention rule.
Speculation (D09): heading matches {Speculation, Speculations, Spoilers
about Book Three, Book Three, Possible Seven Word Combinations, Spoilers
for The Doors of Stone} (case-insensitive, trimmed) → is_speculation=
true for that section's chunks; {{conjecture}} pages → true for ALL
their chunks. Trivia is NOT in the matcher.

## Checks (extend ingest/checks.py; auto-run after full runs)

- Schema completeness on every record; chunk_id uniqueness.
- No template markup ({{, |}, [[Category:) in any chunk text; the 5
  known garbage pages come out clean.
- Spot checks: "Kvothe" yields an infobox chunk (from {{Character}});
  "Cealdish Currency" yields ≥1 quote chunk; every ns-112 page's chunks
  are gold-labeled; ~26 gold pages.
- Label coverage report in the manifest AND printed: % of chunks and %
  of words per provenance tier (gold / citation / null), plus
  speculation counts. This re-derives the dataset-notes "~81% needs LLM"
  figure at chunk level — report it prominently.
- Distribution sanity: chunk count, word-count histogram, count of
  max-size splits (expect ~15 affected sections).

## Tests (pytest, synthetic wikitext fixtures — no network, no LLM)

Section splitting incl. lede-only pages; max-size split with overlap
(and no cross-section overlap); structural infobox detection (incl. a
fake infobox name NOT in the known list — must still detect); citation-
to-chunk positional association incl. a multi-citation max-wins case;
speculation matcher (positive, negative incl. "Trivia"); chunk_id
stability under an unrelated-section edit; unknown citation code logged
not guessed.

## Also

Add to docs/dataset-notes.md, top of section 4 (Labeling pipeline), a
2-line note: the {{ref}} TEMPLATE (225 pages / 843 uses, closed vocab
incl. side-story codes) supersedes the <ref>-tag tier sizing below; see
D11 + reports/exploration.md. Do not rewrite the section.

## Hard rules

- pages.jsonl is read-only. Chunker must be deterministic: same input →
  byte-identical chunks.jsonl (fixed ordering; no timestamps inside
  records — manifest carries run metadata).
- No LLM calls, no network, no embeddings, no Elasticsearch, no
  adversarial sampling (next task).
- Surprises (unknown citation codes, undetected infobox-like templates,
  new residue patterns) are logged and reported, never silently handled.
- Verification order: pytest → --limit 30 smoke run, inspect → full run
  → checks → report label coverage + anything that deviated from spec.
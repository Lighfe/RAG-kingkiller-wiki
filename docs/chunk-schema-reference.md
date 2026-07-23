# `data/chunks_labeled.jsonl` — schema reference

Authoritative, as-built documentation of the frozen labeling-pipeline
output (D29): 1,761 records, one JSON object per line. This describes
the file as it actually exists today, not the task-3 spec in
isolation — see [Deviations from the task-3 spec](#deviations-from-the-task-3-spec)
for where they differ. Background: [tasks/03-chunker.md](../tasks/03-chunker.md)
(chunk schema origin), [tasks/05-labeler.md](../tasks/05-labeler.md) and
[docs/decisions/labeling.md](decisions/labeling.md) (D11–D29, labeling
rules), [data/chunks_labeled_manifest.json](../data/chunks_labeled_manifest.json)
(run metadata for this exact file).

Upstream artifact: `data/chunks.jsonl` (1,761 records, `ingest/chunk_pages.py`,
task 3) is the pre-labeling file — identical schema minus the two
fields added by labeling. `data/chunks_labeled.jsonl` (`ingest/label_llm.py`,
task 5 / D14 stage 3) passes gold/citation rows through unchanged and
fills in every `label_provenance=null` row with an LLM label.

## Deviations from the task-3 spec

The task-3 schema (`tasks/03-chunker.md`, reproduced by `chunks.jsonl`)
specifies `book_level: 1 | 2 | 3 | null` and
`label_provenance: "gold" | "citation" | null`, with null meaning
"needs the LLM tier." Labeling (task 5) closes that gap and, in doing
so, changes the schema in three ways:

1. **New value on an existing field**: `label_provenance` gains a
   third value, `"llm"`, not in the original closed set.
2. **New field**: `book_level_raw` — the model's untouched output,
   before the D12 conservative-default override.
3. **New field**: `label_confidence` — the model's categorical
   self-rated confidence (`"low" | "medium" | "high"`).

Consequence: in `chunks_labeled.jsonl`, `book_level` is **never null**
(verified: 0/1761) and `label_provenance` is never null — every
record carries a concrete level and a concrete tier. Null only ever
appears upstream, in `chunks.jsonl`.

Both new fields are present **only** on the 1,258 rows where
`label_provenance == "llm"`; they are simply absent (not `null`) as
keys on the 123 gold and 380 citation rows, since those never went
through the labeler.

A third, related field — `rationale` (the model's one-sentence
justification) — plus a per-call `overridden` boolean exist in the
labeler's intermediate output (see `data/smoke50_labeled.jsonl` for a
sample of that shape) but are **not** persisted into
`chunks_labeled.jsonl`. They're summarized instead into the run
manifest as `confidence_distribution` and `overridden_count`. If you
need a specific chunk's rationale, it isn't in this file.

## Fields

| Field | Type | Values | Meaning | Applies to |
|---|---|---|---|---|
| `chunk_id` | str | `"{page_id}:{slug}:{ordinal}"` | Stable positional ID. `slug` is a section-heading slug, or `infobox-N` / `quote-N` for non-prose chunks (D10). | all |
| `page_id` | int | wiki page ID | Source page identifier. | all |
| `page_title` | str | free text | Source page title, also the header line prepended to `text`. | all |
| `page_url` | str | URL | Canonical fandom.com URL for the source page. | all |
| `ns` | int | `0`, `112` | MediaWiki namespace: `0` = main article (1,638 chunks, 93.0%), `112` = `Chapter:` namespace (123 chunks, 7.0%). | all |
| `revid` | int | wiki revision ID | Revision the chunk was extracted from. | all |
| `section_heading` | str | free text, `""`, or `"Parent > Child"` | Full heading path; `""` for the lede (856 chunks) and for infobox/quote chunks emitted outside a titled section. | all |
| `chunk_type` | str | `"prose"` (1,318, 74.8%) / `"infobox"` (245, 13.9%) / `"quote"` (198, 11.2%) | What kind of content the chunk holds. Closed set — matches spec exactly. | all |
| `text` | str | free text | Final chunk body: `"{page_title}[ § {section_heading}]\n\n{content}"`. The header line counts toward `word_count`. | all |
| `content_hash` | str | 64-char lowercase hex | sha256 of `text`, for change detection. | all |
| `book_level` | int | `1`, `2`, `3` | Highest book whose content this chunk discloses (1=TNOTW, 2=TWMF/side-stories, 3=TDOS/unpublished). **Never null in this file** — see deviations above. | all |
| `label_provenance` | str | `"gold"` (123, 7.0%) / `"citation"` (380, 21.6%) / `"llm"` (1,258, 71.4%) | How `book_level` was determined: gold = ns-112 chapter's own `\|book=`; citation = a harvested citation code in the chunk; llm = D14 stage-3 labeling pass. **Never null in this file.** | all |
| `citation_codes` | list[str] | subset of `{TNOTW, TWMF, TLT, TSROST, TDOS}`, possibly `[]` | Harvested book codes found in this chunk (`{{ref}}` template or `<ref>` tag title match). 1,380/1,761 chunks (78.4%) have `[]`; 51 have 2 codes; none have 3+. Only drives `book_level` when `label_provenance == "citation"`. | all, mostly quote/prose |
| `is_speculation` | bool | `true` (135, 7.7%) / `false` (1,626, 92.3%) | Section matched the speculation-heading list (D09), or page carried `{{conjecture}}`. Independent of `book_level`. | all |
| `quality_flags` | list[str] | subset of `{"stub", "needhelp", "conjecture"}`, possibly `[]` | Page-level quality template flags, identical across every chunk of a page. Counts (chunk-level, so a flag on a multi-chunk page counts once per chunk): `needhelp` 397, `stub` 76, `conjecture` 28; 1,276 chunks (72.5%) have none. | all |
| `categories` | list[str] | free text, possibly `[]` (2 chunks) | `[[Category:...]]` names harvested from the page; identical across every chunk of a page. | all |
| `word_count` | int | ≥3 | `len(text.split())`, i.e. includes the header line's words. Chunker target is a ~380-word split ceiling (D05); a handful of prose chunks exceed it substantially (max 1,114 words, "Siaru § Vocabulary > Words") because splitting only happens at paragraph boundaries — a single giant paragraph (word list, song list) can't be split further. | all |
| `book_level_raw` | int | `1`, `2`, `3` | The LLM's raw `book_level` before the D12 conservative-default override. Differs from `book_level` only when `label_confidence == "low"` (7 rows), and only 5 of those actually changed value — 2 were already raw level 3. | `llm` rows only (1,258) |
| `label_confidence` | str | `"low"` (7) / `"medium"` (50) / `"high"` (1,201) | Model's categorical self-rated confidence. `"low"` triggers the conservative-default override to `book_level=3` regardless of `book_level_raw`. | `llm` rows only (1,258) |

## Worked examples

### prose

```json
{
  "chunk_id": "2049:lede:0",
  "page_id": 2049,
  "page_title": "Ambrose Jakis",
  "page_url": "https://kingkiller.fandom.com/wiki/Ambrose_Jakis",
  "ns": 0,
  "revid": 31531,
  "section_heading": "",
  "chunk_type": "prose",
  "text": "Ambrose Jakis\n\nAmbrose Jakis is the firstborn son of Baron Jakis, a powerful and wealthy nobleman from Vintas. He is a major antagonist to Kvothe throughout his time at the University.",
  "content_hash": "6f25bf7636d683ce174e498ef7069980cd969816a1450b43957ee5ef452d9537",
  "book_level": 1,
  "label_provenance": "llm",
  "citation_codes": [],
  "is_speculation": false,
  "quality_flags": [],
  "categories": ["Major Characters", "Nobility", "Characters", "Vintas", "University students", "Scrivs", "Musicians"],
  "word_count": 31,
  "book_level_raw": 1,
  "label_confidence": "high"
}
```
Lede chunk (`section_heading=""`), null-provenance at task-3 time, filled by the LLM tier — hence the two extra fields. This is the chunk referenced in D28's field-order bug writeup.

### infobox

```json
{
  "chunk_id": "12344:infobox-0:0",
  "page_id": 12344,
  "page_title": "Chapter:A Beautiful Day",
  "page_url": "https://kingkiller.fandom.com/wiki/Chapter%3AA_Beautiful_Day",
  "ns": 112,
  "revid": 31181,
  "section_heading": "",
  "chunk_type": "infobox",
  "text": "Chapter:A Beautiful Day\n\nbook: TNOTW\narc: Frame story\nprevious: A Place for Demons\nnext: Wood and Word\nlocation: Near Abbott's Ford",
  "content_hash": "27383f842396f081de219c5be311041d5750822fdfb93375b278e0d896ce2498",
  "book_level": 1,
  "label_provenance": "gold",
  "citation_codes": [],
  "is_speculation": false,
  "quality_flags": [],
  "categories": ["Chapters", "Frame story"],
  "word_count": 21
}
```
`ns=112` chapter infobox: gold-labeled directly from its own `book:` param (D07/D11), so `book_level_raw`/`label_confidence` don't apply — this row never touches the labeler.

### quote

```json
{
  "chunk_id": "2334:quote-0:0",
  "page_id": 2334,
  "page_title": "Trapis",
  "page_url": "https://kingkiller.fandom.com/wiki/Trapis",
  "ns": 0,
  "revid": 30394,
  "section_heading": "",
  "chunk_type": "quote",
  "text": "Trapis\n\nWhat what. Hush hush.\n— Trapis",
  "content_hash": "0dea5ad76fec93d5a7f82e2757069c2b0ff6ecf2c3ee19a2051cd78368906c8f",
  "book_level": 1,
  "label_provenance": "citation",
  "citation_codes": ["TNOTW"],
  "is_speculation": false,
  "quality_flags": [],
  "categories": ["Characters", "Minor Characters", "Commonwealth", "Characters who go barefoot"],
  "word_count": 7
}
```
Citation-provenance: a `{{ref}}`/`<ref>` in the source wikitext carried the `TNOTW` code, positionally associated with this quote chunk (D11), driving `book_level=1` without ever reaching the labeler.

## Distributions

All figures computed directly from `data/chunks_labeled.jsonl` (n=1,761), 2026-07-23.

### book_level — overall and by provenance

This closes out D29's wrap-up item.

| book_level | overall | gold (n=123) | citation (n=380) | llm (n=1,258) |
|---|---|---|---|---|
| 1 | 1,188 (67.5%) | 99 (80.5%) | 192 (50.5%) | 897 (71.3%) |
| 2 | 541 (30.7%) | 19 (15.4%) | 187 (49.2%) | 335 (26.6%) |
| 3 | 32 (1.8%) | 5 (4.1%) | 1 (0.3%) | 26 (2.1%) |

Provenance mix overall: gold 123 (7.0%), citation 380 (21.6%), llm 1,258 (71.4%).

### chunk_type

| chunk_type | count | % |
|---|---|---|
| prose | 1,318 | 74.8% |
| infobox | 245 | 13.9% |
| quote | 198 | 11.2% |

### word_count by chunk_type (p50 / p90 / p99)

| chunk_type | n | min | p50 | p90 | p99 | max |
|---|---|---|---|---|---|---|
| prose | 1,318 | 4 | 63.5 | 255.3 | 394.5 | 1,114 |
| infobox | 245 | 3 | 16.0 | 29.0 | 53.6 | 84 |
| quote | 198 | 6 | 23.0 | 54.3 | 87.4 | 104 |
| **all** | 1,761 | 3 | 41.0 | 218.0 | 381.4 | 1,114 |

### is_speculation

`true`: 135 (7.7%) — `false`: 1,626 (92.3%).

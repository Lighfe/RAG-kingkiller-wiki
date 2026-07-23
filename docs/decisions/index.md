# Decision log — index

Append-only decision log, split by topic 2026-07-22 (was a single
docs/decisions.md; see docs/decisions.md for the redirect stub). One
entry per settled decision; date, decision, one-line why — full text
lives in the linked file. Corpus/licensing/labeling-signal background:
docs/kingkiller-dataset-notes.md.

Inferred split (content-based, contiguous by D-number): D01–D16
pipeline (ingestion/chunking mechanics + initial labeler setup),
D17 evaluation (the eval-hierarchy decision), D18–D29 labeling (the
LLM labeler's iterative prompt/schema development plus the full pass
it authorized). Flag if these
boundaries should fall elsewhere — it's a pure move, trivial to redo.

| # | Topic | File |
|---|---|---|
| D01 | Ingestion tool: plain Python script (no dlt) | [pipeline](pipeline.md) |
| D02 | Extraction: parse cached wikitext locally (mwparserfromhell) | [pipeline](pipeline.md) |
| D03 | Pre-strip harvesting order (infobox → refs → quotes → categories → strip) | [pipeline](pipeline.md) |
| D04 | Chunk unit: section-aware; lede is a first-class section | [pipeline](pipeline.md) |
| D05 | Max chunk size 500 tokens; split at paragraph boundaries | [pipeline](pipeline.md) |
| D06 | Overlap: none across sections; ~50 tokens within a split | [pipeline](pipeline.md) |
| D07 | Infoboxes: separate chunks, own book_level | [pipeline](pipeline.md) |
| D08 | Quotes: included as chunk_type=quote with attribution | [pipeline](pipeline.md) |
| D09 | Speculation: boolean is_speculation, separate from book_level | [pipeline](pipeline.md) |
| D10 | Chunk ID: positional, content hash stored alongside | [pipeline](pipeline.md) |
| D11 | Labels are chunk-level; signal cascade (gold → citation → LLM) | [pipeline](pipeline.md) |
| D12 | LLM labeler: gpt-5.4-mini, Pydantic structured output | [pipeline](pipeline.md) |
| D13 | Labeler acceptance thresholds (recall/accuracy) — refined in D24 | [pipeline](pipeline.md) |
| D14 | Pipeline staging: artifact per stage, gitignored + manifest | [pipeline](pipeline.md) |
| D15 | Maintenance banners match structural infobox detection | [pipeline](pipeline.md) |
| D16 | Oversized paragraphs (>380w) stay unsplit | [pipeline](pipeline.md) |
| D17 | Evaluation hierarchy: groundedness primary, spoiler gate a specialization | [evaluation](evaluation.md) |
| D18 | Infobox spoiler judgment: static vs relational — SUPERSEDED by D21 | [labeling](labeling.md) |
| D19 | Bare book-title mentions don't escalate — refined in D21/D22 | [labeling](labeling.md) |
| D20 | Frame-story clarification: presence alone isn't book_level=3 | [labeling](labeling.md) |
| D21 | Infobox spoiler judgment, scoped to Book-1-reachable entities (replaces D18) | [labeling](labeling.md) |
| D22 | D19 refinement: self-identification of book membership escalates | [labeling](labeling.md) |
| D23 | Book-level-3 confidence calibration: needs something specific to ground it | [labeling](labeling.md) |
| D24 | Gold-set accuracy denominator excludes info-free-by-construction chunks | [labeling](labeling.md) |
| D25 | Book-level judges disclosure, not narrative significance | [labeling](labeling.md) |
| D26 | Entity-introduction floor is chunk-type-agnostic | [labeling](labeling.md) |
| D27 | Manual ground-truth corrections to manual_labels.jsonl | [labeling](labeling.md) |
| D28 | Labeler schema: rationale generated before book_level/confidence | [labeling](labeling.md) |
| D29 | Full LLM labeling pass executed: $1.6811 actual, chunks_labeled.jsonl frozen | [labeling](labeling.md) |

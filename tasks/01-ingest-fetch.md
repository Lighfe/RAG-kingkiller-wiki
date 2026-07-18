# Task: ingestion stage 1 — fetch & cache the wiki corpus

Build the first stage of the ingestion pipeline: fetch all content pages
from the Kingkiller Chronicle Fandom wiki via the MediaWiki API and cache
them locally as raw wikitext. This is production code for a graded,
peer-reviewed portfolio project — clarity over cleverness.

Before writing code, read:
- docs/dataset-notes.md (sections: Source & licensing, Corpus shape,
  Ingestion gotchas) — these constraints are non-negotiable.
- https://www.mediawiki.org/wiki/API:Allpages
- https://www.mediawiki.org/wiki/API:Continue
- https://www.mediawiki.org/wiki/API:Revisions
- https://www.mediawiki.org/wiki/API:Etiquette

## Scope

IN: page enumeration, content fetch, local jsonl cache, data-quality
checks, unit tests, README section.
OUT (do not build, do not scaffold): wikitext parsing, chunking,
labeling, embeddings, Elasticsearch, Docker. If you're tempted to "just
add" any of these, stop.

## Spec

Module layout: `ingest/` package with `fetch_pages.py` (fetch logic +
CLI) and `checks.py` (data-quality checks). Runnable as
`uv run python -m ingest.fetch_pages`.

### Enumeration
- Endpoint: https://kingkiller.fandom.com/api.php — assert this host in
  code; refuse any other.
- `list=allpages`, looped over namespaces 0 and 112 separately
  (`apnamespace` is single-valued — no pipe syntax), 
  `apfilterredir=nonredirects`, `aplimit=max`.
- Handle continuation generically: echo back ALL keys of the `continue`
  object as query params until it's absent. Do not hardcode `apcontinue`.
- Use `format=json&formatversion=2` everywhere.

### Content fetch
- `prop=revisions`, `rvprop=content|ids|timestamp`, `rvslots=main`,
  batched `pageids` (max 50 per request).
- Politeness: User-Agent
  "RAG-kingkiller-wiki-capstone/0.1 (https://github.com/Lighfe; LLM
  Zoomcamp capstone)"; sleep ~0.5s between requests; send `maxlag=5`
  and on a maxlag error wait and retry; exponential backoff (max 5
  tries) on 429/5xx.

### Output
- `data/pages.jsonl` — one JSON object per page:
  `pageid, ns, title, revid, rev_timestamp, wikitext, fetched_at`.
- `data/manifest.json` — run metadata: fetch timestamp, per-namespace
  page counts, total, request count, duration, tool version.
- Atomic write: write to a temp file in `data/`, rename on success.
- Verify `data/` is in .gitignore; add it if missing.
- Store raw wikitext exactly as returned. No parsing, no stripping.

### CLI
- `--limit N` (smoke runs: stop after N pages total), `--output DIR`
  (default `data/`). Use argparse and logging (INFO level: progress,
  per-namespace counts, warnings).

### Data-quality checks (`ingest/checks.py`, run automatically after a
full fetch, also runnable standalone against an existing pages.jsonl)
- Page counts: expected ~438 (ns 0) and 26 (ns 112) per the 2026-07
  audit. The wiki is live, so warn (don't fail) on drift up to 5%;
  fail beyond that.
- No duplicate pageids.
- Wikitext non-empty for every page; log count of pages under 200 chars
  (expected — stubs exist; do NOT drop them, filtering happens
  downstream).
- Content sanity: wikitext (not rendered HTML) — check that a majority
  of ns-112 pages contain `{{` template markup and at least one contains
  `|book` (case/space tolerant). If ns-112 pages look rendered instead
  of raw, that's a fetch bug — fix it, don't relax the check.
- Print a summary report; non-zero exit code on failure.

### Tests (pytest, mocked HTTP — no network)
- Continuation loop: multi-page enumeration terminates and collects all
  pages, including when `continue` carries multiple keys.
- Batching: pageids split into chunks of ≤50.
- Namespace loop: both namespaces enumerated, results merged.
- Host assertion: constructing the fetcher against any other host raises.
- One optional integration test hitting the real API for a single small
  batch, behind `@pytest.mark.network`, excluded by default.

### Dependencies
Add in a single call: `uv add requests` and `uv add --dev pytest
requests-mock` (or responses — your choice, say why in the commit).
Nothing else without a stated reason.

### README
Add a "Data & ingestion" section: what the pipeline does, how to run a
smoke run and a full run, expected runtime/request count, the CC BY-SA
3.0 attribution note, and why the data is not committed (share-alike).

## Verification protocol (do these in order, report results)
1. `uv run pytest` — all green.
2. Smoke run: `--limit 25`, inspect output records manually.
3. Full run against the live API.
4. Checks pass on the full output.
5. Report: final counts per namespace, total requests, runtime, any
   warnings, and anything that deviated from this spec.

## Hard rules
- If the live API's behavior contradicts this spec or dataset-notes.md
  (continuation shape, counts wildly off, missing fields), STOP,
  document what you observed, and end with an open question — do not
  invent a workaround.
- Meaningful commits as you go (setup / fetch logic / checks / tests /
  docs), not one squash.
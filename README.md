# RAG-kingkiller-wiki

A retrieval-augmented QA system over the Kingkiller Chronicle Fandom wiki
with spoiler-aware, access-controlled retrieval. LLM Zoomcamp capstone
project.

## Data & ingestion

The corpus is the text of the [Kingkiller Chronicle Fandom wiki](https://kingkiller.fandom.com)
— 464 content pages (438 main-namespace articles plus 26 `Chapter:` pages),
about 157k words of wikitext.

Ingestion stage 1 (`ingest/fetch_pages.py`) enumerates all non-redirect
pages in namespaces 0 and 112 via the MediaWiki API, fetches each page's
latest-revision **raw wikitext** (no parsing or stripping — labeling
signals like infobox `|book=` codes only exist in the markup), and caches
everything locally:

- `data/pages.jsonl` — one record per page:
  `pageid, ns, title, revid, rev_timestamp, wikitext, fetched_at`
- `data/manifest.json` — run metadata (timestamp, per-namespace counts,
  request count, duration)

After a full fetch, data-quality checks (`ingest/checks.py`) run
automatically: page counts against the audited corpus shape (±5% drift
tolerated with a warning — the wiki is live), duplicate pageids, empty
pages, and a raw-wikitext sanity check on the chapter pages.

### Running it

```sh
# smoke run: first 25 pages only, checks skipped
uv run python -m ingest.fetch_pages --limit 25

# full run (all 464 pages, then data-quality checks)
uv run python -m ingest.fetch_pages

# checks standalone, against an existing cache
uv run python -m ingest.checks data/pages.jsonl

# unit tests (HTTP mocked; add `-m network` for one live-API test)
uv run pytest
```

A full run takes well under a minute: ~13 API requests (2 enumeration
requests + 10 content batches of ≤50 pages, plus the odd continuation
reply), throttled to one request per 0.5 s as a politeness measure.

### Licensing & why the data is not committed

The wiki's text is licensed [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/).
This project credits the Kingkiller Chronicle Fandom wiki and its
contributors as the source of all corpus text; the app cites source
pages per answer.

Because of the license's **share-alike** clause, the corpus itself is
not redistributed: `data/` is gitignored, and the repo ships only the
ingestion pipeline. Anyone can rebuild the identical dataset with the
commands above. The fetcher is hard-locked to `kingkiller.fandom.com` —
the separately-run `kingkiller.wiki` is CC BY-**NC**-SA and
license-incompatible, so the code refuses any other host by design.

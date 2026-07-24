"""Ingestion stage 1: fetch & cache the wiki corpus as raw wikitext.

Enumerates all content pages (namespaces 0 and 112) of the Kingkiller
Chronicle Fandom wiki via the MediaWiki API, fetches their latest-revision
wikitext, and caches everything to ``data/pages.jsonl`` plus a run manifest.
Raw wikitext only — parsing, chunking and labeling happen downstream.

Run: ``uv run python -m ingest.fetch_pages [--limit N] [--output DIR]``
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

ALLOWED_HOST = "kingkiller.fandom.com"
API_URL = f"https://{ALLOWED_HOST}/api.php"
USER_AGENT = (
    "RAG-kingkiller-wiki-capstone/0.1 "
    "(https://github.com/Lighfe; LLM Zoomcamp capstone)"
)
CONTENT_NAMESPACES = (0, 112)
BATCH_SIZE = 50  # API cap for prop=revisions with content
REQUEST_DELAY_S = 0.5
MAXLAG_S = 5
MAX_TRIES = 5
TOOL_VERSION = "0.1"

log = logging.getLogger(__name__)


class WikiFetcher:
    """Polite MediaWiki API client, locked to the Kingkiller Fandom wiki."""

    def __init__(
        self,
        api_url: str = API_URL,
        delay_s: float = REQUEST_DELAY_S,
        session: requests.Session | None = None,
    ):
        host = urlparse(api_url).hostname
        if host != ALLOWED_HOST:
            # kingkiller.wiki is a separate CC BY-NC-SA wiki and must never
            # be mixed into this CC BY-SA corpus.
            raise ValueError(
                f"refusing host {host!r}: this fetcher only talks to {ALLOWED_HOST}"
            )
        self.api_url = api_url
        self.delay_s = delay_s
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.request_count = 0
        self._last_request = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.delay_s:
            time.sleep(self.delay_s - elapsed)
        self._last_request = time.monotonic()

    def _get(self, params: dict) -> dict:
        """One API GET: politeness delay, maxlag, retries on 429/5xx."""
        full = {"format": "json", "formatversion": 2, "maxlag": MAXLAG_S, **params}
        for attempt in range(MAX_TRIES):
            self._throttle()
            resp = self.session.get(self.api_url, params=full, timeout=60)
            self.request_count += 1

            if resp.status_code == 429 or resp.status_code >= 500:
                wait = max(2**attempt, float(resp.headers.get("Retry-After", 0)))
                log.warning(
                    "HTTP %d, retrying in %.0fs (try %d/%d)",
                    resp.status_code, wait, attempt + 1, MAX_TRIES,
                )
                time.sleep(wait)
                continue
            resp.raise_for_status()

            payload = resp.json()
            if "warnings" in payload:
                log.warning("API warnings: %s", payload["warnings"])
            error = payload.get("error")
            if error is not None:
                if error.get("code") == "maxlag":
                    wait = float(resp.headers.get("Retry-After", MAXLAG_S))
                    log.warning(
                        "server lagged, waiting %.0fs (try %d/%d)",
                        wait, attempt + 1, MAX_TRIES,
                    )
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"API error: {error}")
            return payload
        raise RuntimeError(f"giving up after {MAX_TRIES} tries: {params}")

    def _query(self, params: dict):
        """Yield successive ``query`` payloads, following continuation.

        Echoes back every key of the ``continue`` object verbatim — the set
        of keys is module-specific and not ours to hardcode.
        """
        cont: dict = {}
        while True:
            payload = self._get({**params, **cont})
            yield payload.get("query", {})
            cont = payload.get("continue") or {}
            if not cont:
                return

    def list_pages(self, namespace: int) -> list[dict]:
        """Enumerate all non-redirect pages of one namespace.

        ``apnamespace`` is single-valued (no pipe syntax), hence one call
        per namespace.
        """
        params = {
            "action": "query",
            "list": "allpages",
            "apnamespace": namespace,
            "apfilterredir": "nonredirects",
            "aplimit": "max",
        }
        pages: list[dict] = []
        for query in self._query(params):
            pages.extend(query.get("allpages", []))
        return pages

    def fetch_wikitext(self, pageids: list[int]) -> list[dict]:
        """Fetch latest-revision wikitext for the given pages, batched ≤50."""
        records: list[dict] = []
        batches = [
            pageids[i : i + BATCH_SIZE] for i in range(0, len(pageids), BATCH_SIZE)
        ]
        for i, batch in enumerate(batches, start=1):
            records.extend(self._fetch_batch(batch))
            log.info("content batch %d/%d done (%d pages)", i, len(batches), len(records))
        return records

    def _fetch_batch(self, pageids: list[int]) -> list[dict]:
        params = {
            "action": "query",
            "prop": "revisions",
            "rvprop": "content|ids|timestamp",
            "rvslots": "main",
            "pageids": "|".join(str(p) for p in pageids),
        }
        # A full-content reply for 50 pages may be split across several
        # responses; merge parts until continuation ends.
        by_id: dict[int, dict] = {}
        for query in self._query(params):
            for page in query.get("pages", []):
                merged = by_id.setdefault(page["pageid"], page)
                if "revisions" not in merged and "revisions" in page:
                    merged["revisions"] = page["revisions"]

        fetched_at = _utcnow()
        records = []
        for pageid in pageids:
            page = by_id.get(pageid)
            if page is None or page.get("missing") or not page.get("revisions"):
                log.warning("page %s has no content in response, skipping", pageid)
                continue
            rev = page["revisions"][0]
            records.append(
                {
                    "pageid": page["pageid"],
                    "ns": page["ns"],
                    "title": page["title"],
                    "revid": rev["revid"],
                    "rev_timestamp": rev["timestamp"],
                    "wikitext": rev["slots"]["main"]["content"],
                    "fetched_at": fetched_at,
                }
            )
        return records

    def fetch_redirects(self, titles: list[str]) -> dict[str, str]:
        """Resolve titles to their final redirect target, if any (task 6b).

        One query per batch of <=50 titles (``redirects=1``), reusing this
        fetcher's throttle/retry/session — no new polling pattern. Threads
        each *original* title through the API's own case/underscore
        normalization and any redirect chain, but only records an entry
        when a real ``redirects`` hop actually fired — a title that was
        merely re-cased (``normalized``) without ever being a redirect is
        left out, same as one that's missing entirely. Callers must not
        assume every input title comes back resolved.
        """
        resolved: dict[str, str] = {}
        batches = [titles[i : i + BATCH_SIZE] for i in range(0, len(titles), BATCH_SIZE)]
        for i, batch in enumerate(batches, start=1):
            payload = self._get(
                {"action": "query", "titles": "|".join(batch), "redirects": 1}
            )
            query = payload.get("query", {})
            normalized = {e["from"]: e["to"] for e in query.get("normalized", [])}
            redirects = {e["from"]: e["to"] for e in query.get("redirects", [])}
            for title in batch:
                current = normalized.get(title, title)
                followed = False
                for _ in range(5):  # bound pathological redirect chains
                    nxt = redirects.get(current)
                    if nxt is None:
                        break
                    current = nxt
                    followed = True
                if followed:
                    resolved[title] = current
            log.info("redirect batch %d/%d done (%d titles queried)", i, len(batches), len(batch))
        return resolved

    def fetch_all(
        self,
        namespaces: tuple[int, ...] = CONTENT_NAMESPACES,
        limit: int | None = None,
    ) -> list[dict]:
        """Enumerate and fetch every content page across the namespaces."""
        listed: list[dict] = []
        for ns in namespaces:
            pages = self.list_pages(ns)
            log.info("namespace %d: %d pages enumerated", ns, len(pages))
            listed.extend(pages)
        if limit is not None:
            listed = listed[:limit]
            log.info("--limit %d: fetching only the first %d pages", limit, len(listed))
        return self.fetch_wikitext([p["pageid"] for p in listed])


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_atomic(path: Path, text: str) -> None:
    """Write via temp file + rename so a crash can't leave a torn file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _ensure_gitignored(output_dir: Path) -> None:
    """CC BY-SA share-alike: the corpus must never end up in git."""
    gitignore = Path(".gitignore")
    if not gitignore.exists():
        return
    try:
        rel = output_dir.resolve().relative_to(Path.cwd()).as_posix()
    except ValueError:
        return  # outside the repo, git can't pick it up
    lines = gitignore.read_text(encoding="utf-8").splitlines()
    if any(line.strip().rstrip("/") == rel for line in lines):
        return
    with gitignore.open("a", encoding="utf-8") as f:
        f.write(f"{rel}/\n")
    log.warning("added %s/ to .gitignore (share-alike: data stays out of git)", rel)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch all Kingkiller wiki content pages as raw wikitext."
    )
    parser.add_argument(
        "--limit", type=int, default=None, metavar="N",
        help="stop after N pages total (for smoke runs)",
    )
    parser.add_argument(
        "--output", type=Path, default=Path("data"), metavar="DIR",
        help="output directory (default: data/)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    started_at = _utcnow()
    t0 = time.monotonic()
    fetcher = WikiFetcher()
    records = fetcher.fetch_all(limit=args.limit)
    duration_s = time.monotonic() - t0

    ns_counts = Counter(r["ns"] for r in records)
    for ns in sorted(ns_counts):
        log.info("namespace %d: %d pages fetched", ns, ns_counts[ns])

    pages_path = args.output / "pages.jsonl"
    _write_atomic(
        pages_path,
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
    )
    manifest = {
        "fetched_at": started_at,
        "duration_s": round(duration_s, 1),
        "pages_by_namespace": {str(ns): n for ns, n in sorted(ns_counts.items())},
        "pages_total": len(records),
        "request_count": fetcher.request_count,
        "limit": args.limit,
        "api_url": fetcher.api_url,
        "tool_version": TOOL_VERSION,
    }
    _write_atomic(args.output / "manifest.json", json.dumps(manifest, indent=2) + "\n")
    _ensure_gitignored(args.output)
    log.info(
        "wrote %d pages to %s (%d requests, %.1fs)",
        len(records), pages_path, fetcher.request_count, duration_s,
    )

    if args.limit is None:
        from ingest.checks import main as checks_main

        return checks_main([str(pages_path)])
    log.info("partial fetch (--limit): skipping data-quality checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())

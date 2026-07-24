"""Task 6b: close the redirect gap left in the entity graph (D36) via one
cached API call, batched (<=50 titles) through the existing WikiFetcher.

Resolves the unique unresolved Stage-A link targets from
``ingest.entity_graph.stage_a`` against the live wiki's redirect table and
caches the result to ``data/redirects.json``: {from_title: to_title}, built
only from titles the API actually reports under ``redirects`` (see
``WikiFetcher.fetch_redirects``) — titles that come back missing or merely
re-cased are genuinely unresolved (typo, non-wiki reference) and are NOT
assumed to be redirects.

One-time fetch: everything downstream (``ingest.entity_graph``'s re-run)
runs offline against this cached file, same as the rest of the pipeline
(D02) — this closes the one gap D36 left open, it doesn't reopen the
offline-afterward principle.

Run: ``uv run python -m ingest.fetch_redirects``
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from ingest.entity_graph import load_jsonl, stage_a
from ingest.fetch_pages import WikiFetcher, _write_atomic

TOOL_VERSION = "0.1"

log = logging.getLogger(__name__)


def unresolved_targets(pages_path: Path) -> list[str]:
    pages = load_jsonl(pages_path)
    return sorted(stage_a(pages).unresolved)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch & cache the redirect map for task 6's unresolved link targets (task 6b)."
    )
    parser.add_argument("--pages", type=Path, default=Path("data/pages.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/redirects.json"))
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not args.pages.exists():
        sys.exit(f"error: {args.pages} not found")

    titles = unresolved_targets(args.pages)
    log.info("%d unique unresolved targets to look up", len(titles))

    t0 = time.monotonic()
    fetcher = WikiFetcher()
    redirect_map = fetcher.fetch_redirects(titles)
    duration_s = time.monotonic() - t0

    still_unresolved = sorted(set(titles) - set(redirect_map))
    log.info(
        "%d/%d resolved via redirect lookup; %d still unresolved",
        len(redirect_map), len(titles), len(still_unresolved),
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    _write_atomic(
        args.output,
        json.dumps(redirect_map, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
    )

    manifest = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pages_input": str(args.pages),
        "tool_version": TOOL_VERSION,
        "duration_s": round(duration_s, 1),
        "queried": len(titles),
        "resolved": len(redirect_map),
        "still_unresolved_count": len(still_unresolved),
        "still_unresolved": still_unresolved,
        "request_count": fetcher.request_count,
        "api_url": fetcher.api_url,
    }
    _write_atomic(
        args.output.with_name(args.output.stem + "_manifest.json"),
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
    )
    print(f"resolved {len(redirect_map)}/{len(titles)} unresolved targets via redirect lookup")
    print(f"still unresolved ({len(still_unresolved)}): {still_unresolved}")
    log.info("wrote %s (%d entries, %.1fs)", args.output, len(redirect_map), duration_s)
    return 0


if __name__ == "__main__":
    sys.exit(main())

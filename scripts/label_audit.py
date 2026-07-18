"""Label-signal audit for the Kingkiller Chronicle Fandom wiki.

Fetches all content pages (wikitext + categories) via the MediaWiki API,
then reports how many pages / how much text volume carry each kind of
book-attribution signal. This decides our spoiler-labeling policy:
if the "no signal" tier exceeds ~15% of text volume, we add an LLM
labeling pass (pre-registered decision, 2026-07).

Usage:
    uv run python scripts/label_audit.py            # uses cache if present
    uv run python scripts/label_audit.py --refresh  # force re-fetch

Output: summary tables to stdout; raw pages cached in data/pages.jsonl
(gitignored -- CC BY-SA content stays out of the repo).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

import requests

# --- Config -----------------------------------------------------------------

BASE_HOST = "kingkiller.fandom.com"  # Fandom wiki ONLY (CC BY-SA).
API_URL = f"https://{BASE_HOST}/api.php"
USER_AGENT = (
    "KingkillerRAG-label-audit/0.1 "
    "(educational capstone project; contact via GitHub Lighfe)"
)
SLEEP_BETWEEN_REQUESTS = 0.5  # seconds; be a polite API citizen
BATCH_SIZE = 50               # max titles per prop query for anon users
CACHE_PATH = Path("data/pages.jsonl")

# Book patterns: order matters for reporting, keys are our book levels.
# Each entry: (label, [regex patterns matched case-insensitively unless noted])
BOOK_PATTERNS: dict[str, list[str]] = {
    "book1_notw": [
        r"the\s+name\s+of\s+the\s+wind",
        r"\bNotW\b", r"\bNOTW\b", r"\bTNOTW\b",
    ],
    "book2_wmf": [
        r"the\s+wise\s+man[\u2019']s\s+fear",
        r"\bWMF\b", r"\bTWMF\b",
    ],
    "book3_dos": [
        r"the\s+doors\s+of\s+stone",
        r"\bDoS\b", r"\bTDOS\b",
    ],
    "side_stories": [
        r"the\s+slow\s+regard\s+of\s+silent\s+things",
        r"slow\s+regard",
        r"(?:the\s+)?lightning\s+tree",
        r"narrow\s+road(?:\s+between\s+desires)?",
        r"old\s+holly",
        r"\bTSROST\b",
        r"\bTLT\b",
    ]
}

# Infobox / template params that might encode appearances. We histogram
# whatever we find; these are the ones we grep for.
APPEARANCE_PARAM_RE = re.compile(
    r"^\s*\|\s*(first_?appear\w*|appear\w*|books?|debut|novels?)\s*=\s*(.*)$",
    re.IGNORECASE | re.MULTILINE,
)

REF_RE = re.compile(r"<ref[^>/]*>(.*?)</ref>", re.IGNORECASE | re.DOTALL)
CHAPTER_PREFIX = "Chapter:"


# --- Fetching ---------------------------------------------------------------


def api_get(session: requests.Session, params: dict) -> dict:
    params = {"format": "json", "formatversion": "2", **params}
    resp = session.get(API_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"API error: {data['error']}")
    time.sleep(SLEEP_BETWEEN_REQUESTS)
    return data


def fetch_site_info(session: requests.Session) -> None:
    """Print namespaces + statistics so we see the wiki's real shape."""
    data = api_get(
        session,
        {"action": "query", "meta": "siteinfo", "siprop": "namespaces|statistics"},
    )
    stats = data["query"]["statistics"]
    print(f"Site statistics: {stats.get('articles')} articles, "
          f"{stats.get('pages')} total pages")
    print("Content-relevant namespaces (id: name):")
    for ns in data["query"]["namespaces"].values():
        ns_id = ns.get("id")
        if ns_id is not None and ns_id >= 0 and ns_id % 2 == 0:  # skip talk
            name = ns.get("name") or "(main)"
            content_flag = " [content]" if ns.get("content") else ""
            print(f"  {ns_id}: {name}{content_flag}")
    print()


def fetch_all_titles(
    session: requests.Session, namespaces: tuple[int, ...] = (0, 112)
) -> list[dict]:
    """All non-redirect pages in the given content namespaces.

    Note: allpages enumerates a single namespace per query
    (apnamespace is not multi-value), so we loop.
    """
    titles: list[dict] = []
    for ns in namespaces:
        params = {
            "action": "query",
            "list": "allpages",
            "apnamespace": str(ns),
            "apfilterredir": "nonredirects",
            "aplimit": "500",
        }
        cont: dict = {}
        while True:
            data = api_get(session, {**params, **cont})
            batch = data["query"]["allpages"]
            titles.extend(batch)
            if "continue" not in data:
                break
            cont = data["continue"]
        print(f"  namespace {ns}: running total {len(titles)} pages", file=sys.stderr)
    return titles


def fetch_pages(session: requests.Session, pages: list[dict]) -> list[dict]:
    """Wikitext + categories for each page, batched by pageid."""
    out: list[dict] = []
    ids = [str(p["pageid"]) for p in pages]
    for i in range(0, len(ids), BATCH_SIZE):
        batch = ids[i : i + BATCH_SIZE]
        cont: dict = {}
        merged: dict[int, dict] = {}
        while True:
            data = api_get(
                session,
                {
                    "action": "query",
                    "pageids": "|".join(batch),
                    "prop": "revisions|categories",
                    "rvprop": "content",
                    "rvslots": "main",
                    "cllimit": "max",
                    **cont,
                },
            )
            for page in data["query"]["pages"]:
                entry = merged.setdefault(
                    page["pageid"],
                    {"pageid": page["pageid"], "title": page["title"],
                     "wikitext": "", "categories": []},
                )
                revs = page.get("revisions")
                if revs:
                    entry["wikitext"] = revs[0]["slots"]["main"]["content"]
                for cat in page.get("categories", []):
                    entry["categories"].append(cat["title"])
            if "continue" not in data:
                break
            cont = data["continue"]
        out.extend(merged.values())
        done = min(i + BATCH_SIZE, len(ids))
        print(f"  fetched {done}/{len(ids)} pages", file=sys.stderr)
    return out


# --- Signal extraction ------------------------------------------------------


def match_books(text: str) -> set[str]:
    found = set()
    for book, patterns in BOOK_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, text, re.IGNORECASE):
                found.add(book)
                break
    return found


def analyze_page(page: dict) -> dict:
    title = page["title"]
    wikitext = page["wikitext"]
    categories = page["categories"]
    word_count = len(wikitext.split())

    is_chapter = title.startswith(CHAPTER_PREFIX)
    chapter_books = match_books(title) | (match_books(wikitext[:1500]) if is_chapter else set())

    cat_text = " ".join(categories)
    category_books = match_books(cat_text)

    ref_bodies = " ".join(REF_RE.findall(wikitext))
    ref_books = match_books(ref_bodies)
    n_refs = len(REF_RE.findall(wikitext))

    appearance_params = APPEARANCE_PARAM_RE.findall(wikitext)
    appearance_books = match_books(" ".join(v for _, v in appearance_params))

    mention_books = match_books(wikitext)

    if is_chapter and chapter_books:
        tier = "1_chapter_page"
    elif category_books:
        tier = "2_book_category"
    elif ref_books:
        tier = "3_book_refs"
    elif appearance_books:
        tier = "4_infobox_appearance"
    elif mention_books:
        tier = "5_plain_mention"
    else:
        tier = "6_no_signal"

    return {
        "title": title,
        "words": word_count,
        "tier": tier,
        "is_chapter": is_chapter,
        "chapter_books": sorted(chapter_books),
        "category_books": sorted(category_books),
        "ref_books": sorted(ref_books),
        "n_refs": n_refs,
        "appearance_params": [name.lower() for name, _ in appearance_params],
        "appearance_books": sorted(appearance_books),
        "mention_books": sorted(mention_books),
        "categories": categories,
    }


# --- Reporting --------------------------------------------------------------


def report(analyses: list[dict]) -> None:
    total_pages = len(analyses)
    total_words = sum(a["words"] for a in analyses) or 1

    print(f"\n=== Tier summary ({total_pages} pages, ~{total_words:,} words of wikitext) ===")
    print(f"{'tier':<24}{'pages':>7}{'words':>10}{'% words':>9}")
    tiers = Counter()
    tier_words = Counter()
    for a in analyses:
        tiers[a["tier"]] += 1
        tier_words[a["tier"]] += a["words"]
    for tier in sorted(tiers):
        w = tier_words[tier]
        print(f"{tier:<24}{tiers[tier]:>7}{w:>10,}{100 * w / total_words:>8.1f}%")

    print("\n=== Chapter pages per book (our ground-truth seed) ===")
    per_book = Counter()
    for a in analyses:
        if a["tier"] == "1_chapter_page":
            for b in a["chapter_books"] or ["unmatched"]:
                per_book[b] += 1
    for book, n in per_book.most_common():
        print(f"  {book}: {n}")
    if not per_book:
        print("  (none found -- check CHAPTER_PREFIX / namespace)")

    print("\n=== Ref density on pages with book-bearing refs ===")
    ref_pages = [a for a in analyses if a["ref_books"]]
    if ref_pages:
        dens = [1000 * a["n_refs"] / max(a["words"], 1) for a in ref_pages]
        dens.sort()
        mid = dens[len(dens) // 2]
        print(f"  {len(ref_pages)} pages; median {mid:.1f} refs/1000 words")

    print("\n=== Infobox appearance-param histogram ===")
    params = Counter(p for a in analyses for p in a["appearance_params"])
    for name, n in params.most_common(15):
        print(f"  {name}: {n} pages")
    if not params:
        print("  (no appearance-style params found)")

    print("\n=== Top 30 categories ===")
    cats = Counter(c for a in analyses for c in a["categories"])
    for name, n in cats.most_common(30):
        print(f"  {name}: {n}")

    print("\n=== Sample of no-signal pages (eyeball these) ===")
    no_signal = sorted(
        (a for a in analyses if a["tier"] == "6_no_signal"),
        key=lambda a: -a["words"],
    )
    for a in no_signal[:15]:
        print(f"  {a['title']} ({a['words']} words)")

    unlabeled_share = 100 * tier_words["6_no_signal"] / total_words
    print(f"\nDecision input: no-signal tier = {unlabeled_share:.1f}% of text volume "
          f"(pre-registered threshold: 15% -> LLM labeling pass)")


# --- Main -------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="ignore cache, re-fetch")
    args = parser.parse_args()

    if CACHE_PATH.exists() and not args.refresh:
        print(f"Loading cached pages from {CACHE_PATH} (use --refresh to re-fetch)")
        pages = [json.loads(line) for line in CACHE_PATH.read_text().splitlines()]
    else:
        session = requests.Session()
        session.headers["User-Agent"] = USER_AGENT
        fetch_site_info(session)
        print("Listing content pages (namespace 0, redirects excluded)...")
        titles = fetch_all_titles(session)
        print(f"  {len(titles)} pages listed; fetching wikitext + categories...")
        pages = fetch_pages(session, titles)
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CACHE_PATH.open("w") as f:
            for p in pages:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
        print(f"  cached to {CACHE_PATH}")

    analyses = [analyze_page(p) for p in pages]
    report(analyses)


if __name__ == "__main__":
    main()
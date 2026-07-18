"""Unit tests for ingest.checks."""

from __future__ import annotations

from ingest.checks import check_pages

CHAPTER_WIKITEXT = (
    "{{Infobox chapter\n| book = TNOTW\n| number = 1\n}}\n"
    "A chapter of raw wikitext with [[links]] and {{templates}}. "
    + "Long enough that the baseline corpus contains no stub-length pages. " * 3
)


def page(pageid: int, ns: int = 0, wikitext: str = "x" * 300) -> dict:
    return {
        "pageid": pageid,
        "ns": ns,
        "title": f"Page {pageid}",
        "revid": pageid * 10,
        "rev_timestamp": "2026-07-18T00:00:00Z",
        "wikitext": wikitext,
        "fetched_at": "2026-07-18T00:00:00Z",
    }


def corpus(n0: int = 438, n112: int = 26) -> list[dict]:
    pages = [page(i) for i in range(1, n0 + 1)]
    pages += [page(10_000 + i, ns=112, wikitext=CHAPTER_WIKITEXT) for i in range(n112)]
    return pages


def test_clean_corpus_passes():
    report = check_pages(corpus())
    assert report.ok
    assert not report.warnings


def test_small_count_drift_warns_but_passes():
    report = check_pages(corpus(n0=430))  # ~1.8% drift
    assert report.ok
    assert any("namespace 0" in w for w in report.warnings)


def test_large_count_drift_fails():
    report = check_pages(corpus(n0=300))
    assert not report.ok


def test_duplicate_pageids_fail():
    pages = corpus()
    pages.append(pages[0].copy())
    report = check_pages(pages)
    assert any("duplicate pageids" in f for f in report.failures)


def test_empty_wikitext_fails():
    pages = corpus()
    pages[0]["wikitext"] = "   "
    report = check_pages(pages)
    assert any("empty wikitext" in f for f in report.failures)


def test_stub_pages_are_counted_not_dropped():
    pages = corpus()
    pages[0]["wikitext"] = "short stub"
    report = check_pages(pages)
    assert report.ok
    assert any("1 pages under 200 chars" in i for i in report.infos)


def test_rendered_html_chapters_fail():
    pages = [page(i) for i in range(1, 439)]
    rendered = (
        '<aside class="portable-infobox">The Name of the Wind</aside>'
        "<p>rendered paragraph text that is long enough not to be a stub</p>" * 3
    )
    pages += [page(10_000 + i, ns=112, wikitext=rendered) for i in range(26)]
    report = check_pages(pages)
    assert not report.ok
    assert any("rendered" in f for f in report.failures)


def test_book_param_match_is_space_and_case_tolerant():
    chapter = "{{Infobox chapter\n| Book = TWMF\n}}" + "x" * 200
    pages = [page(i) for i in range(1, 439)]
    pages += [page(10_000 + i, ns=112, wikitext=chapter) for i in range(26)]
    report = check_pages(pages)
    assert report.ok

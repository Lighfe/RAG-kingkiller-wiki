"""Unit tests for ingest.fetch_pages — all HTTP mocked, no network."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import pytest
import responses

from ingest.fetch_pages import API_URL, BATCH_SIZE, WikiFetcher


def make_fetcher() -> WikiFetcher:
    return WikiFetcher(delay_s=0)


def query_params(call) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlparse(call.request.url).query).items()}


def rev_page(pageid: int, ns: int = 0, title: str | None = None) -> dict:
    return {
        "pageid": pageid,
        "ns": ns,
        "title": title or f"Page {pageid}",
        "revisions": [
            {
                "revid": pageid * 10,
                "timestamp": "2026-07-18T00:00:00Z",
                "slots": {"main": {"content": f"'''Page {pageid}''' wikitext"}},
            }
        ],
    }


@responses.activate
def test_continuation_collects_all_pages_and_echoes_all_keys():
    responses.get(
        API_URL,
        json={
            "query": {
                "allpages": [
                    {"pageid": 1, "ns": 0, "title": "Auri"},
                    {"pageid": 2, "ns": 0, "title": "Bast"},
                ]
            },
            "continue": {
                "apcontinue": "Cinder",
                "continue": "-||",
                "opaque": "some-module-token",
            },
        },
    )
    responses.get(
        API_URL,
        json={
            "batchcomplete": True,
            "query": {"allpages": [{"pageid": 3, "ns": 0, "title": "Cinder"}]},
        },
    )

    pages = make_fetcher().list_pages(0)

    assert [p["pageid"] for p in pages] == [1, 2, 3]
    assert len(responses.calls) == 2
    follow_up = query_params(responses.calls[1])
    # every continue key must be echoed back, not just apcontinue
    assert follow_up["apcontinue"] == "Cinder"
    assert follow_up["continue"] == "-||"
    assert follow_up["opaque"] == "some-module-token"


@responses.activate
def test_batching_splits_pageids_into_chunks_of_50():
    def content_callback(request):
        ids = [int(x) for x in parse_qs(urlparse(request.url).query)["pageids"][0].split("|")]
        return 200, {}, json.dumps({"query": {"pages": [rev_page(i) for i in ids]}})

    responses.add_callback(responses.GET, API_URL, callback=content_callback)

    ids = list(range(1, 121))
    records = make_fetcher().fetch_wikitext(ids)

    batch_sizes = [len(query_params(c)["pageids"].split("|")) for c in responses.calls]
    assert batch_sizes == [50, 50, 20]
    assert all(size <= BATCH_SIZE for size in batch_sizes)
    assert [r["pageid"] for r in records] == ids


@responses.activate
def test_fetch_all_enumerates_both_namespaces_and_merges():
    listed = {
        0: [{"pageid": 1, "ns": 0, "title": "Auri"}],
        112: [{"pageid": 9, "ns": 112, "title": "Chapter:The Broken Binding"}],
    }

    def api_callback(request):
        q = {k: v[0] for k, v in parse_qs(urlparse(request.url).query).items()}
        if q.get("list") == "allpages":
            body = {"query": {"allpages": listed[int(q["apnamespace"])]}}
        else:
            pages = [
                rev_page(int(pid), ns=0 if int(pid) == 1 else 112)
                for pid in q["pageids"].split("|")
            ]
            body = {"query": {"pages": pages}}
        return 200, {}, json.dumps(body)

    responses.add_callback(responses.GET, API_URL, callback=api_callback)

    records = make_fetcher().fetch_all()

    enumerated_ns = [
        query_params(c)["apnamespace"]
        for c in responses.calls
        if query_params(c).get("list") == "allpages"
    ]
    assert enumerated_ns == ["0", "112"]
    assert {(r["pageid"], r["ns"]) for r in records} == {(1, 0), (9, 112)}


@responses.activate
def test_split_content_reply_is_merged():
    # page 2 arrives without revisions first; continuation delivers them
    responses.get(
        API_URL,
        json={
            "query": {
                "pages": [rev_page(1), {"pageid": 2, "ns": 0, "title": "Bast"}]
            },
            "continue": {"rvcontinue": "2|999", "continue": "||"},
        },
    )
    responses.get(
        API_URL,
        json={"batchcomplete": True, "query": {"pages": [rev_page(2)]}},
    )

    records = make_fetcher().fetch_wikitext([1, 2])

    assert [r["pageid"] for r in records] == [1, 2]
    assert all(r["wikitext"] for r in records)
    assert query_params(responses.calls[1])["rvcontinue"] == "2|999"


def test_record_fields_match_cache_schema():
    with responses.RequestsMock() as rsps:
        rsps.get(API_URL, json={"query": {"pages": [rev_page(7)]}})
        (record,) = make_fetcher().fetch_wikitext([7])
    assert set(record) == {
        "pageid", "ns", "title", "revid", "rev_timestamp", "wikitext", "fetched_at",
    }
    assert record["revid"] == 70
    assert record["rev_timestamp"] == "2026-07-18T00:00:00Z"


@pytest.mark.parametrize(
    "url",
    [
        "https://kingkiller.wiki/api.php",  # CC BY-NC-SA — license-incompatible
        "https://en.wikipedia.org/w/api.php",
        "https://coppermind.net/w/api.php",
    ],
)
def test_refuses_foreign_hosts(url):
    with pytest.raises(ValueError, match="refusing host"):
        WikiFetcher(api_url=url)


def test_accepts_the_kingkiller_fandom_host():
    fetcher = WikiFetcher()
    assert fetcher.api_url == API_URL


@responses.activate
def test_fetch_redirects_follows_normalization_and_redirect_chain():
    # "span" -> normalized to "Span" -> redirects to "Calendar of Temerant";
    # mirrors the real API shape observed for this corpus (task 6b).
    responses.get(
        API_URL,
        json={
            "query": {
                "normalized": [{"from": "span", "to": "Span"}],
                "redirects": [
                    {"from": "University", "to": "The University"},
                    {"from": "Span", "to": "Calendar of Temerant"},
                ],
                "pages": [
                    {"pageid": 1, "ns": 0, "title": "The University"},
                    {"pageid": 2, "ns": 0, "title": "Calendar of Temerant"},
                    {"ns": 0, "title": "Nonexistentxyz123", "missing": True},
                ],
            }
        },
    )

    result = make_fetcher().fetch_redirects(["University", "span", "Nonexistentxyz123"])

    assert result == {"University": "The University", "span": "Calendar of Temerant"}


@responses.activate
def test_fetch_redirects_ignores_normalization_only_titles():
    # A title that only gets re-cased, with no actual redirects entry,
    # must NOT be reported as resolved (D36 amendment: redirects-only).
    responses.get(
        API_URL,
        json={
            "query": {
                "normalized": [{"from": "kvothe", "to": "Kvothe"}],
                "pages": [{"pageid": 1, "ns": 0, "title": "Kvothe"}],
            }
        },
    )
    result = make_fetcher().fetch_redirects(["kvothe"])
    assert result == {}


@responses.activate
def test_fetch_redirects_batches_at_50():
    def callback(request):
        titles = parse_qs(urlparse(request.url).query)["titles"][0].split("|")
        return 200, {}, json.dumps({"query": {"redirects": [], "pages": []}})

    responses.add_callback(responses.GET, API_URL, callback=callback)
    make_fetcher().fetch_redirects([f"T{i}" for i in range(120)])

    batch_sizes = [len(query_params(c)["titles"].split("|")) for c in responses.calls]
    assert batch_sizes == [50, 50, 20]


@pytest.mark.network
def test_live_api_small_batch():
    fetcher = WikiFetcher()
    chapters = fetcher.list_pages(112)
    assert len(chapters) >= 20

    records = fetcher.fetch_wikitext([p["pageid"] for p in chapters[:3]])
    assert len(records) == 3
    for record in records:
        assert record["ns"] == 112
        assert record["title"].startswith("Chapter:")
        assert record["wikitext"].strip()

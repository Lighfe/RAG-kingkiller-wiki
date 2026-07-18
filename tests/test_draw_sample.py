"""Unit tests for ingest.draw_sample — synthetic chunk fixtures."""

from __future__ import annotations

from ingest.draw_sample import CLUSTER_TARGET, SAMPLE_SIZE, draw_sample, matched_keyword


def chunk(
    i: int,
    prov: str | None = None,
    spec: bool = False,
    title: str = "Plain Page",
    heading: str = "",
    cats: tuple[str, ...] = (),
) -> dict:
    return {
        "chunk_id": f"{i}:lede:0",
        "label_provenance": prov,
        "is_speculation": spec,
        "page_title": title,
        "section_heading": heading,
        "categories": list(cats),
    }


def test_frame_excludes_labeled_and_speculation():
    chunks = (
        [chunk(i) for i in range(100)]
        + [chunk(200, prov="gold"), chunk(201, prov="citation"), chunk(202, spec=True)]
    )
    records, stats = draw_sample(chunks)
    ids = {r["chunk_id"] for r in records}
    assert not {"200:lede:0", "201:lede:0", "202:lede:0"} & ids
    assert stats["frame_size"] == 100


def test_strata_sizes_when_cluster_pool_is_large():
    chunks = [chunk(i, title="Ademre customs") for i in range(60)] + [
        chunk(100 + i) for i in range(100)
    ]
    records, stats = draw_sample(chunks)
    cluster = [r for r in records if r["stratum"] == "cluster"]
    rand = [r for r in records if r["stratum"] == "random"]
    assert len(cluster) == CLUSTER_TARGET
    assert len(rand) == SAMPLE_SIZE - CLUSTER_TARGET
    assert all(r["matched_keyword"] == "Ademre" for r in cluster)
    assert all("matched_keyword" not in r for r in rand)
    assert stats["shortfall_backfilled"] == 0


def test_backfill_when_cluster_pool_underfills():
    chunks = [chunk(i, cats=("Shehyn",)) for i in range(10)] + [
        chunk(100 + i) for i in range(100)
    ]
    records, stats = draw_sample(chunks)
    assert sum(r["stratum"] == "cluster" for r in records) == 10
    assert sum(r["stratum"] == "random" for r in records) == 70
    assert len(records) == SAMPLE_SIZE
    assert stats["shortfall_backfilled"] == CLUSTER_TARGET - 10


def test_deterministic_across_runs():
    chunks = [chunk(i, title="Felurian" if i % 3 == 0 else "Plain") for i in range(300)]
    first, _ = draw_sample(chunks)
    second, _ = draw_sample(chunks)
    assert first == second


def test_keyword_matching_uses_word_boundaries():
    assert matched_keyword(chunk(1, title="The Academy")) is None  # not "Adem"
    assert matched_keyword(chunk(2, title="Adem culture")) == "Adem"
    assert matched_keyword(chunk(3, heading="Life > Severen fall-out")) == "Severen"
    assert matched_keyword(chunk(4, cats=("Ademre", "Characters"))) == "Ademre"
    assert matched_keyword(chunk(5, title="Adem sign language")) == "Adem"

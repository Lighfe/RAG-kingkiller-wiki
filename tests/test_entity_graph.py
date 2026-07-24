"""Unit tests for ingest.entity_graph — synthetic pages/chunks, no network."""

from __future__ import annotations

from ingest.entity_graph import (
    LinkRow,
    build_title_index,
    category_crosstab,
    classify_target,
    coarse_type,
    extract_link_occurrences,
    pair_directions,
    pair_stats,
    resolve_target,
    spot_check_sample,
    stage_a,
    stage_b,
    types_by_page,
)


def page(pageid: int, title: str, wikitext: str, ns: int = 0) -> dict:
    return {"pageid": pageid, "ns": ns, "title": title, "wikitext": wikitext}


def chunk(chunk_id: str, page_id: int, text: str, categories: list[str] | None = None) -> dict:
    return {"chunk_id": chunk_id, "page_id": page_id, "text": text, "categories": categories or []}


# -- classify_target -------------------------------------------------------


def test_classify_target_skips_known_non_content_namespaces():
    assert classify_target("Category:Characters") == ("skip", "Category:Characters")
    assert classify_target("File:Map.png") == ("skip", "File:Map.png")


def test_classify_target_skips_interwiki_prefix():
    assert classify_target("wikipedia:Octavo") == ("skip", "wikipedia:Octavo")
    assert classify_target("es:Imre") == ("skip", "es:Imre")


def test_classify_target_keeps_chapter_namespace():
    action, target = classify_target("Chapter:Wood and Word")
    assert action == "candidate"
    assert target == "Chapter:Wood and Word"


def test_classify_target_keeps_colon_in_real_title():
    # "Torment: Tides of Numenera" is a real ns-0 title, not a namespace prefix.
    action, target = classify_target("Torment: Tides of Numenera")
    assert action == "candidate"
    assert target == "Torment: Tides of Numenera"


def test_classify_target_strips_leading_colon_before_namespace_check():
    # [[:File:X]]/[[:Category:X]] is MediaWiki's "link to this page instead
    # of triggering the namespace's special behavior" syntax; the leading
    # colon must not defeat the namespace-prefix skip.
    assert classify_target(":File:Triangulation 99 Patrick Rothfuss.jpg") == (
        "skip", "File:Triangulation 99 Patrick Rothfuss.jpg",
    )
    assert classify_target(":Category:Characters") == ("skip", "Category:Characters")


def test_classify_target_strips_anchor():
    assert classify_target("Kvothe#Early_life") == ("candidate", "Kvothe")


def test_classify_target_skips_self_anchor_only():
    action, _ = classify_target("#Section")
    assert action == "skip"


# -- resolve_target ---------------------------------------------------------


def _index():
    pages = [
        page(1, "Kvothe", ""),
        page(2, "Denna", ""),
        page(3, "Seth (farmer)", ""),
        page(4, "Seth (townsfolk)", ""),
    ]
    return build_title_index(pages), pages


def test_resolve_target_exact():
    (exact, cf), pages = _index()
    res = resolve_target("Kvothe", exact, cf)
    assert res.method == "exact"
    assert res.page["pageid"] == 1


def test_resolve_target_normalized_first_letter_case():
    (exact, cf), _ = _index()
    res = resolve_target("denna", exact, cf)  # only the first letter differs -> caught by normalization
    assert res.method == "normalized"
    assert res.page["pageid"] == 2

    res2 = resolve_target("Kvothe_", exact, cf)  # trailing underscore -> trailing space, stripped
    assert res2.method in ("exact", "normalized")
    assert res2.page["pageid"] == 1


def test_resolve_target_casefold_fallback_for_mid_word_case_difference():
    (exact, cf), _ = _index()
    res = resolve_target("dEnnA", exact, cf)  # mid-word case differs -> only casefold catches it
    assert res.method == "casefold"
    assert res.page["pageid"] == 2


def test_resolve_target_ambiguous_casefold_not_resolved():
    (exact, cf), _ = _index()
    res = resolve_target("seth", exact, cf)  # matches two different pages case-insensitively
    assert res.page is None


def test_resolve_target_unresolved_redirect_shaped_target():
    (exact, cf), _ = _index()
    res = resolve_target("Kote", exact, cf)  # a real redirect on the live wiki; not resolved offline
    assert res.page is None
    assert res.method is None


def test_resolve_target_redirect_tier_used_only_as_last_resort():
    (exact, cf), _ = _index()
    redirects = {"Kote": "Kvothe"}
    res = resolve_target("Kote", exact, cf, redirects)
    assert res.method == "redirect"
    assert res.page["pageid"] == 1

    # exact match still wins even if a (nonsensical) redirect entry exists for it
    redirects_conflict = {"Kvothe": "Denna"}
    res2 = resolve_target("Kvothe", exact, cf, redirects_conflict)
    assert res2.method == "exact"
    assert res2.page["pageid"] == 1


def test_resolve_target_redirect_pointing_to_unknown_title_stays_unresolved():
    (exact, cf), _ = _index()
    redirects = {"Kote": "Some Page Not In The Corpus"}
    res = resolve_target("Kote", exact, cf, redirects)
    assert res.page is None


def test_stage_a_uses_redirect_map_and_shrinks_unresolved():
    pages = [
        page(1, "Kvothe", "[[Kote]] walked home."),
        page(2, "Denna", "no links"),
    ]
    baseline = stage_a(pages)
    assert "Kote" in baseline.unresolved

    with_redirects = stage_a(pages, redirects={"Kote": "Kvothe"})
    assert "Kote" not in with_redirects.unresolved
    assert with_redirects.resolution_methods["redirect"] == 1


# -- extract_link_occurrences ------------------------------------------------


def test_extract_link_occurrences_piped_and_unpiped():
    wikitext = "[[Kvothe]] met [[Denna|Dianne]] near [[Waystone Inn#History|the inn]]."
    occs = extract_link_occurrences(wikitext)
    assert [o.raw_target for o in occs] == ["Kvothe", "Denna", "Waystone Inn#History"]
    assert [o.display for o in occs] == ["Kvothe", "Dianne", "the inn"]


# -- stage_a ------------------------------------------------------------------


def test_stage_a_builds_edge_and_skips_self_link():
    pages = [
        page(1, "Kvothe", "[[Denna]] and [[Kvothe]] and [[Category:Characters]] and [[Nowhere Real]]"),
        page(2, "Denna", "no links here"),
    ]
    result = stage_a(pages)
    assert result.edges == {(1, 2): ["Denna"]}
    assert result.self_links_skipped == 1
    assert result.skipped_namespace == 1
    assert "Nowhere Real" in result.unresolved
    assert result.unresolved["Nowhere Real"] == 1
    assert result.unresolved_samples["Nowhere Real"] == ["Kvothe"]


def test_pair_stats_bidirectional_vs_one_directional():
    edges = {(1, 2): ["a"], (2, 1): ["b"], (1, 3): ["c"]}
    stats = pair_stats(edges)
    assert stats["pairs_total"] == 2
    assert stats["pairs_bidirectional"] == 1
    assert stats["pairs_one_directional"] == 1
    assert pair_directions(edges)[frozenset((1, 2))] == {(1, 2), (2, 1)}


# -- coarse_type / category_crosstab ------------------------------------------


def test_coarse_type_matches_keywords():
    assert coarse_type(["Major Characters"]) == "Character"
    assert coarse_type(["Vintas", "Cities"]) == "Location"
    assert coarse_type(["Sympathy"]) == "Magic"
    assert coarse_type(["Unrelated Tag"]) == "Other"


def test_category_crosstab_pairs_types():
    edges = {(1, 2): ["a"]}
    types = {1: "Character", 2: "Location"}
    tab = category_crosstab(edges, types)
    assert tab[("Character", "Location")] == 1


def test_types_by_page_uses_first_seen_categories():
    chunks = [
        chunk("1:lede:0", 1, "Kvothe", categories=["Major Characters"]),
        chunk("1:trivia:0", 1, "Kvothe trivia"),
    ]
    types = types_by_page(chunks)
    assert types[1] == "Character"


# -- stage_b ------------------------------------------------------------------


def test_stage_b_localizes_link_and_recovers_text_mention():
    edges = {(1, 2): ["Denna"]}  # page 1 (Kvothe) links to page 2 (Denna), display text "Denna"
    chunks_by_page = {
        1: [
            chunk("1:lede:0", 1, "Kvothe\n\nHe grew up in Tarbean."),
            chunk("1:denna:0", 1, "Kvothe § Denna\n\nHe met Denna at a fire."),
            chunk("1:later:0", 1, "Kvothe § Later\n\nDenna appears again, unlinked this time."),
        ],
        2: [
            chunk("2:lede:0", 2, "Denna\n\nA traveling woman."),
        ],
    }
    title_by_id = {1: "Kvothe", 2: "Denna"}

    rows = stage_b(edges, chunks_by_page, title_by_id)
    by_chunk = {r.chunk_id: r for r in rows}

    assert by_chunk["1:denna:0"].match_type == "link"
    assert by_chunk["1:denna:0"].direction == "forward"
    assert by_chunk["1:later:0"].match_type == "text"
    assert by_chunk["1:later:0"].direction == "forward"
    assert "1:lede:0" not in by_chunk  # no mention of "Denna" in this chunk

    # reverse direction: page 2 has no link to page 1, but Kvothe's name never
    # appears in page 2's only chunk, so no reverse row is produced here.
    assert all(r.source_page_id != 2 for r in rows)


def test_stage_b_reverse_direction_recovers_text_only_mention():
    edges = {(1, 2): ["Denna"]}
    chunks_by_page = {
        1: [chunk("1:denna:0", 1, "Kvothe § Denna\n\nHe met Denna at a fire.")],
        2: [chunk("2:lede:0", 2, "Denna\n\nShe once traveled with Kvothe.")],
    }
    title_by_id = {1: "Kvothe", 2: "Denna"}

    rows = stage_b(edges, chunks_by_page, title_by_id)
    reverse_rows = [r for r in rows if r.source_page_id == 2]
    assert len(reverse_rows) == 1
    assert reverse_rows[0].chunk_id == "2:lede:0"
    assert reverse_rows[0].direction == "reverse"
    assert reverse_rows[0].match_type == "text"


def test_stage_b_word_boundary_not_substring():
    edges = {(1, 2): ["Adem"]}
    chunks_by_page = {
        1: [chunk("1:a:0", 1, "He studied Ademre customs, not Adem itself.")],
        2: [],
    }
    title_by_id = {1: "Page1", 2: "Adem"}
    rows = stage_b(edges, chunks_by_page, title_by_id)
    # "Ademre" must not count as a match for "Adem"; the bare word does.
    assert len(rows) == 1
    assert rows[0].chunk_id == "1:a:0"


def test_spot_check_sample_sorts_by_title_length():
    rows = [
        LinkRow("c1", 1, 2, "Fae", "forward", "text"),
        LinkRow("c2", 1, 3, "Ambrose Jakis", "forward", "text"),
        LinkRow("c3", 1, 4, "Adem", "forward", "link"),  # excluded: match_type=link
    ]
    sample = spot_check_sample(rows, n=5)
    assert [r.chunk_id for r in sample] == ["c1", "c2"]

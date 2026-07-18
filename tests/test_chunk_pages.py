"""Unit tests for ingest.chunk_pages — synthetic wikitext, no network."""

from __future__ import annotations

import logging

import pytest

from ingest.chunk_pages import MAX_WORDS, OVERLAP_WORDS, chunk_page


def rec(wikitext: str, pageid: int = 1, ns: int = 0, title: str = "Test Page", revid: int = 9) -> dict:
    return {"pageid": pageid, "ns": ns, "title": title, "revid": revid, "wikitext": wikitext}


def para(word: str, n: int = 60) -> str:
    return " ".join(f"{word}{i}" for i in range(n))


def prose(chunks):
    return [c for c in chunks if c["chunk_type"] == "prose"]


# --- section splitting --------------------------------------------------


def test_sections_and_lede_paths():
    chunks, _ = chunk_page(
        rec(
            f"{para('lede')}\n\n== History ==\n{para('hist')}\n\n"
            f"=== Creation War ===\n{para('war')}\n\n== Culture ==\n{para('cult')}"
        )
    )
    headings = [c["section_heading"] for c in prose(chunks)]
    assert headings == ["", "History", "History > Creation War", "Culture"]
    assert prose(chunks)[0]["chunk_id"] == "1:lede:0"
    assert prose(chunks)[1]["chunk_id"] == "1:history:0"
    assert prose(chunks)[2]["chunk_id"] == "1:history-creation-war:0"
    assert all(c["text"].startswith("Test Page § ") for c in prose(chunks)[1:])
    assert prose(chunks)[0]["text"].startswith("Test Page\n\n")


def test_lede_only_page():
    chunks, stats = chunk_page(rec(para("only")))
    assert [c["chunk_id"] for c in chunks] == ["1:lede:0"]
    assert chunks[0]["section_heading"] == ""
    assert not stats.dropped


def test_near_empty_page_dropped():
    chunks, stats = chunk_page(rec("{{some infobox|a=b|c=d}}\nTiny."))
    assert chunks == []
    assert stats.dropped


# --- max-size splitting -------------------------------------------------


def test_max_size_split_with_overlap():
    paras = [para(f"p{i}", 200) for i in range(3)]  # 600 words total
    chunks, stats = chunk_page(
        rec("== Long ==\n" + "\n\n".join(paras) + "\n\n== Next ==\nShort follow section.")
    )
    parts = [c for c in prose(chunks) if c["section_heading"] == "Long"]
    assert len(parts) == 3
    assert [c["chunk_id"] for c in parts] == ["1:long:0", "1:long:1", "1:long:2"]
    assert stats.split_sections == 1

    tail = " ".join(parts[0]["text"].split()[-OVERLAP_WORDS:])
    body1 = parts[1]["text"].split("\n\n", 1)[1]
    assert body1.startswith(tail)

    # no overlap across the section boundary
    nxt = next(c for c in prose(chunks) if c["section_heading"] == "Next")
    assert "p2199" not in nxt["text"]


def test_small_section_not_split():
    chunks, stats = chunk_page(rec(f"== A ==\n{para('a', MAX_WORDS - 10)}"))
    assert len(prose(chunks)) == 1
    assert stats.split_sections == 0


def test_oversize_single_paragraph_kept_and_logged():
    chunks, stats = chunk_page(rec(f"== Big ==\n{para('big', MAX_WORDS + 50)}"))
    assert len(prose(chunks)) == 1
    assert stats.oversize_paragraphs == 1
    assert any("exceeds the max chunk size" in s for s in stats.surprises)


# --- infobox detection --------------------------------------------------


def test_structural_infobox_detection_unknown_name():
    chunks, stats = chunk_page(
        rec(
            "{{Totally novel box|alpha = one|beta = [[Linked]] value}}\n"
            + para("body")
        )
    )
    boxes = [c for c in chunks if c["chunk_type"] == "infobox"]
    assert len(boxes) == 1
    assert boxes[0]["chunk_id"] == "1:infobox-0:0"
    assert "alpha: one" in boxes[0]["text"]
    assert "beta: Linked value" in boxes[0]["text"]
    assert any("totally novel box" in s for s in stats.surprises)


def test_positional_and_bare_templates_are_not_infoboxes():
    chunks, _ = chunk_page(
        rec(f"{{{{stub}}}}\n{{{{main|Other page}}}}\n{{{{ref|TNOTW|3}}}}\n{para('body')}")
    )
    assert [c for c in chunks if c["chunk_type"] == "infobox"] == []


def test_infobox_image_params_skipped():
    chunks, _ = chunk_page(
        rec("{{character infobox|image = Foo.jpg|fullname = Bob}}\n" + para("body"))
    )
    box = next(c for c in chunks if c["chunk_type"] == "infobox")
    assert "fullname: Bob" in box["text"]
    assert "Foo.jpg" not in box["text"]


# --- citations ----------------------------------------------------------


def test_citation_positional_association_and_max_wins():
    paras = [para("one", 200), para("two", 190) + " {{ref|TNOTW|5}}{{ref|TWMF|9}}"]
    chunks, _ = chunk_page(rec("== S ==\n" + "\n\n".join(paras)))
    parts = prose(chunks)
    assert len(parts) == 2
    assert parts[0]["citation_codes"] == []
    assert parts[0]["book_level"] is None
    assert parts[0]["label_provenance"] is None
    assert parts[1]["citation_codes"] == ["TNOTW", "TWMF"]
    assert parts[1]["book_level"] == 2  # max wins
    assert parts[1]["label_provenance"] == "citation"


def test_ref_tag_body_scanned_and_removed():
    chunks, _ = chunk_page(
        rec(
            f"{para('body')} Fact.<ref>See ''The Wise Man's Fear'', ch. 12</ref>\n"
        )
    )
    (chunk,) = prose(chunks)
    assert chunk["citation_codes"] == ["TWMF"]
    assert chunk["book_level"] == 2
    assert "ch. 12" not in chunk["text"]  # ref body must not leak into prose


def test_unknown_citation_code_logged_not_guessed(caplog):
    with caplog.at_level(logging.WARNING):
        chunks, stats = chunk_page(rec(f"{para('body')} {{{{ref|WEIRD|3}}}}"))
    (chunk,) = prose(chunks)
    assert chunk["citation_codes"] == ["WEIRD"]
    assert chunk["book_level"] is None
    assert chunk["label_provenance"] is None
    assert any("WEIRD" in s for s in stats.surprises)
    assert "WEIRD" in caplog.text


# --- quotes -------------------------------------------------------------


def test_quote_chunk_with_attribution():
    chunks, _ = chunk_page(
        rec(f"== Words ==\n{para('sec')}\n{{{{Quote|Wise words here.|The Chronicler}}}}")
    )
    (q,) = [c for c in chunks if c["chunk_type"] == "quote"]
    assert q["chunk_id"] == "1:quote-0:0"
    assert q["section_heading"] == "Words"
    assert "Wise words here." in q["text"]
    assert "— The Chronicler" in q["text"]


# --- speculation --------------------------------------------------------


def test_speculation_matcher():
    chunks, _ = chunk_page(
        rec(
            f"{para('lede')}\n== Speculation ==\n{para('spec')}\n"
            f"== Trivia ==\n{para('triv')}\n== SPECULATIONS ==\n{para('spec2')}"
        )
    )
    by_heading = {c["section_heading"]: c for c in prose(chunks)}
    assert by_heading["Speculation"]["is_speculation"] is True
    assert by_heading["SPECULATIONS"]["is_speculation"] is True
    assert by_heading["Trivia"]["is_speculation"] is False
    assert by_heading[""]["is_speculation"] is False


def test_conjecture_page_flags_all_chunks():
    chunks, _ = chunk_page(
        rec(f"{{{{conjecture}}}}\n{para('lede')}\n== Facts ==\n{para('facts')}")
    )
    assert all(c["is_speculation"] for c in chunks)
    assert all(c["quality_flags"] == ["conjecture"] for c in chunks)


# --- gold labeling ------------------------------------------------------


def test_gold_from_chapter_infobox():
    chunks, _ = chunk_page(
        rec(
            "{{chapter infobox|book = TNOTW|chapter = 2}}\n" + para("chap"),
            ns=112,
            title="Chapter:A Test",
        )
    )
    assert chunks  # infobox + prose
    assert all(c["book_level"] == 1 for c in chunks)
    assert all(c["label_provenance"] == "gold" for c in chunks)


def test_gold_from_title_fallback():
    chunks, _ = chunk_page(
        rec(
            para("chap"),
            ns=112,
            title="Chapter:X (prologue of The Wise Man's Fear)",
        )
    )
    assert all(c["book_level"] == 2 for c in chunks)
    assert all(c["label_provenance"] == "gold" for c in chunks)


def test_no_page_level_inheritance_on_ns0():
    wikitext = f"{para('a', 30)} {{{{ref|TNOTW|1}}}}\n\n== Later ==\n{para('b')}"
    chunks, _ = chunk_page(rec(wikitext))
    lede = next(c for c in prose(chunks) if c["section_heading"] == "")
    later = next(c for c in prose(chunks) if c["section_heading"] == "Later")
    assert lede["label_provenance"] == "citation"
    assert later["label_provenance"] is None  # no inheritance from the lede


# --- chunk_id stability -------------------------------------------------


def test_chunk_ids_stable_under_unrelated_edit():
    base = f"== Alpha ==\n{para('alpha')}\n== Beta ==\n{para('beta')}"
    edited = f"== Alpha ==\n{para('alpha')}\n== Beta ==\n{para('beta')} plus an edit."
    before, _ = chunk_page(rec(base))
    after, _ = chunk_page(rec(edited))
    b_alpha = next(c for c in before if c["section_heading"] == "Alpha")
    a_alpha = next(c for c in after if c["section_heading"] == "Alpha")
    assert b_alpha["chunk_id"] == a_alpha["chunk_id"]
    assert b_alpha["content_hash"] == a_alpha["content_hash"]
    b_beta = next(c for c in before if c["section_heading"] == "Beta")
    a_beta = next(c for c in after if c["section_heading"] == "Beta")
    assert b_beta["chunk_id"] == a_beta["chunk_id"]  # id survives the edit
    assert b_beta["content_hash"] != a_beta["content_hash"]  # hash flags it


def test_duplicate_headings_get_distinct_ids():
    chunks, _ = chunk_page(rec(f"== Twin ==\n{para('a')}\n== Twin ==\n{para('b')}"))
    ids = [c["chunk_id"] for c in prose(chunks) if c["section_heading"] == "Twin"]
    assert len(ids) == len(set(ids)) == 2


# --- empty sections & categories ---------------------------------------


def test_empty_section_emits_nothing():
    chunks, stats = chunk_page(
        rec(f"{para('lede')}\n== References ==\n{{{{reflist}}}}\n")
    )
    assert [c["section_heading"] for c in prose(chunks)] == [""]
    assert stats.empty_sections == 1


def test_categories_harvested_and_removed():
    chunks, _ = chunk_page(
        rec(f"{para('body')}\n[[Category:Characters]]\n[[Category:Magic]]")
    )
    (chunk,) = prose(chunks)
    assert chunk["categories"] == ["Characters", "Magic"]
    assert "Category:" not in chunk["text"]

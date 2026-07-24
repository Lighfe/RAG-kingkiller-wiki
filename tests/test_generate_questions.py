"""Unit tests for ingest.generate_questions - no live API calls (client is mocked)."""

from __future__ import annotations

import pytest

from ingest.generate_questions import (
    MAX_CONTENT_RETRIES,
    QuestionResult,
    STRATA_CONFIG,
    actual_cost,
    banned_term_violations,
    build_user_message,
    draw_questions_pool,
    eligible_pool,
    estimate_cost,
    excluded_category,
    generate_question,
    has_banned_reference,
)


def chunk(
    chunk_id: str,
    book_level: int = 1,
    chunk_type: str = "prose",
    ns: int = 0,
    section_heading: str = "",
    page_title: str = "Plain Page",
    text: str = "Plain Page\n\nSome body text.",
) -> dict:
    return {
        "chunk_id": chunk_id,
        "page_title": page_title,
        "section_heading": section_heading,
        "chunk_type": chunk_type,
        "ns": ns,
        "book_level": book_level,
        "text": text,
    }


class FakeUsageDetails:
    def __init__(self, cached_tokens):
        self.cached_tokens = cached_tokens


class FakeUsage:
    def __init__(self, input_tokens=1000, cached_tokens=0, output_tokens=20):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.input_tokens_details = FakeUsageDetails(cached_tokens)


class FakeResponse:
    def __init__(self, parsed, usage=None):
        self.output_parsed = parsed
        self.usage = usage if usage is not None else FakeUsage()


class FakeResponsesClient:
    def __init__(self, results):
        self._queue = list(results)
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, FakeResponse):
            return item
        return FakeResponse(item)


class FakeClient:
    def __init__(self, results):
        self.responses = FakeResponsesClient(results)


# -- exclusion (D24-class chunks) --------------------------------------------


def test_chapter_infobox_excluded():
    c = chunk("1:infobox-0:0", ns=112, chunk_type="infobox")
    assert excluded_category(c) == "chapter-infobox"


def test_ordinary_infobox_not_excluded():
    # ns=0 infobox (e.g. an entity page's infobox) carries real content -
    # only the ns=112 chapter-navigation infobox is structurally empty.
    c = chunk("2:infobox-0:0", ns=0, chunk_type="infobox")
    assert excluded_category(c) is None


def test_silence_heading_excluded_case_insensitive():
    c = chunk("3:desc:0", section_heading="Description > The First Silence")
    assert excluded_category(c) == "silence-heading"


def test_ordinary_prose_not_excluded():
    c = chunk("4:lede:0")
    assert excluded_category(c) is None


def test_eligible_pool_filters_both_categories():
    chunks = [
        chunk("1:infobox-0:0", ns=112, chunk_type="infobox"),
        chunk("2:desc:0", section_heading="The second silence"),
        chunk("3:lede:0"),
    ]
    pool = eligible_pool(chunks)
    assert [c["chunk_id"] for c in pool] == ["3:lede:0"]


# -- navigational-heading exclusion (D41) -------------------------------------


@pytest.mark.parametrize(
    "heading",
    ["CHARACTERS LIST", "Character List", "Character list", "Characters list", "characters list"],
)
def test_characters_list_variants_excluded_case_insensitive(heading):
    c = chunk("5:characters-list:0", ns=112, section_heading=heading)
    assert excluded_category(c) == "navigational-heading"


def test_external_links_excluded():
    c = chunk("6:external-links:0", section_heading="External links")
    assert excluded_category(c) == "navigational-heading"


def test_list_of_appearances_excluded_with_parent_heading():
    c = chunk("7:list-of-appearances:0", section_heading="In The Chronicle > List Of Appearances")
    assert excluded_category(c) == "navigational-heading"


def test_see_also_not_excluded():
    # checked corpus-wide (D41): "See also" instances carry a real
    # one-line relationship claim, unlike bare characters-list/external-
    # links - same "verify before excluding" discipline as D24's "Title".
    c = chunk("8:see-also:0", section_heading="See also")
    assert excluded_category(c) is None


def test_appearances_in_the_books_not_excluded():
    c = chunk("9:appearances:0", section_heading="Appearances in the books")
    assert excluded_category(c) is None


def test_list_of_languages_not_excluded():
    # contains "list" but is content-bearing (per-language descriptions) -
    # heading text alone doesn't determine exclusion, content does.
    c = chunk("10:list-of-languages:0", section_heading="List of languages")
    assert excluded_category(c) is None


# -- wiki-metatextual leakage detection (D41) ---------------------------------


@pytest.mark.parametrize("term", ["infobox", "listed", "stated", "section"])
def test_bare_structural_terms_flagged(term):
    assert has_banned_reference(f"What is {term} for this entity?") == term


def test_bare_terms_are_case_insensitive():
    assert has_banned_reference("What is INFOBOX for this entity?") == "infobox"


@pytest.mark.parametrize(
    "structural_word",
    ["wiki", "page", "article", "chapter", "entry", "infobox", "section", "speculation", "text", "list"],
)
def test_according_to_the_structural_noun_flagged(structural_word):
    # flagged either as the phrase pattern, or (for "infobox"/"section")
    # by the bare-term check firing first - both are correct, layered
    # detection, not a bug: either way the question must be flagged.
    q = f"According to the {structural_word}, what happened?"
    assert has_banned_reference(q) is not None


def test_in_world_attribution_to_a_named_person_is_not_flagged():
    assert has_banned_reference("According to Kvothe, what happened at the inn?") is None


def test_in_world_attribution_to_a_named_being_is_not_flagged():
    assert has_banned_reference("According to the Cthaeh, what must never be forgotten?") is None


def test_clean_question_is_not_flagged():
    assert has_banned_reference("What did Ambrose do to provoke Kvothe?") is None


# -- floor-stratified draw (D31) ---------------------------------------------


def _make_corpus():
    chunks = []
    for level, cfg in STRATA_CONFIG.items():
        for ct, n in (("prose", 200), ("infobox", 50), ("quote", 50)):
            for i in range(n):
                chunks.append(chunk(f"{level}-{ct}-{i}", book_level=level, chunk_type=ct))
    return chunks


def test_draw_hits_target_and_floors_when_pool_is_large():
    drawn, stats = draw_questions_pool(_make_corpus())

    by_cell = {}
    for c in drawn:
        by_cell.setdefault((c["book_level"], c["chunk_type"]), []).append(c)

    for level in (1, 2):
        assert len(by_cell[(level, "infobox")]) == 10
        assert len(by_cell[(level, "quote")]) == 10
        assert len(by_cell[(level, "prose")]) == 40

    assert len(drawn) == 60 + 60 + 300  # level 3 takes its whole pool (200+50+50)
    assert stats["drawn_total"] == len(drawn)


def test_level_3_takes_whole_pool_not_a_floor():
    chunks = [chunk(f"3-prose-{i}", book_level=3, chunk_type="prose") for i in range(22)]
    chunks += [chunk(f"3-infobox-{i}", book_level=3, chunk_type="infobox") for i in range(5)]
    chunks += [chunk("3-quote-0", book_level=3, chunk_type="quote")]
    drawn, stats = draw_questions_pool(chunks)
    assert len(drawn) == 28
    assert stats["cells"]["3:quote"] == {"available": 1, "drawn": 1}


def test_draw_reports_shortfall_when_floor_unreachable():
    chunks = [chunk(f"1-prose-{i}", book_level=1, chunk_type="prose") for i in range(100)]
    chunks += [chunk("1-quote-0", book_level=1, chunk_type="quote")]  # only 1, floor is 10
    drawn, stats = draw_questions_pool(chunks)
    assert stats["cells"]["1:quote"] == {"available": 1, "drawn": 1}
    quote_drawn = [c for c in drawn if c["chunk_type"] == "quote"]
    assert len(quote_drawn) == 1


def test_draw_excludes_d24_class_chunks_from_the_pool():
    chunks = _make_corpus()
    chunks.append(chunk("extra-infobox", ns=112, chunk_type="infobox", book_level=1))
    drawn, stats = draw_questions_pool(chunks)
    assert "extra-infobox" not in {c["chunk_id"] for c in drawn}
    assert stats["excluded"] == 1


def test_draw_is_deterministic_across_runs():
    corpus = _make_corpus()
    first, _ = draw_questions_pool(corpus)
    second, _ = draw_questions_pool(corpus)
    assert first == second


def test_draw_produces_no_duplicate_chunk_ids():
    drawn, _ = draw_questions_pool(_make_corpus())
    ids = [c["chunk_id"] for c in drawn]
    assert len(ids) == len(set(ids))


# -- prompt construction (pure function) -------------------------------------


def test_build_user_message_includes_page_context_and_body():
    msg = build_user_message("Severen", "Transportation", "prose", "Severen § Transportation\n\nBody text.")
    assert "Severen" in msg
    assert "Transportation" in msg
    assert "prose" in msg
    assert "Body text." in msg


def test_build_user_message_marks_empty_heading_as_lede():
    msg = build_user_message("A Quainte Compendium", "", "prose", "A Quainte Compendium\n\nBody.")
    assert "(lede)" in msg


# -- generate_question (mocked client) ---------------------------------------


CHUNK = chunk("2049:lede:0", page_title="Ambrose Jakis", text="Ambrose Jakis\n\nAmbrose is a nobleman.")


def test_generate_question_returns_expected_shape():
    client = FakeClient([QuestionResult(question="Who is Ambrose Jakis?")])
    record = generate_question(client, CHUNK)
    assert record["question"] == "Who is Ambrose Jakis?"
    assert record["chunk_id"] == CHUNK["chunk_id"]
    assert record["book_level"] == CHUNK["book_level"]
    assert record["chunk_type"] == CHUNK["chunk_type"]
    assert record["banned_reference"] is None


def test_generate_question_calls_api_with_expected_shape():
    client = FakeClient([QuestionResult(question="x?")])
    generate_question(client, CHUNK, model="gpt-5.4-mini")
    [call] = client.responses.calls
    assert call["model"] == "gpt-5.4-mini"
    assert call["text_format"] is QuestionResult
    assert "Ambrose Jakis" in call["input"]


def test_generate_question_retries_transient_errors_then_succeeds():
    client = FakeClient([RuntimeError("503"), QuestionResult(question="x?")])
    record = generate_question(client, CHUNK)
    assert record["question"] == "x?"
    assert len(client.responses.calls) == 2


def test_generate_question_gives_up_after_max_retries():
    client = FakeClient([RuntimeError("1"), RuntimeError("2"), RuntimeError("3")])
    with pytest.raises(RuntimeError):
        generate_question(client, CHUNK)
    assert len(client.responses.calls) == 3


def test_generate_question_records_usage_from_response():
    usage = FakeUsage(input_tokens=1500, cached_tokens=1200, output_tokens=15)
    client = FakeClient([FakeResponse(QuestionResult(question="x?"), usage=usage)])
    record = generate_question(client, CHUNK)
    assert record["input_tokens"] == 1500
    assert record["cached_tokens"] == 1200
    assert record["output_tokens"] == 15


# -- content-retry on banned-reference hit (D41) ------------------------------


def test_generate_question_regenerates_on_banned_reference_then_succeeds():
    client = FakeClient([
        QuestionResult(question="What is listed as Ambrose's occupation?"),  # violates
        QuestionResult(question="What is Ambrose Jakis's occupation?"),  # clean
    ])
    record = generate_question(client, CHUNK)
    assert record["question"] == "What is Ambrose Jakis's occupation?"
    assert record["banned_reference"] is None
    assert len(client.responses.calls) == 2


def test_generate_question_accumulates_tokens_across_content_retries():
    violating = FakeResponse(
        QuestionResult(question="What is stated about Ambrose?"),
        usage=FakeUsage(input_tokens=500, cached_tokens=0, output_tokens=10),
    )
    clean = FakeResponse(
        QuestionResult(question="Who is Ambrose Jakis?"),
        usage=FakeUsage(input_tokens=500, cached_tokens=0, output_tokens=10),
    )
    client = FakeClient([violating, clean])
    record = generate_question(client, CHUNK)
    assert record["input_tokens"] == 1000
    assert record["output_tokens"] == 20


def test_generate_question_gives_up_gracefully_after_max_content_retries():
    # unlike transient API errors, a persistent content violation doesn't
    # raise - it keeps the last attempt and reports the violation on the
    # record, for the standalone gate (banned_term_violations) to surface.
    results = [QuestionResult(question="What is listed here?") for _ in range(MAX_CONTENT_RETRIES)]
    client = FakeClient(results)
    record = generate_question(client, CHUNK)
    assert record["banned_reference"] == "listed"
    assert len(client.responses.calls) == MAX_CONTENT_RETRIES


def test_banned_term_violations_reports_only_flagged_records():
    records = [
        {"chunk_id": "a", "banned_reference": None},
        {"chunk_id": "b", "banned_reference": "infobox"},
        {"chunk_id": "c", "banned_reference": None},
    ]
    violations = banned_term_violations(records)
    assert [v["chunk_id"] for v in violations] == ["b"]


# -- cost estimation/actuals --------------------------------------------------


def test_estimate_cost_is_pure_and_scales_with_chunk_count():
    stats = estimate_cost([CHUNK, {**CHUNK, "chunk_id": "other"}])
    assert stats["chunks"] == 2
    assert stats["output_tokens_est"] == 2 * 40
    assert stats["input_tokens"] > 0


def test_estimate_cost_empty_input_is_free():
    stats = estimate_cost([])
    assert stats["input_tokens"] == 0
    assert stats["cost_usd_est"] == 0.0


def test_actual_cost_applies_cached_discount_only_to_cached_tokens():
    records = [
        {"input_tokens": 1000, "cached_tokens": 800, "output_tokens": 20},
        {"input_tokens": 1000, "cached_tokens": 0, "output_tokens": 20},
    ]
    cost = actual_cost(records)
    assert cost["chunks"] == 2
    expected = (
        1200 / 1_000_000 * 0.75
        + 800 / 1_000_000 * 0.075
        + 40 / 1_000_000 * 4.50
    )
    assert cost["cost_usd"] == pytest.approx(expected, abs=5e-5)


def test_actual_cost_empty_records_is_free_not_a_crash():
    cost = actual_cost([])
    assert cost["cache_hit_rate"] == 0.0
    assert cost["cost_usd"] == 0.0

"""Unit tests for ingest.label_llm - no live API calls (client is mocked)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ingest.label_llm import (
    LabelResult,
    actual_cost,
    apply_conservative_default,
    assemble_labeled_chunks,
    build_user_message,
    chunk_content,
    confidence_distribution,
    content_hash,
    estimate_cost,
    label_chunk,
    label_provenance_breakdown,
    null_provenance_frame,
    prompt_hash,
)

CHUNK = {
    "chunk_id": "4502:infobox-0:0",
    "page_title": "Severen",
    "section_heading": "",
    "chunk_type": "infobox",
    "text": (
        "Severen\n\nlocation: Vintas\nposition: City\n"
        "ruler: Maer Alveron; Roderic Calanthis\ncurrency: Vintish, Cealdish"
    ),
}


class FakeUsageDetails:
    def __init__(self, cached_tokens):
        self.cached_tokens = cached_tokens


class FakeUsage:
    def __init__(self, input_tokens=1000, cached_tokens=0, output_tokens=50):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.input_tokens_details = FakeUsageDetails(cached_tokens)


class FakeResponse:
    def __init__(self, parsed, usage=None):
        self.output_parsed = parsed
        self.usage = usage if usage is not None else FakeUsage()


class FakeResponsesClient:
    """Records calls; returns a scripted queue of results/exceptions."""

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


# -- LabelResult schema ----------------------------------------------------


def test_label_result_accepts_valid_values():
    r = LabelResult(book_level=2, confidence="medium", rationale="because reasons.")
    assert r.book_level == 2
    assert r.confidence == "medium"


@pytest.mark.parametrize("book_level", [0, 4, "2", None])
def test_label_result_rejects_bad_book_level(book_level):
    with pytest.raises(ValidationError):
        LabelResult(book_level=book_level, confidence="high", rationale="x")


@pytest.mark.parametrize("confidence", ["High", "certain", 0.9, None])
def test_label_result_rejects_bad_confidence(confidence):
    with pytest.raises(ValidationError):
        LabelResult(book_level=1, confidence=confidence, rationale="x")


def test_label_result_requires_rationale_field():
    with pytest.raises(ValidationError):
        LabelResult(book_level=1, confidence="high")


# -- conservative-default override (D12) -----------------------------------


def test_low_confidence_overrides_to_conservative_default_regardless_of_raw_level():
    for raw_level in (1, 2, 3):
        result = LabelResult(book_level=raw_level, confidence="low", rationale="unsure")
        applied, overridden = apply_conservative_default(result)
        assert applied == 3
        assert overridden is True


@pytest.mark.parametrize("confidence", ["medium", "high"])
def test_non_low_confidence_keeps_raw_level(confidence):
    result = LabelResult(book_level=2, confidence=confidence, rationale="clear")
    applied, overridden = apply_conservative_default(result)
    assert applied == 2
    assert overridden is False


# -- prompt construction (pure functions) -----------------------------------


def test_chunk_content_strips_header_line():
    text = "Severen § Transportation\n\nSeveren-High sits atop a cliff."
    assert chunk_content(text) == "Severen-High sits atop a cliff."


def test_chunk_content_preserves_internal_paragraph_breaks():
    text = "Page\n\nFirst paragraph.\n\nSecond paragraph."
    assert chunk_content(text) == "First paragraph.\n\nSecond paragraph."


def test_chunk_content_handles_missing_header_gracefully():
    # no blank-line separator: nothing to strip, return as-is
    assert chunk_content("no header here") == "no header here"


def test_build_user_message_uses_only_the_four_allowed_fields():
    msg = build_user_message("Severen", "Transportation", "prose", "Severen § Transportation\n\nBody text.")
    assert "Severen" in msg
    assert "Transportation" in msg
    assert "prose" in msg
    assert "Body text." in msg


def test_build_user_message_marks_empty_heading_as_lede():
    msg = build_user_message("A Quainte Compendium", "", "prose", "A Quainte Compendium\n\nBody.")
    assert "(lede)" in msg


def test_build_user_message_never_receives_citation_or_provenance_fields():
    # the function signature itself enforces purity: only these four
    # positional/keyword params exist, so citation_codes/label_provenance
    # cannot leak in even if a caller has them on hand.
    import inspect

    params = list(inspect.signature(build_user_message).parameters)
    assert params == ["page_title", "section_heading", "chunk_type", "text"]


# -- label_chunk (mocked client) ---------------------------------------------


def test_label_chunk_applies_override_and_reports_raw_and_applied():
    raw = LabelResult(book_level=1, confidence="low", rationale="ambiguous ruler field")
    client = FakeClient([raw])

    record = label_chunk(client, CHUNK)

    assert record["chunk_id"] == CHUNK["chunk_id"]
    assert record["book_level"] == 3  # overridden
    assert record["book_level_raw"] == 1
    assert record["overridden"] is True
    assert record["confidence"] == "low"
    assert record["rationale"] == "ambiguous ruler field"


def test_label_chunk_passes_through_high_confidence_unmodified():
    raw = LabelResult(book_level=1, confidence="high", rationale="static infobox facts only")
    client = FakeClient([raw])

    record = label_chunk(client, CHUNK)

    assert record["book_level"] == 1
    assert record["book_level_raw"] == 1
    assert record["overridden"] is False


def test_label_chunk_calls_api_with_expected_shape():
    raw = LabelResult(book_level=1, confidence="high", rationale="x")
    client = FakeClient([raw])

    label_chunk(client, CHUNK, model="gpt-5.4-mini")

    [call] = client.responses.calls
    assert call["model"] == "gpt-5.4-mini"
    assert call["text_format"] is LabelResult
    assert "Severen" in call["input"]
    assert isinstance(call["instructions"], str) and len(call["instructions"]) > 0


def test_label_chunk_retries_transient_errors_then_succeeds():
    raw = LabelResult(book_level=2, confidence="medium", rationale="ok")
    client = FakeClient([RuntimeError("503"), raw])

    record = label_chunk(client, CHUNK)

    assert record["book_level"] == 2
    assert len(client.responses.calls) == 2


def test_label_chunk_gives_up_after_max_retries():
    client = FakeClient([RuntimeError("1"), RuntimeError("2"), RuntimeError("3")])
    with pytest.raises(RuntimeError):
        label_chunk(client, CHUNK)
    assert len(client.responses.calls) == 3


def test_label_chunk_records_usage_from_response():
    raw = LabelResult(book_level=1, confidence="high", rationale="x")
    usage = FakeUsage(input_tokens=1500, cached_tokens=1200, output_tokens=40)
    client = FakeClient([FakeResponse(raw, usage=usage)])

    record = label_chunk(client, CHUNK)

    assert record["input_tokens"] == 1500
    assert record["cached_tokens"] == 1200
    assert record["output_tokens"] == 40


# -- real cost from observed usage --------------------------------------------


def test_actual_cost_applies_cached_discount_only_to_cached_tokens():
    records = [
        {"input_tokens": 1000, "cached_tokens": 800, "output_tokens": 50},
        {"input_tokens": 1000, "cached_tokens": 0, "output_tokens": 50},
    ]
    cost = actual_cost(records)
    assert cost["chunks"] == 2
    assert cost["input_tokens"] == 2000
    assert cost["cached_tokens"] == 800
    assert cost["cache_hit_rate"] == pytest.approx(0.4)
    expected = (
        1200 / 1_000_000 * 0.75  # uncached input
        + 800 / 1_000_000 * 0.075  # cached input
        + 100 / 1_000_000 * 4.50  # output
    )
    assert cost["cost_usd"] == pytest.approx(expected, abs=5e-5)  # rounded to 4dp


def test_actual_cost_empty_records_is_free_not_a_crash():
    cost = actual_cost([])
    assert cost["cache_hit_rate"] == 0.0
    assert cost["cost_usd"] == 0.0


# -- dry-run cost estimate (no API calls) ------------------------------------


def test_estimate_cost_is_pure_and_scales_with_chunk_count():
    chunks = [CHUNK, {**CHUNK, "chunk_id": "other"}]
    stats = estimate_cost(chunks)
    assert stats["chunks"] == 2
    assert stats["output_tokens_est"] == 2 * 60
    assert stats["input_tokens"] > 0


def test_estimate_cost_formula_matches_reported_prices():
    stats = estimate_cost([CHUNK])
    expected = (
        stats["input_tokens"] / 1_000_000 * stats["price_per_1m_input"]
        + stats["output_tokens_est"] / 1_000_000 * stats["price_per_1m_output"]
    )
    assert stats["cost_usd_est"] == pytest.approx(expected, abs=5e-5)  # rounded to 4dp


def test_estimate_cost_empty_input_is_free():
    stats = estimate_cost([])
    assert stats["input_tokens"] == 0
    assert stats["cost_usd_est"] == 0.0


# -- null-provenance framing --------------------------------------------------


def test_null_provenance_frame_filters_out_labeled_chunks():
    chunks = [
        {"chunk_id": "a", "label_provenance": None},
        {"chunk_id": "b", "label_provenance": "gold"},
        {"chunk_id": "c", "label_provenance": "citation"},
        {"chunk_id": "d", "label_provenance": None},
    ]
    frame = null_provenance_frame(chunks)
    assert [c["chunk_id"] for c in frame] == ["a", "d"]


# -- assembling the D14 third-stage artifact ----------------------------------


def _record(chunk_id, book_level=1, book_level_raw=1, confidence="high", overridden=False):
    return {
        "chunk_id": chunk_id,
        "book_level": book_level,
        "book_level_raw": book_level_raw,
        "confidence": confidence,
        "rationale": "x",
        "overridden": overridden,
        "model": "gpt-5.4-mini",
        "input_tokens": 100,
        "cached_tokens": 0,
        "output_tokens": 20,
    }


def test_assemble_labeled_chunks_leaves_gold_and_citation_untouched():
    chunks = [
        {"chunk_id": "a", "label_provenance": "gold", "book_level": 2},
        {"chunk_id": "b", "label_provenance": "citation", "book_level": 3},
    ]
    assembled = assemble_labeled_chunks(chunks, [])
    assert assembled == chunks


def test_assemble_labeled_chunks_fills_in_null_provenance_rows():
    chunks = [
        {"chunk_id": "a", "label_provenance": "gold", "book_level": 2},
        {"chunk_id": "n", "label_provenance": None, "book_level": None, "text": "t"},
    ]
    records = [_record("n", book_level=3, book_level_raw=1, confidence="low")]
    assembled = assemble_labeled_chunks(chunks, records)

    gold, null_row = assembled
    assert gold == chunks[0]
    assert null_row["book_level"] == 3
    assert null_row["book_level_raw"] == 1
    assert null_row["label_confidence"] == "low"
    assert null_row["label_provenance"] == "llm"
    assert null_row["text"] == "t"  # other chunk fields preserved


def test_assemble_labeled_chunks_preserves_input_order_and_count():
    chunks = [
        {"chunk_id": "a", "label_provenance": None},
        {"chunk_id": "b", "label_provenance": "gold"},
        {"chunk_id": "c", "label_provenance": None},
    ]
    records = [_record("a"), _record("c")]
    assembled = assemble_labeled_chunks(chunks, records)
    assert [c["chunk_id"] for c in assembled] == ["a", "b", "c"]
    assert len(assembled) == len(chunks)


def test_assemble_labeled_chunks_rejects_mismatched_records():
    chunks = [{"chunk_id": "a", "label_provenance": None}]
    with pytest.raises(ValueError):
        assemble_labeled_chunks(chunks, [_record("wrong-id")])
    with pytest.raises(ValueError):
        assemble_labeled_chunks(chunks, [])


# -- manifest aggregates --------------------------------------------------


def test_label_provenance_breakdown_counts_each_tier():
    chunks = [
        {"label_provenance": "gold"},
        {"label_provenance": "gold"},
        {"label_provenance": "citation"},
        {"label_provenance": "llm"},
    ]
    assert label_provenance_breakdown(chunks) == {"gold": 2, "citation": 1, "llm": 1}


def test_confidence_distribution_counts_all_three_levels_even_if_zero():
    records = [_record("a", confidence="low"), _record("b", confidence="low"), _record("c", confidence="high")]
    assert confidence_distribution(records) == {"low": 2, "medium": 0, "high": 1}


def test_prompt_hash_is_stable_and_short():
    h1 = prompt_hash()
    h2 = prompt_hash()
    assert h1 == h2
    assert len(h1) == 12


def test_content_hash_is_deterministic_and_sensitive_to_content():
    a = content_hash(b"hello")
    b = content_hash(b"hello")
    c = content_hash(b"goodbye")
    assert a == b
    assert a != c
    assert len(a) == 64  # full sha256 hex digest

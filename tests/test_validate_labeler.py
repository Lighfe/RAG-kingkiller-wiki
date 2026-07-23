"""Unit tests for the pure metric functions in ingest.validate_labeler.

No API calls here - these are the correctness-critical bits behind the
D13 go/no-go decision, so they get direct coverage independent of the
live gold/adversarial run.
"""

from __future__ import annotations

import pytest

from ingest.validate_labeler import (
    accuracy,
    book2_recall,
    confusion_matrix,
    d24_exclusion_category,
    disagreements,
    gold_chunks,
    load_manual_labels,
    wilson_interval,
)


def test_accuracy_counts_exact_matches():
    pairs = [(1, 1), (2, 2), (2, 1), (3, 3)]
    rate, correct, n = accuracy(pairs)
    assert (correct, n) == (3, 4)
    assert rate == pytest.approx(0.75)


def test_accuracy_empty_is_zero_not_a_crash():
    assert accuracy([]) == (0.0, 0, 0)


def test_book2_recall_counts_2_and_3_as_caught_but_not_1():
    # actual==2: predicted 2 (caught), 3 (caught, over-conservative but not
    # a leak), 1 (missed - the dangerous under-labeling direction)
    pairs = [(2, 2), (2, 3), (2, 1), (1, 1)]
    rate, caught, total = book2_recall(pairs)
    assert (caught, total) == (2, 3)
    assert rate == pytest.approx(2 / 3)


def test_book2_recall_ignores_non_book2_actuals():
    pairs = [(1, 1), (3, 3), (1, 2)]
    rate, caught, total = book2_recall(pairs)
    assert total == 0
    assert rate == 0.0


def test_confusion_matrix_shape_and_counts():
    pairs = [(1, 1), (1, 2), (2, 2), (2, 2), (3, 1)]
    m = confusion_matrix(pairs)
    assert m[1][1] == 1 and m[1][2] == 1 and m[1][3] == 0
    assert m[2][2] == 2
    assert m[3][1] == 1 and m[3][3] == 0
    # every actual level has an entry for every predicted level, even zero
    assert set(m.keys()) == {1, 2, 3}
    assert all(set(row.keys()) == {1, 2, 3} for row in m.values())


def test_disagreements_filters_to_mismatches_only():
    records = [
        {"chunk_id": "a", "actual": 1, "predicted": 1},
        {"chunk_id": "b", "actual": 2, "predicted": 1},
        {"chunk_id": "c", "actual": 3, "predicted": 3},
    ]
    result = disagreements(records)
    assert [r["chunk_id"] for r in result] == ["b"]


def test_wilson_interval_contains_point_estimate_and_widens_for_small_n():
    lo, hi = wilson_interval(8, 10)
    assert lo < 0.8 < hi
    lo_small, hi_small = wilson_interval(4, 5)
    lo_large, hi_large = wilson_interval(400, 500)
    # same 80% point estimate, but the small-n interval must be wider
    assert (hi_small - lo_small) > (hi_large - lo_large)


def test_wilson_interval_handles_zero_n():
    assert wilson_interval(0, 0) == (0.0, 0.0)


def test_gold_chunks_filters_by_provenance():
    chunks = [
        {"chunk_id": "a", "label_provenance": "gold"},
        {"chunk_id": "b", "label_provenance": "citation"},
        {"chunk_id": "c", "label_provenance": None},
        {"chunk_id": "d", "label_provenance": "gold"},
    ]
    assert [c["chunk_id"] for c in gold_chunks(chunks)] == ["a", "d"]


def test_load_manual_labels_last_record_wins(tmp_path):
    path = tmp_path / "manual_labels.jsonl"
    path.write_text(
        '{"chunk_id": "x", "manual_book_level": 1}\n'
        '{"chunk_id": "x", "manual_book_level": 2}\n'
        '{"chunk_id": "y", "manual_book_level": "u"}\n'
    )
    labels = load_manual_labels(path)
    assert labels["x"]["manual_book_level"] == 2
    assert labels["y"]["manual_book_level"] == "u"


# -- D24 exclusion category ---------------------------------------------------


def test_d24_excludes_infobox_chunks():
    assert d24_exclusion_category({"chunk_type": "infobox", "section_heading": ""}) == "infobox"


@pytest.mark.parametrize(
    "heading",
    [
        "Chapter summary > The first silence",
        "Chapter summary > The second silence",
        "Chapter summary > The third silence",
        "THE FIRST SILENCE",  # case-insensitive
    ],
)
def test_d24_excludes_silence_headings(heading):
    assert d24_exclusion_category({"chunk_type": "prose", "section_heading": heading}) == "silence-heading"


@pytest.mark.parametrize(
    "heading",
    ["Title", "TITLE", "Chapter summary", "Characters list", ""],
)
def test_d24_does_not_exclude_other_headings(heading):
    # "Title" was checked empirically (2026-07-22) and rejected as a category:
    # most instances state a specific chapter-content claim, so it stays in
    # the denominator rather than being auto-excluded.
    assert d24_exclusion_category({"chunk_type": "prose", "section_heading": heading}) is None

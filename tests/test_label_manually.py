"""Unit tests for ingest.label_manually — scripted keystrokes, no TTY."""

from __future__ import annotations

import json

from ingest.label_manually import load_labels, run_session

CHUNKS = {
    f"c{i}": {
        "chunk_id": f"c{i}",
        "page_title": f"Page {i}",
        "section_heading": "" if i == 0 else f"Section {i}",
        "chunk_type": "prose",
        "page_url": f"https://kingkiller.fandom.com/wiki/Page_{i}",
        "text": f"Page {i}\n\nSynthetic body text {i}.",
    }
    for i in range(3)
}
ORDER = ["c0", "c1", "c2"]


def scripted(keys: list[str]):
    it = iter(keys)

    def input_fn(_prompt: str) -> str:
        return next(it)

    return input_fn


def run(tmp_path, keys, order=ORDER):
    path = tmp_path / "manual_labels.jsonl"
    labels = run_session(
        order, CHUNKS, path, input_fn=scripted(keys), print_fn=lambda *a: None
    )
    return labels, path


def test_labels_written_with_schema(tmp_path):
    labels, path = run(tmp_path, ["1", "2", "u"])
    assert [labels[c]["manual_book_level"] for c in ORDER] == [1, 2, "u"]
    records = [json.loads(l) for l in path.read_text().splitlines()]
    assert len(records) == 3
    for rec in records:
        assert set(rec) == {"chunk_id", "manual_book_level", "seconds_spent", "timestamp"}
        assert isinstance(rec["seconds_spent"], float)


def test_resume_skips_already_labeled(tmp_path):
    path = tmp_path / "manual_labels.jsonl"
    path.write_text(
        json.dumps(
            {"chunk_id": "c1", "manual_book_level": 3, "seconds_spent": 1.0, "timestamp": "t"}
        )
        + "\n"
    )
    labels = run_session(
        ORDER, CHUNKS, path, input_fn=scripted(["1", "2"]), print_fn=lambda *a: None
    )
    # only c0 and c2 were asked; c1 kept its prior label
    assert labels["c0"]["manual_book_level"] == 1
    assert labels["c1"]["manual_book_level"] == 3
    assert labels["c2"]["manual_book_level"] == 2


def test_back_rewrites_previous_record(tmp_path):
    labels, path = run(tmp_path, ["1", "b", "2", "3", "1"])
    # c0 labeled 1, then "b" → c0 relabeled 2, then c1=3, c2=1
    assert labels["c0"]["manual_book_level"] == 2
    assert labels["c1"]["manual_book_level"] == 3
    assert labels["c2"]["manual_book_level"] == 1
    lines = [json.loads(l) for l in path.read_text().splitlines()]
    assert len(lines) == 4  # append-only log keeps both c0 records
    assert load_labels(path)["c0"]["manual_book_level"] == 2  # last wins


def test_back_at_start_is_harmless(tmp_path):
    labels, _ = run(tmp_path, ["b", "1", "2", "3"])
    assert [labels[c]["manual_book_level"] for c in ORDER] == [1, 2, 3]


def test_quit_saves_partial(tmp_path):
    labels, path = run(tmp_path, ["1", "q"])
    assert set(labels) == {"c0"}
    assert len(path.read_text().splitlines()) == 1


def test_invalid_key_reprompts(tmp_path):
    labels, _ = run(tmp_path, ["x", "9", "1", "2", "3"])
    assert [labels[c]["manual_book_level"] for c in ORDER] == [1, 2, 3]

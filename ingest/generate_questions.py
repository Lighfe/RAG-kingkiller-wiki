"""Task 8 Part B (revised by task 8a): single-hop question generation
(D31, ground truth per D40).

LLM-generates one question per chunk drawn from a floor-stratified sample
of chunks_labeled.jsonl (D31: prose-dominant, floor coverage for
infobox/quote, book_level=3 not inflated to parity). Ground truth is
binary — that chunk_id only (D40, refining D32's graded scheme for this
bake-off). Chapter infoboxes (ns=112), atmospheric "Silence of Three
Parts" sub-headings, and bare navigational/index sections (character
lists, external-link lists, appearance indexes — D41) are excluded from
the source pool: the same structurally-uninformative class D24 excludes
from the gold accuracy denominator, since none of these can ground a
chunk-specific question.

Task 8a (D41): human review of task 8's original 148-question set found
three real generation defects — wiki-metatextual leakage ("in the
infobox", "according to the speculation"), compound/quiz-style questions
joining two asks with "and", and the navigational-section pool gap above.
Task 8's questions.jsonl/embedding_baking_off_results are void; this
module now bans structural self-reference in the prompt (checked by an
automated post-generation gate, retried on violation) and instructs a
single-focus, curious-reader persona instead of exhaustive-recall
framing.

Run: ``uv run python -m ingest.generate_questions --dry-run`` (cost
estimate, no API calls) or ``uv run python -m ingest.generate_questions``
(live run, writes data/eval/questions.jsonl).
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import tiktoken
from pydantic import BaseModel

from ingest.label_llm import chunk_content

MODEL = "gpt-5.4-mini"
TOOL_VERSION = "0.2"
PROMPT_VERSION = "D41-task8a"
SEED = 20260724

# Same atmospheric-sub-heading pattern D24 uses for the gold-accuracy
# denominator (ingest/validate_labeler.py SILENCE_HEADING_RE). The ns=112
# chapter-infobox check is scoped locally rather than reusing D24's
# chunk_type=="infobox" test wholesale: that test alone also matches the
# ~200 ordinary entity infoboxes (Severen, A Quainte Compendium, ...),
# which DO carry question-worthy content — only the 24 ns=112 chapter-
# navigation infoboxes (book/chapter/arc/location/previous/next fields)
# are structurally uninformative.
SILENCE_HEADING_RE = re.compile(r"(first|second|third)\s+silence", re.IGNORECASE)

# D41/task 8a: corpus-wide audit of section_heading leaves for other
# navigational/index-shaped sections beyond D24's originally-named pair,
# triggered by 12385:characters-list:0 turning up in task 8's set with no
# checkable content ("CHARACTERS LIST\n\nKote\n Kote's father\n Mayor...").
# Confirmed by inspecting every instance corpus-wide (2026-07-24):
#   - "characters list" (any case variant: CHARACTERS LIST/Character
#     List/Character list/Characters list, 18 chunks, all ns=112) — bare
#     name lists, no narrative claim.
#   - "external links" (4 chunks) — bare link/website-name lists (e.g.
#     "DAW Books Website"); one of these (3770:external-links:0, Tak)
#     produced task 8's "which official Tak resources include..."
#     compound-listing question.
#   - "list of appearances" (1 chunk, Elodin) — a bare chapter+page index,
#     no narrative content.
# Checked and NOT excluded, same "verify before excluding" discipline as
# D24's "Title" precedent: "see also" (2 chunks — each carries a real
# one-line relationship claim, e.g. "Tak - A modern game that arose from
# Kaen") and "appearances in the books" (1 chunk, Gerrek — real
# descriptive content, not a bare index). Headings containing "list" that
# turned out content-bearing (List of languages, List of songs, List of
# editions by country, Siaru's grammar "Lists" section) were checked and
# also NOT excluded for the same reason.
NAVIGATIONAL_HEADING_LEAVES = {"characters list", "character list", "external links", "list of appearances"}

# D41/task 8a: wiki-metatextual leakage — questions referencing the
# source's own document structure instead of the story/world. Found via
# human review of task 8's set, e.g. "Who is listed as Meluan Lackless's
# husband in the infobox?" and "According to the speculation, which
# person is suggested as a possible Amyr member because he guards the
# door?" (the latter proving the bug is the leakage pattern, not
# speculation-sourced content itself — is_speculation chunks stay in the
# pool). Bare-word bans apply regardless of chunk_type; the phrase ban
# targets "according to the <document-structure-noun>" specifically, so
# legitimate in-world attribution ("According to Kvothe...", "According
# to the Cthaeh...") is never caught — only capitalized proper nouns
# would follow "according to" in-world, never these generic nouns.
STRUCTURAL_BARE_TERMS = ("infobox", "listed", "stated", "section")
STRUCTURAL_ACCORDING_TO_RE = re.compile(
    r"according to the (wiki|page|article|chapter|entry|infobox|section|speculation|text|list)\b",
    re.IGNORECASE,
)

# D31 floors, approved 2026-07-24 from real chunks_labeled.jsonl pool sizes
# (eligible pool 1,719/1,761 after task 8's exclusion; re-verified at
# 1,696/1,761 after task 8a's extended exclusion above — near-unchanged,
# confirmed rather than assumed per Part C, since none of the newly-
# excluded navigational sections happen to be book_level=3). book_level=
# 1/2 each drawn to a target of 60 — prose-dominant, with a floor of 10
# for infobox/quote so neither vanishes. book_level=3 takes its whole
# eligible pool (28: 22 prose/5 infobox/1 quote) rather than a forced
# floor — too small/speculative to subsample, same stance D31 already
# takes on book-3 parity. The quote floor is unreachable there (only 1
# chunk exists) — a real, reported shortfall, not silently patched.
STRATA_CONFIG = {
    1: {"target": 60, "floor_infobox": 10, "floor_quote": 10},
    2: {"target": 60, "floor_infobox": 10, "floor_quote": 10},
    3: {"target": None, "floor_infobox": 0, "floor_quote": 0},  # take-all stratum
}

ESTIMATED_OUTPUT_TOKENS_PER_CHUNK = 40
PRICE_PER_1M_INPUT = 0.75
PRICE_PER_1M_OUTPUT = 4.50
PRICE_PER_1M_CACHED_INPUT = 0.075
TOKENIZER_ENCODING = "o200k_base"

MAX_RETRIES = 3
RETRY_BACKOFF_S = 2.0
# D41/task 8a: zero-tolerance automated gate on wiki-metatextual leakage
# (has_banned_reference) - regenerate on a hit rather than hand-editing
# around it. Separate from MAX_RETRIES (transient API errors).
MAX_CONTENT_RETRIES = 4

log = logging.getLogger(__name__)


class QuestionResult(BaseModel):
    question: str


INSTRUCTIONS = """You are a curious reader of the Kingkiller Chronicle wiki, \
not a quiz-writer testing recall. For the given chunk, write exactly ONE \
natural-language question you would genuinely want answered, whose answer is \
fully contained in this chunk's text.

Requirements:
  - ONE thing, not several: ask a single focused question. Never join two \
distinct asks with "and" (e.g. NOT "What did X do, and why did Y happen?"). \
Never request an exhaustive list of every item/fact the chunk states - pick \
the single most interesting fact and ask about that one.
  - Self-contained: the question must be answerable using only this chunk's \
content, without needing outside context.
  - Specific, not generic: ground the question in a specific fact, entity, \
relationship, or detail this chunk actually states, not a boilerplate \
question that any chunk about the page's general topic could equally \
answer (avoid bare "Who is X?" / "What is X?" when the chunk states \
something more particular than an identity or one-line definition).
  - Don't quote long verbatim phrases from the text back into the question - \
paraphrase naturally, the way a real user unfamiliar with the exact wording \
would ask.
  - Never reference the wiki's own document structure: do not use the words \
"infobox," "listed," "stated," or "section," and do not write "according to \
the page/wiki/article/chapter/entry/speculation/text/list." Ask about the \
world and story directly, as if you already know it firsthand, not about \
what a document says about it. Exception: attributing something to an \
in-story person or being by name (e.g. "According to Kvothe...", "According \
to the Cthaeh...") is natural and encouraged, especially for quote chunks - \
the ban is on referencing the SOURCE DOCUMENT, not on in-world attribution.
  - Speculative/theory content is fair game and should use ordinary topical \
words a reader would actually use - "theory," "speculation," "mystery," \
"unresolved," "some readers/fans believe" - phrased as genuine curiosity \
about an in-world mystery, never as "according to the speculation" (a \
document-structure reference, banned above).
  - For infobox chunks: ask about a specific field's value actually listed \
(a location, role, attribute), not a request to "list the infobox."
  - For quote chunks: ask who said something, in what circumstance, or what \
a specific line means or refers to - not just "what did X say" when the \
quote is the entire answerable content.

Output only the question text, nothing else."""


def excluded_category(chunk: dict) -> str | None:
    if chunk["ns"] == 112 and chunk["chunk_type"] == "infobox":
        return "chapter-infobox"
    heading = chunk["section_heading"] or ""
    if SILENCE_HEADING_RE.search(heading):
        return "silence-heading"
    leaf = heading.split(">")[-1].strip().lower()
    if leaf in NAVIGATIONAL_HEADING_LEAVES:
        return "navigational-heading"
    return None


def has_banned_reference(question: str) -> str | None:
    """D41: detect wiki-metatextual leakage. Returns the offending term/
    pattern name, or None if the question is clean."""
    for term in STRUCTURAL_BARE_TERMS:
        if re.search(rf"\b{term}\b", question, re.IGNORECASE):
            return term
    if STRUCTURAL_ACCORDING_TO_RE.search(question):
        return "according-to-the-X"
    return None


def eligible_pool(chunks: list[dict]) -> list[dict]:
    return [c for c in chunks if excluded_category(c) is None]


def draw_questions_pool(chunks: list[dict]) -> tuple[list[dict], dict]:
    """Floor-stratified draw across book_level x chunk_type (D31).

    Deterministic: fixed seed, pool order comes from the (deterministic)
    input file order.
    """
    pool = eligible_pool(chunks)
    rng = random.Random(SEED)

    by_cell: dict[tuple[int, str], list[dict]] = {}
    for c in pool:
        by_cell.setdefault((c["book_level"], c["chunk_type"]), []).append(c)

    drawn: list[dict] = []
    cell_stats: dict[str, dict] = {}
    for level, cfg in STRATA_CONFIG.items():
        level_cells = {ct: by_cell.get((level, ct), []) for ct in ("prose", "infobox", "quote")}

        if cfg["target"] is None:
            for ct, cell_chunks in level_cells.items():
                drawn.extend(cell_chunks)
                cell_stats[f"{level}:{ct}"] = {"available": len(cell_chunks), "drawn": len(cell_chunks)}
            continue

        floor_drawn: dict[str, list[dict]] = {}
        for ct, floor_key in (("infobox", "floor_infobox"), ("quote", "floor_quote")):
            n = min(cfg[floor_key], len(level_cells[ct]))
            floor_drawn[ct] = rng.sample(level_cells[ct], n)
            cell_stats[f"{level}:{ct}"] = {"available": len(level_cells[ct]), "drawn": n}

        prose_target = cfg["target"] - sum(len(v) for v in floor_drawn.values())
        prose_n = min(max(prose_target, 0), len(level_cells["prose"]))
        prose_drawn = rng.sample(level_cells["prose"], prose_n)
        cell_stats[f"{level}:prose"] = {"available": len(level_cells["prose"]), "drawn": prose_n}

        drawn.extend(prose_drawn)
        for v in floor_drawn.values():
            drawn.extend(v)

    drawn.sort(key=lambda c: c["chunk_id"])

    ids = [c["chunk_id"] for c in drawn]
    assert len(ids) == len(set(ids)), "duplicate chunk_ids drawn"
    pool_ids = {c["chunk_id"] for c in pool}
    assert set(ids) <= pool_ids, "drawn chunk outside eligible pool"

    stats = {
        "total_chunks": len(chunks),
        "eligible_pool": len(pool),
        "excluded": len(chunks) - len(pool),
        "drawn_total": len(drawn),
        "cells": cell_stats,
    }
    return drawn, stats


def build_user_message(page_title: str, section_heading: str, chunk_type: str, text: str) -> str:
    heading = section_heading or "(lede)"
    return (
        f"Page: {page_title}\n"
        f"Section: {heading}\n"
        f"Chunk type: {chunk_type}\n\n"
        f"{chunk_content(text)}"
    )


def _call_once(client, message: str, model: str):
    """One structured-output call with transient-error retry. ``client``
    exposes ``.responses.parse(...)`` returning something with
    ``.output_parsed`` - real OpenAI client or a test double (same shape
    as ingest.label_llm.label_chunk)."""
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            return client.responses.parse(
                model=model,
                instructions=INSTRUCTIONS,
                input=message,
                text_format=QuestionResult,
            )
        except Exception as exc:  # noqa: BLE001 - retry any transient API error
            last_error = exc
            if attempt < MAX_RETRIES - 1:
                log.warning(
                    "generate_question call: %s (attempt %d/%d), retrying",
                    exc, attempt + 1, MAX_RETRIES,
                )
                time.sleep(RETRY_BACKOFF_S * (attempt + 1))
    raise RuntimeError(f"giving up after {MAX_RETRIES} tries") from last_error


def generate_question(client, chunk: dict, model: str = MODEL) -> dict:
    """D41: regenerates (not hand-edits) on a banned-reference hit
    (has_banned_reference), up to MAX_CONTENT_RETRIES - zero tolerance for
    wiki-metatextual leakage. Token usage accumulates across every attempt
    (including discarded ones), so cost accounting reflects real spend."""
    message = build_user_message(
        chunk["page_title"], chunk["section_heading"], chunk["chunk_type"], chunk["text"]
    )

    input_tokens = cached_tokens = output_tokens = 0
    result = None
    violation = None
    for content_attempt in range(MAX_CONTENT_RETRIES):
        response = _call_once(client, message, model)
        result = response.output_parsed
        usage = response.usage
        if usage:
            input_tokens += usage.input_tokens
            cached_tokens += usage.input_tokens_details.cached_tokens
            output_tokens += usage.output_tokens

        violation = has_banned_reference(result.question)
        if violation is None:
            break
        log.warning(
            "generate_question %s: banned reference %r in %r (attempt %d/%d), regenerating",
            chunk["chunk_id"], violation, result.question, content_attempt + 1, MAX_CONTENT_RETRIES,
        )
    else:
        log.warning(
            "generate_question %s: still violating (%r) after %d regeneration attempts - keeping last",
            chunk["chunk_id"], violation, MAX_CONTENT_RETRIES,
        )

    return {
        "question": result.question,
        "chunk_id": chunk["chunk_id"],
        "book_level": chunk["book_level"],
        "chunk_type": chunk["chunk_type"],
        "model": model,
        "input_tokens": input_tokens,
        "cached_tokens": cached_tokens,
        "output_tokens": output_tokens,
        "banned_reference": violation,
    }


def generate_questions(client, chunks: list[dict], model: str = MODEL) -> list[dict]:
    records = []
    for i, chunk in enumerate(chunks, start=1):
        records.append(generate_question(client, chunk, model=model))
        if i % 20 == 0 or i == len(chunks):
            log.info("generated %d/%d questions", i, len(chunks))
    return records


def banned_term_violations(records: list[dict]) -> list[dict]:
    """D41's automated gate: every record still flagged after generation's
    own regenerate-on-violation loop gave up. Zero tolerance means this
    should be empty for a real run; non-empty is a finding to report, not
    silently drop or hand-edit."""
    return [r for r in records if r.get("banned_reference")]


def estimate_cost(chunks: list[dict], model: str = MODEL) -> dict:
    """Token/cost estimate from local tokenisation - no API calls."""
    enc = tiktoken.get_encoding(TOKENIZER_ENCODING)
    instructions_tokens = len(enc.encode(INSTRUCTIONS))

    input_tokens = 0
    for c in chunks:
        message = build_user_message(c["page_title"], c["section_heading"], c["chunk_type"], c["text"])
        input_tokens += instructions_tokens + len(enc.encode(message))

    output_tokens = ESTIMATED_OUTPUT_TOKENS_PER_CHUNK * len(chunks)
    cost_usd = (
        input_tokens / 1_000_000 * PRICE_PER_1M_INPUT
        + output_tokens / 1_000_000 * PRICE_PER_1M_OUTPUT
    )
    return {
        "chunks": len(chunks),
        "model": model,
        "tokenizer_encoding": TOKENIZER_ENCODING,
        "input_tokens": input_tokens,
        "output_tokens_est": output_tokens,
        "cost_usd_est": round(cost_usd, 4),
        "price_per_1m_input": PRICE_PER_1M_INPUT,
        "price_per_1m_output": PRICE_PER_1M_OUTPUT,
    }


def actual_cost(records: list[dict]) -> dict:
    input_tokens = sum(r["input_tokens"] for r in records)
    cached_tokens = sum(r["cached_tokens"] for r in records)
    output_tokens = sum(r["output_tokens"] for r in records)
    uncached_tokens = input_tokens - cached_tokens
    cost_usd = (
        uncached_tokens / 1_000_000 * PRICE_PER_1M_INPUT
        + cached_tokens / 1_000_000 * PRICE_PER_1M_CACHED_INPUT
        + output_tokens / 1_000_000 * PRICE_PER_1M_OUTPUT
    )
    return {
        "chunks": len(records),
        "input_tokens": input_tokens,
        "cached_tokens": cached_tokens,
        "cache_hit_rate": cached_tokens / input_tokens if input_tokens else 0.0,
        "output_tokens": output_tokens,
        "cost_usd": round(cost_usd, 4),
    }


def load_chunks(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Single-hop question generation (D31 stratified draw; D40 binary ground truth)."
    )
    parser.add_argument("--input", type=Path, default=Path("data/chunks_labeled.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/eval/questions.jsonl"))
    parser.add_argument(
        "--chunks", type=int, default=None, metavar="N",
        help="limit to the first N drawn chunks (smoke run)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="estimate tokens and cost from local tokenisation only; no API calls",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    chunks = load_chunks(args.input)
    drawn, stats = draw_questions_pool(chunks)
    log.info(
        "eligible pool %d/%d chunks (excluded %d); drew %d questions",
        stats["eligible_pool"], stats["total_chunks"], stats["excluded"], stats["drawn_total"],
    )
    if args.chunks is not None:
        drawn = drawn[: args.chunks]

    if args.dry_run:
        cost = estimate_cost(drawn)
        print(f"chunks to generate: {cost['chunks']} (model={cost['model']})")
        print(f"estimated input tokens:  {cost['input_tokens']:,}")
        print(f"estimated output tokens: {cost['output_tokens_est']:,} (approximation, not measured)")
        print(
            f"estimated cost: ${cost['cost_usd_est']:.4f} "
            f"(${cost['price_per_1m_input']}/1M in, ${cost['price_per_1m_output']}/1M out, "
            f"tokenised with {cost['tokenizer_encoding']})"
        )
        print("stratification (level:chunk_type -> drawn/available):")
        for cell, s in stats["cells"].items():
            print(f"  {cell}: {s['drawn']}/{s['available']}")
        return 0

    from dotenv import load_dotenv
    load_dotenv()
    from openai import OpenAI

    client = OpenAI()
    t0 = time.monotonic()
    records = generate_questions(client, drawn)
    duration_s = time.monotonic() - t0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    output_rows = [
        {
            "question": r["question"],
            "chunk_id": r["chunk_id"],
            "book_level": r["book_level"],
            "chunk_type": r["chunk_type"],
        }
        for r in records
    ]
    output_text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in output_rows)
    args.output.write_text(output_text, encoding="utf-8")

    violations = banned_term_violations(records)
    if violations:
        log.warning(
            "D41 gate: %d/%d questions still violate the banned-reference constraint after retries: %s",
            len(violations), len(records), [(v["chunk_id"], v["banned_reference"]) for v in violations],
        )
    else:
        log.info("D41 gate: 0/%d questions violate the banned-reference constraint", len(records))

    cost = actual_cost(records)
    manifest = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "supersedes": "task 8's original questions.jsonl/questions_manifest.json (D41: void due to "
                       "wiki-metatextual leakage, compound/quiz-style questions, and a pool-exclusion "
                       "gap found on human review) - not a silent overwrite.",
        "input": str(args.input),
        "model": MODEL,
        "prompt_version": PROMPT_VERSION,
        "seed": SEED,
        "questions_total": len(output_rows),
        "stratification": stats,
        "banned_reference_gate_violations": len(violations),
        "duration_s": round(duration_s, 1),
        "tool_version": TOOL_VERSION,
        "actual_cost": cost,
    }
    args.output.with_name(args.output.stem + "_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    log.info("wrote %d questions to %s (%.1fs)", len(output_rows), args.output, duration_s)
    print(
        f"actual cost: ${cost['cost_usd']:.4f} ({cost['chunks']} chunks, "
        f"cache hit rate {cost['cache_hit_rate']:.1%}, "
        f"input={cost['input_tokens']:,} cached={cost['cached_tokens']:,} output={cost['output_tokens']:,})"
    )
    print(f"D41 banned-reference gate: {len(violations)} violation(s) remaining")
    return 0


if __name__ == "__main__":
    sys.exit(main())

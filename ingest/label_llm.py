"""Ingestion stage 3: LLM labeling pass over label_provenance=null chunks.

Fills in book_level for the ~72% of chunks (D11) that carry no gold
(chapter |book=) or citation ({{ref}}/<ref>) signal. Structured-output
call per chunk (page title + section heading + chunk type + text only —
no citation codes or provenance, D12); confidence="low" is overridden to
the conservative default (D12) before writing.

Run: ``uv run python -m ingest.label_llm --dry-run`` (cost estimate,
no API calls) or ``uv run python -m ingest.label_llm --chunks N``
(small live run). See docs/decisions/pipeline.md D13 for the acceptance
gate that must pass before a full (--chunks omitted, no --dry-run) run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import tiktoken
from pydantic import BaseModel

MODEL = "gpt-5.4-mini"
CONSERVATIVE_DEFAULT_LEVEL = 3  # D12: uncertain -> highest (most restrictive) level
TOOL_VERSION = "0.1"
PROMPT_VERSION = "D28"  # docs/decisions/labeling.md - last revision folded into INSTRUCTIONS

# Pricing sourced from https://developers.openai.com/api/docs/pricing on
# 2026-07-22. gpt-5.4-mini has no tiktoken model mapping yet (checked against
# tiktoken 0.13.0's tokeniser table), so token counts use o200k_base — the
# encoding shared by current-generation OpenAI models — as an approximation.
# Re-check both before trusting a cost estimate for real spend.
PRICE_PER_1M_INPUT = 0.75
PRICE_PER_1M_OUTPUT = 4.50
# Cached-input rate for repeated prompt prefixes (our INSTRUCTIONS block is
# byte-identical across every call) - a 90% discount off PRICE_PER_1M_INPUT,
# same source/date as above. Whether this is actually realized depends on
# provider-side caching behavior; label_chunk() logs response.usage so real
# cache hit rate can be measured rather than assumed.
PRICE_PER_1M_CACHED_INPUT = 0.075
TOKENIZER_ENCODING = "o200k_base"

# A structured {book_level, confidence, rationale} reply: a few JSON-shape
# tokens plus a one-sentence rationale. Not measured from a live call (that
# would defeat the point of --dry-run); revise once Part 2 usage data exists.
ESTIMATED_OUTPUT_TOKENS_PER_CHUNK = 60

MAX_RETRIES = 3
RETRY_BACKOFF_S = 2.0

log = logging.getLogger(__name__)


class LabelResult(BaseModel):
    # Field order is generation order (D28): rationale first, so book_level
    # and confidence are constrained to follow from reasoning already
    # committed to, rather than a label chosen first and rationalized after.
    rationale: str
    book_level: Literal[1, 2, 3]
    confidence: Literal["low", "medium", "high"]


INSTRUCTIONS = """You are labeling short excerpts from a Kingkiller Chronicle \
wiki for a spoiler-gated RAG system. For each chunk, decide the highest book \
level whose content it reveals.

Book levels:
  1 - everything stated is established in The Name of the Wind.
  2 - anything requires The Wise Man's Fear. Side stories count as 2: The \
Slow Regard of Silent Things, The Lightning Tree, The Narrow Road Between \
Desires, How Old Holly Came to Be.
  3 - anything reveals The Doors of Stone / unpublished material (prologue \
text, Rothfuss statements about book three's content).

The core rule: judge what the text REVEALS, not what it MENTIONS.
  - "She reappears later" reveals nothing book-2 - a forward reference with \
no content is level 1.
  - "She reappears later and trains him in her homeland" reveals book-2 \
content - level 2.
  - A bare, unattached mention of a book title (e.g. a References section \
that is just the plain text "The Name of the Wind" / "The Wise Man's Fear", \
or an interwiki-link line like "es:Imre") is not a claim about content and \
never escalates the level on its own.
  - Contrast that with direct self-identification: a chunk stating that ITS \
OWN content belongs to a specific book (e.g. "Elderberry is the hundred \
fifty-second and last numbered chapter of the novel The Wise Man's Fear") \
functions as a citation-equivalent signal and DOES escalate to that book's \
level - the book title is naming the direct source of the specific claim \
the chunk is making about itself, unlike an untethered reference list. This \
applies to any content, not just chapter pages.

Frame story: the present-day frame narration (Kote/Bast/Chronicler at the \
Waystone Inn) runs through all three books - it is not itself a Doors of \
Stone signal. Judge frame-story chunks the same way as any other: by what \
backstory or plot content they actually disclose, not by the presence of \
the frame device. A frame scene that discloses nothing beyond established \
background is level 1, however "present-day" or "prologue-flavored" it \
reads. This includes frame-story SUSPENSE, not just frame-story presence: \
unresolved mystery, foreboding, and things-left-unexplained are a core \
device running through Books 1 and 2, not a signal of unpublished \
material. Book level 3 should be grounded in something SPECIFIC - an \
explicit Doors of Stone / unpublished-material reference, or content that \
is plainly the prologue of the unpublished third book - never in a scene \
merely "feeling" ominous, mysterious, or unresolved. If you cannot point \
to that something specific, the chunk is not level 3 just because it is \
tense or withholds an explanation; register LOW confidence instead of a \
confident but ungrounded guess.

Introduction vs. resolution: book_level judges DISCLOSURE, not narrative \
significance. Introducing an unresolved mystery, strange object, or \
ominous detail is establishing content at whatever book_level it first \
appears - it does NOT itself imply a later book, even when the mystery's \
eventual resolution lies further along or unpublished. A sealed chest \
first described, an attack whose culprit is unknown, a creature nobody \
has named yet: these are book-of-introduction content, however dramatic \
or dangerous they read. Escalate ONLY when a chunk actually RESOLVES, \
EXPLAINS, or EXTENDS a previously-established mystery with genuinely NEW \
information beyond its book of introduction - never merely because the \
content is dramatic, dangerous, or thematically important. A tense scene \
is not evidence of a later book; a scene that answers a question raised \
earlier is.

Entity-introduction floor: for ANY chunk - lede, description, infobox, \
trivia, real-world-references, or any other section - first ask whether \
the entity it is about (the person, place, or group) is something a \
reader with only Book 1 could already know exists. If the entity is \
first introduced in Book 2 or later (e.g. a companion first met when \
Kvothe travels to Ademre), Book 2 is a FLOOR under every chunk about \
that entity, regardless of chunk type or content genre - even when a \
given chunk's content, taken alone, looks as mundane and static as any \
Book-1-reachable entity's, and even when it is pure real-world trivia \
(etymology, translations) with no in-story claim at all. The mandatory \
page-title/section-heading prefix on every chunk discloses the entity's \
existence by itself; the disclosure is the entity existing, not any one \
field, sentence, or content genre.

Infobox chunks (structured "key: value" lines): once an entity is \
already Book-1-reachable (e.g. Severen - named in a Book-1 letter and \
shown on the Book-1 map, well before Kvothe travels there), apply this \
split: static facts (region, government type, currency, species) never \
escalate book_level by themselves; relational facts (e.g. ruler, \
affiliation, family) escalate ONLY if the pairing itself is a story \
disclosure (something that happens in the plot), not if it is just \
background civic or genealogical structure. Example: Severen's infobox \
naming its ruler is background lore, not a disclosure, even though \
Kvothe only visits Severen in a later book.

Be conservative in the direction of protecting spoilers, but do not invent \
implied information absent from the given text - the point is to find the \
level actually revealed, not to imagine what an insider would infer.

confidence is a categorical judgment ("low", "medium", "high") of how sure \
you are in the book_level call, not a fabricated numeric probability. Use \
"low" whenever the excerpt is genuinely ambiguous or needs context it does \
not itself provide.

rationale is one sentence explaining the book_level you chose."""


def prompt_hash() -> str:
    """Short sha256 of the current INSTRUCTIONS text. The prompt is
    versioned in-repo (D12/PROMPT_VERSION); this hash ties a manifest to
    the exact prompt text that produced it, independent of that tag."""
    return hashlib.sha256(INSTRUCTIONS.encode("utf-8")).hexdigest()[:12]


def chunk_content(text: str) -> str:
    """Strip the 'page title [§ heading]\\n\\n' header line chunk_pages.py
    prepends to every chunk's text, leaving only the body content."""
    _, sep, content = text.partition("\n\n")
    return content if sep else text


def build_user_message(
    page_title: str, section_heading: str, chunk_type: str, text: str
) -> str:
    """Pure: only the fields the labeler is allowed to see (D12) - no
    citation_codes, no label_provenance, no other chunk metadata."""
    heading = section_heading or "(lede)"
    return (
        f"Page: {page_title}\n"
        f"Section: {heading}\n"
        f"Chunk type: {chunk_type}\n\n"
        f"{chunk_content(text)}"
    )


def apply_conservative_default(result: LabelResult) -> tuple[int, bool]:
    """confidence=low -> override to the conservative default (D12).

    Returns (applied_level, overridden).
    """
    if result.confidence == "low":
        return CONSERVATIVE_DEFAULT_LEVEL, True
    return result.book_level, False


def label_chunk(client, chunk: dict, model: str = MODEL) -> dict:
    """One structured-output call + conservative-default post-processing.

    ``client`` is any object exposing ``.responses.parse(...)`` returning
    something with ``.output_parsed`` - real OpenAI client or a test double.
    """
    message = build_user_message(
        chunk["page_title"], chunk["section_heading"], chunk["chunk_type"], chunk["text"]
    )

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            response = client.responses.parse(
                model=model,
                instructions=INSTRUCTIONS,
                input=message,
                text_format=LabelResult,
            )
            break
        except Exception as exc:  # noqa: BLE001 - retry any transient API error
            last_error = exc
            if attempt < MAX_RETRIES - 1:
                log.warning(
                    "label_chunk %s: %s (attempt %d/%d), retrying",
                    chunk["chunk_id"], exc, attempt + 1, MAX_RETRIES,
                )
                time.sleep(RETRY_BACKOFF_S * (attempt + 1))
    else:
        raise RuntimeError(f"giving up on {chunk['chunk_id']} after {MAX_RETRIES} tries") from last_error

    result = response.output_parsed
    applied_level, overridden = apply_conservative_default(result)
    usage = response.usage
    cached_tokens = usage.input_tokens_details.cached_tokens if usage else 0
    input_tokens = usage.input_tokens if usage else 0
    output_tokens = usage.output_tokens if usage else 0
    log.info(
        "usage %s: input=%d cached=%d (%.0f%%) output=%d",
        chunk["chunk_id"], input_tokens, cached_tokens,
        100 * cached_tokens / input_tokens if input_tokens else 0.0, output_tokens,
    )
    return {
        "chunk_id": chunk["chunk_id"],
        "book_level": applied_level,
        "book_level_raw": result.book_level,
        "confidence": result.confidence,
        "rationale": result.rationale,
        "overridden": overridden,
        "model": model,
        "input_tokens": input_tokens,
        "cached_tokens": cached_tokens,
        "output_tokens": output_tokens,
    }


def label_chunks(client, chunks: list[dict], model: str = MODEL) -> list[dict]:
    records = []
    for i, chunk in enumerate(chunks, start=1):
        records.append(label_chunk(client, chunk, model=model))
        if i % 20 == 0 or i == len(chunks):
            log.info("labeled %d/%d chunks", i, len(chunks))
    return records


def actual_cost(records: list[dict]) -> dict:
    """Real cost from observed usage (label_chunk's input/cached/output_tokens),
    as opposed to estimate_cost's pre-call, no-caching approximation."""
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


def assemble_labeled_chunks(chunks: list[dict], records: list[dict]) -> list[dict]:
    """D14's third pipeline artifact: every chunk from chunks.jsonl, with
    gold/citation-tier chunks passed through unchanged and null-provenance
    chunks filled in with this run's LLM labels - book_level_raw and
    label_confidence alongside the (possibly conservative-default-overridden)
    applied book_level, per D12's logging spec."""
    records_by_id = {r["chunk_id"]: r for r in records}
    null_ids = {c["chunk_id"] for c in chunks if c["label_provenance"] is None}
    if records_by_id.keys() != null_ids:
        missing = null_ids - records_by_id.keys()
        extra = records_by_id.keys() - null_ids
        raise ValueError(
            f"records don't match null-provenance chunks: "
            f"{len(missing)} missing, {len(extra)} unexpected"
        )

    assembled = []
    for c in chunks:
        if c["label_provenance"] is None:
            r = records_by_id[c["chunk_id"]]
            c = {
                **c,
                "book_level": r["book_level"],
                "book_level_raw": r["book_level_raw"],
                "label_confidence": r["confidence"],
                "label_provenance": "llm",
            }
        assembled.append(c)
    return assembled


def label_provenance_breakdown(chunks: list[dict]) -> dict:
    breakdown: dict[str, int] = {}
    for c in chunks:
        key = c["label_provenance"] or "null"
        breakdown[key] = breakdown.get(key, 0) + 1
    return breakdown


def confidence_distribution(records: list[dict]) -> dict:
    dist = {"low": 0, "medium": 0, "high": 0}
    for r in records:
        dist[r["confidence"]] += 1
    return dist


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


def load_chunks(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def null_provenance_frame(chunks: list[dict]) -> list[dict]:
    return [c for c in chunks if c["label_provenance"] is None]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="LLM labeling pass over label_provenance=null chunks (D12)."
    )
    parser.add_argument("--input", type=Path, default=Path("data/chunks.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/chunks_labeled.jsonl"))
    parser.add_argument(
        "--chunks", type=int, default=None, metavar="N",
        help="limit to the first N null-provenance chunks (validation / smoke runs)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="estimate tokens and cost from local tokenisation only; no API calls",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    chunks = load_chunks(args.input)
    frame = null_provenance_frame(chunks)
    log.info("%d/%d chunks are label_provenance=null", len(frame), len(chunks))
    if args.chunks is not None:
        frame = frame[: args.chunks]

    if args.dry_run:
        stats = estimate_cost(frame)
        print(f"chunks: {stats['chunks']} (model={stats['model']})")
        print(f"estimated input tokens:  {stats['input_tokens']:,}")
        print(f"estimated output tokens: {stats['output_tokens_est']:,} (approximation, not measured)")
        print(
            f"estimated cost: ${stats['cost_usd_est']:.4f} "
            f"(${stats['price_per_1m_input']}/1M in, ${stats['price_per_1m_output']}/1M out, "
            f"tokenised with {stats['tokenizer_encoding']})"
        )
        return 0

    full_run = args.chunks is None
    if full_run:
        from ingest.draw_sample import verify_frozen
        verify_frozen(args.input)  # D14: labeling runs against the frozen chunk set

    from dotenv import load_dotenv
    load_dotenv()
    from openai import OpenAI

    client = OpenAI()
    t0 = time.monotonic()
    records = label_chunks(client, frame)
    duration_s = time.monotonic() - t0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    cost = actual_cost(records)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if full_run:
        # D14's third pipeline artifact: the full chunk set, gold/citation
        # rows unchanged, null-provenance rows filled in with this run's
        # LLM labels.
        assembled = assemble_labeled_chunks(chunks, records)
        assert len(assembled) == len(chunks), "assembled row count must match chunks.jsonl"
        assert all(c["book_level"] is not None for c in assembled), "every row must have a book_level"
        ids = [c["chunk_id"] for c in assembled]
        assert len(ids) == len(set(ids)), "chunk_id collision in assembled output"

        args.output.write_text(
            "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in assembled),
            encoding="utf-8",
        )
        manifest = {
            "generated_at": generated_at,
            "input": str(args.input),
            "model": MODEL,
            "prompt_version": PROMPT_VERSION,
            "prompt_hash": prompt_hash(),
            "chunks_total": len(assembled),
            "chunks_labeled_this_run": len(records),
            "overridden_count": sum(r["overridden"] for r in records),
            "label_provenance_breakdown": label_provenance_breakdown(assembled),
            "confidence_distribution": confidence_distribution(records),
            "duration_s": round(duration_s, 1),
            "tool_version": TOOL_VERSION,
            "actual_cost": cost,
        }
        log.info("wrote %d assembled chunks to %s (%.1fs)", len(assembled), args.output, duration_s)
    else:
        args.output.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
            encoding="utf-8",
        )
        manifest = {
            "generated_at": generated_at,
            "input": str(args.input),
            "model": MODEL,
            "chunks_labeled": len(records),
            "overridden_count": sum(r["overridden"] for r in records),
            "duration_s": round(duration_s, 1),
            "tool_version": TOOL_VERSION,
            "actual_cost": cost,
        }
        log.info("wrote %d labeled chunks to %s (%.1fs)", len(records), args.output, duration_s)

    args.output.with_name(args.output.stem + "_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"actual cost: ${cost['cost_usd']:.4f} ({cost['chunks']} chunks, "
        f"cache hit rate {cost['cache_hit_rate']:.1%}, "
        f"input={cost['input_tokens']:,} cached={cost['cached_tokens']:,} output={cost['output_tokens']:,})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

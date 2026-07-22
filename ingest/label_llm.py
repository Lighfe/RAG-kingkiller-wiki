"""Ingestion stage 3: LLM labeling pass over label_provenance=null chunks.

Fills in book_level for the ~72% of chunks (D11) that carry no gold
(chapter |book=) or citation ({{ref}}/<ref>) signal. Structured-output
call per chunk (page title + section heading + chunk type + text only —
no citation codes or provenance, D12); confidence="low" is overridden to
the conservative default (D12) before writing.

Run: ``uv run python -m ingest.label_llm --dry-run`` (cost estimate,
no API calls) or ``uv run python -m ingest.label_llm --chunks N``
(small live run). See docs/decisions.md D13 for the acceptance gate
that must pass before a full (--chunks omitted, no --dry-run) run.
"""

from __future__ import annotations

import argparse
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

# Pricing sourced from https://developers.openai.com/api/docs/pricing on
# 2026-07-22. gpt-5.4-mini has no tiktoken model mapping yet (checked against
# tiktoken 0.13.0's tokeniser table), so token counts use o200k_base — the
# encoding shared by current-generation OpenAI models — as an approximation.
# Re-check both before trusting a cost estimate for real spend.
PRICE_PER_1M_INPUT = 0.75
PRICE_PER_1M_OUTPUT = 4.50
TOKENIZER_ENCODING = "o200k_base"

# A structured {book_level, confidence, rationale} reply: a few JSON-shape
# tokens plus a one-sentence rationale. Not measured from a live call (that
# would defeat the point of --dry-run); revise once Part 2 usage data exists.
ESTIMATED_OUTPUT_TOKENS_PER_CHUNK = 60

MAX_RETRIES = 3
RETRY_BACKOFF_S = 2.0

log = logging.getLogger(__name__)


class LabelResult(BaseModel):
    book_level: Literal[1, 2, 3]
    confidence: Literal["low", "medium", "high"]
    rationale: str


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

Infobox chunks (structured "key: value" lines):
  - Static facts - region, government type, currency, species, and similar \
background-lore fields - never escalate book_level by themselves.
  - Relational facts (e.g. ruler, affiliation, family) escalate ONLY if the \
pairing itself is a story disclosure (something that happens in the plot), \
not if it is just background civic or genealogical structure. Example: a \
city's infobox naming its ruler is background lore, not a disclosure, even \
if the character only visits that city in a later book.

Be conservative in the direction of protecting spoilers, but do not invent \
implied information absent from the given text - the point is to find the \
level actually revealed, not to imagine what an insider would infer.

confidence is a categorical judgment ("low", "medium", "high") of how sure \
you are in the book_level call, not a fabricated numeric probability. Use \
"low" whenever the excerpt is genuinely ambiguous or needs context it does \
not itself provide.

rationale is one sentence explaining the book_level you chose."""


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
    return {
        "chunk_id": chunk["chunk_id"],
        "book_level": applied_level,
        "book_level_raw": result.book_level,
        "confidence": result.confidence,
        "rationale": result.rationale,
        "overridden": overridden,
        "model": model,
    }


def label_chunks(client, chunks: list[dict], model: str = MODEL) -> list[dict]:
    records = []
    for i, chunk in enumerate(chunks, start=1):
        records.append(label_chunk(client, chunk, model=model))
        if i % 20 == 0 or i == len(chunks):
            log.info("labeled %d/%d chunks", i, len(chunks))
    return records


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

    from openai import OpenAI

    client = OpenAI()
    t0 = time.monotonic()
    records = label_chunks(client, frame)
    duration_s = time.monotonic() - t0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
        encoding="utf-8",
    )
    manifest = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "input": str(args.input),
        "model": MODEL,
        "chunks_labeled": len(records),
        "overridden_count": sum(r["overridden"] for r in records),
        "duration_s": round(duration_s, 1),
        "tool_version": TOOL_VERSION,
    }
    args.output.with_name(args.output.stem + "_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    log.info("wrote %d labeled chunks to %s (%.1fs)", len(records), args.output, duration_s)
    return 0


if __name__ == "__main__":
    sys.exit(main())

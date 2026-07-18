"""Pipeline stage 2: pages.jsonl → chunks.jsonl (+ chunks_manifest.json).

Implements decisions D02–D11: pre-strip harvesting of labeling signals
(infobox params, citation codes, quote text, categories), section-aware
chunking with the lede as a first-class section, and deterministic
chunk-level labels (gold via chapter ``|book=``, citation via in-chunk
codes). Everything below the citation tier stays unlabeled for the LLM
pass — no page-level inheritance, no mention rule.

Deterministic by construction: same input → byte-identical chunks.jsonl
(fixed ordering, no timestamps in records; the manifest carries run
metadata).

Run: ``uv run python -m ingest.chunk_pages [--input FILE] [--output DIR]
[--limit N]``
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote as urlquote

import mwparserfromhell as mwph

from ingest.fetch_pages import _write_atomic

TOOL_VERSION = "0.1"
WIKI_BASE_URL = "https://kingkiller.fandom.com/wiki/"

MAX_WORDS = 380  # ≈500-token proxy (D05)
OVERLAP_WORDS = 40  # ≈50-token overlap between parts of a split (D06)
MIN_PAGE_WORDS = 20  # pure-infobox shells are dropped below this

# Citation code → book_level (D11). Side stories map to the trilogy level
# they presuppose (dataset-notes §3).
CODE_LEVELS = {
    "TNOTW": 1,
    "TWMF": 2,
    "TLT": 2,
    "TSROST": 2,
    "TNRBD": 2,
    "HOHCTB": 2,
    "TDOS": 3,
}
REF_TEMPLATE_VOCAB = {"TNOTW", "TWMF", "TLT", "TSROST"}
CHAPTER_BOOK_VOCAB = {"TNOTW", "TWMF", "TDOS"}

# Book-title strings recognized in <ref> bodies, chapter titles, and the
# chapter first-1.5k-chars fallback.
TITLE_CODES = {
    "the name of the wind": "TNOTW",
    "the wise man's fear": "TWMF",
    "the doors of stone": "TDOS",
    "the slow regard of silent things": "TSROST",
    "the lightning tree": "TLT",
    "the narrow road between desires": "TNRBD",
    "how old holly came to be": "HOHCTB",
}
CHAPTER_FALLBACK_CHARS = 1500

# D09: exact heading matches (case-insensitive, trimmed). Trivia is NOT here.
SPECULATION_HEADINGS = {
    "speculation",
    "speculations",
    "spoilers about book three",
    "book three",
    "possible seven word combinations",
    "spoilers for the doors of stone",
}

QUALITY_FLAG_TEMPLATES = ("stub", "needhelp", "conjecture")

# The 13-name verification set for structural infobox detection (D07).
KNOWN_INFOBOX_NAMES = {
    "character infobox", "location infobox", "chapter infobox",
    "object infobox", "group infobox", "book infobox", "product infobox",
    "song infobox", "species infobox", "person infobox", "game infobox",
    "play infobox", "character",
}

# Citation positions survive strip_code as private-use-area sentinels and
# are mapped to the chunk whose text span contains them.
SENTINEL_RE = re.compile("(\\d+)")

log = logging.getLogger(__name__)


@dataclass
class PageStats:
    dropped: bool = False
    stripped_words: int = 0
    empty_sections: int = 0
    split_sections: int = 0
    oversize_paragraphs: int = 0
    surprises: list[str] = field(default_factory=list)


def _sentinel(citation_id: int) -> str:
    return f"{citation_id}"


def _norm_name(name: str) -> str:
    return name.replace("_", " ").strip().casefold()


def _slugify(text: str) -> str:
    ascii_text = (
        unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug or "section"


def _plain(wikitext: str) -> str:
    return mwph.parse(wikitext).strip_code()


def _is_infobox(tpl) -> bool:
    """Structural detection (D07): ≥1 param, every param named key=value."""
    return bool(tpl.params) and all(p.showkey for p in tpl.params)


def _titles_in(text: str) -> list[str]:
    low = text.casefold()
    return [code for title, code in TITLE_CODES.items() if title in low]


def _clean_residue(text: str) -> str:
    """Targeted cleanup of what strip_code leaves behind: {|…|} table
    markup (cell text is kept — the verse tables are content), bare
    params, HTML comments, raw interwiki links, bold/italic ticks."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    lines: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("{|") or s.startswith("|}") or s.startswith(("|-", "|+")):
            continue
        m = re.match(r"^[|!](.*)$", s)
        if m:
            for cell in re.split(r"\|\||!!", m.group(1)):
                if "|" in cell:  # drop attribute prefix: width="50%"|Text
                    cell = cell.rpartition("|")[2]
                cell = cell.strip()
                if cell and not re.fullmatch(r"[\w\s-]+=\S*", cell):
                    lines.append(cell)
            continue
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"\[\[(?:[^\[\]|]*\|)?([^\[\]]*)\]\]", r"\1", text)
    text = re.sub(r"'{2,}", "", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_sections(code) -> list[dict]:
    """Split page wikicode on h2/h3 headings. The lede (path "") comes
    first; h3 paths carry their h2 parent: "History > Creation War"."""
    sections: list[dict] = []
    current: list = []
    path = ""
    h2 = ""

    def flush():
        sections.append({"path": path, "wikitext": "".join(str(n) for n in current)})

    for node in code.nodes:
        if isinstance(node, mwph.nodes.Heading) and node.level in (2, 3):
            flush()
            title = node.title.strip_code().strip()
            if node.level == 2:
                h2 = title
                path = title
            else:
                path = f"{h2} > {title}" if h2 else title
            current = []
        else:
            current.append(node)
    flush()
    return sections


class PageChunker:
    """Chunks one page record; pure — no I/O, no clocks (determinism)."""

    def __init__(self, record: dict, stats: PageStats):
        self.record = record
        self.stats = stats
        self.page_id = record["pageid"]
        self.title = record["title"]
        self.ns = record["ns"]
        self.citations: dict[int, list[str]] = {}  # citation id → codes
        self.next_citation_id = 0
        self.categories: list[str] = []
        self.infoboxes: list[dict] = []  # {"name", "params": [(k, v)]}
        self.quotes: list[dict] = []  # {"section", "text", "attribution", "codes"}
        self.quality_flags: list[str] = []
        self.chapter_book_code: str | None = None
        self.slug_seen: Counter[str] = Counter()

    def surprise(self, msg: str) -> None:
        full = f"{self.title}: {msg}"
        log.warning("surprise: %s", full)
        self.stats.surprises.append(full)

    # -- pre-strip harvesting (D03; order matters) --------------------

    def _harvest_section(self, sec_wikitext: str, path: str) -> str:
        """Run the D03 harvest cascade on one section; returns the
        cleaned plain text (with citation sentinels still embedded)."""
        code = mwph.parse(sec_wikitext)

        # 1. infoboxes — structural, top-level nodes only (nested
        # templates like {{map}} inside an infobox are its params' business)
        for tpl in [t for t in code.filter_templates(recursive=False) if _is_infobox(t)]:
            self._harvest_infobox(tpl)
            code.remove(tpl)

        # 2a. {{ref}} templates: first param is a book code
        for tpl in [
            t for t in code.filter_templates()
            if _norm_name(str(t.name)) == "ref"
        ]:
            codes = []
            if tpl.params:
                value = str(tpl.params[0].value).strip()
                codes = [value.upper()]
                if value.upper() not in REF_TEMPLATE_VOCAB:
                    self.surprise(f"unknown {{{{ref}}}} code {value!r} (not mapped to a level)")
            code.replace(tpl, self._register_citation(codes))

        # 2b. <ref> tags: body scanned for book-title strings
        for tag in [
            t for t in code.filter_tags()
            if str(t.tag).strip().lower() == "ref"
        ]:
            codes = _titles_in(_plain(str(tag.contents))) if tag.contents else []
            code.replace(tag, self._register_citation(codes))

        # 3. {{quote}} templates → quote chunks (D08)
        for tpl in [
            t for t in code.filter_templates()
            if _norm_name(str(t.name)) == "quote"
        ]:
            self._harvest_quote(tpl, path)
            code.remove(tpl)

        # 4. [[Category:…]] links
        for link in [
            l for l in code.filter_wikilinks()
            if str(l.title).strip().casefold().startswith("category:")
        ]:
            name = str(link.title).strip().split(":", 1)[1].strip()
            if name and name not in self.categories:
                self.categories.append(name)
            code.remove(link)

        return _clean_residue(code.strip_code())

    def _register_citation(self, codes: list[str]) -> str:
        """Swap a harvested citation for a positional sentinel; refs that
        yielded no codes are simply removed (their bodies must not leak)."""
        if not codes:
            return ""
        cid = self.next_citation_id
        self.next_citation_id += 1
        self.citations[cid] = codes
        return _sentinel(cid)

    def _harvest_infobox(self, tpl) -> None:
        name = _norm_name(str(tpl.name))
        if name not in KNOWN_INFOBOX_NAMES:
            self.surprise(f"template {{{{{name}}}}} detected as infobox (not in the known set)")
        params: list[tuple[str, str]] = []
        for p in tpl.params:
            key = str(p.name).strip()
            # image/file params carry no text; a bare date param is the
            # signature of maintenance banners ({{orphan}}, {{underlinked}}),
            # which then serialize to nothing and emit no chunk
            if re.search(r"image|file", key, re.IGNORECASE) or key.casefold() == "date":
                continue
            value = "; ".join(
                s.strip().lstrip("*").strip()
                for s in _plain(str(p.value)).splitlines()
                if s.strip()
            )
            if value:
                params.append((key, value))
            if self.ns == 112 and key.casefold() == "book":
                code_value = str(p.value).strip().upper()
                if code_value in CHAPTER_BOOK_VOCAB:
                    self.chapter_book_code = code_value
                else:
                    self.surprise(f"unknown chapter |book= value {code_value!r}")
        self.infoboxes.append({"name": name, "params": params})

    def _harvest_quote(self, tpl, path: str) -> None:
        def get(*names: str) -> str:
            for n in names:
                if tpl.has(n):
                    return str(tpl.get(n).value)
            return ""

        body = _plain(get("1", "quote", "text")).strip()
        attribution = _plain(get("2", "author", "attribution", "speaker")).strip()
        codes: list[str] = []
        for part in (body, attribution):
            for m in SENTINEL_RE.finditer(part):
                codes.extend(self.citations.pop(int(m.group(1)), []))
        body = SENTINEL_RE.sub("", body).strip()
        attribution = SENTINEL_RE.sub("", attribution).strip()
        if body:
            self.quotes.append(
                {"section": path, "text": body, "attribution": attribution, "codes": codes}
            )

    # -- labeling (D11) ----------------------------------------------

    def _gold_level(self, sections: list[dict]) -> int | None:
        """ns-112 fallback chain: |book= → title match → first ~1.5k chars."""
        if self.chapter_book_code:
            return CODE_LEVELS[self.chapter_book_code]
        title_codes = _titles_in(self.title)
        if title_codes:
            return max(CODE_LEVELS[c] for c in title_codes)
        head = self.record["wikitext"][:CHAPTER_FALLBACK_CHARS]
        head_codes = _titles_in(head)
        if head_codes:
            return max(CODE_LEVELS[c] for c in head_codes)
        self.surprise("ns-112 page but no book signal in infobox, title, or first 1.5k chars")
        return None

    # -- assembly ----------------------------------------------------

    def run(self) -> list[dict]:
        page_code = mwph.parse(self.record["wikitext"])
        self.quality_flags = sorted(
            {
                flag
                for tpl in page_code.filter_templates()
                for flag in QUALITY_FLAG_TEMPLATES
                if _norm_name(str(tpl.name)) == flag
            },
            key=QUALITY_FLAG_TEMPLATES.index,
        )
        conjecture_page = "conjecture" in self.quality_flags

        sections = _split_sections(page_code)
        for sec in sections:
            sec["text"] = self._harvest_section(sec["wikitext"], sec["path"])

        total_words = sum(len(SENTINEL_RE.sub("", s["text"]).split()) for s in sections)
        self.stats.stripped_words = total_words
        if total_words < MIN_PAGE_WORDS:
            self.stats.dropped = True
            log.info(
                "dropping %r: %d stripped words (< %d, pure-infobox shell)",
                self.title, total_words, MIN_PAGE_WORDS,
            )
            return []

        gold_level = self._gold_level(sections) if self.ns == 112 else None

        chunks: list[dict] = []
        for i, infobox in enumerate(self.infoboxes):
            chunk = self._infobox_chunk(infobox, i, gold_level, conjecture_page)
            if chunk:
                chunks.append(chunk)

        quotes_by_section: dict[str, list[dict]] = {}
        for q in self.quotes:
            quotes_by_section.setdefault(q["section"], []).append(q)
        quote_n = 0

        for sec in sections:
            if not sec["text"]:
                if sec["path"]:  # empty lede on a page with sections is normal
                    self.stats.empty_sections += 1
            else:
                chunks.extend(
                    self._prose_chunks(sec, gold_level, conjecture_page)
                )
            for q in quotes_by_section.get(sec["path"], []):
                chunks.append(
                    self._quote_chunk(q, quote_n, gold_level, conjecture_page)
                )
                quote_n += 1
        return chunks

    def _is_speculative(self, path: str) -> bool:
        return any(
            part.strip().casefold() in SPECULATION_HEADINGS
            for part in path.split(" > ")
        )

    def _prose_chunks(
        self, sec: dict, gold_level: int | None, conjecture_page: bool
    ) -> list[dict]:
        path = sec["path"]
        paragraphs = [p for p in sec["text"].split("\n\n") if p.strip()]

        parts: list[list[str]] = [[]]
        part_words = 0
        for para in paragraphs:
            n = len(SENTINEL_RE.sub("", para).split())
            if n > MAX_WORDS:
                self.stats.oversize_paragraphs += 1
                self.surprise(
                    f"single paragraph of {n} words in section {path or 'lede'!r} "
                    "exceeds the max chunk size; kept unsplit (paragraph is the "
                    "smallest split unit per D05)"
                )
            if parts[-1] and part_words + n > MAX_WORDS:
                parts.append([])
                part_words = 0
            parts[-1].append(para)
            part_words += n
        if len(parts) > 1:
            self.stats.split_sections += 1

        slug = "lede" if not path else _slugify(path)
        self.slug_seen[slug] += 1
        if self.slug_seen[slug] > 1:  # same heading twice on one page
            slug = f"{slug}-{self.slug_seen[slug]}"

        chunks = []
        prev_tail = ""
        for ordinal, part in enumerate(parts):
            raw = "\n\n".join(part)
            codes = [self.citations[int(m)] for m in SENTINEL_RE.findall(raw)]
            codes = [c for group in codes for c in group]
            clean = SENTINEL_RE.sub("", raw)
            clean = re.sub(r" {2,}", " ", clean)
            content = f"{prev_tail}\n\n{clean}" if prev_tail else clean
            prev_tail = " ".join(clean.split()[-OVERLAP_WORDS:])
            chunks.append(
                self._chunk(
                    slug=slug,
                    ordinal=ordinal,
                    heading=path,
                    chunk_type="prose",
                    content=content,
                    codes=codes,
                    gold_level=gold_level,
                    speculative=conjecture_page or self._is_speculative(path),
                )
            )
        return chunks

    def _infobox_chunk(
        self, infobox: dict, n: int, gold_level: int | None, conjecture_page: bool
    ) -> dict | None:
        if not infobox["params"]:
            return None
        content = "\n".join(f"{k}: {v}" for k, v in infobox["params"])
        return self._chunk(
            slug=f"infobox-{n}",
            ordinal=0,
            heading="",
            chunk_type="infobox",
            content=content,
            codes=[],
            gold_level=gold_level,
            speculative=conjecture_page,
        )

    def _quote_chunk(
        self, q: dict, n: int, gold_level: int | None, conjecture_page: bool
    ) -> dict:
        content = q["text"]
        if q["attribution"]:
            content += f"\n— {q['attribution']}"
        return self._chunk(
            slug=f"quote-{n}",
            ordinal=0,
            heading=q["section"],
            chunk_type="quote",
            content=content,
            codes=q["codes"],
            gold_level=gold_level,
            speculative=conjecture_page or self._is_speculative(q["section"]),
        )

    def _chunk(
        self,
        *,
        slug: str,
        ordinal: int,
        heading: str,
        chunk_type: str,
        content: str,
        codes: list[str],
        gold_level: int | None,
        speculative: bool,
    ) -> dict:
        header = self.title if not heading else f"{self.title} § {heading}"
        text = f"{header}\n\n{content}"

        codes = list(dict.fromkeys(codes))  # dedupe, keep first-seen order
        recognized = [CODE_LEVELS[c] for c in codes if c in CODE_LEVELS]
        if gold_level is not None:
            book_level, provenance = gold_level, "gold"
        elif recognized:
            book_level, provenance = max(recognized), "citation"
        else:
            book_level, provenance = None, None

        return {
            "chunk_id": f"{self.page_id}:{slug}:{ordinal}",
            "page_id": self.page_id,
            "page_title": self.title,
            "page_url": WIKI_BASE_URL + urlquote(self.title.replace(" ", "_")),
            "ns": self.ns,
            "revid": self.record["revid"],
            "section_heading": heading,
            "chunk_type": chunk_type,
            "text": text,
            "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "book_level": book_level,
            "label_provenance": provenance,
            "citation_codes": codes,
            "is_speculation": speculative,
            "quality_flags": self.quality_flags,
            "categories": self.categories,
            "word_count": len(text.split()),
        }


def chunk_page(record: dict) -> tuple[list[dict], PageStats]:
    stats = PageStats()
    chunks = PageChunker(record, stats).run()
    return chunks, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Chunk cached wiki pages into labeled chunks.")
    parser.add_argument("--input", type=Path, default=Path("data/pages.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data"), metavar="DIR")
    parser.add_argument(
        "--limit", type=int, default=None, metavar="N",
        help="chunk only the first N pages (smoke runs; checks skipped)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not args.input.exists():
        sys.exit(f"error: {args.input} not found — run `uv run python -m ingest.fetch_pages` first")

    t0 = time.monotonic()
    records = []
    with args.input.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    if args.limit is not None:
        records = records[: args.limit]

    all_chunks: list[dict] = []
    dropped: list[str] = []
    surprises: list[str] = []
    empty_sections = 0
    split_sections = 0
    oversize_paragraphs = 0
    for record in records:
        chunks, stats = chunk_page(record)
        all_chunks.extend(chunks)
        surprises.extend(stats.surprises)
        empty_sections += stats.empty_sections
        split_sections += stats.split_sections
        oversize_paragraphs += stats.oversize_paragraphs
        if stats.dropped:
            dropped.append(record["title"])

    from ingest.checks import label_coverage, word_histogram

    coverage = label_coverage(all_chunks)
    chunks_path = args.output / "chunks.jsonl"
    _write_atomic(
        chunks_path,
        "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in all_chunks),
    )
    manifest = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "input": str(args.input),
        "limit": args.limit,
        "tool_version": TOOL_VERSION,
        "duration_s": round(time.monotonic() - t0, 1),
        "pages_in": len(records),
        "pages_dropped": dropped,
        "chunks_total": len(all_chunks),
        "chunks_by_type": dict(Counter(c["chunk_type"] for c in all_chunks)),
        "empty_sections": empty_sections,
        "split_sections": split_sections,
        "oversize_paragraphs_kept_unsplit": oversize_paragraphs,
        "label_coverage": coverage,
        "word_count_histogram": word_histogram(all_chunks),
        "surprises": surprises,
    }
    _write_atomic(args.output / "chunks_manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    log.info(
        "wrote %d chunks from %d pages to %s (%d dropped, %d surprises, %.1fs)",
        len(all_chunks), len(records), chunks_path, len(dropped),
        len(surprises), time.monotonic() - t0,
    )

    if args.limit is None:
        from ingest.checks import main as checks_main

        return checks_main([str(chunks_path)])
    log.info("partial run (--limit): skipping chunk checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# RAG-kingkiller-wiki — capstone for LLM Zoomcamp 2026

Portfolio project, peer-reviewed. Production-grade code, written to be
readable by a reviewer with no course context.

## Conventions
- Python 3.12, managed with uv. Add related deps in ONE `uv add` call.
  All versions pinned via uv.lock.
- Corpus: kingkiller.fandom.com only (CC BY-SA 3.0). NEVER fetch from
  kingkiller.wiki (incompatible license). Corpus data is never
  committed: `data/` is gitignored.
- Be a polite API citizen: descriptive User-Agent, ~0.5s between
  requests, batched requests, respect maxlag.
- Prefer root-cause fixes over workarounds. If reality contradicts the
  task spec (API shape, page counts), stop and report — don't improvise
  around it.
- Tests with pytest; network-dependent tests behind a marker, excluded
  by default.
- Read docs/dataset-notes.md before touching ingestion code.
- Read docs/decisions/index.md before revisiting a decision — it may
  already be settled (and why) across pipeline.md/labeling.md/evaluation.md.
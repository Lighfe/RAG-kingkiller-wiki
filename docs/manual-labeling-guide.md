# Manual labeling guide (adversarial sample)

You are labeling ~80 chunks blind: no heuristic labels, no strata shown.
Start with `uv run python -m ingest.label_manually`; resume anytime.

## The rule

Label the **highest book whose content the chunk reveals**:

- **1** — everything stated is established in *The Name of the Wind*.
- **2** — anything requires *The Wise Man's Fear*. Side stories count
  as 2 (*Slow Regard*, *The Lightning Tree*, *Narrow Road*, *Old Holly*
  — per the D11 mapping).
- **3** — anything reveals *The Doors of Stone* / unpublished material
  (prologue text, Rothfuss statements about book three's content).

Judge what the text **reveals, not what it mentions**. "She reappears
later" reveals nothing book-2 — it's a forward reference with no
content. "She reappears later and trains him in her homeland" reveals
book-2 content.

When torn between two levels, open the `page_url`, check context, then
choose the **higher** level. Use **u** only if genuinely undecidable
after that — "u" chunks are excluded from recall metrics and reported
separately, so an honest "u" beats a coin flip.

## Invented examples (not real wiki text)

- *"Deral is a innkeeper in Imre who rents Kvothe a room during his
  first term at the University."* → **1**: setting and events all
  established in book 1.
- *"After the trial, Deral travels east with the caravan and is among
  those killed by bandits on the Levinshir road."* → **2**: the events
  described happen in book 2, regardless of where the page lives.
- *"Deral is first mentioned in chapter 12; she appears again in The
  Wise Man's Fear."* → **1**: the book-2 APPEARANCE is mentioned, but
  nothing book-2 is revealed. Mention ≠ reveal — this is the trap the
  labeler exists to catch.

## Mechanics

Keys: `1` / `2` / `3` = level · `u` = unsure · `b` = back (redo
previous) · `q` = save and quit. Progress and elapsed time are shown;
output appends to `data/manual_labels.jsonl` (labels only, no text —
committed). Aim for flow, not deliberation: ~30–60 s per chunk; the
page_url is there for the genuinely tricky ones.

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

## Infobox and reference-section edge cases (D19, D20, D21, D26)

- *(Severen-shape, invented)* An infobox reads `location: Vintas`,
  `position: City`, `currency: Vintish, Cealdish`, `ruler: Maer
  Alveron; King Roderic Calanthis`. → **1** (assuming the page itself
  is otherwise book-1): the geography/government/currency fields are
  static background lore. `ruler` is a relational field, but naming
  who rules a city is civic structure, not a story disclosure — it
  doesn't reveal a plot event. Contrast with a field that pairs two
  entities *because of what happens between them* (e.g. a character's
  infobox listing a book-2-only ally gained through a book-2 event) —
  that pairing would escalate.
  **This holds specifically because Severen is Book-1-reachable** —
  it's on the TNOTW map and named in a book-1 letter before Kvothe
  ever travels there. The "static fields don't escalate" reasoning
  does not transfer to an entity a Book-1-only reader has never heard
  of (D21, next example).
- *(Adem-companion-shape, invented)* An infobox for "Tepa," a mercenary
  first introduced when Kvothe travels to Ademre, reads `species:
  human`, `occupation: mercenary`, `residence: Ademre`, `affiliation:
  Kvothe's traveling company` — fields exactly as mundane and static
  as Severen's. → **2**, still: nothing here is a plot disclosure, but
  Tepa's entire *existence* is a Book-2 fact. A Book-1-only reader has
  no way to encounter this page at all without learning that Kvothe's
  story includes an Adem mercenary company — that's the disclosure,
  not any individual field (D21). The static/relational split from
  D18/D19 only ever applied to entities already knowable from Book 1;
  for a Book-2-introduced entity, Book-2 is a floor under every one of
  its chunks, infobox included.
- *(Tepa-trivia-shape, invented, D26)* A `Trivia` section on the same
  "Tepa" page (D26 next example): *"The name Tepa may derive from an
  old Cormerant word meaning 'quick.'"* → **2**, still — same floor as
  above, and it doesn't matter that this chunk isn't even an infobox.
  It's pure real-world etymology with zero in-story content, the kind
  of chunk that's easy to wave through as "obviously book-1-safe." But
  a Book-1-only reader can't reach this page at all without already
  knowing Tepa exists, and that's a Book-2 fact regardless of the
  chunk's content genre (D21/D26: the floor is chunk-type-agnostic —
  it's not just an infobox thing).
- *(Four-plate-door-shape, invented)* A page's `References` section
  (no `{{ref}}` template, no citation) is just the plain-text lines
  *"The Name of the Wind"* / *"The Wise Man's Fear"*. → **1**: these
  are bare title mentions with no attached claim — nothing is
  revealed, so nothing escalates (D19). Also applies to interwiki-link
  debris in the same shape (e.g. `es:Imre`) — not a book reference at
  all, and never a label signal.

## Mechanics

Keys: `1` / `2` / `3` = level · `u` = unsure · `b` = back (redo
previous) · `q` = save and quit. Progress and elapsed time are shown;
output appends to `data/manual_labels.jsonl` (labels only, no text —
committed). Aim for flow, not deliberation: ~30–60 s per chunk; the
page_url is there for the genuinely tricky ones.

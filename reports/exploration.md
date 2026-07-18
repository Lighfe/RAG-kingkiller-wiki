# Corpus exploration report

Generated 2026-07-18T16:50:09Z from `data/pages.jsonl` (464 pages: {'0': 438, '112': 26}). Parser: mwparserfromhell 0.7.2.

> Excerpts below are from the [Kingkiller Chronicle Fandom wiki](https://kingkiller.fandom.com), CC BY-SA 3.0.

## 1. Template inventory

46 distinct templates, 1944 total occurrences.

| template | pages | occurrences | class |
|---|--:|--:|---|
| `{{ref}}` | 225 | 843 |  |
| `{{quote}}` | 176 | 198 | quote |
| `{{reflist}}` | 195 | 195 |  |
| `{{needhelp}}` | 140 | 140 |  |
| `{{character infobox}}` | 92 | 92 | infobox |
| `{{pron}}` | 66 | 81 |  |
| `{{stub}}` | 62 | 62 |  |
| `{{university navbox}}` | 50 | 50 |  |
| `{{Location infobox}}` | 40 | 40 | infobox |
| `{{Character}}` | 32 | 32 |  |
| `{{Orphan}}` | 26 | 26 |  |
| `{{Chapter infobox}}` | 25 | 25 | infobox |
| `{{series navbox}}` | 17 | 17 |  |
| `{{chapters navbox}}` | 14 | 14 |  |
| `{{object infobox}}` | 13 | 13 | infobox |
| `{{group infobox}}` | 12 | 12 | infobox |
| `{{book infobox}}` | 11 | 12 | infobox |
| `{{main}}` | 5 | 11 |  |
| `{{temerant navbox}}` | 7 | 7 |  |
| `{{disambig}}` | 6 | 6 |  |
| `{{conjecture}}` | 6 | 6 |  |
| `{{product infobox}}` | 5 | 5 | infobox |
| `{{song infobox}}` | 5 | 5 | infobox |
| `{{species infobox}}` | 5 | 5 | infobox |
| `{{clr}}` | 3 | 5 |  |
| `{{for}}` | 5 | 5 |  |
| `{{Underlinked}}` | 4 | 4 |  |
| `{{map}}` | 4 | 4 |  |
| `{{Person infobox}}` | 4 | 4 | infobox |
| `{{cite}}` | 3 | 4 |  |

(long tail of 16 more templates in the stats JSON)

**Infobox templates:** `{{character infobox}}`, `{{Location infobox}}`, `{{Chapter infobox}}`, `{{object infobox}}`, `{{group infobox}}`, `{{book infobox}}`, `{{product infobox}}`, `{{song infobox}}`, `{{species infobox}}`, `{{Person infobox}}`, `{{Game infobox}}`, `{{Play infobox}}`.
**Quote templates:** `{{quote}}`, `{{Mainpage/Quote}}`.

**`{{ref}}` first-parameter values** (the book-code signal): `TNOTW`×430, `TWMF`×406, `TLT`×6, `TSROST`×1.

### strip_code() behavior — top templates and all infobox/quote templates

#### `{{ref}}` — example from “A Quainte Compendium of Folke Belief”

Raw wikitext:
```wikitext
{{ref|TWMF|16|Author of ''A Quainte Compendium of Folke Belief''|Of the Chaendrian there is little to be said. Every Man knows of them. Every child chants their song. Yet folke tell no stories.<br>For the price of a small beer a Farmer will talk two hours on Dannerlings. But mention the Chaendrian and his mouth goes tight as a Spinner’s Asse and he is touching iron and pushing back his chair.<br>Many think it bad luck to speak of the Fae, yet still folke do. What makes the Chaendrian different I knowe notte. One rather drunk Tanner in the towne of Hillesborrow said in hushed tones, “If you tal …[truncated]
```
strip_code() leaves: **nothing**

#### `{{quote}}` — example from “Cealdish Currency”

Raw wikitext:
```wikitext
{{Quote|Ages ago, barter was the most common method of trade. Some larger cities coined their own currency, but outside those cities the money was only worth the weight of the metal. Bars of metal were better for bartering, but inconvenient to carry.... [[Ceald|The Cealdim]] were the first to establish a standardized currency that was widely accepted. By cutting a bar of metal into pieces, you would get copper [[jot]]s. It was a great improvement on the previous system, and is still the most widely accepted currency in [[The Four Corners of Civilization|The Four Corners]] today.|Tillen Andra: …[truncated]
```
strip_code() leaves: **nothing**

#### `{{reflist}}` — example from “Adaptations of The Kingkiller Chronicle”

Raw wikitext:
```wikitext
{{reflist|2}}
```
strip_code() leaves: **nothing**

#### `{{needhelp}}` — example from “Ademic”

Raw wikitext:
```wikitext
{{needhelp}}
```
strip_code() leaves: **nothing**

#### `{{character infobox}}` — example from “Ambrose Jakis”

Raw wikitext:
```wikitext
{{character infobox
|image = Playing Cards poster Ambrose.jpg
|fullname = Ambrose Jakis
|species = Human
|family = [[Baron Jakis]] (father)
Unnamed sister

Deceased unnamed mother
|gender = Male
|ethnicity = [[Vintas|Vintish]]
|occupation = *University student
*Scriv
*Musician
|field = 
|rank = [[Re'lar]]
|instrument = Lyre|skin=Pale|hair=Brown|eye=Dark|residence=The Golden Pony}}
```
strip_code() leaves: **nothing**

#### `{{pron}}` — example from “Temic”

Raw wikitext:
```wikitext
{{pron|PR|/vɔɹ'feɪlən ɹɪn'ɑtə 'mɔreɪ/}}
```
strip_code() leaves: **nothing**

#### `{{stub}}` — example from “Advanced Mathematics”

Raw wikitext:
```wikitext
{{stub}}
```
strip_code() leaves: **nothing**

#### `{{university navbox}}` — example from “Advanced Mathematics”

Raw wikitext:
```wikitext
{{university navbox}}
```
strip_code() leaves: **nothing**

#### `{{Location infobox}}` — example from “Vintas”

Raw wikitext:
```wikitext
{{location infobox 
|name = Vintas
|location = Eastern part of [[the Four Corners of Civilization]]
|position = Sovereign state
|government = Monarchy
|ruler = King [[Roderic Calanthis]] and Queen Rinne Calanthis
|currency = [[Currency of Vintas|Vintish currency]], [[Currency of Ceald|Cealdish currency]]
|map = {{map|vin}}
}}
```
strip_code() leaves: **nothing**

#### `{{Character}}` — example from “Kvothe”

Raw wikitext:
```wikitext
{{Character
|image = The kingkiller chronicle kvothe by shilesque-d8m6yzz.jpg
|fullname = Kvothe, Son of Arliden
|alias = Kote<br>Reshi<br>Maedre<br>Red<br>Dulator<br>Shadicar<br>Lightfinger<br>Six-String<br>Kvothe the Bloodless<br>Kvothe the Arcane<br>Kvothe Kingkiller
|family = *[[Arliden]] (father) †
*[[Laurian]] (mother) †
|fate = Alive
|gender = Male
|skin = Pale
|age = Around 15-16 (In the past)
Mid 20s (In the present)
|hair = Red
|eye = Green
|ethnicity = [[Edema Ruh]]
|occupation = *University student (former)
*Musician (former)
*Innkeeper
|field = Artificing, Medica, Naming, Sympathy …[truncated]
```
strip_code() leaves: **nothing**

#### `{{Chapter infobox}}` — example from “Chapter:A Place for Demons”

Raw wikitext:
```wikitext
{{chapter infobox
|book = TNOTW
|chapter = 2
|arc = Frame story
|location = [[Waystone Inn]]
|previous = [[Chapter:A Silence of Three Parts (prologue of The Name of the Wind)|A Silence of Three Parts]]
|next = [[Chapter:A Beautiful Day|A Beautiful Day]]
}}
```
strip_code() leaves: **nothing**

#### `{{object infobox}}` — example from “Shaed”

Raw wikitext:
```wikitext
{{object infobox
|image = 43a3cde4cefcdc363a4e725db9c7d9e0-d48rk7w.jpg
|alias = The Shadow Cloak
|type = Cloak
|creator = [[Felurian]]
|made = During Kvothe's stay in the Faen realm
|usage = *Protects the wearer from harm
*Provides camouflage in the dark
|owner = [[Kvothe]]}}
```
strip_code() leaves: **nothing**

#### `{{group infobox}}` — example from “The Amyr”

Raw wikitext:
```wikitext
{{group infobox
|alias = The Holy Order of Amyr
Ciridae
|image = <gallery>
Playing Cards deck seal.jpg|Play-Seal
Pairs Commonwealth Amyr.jpg|Pairs-C
Amyr ciridae.jpg|Fanart
</gallery>
|founder = [[Tehlinism|Tehlin Church]]<br>[[Selitos]] (myth version)
|member = *Sir Savien Traliard
*Atreyon
|purpose = *Protection of [[the Aturan Empire]]
*Guarding the Faith
*Destruction of [[the Chandrian]] (myth version)
*Avenging the destruction of [[Myr Tariniel]] (myth version)
|status = Disbanded
|name=|patron=|leader=}}
```
strip_code() leaves: **nothing**

#### `{{book infobox}}` — example from “The Adventures of the Princess and Mr. Whiffle”

Raw wikitext:
```wikitext
{{Book_infobox|image = Dark of deep below cover.jpg|name = The Adventures of the Princess and Mr. Whiffle: The Dark of Deep Below|author = Patrick Rothfuss (writer), Nate Taylor (illustrator)|country = United States|language = English|publisher = Subterranean Press|date = November 1st, 2013|type = Print (hardcover)|isbn = 978-1596066205|pages = 232|previous = The Adventures of the Princess and Mr. Whiffle: The Thing Beneath the Bed|next = None}}
```
strip_code() leaves: **nothing**

#### `{{product infobox}}` — example from “Pairs”

Raw wikitext:
```wikitext
{{product infobox
|image = Pairs photo.jpg
|product = Card game
|designer = [[Wikipedia:James Ernest|James Ernest]], Paul Peterson
|illustrator = Brett Bean, Echo Chernik, Phil Foglio, Kaja Foglio, John Kovalic, [[Nate Taylor]], Shane Tyree, Pete Venters, Cheyenne Wright
|country = United States
|producer = [[Wikipedia:Cheapass Games|Cheapass Games]]
|date = October 20, 2014}}
```
strip_code() leaves: **nothing**

#### `{{song infobox}}` — example from “Chandrian (children's song)”

Raw wikitext:
```wikitext
{{Song infobox
|name = Chandrian
|alias = Chandrian, Chandrian
|creator = Unknown
|performer = Children
|genre = Children's song}}
```
strip_code() leaves: **nothing**

#### `{{species infobox}}` — example from “Draccus”

Raw wikitext:
```wikitext
{{species infobox
|image = Playing Cards poster Draccus.png
|alias = Dragon
|sentience = Sentient
|mortality = Mortal
|status = Mostly extinct
|skin = Black scales}}
```
strip_code() leaves: **nothing**

#### `{{Person infobox}}` — example from “Patrick Rothfuss”

Raw wikitext:
```wikitext
{{person infobox
|image = Patrick-rothfuss-0.jpg
|fullname = Patrick James Rothfuss
|alias = Pat
|birthday = June 6, 1973
|family = 
|gender = Male
|nationality = American
|occupation = *College lecturer (former)
*Fiction author
|website = [http://www.patrickrothfuss.com/ patrickrothfuss.com]}}
```
strip_code() leaves: **nothing**

#### `{{Game infobox}}` — example from “Chandrian (children's game)”

Raw wikitext:
```wikitext
{{Game infobox
|name = Chandrian
|genre = Children's game
|creator = Unknown
|players = Children
}}
```
strip_code() leaves: **nothing**

#### `{{Play infobox}}` — example from “Daeonica”

Raw wikitext:
```wikitext
{{Play infobox
|creator = Unknown
|performers = [[Lord Greyfallow's Men]]
|genre = Tragedy or Epic}}
```
strip_code() leaves: **nothing**

#### `{{Mainpage/Quote}}` — example from “Kingkiller Wiki”

Raw wikitext:
```wikitext
{{Mainpage/Quote}}
```
strip_code() leaves: **nothing**

## 2. Section structure

### Heading inventory (level 2–3, case-insensitive groups)

| heading | levels | occurrences | pages | speculative? |
|---|---|--:|--:|---|
| References | h2×206 | 206 | 206 |  |
| Description | h2×166, h3×1 | 167 | 167 |  |
| In The Chronicle | h2×148 | 148 | 148 |  |
| Speculation | h2×70, h3×3 | 73 | 72 | **yes** |
| Trivia | h2×30, h3×1 | 31 | 31 | **yes** |
| Chapter summary | h2×26 | 26 | 26 |  |
| TITLE | h2×19 | 19 | 19 |  |
| CHARACTERS LIST | h2×16 | 16 | 16 |  |
| Fanarts | h2×10 | 10 | 10 | **yes** |
| Background and publication | h2×9 | 9 | 9 |  |
| Current Master | h2×9 | 9 | 9 |  |
| Speculations | h2×8 | 8 | 8 | **yes** |
| Plot summary | h2×8 | 8 | 8 |  |
| Synopsis | h2×6, h3×1 | 7 | 7 |  |
| The first silence | h3×6 | 6 | 6 |  |
| The second silence | h3×6 | 6 | 6 |  |
| The third silence | h3×6 | 6 | 6 |  |
| Known terms | h2×6 | 6 | 6 |  |
| The Lightning Tree | h2×6 | 6 | 6 |  |
| Reception | h2×6 | 6 | 6 |  |
| Fan arts | h2×5 | 5 | 5 | **yes** |
| Editions | h2×5 | 5 | 5 |  |
| Appearance | h2×3, h3×1 | 4 | 4 |  |
| In the Chronicles | h2×4 | 4 | 4 |  |
| External links | h2×4 | 4 | 4 |  |
| Geography | h2×2, h3×1 | 3 | 3 |  |
| Culture | h2×2, h3×1 | 3 | 3 |  |
| Fan art | h2×3 | 3 | 3 | **yes** |
| Etymology | h2×3 | 3 | 3 |  |
| History | h2×3 | 3 | 3 |  |
| Relationships | h3×3 | 3 | 3 |  |
| Biography | h2×3 | 3 | 3 |  |
| Career | h2×3 | 3 | 3 |  |
| References List | h2×3 | 3 | 3 |  |
| In the Story | h2×3 | 3 | 3 |  |
| Character list | h2×3 | 3 | 3 |  |
| Owners and Affiliates | h2×2 | 2 | 2 |  |
| Drinks | h2×2 | 2 | 2 |  |
| Origin | h2×1, h3×1 | 2 | 2 |  |
| 500 years before | h2×2 | 2 | 2 |  |
| In the Plot | h2×2 | 2 | 2 |  |
| Works | h2×2 | 2 | 2 |  |
| Real World References and Parallels | h2×2 | 2 | 2 |  |
| Rules | h2×2 | 2 | 2 |  |
| See also | h2×2 | 2 | 2 |  |
| Real-World References and Parallels | h2×2 | 2 | 2 |  |
| Personal Life | h2×2 | 2 | 2 |  |
| Other media | h2×1, h3×1 | 2 | 2 |  |
| Stories | h2×2 | 2 | 2 |  |
| Awards and honors | h2×2 | 2 | 2 |  |
| Card images | h2×2 | 2 | 2 |  |
| Writing and structure | h2×2 | 2 | 2 |  |
| Chapters | h2×1 | 1 | 1 |  |
| Inspiration | h2×1 | 1 | 1 |  |
| Twentieth Century Fox | h2×1 | 1 | 1 |  |
| Production | h3×1 | 1 | 1 |  |
| Lionsgate | h2×1 | 1 | 1 |  |
| Known gestures | h2×1 | 1 | 1 |  |
| Origins | h2×1 | 1 | 1 |  |
| Cultural Exports | h2×1 | 1 | 1 |  |
| Elitism | h3×1 | 1 | 1 |  |
| Communication | h3×1 | 1 | 1 |  |
| Music | h3×1 | 1 | 1 |  |
| Sexual beliefs and behavior | h3×1 | 1 | 1 |  |
| Matriarchy | h3×1 | 1 | 1 |  |
| Notable figures | h2×1 | 1 | 1 |  |
| Training in Alar | h3×1 | 1 | 1 |  |
| Known Alchemical Products | h2×1 | 1 | 1 |  |
| Named Angels | h2×1 | 1 | 1 |  |
| Basic Principles | h2×1 | 1 | 1 |  |
| Known Schema | h2×1 | 1 | 1 |  |
| Significance | h2×1 | 1 | 1 |  |
| Meta-knowledge | h2×1 | 1 | 1 |  |
| Gifts | h2×1 | 1 | 1 |  |
| Operation | h2×1 | 1 | 1 |  |
| The Slow Regard of Silent Things | h2×1 | 1 | 1 |  |
| Quotations | h2×1 | 1 | 1 |  |
| Year and months | h2×1 | 1 | 1 |  |
| Days and spans | h2×1 | 1 | 1 |  |
| Copper Jot | h3×1 | 1 | 1 |  |
| Iron Drab | h3×1 | 1 | 1 |  |
| Silver Talent | h3×1 | 1 | 1 |  |
| Gold Mark | h3×1 | 1 | 1 |  |
| Sets | h2×1 | 1 | 1 |  |
| Background and production | h2×1 | 1 | 1 |  |
| Known Chancellors | h2×1 | 1 | 1 |  |
| Versions | h2×1 | 1 | 1 |  |
| In the Books | h2×1 | 1 | 1 |  |
| Known Players | h2×1 | 1 | 1 |  |
| Currency of Ceald | h2×1 | 1 | 1 |  |
| Currency of Commonwealth | h2×1 | 1 | 1 |  |
| Currency of Vintas | h2×1 | 1 | 1 |  |
| Resource | h2×1 | 1 | 1 |  |
| Creation War | h3×1 | 1 | 1 |  |
| Taborlin stories | h3×1 | 1 | 1 |  |
| The Kingkiller Chronicle | h2×1 | 1 | 1 |  |
| Structure | h2×1 | 1 | 1 |  |
| Meeting Kvothe | h3×1 | 1 | 1 |  |
| The Eolian | h3×1 | 1 | 1 |  |
| Trebon massacre | h3×1 | 1 | 1 |  |
| The Ring and Relationship with Ambrose | h3×1 | 1 | 1 |  |
| Severen fall-out | h3×1 | 1 | 1 |  |
| Personality | h2×1 | 1 | 1 |  |
| Quotes about Denna | h2×1 | 1 | 1 |  |
| Fun Fact | h2×1 | 1 | 1 |  |
| Translation process | h2×1 | 1 | 1 |  |
| Issues in translation | h2×1 | 1 | 1 |  |
| Culture and language | h3×1 | 1 | 1 |  |
| Rhymes and acronyms | h3×1 | 1 | 1 |  |
| Invented words and names | h3×1 | 1 | 1 |  |
| Implication in texts | h3×1 | 1 | 1 |  |
| List of editions by country | h2×1 | 1 | 1 |  |
| Isolation | h3×1 | 1 | 1 |  |
| Role In Narrative | h3×1 | 1 | 1 |  |
| Notes and references | h2×1 | 1 | 1 |  |
| Summary | h3×1 | 1 | 1 |  |
| List Of Appearances | h3×1 | 1 | 1 |  |
| Ancient Mael language | h3×1 | 1 | 1 |  |
| Glammourie | h2×1 | 1 | 1 |  |
| Grammarie | h2×1 | 1 | 1 |  |
| Combined Uses | h2×1 | 1 | 1 |  |
| Fanart | h2×1 | 1 | 1 | **yes** |
| Appearances in the books | h2×1 | 1 | 1 |  |
| Notable Persons | h3×1 | 1 | 1 |  |
| Jax's Story | h3×1 | 1 | 1 |  |
| Period of the Ergen Empire | h2×1 | 1 | 1 |  |
| Period of the Aturan Empire | h2×1 | 1 | 1 |  |
| Recent history | h2×1 | 1 | 1 |  |
| Loeclos Box | h3×1 | 1 | 1 |  |
| Lackless poem | h3×1 | 1 | 1 |  |
| Jax | h2×1 | 1 | 1 |  |
| Notable Locations | h3×1 | 1 | 1 |  |
| Prominent Residents | h3×1 | 1 | 1 |  |
| Notable Characteristics | h2×1 | 1 | 1 |  |
| Broad Jurisdiction | h3×1 | 1 | 1 |  |
| Close Connections to Tehlin Church | h3×1 | 1 | 1 |  |
| Antagonism Towards Practice of Magic | h3×1 | 1 | 1 |  |
| Archaic Methodology | h3×1 | 1 | 1 |  |
| Split Enforcement | h3×1 | 1 | 1 |  |
| Historical Significance | h2×1 | 1 | 1 |  |
| Discipline | h2×1 | 1 | 1 |  |
| Ketan movements | h2×1 | 1 | 1 |  |
| Early life | h3×1 | 1 | 1 |  |
| Tarbean | h3×1 | 1 | 1 |  |
| The University | h3×1 | 1 | 1 |  |
| Vintas | h3×1 | 1 | 1 |  |
| The Faen Realm | h3×1 | 1 | 1 |  |
| Ademre | h3×1 | 1 | 1 |  |
| Return to the University | h3×1 | 1 | 1 |  |
| The present | h3×1 | 1 | 1 |  |
| Other Names | h2×1 | 1 | 1 |  |
| Kote | h3×1 | 1 | 1 |  |
| Reshi | h3×1 | 1 | 1 |  |
| Maedre | h3×1 | 1 | 1 |  |
| Dulator | h3×1 | 1 | 1 |  |
| Shadicar | h3×1 | 1 | 1 |  |
| Lightfinger | h3×1 | 1 | 1 |  |
| Six-String | h3×1 | 1 | 1 |  |
| Kvothe the Bloodless | h3×1 | 1 | 1 |  |
| Kvothe the Arcane | h3×1 | 1 | 1 |  |
| Kvothe Kingkiller | h3×1 | 1 | 1 |  |
| Naming | h3×1 | 1 | 1 |  |
| Identity | h3×1 | 1 | 1 |  |
| Rings | h3×1 | 1 | 1 |  |
| Kvothe and Kote | h3×1 | 1 | 1 |  |
| Significance to Kvothe | h2×1 | 1 | 1 |  |
| List of languages | h2×1 | 1 | 1 |  |
| Unknown terms | h2×1 | 1 | 1 |  |
| The Tale of the Nine and Ninety Tales | h2×1 | 1 | 1 |  |
| The Way of the Lethani | h2×1 | 1 | 1 |  |
| Entry into The Kingkiller Chronicle | h2×1 | 1 | 1 |  |
| Film and TV Show | h2×1 | 1 | 1 |  |
| Contents | h3×1 | 1 | 1 |  |
| Members | h3×1 | 1 | 1 |  |
| From the Author | h2×1 | 1 | 1 |  |
| Arcanist's Arts | h2×1 | 1 | 1 |  |
| Fae magic | h2×1 | 1 | 1 |  |
| Crossover-the Nature of Naming | h2×1 | 1 | 1 |  |
| Rothfuss interview with Jo Walton | h2×1 | 1 | 1 |  |
| Medicine within the Chronicle | h2×1 | 1 | 1 |  |
| Medical Basis | h3×1 | 1 | 1 |  |
| Known Medicine | h3×1 | 1 | 1 |  |
| Gaps in Knowledge | h3×1 | 1 | 1 |  |
| Areas | h2×1 | 1 | 1 |  |
| Items | h3×1 | 1 | 1 |  |
| Instruments | h2×1 | 1 | 1 |  |
| Songs | h2×1 | 1 | 1 |  |
| Notable musicians | h2×1 | 1 | 1 |  |
| Known Namers | h2×1 | 1 | 1 |  |
| Denizens | h2×1 | 1 | 1 |  |
| Quotes | h2×1 | 1 | 1 |  |
| Decks | h2×1 | 1 | 1 |  |
| Commonwealth deck | h3×1 | 1 | 1 |  |
| Modegan deck | h3×1 | 1 | 1 |  |
| Faen deck | h3×1 | 1 | 1 |  |
| Temerant books | h3×1 | 1 | 1 |  |
| Other books | h3×1 | 1 | 1 |  |
| Spoilers about Book Three | h2×1 | 1 | 1 | **yes** |
| Family | h2×1 | 1 | 1 |  |
| Background | h2×1 | 1 | 1 |  |
| Book Three | h2×1 | 1 | 1 | **yes** |
| Archival scrivs | h3×1 | 1 | 1 |  |
| Procurement Scrivs | h3×1 | 1 | 1 |  |
| Known Scrivs | h2×1 | 1 | 1 |  |
| The Name of the Wind | h3×1 | 1 | 1 |  |
| Possible Seven Word Combinations | h2×1 | 1 | 1 | **yes** |
| Transportation | h2×1 | 1 | 1 |  |
| Making of the Shaed | h2×1 | 1 | 1 |  |
| Properties of the Shaed | h2×1 | 1 | 1 |  |
| Vocabulary | h2×1 | 1 | 1 |  |
| Words | h3×1 | 1 | 1 |  |
| Phrases | h3×1 | 1 | 1 |  |
| Imperfect Aturan by Siaru speakers | h3×1 | 1 | 1 |  |
| Grammar* | h2×1 | 1 | 1 |  |
| Word order | h3×1 | 1 | 1 |  |
| Zero prepositions | h3×1 | 1 | 1 |  |
| Lists | h3×1 | 1 | 1 |  |
| List of songs | h2×1 | 1 | 1 |  |
| Laws, Terms, and Maxims of Sympathy | h2×1 | 1 | 1 |  |
| Known Bindings | h2×1 | 1 | 1 |  |
| Setup | h3×1 | 1 | 1 |  |
| Alternate rules | h3×1 | 1 | 1 |  |
| Competitive Play | h3×1 | 1 | 1 |  |
| Tak Media Content | h3×1 | 1 | 1 |  |
| Background Information | h2×1 | 1 | 1 |  |
| Images of Talent Pipes | h2×1 | 1 | 1 |  |
| Known Establishments in Tarbean | h3×1 | 1 | 1 |  |
| His works | h2×1 | 1 | 1 |  |
| Beliefs | h2×1 | 1 | 1 |  |
| Practices | h2×1 | 1 | 1 |  |
| Species | h2×1 | 1 | 1 |  |
| Magic | h2×1 | 1 | 1 |  |
| Plot Summary of The Thing Beneath the Bed | h2×1 | 1 | 1 |  |
| Plot Summary of The Dark of Deep Below | h2×1 | 1 | 1 |  |
| Importance to the Chronicle | h2×1 | 1 | 1 |  |
| Human Amyr | h3×1 | 1 | 1 |  |
| Myth Amyr | h3×1 | 1 | 1 |  |
| Ranks | h2×1 | 1 | 1 |  |
| Signs and Symbols | h2×1 | 1 | 1 |  |
| Motivation | h3×1 | 1 | 1 |  |
| Characters Known to Have Spoken with The Cthaeh | h2×1 | 1 | 1 |  |
| Spoilers for The Doors of Stone | h2×1 | 1 | 1 | **yes** |
| Inhabitants | h2×1 | 1 | 1 |  |
| The Folding House | h2×1 | 1 | 1 |  |
| Plot description | h2×1 | 1 | 1 |  |
| Works in the series | h2×1 | 1 | 1 |  |
| Main trilogy | h3×1 | 1 | 1 |  |
| Companion tales | h3×1 | 1 | 1 |  |
| Editions and translations | h3×1 | 1 | 1 |  |
| Derived works | h2×1 | 1 | 1 |  |
| TV series, Movie and Video Game | h3×1 | 1 | 1 |  |
| Lyrics and form | h2×1 | 1 | 1 |  |
| Notes | h2×1 | 1 | 1 |  |
| Skarpi's Story | h2×1 | 1 | 1 |  |
| Terms, Admissions, and Tuition | h3×1 | 1 | 1 |  |
| Masters | h3×1 | 1 | 1 |  |
| In Hespe's story | h2×1 | 1 | 1 |  |
| Background and General Information | h2×1 | 1 | 1 |  |
| Patrick Rothfuss | h2×1 | 1 | 1 |  |
| Wards | h2×1 | 1 | 1 |  |
| Growing | h2×1 | 1 | 1 |  |
| Sex | h2×1 | 1 | 1 |  |
| Act | h2×1 | 1 | 1 |  |
| Reproduction | h2×1 | 1 | 1 |  |
| Place in the Story | h2×1 | 1 | 1 |  |
| Abilities | h2×1 | 1 | 1 |  |
| Involvement | h2×1 | 1 | 1 |  |
| Social Rings | h2×1 | 1 | 1 |  |
| Nobility | h2×1 | 1 | 1 |  |
| Line of Succession | h3×1 | 1 | 1 |  |
| Regulars | h2×1 | 1 | 1 |  |
| Beverages | h2×1 | 1 | 1 |  |
| Food | h2×1 | 1 | 1 |  |
| The loeclos Box | h3×1 | 1 | 1 |  |

**Speculative headings** (108 pages total): “Speculation” on 72 pages; “Trivia” on 31 pages; “Fanarts” on 10 pages; “Speculations” on 8 pages; “Fan arts” on 5 pages; “Fan art” on 3 pages; “Fanart” on 1 pages; “Spoilers about Book Three” on 1 pages; “Book Three” on 1 pages; “Possible Seven Word Combinations” on 1 pages; “Spoilers for The Doors of Stone” on 1 pages.

### Section length (words after strip_code, lede excluded)

| scope | n | p50 | p90 | p99 | max |
|---|--:|--:|--:|--:|--:|
| all | 1082 | 56 | 251 | 588 | 2320 |
| ns 0 | 1003 | 58 | 251 | 571 | 2320 |
| ns 112 | 79 | 30 | 259 | 852 | 852 |

Histogram (all sections):

| words | sections |
|---|--:|
| 0–50 | 512 |
| 50–100 | 199 |
| 100–230 | 241 |
| 230–380 | 103 |
| 380–500 | 12 |
| 500–1000 | 11 |
| 1000+ | 4 |

Sections over 500 words (need max-size splitting): **15**. Sections under 50 words (kept as-is per tiny-section policy): **512**.

### The lede (text before the first heading)

Words: p50 26, p90 118, p99 293, max 585 across 464 pages. **127 pages have no headings at all** (lede = whole page), e.g. “Advanced Mathematics”, “Alleg”, “Andan”, “Anisat”, “Anne”.

## 3. Refs and strip behavior

Of 364 `<ref>` tags with non-trivial content, 363 **survive strip_code()** — ref bodies (often bare URLs) are inlined into the stripped text. Note that most citations on this wiki use the `{{ref}}` template instead, which strip_code drops entirely (see section 1).

Example (from “Abbott's Ford”):
```wikitext
<ref name=":0">''The Name of the Wind'', Chapter 4: "Halfway to Newarre"</ref>
```
strip_code() leaves: `The Name of the Wind, Chapter 4: "Halfway to Newarre"`

Citations per section (`<ref>` tags + `{{ref}}` templates): p50 0, p90 2, max 68. **29.8% of sections have ≥1 citation** (461/1546; `<ref>` tags alone 12.4%, `{{ref}}` templates alone 21.2%).

| citations/section | sections |
|---|--:|
| 0–1 | 1085 |
| 1–2 | 240 |
| 2–3 | 89 |
| 3–6 | 88 |
| 6–11 | 29 |
| 11+ | 15 |

## 4. Garbage watch

`[[Category:…]]` links survive strip_code() as literal text on **455 pages**.

5 pages retain markup residue after strip_code(). Worst 10 by residue count:

- **Chandrian (children's song)** (ns 0, 10 artifacts)
  ```
  "ages old" and provides the names of the Chandrian and their signs. ⏎  ⏎  Versions  ⏎ {| width="100%" ⏎ | width="50%"|Children's version ⏎ When the hearthfire turns to blue, ⏎ What to do? What to do? ⏎ Run outside. Run a …[truncated]
  ```
- **Maple, Maypole** (ns 0, 5 artifacts)
  ```
  couplet of the rhyme is the chosen item. ⏎  ⏎ There are two versions of the rhyme: ⏎ {| width="55%" ⏎ |- ⏎ |Waystone version ⏎  ⏎ Maple. Maypole. ⏎ Catch and carry. ⏎ Ash and Ember. ⏎ Elderberry. ⏎  ⏎ Woolen. Woman. ⏎ Mo …[truncated]
  ```
- **Lackless poem** (ns 0, 4 artifacts)
  ```
  at least two versions of the rhyme known in the Four Corners of Civilization. ⏎  ⏎ {| width="100%" ⏎ | width="50%"|Girl's version ⏎ Seven things has Lady Lackless ⏎ Keeps them underneath her black dress ⏎ One a ring that …[truncated]
  ```
- **Tinker Tanner** (ns 0, 4 artifacts)
  ```
  w verse to Kvothe who was on his way back to Severen from the Pennysworth Inn. ⏎  ⏎ {| width="100%" ⏎ |Young boy's verse: ⏎ I once saw a fair farmer's daughter ⏎ On the riverbank far from all men ⏎ She was taking a bath …[truncated]
  ```
- **Viari** (ns 0, 2 artifacts)
  ```
  le-plays a character named Viari (whose appearance is based on Kvothe's) in the [[w:c:pennyarcade:List of D&D Podcasts|Penny Arcade'''s live Dungeons & Dragons games]] (also known as Acquisitions Inc.'') from season 7 on …[truncated]
  ```

Near-empty after stripping despite non-trivial wikitext (pure-infobox pages):

| page | ns | wikitext chars | stripped words |
|---|--:|--:|--:|
| Kingkiller Wiki | 0 | 525 | 16 |
| Evesdown | 0 | 310 | 19 |

## 5. Implications for chunking

Decisions to confirm (recommendations, not implementations):

- Infobox templates — {{character infobox}} (92 pages), {{Location infobox}} (40 pages), {{Chapter infobox}} (25 pages), {{object infobox}} (13 pages), {{group infobox}} (12 pages), {{book infobox}} (11 pages), {{product infobox}} (5 pages), {{song infobox}} (5 pages), {{species infobox}} (5 pages), {{Person infobox}} (4 pages), {{Game infobox}} (1 pages), {{Play infobox}} (1 pages) — strip to nothing with strip_code(), so their structured params (incl. `|book=` on chapter pages) are lost unless extracted BEFORE stripping. Decision to confirm: drop infoboxes from chunk text, harvest their params into chunk metadata in a pre-strip pass.
- {{quote}} (176 pages, 198 uses) is stripped ENTIRELY — quote text is silently lost. Decision to confirm: extract quote text + attribution from the template params pre-strip and inline them as regular prose.
- Only 15 of 1082 sections (1.4%) exceed 500 words → max-size splitting is a rare fallback, not the main mechanism; section-aware chunking fits this corpus.
- 512 sections (47.3%) are under 50 words → confirms the tiny-section policy (keep as-is) matters; consider prepending page title + heading to every chunk so tiny chunks stay self-describing.
- The lede (p50 26 words, p90 118) is a de-facto section, and 127 pages are lede-only → the chunker must treat pre-heading text as a first-class section.
- Speculative-content headings found: "Speculation" (72p), "Trivia" (31p), "Fanarts" (10p), "Speculations" (8p), "Fan arts" (5p), "Fan art" (3p), "Fanart" (1p), "Spoilers about Book Three" (1p), "Book Three" (1p), "Possible Seven Word Combinations" (1p), "Spoilers for The Doors of Stone" (1p) — 108 pages total. Decision to confirm: is_speculation flag on chunks from these sections (case-insensitive match).
- <ref> tag contents SURVIVE strip_code() (363/364 ref bodies remain, often as bare URLs inlined mid-sentence) → remove ref tags pre-strip, harvesting their book signals first.
- The dominant citation mechanism is the {{ref}} TEMPLATE, whose first param is a closed book-code vocabulary (TNOTW×430, TWMF×406, TLT×6, TSROST×1) — dropped by strip_code, so harvest it pre-strip. 29.8% of sections carry ≥1 citation (tag or template; tags alone 12.4%) → section-level ref-to-chunk association is feasible for that slice.
- [[Category:…]] links survive strip_code() as literal “Category:X” text on 455 pages → remove category links pre-strip and harvest them as chunk metadata (they are the planned retrieval-filter facets).
- 2 pages strip to <20 words despite non-trivial wikitext (pure-infobox pages) → apply a minimum stripped-length filter before chunking (consistent with the gold-seed skeleton filtering in the dataset notes).
- 5 pages leave markup residue after strip_code (tables, bare params, comments) → add a residue-cleanup regex pass after stripping; re-run this garbage watch to verify.

# Product resolution: replacing fuzzy matching

Status: proposal, 2026-09-17. Follows `docs/reviews/pipeline-foundations.md` (Important #1 and
misjudgements 1-3). Nothing here is scheduled; the increments at the end are sized for the
backlog once the operator picks them up.

## 1. Why fuzzy matching cannot be fixed in place

The receipt pipeline decides which product a line is by string similarity
(`services/matching_service.py`, RapidFuzz `WRatio`, threshold 80). Reproduced against the real
service with a catalog of Milk, Apple, Cream, Butter, Tomato:

| printed | model's generic name | fuzzy decision | score |
| --- | --- | --- | --- |
| OATLY KAURAJUOMA | Oat milk | Milk | 90 high |
| PIRKKA ANANAS | Pineapple | Apple | 90 high |
| VALIO SMETANA | Sour cream | Cream | 90 high |
| MAAPÄHKINÄVOI | Peanut butter | Butter | 90 high |
| KIRSIKKATOMAATTI | Cherry tomato | Tomato | 90 high |
| ATRIA JAUHELIHA | Minced beef (catalog: Ground beef) | none | 64 |

Both failure directions are structural, not a threshold problem:

- **Similarity conflates containment with identity.** Any scorer that rewards shared substrings
  or shared tokens scores "Sour cream" against "Cream" as near-identical. Token-set variants
  fail the same way (every token of the shorter name is in the longer one). Raising the
  threshold to 95 loses the OCR-noise tolerance the step exists for.
- **Similarity cannot see synonyms.** "Minced beef" and "Ground beef" are the same product and
  score 64. The only thing that bridges them today is the model being told the catalog names
  in the prompt, capped at 300 and growing with the catalog.
- **The learning loop amplifies the error.** A fuzzy pre-match is shown read-only on the review
  row; including the line writes a `manually_verified` alias, and that alias then wins outright
  for every future receipt from that chain. Matching mistakes become permanent memory.

Fuzzy similarity is the wrong tool for *deciding*. It is a fine tool for *shortlisting*, and for
interactive search where a person makes the final choice. The refactor keeps it in exactly
those two roles.

## 2. Principles

1. **Identity is a key, not a score.** A line resolves to a product only through an exact key:
   a learned alias for the printed name, or a known name (canonical or synonym) for the generic
   name. No path stores a product id because two strings looked alike.
2. **Semantic judgement belongs to the model, constrained to a shortlist.** When the keys miss,
   the model chooses from a small candidate list per line, or answers "new". The system verifies
   the answer is one of the candidates it offered. The model already answers "Pineapple ≠ Apple"
   correctly; the matcher was overriding it.
3. **Extraction and resolution are separate steps.** Extraction reads the receipt (printed
   name, generic name, category, quantity, Q-fields). Resolution maps lines to the catalog.
   Today they are tangled: the extraction prompt carries the catalog to get consistent names.
4. **Learning is explicit and attributable.** Every alias and synonym records where it came from
   (cook, model selection, exact key). Only the cook's own actions produce verified memory. The
   cook can always detach a proposed product on the review row.
5. **Duplicates are prevented at the schema and repairable by merge.** A normalised product name
   is unique; a merge operation exists for the duplicates that already exist and for the ones a
   cook will still create by hand.

## 3. Target design

### 3.1 Data model

```
product_master                (unchanged columns)
  + UNIQUE INDEX ON lower(canonical_name)      -- after a dedupe migration

product_name                   NEW: every name that means this product
  id, product_master_id FK (ondelete CASCADE), name (normalised: casefold, single spaces),
  source ('canonical' | 'cook' | 'model'), created_at
  UNIQUE (name)
  -- the canonical name is also a row, so a lookup is one query

store_product_alias            printed name per chain -> product (exists)
  + source ('cook' | 'model' | 'name')        -- how the mapping was first made
  + UNIQUE (store_chain, receipt_name)         -- today only an index
  manually_verified keeps its meaning: the cook chose or corrected this mapping

receipt.ocr_structured.lines[] each line gains
  line_id (uuid, stable across re-reads of the same printed line where possible; new otherwise)
  resolution: { product_id | null, source: 'alias' | 'name' | 'selected' | 'none',
                verified: bool, candidates: [{product_id, name}] }
```

`line_id` is the minimum needed so review edits, `non_food_indexes` and alias learning stop
depending on array position (foundations misjudgement 3). A `receipt_line` table is the better
home and can replace the blob later; the resolution service should not care which.

### 3.2 Resolution service

`services/product_resolution.py` replaces `MatchingService.match_line` in the pipeline.
`MatchingService.match_all`/`match_product` are dead code today and go with it.

```
resolve(lines, chain, catalog):
  for each line:
    if normalised(printed) in non_food_names          -> non_food, stop
    alias = aliases[(chain, normalised(printed))]
         or aliases[(any chain, normalised(printed))] -> product, source=alias, verified=alias.manually_verified
    name  = product_names[normalised(generic)]
         or product_names[normalised(printed)]        -> product, source=name, verified=True
    else                                              -> unresolved

  if unresolved and catalog not empty:
    for each unresolved line:
      candidates = retrieve(generic, printed, category, k=5)
    ask the model once (see 3.3) for the lines that have candidates
    for each answer: accept product_id only if it is in that line's candidates
                                                      -> product, source=selected, verified=False
  everything else                                     -> none (a new product, named by generic)
```

Rules the service enforces, not the caller:

- No product id is ever assigned from a similarity score.
- A `selected` result never becomes an alias or synonym by itself; only confirm does that
  (3.4), and it records the source.
- If the model is unavailable, unresolved lines stay `none`. The receipt still completes;
  nothing falls back to fuzzy.

### 3.3 Candidate retrieval and the selection call

Retrieval is the only place similarity survives, and it only builds shortlists:

- `pg_trgm` similarity over `product_name.name` against the generic name and the printed name
  (Postgres 15 ships the extension; one migration enables it and adds a GIN index).
- Same-category products are included when the line has a category, so "Oat milk" always sees
  every dairy product even when the trigram score is poor.
- k = 5 per line, deduplicated by product. An empty shortlist means no call for that line.

The selection call is one request per receipt, only for unresolved lines with candidates:

```
For each line, pick the catalog product that is the same thing, or null if none is.
Same thing means a home cook would put them on one shopping-list line. Different variety,
plant milk vs dairy milk, or a different cut are different products.
Lines: [{"id": line_id, "n": printed, "g": generic, "c": category,
         "candidates": [{"p": product_id, "name": ...}, ...]}]
Answer: {"r": [{"id": line_id, "p": product_id or null}]}
```

Strict JSON schema as in extraction; `p` validated against the offered set. Expected cost on
the homelab: a dozen unresolved lines with five candidates each is a few hundred tokens of
output and roughly 10-20 s on `c2.muse-glimmer`; measure on the 49-line fixture with an empty
catalog (no call), a warm catalog (few unresolved) and a cold one (all unresolved).

Retrieval is behind a small interface (`Retriever.candidates(line) -> list[Candidate]`) so an
embedding-based retriever (pgvector plus an embedding model on the gateway) can replace trigram
later without touching resolution or the prompt. Not needed for a household-sized catalog.

### 3.4 Learning at confirm

Confirm receives, per included line, the product the cook ended up with. It compares that to
the line's `resolution.product_id`:

| situation | alias (chain, printed) | product_name (generic) |
| --- | --- | --- |
| cook kept an `alias` result | reinforce count, keep source | learn generic → product, source=model, if unknown |
| cook kept a `name` result | create/reinforce, source=name, verified=True (a key matched) | nothing to learn |
| cook kept a `selected` result | create, source=model, verified=False | learn generic → product, source=model |
| cook changed the product (attach or search) | create/correct, source=cook, verified=True | learn generic → product, source=cook |
| cook detached and named a new product | create, source=cook, verified=True | canonical row for the new product |
| cook skipped the line | nothing | nothing |

Alias precedence in resolution: verified before unverified, then occurrence count, then
recency. An unverified alias still pre-fills the row, but the row shows it as "auto" (3.5).
A synonym learned from the model (`source=model`) is a key like any other; it is what makes
"Minced beef" hit "Ground beef" next week without the prompt carrying the catalog.

### 3.5 Review row

The row today offers include or skip. It gains:

- The proposed product as a chip with its provenance: **known** (alias verified or name),
  **auto** (model selection or unverified alias).
- **Change**: opens the existing product search (`useProductSearch`, ILIKE on the API) with a
  "New product: <generic name>" entry at the top. This is the deferred "attach an existing
  product per line" and the missing "detach" in one control.
- Confirm with zero included lines is allowed, so a receipt with nothing to add can be
  dismissed and its household lines remembered.

### 3.6 Extraction prompt

Once synonyms exist, the extraction prompt no longer needs the catalog list to keep names
consistent. Remove the 300-name block (`llm_extractor.build_instructions`), which also removes
the alphabetical cap and part of the prompt-size growth. Verify on the 49-line fixture that
generic-name quality does not regress and extraction time drops; keep the block behind a
setting for one release if it does regress.

### 3.7 Merge

`POST /api/products/{id}/merge` with `{target_id}`: re-point inventory items, aliases, product
names, shopping list items and consumption logs to the target, add the source's canonical name
as a synonym of the target, delete the source. One transaction, `handle_integrity_errors`,
broadcasts for the moved inventory items. This is also the only safe answer to "delete this
product" once the FKs are RESTRICT (foundations Critical #1).

## 4. What is deliberately not in this design

- **No embeddings first.** Trigram plus category is enough to shortlist for a catalog of
  hundreds; the retriever interface leaves the door open.
- **No language handling.** Generic names stay English (operator ruling, MVP-R2). Finnish
  display names are post-MVP item 13 and would be another `product_name.source`.
- **No automatic merging.** The unique index prevents new exact duplicates; near-duplicates
  ("Ground beef" vs "Beef mince") are found by the model at resolution time and fixed by the
  cook via merge, never by a script.

## 5. Increments

PR-sized, each with tests, in dependency order. Names follow the MVP convention; these are
fixes to MVP-R1b/R2 behaviour rather than post-MVP work, which is the operator's call.

| ID | Side | Increment | Depends on |
| --- | --- | --- | --- |
| PR-1 | backend | `product_name` table, unique normalised canonical name, dedupe migration, `ProductResolver` resolves by name; confirm learns synonyms (3.4 last column) | — |
| PR-2 | backend | `line_id` and `resolution` on stored lines; `ExtractedItem` exposes `match_source` as alias/name/selected/none and `verified`; `items_from_structured` tolerates old blobs | — |
| PR-3 | backend | `product_resolution.py`: deterministic tiers + `pg_trgm` retrieval + selection call; pipeline uses it; fuzzy decision path, `match_all`, `match_product` and `FUZZY_MATCH_THRESHOLD` removed | PR-1, PR-2 |
| PR-4 | backend | Alias provenance: `source`, unique (chain, receipt_name), learning table from 3.4, precedence in resolution | PR-3 |
| PR-5 | frontend | Review row: provenance chip, Change (search + new), empty confirm allowed | PR-2, PR-4 |
| PR-6 | backend | Merge endpoint; FKs to `product_master` become RESTRICT with a 409 naming the references | PR-1 |
| PR-7 | pipeline | Drop the catalog list from the extraction prompt behind a setting; measure on the fixture; make it the default if quality holds | PR-3 |

### Acceptance

- The six-line table in section 1 resolves to `none` for the five substring cases and to
  Ground beef for Minced beef once the synonym is learned by one confirm.
- The R1b regression (CHEDDAR PUNAINEN must not pair with PUNASIPULI) holds without a threshold.
- The MVP-R2 end-to-end (second receipt with other brands arrives 11/12 pre-matched) holds or
  improves; pre-matches are `name` or `alias`, not `selected`.
- Resolution with the model unreachable completes the receipt with unresolved lines as `none`.
- A wrong `selected` proposal changed by the cook on the row produces a verified alias and a
  cook-sourced synonym, and the next receipt resolves it by key with no model call.
- Merging two products leaves no orphan rows and the merged name resolves to the target.
- Extraction time on the 49-line fixture without the catalog block is recorded in
  `docs/vLLM_MANUAL_TEST.md` next to the existing 60-77 s runs.

### Risks

- One more model call per receipt when the catalog is warm and a line is unknown. Bounded by
  candidate count and only for unresolved lines; the cold-catalog case makes no call at all.
- The dedupe migration must run on the homelab data before the unique index; it should list
  what it merged in the migration log.
- `pg_trgm` is a new extension in the database; the migration creates it, and the test database
  must allow `CREATE EXTENSION` (the compose Postgres does).

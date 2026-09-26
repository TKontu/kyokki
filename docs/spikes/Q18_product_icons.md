# Q18 spike: product icons, picked or drawn

**Round:** 2026-09-26-6 (A3) · **Backlog:** Q18 in `docs/TODO.md` · **Model:** `c2.qwen3.8-27b`
on the homelab gateway (reasoning on, temperature 0.2, one request at a time)

## Question

Today every tile shows its **category's** emoji (`category_icon` in `IngredientTile`), so every
fruit is an apple and all meat a steak. Which route gives good-looking, *distinct* product
icons?

- **(a) pick:** the model picks an icon from one curated open SVG set, or answers `null`.
- **(b) draw:** the model writes a flat 48×48 SVG itself, in a fixed style.

## Answer

**Route (b), drawing, is the better route.** It produced a parseable, on-palette icon for all 20
products on the first attempt. 15 of them are clearly the product and 4 more are usable with
the name under them, so 19 of 20 are usable. Every icon is distinct from the others and all
share one style. Route (a) was right for 11 of 20 products (14 of 20 counting fair stand-ins).
It gave two pairs of products the same icon, and it had nothing at all for minced beef, salmon
or crisps. On the dark theme its black outlines disappear, and outline-only icons almost vanish.

## Method

- **Fixture:** `backend/tests/fixtures/icon_spike/products.json`, 20 generic names with their
  seeded category, from easy (tomato, banana) to hard (quark, rye bread, Karelian pasty, oat
  drink).
- **Tool:** `backend/scripts/icon_spike.py` (`--route vendor | pick | draw`). It writes
  `frontend/public/icon-spike/results.json`.
- **Set for (a):** OpenMoji 17.0.0, the default in the spec. I kept its food and drink subset:
  the Unicode `food-drink` group without `dishware`, plus OpenMoji's own food extras (boule
  bread, pretzel, roasted coffee bean, coloured jars and others). That is **144 icons, 466 KB**,
  with comments and whitespace removed. The prompt lists each icon as `id: annotation (tags)`.
  The answer is JSON `{"icon": id | null, "reason"}`, and an id outside the set counts as
  invalid. All 20 answers were valid.
- **Style for (b):** the prompt fixes `viewBox="0 0 48 48"`, an 8-colour palette (`#2B2B2B`
  outline, red, orange, yellow, green, brown, cream, white) and either a 2 px `#2B2B2B` outline
  or none. It forbids text, gradients, filters, `<image>`, `<script>`, `<style>`,
  `<foreignObject>`, event attributes and external references. At most 2 attempts per product.
- **Sanitiser:** the script parses the answer with `xml.etree.ElementTree`. It keeps only
  `svg g path circle ellipse rect polygon polyline line` and the geometry and presentation
  attributes. A `fill` or `stroke` value must be plain hex or `none`, so `url(#…)` cannot get
  through. It drops text nodes, namespaced attributes (`xlink:href`), `style`, `class`, `id` and
  `on*`, and it forces the viewBox. A test input containing `<script>`, `onload`, `<image
  xlink:href>`, `<foreignObject>`, `<style>`, `<text>` and a gradient fill came out as the
  circle and rect only.
- **Page:** `/components-demo/icons` shows the category emoji, (a) and (b) for each product,
  at tile size (40 px in a tile) and at 96 px, in a light panel and a dark panel. Drawn SVGs
  load only through `<img src>`, so even an SVG the sanitiser missed cannot run script.
- **Judging:** the "right" and "recognisable" columns below are **my judgement**, made from
  96 px and 40 px renders on light and dark backgrounds. The rule was: would someone glancing
  at the fridge screen, with the name under the icon, take it for this product?

## Results

| # | Product | (a) pick | (a) right? | (b) parsed | (b) recognisable | (b) s | (a) s |
|---|---|---|---|---|---|---|---|
| 1 | Tomato | 1F345 tomato | yes | yes (1st) | yes | 145.1 | 39.5 |
| 2 | Banana | 1F34C banana | yes | yes (1st) | yes | 83.9 | 32.9 |
| 3 | Orange | 1F34A tangerine | yes | yes (1st) | yes | 32.6 | 44.6 |
| 4 | Carrot | 1F955 carrot | yes | yes (1st) | yes | 72.1 | 37.8 |
| 5 | Potato | 1F954 potato | yes | yes (1st) | weak: a brown oval with eyes | 25.7 | 38.7 |
| 6 | Cucumber | 1F952 cucumber | yes | yes (1st) | yes (reads as a gherkin) | 57.2 | 31.1 |
| 7 | Milk | 1F95B glass of milk | yes | yes (1st) | yes (carton) | 268.3 | 10.5 |
| 8 | Quark | 1F9C0 cheese wedge | **no**: a hard cheese, the same icon as cheddar | yes (1st) | weak: a generic tub | 273.3 | 28.0 |
| 9 | Eggs | 1F95A egg | yes | yes (1st) | yes (eggs in a box) | 262.8 | 41.9 |
| 10 | Butter | 1F9C8 butter | yes | yes (1st) | weak: a striped block | 37.1 | 35.4 |
| 11 | Cheddar | 1F9C0 cheese wedge | yes | yes (1st) | yes (wedge) | 77.6 | 6.7 |
| 12 | Minced beef | null | **no**: 1F969 cut of meat was available | yes (1st) | yes (mince in a tray) | 86.2 | 19.6 |
| 13 | Chicken fillet strips | 1F357 poultry leg | stand-in | yes (1st) | yes (strips in a tray) | 44.1 | 13.9 |
| 14 | Salmon | null | none exists (no fish in the food subset) | yes (1st) | yes (striped fillet) | 92.0 | 13.0 |
| 15 | Rye bread | 1F35E bread | stand-in (a white toast loaf) | yes (1st) | yes (dark scored loaf) | 60.7 | 14.1 |
| 16 | Karelian pasty | 1F959 stuffed flatbread | **no**: reads as a kebab | yes (1st) | **no**: a wheel, not an oval pasty | 40.4 | 20.0 |
| 17 | Oat drink | 1F95B glass of milk | stand-in, the same icon as milk | yes (1st) | weak: a generic carton, but not the milk one | 29.5 | 16.2 |
| 18 | Apple juice | 1F34E red apple | **no**: 1F9C3 beverage box was a better pick | yes (1st) | yes (carton with an apple) | 57.8 | 17.1 |
| 19 | Crisps | null | none exists | yes (1st) | yes (a red bag) | 84.5 | 17.8 |
| 20 | Coffee | E0C6 roasted coffee bean | yes | yes (1st) | yes (a bag with a bean) | 60.7 | 13.3 |

Sanitising changed **none** of the 20 drawings. Every colour used was on the palette (50
outline, 17 cream, 13 white, 10 green, 8 brown, 7 red, 5 yellow, 4 orange). 19 of the 20 used
the 2 px outline; the salmon had none. The drawings are 239 to 547 bytes each, 8 KB in all.

### Totals

| | Route (a) pick | Route (b) draw |
|---|---|---|
| Right / recognisable | **11/20** right, 14/20 counting stand-ins | **15/20** clear, **19/20** usable |
| No icon at all | 3 (minced beef, salmon, crisps) | 0 |
| Wrong or unrecognisable | 3 (quark, Karelian pasty, apple juice) | 1 (Karelian pasty) |
| Distinct across the 20 | no: cheese wedge ×2, glass of milk ×2 | yes: all 20 differ |
| First-attempt success | 20/20 valid answers | 20/20 parsed and sanitised on the 1st attempt |
| Latency on `c2.qwen3.8-27b` | mean 24.6 s, median 19.8 s (6.7–44.6) | mean 94.6 s, median 66.4 s (25.7–273.3) |
| Total for 20 | 492 s | 1892 s (≈ 32 min) |

Most of the latency is reasoning (about 36 tokens/s on this slot). The three runs over 260 s
(milk, quark, eggs) came in a row, which points to a busy GPU as much as to the product. Both
routes are far too slow to run inline, and both are fine for a background job.

### What the pictures show

- OpenMoji looks very good wherever an icon exists, better than the model's drawings. But
  a set of 144 food icons cannot tell apart the products a Finnish household actually buys.
  Quark, rye bread, Karelian pasty, oat drink, minced meat, fillet strips and crisps have no
  icon of their own, and neither does fish.
- OpenMoji draws with thin **black** outlines and some shapes are unfilled (the glass of milk).
  On the dark theme the outlines disappear. Filled icons still read, but an outline-only
  shape like the glass of milk almost vanishes.
- The model's drawings are simple, but they are consistent: the fixed palette and the 2 px
  outline make them look like one set. They are also **specific in the way that matters**: the
  mince comes in a tray, the rye loaf is dark, and apple juice is a carton. Their weak spot
  is packaging. Quark, butter and oat drink came out as generic tubs, blocks and cartons, which
  work with the name under them but not without it.
- The model did not know what a Karelian pasty looks like under either route. That is a
  knowledge gap, not a drawing problem. The override will cover it.

## Licences

- **OpenMoji is CC BY-SA 4.0.** Shipping it means crediting it ("All emojis designed by
  OpenMoji – the open-source emoji and icon project. License: CC BY-SA 4.0") somewhere
  reachable in the app, for example an About or Credits page, and keeping the licence text.
  **Share-alike** applies to adaptations: a recoloured or edited OpenMoji must also be
  CC BY-SA. Displaying the icons unchanged next to our own code does not relicense the code.
  The vendored subset and its attribution are in `frontend/public/icon-spike/` (see
  `ATTRIBUTION.md`).
- Other sets would carry lighter terms, but they bring the same coverage gap and a style
  mismatch: Noto Emoji (Apache 2.0), Fluent Emoji (MIT), Twemoji (CC BY 4.0).
- **Drawn icons** come from our own model on our own hardware, with no third-party material,
  so no attribution is needed.

## Recommendation

Build **route (b)** next round: the model draws each product's icon once, in the background,
in the fixed style, and falls back to the category emoji. **Do not vendor a set.** An icon set
would add a licence obligation, a second visual style and dark-mode fixes, and it would only
improve the 11 easy products, which already look fine drawn. Keep the palette and the prompt
from `backend/scripts/icon_spike.py`, move the sanitiser into the app unchanged, and let the
operator redraw or pick another product's icon when the model misses, as it did for the
Karelian pasty.

### Next-round build outline

1. **`product_master.icon_svg`** (`Text`, nullable) holding the sanitised SVG markup, which is
   under 1 KB for the drawings seen here. Add `icon_status` (`pending | ready | failed`), or
   treat `NULL` plus a job record as pending. Alembic revision: add the columns only, with no
   backfill in the migration. Backfill existing products with a one-off script that queues the
   job. If a set is ever added, a second column `icon_ref` (for example `openmoji:1F345`) can
   sit beside it, and `icon_svg` wins.
2. **Mapping at product creation:** a background job like the shelf-life estimate, triggered
   when a product is created or renamed. It sends the draw prompt (2 attempts), sanitises the
   answer (move the spike's `sanitise()` into `app/services/product_icons.py`, with unit tests
   for the allowlist, including the malicious-input case), stores the result, and broadcasts a
   product update over the WebSocket so tiles refresh. A failure leaves the icon `NULL`. Budget
   about 1–5 minutes per product on `c2.qwen3.8-27b`, and queue jobs one at a time, because
   the gateway serves one request at a time.
3. **Serving:** `GET /api/v1/products/{id}/icon.svg` returns the stored markup with
   `Content-Type: image/svg+xml`, `Content-Security-Policy: default-src 'none'` and
   `X-Content-Type-Options: nosniff`. The frontend only ever uses it as `<img src>`, never
   `dangerouslySetInnerHTML`. Add an `icon_url` or `has_icon` to the product and inventory
   schemas and to `types/`.
4. **Override on `frontend/components/products/ProductEditSheet.tsx`:** show the current icon
   with **Redraw** (queue the job again, optionally with a hint such as "oval rye pastry with
   rice filling") and **Use category emoji** (clear it). A later option is to reuse another
   product's icon.
5. **`IngredientTile`:** render `<img src={icon_url}>` at about 40 px when the product has an
   icon, and fall back to `category_icon` otherwise, including while the icon is pending or
   failed. Keep `aria-hidden`, since the name already labels the tile.
6. **Dark mode:** the `#2B2B2B` outline is weak on dark tiles, but the filled shapes carry
   the icon. Check it on the iPad. If it is too faint, add a light rounded backdrop behind the
   image on dark tiles rather than recolouring the SVG.

### A diffusion model plus a tracer?

**Not worth adding now.** The gateway serves only LLMs. A diffusion model (an SDXL- or
Flux-class model with an icon-style LoRA) needs its own GPU memory and another service to run,
and its output still has to go through vtracer or potrace. Tracing a raster tends to give many
noisy paths and off-palette colours, so the result is harder to sanitise and less consistent
than the 250–550-byte drawings above. It would pay off only for detailed, photo-like icons,
which this UI does not need. Revisit it if the drawn icons turn out to fall short on the iPad.

## Caveats

- One run of 20 products at temperature 0.2. The variance between runs was not measured, and
  a redraw may come out better or worse.
- "Right" and "recognisable" are one reviewer's judgement from renders, not a user test.
- The comparison page runs in the Next app. The contact sheets in
  `frontend/public/icon-spike/screenshots/` were rendered from the
  same SVGs with resvg, because this container has no browser. They omit the colour emoji.

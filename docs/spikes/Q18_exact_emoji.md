# Q18 spike: exact Apple emoji or none, and the gap list

**Round:** 2026-09-27-3 (C2) · **Backlog:** Q18 in `docs/TODO.md` (new direction of 2026-09-27)
· **Model:** `c2.muse-glimmer` on the homelab gateway, one request at a time

## Question

The operator's rule: a product tile shows an Apple emoji **only when an exact one exists**. The
closest match is never used. Every product without an exact emoji goes on a **gap list**, and a
ComfyUI pipeline will draw those later. Which products have an exact emoji, how reliably can the
model tell, and what is left for the gap list?

"Exact", as the spike's spec defines it: the emoji's CLDR short name names the same food as the
product's generic name, at the level a cook means it. So Broccoli → 🥦 "broccoli" is exact,
Parsnip → 🥕 "carrot" is none, and Entrecôte → 🥩 "cut of meat" is borderline for the operator
to rule on.

## Answer

- **After the [operator rulings](#operator-rulings-2026-09-27), 109 of the 167 food products
  have an exact emoji and 58 go on the [gap list](#gap-list).** The other 24 of the 191 names
  are household goods and medicine. They are [not applicable](#not-applicable-non-food): the
  operator ruled that non-food needs no icon, because non-food lines are folded out on the
  review screen and never reach the fridge. Before the rulings, with my precision bar applied
  evenly, the 191 names split 83 exact, 54 borderline and 54 with nothing. The gap list is
  mostly yoghurts, quark and the cream family, condiments, processed meat and fish, and Finnish
  specialities.
- **The model is a good proposer but not a judge.** At reasoning `low` (the app's setting):
  - **Before the rulings** (all 191 names): it answered `exact` 85 times and 77 were correct,
    so precision is **0.91**. It found 77 of 83, so recall is **0.93**. All 8 errors are
    closest-match leaks: a generic, vessel or dish emoji for a more specific product.
  - **Against the ruled set** (167 food products): precision **0.97** (76 of 78). Only Whole
    chicken → 🐔 and Canned tomatoes → 🍅 are wrong, about **1 leak in 39**. Recall is only
    **0.70** (76 of 109). The prompt carries the old family-level definition and knows no
    per-product rulings, so the model leaves most of the newly exact products as borderline.
- **Reasoning `high` does not help.**
  - It is no more accurate: 0.88 / 0.87 before the rulings, 0.96 / 0.65 after.
  - It is about **6 times slower** (67–132 s a batch against 11–23 s).
  - It agrees with `low` on only 158 of 191 products.
- **Recommendation for the build:**
  - a curated per-product table first, and the model only for names the table does not know;
  - non-food skipped entirely;
  - the model's `exact` counts only after a person has confirmed it once.

  See [Recommendation](#recommendation-for-the-build).

## Method

- **Reference data:** `backend/scripts/emoji_food.json` has **186 emoji**. It was generated
  by `python -m scripts.emoji_trial --build-reference emoji-test.txt` from Unicode's
  [`emoji-test.txt`](https://unicode.org/Public/emoji/latest/emoji-test.txt), **Emoji 18.0**
  (dated 2026-04-30), keeping fully qualified forms only. It lives beside the script, not in a
  `data/` folder, because `.gitignore` ignores every `data/` directory. It takes:
  - the whole *Food & Drink* group, all subgroups, dishware included;
  - the *plant-flower* and *plant-other* subgroups (🌿 herb, 💐 bouquet, 🍄 mushroom);
  - named animals sold as food. Emoji 18.0 files seafood under *animal-marine*, so this covers
    🐟 fish, 🐙 octopus, 🦀 crab, 🦞 lobster, 🦐 shrimp, 🦑 squid, 🦪 oyster and 🐔 chicken;
  - household goods found on receipts: 🧼 soap, 🧻 roll of paper, 🧽 sponge, 🪥 toothbrush,
    🧴 lotion bottle, 🕯️ candle, 💊 pill, 🩹 adhesive bandage, 🔋 battery, 💡 light bulb,
    🧹 broom, 🧺 basket, 🪣 bucket, 🪒 razor, 🫧 bubbles, 🧷 safety pin, 🗑️ wastebasket,
    🛍️ shopping bags, 🌡️ thermometer and 💉 syringe.
- **Version cutoff: Emoji 15.1, a conservative choice.** Apple shipped Emoji 15.0 in iOS/iPadOS
  16.4, 15.1 in 17.4 and 16.0 in 18.4. The iPad 8th gen runs iPadOS 17 or 18, so an up-to-date
  one (18.4 or later) renders Emoji 16.0 too. The cutoff at 15.1 is safe for any iPadOS 17.4
  or later.
  - **Excluded as newer** (listed in the JSON under `excluded_newer`): 🫜 root vegetable
    (16.0), 🪾 leafless tree (16.0) and **🫝 pickle (18.0)**. Pickle would make Pickles exact,
    so it is worth revisiting once the iPad's iPadOS renders Emoji 18.
  - **Kept, and needing iPadOS 16.4 or 17.4:** 🫚 ginger root, 🫛 pea pod, 🪻 hyacinth (15.0);
    🍋‍🟩 lime and 🍄‍🟫 brown mushroom (15.1).
- **Picker:** `backend/scripts/emoji_trial.py`. It sends batches of products, each with its
  category, together with the whole reference list (`emoji name` per line) and a definition of
  "exact" with its examples, and asks for strict-schema JSON:
  `{"r": [{"i", "e": emoji|null, "m": "exact"|"borderline"|"none", "why"}]}`.
  - **An addition of mine in the prompt:** it says "a brand, a pack size, a variety or
    plural/singular does not change the food". The spec's definition does not say that, and the
    spec treats Entrecôte → 🥩 as borderline. The clause may have pushed the model towards
    exact for Gouda → 🧀 and Rainbow trout → 🐟, which the pre-ruling scoring counts as errors.
    The operator later ruled both exact.
  - **How the script checks every answer:**
    - An emoji outside the reference list, or `exact`/`borderline` without an emoji, is
      `invalid`, and its emoji is dropped.
    - A `none` that still names an emoji keeps no emoji, so a closest match can never be
      stored.
    - The answer rows must be numbered exactly 1..n. Otherwise the whole batch is `invalid`,
      because the rows are matched to products by number.
    - An emoji missing its variation selector is mapped to the fully qualified form.
    - A reply with no JSON, or a failed request, makes its batch `missing`.
    - The output files are rewritten after every batch.

    None of the three runs had an invalid or missing answer. The numbering check and the
    incremental output were added after the runs, in review.
- **Names:** 191 generic English names with a category. The spec asked for about 150, with
  about 60 added groceries. The input is committed as
  [`q18_exact_emoji/names.csv`](q18_exact_emoji/names.csv), in run order. It is built from:
  - the spike's 20 products (`backend/tests/fixtures/icon_spike/products.json`);
  - the lines of the four `backend/tests/fixtures/receipts/expected_*.json` files, rewritten as
    generic names (for example "PORKKANA 1KG" → Carrot, "Naudan Entrecote Palana" → Entrecôte)
    and given seeded category ids;
  - about 110 common Finnish household groceries and household goods covering dairy, bread,
    meat, fish, vegetables, fruit, dry goods, condiments, drinks, ready meals and household
    items.

  The spec also named the "category seed examples" as a source. `seed_categories.py` has no
  example product names, only the 13 categories, so that source contributed the category ids
  and nothing else. Household goods have category `household`. There is no such seeded
  category; it only gives the model context.
- **Runs** (temperature 0.1, batches of 20, one request at a time). The raw outputs are in
  [`q18_exact_emoji/`](q18_exact_emoji/), as `run<N>_<reasoning>.csv` and `.log`:

  | Run | Reasoning | Batch time | exact | borderline | none |
  | --- | --- | --- | --- | --- | --- |
  | 0 | low | 11–21 s | 84 | 45 | 62 |
  | 1 | low | 12–23 s | 85 | 41 | 65 |
  | 2 | high | 67–132 s | 82 | 53 | 56 |

  Run 0 used a reference list that had only the *Food & Drink* group. Reviewing it showed that
  Emoji 18.0 files 🦐 🦑 🦪 🦀 🦞 under *animal-marine*. As a result Squid and Oysters came back
  none and Shrimp got 🍤 "fried shrimp". I added the seafood and re-ran; run 0 is not scored.
  Apart from those three products, runs 0 and 1 still differ on 16 of the others, so a single
  `low` answer is not stable.
- **Precision check, before the rulings:** I ruled every product myself against the CLDR names,
  using the spec's examples as the bar, applied evenly:
  - a generic emoji for a specific product (🧀 for Gouda, 🐟 for trout, 🥩 for pork chops) is
    borderline;
  - so is an emoji that shows a vessel (🍺 "beer mug", 🍷 "wine glass", ☕), a dish (🍚
    "cooked rice", 🍝, 🍠 "roasted sweet potato") or a different form of the product (🫛 "pea
    pod" for frozen peas, a 🧼 bar of soap for liquid soap).

  An `exact` answer counts as correct only when my ruling is exact with the same emoji. Where
  I was unsure, I ruled borderline. The operator's rulings then replaced this bar; the
  [re-score](#precision-and-recall) uses them.

## Precision and recall

| | Run 1 (`low`) | Run 2 (`high`) |
| --- | --- | --- |
| **Before the rulings** (all 191; my bar, applied evenly: 83 exact) | | |
| `exact` answers | 85 | 82 |
| correct | 77 | 72 |
| precision | **0.91** | 0.88 |
| recall | 77/83 = **0.93** | 72/83 = 0.87 |
| **Against the ruled set** (167 food products, 109 exact) | | |
| `exact` answers | 78 | 74 |
| correct | 76 | 71 |
| precision | **0.97** | 0.96 |
| recall | 76/109 = **0.70** | 71/109 = 0.65 |

The first version of this doc applied my bar unevenly: it counted Beer → 🍺 "beer mug", Sweet
potato → 🍠 "roasted", Frozen peas → 🫛 and the liquid soaps → 🧼 as exact. Against that
uneven bar, `low` scored 0.92 / 0.89 and `high` 0.93 / 0.86. The operator then ruled 🍺, 🍠
and 🫛 exact, and the soaps not applicable.

### Errors: `exact` answers that break the rule

| Product | Answered | CLDR name | Before the rulings | Against the rulings | Run |
| --- | --- | --- | --- | --- | --- |
| Whole chicken | 🐔 | chicken | error: the live bird | **error** (ruled no) | low, high |
| Canned tomatoes | 🍅 | tomato | error: processed product | **error** (ruled: must not be 🍅) | low, high |
| Sparkling wine | 🍷 | wine glass | error: vessel | **error** (ruled 🍾) | high |
| Gouda | 🧀 | cheese wedge | error: generic emoji | correct (ruled yes) | low |
| Rainbow trout | 🐟 | fish | error: generic emoji | correct (ruled yes) | low |
| Rice | 🍚 | cooked rice | error: dish | correct (ruled yes) | low |
| Spaghetti | 🍝 | spaghetti | error: dish | correct (ruled yes) | low, high |
| Red wine | 🍷 | wine glass | error: vessel | correct (ruled yes) | low, high |
| Beer | 🍺 | beer mug | error: vessel | correct (vessel ruling) | low, high |
| Sweet potato | 🍠 | roasted sweet potato | error: dish | correct (ruled yes) | high |
| Dish soap, Foam hand soap, Liquid soap | 🧼 | soap | error | not applicable (non-food) | high |

### Misses: exact products the model did not call exact

- **Before the rulings, `low`:** 6 of the 83 went to `borderline` (Toast bread, Sweet corn,
  Kidney beans, Mandarin, Kitchen roll, Cut flowers) and none went to `none`. `high`
  downgraded 11: of those six it has only 4 (Toast bread, Mandarin, Kitchen roll, Cut
  flowers), and adds Apple, Milk chocolate with hazelnuts, Lactose-free milk drink, Chicken
  drumsticks, Chili pepper, Toilet paper and Dish sponge.
- **Against the ruled set, `low`:**
  - 6 exact products went to `none`: Orange, Dill, Tea, Instant noodles, Cola and Liver
    casserole.
  - 27 went to `borderline`, mostly the family rulings: the cheeses, fish, meats, breads,
    greens and vessels.
  - Under the rule a borderline answer reaches the operator, not the tile. A `none` would put
    an exact product on the gap list, so these rulings belong in the curated table.

## Operator rulings (2026-09-27)

**The operator's principle, in their words:** "It needs to be precise, so it doesn't require
cognitive effort." Matches are decided **per product, not per family**.

The planner summarised this as "an emoji counts only if it depicts the product as it looks
when bought". **That is the planner's gloss, not a ruling.** 10 of the yes-rulings do not
follow it: 🍚 "cooked rice", 🍝, 🍜 and 🍲 for dry or packaged products, and the drink
vessels ☕ (coffee, glögi), 🍵, 🍷, 🍾 and 🥤. The rulings below are the record; the gloss is
not a rule.

The rulings came in two rounds. Round 2 answered the 10 products that round 1 left to
inference.

| Ruling | Exact (yes) | Gap list (no) |
| --- | --- | --- |
| 🧀 for a named cheese that is whole or sliced | Cheddar, Gouda, Emmental, Keisarinna cheese, Feta | Mozzarella, Blue cheese, Cottage cheese (pre-grated cheese is no as well) |
| 🥩 for Entrecôte and similar whole cuts | Entrecôte; round 2: Pork chops, Reindeer sauté | Minced beef (minced meat, fillet slices and strips are no) |
| 🐟 for a named fish sold as fish | Salmon, Rainbow trout, Baltic herring; round 2: Pickled herring | Round 2: Canned tuna, Fish fingers ("No, fish fingers and tuna can should look as they should.") |
| 🥬 / 🌿 for a named green or herb | Lettuce 🥬, Cabbage 🥬, Spinach 🥬, Parsley 🌿, Dill 🌿 | none |
| 🍞 for other breads, 🫓 for pita and tortilla | Rye bread 🍞, Rye crispbread 🍞, Pita bread 🫓, Tortilla wraps 🫓 | none |
| A drink vessel for the drink | Coffee ☕, Glögi ☕, Tea 🍵, Red wine 🍷, Sparkling wine 🍾, Cola 🥤 | none |
| A dish for its ingredient | Rice 🍚, Spaghetti 🍝, Instant noodles 🍜, Liver casserole 🍲 | Canned tomatoes (must not be 🍅); Hot dog sausages (must not be 🌭, which has a bun); round 2: Tomato puree ("Tomato puree should either be a small can or squeeze out tube.") |
| A different form of the product (round 2) | Sweet potato 🍠 "roasted sweet potato", Frozen peas 🫛 "pea pod" | none |
| Single products | Orange 🍊 | Chanterelles 🍄, Whole chicken 🐔, Margarine 🧈 |
| **Non-food (round 2):** "I do not get why soap needs an emoji, it is not food." | none | none: [not applicable](#not-applicable-non-food) |

- **Tomato puree:** the operator ticked 🍅, then added the sentence quoted above, so it needs
  its own icon and goes on the gap list.
- **Beer → 🍺 "beer mug":** never borderline, but covered by the vessel ruling, so it stays
  exact.
- **My other own exact calls,** where the CLDR name is not literally the product's name, were
  not challenged and stay exact: Mandarin 🍊 "tangerine", Kidney beans 🫘 "beans", Sweet corn 🌽
  "ear of corn" and Toast bread 🍞 "bread".

Nothing is pending any more.

## Gap list

These **58 food products** need a generated icon. Rulings are marked *(ruled)*; the rest had no
candidate emoji.

- **Dairy:** Quark, Drinking yoghurt, Natural yoghurt, Turkish yoghurt, Viili, Skyr, Buttermilk,
  Crème fraîche, Sour cream, Whipping cream, Margarine *(ruled)*
- **Cheese:** Mozzarella *(ruled)*, Blue cheese *(ruled)*, Cottage cheese *(ruled)*
- **Bread and bakery:** Karelian pasty, Cinnamon bun
- **Meat:** Chicken fillet strips, Sausage, Sliced ham, Meatballs, Minced beef *(ruled)*,
  Hot dog sausages *(ruled)*, Whole chicken *(ruled)*
- **Fish:** Canned tuna *(ruled)*, Fish fingers *(ruled)*
- **Vegetables:** Parsnip, Swede, Leek, Zucchini, Sauerkraut, Chanterelles *(ruled)*
- **Fruit and berries:** Pomegranate, Lingonberries, Raspberries
- **Dry goods and pantry:** Wheat flour, Porridge oats, Sugar, Olive oil, Canned tomatoes
  *(ruled)*, Tomato puree *(ruled)*
- **Condiments and spreads:** Ketchup, Mustard, Mayonnaise, Strawberry jam, Apple sauce,
  Taco sauce, Sweet chili dip, Beetroot hummus, Pickles (🫝 pickle exists from Emoji 18.0,
  above the cutoff)
- **Drinks:** Oat drink, Apple juice, Orange juice, Mineral water
- **Snacks:** Crisps, Tortilla chips, Potato sticks, Salty liquorice
- **Ready meals:** Lasagne

### Icon briefs from the operator

For the ComfyUI lane: where the operator described the look, the generated icon should show
it.

| Product | Brief |
| --- | --- |
| Tomato puree | "a small can or squeeze out tube" |
| Canned tomatoes | a can (not a fresh 🍅) |
| Canned tuna | "should look as they should": the tuna can as sold |
| Fish fingers | "should look as they should": the fish fingers, or their pack, as sold |

## Not applicable: non-food

The operator: "I do not get why soap needs an emoji, it is not food." Non-food lines are
folded out on the receipt review screen and never become fridge stock, so they need neither an
emoji nor a generated icon. These **24** names are out of the counts:

- **Cleaning:** Dish soap, Foam hand soap, Liquid soap, Laundry rinse vinegar, Kitchen
  cleaning spray, All-purpose cleaner, Laundry detergent, Sponge cloth, Dish sponge
- **Paper and bags:** Toilet paper, Kitchen roll, Compost bags, Bin bags
- **Personal care and medicine:** Toothbrush, Toothpaste, Shampoo, Tampons, Plasters,
  Multivitamin, Painkillers
- **Other:** Candles, Batteries, Light bulb, Cut flowers

The model answered `exact` for several of these (🧻, 🪥, 🕯️, 🔋, 💡, 🩹), and 🧼 for the soaps
in `high`. The reference list keeps its household emoji only because this trial measured them.

## Borderline as submitted (now ruled)

This is the list the operator was asked about in round 1, kept for the record. It was grouped
by family; the [rulings](#operator-rulings-2026-09-27) decide each product on its own.

| Family question | Products | Candidate |
| --- | --- | --- |
| Does 🧀 "cheese wedge" stand for a named cheese? | Cheddar, Gouda, Feta, Mozzarella, Emmental, Blue cheese, Keisarinna cheese, Cottage cheese | 🧀 |
| Does 🐟 "fish" stand for a named fish, raw or processed? | Salmon, Rainbow trout, Baltic herring, Pickled herring, Canned tuna, Fish fingers | 🐟 |
| Does 🥩 "cut of meat" stand for a named cut or meat? | Entrecôte, Pork chops, Reindeer sauté, Minced beef | 🥩 |
| Does 🍞 "bread" (a white loaf) stand for other breads? | Rye bread, Rye crispbread | 🍞 |
| Does 🫓 "flatbread" stand for pita and tortilla? | Pita bread, Tortilla wraps | 🫓 |
| Does 🥬 "leafy green" / 🌿 "herb" stand for a named green or herb? | Lettuce, Cabbage, Spinach, Parsley, Dill | 🥬 🌿 |
| Does a drink vessel stand for the drink? | Coffee, Tea, Glögi, Red wine, Sparkling wine, Cola | ☕ 🍵 🍷 🍾 🥤 |
| Does a dish or processed form stand for the ingredient? | Rice, Spaghetti, Instant noodles, Canned tomatoes, Tomato puree, Liver casserole, Hot dog sausages | 🍚 🍝 🍜 🍅 🍲 🌭 |
| Single products | Orange, Whole chicken, Chanterelles, Margarine, Dish soap, Sponge cloth, Multivitamin, Painkillers, Shampoo | 🍊 🐔 🍄 🧈 🧼 🧽 💊 🧴 |

## Full results

The tables are grouped by the run 1 (`low`) answer. *High* is run 2's answer for the same
product.
- *Pre-ruling bar* is my own ruling, applied evenly, before the operator ruled.
- *Now* is the current state: exact, gap or n/a (non-food).
- *Why* is the model's own reason, from run 1.

The same data is in the raw CSVs under [`q18_exact_emoji/`](q18_exact_emoji/).

### Model said exact (85)

| Product | Category | Low | High | Pre-ruling bar | Now | Model's why (low) |
| --- | --- | --- | --- | --- | --- | --- |
| Tomato | produce | 🍅 exact | 🍅 exact | exact 🍅 | exact 🍅 | emoji name is tomato |
| Banana | fruits | 🍌 exact | 🍌 exact | exact 🍌 | exact 🍌 | emoji name is banana |
| Carrot | produce | 🥕 exact | 🥕 exact | exact 🥕 | exact 🥕 | emoji name is carrot |
| Potato | produce | 🥔 exact | 🥔 exact | exact 🥔 | exact 🥔 | emoji name is potato |
| Cucumber | produce | 🥒 exact | 🥒 exact | exact 🥒 | exact 🥒 | emoji name is cucumber |
| Milk | dairy | 🥛 exact | 🥛 exact | exact 🥛 | exact 🥛 | example milk to glass of milk |
| Eggs | dairy | 🥚 exact | 🥚 exact | exact 🥚 | exact 🥚 | example eggs to egg |
| Butter | dairy | 🧈 exact | 🧈 exact | exact 🧈 | exact 🧈 | emoji name is butter |
| White bread | bread | 🍞 exact | 🍞 exact | exact 🍞 | exact 🍞 | white bread is bread |
| Apple | fruits | 🍎 exact | 🍎 borderline | exact 🍎 | exact 🍎 | apple is apple |
| Milk chocolate with hazelnuts | snacks | 🍫 exact | 🍫 borderline | exact 🍫 | exact 🍫 | milk chocolate is chocolate bar |
| Gouda | cheese | 🧀 exact | 🧀 borderline | borderline | exact 🧀 | gouda is cheese |
| Chocolate chip cookies | snacks | 🍪 exact | 🍪 exact | exact 🍪 | exact 🍪 | chocolate chip cookies are cookies |
| Chocolate ice cream | frozen | 🍨 exact | 🍨 exact | exact 🍨 | exact 🍨 | chocolate ice cream is ice cream |
| Grapes | fruits | 🍇 exact | 🍇 exact | exact 🍇 | exact 🍇 | grapes is grapes |
| Plum tomatoes | produce | 🍅 exact | 🍅 exact | exact 🍅 | exact 🍅 | plum tomatoes are tomato |
| Mini bell peppers | produce | 🫑 exact | 🫑 exact | exact 🫑 | exact 🫑 | mini bell peppers are bell pepper |
| Broccoli | produce | 🥦 exact | 🥦 exact | exact 🥦 | exact 🥦 | broccoli is broccoli |
| Lactose-free milk drink | dairy | 🥛 exact | 🥛 borderline | exact 🥛 | exact 🥛 | lactose free milk drink is milk |
| Mango | fruits | 🥭 exact | 🥭 exact | exact 🥭 | exact 🥭 | emoji name is mango |
| Bacon | meat | 🥓 exact | 🥓 exact | exact 🥓 | exact 🥓 | emoji name is bacon |
| Green apple | fruits | 🍏 exact | 🍏 exact | exact 🍏 | exact 🍏 | emoji name is green apple |
| Pear | fruits | 🍐 exact | 🍐 exact | exact 🍐 | exact 🍐 | emoji name is pear |
| Red onion | produce | 🧅 exact | 🧅 exact | exact 🧅 | exact 🧅 | red onion is onion |
| Lime | fruits | 🍋‍🟩 exact | 🍋‍🟩 exact | exact 🍋‍🟩 | exact 🍋‍🟩 | lime is lime |
| Cherry tomatoes | produce | 🍅 exact | 🍅 exact | exact 🍅 | exact 🍅 | cherry tomatoes are tomatoes |
| Baguette | bread | 🥖 exact | 🥖 exact | exact 🥖 | exact 🥖 | baguette bread |
| Croissant | bread | 🥐 exact | 🥐 exact | exact 🥐 | exact 🥐 | croissant |
| Bagel | bread | 🥯 exact | 🥯 exact | exact 🥯 | exact 🥯 | bagel |
| Pretzel | bread | 🥨 exact | 🥨 exact | exact 🥨 | exact 🥨 | pretzel |
| Pancakes | frozen | 🥞 exact | 🥞 exact | exact 🥞 | exact 🥞 | pancakes |
| Whole chicken | meat | 🐔 exact | 🐔 exact | borderline | gap | whole chicken |
| Chicken drumsticks | meat | 🍗 exact | 🍗 borderline | exact 🍗 | exact 🍗 | drumstick is poultry leg |
| Rainbow trout | fish | 🐟 exact | 🐟 borderline | borderline | exact 🐟 | trout is fish |
| Shrimp | fish | 🦐 exact | 🦐 exact | exact 🦐 | exact 🦐 | shrimp matches shrimp |
| Squid | fish | 🦑 exact | 🦑 exact | exact 🦑 | exact 🦑 | squid matches squid |
| Oysters | fish | 🦪 exact | 🦪 exact | exact 🦪 | exact 🦪 | oysters match oyster |
| Onion | produce | 🧅 exact | 🧅 exact | exact 🧅 | exact 🧅 | onion matches onion |
| Garlic | produce | 🧄 exact | 🧄 exact | exact 🧄 | exact 🧄 | garlic matches garlic |
| Bell pepper | produce | 🫑 exact | 🫑 exact | exact 🫑 | exact 🫑 | bell pepper matches bell pepper |
| Avocado | produce | 🥑 exact | 🥑 exact | exact 🥑 | exact 🥑 | avocado matches avocado |
| Mushrooms | produce | 🍄 exact | 🍄 exact | exact 🍄 | exact 🍄 | mushrooms match mushroom |
| Aubergine | produce | 🍆 exact | 🍆 exact | exact 🍆 | exact 🍆 | aubergine is eggplant |
| Ginger | produce | 🫚 exact | 🫚 exact | exact 🫚 | exact 🫚 | emoji is ginger root |
| Chili pepper | produce | 🌶️ exact | 🌶️ borderline | exact 🌶️ | exact 🌶️ | emoji is hot pepper |
| Olives | condiments | 🫒 exact | 🫒 exact | exact 🫒 | exact 🫒 | emoji is olive |
| Lemon | fruits | 🍋 exact | 🍋 exact | exact 🍋 | exact 🍋 | emoji is lemon |
| Strawberries | fruits | 🍓 exact | 🍓 exact | exact 🍓 | exact 🍓 | emoji is strawberry |
| Blueberries | fruits | 🫐 exact | 🫐 exact | exact 🫐 | exact 🫐 | emoji is blueberries |
| Watermelon | fruits | 🍉 exact | 🍉 exact | exact 🍉 | exact 🍉 | emoji is watermelon |
| Melon | fruits | 🍈 exact | 🍈 exact | exact 🍈 | exact 🍈 | emoji is melon |
| Pineapple | fruits | 🍍 exact | 🍍 exact | exact 🍍 | exact 🍍 | emoji is pineapple |
| Kiwi | fruits | 🥝 exact | 🥝 exact | exact 🥝 | exact 🥝 | emoji is kiwi fruit |
| Peach | fruits | 🍑 exact | 🍑 exact | exact 🍑 | exact 🍑 | emoji is peach |
| Cherries | fruits | 🍒 exact | 🍒 exact | exact 🍒 | exact 🍒 | emoji is cherries |
| Coconut | fruits | 🥥 exact | 🥥 exact | exact 🥥 | exact 🥥 | emoji is coconut |
| Rice | pantry | 🍚 exact | 🍚 borderline | borderline | exact 🍚 | cooked rice matches rice |
| Spaghetti | pantry | 🍝 exact | 🍝 exact | borderline | exact 🍝 | spaghetti matches spaghetti |
| Salt | pantry | 🧂 exact | 🧂 exact | exact 🧂 | exact 🧂 | salt matches salt |
| Honey | pantry | 🍯 exact | 🍯 exact | exact 🍯 | exact 🍯 | honey pot names honey |
| Peanuts | snacks | 🥜 exact | 🥜 exact | exact 🥜 | exact 🥜 | peanuts matches peanuts |
| Chestnuts | snacks | 🌰 exact | 🌰 exact | exact 🌰 | exact 🌰 | chestnut matches chestnuts |
| Popcorn | snacks | 🍿 exact | 🍿 exact | exact 🍿 | exact 🍿 | popcorn matches popcorn |
| Chocolate bar | snacks | 🍫 exact | 🍫 exact | exact 🍫 | exact 🍫 | chocolate bar matches chocolate bar |
| Lollipop | snacks | 🍭 exact | 🍭 exact | exact 🍭 | exact 🍭 | lollipop matches lollipop |
| Canned tomatoes | pantry | 🍅 exact | 🍅 exact | borderline | gap | tomato matches canned tomatoes |
| Beer | beverages | 🍺 exact | 🍺 exact | borderline | exact 🍺 | beer mug names beer |
| Red wine | beverages | 🍷 exact | 🍷 exact | borderline | exact 🍷 | wine glass names wine |
| Yerba mate | beverages | 🧉 exact | 🧉 exact | exact 🧉 | exact 🧉 | mate names yerba mate |
| Frozen pizza | frozen | 🍕 exact | 🍕 exact | exact 🍕 | exact 🍕 | pizza names pizza |
| Sushi | ready_meals | 🍣 exact | 🍣 exact | exact 🍣 | exact 🍣 | sushi names sushi |
| Dumplings | frozen | 🥟 exact | 🥟 exact | exact 🥟 | exact 🥟 | dumpling names dumplings |
| Falafel | ready_meals | 🧆 exact | 🧆 exact | exact 🧆 | exact 🧆 | falafel names falafel |
| Burrito | ready_meals | 🌯 exact | 🌯 exact | exact 🌯 | exact 🌯 | burrito names burrito |
| Hamburger | ready_meals | 🍔 exact | 🍔 exact | exact 🍔 | exact 🍔 | hamburger names hamburger |
| Ice cubes | frozen | 🧊 exact | 🧊 exact | exact 🧊 | exact 🧊 | ice names ice cubes |
| Doughnut | bread | 🍩 exact | 🍩 exact | exact 🍩 | exact 🍩 | doughnut names doughnut |
| Cupcake | bread | 🧁 exact | 🧁 exact | exact 🧁 | exact 🧁 | cupcake names cupcake |
| Toilet paper | household | 🧻 exact | 🧻 borderline | exact 🧻 | n/a (non-food) | roll of paper names toilet paper |
| Toothbrush | household | 🪥 exact | 🪥 exact | exact 🪥 | n/a (non-food) | toothbrush names toothbrush |
| Candles | household | 🕯️ exact | 🕯️ exact | exact 🕯️ | n/a (non-food) | candle matches candles |
| Batteries | household | 🔋 exact | 🔋 exact | exact 🔋 | n/a (non-food) | battery matches batteries |
| Dish sponge | household | 🧽 exact | 🧽 borderline | exact 🧽 | n/a (non-food) | sponge matches dish sponge |
| Light bulb | household | 💡 exact | 💡 exact | exact 💡 | n/a (non-food) | light bulb matches |
| Plasters | household | 🩹 exact | 🩹 exact | exact 🩹 | n/a (non-food) | adhesive bandage is plaster |

### Model said borderline (41)

| Product | Category | Low | High | Pre-ruling bar | Now | Model's why (low) |
| --- | --- | --- | --- | --- | --- | --- |
| Cheddar | cheese | 🧀 borderline | 🧀 borderline | borderline | exact 🧀 | cheddar is cheese, emoji is cheese wedge |
| Minced beef | meat | 🥩 borderline | none | borderline | gap | minced beef is meat, emoji is cut of meat |
| Chicken fillet strips | meat | 🐔 borderline | 🐔 borderline | none | gap | strips are chicken, emoji is chicken |
| Salmon | fish | 🐟 borderline | 🐟 borderline | borderline | exact 🐟 | salmon is fish, emoji is fish |
| Rye bread | bread | 🍞 borderline | 🍞 borderline | borderline | exact 🍞 | rye bread is bread, emoji is white loaf |
| Coffee | pantry | ☕ borderline | ☕ borderline | borderline | exact ☕ | coffee is hot beverage, emoji is hot beverage |
| Entrecôte | meat | 🥩 borderline | 🥩 borderline | borderline | exact 🥩 | entrecôte is cut of meat |
| Feta | cheese | 🧀 borderline | 🧀 borderline | borderline | exact 🧀 | feta is a cheese, emoji is generic cheese wedge |
| Keisarinna cheese | cheese | 🧀 borderline | 🧀 borderline | borderline | exact 🧀 | keisarinna is a cheese, emoji is generic cheese wedge |
| Rye crispbread | bread | 🍞 borderline | 🍞 borderline | borderline | exact 🍞 | crispbread is bread, emoji is white loaf |
| Liquid soap | household | 🧼 borderline | 🧼 exact | borderline | n/a (non-food) | liquid soap is soap, emoji is soap |
| Sponge cloth | household | 🧽 borderline | 🧽 borderline | borderline | n/a (non-food) | sponge cloth is a sponge, emoji is sponge |
| Glögi | beverages | ☕ borderline | ☕ borderline | borderline | exact ☕ | glögi is a hot beverage, emoji is generic |
| Lettuce | produce | 🥬 borderline | 🥬 borderline | borderline | exact 🥬 | lettuce is a leafy green |
| Tomato puree | pantry | 🍅 borderline | none | borderline | gap | puree is tomato product |
| Mozzarella | cheese | 🧀 borderline | 🧀 borderline | borderline | gap | mozzarella is cheese |
| Parsley | produce | 🌿 borderline | 🌿 borderline | borderline | exact 🌿 | parsley is an herb |
| Cottage cheese | cheese | 🧀 borderline | 🧀 borderline | borderline | gap | cottage cheese is cheese |
| Emmental | cheese | 🧀 borderline | 🧀 borderline | borderline | exact 🧀 | emmental is cheese |
| Blue cheese | cheese | 🧀 borderline | 🧀 borderline | borderline | gap | blue cheese is cheese |
| Pita bread | bread | 🫓 borderline | 🫓 borderline | borderline | exact 🫓 | pita is a flatbread |
| Tortilla wraps | bread | 🫓 borderline | 🫓 borderline | borderline | exact 🫓 | tortilla is a flatbread |
| Toast bread | bread | 🍞 borderline | 🍞 borderline | exact 🍞 | exact 🍞 | toast is bread |
| Hot dog sausages | meat | 🌭 borderline | 🌭 borderline | borderline | gap | hot dog sausages is hot dog |
| Pork chops | meat | 🥩 borderline | 🍖 borderline | borderline | exact 🥩 | pork chop is cut of meat |
| Reindeer sauté | meat | 🥩 borderline | 🥩 borderline | borderline | exact 🥩 | reindeer is cut of meat |
| Baltic herring | fish | 🐟 borderline | 🐟 borderline | borderline | exact 🐟 | herring is a fish, emoji is generic fish |
| Pickled herring | fish | 🐟 borderline | 🐟 borderline | borderline | exact 🐟 | pickled herring is a fish, emoji is generic fish |
| Canned tuna | fish | 🐟 borderline | 🐟 borderline | borderline | gap | tuna is a fish, emoji is generic fish |
| Fish fingers | frozen | 🐟 borderline | none | borderline | gap | fish fingers are fish, emoji is generic fish |
| Sweet corn | produce | 🌽 borderline | 🌽 exact | exact 🌽 | exact 🌽 | sweet corn is corn, emoji is ear of corn |
| Chanterelles | produce | 🍄 borderline | 🍄 borderline | borderline | gap | chanterelle is a mushroom, emoji is generic mushroom |
| Cabbage | produce | 🥬 borderline | 🥬 borderline | borderline | exact 🥬 | cabbage is leafy green, emoji is generic leafy green |
| Spinach | produce | 🥬 borderline | 🥬 borderline | borderline | exact 🥬 | spinach is leafy green, emoji is generic leafy green |
| Frozen peas | frozen | 🫛 borderline | none | borderline | exact 🫛 | emoji is pea pod not peas |
| Kidney beans | pantry | 🫘 borderline | 🫘 exact | exact 🫘 | exact 🫘 | emoji is beans generic |
| Sweet potato | produce | 🍠 borderline | 🍠 exact | borderline | exact 🍠 | emoji is roasted sweet potato |
| Mandarin | fruits | 🍊 borderline | 🍊 borderline | exact 🍊 | exact 🍊 | emoji is tangerine for mandarin |
| Sparkling wine | beverages | 🍾 borderline | 🍷 exact | borderline | exact 🍾 | bottle with popping cork for sparkling wine |
| Kitchen roll | household | 🧻 borderline | 🧻 borderline | exact 🧻 | n/a (non-food) | roll of paper is generic for kitchen roll |
| Cut flowers | household | 💐 borderline | 💐 borderline | exact 💐 | n/a (non-food) | bouquet is cut flowers, generic match |

### Model said none (65)

| Product | Category | Low | High | Pre-ruling bar | Now | Model's why (low) |
| --- | --- | --- | --- | --- | --- | --- |
| Orange | fruits | none | none | borderline | exact 🍊 | emoji is tangerine not orange |
| Quark | dairy | none | none | none | gap | no quark emoji |
| Karelian pasty | bread | none | none | none | gap | no pasty emoji |
| Oat drink | beverages | none | none | none | gap | no oat drink emoji |
| Apple juice | beverages | none | none | none | gap | no apple juice emoji |
| Crisps | snacks | none | none | none | gap | no crisps emoji |
| Drinking yoghurt | dairy | none | none | none | gap | no yoghurt emoji |
| Dish soap | household | none | 🧼 exact | borderline | n/a (non-food) | no dish soap emoji |
| Natural yoghurt | dairy | none | none | none | gap | no yoghurt emoji |
| Parsnip | produce | none | none | none | gap | parsnip no emoji carrot is carrot |
| Foam hand soap | household | none | 🧼 exact | borderline | n/a (non-food) | no hand soap emoji |
| Tampons | household | none | none | none | n/a (non-food) | no tampon emoji |
| Sauerkraut | produce | none | none | none | gap | no sauerkraut emoji |
| Beetroot hummus | condiments | none | none | none | gap | no hummus emoji |
| Apple sauce | condiments | none | none | none | gap | no sauce emoji |
| Pomegranate | fruits | none | none | none | gap | no pomegranate emoji |
| Taco sauce | condiments | none | none | none | gap | no sauce emoji |
| Crème fraîche | dairy | none | none | none | gap | no crème fraîche emoji |
| Tortilla chips | snacks | none | none | none | gap | no tortilla chips emoji |
| Compost bags | household | none | none | none | n/a (non-food) | no compost bags emoji |
| Bin bags | household | none | none | none | n/a (non-food) | no bin bags emoji |
| Potato sticks | snacks | none | none | none | gap | no potato sticks emoji |
| Olive oil | pantry | none | none | none | gap | no olive oil emoji |
| Laundry rinse vinegar | household | none | none | none | n/a (non-food) | no laundry vinegar emoji |
| Sweet chili dip | condiments | none | none | none | gap | no chili dip emoji |
| Kitchen cleaning spray | household | none | none | none | n/a (non-food) | no cleaning spray emoji |
| All-purpose cleaner | household | none | none | none | n/a (non-food) | no cleaner emoji |
| Turkish yoghurt | dairy | none | none | none | gap | no yoghurt emoji |
| Multivitamin | household | none | 💊 borderline | borderline | n/a (non-food) | no vitamin emoji |
| Wheat flour | pantry | none | none | none | gap | no flour emoji |
| Sour cream | dairy | none | none | none | gap | no sour cream emoji |
| Margarine | dairy | none | none | borderline | gap | no margarine emoji |
| Whipping cream | dairy | none | none | none | gap | no whipping cream emoji |
| Viili | dairy | none | none | none | gap | no viili emoji |
| Buttermilk | dairy | none | none | none | gap | no buttermilk emoji |
| Skyr | dairy | none | none | none | gap | no skyr yogurt emoji |
| Cinnamon bun | bread | none | 🍞 borderline | none | gap | no cinnamon bun emoji |
| Sausage | meat | none | 🥩 borderline | none | gap | no sausage emoji |
| Sliced ham | meat | none | 🥩 borderline | none | gap | no ham emoji |
| Meatballs | meat | none | 🥩 borderline | none | gap | no meatballs emoji |
| Swede | produce | none | none | none | gap | no swede emoji |
| Leek | produce | none | none | none | gap | no leek emoji |
| Zucchini | produce | none | none | none | gap | no zucchini emoji |
| Dill | produce | none | 🌿 borderline | borderline | exact 🌿 | no dill emoji |
| Lingonberries | fruits | none | none | none | gap | no lingonberry emoji |
| Raspberries | fruits | none | none | none | gap | no raspberry emoji |
| Porridge oats | pantry | none | none | none | gap | no oats emoji |
| Sugar | pantry | none | none | none | gap | no sugar emoji |
| Tea | beverages | none | ☕ borderline | borderline | exact 🍵 | no tea emoji |
| Salty liquorice | snacks | none | 🍬 borderline | none | gap | no liquorice emoji |
| Instant noodles | pantry | none | none | borderline | exact 🍜 | no instant noodles emoji |
| Ketchup | condiments | none | none | none | gap | no ketchup emoji |
| Mustard | condiments | none | none | none | gap | no mustard emoji |
| Mayonnaise | condiments | none | none | none | gap | no mayonnaise emoji |
| Strawberry jam | condiments | none | none | none | gap | no jam emoji |
| Orange juice | beverages | none | none | none | gap | no orange juice emoji |
| Mineral water | beverages | none | none | none | gap | no water emoji |
| Cola | beverages | none | none | borderline | exact 🥤 | no cola emoji |
| Lasagne | ready_meals | none | 🍲 borderline | none | gap | no lasagne emoji |
| Liver casserole | ready_meals | none | 🍲 borderline | borderline | exact 🍲 | no liver casserole emoji |
| Toothpaste | household | none | none | none | n/a (non-food) | no toothpaste emoji |
| Shampoo | household | none | none | borderline | n/a (non-food) | no shampoo emoji |
| Laundry detergent | household | none | none | none | n/a (non-food) | no detergent emoji |
| Painkillers | household | none | 💊 borderline | borderline | n/a (non-food) | no painkiller emoji |
| Pickles | condiments | none | none | none | gap | no pickle emoji |

## Running it on the real catalog

The catalog lives in the homelab database, so the operator runs the script inside the API
container. It only reads:
- the queries run in a `SET TRANSACTION READ ONLY` transaction;
- the output goes to files in `/tmp`.

It uses the container's `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_TIMEOUT` and
`LLM_REASONING_STRENGTH`. Keep the default `low`.

0. **Get the script into the container first.** It exists in `kyokki-api` only after:
   1. this PR is merged to `main`;
   2. the image workflow (`.github/workflows/images.yml`) has published the new image to GHCR;
   3. the stack is re-pulled: Portainer → the stack → **Pull and redeploy** with *re-pull
      image* ticked (`docs/DEPLOY.md`).

   Before that, the command below fails with `ModuleNotFoundError: No module named
   'scripts.emoji_trial'`.
1. Portainer → *Containers* → the `kyokki-api` container (named `<stack>-kyokki-api-1`) →
   *Console* → connect with `/bin/sh`.
2. Run:
   ```sh
   python -m scripts.emoji_trial --from-db --out /tmp/emoji.md
   ```
   - It prints one line per batch of 20 (the default `--batch-size`). A batch took about 20 s
     on the gateway, so 500 products take about 8 minutes.
   - Each request may take up to `LLM_TIMEOUT` (`--timeout` overrides it).
   - `--limit 40` tries the first 40 products first.
   - The output files are rewritten after every batch. If the console closes, what finished is
     already in `/tmp/emoji.*`.
3. Read the result in the same console with `cat /tmp/emoji.md`, or copy it to the host. On
   the Docker host, run `docker cp <stack>-kyokki-api-1:/tmp/emoji.md .`, and the same for
   `/tmp/emoji.csv` and `/tmp/emoji.json`.
   - The Markdown file has the counts on top, then tables for *Exact*, *Borderline (operator
     ruling needed)*, *None* and any *Invalid* or *Missing* answers.
   - It ends with the *Gap list*: everything that is not `exact`, borderline included until it
     is ruled on.
   - The CSV has the columns `name, category, emoji, match, why` and opens in a spreadsheet for
     ticking off.
4. **Treat every `exact` as a proposal.** Against the ruled set, about 1 in 39 was a
   closest-match leak (2 of 78 food products, see
   [Errors](#errors-exact-answers-that-break-the-rule)). Expect many products the rulings make
   exact to come back `borderline`: the prompt still carries the old family-level definition.
5. **Ignore non-food rows.** The script does not skip them. The catalog should hold few,
   because non-food receipt lines are folded out on review and never become products, but any
   that are there need no icon (see [Not applicable](#not-applicable-non-food)).

`--names file.csv` runs the same check on a list (`name,category`, or one name per line; a
`name` header is skipped) without the database. That is how the trial here was run:
`--names docs/spikes/q18_exact_emoji/names.csv`.

## Recommendation for the build

Not implemented here.

1. **Storage:** add `product_master.emoji` (nullable text, one emoji from the reference list)
   and `product_master.emoji_match`, an enum with these values:
   - `exact`: from the curated table, or a model proposal a person confirmed;
   - `proposed`: the model's `exact` or `borderline`, not yet confirmed;
   - `none`: on the gap list;
   - `cook`: set by hand, never overwritten.

   The tile shows `emoji` only for `exact` and `cook`. Everything else shows the generated icon
   when one exists (the ComfyUI lane), and the category emoji until then.
2. **Deterministic first: a curated per-product table.**
   - The table maps a generic name to an emoji or none. It is **per product, not per family**:
     Gouda → 🧀 does not imply Mozzarella → 🧀.
   - Seed it with the 109 exact and 58 gap-list products here, which include both rounds of
     [operator rulings](#operator-rulings-2026-09-27). The gap-list rows carry their
     [icon briefs](#icon-briefs-from-the-operator) where the operator gave one.
   - Its rule for a new product is the operator's own: "It needs to be precise, so it doesn't
     require cognitive effort", decided per product by the operator, with the rulings here as
     the precedent. The planner's "as it looks when bought" gloss is not the rule; the
     operator's yes-rulings for dishes and drink vessels contradict it.
   - A new product's generic name is looked up in the table before any model call, so the
     common groceries never depend on the model.
3. **Model second:** for names the table does not know, ask the model at reasoning `low`,
   batched, as this script does, with the rulings as examples in the prompt in place of the
   old family-level definition. Store its `exact` answers as `proposed` and show them on a
   short review list: even at 0.97 precision they cannot go straight to the tile. A confirmed
   answer goes into the curated table, so the same generic name is never asked again.
4. **Skip non-food entirely.** The picker, the curated table and the ComfyUI gap list take food
   products only. Non-food lines are folded out on the review screen (the `non_food_name` list)
   and never reach the fridge, so they get no emoji and no generated icon. The operator: "I do
   not get why soap needs an emoji, it is not food." Drop the household emoji from the reference
   list when it moves under `app/`.
5. **Cook override:** the product edit sheet gets an emoji picker limited to the reference list
   (`scripts/emoji_food.json`, moved under `app/` but outside any `data/` folder, which
   `.gitignore` ignores), plus "no emoji".
   - Picking one sets `emoji_match = cook`.
   - The existing `icon_status = cleared` idea carries over: a product whose emoji the cook
     cleared is never proposed again.
6. **Version cutoff:** Emoji 15.1 is safe for iPadOS 17.4 or later. Once the kitchen iPad is
   known to run iPadOS 18.4 or later, regenerate the list with `--build-reference` and
   `--cutoff 16.0`. Go higher when its iPadOS renders Emoji 18 (🫝 pickle).

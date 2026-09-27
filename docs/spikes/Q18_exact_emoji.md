# Q18 spike: exact Apple emoji or none, and the gap list

**Round:** 2026-09-27-3 (C2) · **Backlog:** Q18 in `docs/TODO.md` (new direction of 2026-09-27)
· **Model:** `c2.muse-glimmer` on the homelab gateway, one request at a time

## Question

The operator's rule: a product tile shows an Apple emoji **only when an exact one exists**. The
closest match is never used. Every product without an exact emoji goes on a **gap list**, and a
ComfyUI pipeline will draw those later. Which products have an exact emoji, how reliably can the
model tell, and what is left for the gap list?

"Exact" means the emoji's CLDR short name names the same food as the product's generic name, at
the level a cook means it. So Broccoli → 🥦 "broccoli" is exact. Parsnip → 🥕 "carrot" is none.
Entrecôte → 🥩 "cut of meat" is borderline, and borderline goes to the operator.

## Answer

- **About half the products in a Finnish household basket have an exact emoji.** By my own
  ruling, 88 of the 191 names do. Another 49 are borderline and need an operator ruling (every
  specific cheese → 🧀, every fish → 🐟, rye bread → 🍞, herbs → 🌿 and so on). The last 54
  have nothing and go straight to the gap list: yoghurts, quark, the cream family, condiments,
  cleaning products and Finnish specialities.
- **The model is a good proposer but not a judge.** At reasoning `low` (the app's setting) it
  answered `exact` 85 times. 78 of those are right, so **precision is 0.92**. It found 78 of my
  88 exact products, so **recall is 0.89**. No exact answer named a different food. All 7 errors
  are the same kind: a generic or related emoji for a more specific product, such as Gouda → 🧀,
  Rainbow trout → 🐟, Red wine → 🍷 "wine glass" and Canned tomatoes → 🍅. The operator's rule
  forbids exactly that, so at this rate about **one displayed emoji in twelve would be a
  closest-match leak** if the answers were accepted unreviewed.
- **Reasoning `high` does not help.** Precision is about the same (0.93), recall is lower
  (0.86), it takes about 4.5 times longer (67–132 s a batch against 11–23 s) and it agrees with
  `low` on only 158 of 191 products. It trades some leaks for others: it gets Gouda and trout
  right, but calls Dish soap → 🧼 and Sparkling wine → 🍷 exact.
- **Recommendation for the build:** use a fixed exact table first and the model only for names
  the table does not know. The model's `exact` counts only after a person has confirmed it
  once. See [Recommendation](#recommendation-for-the-build).

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
- **Version cutoff: Emoji 15.1.** The iPad 8th gen runs iPadOS 17/18. Emoji 15.1 needs
  iPadOS 17.4 and Emoji 16.0 needs iPadOS 18.4, so 15.1 is the newest version every supported
  iPad renders once it is up to date. Three emoji fall above the cutoff and are listed in the
  JSON under `excluded_newer`: 🫜 root vegetable (16.0), 🪾 leafless tree (16.0) and
  **🫝 pickle (18.0)**. Pickle would make Pickles exact, so it is worth revisiting when the
  iPad reaches an iPadOS that renders Emoji 18. Kept 15.x entries that need iPadOS 17.4 or
  later: 🍋‍🟩 lime, 🍄‍🟫 brown mushroom (15.1), 🫚 ginger root, 🫛 pea pod and 🪻 hyacinth
  (15.0).
- **Picker:** `backend/scripts/emoji_trial.py`. It sends batches of 20 products, each with its
  category, together with the whole reference list (`emoji name` per line) and the binding
  definition with its examples. It asks for strict-schema JSON:
  `{"r": [{"i", "e": emoji|null, "m": "exact"|"borderline"|"none", "why"}]}`. The script
  checks every answer:
  - An emoji outside the reference list, or `exact`/`borderline` without an emoji, is
    `invalid`, and its emoji is dropped.
  - A `none` that still names an emoji keeps no emoji, so a closest match can never be stored.
  - An emoji missing its variation selector is mapped to the fully qualified form.
  - A product the model did not answer, or a batch whose request failed, is `missing`.

  None of the runs produced an invalid or missing answer.
- **Names:** 191 generic English names with a category:
  - the spike's 20 products (`backend/tests/fixtures/icon_spike/products.json`);
  - the lines of the four `backend/tests/fixtures/receipts/expected_*.json` files, rewritten as
    generic names (for example "PORKKANA 1KG" → Carrot, "Naudan Entrecote Palana" → Entrecôte)
    and assigned the seeded category ids;
  - about 110 common Finnish household groceries and household goods covering dairy, bread,
    meat, fish, vegetables, fruit, dry goods, condiments, drinks, ready meals and household
    items.

  Household goods have category `household`. There is no such seeded category; it only gives
  the model context. The names are the *Product* column of the table below.
- **Runs** (temperature 0.1, 20 products a request, one request at a time):

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
- **Precision check:** I ruled every product myself against the CLDR names, using the spec's
  examples as the bar. A generic emoji for a specific product (🧀 for Gouda, 🐟 for trout, 🥩
  for pork chops) is borderline, not exact. So is an emoji that shows a dish or a vessel rather
  than the product (🍚 "cooked rice" for a bag of rice, 🍝 for dry spaghetti, 🍷 "wine glass",
  🥫/🍅 for canned tomatoes). An `exact` answer counts as correct only when my ruling is exact
  with the same emoji. That ruling is the *My ruling* column below; where I am unsure, it says
  borderline.

## Precision and recall

| | Run 1 (`low`) | Run 2 (`high`) |
| --- | --- | --- |
| `exact` answers | 85 | 82 |
| correct | 78 | 76 |
| **precision** | **0.92** | **0.93** |
| my exact products found (of 88) | 78 | 76 |
| **recall** | **0.89** | **0.86** |
| an exact product answered `none` (lost silently) | 1 (Foam hand soap) | 1 (Frozen peas) |
| an exact product answered `borderline` (goes to the operator, not lost) | 9 | 11 |

### Errors: `exact` answers that break the rule

| Product | Answered | CLDR name | Why it is not exact | Run |
| --- | --- | --- | --- | --- |
| Gouda | 🧀 | cheese wedge | a specific cheese under the generic emoji | low |
| Rainbow trout | 🐟 | fish | a specific fish under the generic emoji | low |
| Rice | 🍚 | cooked rice | the product is dry rice; the emoji is a bowl of cooked rice | low |
| Whole chicken | 🐔 | chicken | the emoji is the live bird | low, high |
| Spaghetti | 🍝 | spaghetti | the emoji is a plated pasta dish, not dry pasta. A cook might accept it, so the operator should rule | low, high |
| Canned tomatoes | 🍅 | tomato | a processed product under the fresh vegetable | low, high |
| Red wine | 🍷 | wine glass | the name is a glass, not the wine | low, high |
| Dish soap | 🧼 | soap | washing-up liquid is not a bar of soap | high |
| Sparkling wine | 🍷 | wine glass | as Red wine; `low` gave 🍾 borderline | high |

### Misses: exact products the model did not call exact

- **Lost as `none`:** Foam hand soap → 🧼 soap (low) and Frozen peas → 🫛 pea pod (high).
- **Downgraded to `borderline`:** Liquid soap 🧼, Toast bread 🍞, Sweet corn 🌽 "ear of corn",
  Frozen peas 🫛, Kidney beans 🫘 "beans", Sweet potato 🍠 "roasted sweet potato", Mandarin 🍊
  "tangerine", Kitchen roll 🧻 and Cut flowers 💐 "bouquet" (low). `high` has most of these as
  well as Apple 🍎 "red apple", Chicken drumsticks 🍗 "poultry leg", Chili pepper 🌶️ "hot
  pepper", Toilet paper 🧻, Dish sponge 🧽, Lactose-free milk drink 🥛 and Milk chocolate with
  hazelnuts 🍫. These downgrades are safe: under the rule they reach the operator, not the
  tile. Several are also my own calls that the operator may overrule (🍊 is "tangerine",
  🍠 is "roasted").

## Full results

Grouped by the run 1 (`low`) answer. *High* is run 2's answer for the same product. *My
ruling* is the precision check. *Why* is the model's own reason, from run 1.

### Model said exact (85)

| Product | Category | Low | High | My ruling | Model's why (low) |
| --- | --- | --- | --- | --- | --- |
| Tomato | produce | 🍅 exact | 🍅 exact | exact 🍅 | emoji name is tomato |
| Banana | fruits | 🍌 exact | 🍌 exact | exact 🍌 | emoji name is banana |
| Carrot | produce | 🥕 exact | 🥕 exact | exact 🥕 | emoji name is carrot |
| Potato | produce | 🥔 exact | 🥔 exact | exact 🥔 | emoji name is potato |
| Cucumber | produce | 🥒 exact | 🥒 exact | exact 🥒 | emoji name is cucumber |
| Milk | dairy | 🥛 exact | 🥛 exact | exact 🥛 | example milk to glass of milk |
| Eggs | dairy | 🥚 exact | 🥚 exact | exact 🥚 | example eggs to egg |
| Butter | dairy | 🧈 exact | 🧈 exact | exact 🧈 | emoji name is butter |
| White bread | bread | 🍞 exact | 🍞 exact | exact 🍞 | white bread is bread |
| Apple | fruits | 🍎 exact | 🍎 borderline | exact 🍎 | apple is apple |
| Milk chocolate with hazelnuts | snacks | 🍫 exact | 🍫 borderline | exact 🍫 | milk chocolate is chocolate bar |
| Gouda | cheese | 🧀 exact | 🧀 borderline | borderline | gouda is cheese |
| Chocolate chip cookies | snacks | 🍪 exact | 🍪 exact | exact 🍪 | chocolate chip cookies are cookies |
| Chocolate ice cream | frozen | 🍨 exact | 🍨 exact | exact 🍨 | chocolate ice cream is ice cream |
| Grapes | fruits | 🍇 exact | 🍇 exact | exact 🍇 | grapes is grapes |
| Plum tomatoes | produce | 🍅 exact | 🍅 exact | exact 🍅 | plum tomatoes are tomato |
| Mini bell peppers | produce | 🫑 exact | 🫑 exact | exact 🫑 | mini bell peppers are bell pepper |
| Broccoli | produce | 🥦 exact | 🥦 exact | exact 🥦 | broccoli is broccoli |
| Lactose-free milk drink | dairy | 🥛 exact | 🥛 borderline | exact 🥛 | lactose free milk drink is milk |
| Mango | fruits | 🥭 exact | 🥭 exact | exact 🥭 | emoji name is mango |
| Bacon | meat | 🥓 exact | 🥓 exact | exact 🥓 | emoji name is bacon |
| Green apple | fruits | 🍏 exact | 🍏 exact | exact 🍏 | emoji name is green apple |
| Pear | fruits | 🍐 exact | 🍐 exact | exact 🍐 | emoji name is pear |
| Red onion | produce | 🧅 exact | 🧅 exact | exact 🧅 | red onion is onion |
| Lime | fruits | 🍋‍🟩 exact | 🍋‍🟩 exact | exact 🍋‍🟩 | lime is lime |
| Cherry tomatoes | produce | 🍅 exact | 🍅 exact | exact 🍅 | cherry tomatoes are tomatoes |
| Baguette | bread | 🥖 exact | 🥖 exact | exact 🥖 | baguette bread |
| Croissant | bread | 🥐 exact | 🥐 exact | exact 🥐 | croissant |
| Bagel | bread | 🥯 exact | 🥯 exact | exact 🥯 | bagel |
| Pretzel | bread | 🥨 exact | 🥨 exact | exact 🥨 | pretzel |
| Pancakes | frozen | 🥞 exact | 🥞 exact | exact 🥞 | pancakes |
| Whole chicken | meat | 🐔 exact | 🐔 exact | borderline | whole chicken |
| Chicken drumsticks | meat | 🍗 exact | 🍗 borderline | exact 🍗 | drumstick is poultry leg |
| Rainbow trout | fish | 🐟 exact | 🐟 borderline | borderline | trout is fish |
| Shrimp | fish | 🦐 exact | 🦐 exact | exact 🦐 | shrimp matches shrimp |
| Squid | fish | 🦑 exact | 🦑 exact | exact 🦑 | squid matches squid |
| Oysters | fish | 🦪 exact | 🦪 exact | exact 🦪 | oysters match oyster |
| Onion | produce | 🧅 exact | 🧅 exact | exact 🧅 | onion matches onion |
| Garlic | produce | 🧄 exact | 🧄 exact | exact 🧄 | garlic matches garlic |
| Bell pepper | produce | 🫑 exact | 🫑 exact | exact 🫑 | bell pepper matches bell pepper |
| Avocado | produce | 🥑 exact | 🥑 exact | exact 🥑 | avocado matches avocado |
| Mushrooms | produce | 🍄 exact | 🍄 exact | exact 🍄 | mushrooms match mushroom |
| Aubergine | produce | 🍆 exact | 🍆 exact | exact 🍆 | aubergine is eggplant |
| Ginger | produce | 🫚 exact | 🫚 exact | exact 🫚 | emoji is ginger root |
| Chili pepper | produce | 🌶️ exact | 🌶️ borderline | exact 🌶️ | emoji is hot pepper |
| Olives | condiments | 🫒 exact | 🫒 exact | exact 🫒 | emoji is olive |
| Lemon | fruits | 🍋 exact | 🍋 exact | exact 🍋 | emoji is lemon |
| Strawberries | fruits | 🍓 exact | 🍓 exact | exact 🍓 | emoji is strawberry |
| Blueberries | fruits | 🫐 exact | 🫐 exact | exact 🫐 | emoji is blueberries |
| Watermelon | fruits | 🍉 exact | 🍉 exact | exact 🍉 | emoji is watermelon |
| Melon | fruits | 🍈 exact | 🍈 exact | exact 🍈 | emoji is melon |
| Pineapple | fruits | 🍍 exact | 🍍 exact | exact 🍍 | emoji is pineapple |
| Kiwi | fruits | 🥝 exact | 🥝 exact | exact 🥝 | emoji is kiwi fruit |
| Peach | fruits | 🍑 exact | 🍑 exact | exact 🍑 | emoji is peach |
| Cherries | fruits | 🍒 exact | 🍒 exact | exact 🍒 | emoji is cherries |
| Coconut | fruits | 🥥 exact | 🥥 exact | exact 🥥 | emoji is coconut |
| Rice | pantry | 🍚 exact | 🍚 borderline | borderline | cooked rice matches rice |
| Spaghetti | pantry | 🍝 exact | 🍝 exact | borderline | spaghetti matches spaghetti |
| Salt | pantry | 🧂 exact | 🧂 exact | exact 🧂 | salt matches salt |
| Honey | pantry | 🍯 exact | 🍯 exact | exact 🍯 | honey pot names honey |
| Peanuts | snacks | 🥜 exact | 🥜 exact | exact 🥜 | peanuts matches peanuts |
| Chestnuts | snacks | 🌰 exact | 🌰 exact | exact 🌰 | chestnut matches chestnuts |
| Popcorn | snacks | 🍿 exact | 🍿 exact | exact 🍿 | popcorn matches popcorn |
| Chocolate bar | snacks | 🍫 exact | 🍫 exact | exact 🍫 | chocolate bar matches chocolate bar |
| Lollipop | snacks | 🍭 exact | 🍭 exact | exact 🍭 | lollipop matches lollipop |
| Canned tomatoes | pantry | 🍅 exact | 🍅 exact | borderline | tomato matches canned tomatoes |
| Beer | beverages | 🍺 exact | 🍺 exact | exact 🍺 | beer mug names beer |
| Red wine | beverages | 🍷 exact | 🍷 exact | borderline | wine glass names wine |
| Yerba mate | beverages | 🧉 exact | 🧉 exact | exact 🧉 | mate names yerba mate |
| Frozen pizza | frozen | 🍕 exact | 🍕 exact | exact 🍕 | pizza names pizza |
| Sushi | ready_meals | 🍣 exact | 🍣 exact | exact 🍣 | sushi names sushi |
| Dumplings | frozen | 🥟 exact | 🥟 exact | exact 🥟 | dumpling names dumplings |
| Falafel | ready_meals | 🧆 exact | 🧆 exact | exact 🧆 | falafel names falafel |
| Burrito | ready_meals | 🌯 exact | 🌯 exact | exact 🌯 | burrito names burrito |
| Hamburger | ready_meals | 🍔 exact | 🍔 exact | exact 🍔 | hamburger names hamburger |
| Ice cubes | frozen | 🧊 exact | 🧊 exact | exact 🧊 | ice names ice cubes |
| Doughnut | bread | 🍩 exact | 🍩 exact | exact 🍩 | doughnut names doughnut |
| Cupcake | bread | 🧁 exact | 🧁 exact | exact 🧁 | cupcake names cupcake |
| Toilet paper | household | 🧻 exact | 🧻 borderline | exact 🧻 | roll of paper names toilet paper |
| Toothbrush | household | 🪥 exact | 🪥 exact | exact 🪥 | toothbrush names toothbrush |
| Candles | household | 🕯️ exact | 🕯️ exact | exact 🕯️ | candle matches candles |
| Batteries | household | 🔋 exact | 🔋 exact | exact 🔋 | battery matches batteries |
| Dish sponge | household | 🧽 exact | 🧽 borderline | exact 🧽 | sponge matches dish sponge |
| Light bulb | household | 💡 exact | 💡 exact | exact 💡 | light bulb matches |
| Plasters | household | 🩹 exact | 🩹 exact | exact 🩹 | adhesive bandage is plaster |

### Model said borderline (41)

| Product | Category | Low | High | My ruling | Model's why (low) |
| --- | --- | --- | --- | --- | --- |
| Cheddar | cheese | 🧀 borderline | 🧀 borderline | borderline | cheddar is cheese, emoji is cheese wedge |
| Minced beef | meat | 🥩 borderline | none | borderline | minced beef is meat, emoji is cut of meat |
| Chicken fillet strips | meat | 🐔 borderline | 🐔 borderline | none | strips are chicken, emoji is chicken |
| Salmon | fish | 🐟 borderline | 🐟 borderline | borderline | salmon is fish, emoji is fish |
| Rye bread | bread | 🍞 borderline | 🍞 borderline | borderline | rye bread is bread, emoji is white loaf |
| Coffee | pantry | ☕ borderline | ☕ borderline | borderline | coffee is hot beverage, emoji is hot beverage |
| Entrecôte | meat | 🥩 borderline | 🥩 borderline | borderline | entrecôte is cut of meat |
| Feta | cheese | 🧀 borderline | 🧀 borderline | borderline | feta is a cheese, emoji is generic cheese wedge |
| Keisarinna cheese | cheese | 🧀 borderline | 🧀 borderline | borderline | keisarinna is a cheese, emoji is generic cheese wedge |
| Rye crispbread | bread | 🍞 borderline | 🍞 borderline | borderline | crispbread is bread, emoji is white loaf |
| Liquid soap | household | 🧼 borderline | 🧼 exact | exact 🧼 | liquid soap is soap, emoji is soap |
| Sponge cloth | household | 🧽 borderline | 🧽 borderline | borderline | sponge cloth is a sponge, emoji is sponge |
| Glögi | beverages | ☕ borderline | ☕ borderline | borderline | glögi is a hot beverage, emoji is generic |
| Lettuce | produce | 🥬 borderline | 🥬 borderline | borderline | lettuce is a leafy green |
| Tomato puree | pantry | 🍅 borderline | none | borderline | puree is tomato product |
| Mozzarella | cheese | 🧀 borderline | 🧀 borderline | borderline | mozzarella is cheese |
| Parsley | produce | 🌿 borderline | 🌿 borderline | borderline | parsley is an herb |
| Cottage cheese | cheese | 🧀 borderline | 🧀 borderline | borderline | cottage cheese is cheese |
| Emmental | cheese | 🧀 borderline | 🧀 borderline | borderline | emmental is cheese |
| Blue cheese | cheese | 🧀 borderline | 🧀 borderline | borderline | blue cheese is cheese |
| Pita bread | bread | 🫓 borderline | 🫓 borderline | borderline | pita is a flatbread |
| Tortilla wraps | bread | 🫓 borderline | 🫓 borderline | borderline | tortilla is a flatbread |
| Toast bread | bread | 🍞 borderline | 🍞 borderline | exact 🍞 | toast is bread |
| Hot dog sausages | meat | 🌭 borderline | 🌭 borderline | borderline | hot dog sausages is hot dog |
| Pork chops | meat | 🥩 borderline | 🍖 borderline | borderline | pork chop is cut of meat |
| Reindeer sauté | meat | 🥩 borderline | 🥩 borderline | borderline | reindeer is cut of meat |
| Baltic herring | fish | 🐟 borderline | 🐟 borderline | borderline | herring is a fish, emoji is generic fish |
| Pickled herring | fish | 🐟 borderline | 🐟 borderline | borderline | pickled herring is a fish, emoji is generic fish |
| Canned tuna | fish | 🐟 borderline | 🐟 borderline | borderline | tuna is a fish, emoji is generic fish |
| Fish fingers | frozen | 🐟 borderline | none | borderline | fish fingers are fish, emoji is generic fish |
| Sweet corn | produce | 🌽 borderline | 🌽 exact | exact 🌽 | sweet corn is corn, emoji is ear of corn |
| Chanterelles | produce | 🍄 borderline | 🍄 borderline | borderline | chanterelle is a mushroom, emoji is generic mushroom |
| Cabbage | produce | 🥬 borderline | 🥬 borderline | borderline | cabbage is leafy green, emoji is generic leafy green |
| Spinach | produce | 🥬 borderline | 🥬 borderline | borderline | spinach is leafy green, emoji is generic leafy green |
| Frozen peas | frozen | 🫛 borderline | none | exact 🫛 | emoji is pea pod not peas |
| Kidney beans | pantry | 🫘 borderline | 🫘 exact | exact 🫘 | emoji is beans generic |
| Sweet potato | produce | 🍠 borderline | 🍠 exact | exact 🍠 | emoji is roasted sweet potato |
| Mandarin | fruits | 🍊 borderline | 🍊 borderline | exact 🍊 | emoji is tangerine for mandarin |
| Sparkling wine | beverages | 🍾 borderline | 🍷 exact | borderline | bottle with popping cork for sparkling wine |
| Kitchen roll | household | 🧻 borderline | 🧻 borderline | exact 🧻 | roll of paper is generic for kitchen roll |
| Cut flowers | household | 💐 borderline | 💐 borderline | exact 💐 | bouquet is cut flowers, generic match |

### Model said none (65)

| Product | Category | Low | High | My ruling | Model's why (low) |
| --- | --- | --- | --- | --- | --- |
| Orange | fruits | none | none | borderline | emoji is tangerine not orange |
| Quark | dairy | none | none | none | no quark emoji |
| Karelian pasty | bread | none | none | none | no pasty emoji |
| Oat drink | beverages | none | none | none | no oat drink emoji |
| Apple juice | beverages | none | none | none | no apple juice emoji |
| Crisps | snacks | none | none | none | no crisps emoji |
| Drinking yoghurt | dairy | none | none | none | no yoghurt emoji |
| Dish soap | household | none | 🧼 exact | borderline | no dish soap emoji |
| Natural yoghurt | dairy | none | none | none | no yoghurt emoji |
| Parsnip | produce | none | none | none | parsnip no emoji carrot is carrot |
| Foam hand soap | household | none | 🧼 exact | exact 🧼 | no hand soap emoji |
| Tampons | household | none | none | none | no tampon emoji |
| Sauerkraut | produce | none | none | none | no sauerkraut emoji |
| Beetroot hummus | condiments | none | none | none | no hummus emoji |
| Apple sauce | condiments | none | none | none | no sauce emoji |
| Pomegranate | fruits | none | none | none | no pomegranate emoji |
| Taco sauce | condiments | none | none | none | no sauce emoji |
| Crème fraîche | dairy | none | none | none | no crème fraîche emoji |
| Tortilla chips | snacks | none | none | none | no tortilla chips emoji |
| Compost bags | household | none | none | none | no compost bags emoji |
| Bin bags | household | none | none | none | no bin bags emoji |
| Potato sticks | snacks | none | none | none | no potato sticks emoji |
| Olive oil | pantry | none | none | none | no olive oil emoji |
| Laundry rinse vinegar | household | none | none | none | no laundry vinegar emoji |
| Sweet chili dip | condiments | none | none | none | no chili dip emoji |
| Kitchen cleaning spray | household | none | none | none | no cleaning spray emoji |
| All-purpose cleaner | household | none | none | none | no cleaner emoji |
| Turkish yoghurt | dairy | none | none | none | no yoghurt emoji |
| Multivitamin | household | none | 💊 borderline | borderline | no vitamin emoji |
| Wheat flour | pantry | none | none | none | no flour emoji |
| Sour cream | dairy | none | none | none | no sour cream emoji |
| Margarine | dairy | none | none | borderline | no margarine emoji |
| Whipping cream | dairy | none | none | none | no whipping cream emoji |
| Viili | dairy | none | none | none | no viili emoji |
| Buttermilk | dairy | none | none | none | no buttermilk emoji |
| Skyr | dairy | none | none | none | no skyr yogurt emoji |
| Cinnamon bun | bread | none | 🍞 borderline | none | no cinnamon bun emoji |
| Sausage | meat | none | 🥩 borderline | none | no sausage emoji |
| Sliced ham | meat | none | 🥩 borderline | none | no ham emoji |
| Meatballs | meat | none | 🥩 borderline | none | no meatballs emoji |
| Swede | produce | none | none | none | no swede emoji |
| Leek | produce | none | none | none | no leek emoji |
| Zucchini | produce | none | none | none | no zucchini emoji |
| Dill | produce | none | 🌿 borderline | borderline | no dill emoji |
| Lingonberries | fruits | none | none | none | no lingonberry emoji |
| Raspberries | fruits | none | none | none | no raspberry emoji |
| Porridge oats | pantry | none | none | none | no oats emoji |
| Sugar | pantry | none | none | none | no sugar emoji |
| Tea | beverages | none | ☕ borderline | borderline | no tea emoji |
| Salty liquorice | snacks | none | 🍬 borderline | none | no liquorice emoji |
| Instant noodles | pantry | none | none | borderline | no instant noodles emoji |
| Ketchup | condiments | none | none | none | no ketchup emoji |
| Mustard | condiments | none | none | none | no mustard emoji |
| Mayonnaise | condiments | none | none | none | no mayonnaise emoji |
| Strawberry jam | condiments | none | none | none | no jam emoji |
| Orange juice | beverages | none | none | none | no orange juice emoji |
| Mineral water | beverages | none | none | none | no water emoji |
| Cola | beverages | none | none | borderline | no cola emoji |
| Lasagne | ready_meals | none | 🍲 borderline | none | no lasagne emoji |
| Liver casserole | ready_meals | none | 🍲 borderline | borderline | no liver casserole emoji |
| Toothpaste | household | none | none | none | no toothpaste emoji |
| Shampoo | household | none | none | borderline | no shampoo emoji |
| Laundry detergent | household | none | none | none | no detergent emoji |
| Painkillers | household | none | 💊 borderline | borderline | no painkiller emoji |
| Pickles | condiments | none | none | none | no pickle emoji |


## Gap list

These products need a generated icon. There are **54 by my ruling**, plus whichever of the 49
borderline products the operator rules out.

- **Dairy:** Quark, Drinking yoghurt, Natural yoghurt, Turkish yoghurt, Viili, Skyr, Buttermilk,
  Crème fraîche, Sour cream, Whipping cream
- **Bread and bakery:** Karelian pasty, Cinnamon bun
- **Meat:** Chicken fillet strips, Sausage, Sliced ham, Meatballs
- **Vegetables:** Parsnip, Swede, Leek, Zucchini, Sauerkraut
- **Fruit and berries:** Pomegranate, Lingonberries, Raspberries
- **Dry goods and pantry:** Wheat flour, Porridge oats, Sugar, Olive oil
- **Condiments and spreads:** Ketchup, Mustard, Mayonnaise, Strawberry jam, Apple sauce,
  Taco sauce, Sweet chili dip, Beetroot hummus, Pickles (🫝 pickle exists from Emoji 18.0,
  above the cutoff)
- **Drinks:** Oat drink, Apple juice, Orange juice, Mineral water
- **Snacks:** Crisps, Tortilla chips, Potato sticks, Salty liquorice
- **Ready meals:** Lasagne
- **Household:** Tampons, Compost bags, Bin bags, Laundry rinse vinegar, Kitchen cleaning
  spray, All-purpose cleaner, Laundry detergent, Toothpaste

## Borderline: operator rulings needed

Each row names the candidate emoji and the question. A "yes" makes it exact; a "no" puts it on
the gap list. Most rulings are really about a **family**, so eight rulings settle nearly all
49 rows:

| Family ruling | Products it settles | Candidate |
| --- | --- | --- |
| Does 🧀 "cheese wedge" stand for a named cheese? | Cheddar, Gouda, Feta, Mozzarella, Emmental, Blue cheese, Keisarinna cheese, Cottage cheese | 🧀 |
| Does 🐟 "fish" stand for a named fish, raw or processed? | Salmon, Rainbow trout, Baltic herring, Pickled herring, Canned tuna, Fish fingers | 🐟 |
| Does 🥩 "cut of meat" stand for a named cut or meat? | Entrecôte, Pork chops, Reindeer sauté, Minced beef | 🥩 |
| Does 🍞 "bread" (a white loaf) stand for other breads? | Rye bread, Rye crispbread | 🍞 |
| Does 🫓 "flatbread" stand for pita and tortilla? | Pita bread, Tortilla wraps | 🫓 |
| Does 🥬 "leafy green" / 🌿 "herb" stand for a named green or herb? | Lettuce, Cabbage, Spinach, Parsley, Dill | 🥬 🌿 |
| Does a drink vessel stand for the drink? | Coffee ☕ "hot beverage", Tea 🍵/☕, Glögi ☕, Red wine 🍷 "wine glass", Sparkling wine 🍾, Cola 🥤 "cup with straw" | ☕ 🍵 🍷 🍾 🥤 |
| Does a dish or processed form stand for the ingredient? | Rice 🍚 "cooked rice", Spaghetti 🍝, Instant noodles 🍜 "steaming bowl", Canned tomatoes 🍅, Tomato puree 🍅, Liver casserole 🍲 "pot of food", Hot dog sausages 🌭 "hot dog" | 🍚 🍝 🍜 🍅 🍲 🌭 |

Single rows:

| Product | Candidate | Question |
| --- | --- | --- |
| Orange | 🍊 tangerine | Is the tangerine emoji an orange? Apple's artwork looks like one. |
| Whole chicken | 🐔 chicken | The live bird, for a whole bird to roast |
| Chanterelles | 🍄 mushroom / 🍄‍🟫 brown mushroom | A named mushroom under the generic one |
| Margarine | 🧈 butter | Margarine is not butter |
| Dish soap | 🧼 soap | Washing-up liquid as a bar of soap |
| Sponge cloth | 🧽 sponge | A cloth (Wettex) as a sponge |
| Multivitamin, Painkillers | 💊 pill | Medicine by its form |
| Shampoo | 🧴 lotion bottle | A bottle of something else |

My ruling also takes the model's `exact` for these, which the operator may still want to see:
Mandarin 🍊 "tangerine", Sweet potato 🍠 "roasted sweet potato", Frozen peas 🫛 "pea pod",
Kidney beans 🫘 "beans", Sweet corn 🌽 "ear of corn", Kitchen roll / Toilet paper 🧻 "roll of
paper", Cut flowers 💐 "bouquet" and Foam hand soap / Liquid soap 🧼 "soap".

## Running it on the real catalog

The catalog lives in the homelab database, so the operator runs the script inside the API
container. It only reads: the queries run in a `SET TRANSACTION READ ONLY` transaction, and
the output goes to files in `/tmp`. It uses the container's `LLM_BASE_URL`, `LLM_MODEL` and
`LLM_REASONING_STRENGTH`. Keep the default `low`.

1. Portainer → *Containers* → the `kyokki-api` container (named `<stack>-kyokki-api-1`) →
   *Console* → connect with `/bin/sh`.
2. Run:
   ```sh
   python -m scripts.emoji_trial --from-db --out /tmp/emoji.md
   ```
   It prints one line per batch of 20. On the gateway a batch takes about 20 s, so 500
   products take about 8 minutes. Add `--batch-size 10` if a batch comes close to the 180 s
   `--timeout`.
3. Read the result in the same console with `cat /tmp/emoji.md`. Or copy it to the host (on
   the Docker host, `docker cp <stack>-kyokki-api-1:/tmp/emoji.md .`, and the same for
   `/tmp/emoji.csv` and `/tmp/emoji.json`). The Markdown file has the counts on top, then
   tables for *Exact*, *Borderline (operator ruling needed)*, *None* and any *Invalid* or
   *Missing* answers, and ends with the *Gap list*: everything that is not `exact`,
   borderline included until it is ruled on. The CSV has the columns `name, category, emoji,
   match, why` and opens in a spreadsheet for ticking off.
4. Treat every `exact` as a proposal: expect about one in twelve to be a closest-match leak
   of the kinds listed under [Errors](#errors-exact-answers-that-break-the-rule).

`--names file.csv` runs the same check on a list (`name,category`, or one name per line)
without the database.

## Recommendation for the build

Not implemented here.

1. **Storage:** add `product_master.emoji` (nullable text, one emoji from the reference list)
   and `product_master.emoji_match`, an enum with these values:
   - `exact`: the model proposed it and a person confirmed it;
   - `proposed`: the model's `exact` or `borderline`, not yet confirmed;
   - `none`: on the gap list;
   - `cook`: set by hand, never overwritten.

   The tile shows `emoji` only for `exact` and `cook`. Everything else shows the generated icon
   when one exists (the ComfyUI lane), and the category emoji until then.
2. **Deterministic first:** keep a curated table `generic name → emoji`, seeded from the 88
   exact products here plus the operator's family rulings. A new product's generic name is
   looked up there before any model call. With the table, the common groceries never depend on
   the model's 0.92 precision.
3. **Model second:** for names the table does not know, ask the model at reasoning `low`,
   batched, as this script does. Store `exact` answers as `proposed` and show them on a short
   review list, since at 0.92 they cannot go straight to the tile. A confirmed answer goes into
   the curated table, so the same generic name is never asked again.
4. **Cook override:** the product edit sheet gets an emoji picker limited to the reference list
   (`scripts/emoji_food.json`, moved under `app/` but outside any `data/` folder, which
   `.gitignore` ignores), plus "no emoji". Picking one sets
   `emoji_match = cook`. The existing `icon_status = cleared` idea carries over: a product
   whose emoji the cook cleared is never proposed again.
5. **Version cutoff:** keep the reference list at Emoji 15.1 while the iPad might be below
   iPadOS 18.4. Regenerate it with `--build-reference` and a higher `--cutoff` once the iPad's
   iPadOS version is known to render Emoji 16/18 (🫝 pickle).

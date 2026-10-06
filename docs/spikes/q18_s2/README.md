# Q18-S2 icon style spike: can generated icons match the emoji catalog?

Backlog item: `docs/TODO.md` **Q18-S2** (operator-approved 2026-10-06). The operator called the
generated icons "ugly and lazy" next to the Apple emoji catalog; "red bell pepper" came out as a
blank red silhouette. This spike renders the same 12 products at the same 2 seeds in today's
setup and in two candidate setups, so the operator can compare them side by side. It does not
pick a winner.

- Contact sheets (rows = products, columns = S0 | S1 | S2; each cell is the 256 px icon with its
  64 px copy beside it): [seed 20261006](contact_sheet_seed20261006.png),
  [seed 20261007](contact_sheet_seed20261007.png)
- IP-Adapter weight sensitivity (S1 | S2 at 0.6 | S2 at 0.8, first three products):
  [seed 20261006](sensitivity_seed20261006.png), [seed 20261007](sensitivity_seed20261007.png)
- Every render at 256 px and 64 px: [`icons/`](icons/), named `<product>_<setup>_<seed>_<size>.png`
  (setup `s0`, `s1`, `s2`, or `s2w06` for S2 at weight 0.6). Full-size 1024 px renders were kept
  in a scratch directory and are not committed.
- Per-render prompts, weights and timings: [`renders.json`](renders.json)
- Style board used as the S2 reference: [`style_board.png`](style_board.png), nine Microsoft
  Fluent Emoji 3D food images (MIT); sources and licence in
  [`LICENSE-fluent-emoji.md`](LICENSE-fluent-emoji.md). No Apple emoji image was used.

## How it was rendered

`backend/scripts/icon_style_spike.py` (run from `backend/`):

```
python -m scripts.icon_style_spike board --source-dir <scratch>/fluent
python -m scripts.icon_style_spike render --full-dir <scratch>/full
python -m scripts.icon_style_spike sheets      # rebuild the sheets from icons/
```

Every graph is `app.services.icon_workflow.build_icon_workflow(...)`'s output, adjusted in the
script only (no production module changed). Subjects come from
`app.services.product_icons.icon_subject(name)` exactly as production calls it (no cook hint).
All jobs went through `app.services.comfyui.render` (hold protocol, one job at a time) against
`a4.comfyui` via the gateway, 2026-10-06. `/comfyui-hold/status` was checked before each
product's batch and was clear every time. The style board was uploaded once with
`comfyui.upload_image` (stored as `kyokki_q18_s2_style_board.png`).

Fixed for all setups (from `build_icon_workflow`): `sd_xl_base_1.0.safetensors`,
`SDXL-Emoji-Lora-r4.safetensors`, 1024x1024, batch 1, `dpmpp_2m`/`karras`, cfg 7.0, 25 steps,
BiRefNet `General.safetensors` cut-out. Seeds: **20261006** and **20261007**, the same across
every setup.

### Setups

| | LoRA trigger, strength | Positive prompt | Negative prompt | IP-Adapter |
| --- | --- | --- | --- | --- |
| **S0 today** | `flat`, 0.75 | `flat, {subject}, simple flat icon, white background` | `NEGATIVE_PROMPT` | none |
| **S1 prompt** | `emoji`, 0.4 | `emoji, {subject}, glossy 3D emoji icon, soft gradient shading, highlight, full colour, detailed, white background` | `NEGATIVE_PROMPT` + `, silhouette, monochrome, outline, line art, lineart, flat colour, blank, sketch` | none |
| **S2 prompt + style** | as S1 | as S1 | as S1 | style board; `IPAdapterUnifiedLoader` preset `PLUS (high strength)`; `IPAdapterAdvanced` weight **0.8**, weight_type **`style transfer`**, combine `concat`, start 0.0, end 1.0, embeds scaling `V only` |
| S2 at 0.6 | as S1 | as S1 | as S1 | as S2, weight **0.6** (first three products only) |

`NEGATIVE_PROMPT` = `blurry, text, watermark, face, eyes, mouth, smile, cartoon character,
mascot, anthropomorphic`.

`style transfer` is what `GET /object_info/IPAdapterAdvanced` on a4 listed among its weight types
(`linear, ease in, ease out, ease in-out, reverse in-out, weak input, weak output, weak middle,
strong middle, style transfer, composition, strong style transfer, style and composition, style
transfer precise, composition precise`).

### Subjects (from `icon_subject`)

| Product | Subject text sent |
| --- | --- |
| Red bell pepper | Red bell pepper |
| Quark | Quark, a tub of smooth white soft cheese with a spoon in it |
| Tomato puree | Tomato puree, a small can or squeeze out tube |
| Fish fingers | Fish fingers, "should look as they should": the fish fingers, or their pack, as sold |
| Canned tuna | Canned tuna, "should look as they should": the tuna can as sold |
| Karelian pasty | Karelian pasty, oval rye pastry, scalloped crimped edge, rice filling showing |
| Leek | Leek, a single pale green and white leek with roots trimmed |
| Mineral water | Mineral water, clear liquid in a plastic bottle with blue label |
| Oat drink | Oat drink, tall carton of pale beige oat beverage with a straw cap |
| Rye bread | Rye bread |
| Cottage cheese | Cottage cheese, small white curds in a white plastic tub with lid |
| Hot dog sausages | Hot dog sausages, plump pink sausages in a vacuum sealed plastic pack |

The ten products the assignment named, plus Cottage cheese and Hot dog sausages from the Q18
subjects gap list (`docs/spikes/q18_subjects/README.md`).

## Timings and failures

78 renders (12 products x 2 seeds x 3 setups, plus 3 products x 2 seeds at S2 weight 0.6),
**78/78 ok, no failures**, 2028 s wall clock for the whole run including the hold checks.

| Setup | Renders | Min | Median | Max |
| --- | --- | --- | --- | --- |
| S0 | 24 | 24.1 s | 24.9 s | 40.2 s (first job, cold start) |
| S1 | 24 | 24.2 s | 25.1 s | 31.0 s |
| S2 (0.8) | 24 | 23.3 s | 24.7 s | 28.8 s |
| S2 (0.6) | 6 | 22.9 s | 24.7 s | 24.8 s |

The IP-Adapter adds no measurable render time once loaded. Per-render times are in
`renders.json`.

## Observations per product

"Tiling" means the image is a repeating pattern of many small objects instead of one centred
icon (the failure earlier trials saw). "Face" means a face, eyes or a smile appears despite the
negative prompt. Seeds are abbreviated `…06` and `…07`.

| Product | S0 today | S1 prompt | S2 prompt + style |
| --- | --- | --- | --- |
| Red bell pepper | …06: tiled field of flat **red silhouettes** (the operator's complaint, reproduced). …07: one flat pepper with odd white blotches; legible at 64 px. No faces. | Both seeds tiled: many glossy, shaded, detailed peppers. Much more volume, but not one icon; at 64 px a red speckle. No faces. | Both seeds tiled, and the reference pulls in other foods and colours (yellow/green/blue peppers, apples, bread-like shapes). Off-subject; illegible at 64 px. No faces. |
| Quark | Both: flat white tub with spoon; clean, legible at 64 px. | Both: one glossy white bowl with spoon, soft shading and highlights; on-subject, legible at 64 px. No faces. | Both: one pastel object, but it reads as a dessert (strawberry, layered cake cup, extra fruit). At 0.6, …07 gained a **face**. |
| Tomato puree | …06: red bottle/drop symbol; …07: jar with a tomato label. Both single and legible. | Both tiled: fields of fresh tomatoes; the can/tube brief is lost. | Both tiled mixes of tomatoes, cans, bottles in pastel; at 0.6, …06 has **faces** on two items. Illegible at 64 px. |
| Fish fingers | Both tiled (flat orange sticks). | Both tiled (glossy sticks, more detail). | Both tiled, pastel; …06 drifts to literal fish. |
| Canned tuna | …06: one can with garbled label text; …07: line-art fish with a big cartoon eye over a can lid (character-like). | Both tiled: rainbow-coloured cans. | Both tiled pastel mixes, no recognisable can. |
| Karelian pasty | Both: one oval pastry with crimped edge, flat; legible at 64 px. | Both tiled: detailed, shaded pastries. | Both tiled pastel shapes (…06 candy-like, …07 one hot-dog-like centrepiece among blobs). Off-subject. |
| Leek | …06: sparse leaves with a bulb; …07: grass-like tuft. Thin at 64 px. | Both: one leek, 3D shaded, detailed; …06 reads more like spring onion. Legible at 64 px. No faces. | Both: one stylised leek-like shape in rainbow/pastel colours; wrong colours. |
| Mineral water | Both: one clean flat bottle; legible at 64 px. | Both: one glossy bottle with an emoji **face** on it. | …06: pink bottle surrounded by smiley **faces**; …07: bottle with a **face**. |
| Oat drink | Both: one flat beige carton/bottle; legible but low-detail at 64 px. | Both: a cup of oats with a **face**. | …06: one pastel cup with straw, no face; …07: cup with a **face**. |
| Rye bread | …06: one loaf in outline; …07: tiled bread slices. | Both tiled: glossy bread rolls and loaves. | Both tiled pastel mixes. |
| Cottage cheese | Both: one tub of curds; legible at 64 px. | …06: tub with a **face**; …07: glossy bowl of curds, no face, legible. | Both: one pastel tub; …06 label reads as a face with moustache, …07 has face-like cut-outs. |
| Hot dog sausages | …06: three sausages, one group; …07: tiled. | Both tiled. | Both tiled pastel mixes. |

### Totals (24 renders per setup)

| | S0 | S1 | S2 (0.8) |
| --- | --- | --- | --- |
| Tiled / not one icon | 5 | 14 | 14 |
| Face or character visible | 1 (Canned tuna …07, fish eye) | 5 | 5 |
| One object (on-subject or not) | 19 | 10 | 10 |
| One object that also keeps the subject's own colours | 19 | 10 | ~0 (pastel or wrong colours throughout) |
| Silhouette | 1 (Red bell pepper …06) | 0 | 0 |

These counts are one reader's judgement from the sheets, not a measurement tool.

## Reading the result (not a decision)

- **Closest to the catalog look, where it works: S1.** Where S1 produces a single object (Quark,
  Leek, Cottage cheese …07) it has what the Apple/Fluent catalog has and S0 lacks: full colour,
  soft gradient shading, highlights and volume. The S1 negative terms did remove the flat
  silhouettes.
- **But S1 breaks composition and the no-faces rule.** It tiled 14 of 24 renders (S0 tiled 5),
  including products S0 draws as one clean icon (Tomato puree, Karelian pasty), and the `emoji`
  trigger brings back emoji faces on containers (Mineral water, Oat drink, Cottage cheese) even
  though the negative prompt excludes faces. That is the same behaviour the 2026-09-30 trial saw
  and the reason for the "Flat. No faces" ruling.
- **S2 (style transfer from the Fluent board) does not help here.** It carries the board's
  palette and plastic pastel finish, but also its *content*: other foods and colours appear
  (yellow and blue peppers, cheese, bread, fruit next to quark), subjects drift (fish fingers to
  fish, pasty to candy), tiling stays as bad as S1, and faces still appear. Weight 0.6 versus 0.8
  changes little: 0.6 is slightly closer to S1 and still shows faces and tiling.
- **S0 stays the most legible at 64 px** and the most reliably single-object, but it is flat and
  low-detail, which is the operator's complaint.

None of the three setups gives "S0's composition with S1's rendering" on this evidence. The
tiling and the faces look tied to the `emoji` trigger and the long style prompt rather than to the
reference image. If the operator wants a follow-up, options the evidence points at (not tried
here) are S1's prompt with the `flat` trigger, or a single-object composition term on S1 only;
both would need their own measured spike under the "keep the template change only if it helps"
rule.

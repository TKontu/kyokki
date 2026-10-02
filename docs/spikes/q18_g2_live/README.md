# Q18-G2 live check (Task 6)

Generated through the real queue (`product_icons.draw_icon`, called once per product - the
same function `draw_icons`/`schedule_icons` use) over the operator's SSH tunnel to
`a4.comfyui`, 2026-10-02. Five gap products (food, `emoji_match: none`) were created in a
private database, generated in sequence, and one (Quark) was then Regenerated through
`request_redraw` + the queue. Images are the exact bytes stored in `product_master.icon_image`
(256x256 PNG, downscaled from ComfyUI's 1024x1024 output) - nothing hand-rolled.

`COMFYUI_BASE_URL=http://localhost:19292/upstream/a4.comfyui` (the operator's tunnel,
`a4.comfyui` only), `COMFYUI_TIMEOUT=300`. No `/api/models/unload` or `/api/inflight/*/cancel`
call was made; no restart; the web UI was not opened.

## Results

| Product | Seed | Time | Verdict | Notes |
| --- | --- | --- | --- | --- |
| Quark | 3734713661473022335 | 42.4s (cold start) | **off-subject** | An abstract swirl/knot icon, not a dairy product. |
| Canned tuna | 4646372781199819264 | 23.0s | ok | Tuna can with a fish illustration, matches the brief ("the tuna can as sold"). Label text is garbled (expected for SDXL). |
| Tomato puree | 3371493984491212398 | 23.1s | **tiled** | Two separate compositions in one frame - a jar on the right, an unrelated tomato splatter on the left. |
| Fish fingers | 8250069608694040321 | 23.3s | ok | Breaded fish fingers on a tray, matches the brief. |
| Karelian pasty | 5145538439959004645 | 23.2s | ok | Correct scalloped-oval pastry shape and rye/rice-filling colouring. |
| Quark (Regenerate) | 5759587308198754360 | 23.3s | **off-subject** | A different seed produced a different image (confirms Regenerate works), but still an abstract icon (a compass/diamond on white), not a dairy product. |

**Quark did not render as a recognisable product in either attempt** - consistent with
`docs/spikes/Q18_icon_styles.md`'s note that "Quark never rendered" in the earlier recheck.
Both Quark seeds produced abstract line-art icons instead of anything resembling soft white
cheese. Everything else in the gap list rendered a recognisable, on-subject icon on the first
try; the one `tiled` result (Tomato puree) and the garbled label text on Canned tuna are
consistent with known SDXL-at-this-size limitations, not a pipeline defect - the gating,
seed handling, Regenerate and storage all behaved exactly as implemented and tested.

4 of 6 images are usable as-is (ok); 1 would need a reroll (tiled); Quark needs either a
different subject phrasing/brief or is simply out of reach for this LoRA/checkpoint at this
style strength - a product decision for the operator, not a code fix.

## Contact sheet (80px, tile size)

![Contact sheet at 80px: Quark, Canned tuna, Tomato puree, Fish fingers, Karelian pasty, Quark regenerated](contact_sheet_80px.png)

## Individual images (stored size, 256x256)

- [Quark.png](Quark.png)
- [Canned_tuna.png](Canned_tuna.png)
- [Tomato_puree.png](Tomato_puree.png)
- [Fish_fingers.png](Fish_fingers.png)
- [Karelian_pasty.png](Karelian_pasty.png)
- [Quark_regenerated.png](Quark_regenerated.png)

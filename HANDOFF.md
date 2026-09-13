# Handoff
Generated-UTC: 2026-09-13T23:30:00Z
Base-SHA: f397f3f

## Round delta
- #27 MVP-S1 merged: inventory responses carry product name/category/icon, Decimal fields are
  JSON numbers (DEC-2), inactive items hidden by default, `consumption_log` written on consume
  and discard. DEC-1 ruled `dl | tsp | tbsp | g | pcs`.
- MVP-C1 on `feat/mvp-c1-bottomsheet-toast` (PR open): `components/ui/BottomSheet.tsx`,
  `components/ui/Toast.tsx` (`ToastProvider`), `hooks/useToast.ts`, provider mounted in
  `app/providers.tsx`, demo sections on `/components-demo`.

## Active PRs and conflicts
- MVP-C1 PR. Touches `app/providers.tsx`, `tailwind.config.ts`, `components/ui/index.ts` and
  the demo page; no other open work touches them.
- Worktree `C:/code/Kyokki-docs` still holds merged `docs/mvp-plan-review-amendments`; removable.
- `HANDOFF.md` stays git-tracked by project practice; do not `git rm` it casually.

## Non-obvious decisions or blockers
- Bottom sheet entrance is a CSS keyframe on purpose. A `requestAnimationFrame`-driven
  transition left the sheet stuck off-screen whenever the tab was hidden (Chrome pauses rAF);
  a PWA resuming on the iPad can hit the same. Regression test in `BottomSheet.test.tsx`.
- The Next dev server does not pick up `tailwind.config.ts` changes; restart it.
- Toasts use a solid surface with coloured border/text, not Badge's translucent tints.
- Toast actions dismiss the toast after running; C2's Undo should call the reverse mutation.
- PR titles must start with a bare `feat:` / `fix:` / `docs:`; `feat(scope):` fails the check,
  and editing the title does not re-run it (close and reopen the PR).
- DEC-1 left ml, l and kg out; confirm conversion factors before R1.
- Local backend tests: 3.12 venv, `docker compose up -d postgres redis`, move root `.env` aside,
  `KYOKKI_TEST_REQUIRE_DB=1`. Check alembic drift against a throwaway DB.
- CRLF: most frontend `components/ui`, `app/providers.tsx`, `tailwind.config.ts` are CRLF in git.
- Operator items still open: rotate Postgres password + LLM key, purge `stack.env` history,
  deploy F2 on the homelab and confirm the iPad renders inventory, run the R0 spike.

## Next action
Operator merges the C1 PR. Then MVP-C2 (ConsumptionSheet on the new BottomSheet and toasts) and
MVP-S4 (item edit sheet) can start; S2 and S3 are unblocked too (S1 and C1 both done). R1 still
waits on the R0 spike, DEC-4, and the DEC-1 conversion follow-up.

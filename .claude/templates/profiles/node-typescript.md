# Profile: Node + TypeScript

Node 20+, TypeScript, ESLint, Prettier, Vitest. Adjust the runner rows for Jest, or the package
manager rows for pnpm/yarn/bun.

## Project Commands

Paste into the `claude:commands` table in `CLAUDE.md`:

```
| install   | npm ci |
| test      | npm test |
| test-one  | npx vitest run {arg} |
| lint      | npx eslint . |
| lint-fix  | npx eslint . --fix |
| format    | npx prettier --write . |
| typecheck | npx tsc --noEmit |
| run       | npm run dev |
| build     | npm run build |
```

## Toolchain config

```jsonc
// package.json (scripts)
{
  "scripts": {
    "dev": "tsx watch src/index.ts",
    "build": "tsc -p tsconfig.build.json",
    "test": "vitest run",
    "test:watch": "vitest",
    "lint": "eslint .",
    "typecheck": "tsc --noEmit"
  }
}
```

```jsonc
// tsconfig.json — the settings that matter
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "noEmit": true
  }
}
```

## Code style

- `strict: true` is not negotiable. `any` requires a comment saying why; prefer `unknown` plus a
  narrowing check.
- Prettier owns formatting — never hand-format around it.
- Prefer `type` for unions and object shapes, `interface` for something meant to be extended.
- Named exports; a default export only where a framework demands one.

**Naming:** `camelCase` variables/functions · `PascalCase` types, classes, components ·
`SCREAMING_SNAKE_CASE` module-level constants · files `kebab-case.ts`.

**Imports** — node builtins, external, internal alias, relative; enforced by
`import/order` or `eslint-plugin-simple-import-sort`:

```ts
import { readFile } from "node:fs/promises";

import { z } from "zod";

import { config } from "@/core/config";

import { UserService } from "./user-service";
```

**Docs** — TSDoc on exported symbols; the types carry the rest:

```ts
/**
 * Process items and return frequency counts.
 *
 * @param items - Strings to process.
 * @param limit - Maximum entries to return.
 * @throws {ValidationError} If `items` is empty.
 */
export function processData(items: string[], limit = 10): Record<string, number> {}
```

## Patterns

**Validate at the boundary** — parse external input into a typed value once, then trust the type:

```ts
import { z } from "zod";

const CreateUser = z.object({ name: z.string().min(1), email: z.string().email() });
export type CreateUser = z.infer<typeof CreateUser>;

export async function createUser(raw: unknown): Promise<User> {
  const input = CreateUser.parse(raw);   // throws ZodError at the edge
  return repo.insert(input);
}
```

**Route handler** (Express-shaped; adapt to Fastify/Hono/Nest):

```ts
router.get("/users/:id", async (req, res, next) => {
  try {
    const user = await userService.get(Number(req.params.id));
    if (!user) throw new NotFoundError("User not found");
    res.json(user);
  } catch (err) {
    next(err);
  }
});
```

**Dependency injection** — constructor injection, wired once at composition root:

```ts
export class UserService {
  constructor(
    private readonly db: Database,
    private readonly cache: Cache,
  ) {}
}
```

**Configuration** — parse `process.env` once into a frozen typed object; never read `process.env`
deep in the code, never hardcode secrets.

## Errors and logging

```ts
export class AppError extends Error {
  constructor(
    message: string,
    readonly code = "INTERNAL_ERROR",
    readonly status = 500,
  ) {
    super(message);
    this.name = new.target.name;
  }
}

export class ValidationError extends AppError {
  constructor(message: string) { super(message, "VALIDATION_ERROR", 422); }
}
export class NotFoundError extends AppError {
  constructor(message: string) { super(message, "NOT_FOUND", 404); }
}
```

- Never swallow an error with an empty `catch`.
- Preserve the chain: `throw new ServiceUnavailableError("...", { cause: err })`.
- Convert library errors to domain errors at the boundary.

Structured logging (pino):

```ts
logger.info({ userId: user.id, email: user.email }, "user_created");
logger.error({ orderId: order.id, err }, "payment_failed");
```

## Testing

```ts
// src/user-service.test.ts
import { describe, expect, it, vi, beforeEach } from "vitest";

describe("UserService.get", () => {
  it("returns the user when it exists", async () => {
    const service = new UserService(fakeDb({ 1: { id: 1 } }), fakeCache());
    await expect(service.get(1)).resolves.toMatchObject({ id: 1 });
  });

  it("returns null when it does not", async () => {
    const service = new UserService(fakeDb({}), fakeCache());
    await expect(service.get(999)).resolves.toBeNull();
  });
});
```

- One behaviour per `it`. Name it after the behaviour, not the method.
- Build fixtures with factory functions taking overrides — not shared mutable objects.
- Fake at the boundary you own (the repository), not at `fetch`, where possible.

## Debugging

- `node --inspect-brk` plus the editor debugger, or `debugger;` under `tsx`
- `npx vitest run -t "name"` — one test by name
- `npx vitest --reporter=verbose` — see each case
- `npx tsc --noEmit --pretty` — full type errors without a build

## Settings

Merge into `.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          { "type": "command", "command": "npx prettier --write \"$CLAUDE_FILE_PATH\" || true" },
          { "type": "command", "command": "npx eslint --fix \"$CLAUDE_FILE_PATH\" || true" }
        ]
      }
    ]
  },
  "permissions": {
    "allow": [
      "Bash(npm test:*)",
      "Bash(npm run:*)",
      "Bash(npm ci)",
      "Bash(npm ls:*)",
      "Bash(npx vitest:*)",
      "Bash(npx jest:*)",
      "Bash(npx eslint:*)",
      "Bash(npx prettier:*)",
      "Bash(npx tsc:*)",
      "Bash(pnpm test:*)",
      "Bash(pnpm run:*)",
      "Bash(yarn test:*)"
    ]
  }
}
```

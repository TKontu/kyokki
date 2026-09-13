# Profile: Go

Go 1.22+, standard toolchain, `golangci-lint`, table-driven tests.

## Project Commands

Paste into the `claude:commands` table in `CLAUDE.md`:

```
| install   | go mod download |
| test      | go test ./... |
| test-one  | go test -run {arg} ./... -v |
| lint      | golangci-lint run |
| lint-fix  | golangci-lint run --fix |
| format    | gofmt -w . |
| typecheck | go vet ./... |
| run       | go run ./cmd/server |
| build     | go build -o bin/server ./cmd/server |
```

`go build` and `go vet` already type-check; `typecheck` maps to `go vet` because it catches the
next tier of mistakes.

## Toolchain config

```yaml
# .golangci.yml
linters:
  enable:
    - errcheck      # unchecked errors
    - govet
    - staticcheck
    - revive
    - ineffassign
    - errorlint     # correct errors.Is/As usage
    - bodyclose
issues:
  exclude-rules:
    - path: _test\.go
      linters: [errcheck]
```

## Repository layout

```
cmd/<binary>/main.go     entry points — wiring only, no logic
internal/                everything not meant to be imported externally
pkg/                     only if you truly export a library
```

Put code in `internal/` by default. `pkg/` is a promise of API stability.

## Code style

- `gofmt` is the whole formatting debate. Never argue with it.
- **Accept interfaces, return structs.** Define the interface where it is *consumed*, not where it
  is implemented, and keep it to the methods that consumer needs.
- Keep the happy path at the left margin — handle the error and return early.
- No naked returns outside very short functions.
- Zero values should be useful; avoid constructors that only set defaults.

**Naming:** `MixedCaps`, never underscores · exported identifiers start upper · short receiver
names (`s *Server`) · no `Get` prefix on getters (`user.Name()`, not `user.GetName()`) · package
names are short, lowercase, and not `util` or `common`.

## Patterns

**Constructor injection at the composition root:**

```go
type UserService struct {
    db    Database
    cache Cache
}

func NewUserService(db Database, cache Cache) *UserService {
    return &UserService{db: db, cache: cache}
}
```

**Handler** (`net/http`; adapt to chi/echo/gin):

```go
func (s *Server) handleGetUser(w http.ResponseWriter, r *http.Request) {
    id, err := strconv.Atoi(r.PathValue("id"))
    if err != nil {
        s.respondError(w, r, fmt.Errorf("%w: id must be an integer", ErrValidation))
        return
    }

    user, err := s.users.Get(r.Context(), id)
    if err != nil {
        s.respondError(w, r, err)
        return
    }
    s.respondJSON(w, http.StatusOK, user)
}
```

**Context** — first parameter, always named `ctx`, never stored in a struct. Every call that can
block takes one and honours cancellation.

**Configuration** — read the environment once at startup into a struct, validate it there, and
fail fast. Never read the environment deep in the call graph; never hardcode secrets.

## Errors

Sentinel errors plus wrapping — the idiomatic equivalent of an exception hierarchy:

```go
var (
    ErrNotFound   = errors.New("not found")
    ErrValidation = errors.New("validation failed")
    ErrConflict   = errors.New("conflict")
)

func (s *UserService) Get(ctx context.Context, id int) (*User, error) {
    user, err := s.db.FindUser(ctx, id)
    if errors.Is(err, sql.ErrNoRows) {
        return nil, fmt.Errorf("user %d: %w", id, ErrNotFound)
    }
    if err != nil {
        return nil, fmt.Errorf("find user %d: %w", id, err)
    }
    return user, nil
}
```

- Always `%w` when wrapping; test with `errors.Is` / `errors.As`, never string comparison.
- Add context when wrapping, and do not repeat what the caller already knows. No "failed to" —
  the fact that it is an error is already established.
- Convert driver and library errors into sentinels at the boundary, so callers never import the
  driver to check an error.
- `panic` only for programmer errors that cannot be recovered; never across a package boundary.

## Logging

`log/slog`, structured, one event name plus fields:

```go
logger.Info("user_created", "user_id", user.ID, "email", user.Email)
logger.Error("payment_failed", "order_id", order.ID, "err", err)
```

Log an error once, at the layer that decides what to do about it — wrapping and returning is not
logging.

## Testing

Table-driven, with subtests:

```go
func TestUserService_Get(t *testing.T) {
    tests := []struct {
        name    string
        id      int
        want    *User
        wantErr error
    }{
        {name: "returns user when it exists", id: 1, want: &User{ID: 1}},
        {name: "reports not found", id: 999, wantErr: ErrNotFound},
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            t.Parallel()
            svc := NewUserService(fakeDB(t), fakeCache(t))

            got, err := svc.Get(context.Background(), tt.id)
            if !errors.Is(err, tt.wantErr) {
                t.Fatalf("err = %v, want %v", err, tt.wantErr)
            }
            if diff := cmp.Diff(tt.want, got); diff != "" {
                t.Errorf("mismatch (-want +got):\n%s", diff)
            }
        })
    }
}
```

- `t.Helper()` in every assertion helper; `t.Cleanup` over `defer` for fixtures.
- `-race` in CI, always.
- `go test ./... -run TestX -count=1` to defeat the test cache when chasing a flake.

## Debugging

- `dlv test ./internal/users -- -test.run TestUserService_Get`
- `go test ./... -race` — data races
- `go test -run TestX -count=1 -v` — bypass the cache
- `go test -bench=. -benchmem` — allocations per op
- `go build -gcflags="-m"` — escape analysis

## Settings

Merge into `.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          { "type": "command", "command": "gofmt -w \"$CLAUDE_FILE_PATH\" || true" }
        ]
      }
    ]
  },
  "permissions": {
    "allow": [
      "Bash(go test:*)",
      "Bash(go build:*)",
      "Bash(go vet:*)",
      "Bash(go run:*)",
      "Bash(go mod:*)",
      "Bash(go list:*)",
      "Bash(gofmt:*)",
      "Bash(golangci-lint run:*)"
    ]
  }
}
```

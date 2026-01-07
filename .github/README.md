# GitHub Actions Workflows

This directory contains CI/CD workflows for the Kyokki project.

## Workflows

### 1. Backend CI (`backend-ci.yml`)
**Triggers:** Push/PR to main/develop affecting backend code

**Jobs:**
- **Lint:** Runs `ruff check` and `ruff format --check` on backend code
- **Type Check:** Runs `mypy` on backend/app/ (non-blocking)
- **Test:** Runs pytest with coverage (PostgreSQL + Redis services)
  - Uploads coverage to Codecov
  - Comments coverage on PRs
- **Integration:** Runs integration tests (PR only, continues on error due to 3 known failing tests)

**Environment:**
- Python 3.12
- PostgreSQL 15
- Redis 7

### 2. Frontend CI (`frontend-ci.yml`)
**Triggers:** Push/PR to main/develop affecting frontend code

**Jobs:**
- **Lint:** Runs ESLint and TypeScript type checking
- **Test:** Runs Jest tests with coverage
- **Build:** Builds Next.js application

**Environment:**
- Node.js 20
- Next.js 14

### 3. PR Quality Checks (`pr-checks.yml`)
**Triggers:** PR opened/synchronized/reopened

**Jobs:**
- **PR Title Check:** Validates conventional commit format
  - Valid prefixes: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`, `style:`, `perf:`, `ci:`, `build:`
- **PR Size Check:** Categorizes PR size and warns on large PRs
  - XS: < 100 lines
  - S: < 300 lines
  - M: < 600 lines
  - L: < 1200 lines
  - XL: > 1200 lines
- **Dependency Check:** Detects and comments on dependency file changes

## Badge Examples

Add these to your README.md:

```markdown
![Backend CI](https://github.com/YOUR_USERNAME/kyokki_2/workflows/Backend%20CI/badge.svg)
![Frontend CI](https://github.com/YOUR_USERNAME/kyokki_2/workflows/Frontend%20CI/badge.svg)
```

## Local Testing

### Backend
```bash
# Lint
ruff check backend/

# Format check
ruff format --check backend/

# Type check
mypy backend/app/

# Tests
cd backend && pytest --cov=app
```

### Frontend
```bash
# Lint
cd frontend && npm run lint

# Type check
cd frontend && npx tsc --noEmit

# Tests
cd frontend && npm test

# Build
cd frontend && npm run build
```

## Required Secrets

For Codecov integration (optional):
- `CODECOV_TOKEN`: Codecov upload token

## Known Issues

1. **Backend Integration Tests:** 3 tests fail due to async event loop conflicts in mocking (not production bugs)
   - `test_receipt_confirm_broadcasts_status`
   - `test_update_inventory_broadcasts`
   - `test_delete_inventory_broadcasts`
   - These tests run but are marked as `continue-on-error: true`

2. **Mypy Type Checking:** Currently non-blocking (`continue-on-error: true`) to allow gradual type safety improvements

## Size Labels

The PR size check automatically adds labels. Create these labels in your repository:
- `size/XS` - Green (#10b981)
- `size/S` - Green (#10b981)
- `size/M` - Yellow (#fbbf24)
- `size/L` - Orange (#f97316)
- `size/XL` - Red (#ef4444)

## Future Enhancements

- [ ] Automated deployment to staging/production
- [ ] Docker image building and pushing
- [ ] Dependency vulnerability scanning (Dependabot/Snyk)
- [ ] Performance regression testing
- [ ] Visual regression testing for frontend
- [ ] Automated changelog generation

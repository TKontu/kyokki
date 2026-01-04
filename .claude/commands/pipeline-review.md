# Pipeline Review

Review an endpoint's pipeline end-to-end. Argument: endpoint path (e.g., "/users/{id}" or "POST /orders").

## Instructions

Trace the full request lifecycle through every layer:

### 1. Route Layer
- Find the route handler matching the endpoint
- Review path/query parameters, request body validation
- Check authentication/authorization dependencies

### 2. Dependencies
- Map all `Depends()` injections
- Trace each dependency's initialization
- Identify shared state, connections, caches

### 3. Service Layer
- Follow business logic step-by-step
- Review input validation and transformations
- Check error handling and edge cases

### 4. Data Layer
- Review database queries/ORM operations
- Check external API calls, timeouts, retries
- Verify transaction boundaries

### 5. Response
- Validate response model matches actual return
- Check error responses and status codes

## For Each Step, Identify:

- **🔴 Errors**: Will cause failures (exceptions, missing handling, type mismatches)
- **🟠 Bugs**: Incorrect behavior (wrong logic, race conditions, data loss)
- **🟡 Issues**: Problems under certain conditions (edge cases, performance)

## Output

Create `endpoint_{name}_review.md` with:

```markdown
# Pipeline Review: {endpoint}

## Summary
[1-2 sentence overview of findings]

## Pipeline Trace
[Mermaid flowchart or numbered steps showing the flow]

## Findings

### Critical (must fix)
- [ ] File:line - Description

### Important (should fix)
- [ ] File:line - Description

### Minor (nice to fix)
- [ ] File:line - Description

## Recommendations
[Prioritized action items]
```

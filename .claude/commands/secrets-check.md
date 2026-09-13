# Secrets Check

Scan staged changes for credentials before they enter history.

## Context

```bash
git diff --cached --name-only
```

## Scan

Check the **staged content**, not the working tree — that is what is about to be committed:

```bash
git diff --cached -U0 | grep -inE "(api[_-]?key|secret|passwd|password|pwd|token|bearer|credential|private[_-]?key|AKIA[0-9A-Z]{16}|BEGIN [A-Z ]*PRIVATE KEY|xox[baprs]-|gh[pousr]_[A-Za-z0-9]{16,}|eyJ[A-Za-z0-9_-]{10,}\.)" || true
```

Then check for connection strings carrying inline credentials:

```bash
git diff --cached -U0 | grep -inE "[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@" || true
```

And for env files that should never be committed:

```bash
git diff --cached --name-only | grep -iE "(^|/)\.env($|\.)|\.pem$|\.p12$|\.pfx$|id_(rsa|dsa|ecdsa|ed25519)$|\.keystore$" || true
```

## Judge each hit

A grep hit is a candidate, not a finding. Read the line and classify it:

- **Real** — a live-looking value assigned to a credential name.
- **Placeholder** — `your-api-key-here`, `xxx`, `changeme`, an obvious example value, or a line in
  `.env.example` / a test fixture / documentation.
- **Not a secret** — a variable name, a type, a config *key* with no value, a function called
  `get_token`.

Report only the real ones, plus anything genuinely ambiguous, marked as ambiguous. Padding the
report with placeholder matches trains the user to ignore it.

Also flag a **high-entropy literal** — a long random-looking string assigned to a constant — even
when its name looks innocent.

## Output

If secrets found:

```
🔴 SECRETS DETECTED — do not commit

file.py:23   API key assigned to `api_key`
config.ts:5  Hardcoded database password in connection string

Remediation:
1. Remove the value from the file; read it from the environment instead
2. Add the file to .gitignore if it should never be tracked
3. Treat the credential as compromised and rotate it — it existed on disk
4. If it is already committed, rewriting history is not enough on a shared remote: rotate
```

If clean:

```
✅ No secrets detected in staged changes (N files scanned)
```

This scan is a safety net, not a guarantee. Say so — it cannot see an obfuscated or encoded secret.

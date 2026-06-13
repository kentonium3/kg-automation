# Quickstart: OpenClaw Auth Verifier

**Mission**: `openclaw-auth-verifier-01KV0Y9E`
**Source issue**: kentonium3/kg-automation#597

For Kent and future agents who need to verify or repair OpenClaw's Anthropic auth substrate from the Mac.

---

## When to run

- After an OpenClaw upgrade on office2 (e.g., 2026.6.5 → 2026.6.6).
- After an Anthropic key rotation.
- When sub-agent cron jobs start failing with `authentication_error: invalid x-api-key` (matches the #596 incident pattern).
- As a sanity check before starting a substantive Felix mission that depends on LLM-driven crons.

## Canonical invocation (Mac terminal)

```bash
ssh office2-claude /home/claude/kg-automation/scripts/security/anthropic-verify.sh --check
```

**Expected green output** (under 30 seconds):

```
==> anthropic-verify --check
==> agents: 6 discovered (main, felix-admin-capture, -habits, -escalation, -tasker, -calendar)
ok    main                      auth_profile_store=1 auth_profile_state=1 sha8=75b3d6c3
ok    felix-admin-capture       auth_profile_store=0 auth_profile_state=0 (inherits main)
ok    felix-admin-habits        auth_profile_store=0 auth_profile_state=0 (inherits main)
ok    felix-admin-escalation    auth_profile_store=0 auth_profile_state=0 (inherits main)
ok    felix-admin-tasker        auth_profile_store=0 auth_profile_state=0 (inherits main)
ok    felix-admin-calendar      auth_profile_store=0 auth_profile_state=0 (inherits main)
ok    plaintext-file            sha8=75b3d6c3 (matches main)
ok    anthropic-ping            HTTP 200 model=claude-haiku-4-5-20251001
==> verify result: green (exit 0) in 3.2s
```

Exit code 0 means all clear.

## Common findings and remediation flows

### Shadow row on a sub-agent (exit 2)

```
FIND  shadow felix-admin-capture: auth_profile_store=1 auth_profile_state=1
```

Remediate:

```bash
ssh office2-claude /home/claude/kg-automation/scripts/security/anthropic-verify.sh --repair
ssh office2-claude 'systemctl --user restart openclaw-gateway.service'
ssh office2-claude /home/claude/kg-automation/scripts/security/anthropic-verify.sh --check
```

The repair backs up the affected SQLite store before clearing the rows. Backup lives at:

```
/home/claude/.openclaw/agents/<sub-agent>/agent/openclaw-agent.sqlite.pre-repair.<unix-ts>.bak
```

### Drift between plaintext file and main SQLite (exit 3)

```
FIND  drift plaintext-file vs main SQLite
      plaintext_sha8=aab12cd3  sqlite_sha8=75b3d6c3
```

Remediate (same `--repair` command — it dispatches by finding type):

```bash
ssh office2-claude /home/claude/kg-automation/scripts/security/anthropic-verify.sh --repair
ssh office2-claude /home/claude/kg-automation/scripts/security/anthropic-verify.sh --check
```

Repair atomically rewrites the plaintext file from main SQLite (no gateway restart needed; consumers — `felix-doc-auditor-driver`, `felix-heartbeat-gate` — re-read on their next tick).

### Anthropic rejected (exit 4)

```
FIND  anthropic_rejected
      http_status=401
```

The key in `main` SQLite was rotated upstream or revoked. Full rotation required:

```bash
ssh -t office2-claude /home/claude/kg-automation/scripts/security/anthropic-rotate.sh
```

The rotation script will invoke `anthropic-verify --check` at the end as a fail-closed gate.

### Network failure (exit 5)

```
FIND  network
      error_class=URLError
```

Transient — retry after network connectivity is restored. The plaintext file and SQLite state were not changed.

### Substrate gap (exit 6)

```
FIND  main_empty       # OR
FIND  plaintext_missing
```

Rotation invariant is broken. Run the full rotation:

```bash
ssh -t office2-claude /home/claude/kg-automation/scripts/security/anthropic-rotate.sh
```

## Integration with anthropic-rotate.sh

`anthropic-rotate.sh` invokes `anthropic-verify --check` as the final step. If verify fails post-rotation:

```
==> ROTATION VERIFY FAILED (exit 2 after rotation).
==> Rotation artifacts ARE in place but verifier flagged a finding above.
==> ... EITHER remediate forward ... OR roll back this rotation:

    /home/claude/kg-automation/scripts/security/anthropic-rotate.sh --rollback 1734106823
```

The rollback path is operator-driven (not auto). Read the finding first; in most cases (e.g., a pre-existing shadow row that the rotation didn't create), the right move is `--repair` not rollback.

## What this verifier does NOT do

- Does not call `openclaw doctor --fix` (that path is what plants shadow rows in the first place).
- Does not restart `openclaw-gateway.service` automatically (operator decides; verifier prints the command after `--repair` clears shadow rows).
- Does not print the actual Anthropic API key value anywhere — output is sha256-prefix fingerprints only.
- Does not ping Anthropic per sub-agent (only the canonical key resident in main SQLite + plaintext file).
- Does not handle Google OAuth (`gog`) or other credential types — Anthropic only.
- Does not run on a schedule. Operator-triggered + rotation-script-invoked only.

## Source

- Helper: `scripts/security/anthropic-verify.sh` + `scripts/security/anthropic_verify/` package
- Tests: `tests/security/test_anthropic_verify_*.py`
- Runbook detail: `docs/runbooks/openclaw-ops.md` § _Known upgrade gotchas_
- Related: `scripts/security/anthropic-rotate.sh` (rotation), `docs/runbooks/credential-rotation-ops.md` (rotation procedure)
- Origin: #596 incident write-up; #597 hardening follow-up

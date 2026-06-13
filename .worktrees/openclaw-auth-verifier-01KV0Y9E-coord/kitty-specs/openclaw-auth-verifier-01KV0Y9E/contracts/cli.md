# Contract: CLI Surface for `anthropic-verify.sh`

**Mission**: `openclaw-auth-verifier-01KV0Y9E`

Defines the operator-facing CLI of `scripts/security/anthropic-verify.sh` and the integration contract with `anthropic-rotate.sh`.

---

## Invocation

```bash
# Operator from Mac
ssh office2-claude /home/claude/kg-automation/scripts/security/anthropic-verify.sh [--check | --repair]

# From inside anthropic-rotate.sh (lifecycle integration)
/home/claude/kg-automation/scripts/security/anthropic-verify.sh --check
```

## Modes

| Flag | Mode | Read/Write | Default? |
|---|---|---|---|
| `--check` | Detection | read-only across all paths | Yes (when no flag passed) |
| `--repair` | Mutation | reads same paths; writes the affected sub-agent SQLite or plaintext file; always writes `.pre-repair.<ts>.bak` first | No |
| `-h`, `--help` | Help | none | n/a |

Exactly one of `--check` or `--repair` may be passed. Passing both is an error (exit code 2 with usage hint).

## Exit codes

Strictly per spec FR-011. Tested by `tests/security/test_anthropic_verify_core.py`.

| Exit | Meaning | Conditions |
|---|---|---|
| 0 | Green | All sub-agents healthy + plaintext sha matches main SQLite sha + Anthropic ping returned HTTP 200 |
| 1 | Unexpected error | Uncaught exception; usage error; permission denied on a required path |
| 2 | Shadow detected | At least one sub-agent has non-zero `auth_profile_store` or `auth_profile_state` rows |
| 3 | Drift detected | Plaintext sha != main SQLite sha |
| 4 | Anthropic rejected | API ping returned HTTP 4xx (typically 401) |
| 5 | Network failure | API ping failed at connect/TLS/DNS layer; no HTTP status received |
| 6 | Substrate gap | `main_empty` OR `plaintext_missing` |

Multiple findings can be present in a single run; in that case the exit code is the **lowest non-zero finding** in priority order (substrate gaps > network > anthropic_rejected > shadow > drift), so the operator sees the most foundational failure first.

## Stdout format

One line per finding (NFR-002), prefixed with finding type. Plus a final summary line.

### Green example

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

### Shadow example

```
==> anthropic-verify --check
==> agents: 6 discovered
ok    main                      auth_profile_store=1 auth_profile_state=1 sha8=75b3d6c3
FIND  shadow felix-admin-capture: auth_profile_store=1 auth_profile_state=1 last_update_ms=1781364272035
      sqlite_path=/home/claude/.openclaw/agents/felix-admin-capture/agent/openclaw-agent.sqlite
      suggested_action: anthropic-verify --repair  (clears per-agent rows; restart gateway afterward)
ok    felix-admin-habits        auth_profile_store=0 auth_profile_state=0 (inherits main)
ok    felix-admin-escalation    auth_profile_store=0 auth_profile_state=0 (inherits main)
ok    felix-admin-tasker        auth_profile_store=0 auth_profile_state=0 (inherits main)
ok    felix-admin-calendar      auth_profile_store=0 auth_profile_state=0 (inherits main)
ok    plaintext-file            sha8=75b3d6c3 (matches main)
ok    anthropic-ping            HTTP 200 model=claude-haiku-4-5-20251001
==> verify result: shadow detected (exit 2) in 3.4s
```

### Drift example

```
FIND  drift plaintext-file vs main SQLite
      plaintext_sha8=aab12cd3  sqlite_sha8=75b3d6c3
      plaintext_path=/data/services/openclaw/secrets/anthropic
      sqlite_path=/home/claude/.openclaw/agents/main/agent/openclaw-agent.sqlite
      suggested_action: anthropic-verify --repair  (rewrites plaintext from main SQLite, atomic)
==> verify result: drift detected (exit 3) in 3.1s
```

### Anthropic-rejected example

```
FIND  anthropic_rejected
      http_status=401  response_summary=Authentication error: invalid x-api-key
      suggested_action: anthropic-rotate.sh  (key was revoked or rotated upstream; full rotation required)
==> verify result: anthropic rejected (exit 4) in 2.8s
```

### Network-failure example

```
FIND  network
      error_class=URLError  error_message=<urlopen error [Errno -2] Name or service not known>
      suggested_action: retry anthropic-verify --check after network connectivity restored
==> verify result: network failure (exit 5) in 5.1s
```

## Stderr format

Reserved for unexpected errors (exit 1 only). Findings always emit on stdout. The verifier never writes to stderr in normal operation.

## Repair-mode output

`--repair` is a no-op when `--check` would have been green. When a finding exists, repair prints what it's doing:

```
==> anthropic-verify --repair
==> agents: 6 discovered
ok    main                      auth_profile_store=1 auth_profile_state=1 sha8=75b3d6c3
FIND  shadow felix-admin-capture: auth_profile_store=1 auth_profile_state=1
==> REPAIR shadow felix-admin-capture
      backup: /home/claude/.openclaw/agents/felix-admin-capture/agent/openclaw-agent.sqlite.pre-repair.1734106823.bak
      DELETE FROM auth_profile_store  (1 row)
      DELETE FROM auth_profile_state  (1 row)
      done.
==> Next: systemctl --user restart openclaw-gateway.service
==> Then re-run: anthropic-verify --check
==> repair result: shadow row(s) cleared (exit 0) in 3.5s
```

## Integration contract: `anthropic-rotate.sh` invocation

After Step 5 (existing inbox-7am liveness probe) succeeds, `anthropic-rotate.sh` adds:

```bash
echo "==> Step 6: anthropic-verify --check (fail-closed gate)..."
if ! /home/claude/kg-automation/scripts/security/anthropic-verify.sh --check; then
  VERIFY_EXIT=$?
  cat <<EOF >&2

==> ROTATION VERIFY FAILED (exit $VERIFY_EXIT after rotation).
==> Rotation artifacts ARE in place but verifier flagged a finding above.
==> Inspect the finding(s), then EITHER remediate forward (e.g., anthropic-verify --repair if shadow)
==> OR roll back this rotation:

    /home/claude/kg-automation/scripts/security/anthropic-rotate.sh --rollback ${ROTATION_TS}

==> The rollback restores the plaintext file, openclaw.json, and the SQLite import-bak
==> from the per-step backups recorded at rotation start.
EOF
  exit $VERIFY_EXIT
fi
echo "  verify: green"
```

Where `ROTATION_TS` is the unix timestamp from the rotation's manifest (set at rotation start).

## Rollback contract: `anthropic-rotate.sh --rollback <ts>`

```bash
ssh office2-claude /home/claude/kg-automation/scripts/security/anthropic-rotate.sh --rollback 1734106823
```

Reads `~/.cache/anthropic-rotate/manifest.<ts>.json`, validates all three backup paths exist, restores them in this order:

1. `openclaw.json.bak` → `~/.openclaw/openclaw.json` (atomic rename)
2. SQLite `auth-profiles.json.sqlite-import.<ts>.bak` → triggers `openclaw doctor --fix --non-interactive` to re-import from the restored file
3. `plaintext.pre-rotate.<ts>.bak` → `/data/services/openclaw/secrets/anthropic` (atomic rename, mode 0600)

Then restarts `openclaw-gateway.service` and reports the result. If any backup is missing, refuses to roll back partially and exits 1 with the missing-paths list.

## Environment variables consumed

NONE. The verifier reads no environment variables. (`SPEC_KITTY_*` and other host-environment variables are irrelevant here.)

## Environment variables produced

NONE. The verifier writes no environment variables to subsequent process output.

---
title: felix-bot Vikunja Provisioning
doc_type: runbook
status: approved
audience: operator
last_updated: '2026-05-17'
---

# felix-bot Vikunja Provisioning

Operator-facing procedural runbook for ADR-0002 Phase 1 (issue
[#304](https://github.com/kentonium3/kg-automation/issues/304)).
Sequences the four mission helpers (`provision_felix_bot.py`,
`validate_felix_bot.py`, `swap_vikunja_secrets.py`,
`revoke_kent_tokens.py`) and the four architecture-doc updates into a
six-phase execution arc with explicit GO/NO-GO criteria at every phase
boundary.

The companion one-page quick reference is
[quickstart.md](../../kitty-specs/felix-bot-vikunja-provisioning-01KRT3N4/quickstart.md);
this runbook is the full procedural document.

**Mission**: `felix-bot-vikunja-provisioning-01KRT3N4`
**Risk tier**: 2 (application/state — Restic snapshot required)
**Total operator time**: 30-60 minutes spread across two sessions
(Phases 1-4 in one session; Phase 6 after the 7-day soak)
**Total wall-clock**: 7+ days end-to-end (dominated by the soak)

---

## How to use this runbook

Read each phase top-to-bottom in order. At every phase boundary there is
a **GO criteria** checklist — every box must be checked before the next
phase starts. If a NO-GO trigger fires, follow the inline rollback
direction; do not improvise.

Phases 1, 2, 3, and 6 run on office2 (`ssh office2-claude`). Phase 4
runs on the Mac (this repo's worktree). Phase 5 is passive monitoring
performed daily during the soak; commands run on office2.

Each helper's full `--help` is the authoritative reference for flags;
this runbook documents the invocations specific to this mission.

---

## Pre-flight (5 minutes)

**Estimated duration**: 5 minutes.

Required conditions before Phase 1 starts. All three must be true.

### Commands

```bash
# 1. Confirm a Restic snapshot exists within the last 24 hours
ssh office2-claude 'sudo restic snapshots --latest 1 || tail -5 /data/services/backup/logs/backup-$(date -u +%Y-%m-%d).log'
```

(Restic snapshot files are root-owned mode 400; if `sudo` is not
available to the session, use the log-file path on the right-hand side
of the `||`. Either confirms the same fact: a snapshot completed in the
last 24 hours.)

```bash
# 2. Confirm openclaw-gateway is healthy and Vikunja is reachable
ssh office2-claude 'systemctl --user is-active openclaw-gateway.service'
ssh office2-claude 'curl -sS -o /dev/null -w "%{http_code}\n" http://100.92.197.90:3456/api/v1/info'
```

```bash
# 3. Confirm kent's existing API token is present and mode 600
ssh office2-claude 'stat -c "%a %U:%G %n" /data/services/openclaw/secrets/vikunja-api'
```

Expected: `600 claude:claude /data/services/openclaw/secrets/vikunja-api`.

### GO criteria

- [ ] Restic snapshot within last 24 hours confirmed (per
  [`change-risk-taxonomy.json`](../design/architecture/data/change-risk-taxonomy.json)
  Tier 2 protocol and [pre-flight-checklist.md](governance/pre-flight-checklist.md))
- [ ] `systemctl --user is-active openclaw-gateway.service` returns `active`
- [ ] Vikunja `/api/v1/info` returns HTTP 200
- [ ] kent's secrets file present at canonical path with mode 600
- [ ] Operator has 30+ minutes of focused availability for Phases 1-4
- [ ] 1Password is open and reachable for password copy/paste

### NO-GO

If any pre-flight check fails, **STOP**. Resolve before proceeding:

- No recent Restic snapshot → trigger a manual backup:
  `ssh office2-claude '/data/services/backup/scripts/backup.sh'` and
  re-check.
- Gateway not active → investigate via `journalctl --user -u openclaw-gateway.service --since '1 hour ago'`.
- Vikunja unreachable → check `systemctl status vikunja` (via kgale).
- Wrong mode or owner on the secrets file → do not touch; halt and
  diagnose. The identity gate inside each helper will refuse to run
  anyway.

---

## Phase 1 — Provision felix-bot (5-10 minutes)

**Spec coverage**: FR-001, FR-002, FR-003, NFR-005, C-004.
**Helper**: `scripts/vikunja/provision_felix_bot.py` (WP01).

Registers the `felix-bot` Vikunja user, enumerates the 12 real projects
(IDs 1, 2, 4-13), shares each one with felix-bot at read/write
(`right=1`), and captures the operator-supplied API token to a
mode-600 file.

### Preparation

1. Generate a strong felix-bot password in 1Password (32+ chars,
   alphanumeric + symbols). Save the entry as `felix-bot (Vikunja)`
   with the email `kentgale+felix-bot@gmail.com`.
2. Decide where the captured token will be written. The default
   recommendation is a tmpfs-backed path so the token never hits a
   persistent disk before the WP03 swap:
   `--token-output-file /run/user/$(id -u)/felix-bot-token`.

### Command

```bash
ssh office2-claude
cd /home/claude/kg-automation
python3 scripts/vikunja/provision_felix_bot.py \
    --username felix-bot \
    --email kentgale+felix-bot@gmail.com \
    --password-from-stdin \
    --kent-token-file /data/services/openclaw/secrets/vikunja-api \
    --token-output-file /run/user/$(id -u)/felix-bot-token
```

Stdin protocol (the helper prompts the operator before each read):

1. **First line**: paste felix-bot's password from 1Password.
2. The helper registers the user, enumerates and shares the 12
   projects, then pauses with an instruction to generate an API token
   for `felix-bot` via the Vikunja UI
   (`https://office2.tail0f5f56.ts.net/` → log in as felix-bot →
   Settings → API tokens → create token with read/write scope).
3. **Second line**: paste the freshly-generated felix-bot API token.

The helper sets mode 600 on `--token-output-file` **before** the
descriptor closes — there is no permission-window race.

### Expected output

Per-project log lines while shares apply, followed by a final summary:

```
SUMMARY: felix-bot registered (uid=<N>), 12 projects shared, token captured to /run/user/<UID>/felix-bot-token
```

Exit code 0.

### GO criteria

- [ ] Exit code 0
- [ ] `SUMMARY:` line is present and matches the format above
- [ ] `uid=<N>` is a positive integer (the new felix-bot user ID)
- [ ] 12 projects shared (count matches the SUMMARY line)
- [ ] Token output file exists, owned by `claude:claude`, mode 600
  (verify: `stat -c "%a %U:%G" /run/user/$(id -u)/felix-bot-token`)

### NO-GO / rollback trigger

- Registration fails (HTTP 4xx): inspect the error, fix the input
  (most likely a username/email collision with an existing account),
  re-run.
- Fewer than 12 shares applied: do NOT proceed to Phase 2. Investigate
  per-project. Production state is untouched — kent's secrets file is
  unmodified.
- Token capture fails (empty stdin, wrong mode after write): delete
  the felix-bot user (via the Vikunja UI, log in as kent → admin) and
  restart Phase 1. No production state has been mutated.

---

## Phase 2 — Validate felix-bot (5 minutes)

**Spec coverage**: FR-004, FR-015, NFR-001, AS-008.
**Helper**: `scripts/vikunja/validate_felix_bot.py` (WP02).

Side-channel validation. Exercises the new token directly (NOT via the
production secrets file). Confirms all 12 projects are readable with
the new token, writes a throwaway task + comment, asserts
`created_by.username == felix-bot`, then cleans up. Also runs a
symbolic rollback smoke test that validates the recovery path will
complete inside the NFR-003 5-minute budget.

### Command — primary validation

```bash
python3 scripts/vikunja/validate_felix_bot.py \
    --token-file /run/user/$(id -u)/felix-bot-token \
    --target-project-id 13 \
    --expected-project-count 12
```

(Project ID 13 is the Habits project — chosen for the throwaway probe
because it is low-impact and operator-owned.)

### Command — rollback smoke test

Run separately so the symbolic trace is logged independently:

```bash
python3 scripts/vikunja/validate_felix_bot.py \
    --token-file /run/user/$(id -u)/felix-bot-token \
    --rollback-smoke-test \
    --secrets-path /data/services/openclaw/secrets/vikunja-api \
    --bak-path /data/services/openclaw/secrets/vikunja-api.kent-pre-felix-bot.bak
```

(`--token-file` is required by the helper's argparse even in smoke-test
mode — the identity gate runs unconditionally so operators always wire
the token path correctly. The smoke test itself is symbolic and makes
no network calls.)

The smoke test refuses to run if the `.bak` already exists (which
would mean Phase 3 had already executed). That refusal is intentional
— symbolic smoke-testing rollback is the wrong tool once a real
rollback path exists; the operator-driven `--rollback-from-bak` mode
in `swap_vikunja_secrets.py` is the correct path then.

### Expected output

Per-project `OK project_id=<N> title="..."` lines, then a final summary
emitted as space-separated `key=value` pairs:

```
SUMMARY: mode=validate projects_ok=12 target_project_id=13 task_id=<id> comment_id=<id> attribution=ok cleanup_comment=<bool> cleanup_task=<bool> elapsed_seconds=<seconds>
```

The rollback smoke test produces:

```
SUMMARY: mode=rollback-smoke-test simulated_seconds=<seconds> budget_seconds=300.0 within_budget=True elapsed_real_seconds=<seconds>
```

Both exit code 0.

### GO criteria

- [ ] Primary validation exit code 0
- [ ] `SUMMARY: mode=validate ... projects_ok=12 ...` line present
  (confirms all 12 projects readable; `--expected-project-count`
  defaulted to 12)
- [ ] `attribution=ok` field present in the primary SUMMARY line
  (helper aborts before this if `created_by.username != felix-bot`)
- [ ] `cleanup_comment=True` and `cleanup_task=True` in the primary
  SUMMARY line (throwaway comment + task removed)
- [ ] Rollback smoke test exit code 0
- [ ] `within_budget=True` in the smoke-test SUMMARY line
  (`simulated_seconds < budget_seconds=300.0`, satisfies NFR-003)

### NO-GO / rollback trigger

**If any validation step fails, STOP. Do not proceed to Phase 3.**
Production state has not been modified — the secrets file is still
kent's token. Diagnose:

- Project access errors → re-check the share grants applied in Phase 1
  via the Vikunja UI as felix-bot; re-run Phase 1 partially if needed.
- Attribution mismatch (`created_by.username != felix-bot`) → the most
  likely cause is wrong token in the file (e.g. you pasted kent's
  token by accident); regenerate the felix-bot token in the UI and
  re-run Phase 1 starting at the token-capture step.
- Smoke-test refuses because `.bak` exists → a prior Phase 3 was not
  cleaned up. **Do not proceed.** Halt and consult the architecture
  doc-updates; the system is in an unexpected state.

---

## Phase 3 — Swap secrets file (5-15 minutes)

**Spec coverage**: FR-005, FR-006, FR-007, FR-008, NFR-002, NFR-004.
**Helper**: `scripts/vikunja/swap_vikunja_secrets.py` (WP03).

This is the **moment-of-truth phase**. The helper atomically rotates
`/data/services/openclaw/secrets/vikunja-api`, restarts the gateway,
and runs a post-swap write probe to verify attribution flipped to
`felix-bot`. On any failure during steps 3-5 inside the helper, it
auto-rolls back from the `.bak` it just wrote.

### Pre-conditions checked by the helper

The helper performs its own identity gate and pre-condition checks
before mutating anything:

- `--new-token-file` exists, mode 600, non-empty.
- `--secrets-path` exists, mode 600, owned by `claude:claude`.
- No stale `.bak` exists at `<secrets-path><bak-suffix>`.
- `--gateway-unit` is loadable as a `--user` systemd unit.

If any precondition fails the helper exits 2 and does NOT mutate state.

### Command — cutover

```bash
python3 scripts/vikunja/swap_vikunja_secrets.py \
    --new-token-file /run/user/$(id -u)/felix-bot-token \
    --secrets-path /data/services/openclaw/secrets/vikunja-api \
    --bak-suffix .kent-pre-felix-bot.bak \
    --gateway-unit openclaw-gateway.service \
    --gateway-health-timeout 30 \
    --verify-task-id 1
```

(`--verify-task-id 1` is the Inbox-resident probe task. The probe
writes a comment with the rotated token, reads it back, asserts
`created_by.username == felix-bot`, then best-effort-deletes the
probe.)

### Expected output (success)

One `SUMMARY:` line per internal phase (`backup`, `rotate`, `restart`,
`verify`) plus a final JSON summary on stdout. The terminal SUMMARY
line resembles:

```
SUMMARY: phase=verify result=ok created_by=felix-bot
```

Exit code 0.

### Expected output (auto-rollback)

If post-swap verify fails the helper restores from `.bak`, restarts
the gateway, verifies kent attribution is restored, and exits 1. The
helper emits `phase=rollback_restore`, `phase=rollback_restart`, and
`phase=rollback_verify` lines during the recovery, then a terminal:

```
SUMMARY: phase=auto_rollback result=ok attribution=kent
```

Exit code 1.

### GO criteria

- [ ] Exit code 0
- [ ] `SUMMARY: phase=verify result=ok created_by=felix-bot` line
  present (this is the post-swap attribution probe; the helper aborts
  into auto-rollback if `created_by` is anything other than
  `felix-bot`)
- [ ] `.bak` file exists at the expected path, mode 600,
  `claude:claude`
  (verify: `stat -c "%a %U:%G %n" /data/services/openclaw/secrets/vikunja-api.kent-pre-felix-bot.bak`)
- [ ] `systemctl --user is-active openclaw-gateway.service` returns
  `active`
- [ ] No `error` / `ERROR` / `fail` matches in `journalctl --user -u
  openclaw-gateway.service --since '5 minutes ago'`
  (NFR-004 starts its 30-minute clock at the restart timestamp; this
  is the smoke-check that the first 5 minutes are clean)

### NO-GO / rollback trigger

- Helper exit code 1 with `SUMMARY: phase=auto_rollback result=ok
  attribution=kent` → auto-rollback succeeded. Production is back on
  kent's token. **Do not retry the swap.** File a follow-up bug issue
  with the helper's JSON summary attached and stop here.
- Helper exit code 1 with `phase=auto_rollback result=fail` (or
  `result=degraded`) → manual recovery required. The `.bak` file is
  the source of truth; run the operator-driven rollback (below) and
  engage Kent immediately:

```bash
# Manual rollback (use this only if auto-rollback inside the helper failed)
python3 scripts/vikunja/swap_vikunja_secrets.py \
    --rollback-from-bak \
    --secrets-path /data/services/openclaw/secrets/vikunja-api \
    --bak-suffix .kent-pre-felix-bot.bak \
    --gateway-unit openclaw-gateway.service
```

- Helper exit code 2 (usage error) → no production state was mutated;
  fix the input and re-run.

---

## Phase 4 — Documentation commit (10 minutes, on the Mac)

**Spec coverage**: FR-010, FR-011, FR-012, FR-013, SC-006, C-003.

The four architecture documents must be updated and committed in a
single commit to prevent drift between the authoritative JSON manifest
and the narrative views (C-003). The doc updates were authored ahead
of time during WP05 implementation; in this phase the operator
**replaces the rotation-date placeholder** with the actual date of
Phase 3 cutover, then commits.

### Steps (on the Mac, in the kg-automation repo on `main`)

1. Open each of the four files:
   - `docs/design/architecture/data/credential-manifest.json`
   - `docs/design/architecture/credentials-and-secrets.md`
   - `docs/design/architecture/identity-model.md`
   - `docs/design/architecture/data/service-inventory.json`
2. Search for the placeholder string `<rotation-date>` and replace
   each occurrence with today's date in ISO-8601 form (`YYYY-MM-DD`).
   For example: `2026-05-17`.
3. Validate JSON parses cleanly:

   ```bash
   python3 -c "import json; json.load(open('docs/design/architecture/data/credential-manifest.json')); print('credential-manifest OK')"
   python3 -c "import json; json.load(open('docs/design/architecture/data/service-inventory.json')); print('service-inventory OK')"
   ```

4. Run markdownlint on the narrative files (acceptable warnings only;
   no new errors):

   ```bash
   markdownlint docs/design/architecture/credentials-and-secrets.md
   markdownlint docs/design/architecture/identity-model.md
   ```

5. Commit and push (single commit, per C-003):

   ```bash
   git add docs/design/architecture/data/credential-manifest.json \
           docs/design/architecture/credentials-and-secrets.md \
           docs/design/architecture/identity-model.md \
           docs/design/architecture/data/service-inventory.json
   git commit -m "docs(architecture): felix-bot Vikunja identity provisioned (#304)"
   git push origin main
   ```

### Expected output

`git push` reports a single new commit on `main`. CI runs cleanly.

### GO criteria

- [ ] Both JSON files parse
- [ ] Both narrative files pass markdownlint (no new errors)
- [ ] Single commit contains all four files
- [ ] `git push origin main` succeeds
- [ ] CI on `main` reports green for this commit

### NO-GO

- JSON parse fails → fix the syntax (most often a trailing comma
  introduced when editing); re-run validation; commit.
- Markdownlint reports new errors → fix in-place; re-run; commit.
- CI fails → investigate and fix; if blocked, revert the commit on
  `main` and re-do with the fix.

---

## Phase 5 — 7-day soak (passive monitoring)

**Spec coverage**: FR-009, NFR-006, SC-003, SC-004.

For 7 consecutive days starting at the Phase 3 cutover timestamp,
monitor each Felix cron tick for auth errors. The mission's value is
realised here — if any cron fails with a 401/403/auth.fail signature,
the rollback path is exercised and the mission is paused for diagnosis.

### Daily verification checklist

Each morning during the soak, run these checks. Each should be a green
line.

```bash
# 1. Habits morning check-in completed successfully at 7:05 AM ET
ssh office2-claude 'journalctl --user -u openclaw-gateway.service --since "8 hours ago" | grep -E "habits-morning-checkin|felix-admin-habits" | tail -20'

# 2. Escalation daily completed successfully at 8:00 AM ET
ssh office2-claude 'journalctl --user -u openclaw-gateway.service --since "8 hours ago" | grep -E "escalation-daily|felix-admin-escalation" | tail -10'

# 3. Inbox crons completed (4x daily at 7am/noon/5pm/10pm ET)
ssh office2-claude 'journalctl --user -u openclaw-gateway.service --since "24 hours ago" | grep -E "inbox-7am|inbox-noon|inbox-5pm|inbox-10pm|felix-admin-capture" | tail -40'

# 4. NFR-006 / SC-003 audit — zero auth errors in the gateway logs
ssh office2-claude 'journalctl --user -u openclaw-gateway.service --since "24 hours ago" | grep -ciE "401|403|auth.*fail"'
# Expected: 0
```

### GO criteria (daily)

- [ ] Habits morning check-in tick observed in logs (no error tail)
- [ ] Escalation daily tick observed in logs (no error tail)
- [ ] All four inbox cron ticks observed in logs (no error tail)
- [ ] Auth-error grep count is 0 (NFR-006)

### Cumulative GO criteria (Day 7)

- [ ] Seven consecutive days completed
- [ ] Zero auth errors across the full soak window
- [ ] Zero regression in cron success rates compared to the pre-cutover baseline (SC-004)
- [ ] Sample 5 random Felix-written comments from the soak window;
  every one has `created_by.username == felix-bot` (SC-001)

### NO-GO / rollback trigger during soak

If any cron fails with auth errors (401/403/auth.fail) and the failure
is reproducible (not a transient network blip), the system is in an
unhealthy state. Roll back immediately, then diagnose:

```bash
# Operator-driven rollback during soak
ssh office2-claude
cd /home/claude/kg-automation
python3 scripts/vikunja/swap_vikunja_secrets.py \
    --rollback-from-bak \
    --secrets-path /data/services/openclaw/secrets/vikunja-api \
    --bak-suffix .kent-pre-felix-bot.bak \
    --gateway-unit openclaw-gateway.service
```

After rollback:

- File a follow-up bug issue documenting what triggered it (cron name,
  timestamp, log excerpt).
- **Do NOT re-attempt the rotation** without root-cause diagnosis.
- Do NOT remove the `.bak` file. Restart the mission from Phase 1
  only after the bug is fixed and a fresh felix-bot token is
  generated.

---

## Phase 6 — Cleanup (5 minutes)

**Spec coverage**: FR-014, SC-007.
**Helper**: `scripts/vikunja/revoke_kent_tokens.py` (WP04).

After the 7-day soak passes cleanly: revoke any remaining kent API
tokens, remove the backup file, and close the GitHub issue.

### Step 1 — Revoke kent's tokens

Two auth modes are supported. Prefer password-based auth (kent's API
tokens may already be revoked by side effect, but the password still
works for the JWT login):

```bash
ssh office2-claude
cd /home/claude/kg-automation
python3 scripts/vikunja/revoke_kent_tokens.py \
    --kent-username kent \
    --kent-password-from-stdin
```

Stdin: paste kent's Vikunja password from 1Password.

If Vikunja v0.24.6 does not expose the token enumeration endpoint, the
helper detects the 404 and falls back to printing step-by-step UI
revocation instructions. Follow them and re-run the helper with
`--dry-run` afterward to confirm zero tokens remain.

#### Expected output — recognized SUMMARY variants

The helper always terminates with a single `SUMMARY:` line on stdout
(exit 0). Verify the operator sees one of the four recognized variants
below — exit code 0 alone is **not** sufficient acknowledgement; the
SUMMARY line is the operator-readable receipt of which code path ran.

1. **Tokens revoked (happy path — expected on the post-soak run)**

   ```
   SUMMARY: revoked 1 kent API token(s); 0 already-gone/skipped
   ```

   Path: API enumeration succeeded, kent owned ≥1 token, the helper
   deleted each one. The typical count is `1` — kent's original API
   token preserved in the `.bak` through the 7-day soak. A count of
   `0 already-gone/skipped` is expected; a non-zero skipped count
   means one or more tokens could not be deleted (treat as NO-GO and
   re-run, or escalate per the NO-GO section below).

2. **Zero tokens (already-clean path — expected on the confirmation
   re-run after a UI fallback)**

   ```
   SUMMARY: kent has zero API tokens — nothing to revoke. Goal achieved (SC-007).
   ```

   Path: API enumeration succeeded and returned an empty list. This is
   the success signal after Step 1 has already cleaned kent's tokens
   in a previous invocation (e.g., re-running with `--dry-run` after a
   UI fallback to confirm SC-007).

3. **Dry-run (verification path — `--dry-run` flag set)**

   ```
   SUMMARY: dry-run — no network calls issued; no changes made.
   ```

   Path: `--dry-run` was passed; the helper printed its intended
   actions and exited without touching the API. Use this to confirm
   intent before the destructive run, or as the post-UI-fallback
   confirmation step.

4. **UI fallback (API-unavailable path — `--ui-fallback-only` flag, or
   Vikunja returned 404 on the token-enumeration endpoint)**

   ```
   SUMMARY: ui_fallback_instructions printed (operator action required)
   ```

   Path: the helper could not (or was instructed not to) talk to the
   token API and instead printed step-by-step browser instructions for
   manually revoking kent's tokens via the Vikunja UI. The operator
   MUST follow the printed steps and then re-run the helper with
   `--dry-run` (variant 3) followed by a fresh API call (variant 2) to
   confirm zero tokens remain.

If stdout contains **no** `SUMMARY:` line, or contains a line that does
not match one of the four variants above, treat the run as failed
regardless of exit code and escalate per the NO-GO section.

### Step 2 — Remove the backup file

Only after Step 1 confirms zero kent tokens:

```bash
ssh office2-claude 'rm /data/services/openclaw/secrets/vikunja-api.kent-pre-felix-bot.bak'
ssh office2-claude 'ls -l /data/services/openclaw/secrets/vikunja-api.kent-pre-felix-bot.bak 2>&1 | head -1'
# Expected: "No such file or directory"
```

### Step 3 — Close the issue

```bash
gh issue close 304 --repo kentonium3/kg-automation \
    --comment "Closed after 7-day soak. felix-bot is sole Vikunja API identity. kent retains UI access; no API tokens. Backup file removed."
```

### GO criteria

- [ ] `revoke_kent_tokens.py` exit code 0 **AND** stdout contains one
  of the four recognized `SUMMARY:` variants documented above. On the
  post-soak revocation run, the happy-path receipt is variant 1
  (`SUMMARY: revoked 1 kent API token(s); 0 already-gone/skipped`).
  If the API was unavailable, expect variant 4
  (`SUMMARY: ui_fallback_instructions printed (operator action
  required)`) followed by manual UI revocation and a confirmation
  re-run that emits variant 2
  (`SUMMARY: kent has zero API tokens — nothing to revoke.
  Goal achieved (SC-007).`).
- [ ] kent's Vikunja per-user token list shows zero active tokens
  (SC-007)
- [ ] `.kent-pre-felix-bot.bak` removed from the secrets directory
- [ ] kent's UI login at `https://office2.tail0f5f56.ts.net/` still
  works (AS-006)
- [ ] Issue #304 closed with the comment above

### NO-GO

- Helper rejects auth → re-check the password (1Password); if Vikunja
  v0.24.6's token endpoints are unavailable, use `--ui-fallback-only`.
- A residual kent token cannot be deleted via the UI → engage Kent;
  treat as a Vikunja-server bug. Do NOT remove the `.bak` until kent
  tokens are gone (the `.bak` is the rollback path; we keep it until
  there is no longer a token to revoke).
- UI login broken after revocation → roll back immediately
  (Phase 3 inverse, see soak rollback above); revoke API tokens but
  preserve UI access (AS-006).

---

## Success criteria checklist (mirrors spec SC-001 through SC-007)

After Phase 6 completes:

- [ ] **SC-001**: Every Felix agent comment write after cutover
  attributes to `felix-bot` at the API layer. (Sample 5 random
  comments written during the soak; all show
  `created_by.username == felix-bot`.)
- [ ] **SC-002**: All 12 real Vikunja projects accessible to felix-bot
  for read AND write. (Phase 2 validation: reads succeed on all 12
  projects; a single-target write probe against project 13 succeeded
  with `attribution=ok`.)
- [ ] **SC-003**: Zero authentication errors in `openclaw-gateway`
  logs across the 7-day post-cutover soak.
  (`journalctl --user -u openclaw-gateway.service --since "7 days ago"
  | grep -ciE '401|403|auth.*fail'` returns 0.)
- [ ] **SC-004**: Zero regression in Felix cron success rates across
  the 7-day soak window. (Per-cron exit codes during the soak match
  or exceed pre-cutover baseline.)
- [ ] **SC-005**: Rollback procedure verified executable in under 5
  minutes during pre-swap validation (Phase 2 smoke test).
- [ ] **SC-006**: All four affected documentation files updated in
  the same commit on `main` (Phase 4).
- [ ] **SC-007**: Kent's existing API tokens are revoked; only
  felix-bot-attributed tokens are active on the instance
  (Phase 6 Step 1).

---

## References

- **Spec**: `kitty-specs/felix-bot-vikunja-provisioning-01KRT3N4/spec.md`
- **Plan**: `kitty-specs/felix-bot-vikunja-provisioning-01KRT3N4/plan.md`
- **Quickstart**: `kitty-specs/felix-bot-vikunja-provisioning-01KRT3N4/quickstart.md`
- **ADR**: [`docs/design/architecture/adr/0002-felix-vikunja-task-model.md`](../design/architecture/adr/0002-felix-vikunja-task-model.md)
- **Tier 2 protocol**: [`docs/runbooks/governance/pre-flight-checklist.md`](governance/pre-flight-checklist.md), [`post-change-verification.md`](governance/post-change-verification.md)
- **Architecture index**: [`docs/INDEX.md`](../INDEX.md)
- **GitHub issue**: [#304](https://github.com/kentonium3/kg-automation/issues/304) (Phase 1), [#311](https://github.com/kentonium3/kg-automation/issues/311) (umbrella)

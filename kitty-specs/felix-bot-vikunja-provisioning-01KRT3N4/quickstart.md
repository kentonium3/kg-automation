# Quickstart: felix-bot Vikunja provisioning

**Mission**: `felix-bot-vikunja-provisioning-01KRT3N4`

This is the operator-facing quick reference for executing the mission. The full runbook lives at `docs/runbooks/felix-bot-vikunja-provisioning.md` (to be created during implementation). This quickstart is a one-page summary suitable for review during pre-flight.

For the technical rationale behind each step, see [plan.md](./plan.md). For the data each step touches, see [data-model.md](./data-model.md). For the Vikunja API endpoints consumed, see [contracts/vikunja-api-endpoints.md](./contracts/vikunja-api-endpoints.md).

---

## Prerequisites

- SSH access to office2 as the `claude` user
- 1Password access for storing felix-bot's password
- A web browser with access to `https://office2.tail0f5f56.ts.net/` for Vikunja UI operations
- Recent Restic backup (within last 24 hours) — required by Tier 2 protocol
- 30-60 minutes of focused time (operator-driven, manual progression between phases)

---

## Step-by-step

### Pre-flight (5 minutes)

1. Confirm recent Restic backup: `ssh office2-claude 'restic snapshots --last 1'` returns a snapshot within the last 24 hours.
2. Confirm dependent services are healthy: `ssh office2-claude 'openclaw doctor'` reports gateway healthy + sample Vikunja read works with kent's current token.
3. Confirm Kent is present and available for the next 60 minutes.

### Phase 1: Provision felix-bot (5-10 minutes)

```bash
# On office2:
python3 /home/claude/kg-automation/scripts/vikunja/provision_felix_bot.py \
    --username felix-bot \
    --email kentgale+felix-bot@gmail.com \
    --password-from-stdin
# Operator pastes 1Password-generated password into stdin
```

Helper:
- Registers felix-bot via `POST /api/v1/register`
- Enumerates the 12 real projects
- Shares each project with felix-bot at R/W via `PUT /api/v1/projects/{id}/users`
- Verifies all 12 shares by reading back via `GET /api/v1/projects/{id}/users`
- Instructs operator to generate felix-bot's API token via the Vikunja UI (or falls back to API if v0.24.6 exposes the endpoint)
- Accepts the operator-supplied token via stdin and stores it ephemerally for Phase 2

Expected output:
```
SUMMARY: felix-bot registered (uid=N), 12 projects shared, token captured
```

GO criteria: SUMMARY line present, exit 0, all 12 projects show felix-bot in their share list.

### Phase 2: Validate felix-bot (5 minutes)

```bash
# On office2:
python3 /home/claude/kg-automation/scripts/vikunja/validate_felix_bot.py \
    --token-file /tmp/felix-bot-token \
    --target-project-id 13
```

Helper:
- Reads all 12 projects with felix-bot's token (no project access errors)
- Creates a throwaway task in the Habits project (id=13)
- Writes a `[Felix-Validation]` comment, reads it back, asserts `created_by.username == felix-bot`
- Deletes the comment and the throwaway task

Expected output:
```
SUMMARY: validated felix-bot — 12 projects readable, write attribution confirmed, cleanup complete
```

GO criteria: SUMMARY line present, exit 0. **If validation fails, STOP — do not proceed to Phase 3. Production state has not been modified.**

### Phase 3: Swap secrets file (5-15 minutes)

```bash
# On office2:
python3 /home/claude/kg-automation/scripts/vikunja/swap_vikunja_secrets.py \
    --new-token-file /tmp/felix-bot-token \
    --secrets-path /data/services/openclaw/secrets/vikunja-api
```

Helper:
- Backs up the existing secrets file to `vikunja-api.kent-pre-felix-bot.bak` (mode 600, claude:claude)
- Atomic-writes felix-bot's token to `vikunja-api`
- `systemctl --user restart openclaw-gateway`
- Waits up to 30s for gateway to come up
- Invokes a sample Felix agent through the gateway to write a comment, verifies `created_by.username == felix-bot`
- If verification fails: automatically restores from `.bak`, restarts gateway again, exits nonzero

Expected output:
```
SUMMARY: secrets rotated, gateway restarted, sample agent write verified — attribution=felix-bot
```

GO criteria: SUMMARY line present, exit 0. **If swap fails, the helper auto-rolls back — verify rollback succeeded and investigate before retrying.**

### Phase 4: Doc updates (10 minutes, on the Mac)

On the Mac, edit:

1. `docs/design/architecture/data/credential-manifest.json` — `vikunja-api` entry (bump `last_reviewed`, prepend `#304-felix-bot-rotation` to `updated_by`, update `notes`)
2. `docs/design/architecture/credentials-and-secrets.md` — frontmatter `last_updated` + `updated_by`, Active Credentials table `vikunja-api` row
3. `docs/design/architecture/identity-model.md` — Agent Service Accounts section, add felix-bot entry
4. `docs/design/architecture/data/service-inventory.json` — `vikunja` service entry, add felix-bot to user list if that field exists

Single commit, push to main:

```bash
git add docs/design/architecture/data/credential-manifest.json \
        docs/design/architecture/credentials-and-secrets.md \
        docs/design/architecture/identity-model.md \
        docs/design/architecture/data/service-inventory.json
git commit -m "docs(architecture): felix-bot Vikunja identity provisioned (#304)"
git push origin main
```

### Phase 5: 7-day soak (passive monitoring)

Each morning for 7 consecutive days, verify:

- Habits-morning-checkin cron at 7:05am ET completed successfully (`ssh office2-claude 'journalctl --user -u openclaw-gateway.service --since "1 hour ago" | grep felix-admin-habits'`)
- Escalation-daily cron completed successfully
- Inbox crons (7am, noon, 5pm, 10pm ET) completed successfully
- No auth errors (`401` / `403` / `auth.*fail`) in gateway logs

If any cron fails with auth errors: roll back via `swap_vikunja_secrets.py --rollback-from-bak` and investigate.

### Phase 6: Cleanup (5 minutes)

After 7-day soak passes:

```bash
# On office2:
python3 /home/claude/kg-automation/scripts/vikunja/revoke_kent_tokens.py
# Helper enumerates kent's remaining API tokens and revokes them
# (may require operator-supplied kent password if Vikunja's revoke API needs kent JWT)

# Then remove the backup file:
ssh office2-claude 'rm /data/services/openclaw/secrets/vikunja-api.kent-pre-felix-bot.bak'
```

Then close the GitHub issue:

```bash
gh issue close 304 --repo kentonium3/kg-automation --comment "Closed after 7-day soak. felix-bot is sole Vikunja API identity. kent retains UI access; no API tokens. Backup file removed."
```

---

## Rollback procedure (if needed during Phase 3 or Phase 5)

```bash
# On office2:
python3 /home/claude/kg-automation/scripts/vikunja/swap_vikunja_secrets.py \
    --rollback-from-bak \
    --secrets-path /data/services/openclaw/secrets/vikunja-api
```

Helper:
- Verifies `.kent-pre-felix-bot.bak` exists
- Atomic-writes its contents back to `/data/services/openclaw/secrets/vikunja-api`
- `systemctl --user restart openclaw-gateway`
- Invokes sample Felix agent write, verifies `created_by.username == kent`

After rollback:
- File a follow-up bug issue documenting what triggered the rollback
- Do NOT re-attempt the rotation without diagnosis

---

## Success criteria checklist

After Phase 6 completes:

- [ ] felix-bot user exists on the office2 Vikunja instance
- [ ] All 12 real projects shared with felix-bot at R/W
- [ ] `/data/services/openclaw/secrets/vikunja-api` holds felix-bot's token
- [ ] `.kent-pre-felix-bot.bak` removed
- [ ] kent has zero active API tokens on the Vikunja instance
- [ ] kent UI login at `https://office2.tail0f5f56.ts.net/` still works
- [ ] All Felix sub-agent comment writes attribute to `created_by.username == felix-bot` (sampled 5 random comments)
- [ ] 7-day soak completed with zero auth errors in gateway logs
- [ ] 4 architecture docs reflect felix-bot ownership
- [ ] Issue #304 closed

---

## What happens after this mission

Phase 2 of ADR-0002 (#305 — shared JSONL state-log infrastructure) can run in parallel with this or after. Phase 3 (#306 — habits migration to native repeat + JSONL state) requires felix-bot identity AND the JSONL library, so it begins only after both #304 and #305 are done.

The new-project auto-share monitor (referenced in spec's Out of Scope) will be filed as a separate sibling infra issue after this spec lands — that's a follow-up reconciliation cron, not part of this mission.

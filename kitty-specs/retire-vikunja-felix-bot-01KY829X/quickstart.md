# Quickstart / Verification: Retire Vikunja felix-bot (single kent-token model)

## Unit / seam tests (local)

- `VikunjaClient` default resolves the kent token path; any test pinning the felix-bot default
  is updated to the new default.
- `route_someday` no longer has the 403 fail-soft branch — the attach path is unconditional;
  update/remove the fail-soft test.
- `validate_refs` draws its token from the shared default; the negative test (registry diverges
  from the runtime view → validator fails) still bites.
- Run the Vikunja + inbox + habits + trust + escalation test surfaces that touch `VikunjaClient`.

## Grep gate (SC-001)

- `grep -rnE "secrets/vikunja-api([^-]|$)" scripts/` → **no runtime** consumer hand-loads the
  felix-bot token or issues raw HTTP to Vikunja; every runtime Vikunja op goes through
  `VikunjaClient` (only admin/one-shot + docs may remain, and felix-bot-tied one-shots are
  archived). The single `VikunjaClient` default is the kent token.

## ⛔ Attended Tier-2 pre-flight (HOLD for the operator — before ANY live change)

1. **Restic snapshot**: confirm a backup within 24h of `/data/services/openclaw/secrets/` +
   service state; trigger one if not.
2. **Before baseline**: for each of the 9 consumers, capture the current connectivity result
   (auth OK; task/project counts under the felix-bot token) — this is the comparison point.
3. Operator present for the cutover.

## Cutover + live verification (SC-002 / NFR-001 / NFR-003)

- Merge → felix-deployer self-pulls → the kent default is live on next consumer invocation
  (no restart; clients read the token per-call). SKILL.md syncs via the skill-sync pipeline.
- **SC-002 / NFR-001**: a live runtime read now returns tasks from projects **16–20** (was 0):
  e.g. list tasks across the topic-projects under the deployed runtime and confirm count > 0.
- **NFR-003**: re-run the connectivity check for all 9 consumers → all green, zero new auth
  failures vs. the before baseline.
- **SC-003**: `validate_refs` passes under the runtime token; a deliberately diverged registry
  entry makes it fail (guardrail proven).

## Rollback (NFR-002)

- Revert the runtime commit + redeploy (self-pull). The felix-bot `vikunja-api` token is still
  valid, so prior behavior is fully restored. No Vikunja-side action needed.

## Close-out

- Confirm rebaseline outcome (per R6 — record `completed` or `not required — <reason>`).
- Close #831 (SKILL.md now current) and #750 (fail-soft branch removed / attach works).

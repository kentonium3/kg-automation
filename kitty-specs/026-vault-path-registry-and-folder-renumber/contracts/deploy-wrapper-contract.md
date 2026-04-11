# Contract: `deploy-f026.sh` Wrapper

**File:** `scripts/deploy/deploy-f026.sh` (NEW in this mission)
**Purpose:** Mission-specific deploy orchestrator that wraps `scripts/vault/deploy.py` with cron pause/resume, verification, and smoke tests. Satisfies the charter rule for named deploy scripts. Created in WP01, used in WP04 and WP05.

## Usage

```bash
# Dry run — show what would happen, no side effects
bash scripts/deploy/deploy-f026.sh --dry-run

# Pre-rename deploy (WP04) — resolve markers against current registry, no cron pause
bash scripts/deploy/deploy-f026.sh --apply --mode pre-rename

# Post-rename deploy (WP05) — pause cron, deploy, verify, smoke test, resume cron
bash scripts/deploy/deploy-f026.sh --apply --mode post-rename

# Help
bash scripts/deploy/deploy-f026.sh --help
```

## Flags

| Flag | Required | Description |
|---|---|---|
| `--dry-run` | no | Show planned actions without executing. Default if no mode flag provided. |
| `--apply` | with `--mode` | Actually execute. Mutually exclusive with `--dry-run`. |
| `--mode pre-rename` | with `--apply` | Pre-rename deploy (WP04). Skips cron pause because nothing is changing that would affect running agents. |
| `--mode post-rename` | with `--apply` | Post-rename deploy (WP05). Full pause/deploy/verify/smoke/resume sequence. |
| `--skip-smoke` | no | Skip the smoke tests. Only for debugging; prints a loud warning. |
| `--skip-cron` | no | Skip cron pause/resume entirely. Only for debugging; prints a loud warning. |
| `--help` | no | Print usage and exit 0. |

## Pre-rename mode (WP04)

1. Run `python3 scripts/vault/deploy.py --apply`
2. Verify: for every target, compare resolved output to a pre-deploy baseline (captured earlier). Differences outside expected marker substitutions are failures.
3. Smoke test: invoke `felix-admin-capture` once, capture output, compare to pre-deploy baseline. Identical → pass. Different → fail.
4. Smoke test: invoke `felix-admin-tasker` once, same comparison.
5. Exit 0 on success, non-zero with clear error message on any failure.

**Does NOT touch cron.** Pre-rename mode's purpose is to prove refactor fidelity — nothing runtime-observable should change.

## Post-rename mode (WP05)

1. **Pre-flight: Tier 2 backup verification.** Call out to `docs/runbooks/governance/pre-flight-checklist.md` sequence; confirm Restic backup is ≤24h old or trigger a new one. Fail fast if backup cannot be confirmed.
2. **Pause `felix-admin-capture` cron on office2.** Command: `ssh office2-claude` + cron-modification command per existing runbook. Verify pause by checking cron does not fire in the next expected window (or use a shorter verification: confirm the cron entry is commented out).
3. **Run** `python3 scripts/vault/deploy.py --apply`. Any non-zero exit triggers rollback sequence (see below).
4. **Verification: repo-wide grep for stale literals.** Search production files for `00-Inbox`, `01-Constitution`, `02-Growth`, `03-Health`, `04-Business`, `05-Finance`, `06-Journal`, `07-Resources` — zero hits required outside the CLAUDE.md `_private/` boundary line and `docs/archive/`/`docs/func-spec/`. Non-zero hits trigger rollback.
5. **Verification: deployed-file grep for unreplaced markers.** Search repo and office2 for `{{VAULT_` — zero hits in deployed (non-`.tmpl`) files required. Non-zero hits trigger rollback.
6. **Smoke test: `felix-admin-capture` full invocation.** Run against the current inbox state, expect clean exit, no errors in logs, no writes to unexpected paths.
7. **Smoke test: `felix-admin-tasker` full invocation.** Same criteria.
8. **Verification: Obsidian wikilink integrity.** Either query Obsidian's "unresolved links" report, or run a scripted scan of vault markdown files for broken `[[link]]` references. No new broken references attributable to this mission. (Mechanism to be finalized in WP01.)
9. **Re-enable `felix-admin-capture` cron on office2.** Verify the cron entry is un-commented.
10. **Post-resume check.** Either wait for the next natural cron tick and observe it fires, OR trigger a manual one-shot run and verify it completes cleanly.
11. Exit 0 on success, non-zero with rollback guidance on any failure.

## Failure and rollback behavior

On any failure in post-rename mode:

1. **Print a loud warning.** At least 3 lines of `===== FAILURE =====` framing so it cannot be missed in a terminal scroll-back.
2. **State the current system state.** Which steps completed, which step failed, whether the cron is still paused.
3. **Provide next-step guidance.** Point at the rollback section of the WP05 work package file.
4. **Exit non-zero.**
5. **NEVER auto-resume the cron on a failure path** unless the failure is in the cron-resume step itself. The operator must acknowledge and authorize resumption.

## Invariants

1. **Idempotent.** Running the wrapper twice with the same inputs and the same registry state produces the same result. No side effects persist between runs beyond the already-deployed files.
2. **No partial success.** Either the deploy completes and all verifications pass, or the script exits non-zero with clear failure state. There is no "half-deployed" success outcome.
3. **Never silent.** Every decision, action, and check produces output on stdout or stderr. No hidden state changes.
4. **Exit code fidelity.** Exit 0 means every step succeeded. Exit non-zero means at least one step failed. The operator can rely on this for any scripted orchestration.
5. **Verification is mandatory.** `--skip-smoke` and `--skip-cron` flags exist only for debugging and must print loud warnings. Never use them in normal operation.

## Test-first acceptance checks (WP01 exit criteria for the wrapper's creation)

- [ ] `scripts/deploy/deploy-f026.sh` exists and is executable
- [ ] `bash scripts/deploy/deploy-f026.sh --help` prints usage and exits 0
- [ ] `bash scripts/deploy/deploy-f026.sh` (no flags) defaults to dry-run and exits 0
- [ ] `bash scripts/deploy/deploy-f026.sh --apply` without a `--mode` flag exits non-zero with an error
- [ ] `bash scripts/deploy/deploy-f026.sh --apply --mode invalid-mode` exits non-zero with an error
- [ ] The script's source is reviewed to confirm the rollback-on-failure invariants

## Lifecycle

- **Created:** WP01
- **First used:** WP04 (`--apply --mode pre-rename`)
- **Risky use:** WP05 (`--apply --mode post-rename`)
- **After mission:** The script stays in the repo as a historical artifact and reference for the next similar migration. It is not invoked again after WP05 closes.

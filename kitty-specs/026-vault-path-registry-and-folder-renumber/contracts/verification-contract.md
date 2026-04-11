# Contract: Verification Acceptance Tests

**Purpose:** Define every verification check this mission requires, per the DIRECTIVE_034 test-first posture. Each check is specified before the work it verifies, and becomes a WP exit criterion.

## Categories

Verifications fall into four categories:
- **Completeness checks** — "did WPx produce all required artifacts?"
- **Hygiene checks** — "are there any stale or leaked references?"
- **Fidelity checks** — "is behavior unchanged where it should be unchanged?"
- **Smoke tests** — "does the system still work end-to-end?"

## WP01 — Registry Extension

### Completeness

- [ ] `scripts/vault/paths.json` contains exactly these 10 keys: `system`, `inbox`, `inbox_processed`, `constitution`, `growth`, `health`, `business`, `finance`, `journal`, `resources`
- [ ] `scripts/vault/targets.json` contains entries for every file identified in the WP01 audit
- [ ] `scripts/deploy/deploy-f026.sh` exists and is executable (`test -x scripts/deploy/deploy-f026.sh`)

### Hygiene

- [ ] `python3 -c 'import json; json.load(open("scripts/vault/paths.json"))'` succeeds
- [ ] `python3 -c 'import json; json.load(open("scripts/vault/targets.json"))'` succeeds
- [ ] No target entry references a missing template file

### Fidelity

- [ ] `python3 scripts/vault/resolver.py inbox` returns the same path as before WP01
- [ ] `python3 scripts/vault/resolver.py _private` raises UnknownPathError
- [ ] `source scripts/vault/paths.sh && echo "$VAULT_INBOX"` prints the same value as before WP01

### Smoke

- [ ] `python3 scripts/vault/deploy.py` (dry-run, no `--apply`) exits 0 with no errors
- [ ] `bash scripts/deploy/deploy-f026.sh --help` exits 0

**WP01 exit gate:** All checks pass.

---

## WP02 — Code Migration

### Completeness

- [ ] Every file identified in the WP02 audit has a `.tmpl` source in the repo
- [ ] Every `.tmpl` source has a corresponding entry in `targets.json`
- [ ] `CLAUDE.md.tmpl` exists with markers for every non-`_private/` vault reference

### Hygiene

- [ ] Repo-wide grep in production files (excluding `.tmpl` sources, `docs/archive/`, `docs/func-spec/`, `kitty-specs/` historical, `.kittify/` historical, and the CLAUDE.md `_private/` boundary line) for old folder name literals returns zero hits:
  ```
  grep -rn "00-Inbox\|01-Constitution\|02-Growth\|03-Health\|04-Business\|05-Finance\|06-Journal\|07-Resources" \
    --include="*.md" --include="*.json" --include="*.py" --include="*.sh" \
    scripts/ ai-agents/ CLAUDE.md \
    | grep -v "\.tmpl:" \
    | grep -v "_private/"
  ```
  (The exact grep command is refined during WP02 — the principle: zero hits outside documented exclusions.)
- [ ] No `.tmpl` file contains an unknown marker (any `{{VAULT_*}}` that does not correspond to a key in `paths.json`)

### Fidelity

- [ ] For each file converted to `.tmpl` in WP02, `python3 scripts/vault/deploy.py --apply` produces a resolved output byte-identical to the pre-conversion file (NFR-001 precondition).
  - Exception: trailing-whitespace differences are acceptable
  - Exception: `CLAUDE.md` has one expected substitution (the `_private/` boundary line changes from `02-Growth` to the new folder name `04-Growth` — this happens post-WP05, not in WP02)

### Smoke

- [ ] `python3 scripts/vault/deploy.py --apply` exits 0 with zero unresolved markers

**WP02 exit gate:** All checks pass.

---

## WP03 — Documentation Synchronization

### Completeness

- [ ] `docs/design/architecture/data/service-inventory.json` `updated_by` field set to `#152`
- [ ] All in-scope JSON files under `docs/design/architecture/data/` have been audited and updated as needed
- [ ] New runbook `docs/runbooks/vault-path-registry-migration.md` exists
- [ ] The new runbook includes a C4-style summary (System Context, Container, Component, Code levels)
- [ ] `docs/INDEX.md` includes an entry for the new runbook
- [ ] `docs/design/felix-capability-roadmap.md` reflects the vault-path-registry capability as "full" rather than "MVP"

### Hygiene

- [ ] Repo-wide grep in `docs/` for old folder name literals returns zero hits except:
  - `docs/archive/` (frozen history)
  - `docs/func-spec/` (historical F-spec archive)
  - `kitty-specs/` historical mission files
- [ ] Every markdown view in `docs/design/architecture/` matches its JSON source (spot check: line-count deltas within ±10%)

### Fidelity

- [ ] `validate_docs.py` passes on all modified docs (frontmatter + secret scan)

**WP03 exit gate:** All checks pass.

---

## WP04 — Pre-Rename Deploy + Refactor-Fidelity Checkpoint

### Pre-deploy baseline capture

Before WP04 begins, the operator captures a baseline:
- [ ] Invoke `felix-admin-capture` once; record all output (stdout, stderr, any files written, any logs emitted)
- [ ] Invoke `felix-admin-tasker` once; record all output
- [ ] Snapshot `paths.json` (should still point at current folder names, pre-rename)
- [ ] Snapshot the `targets.json`-listed resolved files' SHA256 hashes

### Post-deploy verification (the critical fidelity test)

After `bash scripts/deploy/deploy-f026.sh --apply --mode pre-rename`:

- [ ] Every resolved file's SHA256 matches its pre-WP04 snapshot (or differs only in expected marker substitutions)
- [ ] Re-invoke `felix-admin-capture` against the same inbox state — output is indistinguishable from the baseline (ignore timestamps and other inherently non-deterministic fields)
- [ ] Re-invoke `felix-admin-tasker` against the same input — output is indistinguishable from the baseline
- [ ] No entries in `paths.json` changed during this WP
- [ ] `felix-admin-capture` cron is still enabled and firing on schedule (WP04 should not have touched it)

### The NFR-001 acceptance criterion

**Zero behavior change.** If the pre-deploy and post-deploy invocations of the two agents produce any difference that is not clearly attributable to natural nondeterminism (timestamps, run IDs, etc.), WP04 FAILS and the mission halts for investigation.

This is the DIRECTIVE_034 test-first checkpoint: the test was defined in the spec (NFR-001), captured in this contract before WP04 was executed, and WP04 exists solely to prove the test passes.

**WP04 exit gate:** All fidelity checks pass. Operator reviews and explicitly authorizes WP05 entry.

---

## WP05 — Folder Rename + Post-Rename Deploy + Smoke Tests

This is the risky window. Every check in the list below is a WP05 exit criterion.

### Pre-rename Tier 2 pre-flight

- [ ] Restic backup verified ≤24h old per `docs/runbooks/governance/pre-flight-checklist.md`. If older, new backup triggered and confirmed.

### Cron pause

- [ ] `felix-admin-capture` cron entry on office2 is commented out or removed from the active crontab
- [ ] Verify by attempting a test invocation — cron must not fire during the risky window

### Folder creation

- [ ] `/home/kgale/second-brain/notes/02-Inbox-Processed/` exists on office2
- [ ] The folder contains at least a placeholder file (e.g., `.gitkeep` or equivalent) to ensure sync propagates

### Folder renames (one at a time, with verification between each)

For each rename in the table, after executing it:
- [ ] The old folder name no longer exists
- [ ] The new folder name exists with the same contents
- [ ] Obsidian's link index reflects the rename (no new unresolved links attributable to this rename)

Rename order (operator-driven via Obsidian UI):
1. [ ] `00-Inbox` → `01-Inbox`
2. [ ] `01-Constitution` → `03-Constitution`
3. [ ] `02-Growth` → `04-Growth`
4. [ ] `03-Health` → `05-Health`
5. [ ] `04-Business` → `06-Business`
6. [ ] `05-Finance` → `07-Finance`
7. [ ] `06-Journal` → `08-Journal`
8. [ ] `07-Resources` → `09-Resources`

### Registry update

- [ ] `scripts/vault/paths.json` updated with all new folder names
- [ ] `scripts/vault/paths.json` still validates as JSON
- [ ] `CLAUDE.md` (or `CLAUDE.md.tmpl`) `_private/` boundary reference updated from `02-Growth/_private/` to `04-Growth/_private/`

### Deploy

- [ ] `bash scripts/deploy/deploy-f026.sh --apply --mode post-rename` exits 0

### Post-deploy hygiene

- [ ] Repo-wide grep for old folder name literals returns zero hits outside documented exclusions (NFR-002)
- [ ] Deployed-file grep for unreplaced `{{VAULT_*}}` markers returns zero hits (NFR-003)
- [ ] On office2: `ssh office2-claude 'grep -r "{{VAULT_" /data/services/openclaw/'` returns zero hits

### Smoke tests

- [ ] `felix-admin-capture` full invocation exits 0, processes the current inbox state correctly, writes to expected paths only
- [ ] `felix-admin-tasker` full invocation exits 0, produces expected output, writes to expected paths only
- [ ] Neither invocation produces "file not found" or "path does not exist" errors

### Obsidian wikilink integrity

- [ ] Obsidian "Unresolved links" report shows zero new entries attributable to this mission (NFR-005)
- [ ] Spot check: open 3–5 notes known to have wikilinks, confirm all links resolve

### Cron resume

- [ ] `felix-admin-capture` cron entry on office2 is re-enabled
- [ ] Either wait for the next natural cron tick and observe it fires, OR trigger a one-shot manual run and observe it completes cleanly
- [ ] No error logs from the first cron run after resume

### NFR-004 check

- [ ] Total risky-window duration (cron pause → cron resume) is within 90 minutes. If exceeded, the operator has paused mid-flight to reassess, not continued blindly.

**WP05 exit gate:** All 20+ checks pass. Operator reviews and explicitly authorizes WP06 entry.

---

## WP06 — Cross-Repo FR-6 + Mission Close-Out

### FR-6 cross-repo operation

- [ ] `_private/` appears in `~/second-brain/.gitignore`
- [ ] `git check-ignore -v ~/second-brain/_private/test.md` (dry-run with a hypothetical test path) confirms the ignore rule matches
- [ ] `git status` in `~/second-brain/` shows no `_private/` entries after the edit
- [ ] `git rm --cached -r _private/` was executed (idempotent no-op today; for future-proofing)
- [ ] Second-brain commit created and pushed

### Final mission verification

For each item in `spec.md` § Success Criteria:
- [ ] Success Criterion 1 (Registry completeness) — operator confirms
- [ ] Success Criterion 2 (Reference hygiene) — operator confirms
- [ ] Success Criterion 3 (Folder renumbering) — operator confirms
- [ ] Success Criterion 4 (Processed-inbox folder) — operator confirms
- [ ] Success Criterion 5 (Agent integrity) — operator confirms
- [ ] Success Criterion 6 (Cron continuity) — operator confirms
- [ ] Success Criterion 7 (Wikilink integrity) — operator confirms
- [ ] Success Criterion 8 (Privacy boundary reinforcement) — operator confirms
- [ ] Success Criterion 9 (Documentation currency) — operator confirms
- [ ] Success Criterion 10 (Mission #149 unblocked) — operator confirms

**WP06 exit gate:** All 14 checks pass. Mission ready for merge.

---

## Summary: test-first coverage by FR and NFR

| Requirement | Verified in |
|---|---|
| FR-001 (registry completeness) | WP01 completeness + smoke |
| FR-002 (no hardcoded residue) | WP02 hygiene |
| FR-003 (processed-inbox folder) | WP05 folder creation |
| FR-004 (renumber + wikilink integrity) | WP05 renames + WP05 wikilink |
| FR-005 (deploy + verification) | WP05 deploy + hygiene + smoke |
| FR-006 (cross-repo gitignore) | WP06 cross-repo |
| FR-007 (doc sync) | WP03 completeness + hygiene |
| NFR-001 (refactor fidelity) | WP04 fidelity checks (the dedicated checkpoint) |
| NFR-002 (zero hardcoded residue) | WP02 + WP05 hygiene greps |
| NFR-003 (zero unreplaced markers) | WP01 + WP04 + WP05 smoke |
| NFR-004 (90-min risky window) | WP05 final check |
| NFR-005 (wikilink integrity) | WP05 wikilink |
| NFR-006 (doc sync at merge) | WP03 exit gate + WP06 final |

Every requirement has at least one verification check. No requirement is merely asserted — all are tested.

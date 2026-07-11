---
work_package_id: WP05
title: Deploy, docs & verification
dependencies:
- WP01
- WP02
- WP03
- WP04
requirement_refs:
- C-002
- C-004
tracker_refs: []
planning_base_branch: feat/felix-time-logging
merge_target_branch: feat/felix-time-logging
branch_strategy: Planning artifacts for this mission were generated on feat/felix-time-logging. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/felix-time-logging unless the human explicitly redirects the landing branch.
subtasks:
- T014
- T015
- T016
- T017
phase: Phase 4 - Deploy
assignee: ''
agent: claude
agent_profile: "python-pedro"
history:
- at: '2026-07-10T22:30:00Z'
  actor: system
  action: Prompt generated via /spec-kitty.tasks
authoritative_surface: scripts/deploy/
create_intent:
- scripts/deploy/deploy-timelog.py
- deploys/queued/timelog.yaml
- docs/runbooks/timelog.md
execution_mode: code_change
owned_files:
- scripts/deploy/deploy-timelog.py
- deploys/queued/timelog.yaml
- docs/design/architecture/data/service-inventory.json
- docs/design/architecture/service-inventory.md
- docs/design/architecture/data/credential-manifest.json
- docs/design/architecture/data/data-flows.json
- docs/runbooks/timelog.md
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before touching any file, load your implementer profile so identity, governance
scope, and boundaries are in force for this session:

```
Skill(spec-kitty-implement-review)   # or: /spk-doctrine-profile-load role=implementer
```

Then read, in order:

1. `kitty-specs/felix-time-logging-01KX79HT/spec.md` — C-002, C-004; SC-001..005.
2. `kitty-specs/felix-time-logging-01KX79HT/plan.md` — **IC-05** (this WP's charter).
3. `kitty-specs/felix-time-logging-01KX79HT/quickstart.md` — the deploy steps + the
   two MANDATORY operator stops (re-consent; workbook bootstrap).
4. `scripts/deploy/deploy-truthful-reporting.py` — the **REAL file to mirror** for the
   `--dry-run` **self-test that emits NOTHING** and **gates** `enable`/go-live on a
   clean result (the #711 lesson). Study its `_step_dry_run_self_test` +
   `_step_prompt_sync_and_verify` + `_report` (#701 bus) pattern.
5. `scripts/deploy/deploy-felix-calendar-helper.py` — the **#699** deploy entrypoint:
   the venv/deps provisioning, staged-cred presence check, and `--self-check` smoke
   shape you will reuse for the Sheets helper.
6. `docs/runbooks/deploy/discipline.md` — manifest shape + the **numbering rule**
   (do **NOT** pre-number the queued manifest) + the Python-entrypoint checklist
   (shebang, exec bit, `sys.path` shim).

---

## Branch Strategy

- **DEPENDS ON WP01, WP02, WP03, WP04.** This WP deploys and documents the whole
  feature, so it must run **last**. WP01 = `sheets_auth.py`; WP02 = `sheets_helper.py`;
  WP03 = `timelog.py` + `timelog-clients.json`; WP04 = the `main` prompt recognizer.
  Do not start this WP until all four are merged to `feat/felix-time-logging`.
- Planning/base branch: `feat/felix-time-logging`. Work on this WP's lane branch and
  merge back into `feat/felix-time-logging`.
- The office2 apply itself is **operator-run post-merge** (re-consent + bootstrap are
  Kent-in-the-loop). This WP authors the deploy machinery + docs; it does not perform
  the live office2 apply.

---

## Objectives & Success Criteria

Ship the deploy machinery, architecture-doc updates, and ops runbook for the
time-log feature, satisfying:

- **C-002** — the Sheets scope is added to the felix-personal OAuth (a **one-time
  re-consent by Kent**); the runbook documents that re-consent procedure.
- **C-004** — deploy flows through the manifest discipline (`deploys/queued/…` +
  `felix-deployer`); no hand-cranking on office2.
- **SC-001..005** — the live-verification checklist (in the runbook) proves each
  success criterion end-to-end with Kent.

The deploy entrypoint **must NOT emit false alerts** and **must gate go-live on a
clean self-test** — mirror `deploy-truthful-reporting.py` after the #711 fix:

- The self-test runs the helper in **`--dry-run` mode that emits NOTHING** (a
  self-test must never page the operator).
- Success is **gated** on that self-test being clean; only after it passes does the
  entrypoint trigger prompt-sync / verify / report. Do **not** enable/verify-live
  anything before the self-test passes.

---

## Context & Constraints

- **office2 is `python3`-only** — no `python` binary, no system pip. The helper runs
  under the dedicated uv venv provisioned by the #699 deploy pattern; the entrypoint
  verifies `google-api-python-client` is importable in that venv (reuse
  `deploy-felix-calendar-helper.py`'s venv/deps gate).
- **Deploy path**: `deploys/queued/timelog.yaml` picked up by `felix-deployer` within
  ~5 min of merge to `main`; the entrypoint is invoked **by path** (add the
  `sys.path` shim; `chmod +x` the file BEFORE `git add` — an entrypoint without the
  exec bit fails `entrypoint_dry_run` with `Permission denied`).
- **Two MANDATORY operator stops — Kent-in-the-loop, NOT automated:**
  1. **Sheets re-consent.** Re-minting the `personal` token with the added
     `spreadsheets` scope is a **browser OAuth grant only Kent can complete**. This
     WP does **not** automate it; the runbook documents it and the manifest notes it
     as a precondition.
  2. **Workbook bootstrap.** Creating the Felix-owned workbook and recording its id
     is a **one-time operator step**. Not automated by the entrypoint; documented in
     the runbook + noted in the manifest.
- **Rebaseline: NOT required.** `main`'s `AGENTS.md` is an *unmonitored* audited
  surface (gap #621 — `audit.sh` does not hash deployed `AGENTS.md`); `scripts/google/**`
  and `scripts/deploy/**`'s new time-log code are **not hashed baselines**. The merge
  commit records `Rebaseline: not required — <reason>`. (Do not stamp a rebaseline.)
- **Alerting**: outcome reports go through the **#701 alert bus**
  (`scripts.common.alert_bus.emit`) — no parallel channel — exactly as
  `deploy-truthful-reporting.py` does.

---

## Subtasks & Detailed Guidance

### T014 — `scripts/deploy/deploy-timelog.py` (the deploy entrypoint)

Mirror `deploy-truthful-reporting.py` (self-test + gate) and reuse the venv/creds
gates from `deploy-felix-calendar-helper.py`. `chmod +x` the file. Add the
`sys.path` shim (felix-deployer invokes it by path). `--dry-run` / `--apply` only;
usage error → exit 2. No auto-rollback — print recovery to stderr on any failure.

Strict, halt-on-error apply order:

1. **Venv/deps gate** — confirm the helper's uv venv exists and
   `google-api-python-client` (+ `google-auth*`) are importable in it (idempotent
   provision, reusing the #699 pattern). A missing dep fails here with clear recovery.
2. **Staged-cred + workbook-config presence** — verify the re-consented personal
   token is staged (`~/.config/felix/google/personal/*.json`) **and** the workbook-id
   config exists (`~/.config/felix/timelog/workbook.json`). NEVER copy a secret;
   presence-check only. A missing precondition fails with a "complete the operator
   re-consent / bootstrap first" message (these are the two Kent-in-the-loop stops).
3. **Dry-run self-test that emits NOTHING + gate (#711 — CRITICAL).** Run a
   **no-emit** self-test and **gate success on it being clean**:
   - `sheets_helper --self-check --account personal` (via the venv python, `cwd` =
     repo checkout) — confirms creds/scope/reach WITHOUT writing.
   - `timelog` on a **canned input in dry-run/no-write mode** — confirms the normalizer
     resolves + shapes a receipt WITHOUT appending to the workbook and WITHOUT emitting
     any alert. (Use the helper's dry-run/self-check surface — it must not mutate the
     sheet and must not page the operator.)
   - If either is not clean, the deploy **FAILS here** with nothing enabled/synced, so
     no false alert ever fires. Reconcile, then re-deploy.
4. **Prompt-sync trigger + verify (only after the self-test is clean).** Trigger
   `systemctl --user start agent-prompt-sync.service`, then verify **main's deployed
   `AGENTS.md` carries the time-logging recognizer** (resolve main's deployed workspace
   path from `service-inventory.json` `agents.main.workspace`, exactly as
   `deploy-truthful-reporting.py` resolves deployed prompts). A missing recognizer =
   verification failure (likely WP04 hasn't reached main).
5. **Report via the #701 bus** — emit success/failure through
   `scripts.common.alert_bus.emit`; best-effort, never raises.

Do **NOT** `enable` / go-live / verify-prompt before the self-test in step 3 passes.

### T015 — `deploys/queued/timelog.yaml` (the manifest)

Author the manifest per `discipline.md`. **Do NOT pre-number** — name it
`timelog.yaml` (felix-deployer assigns the applied `NNNN-` number). Fields:

- `schema_version: v1`, `name`, `issue: kentonium3/kg-automation#703`,
  `entrypoint: scripts/deploy/deploy-timelog.py`, `created_at`, `created_by`.
- **Tier**: the deploy touches the personal OAuth **credential scope** (Tier 2 —
  credential/state) and installs logic (Tier 3). When uncertain between two tiers,
  **choose the higher** → `tier: 2`, with a `verification:` block (Tier-2 forces the
  Restic recency gate). Include `pre:`/`post:` commands that catch real failure
  cheaply (e.g. presence of the deployed entrypoint; helper `--self-check`).
  Remember: verification commands run **on office2** — never wrap in
  `ssh office2-claude '…'`.
- `audited_surface`: main's `AGENTS.md` is an audited-but-**unmonitored** surface and
  `scripts/**` here is not a hashed baseline → set `audited_surface: false` (no
  rebaseline). Do not add `expected_baselines`.
- **`notes:`** — spell out the **two operator preconditions**: (a) the **Sheets-scope
  re-consent** (personal token re-minted with `calendar + spreadsheets`, staged on
  office2) and (b) the **one-time workbook bootstrap** (workbook created, id recorded
  in `~/.config/felix/timelog/workbook.json`). Note both must be completed by Kent
  BEFORE this manifest can apply cleanly.

### T016 — architecture docs [P]

Update the machine-readable JSON (authoritative) + the narrative markdown:

- **`credential-manifest.json`** — add the new Sheets **scope** to the felix-personal
  Google OAuth credential entry (the `spreadsheets` scope alongside the existing
  `calendar.events` scope from #699). Follow the existing entry shape (`scope`,
  `used_by`, `expiry_policy`, `review_cadence`, `last_reviewed`); update `last_updated`
  + `updated_by` with this mission's slug + #703.
- **`data-flows.json`** — add the **WhatsApp → timelog → Sheets** flow (Kent's DM →
  `main` → `timelog`/`sheets_helper` → Google Sheets workbook), mirroring the #699
  calendar flow entry shape (`name`, `status`, `deployed_by`, `description`, `path[]`).
- **`service-inventory.json` + `service-inventory.md`** — if the time-log capability
  warrants a service/capability entry (it adds a new deterministic helper surface +
  the Sheets API dependency), add it mirroring the #699 calendar-helper entry; at
  minimum record the new Google Sheets API dependency. Keep the JSON authoritative and
  the `.md` narrative in sync; bump `last_updated`/`updated_by`.
- **Validate**: run `python3 tooling/scripts/validate_architecture_data.py` and confirm
  it exits green (it is a BLOCKING Docs-CI gate).

### T017 — `docs/runbooks/timelog.md` (the ops runbook)

Standard runbook frontmatter (`title`, `doc_type: runbook`,
`audience: agents_and_humans`, `status`, `created`, `last_updated`, `owners`).
Document, concretely:

- **Sheets re-consent procedure** — re-mint the `personal` token with the combined
  `calendar + spreadsheets` scope (browser OAuth, Kent only), stage it at
  `~/.config/felix/google/personal/` on office2 (0600), and verify **BOTH**
  `sheets_helper --self-check` AND `calendar_helper --self-check` return ok (the
  combined-scope token must not break calendar — #699). Do not force scope on refresh.
- **One-time workbook bootstrap** — create the Felix-owned time-tracking workbook
  (via `sheets_helper create-tab` / an initial seed), record its id in
  `~/.config/felix/timelog/workbook.json` (0600), and seed any known client tabs.
- **Rollback** — remove the "log time" recognizer from main's `AGENTS.md` + re-sync
  (the helper is inert without the recognizer); the workbook + creds are Kent's — no
  destructive teardown.
- **SC-001..005 live-verification checklist** — the DM-driven checks with Kent
  (SC-001 log→row+receipt; SC-002 unknown client→ask, no write; SC-003 forced Sheets
  error→failure reported + alert fires, no partial write; SC-004 new-client
  confirm→tab created + entry logged; SC-005 correction→most-recent updated/removed).

---

## Test Strategy

Run:

```
python3 tooling/scripts/validate_architecture_data.py
python3 tooling/scripts/validate_docs.py
python3 -m pytest tests/deploy/test_deploy_timelog.py -v
```

- **`validate_architecture_data.py`** — must exit green after the JSON edits (blocking
  Docs-CI gate). **`validate_docs.py`** — must pass for the new runbook's frontmatter.
- **Deploy-entrypoint unit test** — mirror `tests/trust/test_trust_deploy.py`: load the
  hyphenated `deploy-timelog.py` via `importlib`, mock `subprocess.run` (via the
  module's `_run` wrapper) and the path constants (tmp_path) so **no real systemctl /
  office2 / network** call happens. Assert: `--dry-run` has **zero side effects**;
  `--apply`'s step sequence halts correctly; the **self-test gate blocks go-live** when
  the self-test is not clean (the #711 property); a bad mode arg exits 2.

---

## Definition of Done

- [ ] `scripts/deploy/deploy-timelog.py` exists, is **`chmod +x` (0755)**, has the
      `#!/usr/bin/env python3` shebang + `sys.path` shim, and supports
      `--dry-run`/`--apply` (exit 2 on bad args).
- [ ] The entrypoint runs a **`--dry-run` self-test that emits NOTHING** and **gates**
      go-live (prompt-sync/verify) on it being clean (#711); reports via the #701 bus.
- [ ] `deploys/queued/timelog.yaml` — **not pre-numbered**, `tier: 2` with a
      `verification:` block, `audited_surface: false`, `notes:` spelling out the
      re-consent + workbook-bootstrap operator preconditions.
- [ ] `credential-manifest.json` records the added `spreadsheets` scope;
      `data-flows.json` records the WhatsApp→timelog→Sheets flow; `service-inventory.json`
      + `.md` updated as warranted. `validate_architecture_data.py` exits **green**.
- [ ] `docs/runbooks/timelog.md` documents the **re-consent** procedure (verify BOTH
      self-checks), the **one-time workbook bootstrap**, **rollback**, and the
      **SC-001..005** live-verification checklist. `validate_docs.py` passes.
- [ ] Deploy-entrypoint unit test (mirroring `tests/trust/test_trust_deploy.py`) passes:
      dry-run no-op; self-test gate blocks go-live; exit-2 on bad args.
- [ ] Merge commit records `Rebaseline: not required — <reason>` (main's AGENTS.md is
      unmonitored; `scripts/**` here is not a hashed baseline).

---

## Risks

- **Deploy self-test must NOT emit (#711).** The prior mission pinged Kent's phone with
  deploy-time false-positives by running a real emitting scan as the self-test. Use a
  **`--dry-run`/no-emit** self-test and **gate** on it being clean before going live.
  Do not use any "preflight" mode that emits.
- **Re-consent is Kent-in-the-loop.** The Sheets scope re-mint is a browser OAuth grant
  only Kent can complete — the entrypoint must **presence-check, never automate** it,
  and fail cleanly with a "complete the re-consent first" message if the token is
  missing/narrower. Combined scope must not break the calendar helper (#699).
- **Failing queued manifest fail-loops.** A manifest left in `deploys/queued/` that
  keeps failing re-attempts every ~5-min tick and DMs the operator each time. Ensure
  the entrypoint fails fast + clearly on a missing precondition so the operator can
  fix (or pull the manifest) rather than absorb an alert storm.
- **Two-step non-atomic onboarding surfaces at verify.** SC-004 exercises the
  create-tab-then-append path; the runbook's live check must confirm a
  created-but-not-logged case is reported as *not logged* (never a false "logged").

---

## Reviewer Guidance

Verify concretely (not by prose inspection alone):

- **Self-test emits nothing + gates go-live** — the self-test runs no-emit/dry-run and
  prompt-sync/verify is reached ONLY after it is clean; the unit test proves the gate
  blocks on an unclean self-test (the #711 property).
- **Exec bit + shim** — `deploy-timelog.py` is committed `0755` with the `sys.path`
  shim (felix-deployer invokes by path; without the bit it errors 126).
- **Manifest** — **not pre-numbered**, `tier: 2` + `verification:` block,
  `audited_surface: false`, and `notes:` names both operator preconditions. No
  `ssh office2-claude` wrapper in verification commands.
- **Architecture docs** — the `spreadsheets` scope, WhatsApp→timelog→Sheets flow, and
  any service entry landed in the JSON (authoritative) with the `.md` in sync;
  `validate_architecture_data.py` exits green.
- **Runbook** — re-consent verifies **BOTH** self-checks; bootstrap records the id in
  `~/.config/felix/timelog/workbook.json`; rollback removes the recognizer + re-syncs;
  SC-001..005 checklist present and executable.
- **Rebaseline** — merge records `Rebaseline: not required — <reason>`; no baseline
  stamp applied.

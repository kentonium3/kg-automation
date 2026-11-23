---
work_package_id: WP05
title: Deploy entrypoint and manifest
dependencies:
- WP04
requirement_refs:
- C-004
- NFR-002
- NFR-003
- SC-004
planning_base_branch: fix/crash-loop-unit-alerting
merge_target_branch: fix/crash-loop-unit-alerting
branch_strategy: Planning artifacts for this mission were generated on fix/crash-loop-unit-alerting. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into fix/crash-loop-unit-alerting unless the human explicitly redirects the landing branch.
subtasks:
- T020
- T021
- T022
history:
- at: '2026-11-23T23:40:00Z'
  actor: tasks
  action: Prompt generated via /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/deploy/
create_intent:
- scripts/deploy/deploy-crash-loop-unit-alerting.py
- tests/deploy/test_deploy_crash_loop_unit_alerting.py
- deploys/queued/0043-crash-loop-unit-alerting.yaml
execution_mode: code_change
model: claude-opus-5-5
owned_files:
- scripts/deploy/deploy-crash-loop-unit-alerting.py
- tests/deploy/test_deploy_crash_loop_unit_alerting.py
- deploys/queued/0043-crash-loop-unit-alerting.yaml
role: implementer
tags: []
task_type: implement
tracker_refs: []
---

# Work Package Prompt: WP05 – Deploy entrypoint and manifest

## ⚡ Do This First: Load Agent Profile

Use the `/spk-charter-profile-load` skill to load the agent profile specified in the frontmatter, and behave according to its guidance before parsing the rest of this prompt.

- **Profile**: `python-pedro`
- **Role**: `implementer`
- **Agent/tool**: `claude`

---

## ⚠️ IMPORTANT: Review Feedback

Check `review_ref` via `spec-kitty agent tasks status`; address every item; record progress with `spec-kitty agent tasks add-history <WP> --note "..."`.

---

## Objective

Author the felix-deployer manifest and its entrypoint (C-004). When felix-deployer applies it on office2, the entrypoint must prove that all three crash-loop scopes are live and complete.

⛔ **Hard limit.** This WP **authors** files in the lane branch only. Nothing here may be merged to `main`, pushed to `main`, or applied on office2. Merging to `main` deploys, and Kent approves that separately. **Do not run anything on office2.** `ssh office2-claude` is not needed for this WP. Tests are offline.

## Context to read first

- `research.md` R-11 (the exact verification steps and the rebaseline declaration).
- `deploys/applied/0032-health-check-coverage.yaml` and `scripts/deploy/deploy-health-check-coverage.py`: the pattern to copy. The code reaches office2 with the checkout; the entrypoint runs the real unit and verifies fresh artifacts entry by entry.
- `deploys/schema/manifest-v1.schema.json`, `docs/runbooks/deploy/discipline.md` and `docs/runbooks/deployment.md` (the `expected_baselines` section).
- `tests/deploy/test_deploy_health_check_coverage.py` for the offline test pattern.
- WP01 and WP04 modules: the paths of the state, ledger and tick files, and the config loader.

## Branch Strategy

Planning happened on `kitty/mission-crash-loop-unit-alerting-01M858E8`. The merge target is `fix/crash-loop-unit-alerting`, which reaches `main` only through a PR Kent approves. Get the worktree with `spec-kitty agent action implement WP05 --agent claude --mission crash-loop-unit-alerting-01M858E8`.

## Subtasks

### T020 — `scripts/deploy/deploy-crash-loop-unit-alerting.py`

Mirror `deploy-health-check-coverage.py`'s structure: a docstring explaining WHY, argparse with `--dry-run` / `--apply`, every effect injectable, and exit code 0 only on success.

- **Preflight** (both modes): the euid's passwd name is `claude`, and `Path.home()` is `/home/claude`. `scripts/canary/crash_loop_config.json` loads through `crash_loop_model.load_config`. Never wrap anything in `ssh` (the entrypoint runs on office2).
- **`--dry-run`**: call `crash_loop_readers.read_all_scopes(budget_seconds=config.read_budget_seconds)` once, read-only. Print each scope's `complete`, watched/excluded counts, `elapsed_ms` and the total. Exit 1 if any scope is incomplete, printing its error. Write nothing.
- **`--apply`**:
  1. Preflight.
  2. Record `t0 = now(UTC)`. Run `systemctl --user start felix-canary.service` (it blocks until the oneshot finishes) through an injectable `run` with a 120 s timeout. Non-zero means fail.
  3. Verify:
     - (a) `crash-loop.json` exists and its `updated_at_utc ≥ t0`;
     - (b) today's canary ledger `/data/services/felix-canary/ledger/<YYYY-MM-DD>.jsonl` contains, with `evaluated_at ≥ t0`, one line each for `crash-loop:system`, `crash-loop:user` and `crash-loop:container`, **each with outcome `healthy`**;
     - (c) `/data/services/felix-canary/state/last-tick.json` `completed_at_utc ≥ t0`, and its `errors` contains no string starting `crash_loop`;
     - (d) every crash-loop event ledger line with `evaluated_at ≥ t0` (outcome starting `crash-loop` but not `crash-loop-unverified`) has `delivered: true`.
  4. **Joined-pass rule**: if (a) to (c) fail only on freshness, start the unit **once more** and verify again. The first start may have joined a pass the timer had already started before `t0`, and the canary's `now` is captured at pass start. If it is still stale, fail.
  5. Print one line per check (PASS/FAIL plus evidence). Exit 0 only if all pass.
- A **genuine crash-loop alert at apply time** (delivered) is a successful deploy, the same as 0032's "a delivered failure is success". The first pass only sets baselines, so none is expected.

### T021 — `deploys/queued/0043-crash-loop-unit-alerting.yaml`

Check that `0043` is the next free number: `ls deploys/applied deploys/queued deploys/failed`. If another manifest has taken it by implementation time, use the next free number and **rename consistently** (owned_files lists 0043; record the deviation in the WP history).

```yaml
schema_version: v1
name: crash-loop-unit-alerting
issue: kentonium3/kg-automation#1133
mission_slug: crash-loop-unit-alerting-01M858E8
tier: 3
entrypoint: scripts/deploy/deploy-crash-loop-unit-alerting.py
audited_surface: true
verification:
  pre:
  - scripts/deploy/deploy-crash-loop-unit-alerting.py --dry-run
  post:
  - jq -e '.schema_version == 1' /data/services/felix-canary/state/crash-loop.json
created_at: '<UTC now>'
created_by: claude-code-1133
apply_mode: manifest
notes: >-
  (Write the notes in the 0032 style. Cover: WHY (the 2026-11-23 obsidian-sync loop of 39 restarts
  with no alert); what reaches office2 with the checkout; what the entrypoint proves (all three scopes
  healthy, fresh state, no crash_loop errors, delivered events); that the first tick only sets
  baselines (obsidian-sync's 39 is a baseline); Tier 3; why audited_surface is true (this manifest
  matches the deploy-pipeline surface, which has no affected_baselines, so the expected rebaseline
  outcome is a clean reconciliation, pending_clean then cleared_clean); and rollback: revert the
  merge, after which the canary runs without the stage and crash-loop.json is inert. It can be moved
  aside under /data/services/felix-canary/state/retired/.)
```

Validate it against `deploys/schema/manifest-v1.schema.json` in a test. If the schema forbids a field used above, drop the field and note it. **Do not** add `expected_baselines`: no hashed surface drifts.

### T022 — Tests and the audited-surface record

`tests/deploy/test_deploy_crash_loop_unit_alerting.py` (offline, everything injected):

- Preflight refuses a wrong user and a wrong home.
- `--dry-run`: all scopes complete gives exit 0 and writes nothing. Any scope incomplete gives exit 1, with the scope named.
- `--apply`: the happy path. Fresh state, three healthy scope lines and a clean tick give exit 0.
- `--apply` fails in each of these cases:
  - one scope `unknown` (each scope in turn);
  - a stale `updated_at_utc`;
  - a `crash_loop:` error in the tick;
  - an undelivered event line;
  - a non-zero `systemctl` exit.
- **Joined-pass**: a stale first verification and a fresh second gives exit 0 with exactly 2 starts. Stale twice gives exit 1 with 2 starts.
- The manifest parses and validates against the schema. Its `entrypoint` exists and is executable (`git ls-files -s` mode `100755`, or `os.access`). Its `name` matches the filename.
- The entrypoint source contains no `ssh ` invocation and no `sudo`.

Then run `.venv/bin/python tooling/scripts/check_audited_surface_drift.py` against the lane diff (read its `--help` for the range arguments). Paste the output into the WP history with `spec-kitty agent tasks add-history WP05 --note ...`. Expected: the only match is the `deploy-pipeline` surface, for the manifest.

## Definition of Done

- [ ] The tests pass, and the full suite passes with counts recorded.
- [ ] `chmod +x` on the entrypoint, committed as `100755`.
- [ ] The audited-surface check output is recorded.
- [ ] **Nothing was run on office2 and nothing was pushed to `main`.**
- [ ] Commits use conventional messages and these trailers:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01AFaUqc3Puxhf5oxUb9LLP6`.

## Reviewer guidance

- Every R-11 check is individual, so a combined status cannot mask a single scope's `unknown`.
- The joined-pass retry is bounded to one extra start.
- The manifest declares `audited_surface: true`, and its notes are accurate.
- There is no path by which this WP deploys anything.

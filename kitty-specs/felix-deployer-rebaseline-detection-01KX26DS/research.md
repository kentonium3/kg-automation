# Research & Design Decisions: Robust Felix-Deployer Rebaseline Detection

Phase 0 output. Each decision resolves a design choice the spec deliberately left to
plan. Evidence gathered live from the office2 checkout and the in-repo code on
2026-07-09.

## R1 — Watermark storage and advance semantics

**Decision**: Persist a watermark file `rebaseline-observed-head.json` in
`/data/services/felix-deployer/state/` with `{schema_version, observed_head_sha,
updated_at}`. Each tick computes the observe range as
`observed_head_sha .. post_pull_head`. After observe + reconcile, advance the
watermark to **`post_pull_head` extended by the deployer's own `deploy(applied)`
commit SHA(s) made this tick** — captured deterministically from the commit step in
`_record_success` — **not** a blind end-of-tick `git rev-parse HEAD`.

**Rationale**:
- `observe()` stays pure and already-tested — it keeps its `(base, head)` signature;
  only the *base* changes from `pre_pull_head` to the watermark. Minimal blast radius
  (DIRECTIVE_024).
- Advancing to the deployer's *own* commit (rather than a blind HEAD resolve) avoids a
  mid-tick race: if an out-of-band pull lands an audited commit between `post_pull_head`
  capture and end-of-tick, a blind HEAD resolve would jump the watermark past it and
  the change would never be observed. Extending only by our own captured commit SHA
  leaves any such out-of-band commit *ahead* of the watermark, so the next tick's range
  (`watermark .. next post_pull_head`) still covers it.
- JSON (not a bare SHA file) matches the existing `rebaseline-pending.json` convention
  and leaves room for `updated_at` diagnostics.

**Alternatives considered**:
- *Blind end-of-tick `HEAD` as the new watermark* — simplest, but reintroduces the
  mid-tick out-of-band race (rejected).
- *Path-based self-commit filtering* (ignore commits touching only `deploys/applied|queued`)
  — more code, and fragile if a future deployer commit touches other paths (rejected in
  favor of capturing our own commit SHA, which is exact).
- *No persistence; diff `origin/main@{1}..origin/main`* — reflog-relative selectors are
  brittle across concurrent pulls (rejected).

**Fallback (FR-002/FR-004)**: If the watermark file is absent (first tick after this
ships) → use `pre_pull_head` as the base (current legacy behavior), then write the
watermark. If the stored SHA is unreachable (range diff returns non-zero) → log, treat
the range as not-determinable for that tick (observe returns `not_required`, as it
already does on diff failure), and still advance the watermark to `post_pull_head` so
it self-heals next tick. Reads of a missing/corrupt watermark return `None` and never
raise (mirrors `read_token`).

## R2 — Manifest baseline-declaration field shape

**Decision**: Add an optional array field **`expected_baselines`** to the deploy
manifest (`deploys/schema/manifest-v1.schema.json`), holding **explicit baseline
filenames** (e.g. `["openclaw-cron.txt"]`). This mirrors the pending token's
`expected_baselines` vocabulary exactly.

**Rationale**:
- The defect class is drift with **no repo-file / no audited-surface-pattern signal**
  (a cron removed via `openclaw cron rm`). Referencing a *surface id* to borrow its
  baselines would be indirect and misleading (the surface's *patterns* did not match —
  only its baselines are wanted). Naming the baseline files directly is self-documenting
  in the manifest and matches the token field it feeds.
- Keeps the change in the **manifest schema**, not `audited-surfaces.json` (C-002); the
  CI reminder consumer (`check_audited_surface_drift.py`) is untouched.

**Alternatives considered**:
- `audited_surfaces: [<id>]` resolved via the registry — rejected (indirect; the
  surface's patterns are irrelevant to CLI-mutation drift).
- A boolean "rebaseline everything after apply" escape hatch — rejected (defeats the
  D ⊆ E safety check that distinguishes expected from unexpected drift).

**Coupling rule (FR-007)**: `expected_baselines` may only be present when
`audited_surface: true`; otherwise `validate_manifest` fails. `additionalProperties`
in the schema is `false`, so the field must be added to `properties` explicitly.

## R3 — Validation set for declared baselines

**Decision**: A declared baseline name is valid iff it is in the **known-baseline set
derived from the registry at validation time** — the union of every surface's
`affected_baselines` plus every `non_repo_baselines[].name` in
`docs/design/architecture/data/audited-surfaces.json`. Verified live: that union is
exactly the 14 baselines audit.sh produces, matching `expected_baseline_count: 14`. An
unrecognized name is a **manifest validation error** (visible failure), never silently
ignored (FR-007).

**Rationale**: No new field in `audited-surfaces.json` is needed — the registry already
enumerates all 14 baselines across `affected_baselines` and `non_repo_baselines`.
Deriving the set keeps a single source of truth (NFR-005) and auto-tracks future
baseline additions. `openclaw-cron.txt` and the other non-repo baselines
(`crontabs.txt`, `brew-*`, `hosts-hash.txt`) are all in the union, so CLI-mutation
declarations validate.

**Alternatives considered**: Add an explicit `known_baselines` array to the registry —
rejected as unnecessary churn now; the union is exact. (Revisit only if audit.sh gains
a baseline not referenced by any surface.)

## R4 — Folding declared baselines into the token

**Decision**: `_tick.py` collects the union of `expected_baselines` across all manifests
**successfully applied this tick** during the queue loop, then — after `observe()` runs
— calls a new `rebaseline.fold_manifest_baselines(declared, token_path=…)` that
**creates-or-merges** the pending token, unioning `declared` into
`expected_baselines`. `reconcile()` then runs against the merged token.

**Rationale**:
- Ordering: manifests are applied in the queue loop (before the rebaseline block), so
  their declarations are known when we fold. `observe()` may already have created a
  token (the manifest file itself matches the `deploy-pipeline` surface); `fold_…`
  merges into it. If no token exists (e.g. the manifest was observed in a prior tick and
  the token cleared), `fold_…` creates one with a synthetic surface id
  (`manifest-declared`) so the CLI-mutation drift is still expected. This makes FR-006
  hold regardless of observe/apply tick alignment (research risk in IC-02).
- Keeps `observe()` free of manifest knowledge (separation of concerns) — the fold is a
  distinct, testable step.

**Alternatives considered**: Pass declared baselines into `observe()` as an extra arg —
rejected (couples the pure git-diff observer to manifest parsing; harder to test the two
paths independently).

## R5 — Deploy & rebaseline model (verified)

**Decision**: No `deploys/queued` manifest and **no rebaseline** for this mission.

**Evidence** (office2, 2026-07-09):
- `systemctl --user cat felix-deployer.service` → `WorkingDirectory=/home/claude/kg-automation`,
  `ExecStart=/usr/bin/python3 /home/claude/kg-automation/scripts/deploy/felix-deployer/deployer.py`.
- The tick runs `git pull --ff-only` on that same checkout, then imports `rebaseline`
  and `scripts.deploy.lib` from it. So a code change to the applier takes effect on the
  **next tick after the merge reaches `main`** — the self-pull *is* the deploy.
- The `scripts/deploy/**` audited surface has `affected_baselines: []`; no
  security-monitor baseline hashes arbitrary repo Python. Verified: the 14 baselines are
  service/config/package/host fingerprints only. So this change drifts **no** baseline →
  rebaseline **not required**.

**Consequence for verification**: SC-001..SC-003 (live out-of-band + cron-removal
scenarios) are proven by deterministic unit/integration tests using the injection seams
(git-runner, audit-runner, token/watermark paths, registry). The real-world guarantee is
confirmed passively on the **next** natural audited-surface deploy after this ships;
there is no synthetic office2 deploy in this mission. This is honest about what the
mission can demonstrate.

## R6 — Backward compatibility

**Decision**: Additive only. Existing `rebaseline-pending.json` tokens keep
`schema_version: 1` and are read unchanged. Manifests without `expected_baselines`
behave identically (the field is optional; `fold_…` is a no-op when the declared set is
empty). The first tick after this ships has no watermark file → `pre_pull_head` fallback
→ identical to today, then the watermark takes over. No migration step, no office2
action.

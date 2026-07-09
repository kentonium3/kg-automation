# Feature Specification: Robust Felix-Deployer Rebaseline Detection

**Mission**: felix-deployer-rebaseline-detection-01KX26DS
**Type**: software-dev
**Source**: kentonium3/kg-automation#685 (child of Bedrock Stabilization epic #673; deploy-pipeline trust, #557 rebaseline obligation, #618 auto-rebaseline)
**Target branch**: fix/felix-deployer-rebaseline-detection
**Status**: Draft

## Overview

felix-deployer (#618) is supposed to *silently* reset the office2 security-monitor
baselines after any deploy that changes an audited surface, so the daily security
audit never fires a false drift alert and the operator never rebaselines by hand.
That "happy path" guarantee — documented in `CLAUDE.md` — is currently **false** for
a class of deploys, per #685.

Two independent defects, both proven from the #676 deploy (2026-07-09):

1. **Out-of-band HEAD advance defeats the observe range.** felix-deployer derives the
   rebaseline observe range from *its own* `git pull`: it captures `pre_pull_head`
   before the tick's `git pull --ff-only` and `post_pull_head` after, then calls
   `observe(pre, post)`. `observe()` short-circuits to `not_required` when the two
   heads are equal. This assumes the tick's own pull is the *only* thing that advances
   the local checkout HEAD. It is not: the office2 checkout is also fast-forwarded by
   out-of-band pulls (`git pull --ff-only origin main`, recurring throughout the
   reflog). When such a pull lands the audited-surface commit **before** the tick, the
   tick's own pull is a no-op, `pre == post`, `observe()` returns `not_required`, **no
   pending token is written, and reconcile never runs an audit** — a fully silent
   rebaseline skip. This is exactly what happened at the 00:22 tick on 2026-07-09
   (tick log: `pre_pull_head == post_pull_head == 425517f5…`); the operator rebaselined
   manually at 00:25.

2. **CLI-mutation drift has no repo-file signal, so it is mis-classified.** The same
   deploy removed two OpenClaw crons via `openclaw cron rm` (runtime CLI). That drifts
   the `openclaw-cron.txt` baseline, but there is **no repo-file change** to match any
   audited surface's patterns (the merge touched no `openclaw.json`). Even once defect
   1 is fixed, `openclaw-cron.txt` would not be in the pending token's
   `expected_baselines`, so reconcile would classify the post-deploy drift as
   `unexpected_drift` (drift ⊄ expected) → ntfy alert, **still no auto-rebaseline**.

This mission closes both gaps: it makes the observe range **complete regardless of
which actor advanced HEAD**, and it lets a deploy manifest **declare the baselines it
will drift** so CLI-mutation deploys auto-rebaseline cleanly. It is fix-focused and
deliberately narrow — it does not redesign the audit hashing (#621), the rebaseline
command model, or the deploy pipeline; it does not chase down the out-of-band pull.

## Domain Language

| Term | Canonical meaning | Avoid |
|---|---|---|
| Observe range | The commit range `observe()` scans for audited-surface changes to arm a pending rebaseline | "diff", "pull range" |
| Watermark (last-observed head) | Persisted SHA marking the last HEAD felix-deployer fully processed for observe; the range base | "cursor", "checkpoint" |
| Out-of-band pull | Any HEAD advance on the office2 checkout **not** performed by the tick's own `git pull --ff-only` (e.g. a manual/other `git pull origin main`) | "external commit" |
| Pending token | The `rebaseline-pending.json` state file recording surfaces + `expected_baselines` awaiting confirmation | "lock" |
| Expected baselines (E) | The set of baseline files the pending deploy is expected to drift; reconcile rebaselines only when observed drift D ⊆ E | "affected files" |
| Manifest-declared baselines | Baselines a deploy manifest explicitly names as ones it will drift, folded into E at apply time | "manual baselines" |
| `deploy(applied)` bookkeeping commit | The commit felix-deployer makes to move a manifest queued→applied; must not itself be re-observed | "deploy commit" |
| Auto-rebaseline (#618) | The deferred-confirm flow: observe → arm token → reconcile → rebaseline + verify | "reset" |

## User Scenarios & Testing

**Primary actor**: the felix-deployer applier tick on office2 (running as the `claude`
user). Secondary beneficiary: the Felix operator (Kent), who must not be the
load-bearing component for rebaselining.

### Scenario 1 — Out-of-band pull before an audited-surface deploy (the #685 repro)
- **Trigger**: an out-of-band `git pull origin main` fast-forwards the checkout to a
  merge that carries both a queued manifest and an audited-surface change (e.g. a new
  `scripts/office2/*.service` unit), **before** the felix-deployer tick runs. The
  tick's own `git pull` is then a no-op.
- **Expected outcome**: felix-deployer computes the observe range from the persisted
  watermark (`last_observed..current_head`), detects the audited-surface change, arms a
  pending token, and — after the manifest's entrypoint deploys the change — reconcile
  observes the expected drift and rebaselines to `completed`, all with **zero operator
  actions**. The daily audit reports "All clear".

### Scenario 2 — CLI-mutation deploy with no repo-file signal
- **Trigger**: a manifest removes OpenClaw crons via `openclaw cron rm` (no
  `openclaw.json` change), declaring `openclaw-cron.txt` as a baseline it will drift.
- **Expected outcome**: on apply, the declared baseline is unioned into the pending
  token's `expected_baselines`; reconcile sees `openclaw-cron.txt` drift as **expected**
  (D ⊆ E) and rebaselines to `completed`, not `unexpected_drift`. No false ntfy alert.

### Scenario 3 — Idle ticks / the deployer's own bookkeeping commits
- **Trigger**: several ticks with no new upstream commits; between them felix-deployer
  makes its own `deploy(applied)` commit to move a manifest queued→applied.
- **Expected outcome**: the deployer **never re-observes its own `deploy(applied)`
  commit** (which touches `deploys/**`, itself an audited surface). No spurious pending
  token is armed from bookkeeping commits; idle ticks report `not_required`.

### Scenario 4 — First tick after upgrade / missing or invalid watermark
- **Trigger**: the watermark file does not yet exist (first tick after this fix
  deploys), or the stored SHA is unreachable (e.g. history anomaly).
- **Expected outcome**: felix-deployer falls back to the tick's own `pre_pull_head` for
  the range (unchanged legacy behavior), never crashes, logs the condition, and
  advances the watermark so subsequent ticks are governed by it.

### Testing
Unit tests drive `observe`/`reconcile`/tick with injected git-runner, audit-runner,
token path, watermark path, and registry (the existing injection seams). Cover: equal
tick-heads but non-equal watermark range (defect-1 repro), manifest-declared baselines
folding into E (defect-2 repro), self-commit skip, missing/invalid watermark fallback,
and backward compatibility with manifests that declare nothing.

## Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-001 | felix-deployer MUST compute the observe range as `last_observed_head..current_head`, where `last_observed_head` is read from a persisted watermark in felix-deployer state — not from the tick's own `pre_pull_head`/`post_pull_head`. The range MUST cover every commit between the two, regardless of which actor advanced HEAD. | Draft |
| FR-002 | When no watermark exists (first run / post-deploy migration), felix-deployer MUST fall back to the tick's `pre_pull_head` as the range base, preserving current first-tick behavior; the watermark governs all subsequent ticks. | Draft |
| FR-003 | After observe + reconcile complete in a tick, felix-deployer MUST advance the watermark to the end-of-tick HEAD (including any `deploy(applied)` bookkeeping commits it made this tick), so it never re-observes its own commits. | Draft |
| FR-004 | Watermark validity MUST be classified before self-healing. If the stored SHA is **provably invalid or non-ancestor** of `post_pull_head` (verified via `git cat-file -e <sha>^{commit}` and `git merge-base --is-ancestor <sha> <post>`), felix-deployer self-heals by advancing the watermark and proceeding. For **any other** git/diff failure (transient — index lock, malformed runner output), it MUST leave the watermark **unchanged** and retry next tick — never advancing past an unverified range. Neither case crashes the tick. | Draft |
| FR-010 | A pending token created — or whose baselines were folded — during the current tick MUST NOT be cleared (`cleared_clean`) on a `D=∅` audit in that same tick. Clearing on empty drift is deferred until a subsequent tick (or a minimum token age), so a deploy whose audited effect materializes shortly after apply is not silently forgotten. | Draft |
| FR-005 | A deploy manifest MUST be able to declare the set of security baselines it will drift (e.g. `openclaw-cron.txt`). When that manifest is applied in a tick, its declared baselines MUST be unioned into the pending token's `expected_baselines`. | Draft |
| FR-006 | With declared baselines folded into E, reconcile MUST classify the resulting drift as expected (D ⊆ E) and rebaseline to `completed` for CLI-mutation deploys that have no repo-file signal — instead of `unexpected_drift`. | Draft |
| FR-007 | Manifest-declared baseline names MUST be validated against the registry's known baseline set; an unrecognized name MUST be surfaced as a manifest validation error (visible failure), never silently ignored. | Draft |
| FR-008 | The rebaseline outcome (`completed` / `cleared_clean` / `not_required` with reason / `failed` / `unexpected_drift`) MUST continue to be recorded on the tick log, correlated to the applied manifest name(s), as it is today (FR-003 of #618). | Draft |
| FR-009 | Manifests that declare no baselines MUST behave exactly as they do today (no new pending token content, no behavior change). | Draft |

## Non-Functional Requirements

| ID | Requirement | Measure | Status |
|---|---|---|---|
| NFR-001 | The rebaseline path (observe, reconcile, watermark read/write) AND the new manifest validation MUST NEVER crash the tick. Manifest validation runs in the queue loop, **outside** the rebaseline try/except, so it MUST read the audited-surfaces registry via a **non-exiting** helper (the shared `load_audited_surfaces` calls `sys.exit(2)` on a malformed registry — that path MUST NOT be reachable from `validate_manifest`). | `run_tick` returns 0 under injected exceptions in every new code path (incl. malformed registry during manifest validation); regression test asserts it. | Draft |
| NFR-002 | Manifest application MUST NOT be delayed by rebaseline logic. | Watermark/observe/reconcile run after the queue loop (unchanged ordering); test asserts queue processing precedes rebaseline block. | Draft |
| NFR-003 | Watermark persistence MUST be atomic and tolerant of absence/corruption. | Write via tmp + `os.replace`; missing/corrupt watermark treated as absent (fall back), asserted by test. | Draft |
| NFR-004 | No new runtime dependencies; stdlib + existing repo libs only. New logic covered by tests at or above the charter coverage threshold. | `pip`/import diff shows no new deps; `pytest --cov` meets project gate. | Draft |
| NFR-005 | The shared audited-surfaces matcher MUST remain the single source of truth across the CI reminder and felix-deployer (NFR-001 of #618). | `check_audited_surface_drift.py` and `rebaseline.py` still import `audited_surfaces`; no logic fork. | Draft |

## Constraints

| ID | Constraint | Status |
|---|---|---|
| C-001 | Tier 3 change (Python logic in the felix-deployer applier). The fix touches `scripts/deploy/**`, but that surface's `affected_baselines` is empty — no security-monitor baseline hashes repo Python — so **no rebaseline is required**. The mission merge records `Rebaseline: not required — deploy-pipeline surface has affected_baselines=[]`. | Draft |
| C-002 | The manifest baseline declaration is a change to the **deploy manifest schema** (`deploys/schema/manifest-v1.schema.json`), NOT to `audited-surfaces.json`; the CI reminder consumer (`check_audited_surface_drift.py`) MUST remain unaffected. | Draft |
| C-003 | Backward compatible: existing pending tokens (`schema_version`) and existing manifests without a baseline declaration MUST continue to work unchanged. | Draft |
| C-004 | felix-deployer runs on office2 as the `claude` user (no sudo). The rebaseline command derivation (SSH-wrapper stripping, `sg docker -c … audit.sh`) MUST remain as-is. | Draft |
| C-005 | felix-deployer runs its applier **directly from the office2 checkout** (`systemd ExecStart=…/scripts/deploy/felix-deployer/deployer.py`; the tick git-pulls that same checkout). The fix therefore **deploys by merging to `main`** — office2's next tick pulls and runs the new code. **No `deploys/queued` manifest is required** (none could redeploy the deployer's own code more directly than its self-pull). | Draft |

## Success Criteria

| ID | Criterion | Status |
|---|---|---|
| SC-001 | With the checkout advanced out-of-band between ticks, a deploy that adds a `scripts/office2/*.service` unit arms a pending token and completes a rebaseline within the same or next tick, with 0 operator actions. | Draft |
| SC-002 | A deploy that removes an OpenClaw cron (declaring `openclaw-cron.txt`) yields rebaseline outcome `completed`, not `unexpected_drift`. | Draft |
| SC-003 | The daily security audit reports "All clear" after such a deploy with no manual rebaseline. | Draft |
| SC-004 | Across ≥3 consecutive idle ticks that include the deployer's own `deploy(applied)` commit, no spurious pending token is armed. | Draft |
| SC-005 | All new logic is covered by tests and the existing felix-deployer / rebaseline test suites still pass. | Draft |

## Key Entities

- **Watermark (last-observed head)** — persisted marker in `/data/services/felix-deployer/state/` holding the last HEAD processed for observe (SHA + update timestamp). Injectable path for tests.
- **Pending rebaseline token** — existing `rebaseline-pending.json`; its `expected_baselines` set is now fed by both matched repo-file surfaces and manifest declarations.
- **Manifest baseline declaration** — an optional field on the deploy manifest naming the baselines the deploy will drift.

## Assumptions

- Out-of-band pulls into the office2 checkout are fast-forward only (`--ff-only`), so `watermark..current_head` is a valid ancestor range under normal operation. Non-fast-forward history rewrite is out of scope and handled defensively (FR-004).
- The exact shape of the manifest baseline declaration (explicit baseline filenames vs. audited-surface ids resolved via the registry) is a plan-phase decision; this spec requires the *capability*, not the shape.
- We do not repoint or eliminate the out-of-band `git pull origin main` actor; the fix makes observe robust to it.

## Architecture Impact

Consult `docs/design/architecture/data/signal-to-doc-map.json` during plan for the
full doc-target set. Anticipated surfaces:

- **Code**: `scripts/deploy/felix-deployer/rebaseline.py`, `scripts/deploy/felix-deployer/_tick.py`, and their tests (audited surface: `scripts/deploy/**` → rebaseline obligation, C-001).
- **Manifest schema**: `deploys/schema/manifest-v1.schema.json` (optional baseline-declaration field) + `scripts/deploy/lib/manifest.py` validation (FR-007).
- **Deploy**: none required — the applier self-pulls its own code from the checkout (C-005); the merge to `main` is the deploy.
- **Docs**: the `CLAUDE.md` "happy path" text (the guarantee it makes is restored, and should note robustness to out-of-band HEAD advance); `docs/runbooks/security-baseline-ops.md`; the felix-deployer behavior reference. Verify via the signal-to-doc-map in plan.
- **No change** to `audited-surfaces.json` (its systemd/openclaw patterns are already correct; the defect was never in the registry).

## Out of Scope

- Redesigning the `audit.sh` hashing gaps (#621) beyond the minimum needed for the manifest baseline-declaration path.
- Repointing or eliminating the out-of-band `git pull origin main` source.
- Broader F1 observability (canary registry, single alert stream, dashboards — #516/#137).
- Any change to the rebaseline command derivation or the SSH/`sg docker` execution model.

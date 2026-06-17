# Research: Auto-Rebaseline Security Baselines on Deploy

## R1 — Where felix-deployer sees changes, and where audited surfaces actually deploy

**Decision**: Use felix-deployer's `git pull` (in `run_tick()`, `scripts/deploy/felix-deployer/_tick.py`) as the **observation chokepoint** for committed audited-surface changes — not as their applier.

**Rationale**: `run_tick()` does `git pull --ff-only` then applies `deploys/queued/*.yaml` manifests. But per `docs/design/architecture/data/audited-surfaces.json`, the audited surfaces deploy to office2 through *other* channels:
- `openclaw-agent-prompts` → `agent-prompt-sync.service` (auto, ~5 min timer)
- `openclaw-config` → manual / direct edit
- `systemd-user-units` → operator-invoked `scripts/office2/deploy/*.sh`
- `python-dependencies` → operator runs `pip install`
- `docker-stack` → `docker compose pull`/rebuild

None deploy via felix-deployer's manifests today. But felix-deployer's `git pull` is the one tick-driven process that *observes every committed change* to main. That makes it the right place to notice "an audited surface changed" — provided we decouple *noticing* from *rebaselining* (see R2).

**Alternatives considered**: Push rebaseline into each deploy mechanism (agent-prompt-sync triggers its own reset, etc.). Rejected: N touchpoints, more surface area, and the manual channels have no code to hook.

## R2 — Timing model: deferred-confirm via audit

**Decision**: felix-deployer separates *observation* from *rebaselining* using a pending token confirmed by the audit.

1. After `git pull`, compute the pulled commit range (pre-pull `HEAD` → post-pull `HEAD`) and intersect its changed paths with the audited-surface registry (reuse the matcher from R3). If non-empty, write/merge a **rebaseline-pending token** recording: `pending_since`, matched `surface_ids`, and the union of their `affected_baselines`.
2. On every tick, if a pending token exists, run the security audit **read-only** (`audit.sh` with baselines present — the same invocation the daily audit uses; it compares current office2 state to existing baselines and reports drift without resetting).
   - **Drift confined to the expected baselines** → the surface has deployed and changed the fingerprint → **rebaseline** (`rm baselines/* && sg docker -c audit.sh`), verify `baseline count == expected_baseline_count` and audit reports clear, stamp the observability record, clear the token.
   - **Audit clean (no drift)** → deployed state already matches the baseline (e.g. a doc-only edit to an audited path that doesn't change the hashed content, or the surface re-deployed to identical state) → clear the token, no rebaseline.
   - **Drift extends beyond the expected baselines** → unexpected change = potential security event → do **not** auto-rebaseline; emit an ntfy alert for a human (FR-009, off the happy path).
3. If the token exceeds a max age (surface never appears to deploy), emit an ntfy alert so a human investigates.

**Rationale**: Self-corrects the timing gap between "commit pulled" and "surface live"; only rebaselines when expected drift is actually observed; and naturally separates *expected* drift (auto-rebaseline) from *unexpected* drift (human). Satisfies "no human on the happy path" (FR-002/NFR-004) while keeping the daily audit as the backstop (NFR-003).

**Open verification (carried into implementation/tests)**: confirm `audit.sh` run *with baselines present* is a non-destructive drift check, distinct from the `rm + audit.sh` regenerate path. Cheap local probe on office2 at IC-02 start (DIRECTIVE_031); tests mock the audit invocation.

## R3 — Single source of truth for the audited-surface match (NFR-001)

**Decision**: Refactor the reusable core of `tooling/scripts/check_audited_surface_drift.py` — `load_audited_surfaces()`, `changed_files(range)`, `file_matches_pattern()`, `match_surfaces()` — into an importable module `tooling/scripts/audited_surfaces.py` that both the CI reminder and felix-deployer consume. No second pattern list is created.

**Rationale**: NFR-001 forbids divergence between the deploy-time check and the CI reminder. The existing functions already do exactly the glob-match-against-registry work felix-deployer needs; extract, don't duplicate. The CI script keeps its CLI + exit codes (0 normal, 2 setup-broken); it imports the shared matcher.

**Alternatives considered**: Copy the matcher into felix-deployer. Rejected — violates NFR-001.

## R4 — Reusing the existing ntfy dispatch (FR-006, FR-009)

**Decision**: Model the rebaseline-failure / unexpected-drift / stale-token alerts on the existing `scripts/deploy/felix-deployer/notify.py` `dispatch_failure_notification(...)` path (ntfy.sh, the canonical alert substrate). Add a sibling dispatch for the rebaseline-specific events rather than overloading the manifest-failure payload.

**Rationale**: ntfy is the canonical push substrate (security-monitor precedent). The deployer already wraps notification dispatch so it never crashes the tick — reuse that discipline.

## R5 — Execution context & permissions (C-001)

**Decision**: All rebaseline/audit work runs **locally on office2 as the claude user** via `sg docker -c .../audit.sh` — felix-deployer already runs there. No SSH, no sudo.

**Rationale**: felix-deployer is the office2 applier; the rebaseline command in `docs/runbooks/security-baseline-ops.md` is already claude-runnable through the `docker` group via `sg`. `expected_baseline_count` is read from `audited-surfaces.json` (currently 14), not hardcoded.

## R6 — Deploy + documentation obligations (C-002, C-004) + integration verification

**Decision**: This change ships through a `deploys/queued/<name>.yaml` manifest (the felix-deployer code update itself is a Tier-3 deploy). CLAUDE.md "Rebaseline obligation" and the charter "Rebaseline Obligation (Audited Surfaces, #557)" section are updated so automation is the documented happy path and manual reset is the out-of-band exception. The integration verification is a **post-merge operator canary** (SC-001…SC-004) — a pre-merge live smoke is impossible because the code goes live only on the felix-deployer tick after merge. This mission is the meta-case: deploying it touches `scripts/deploy/**` (an audited surface) — so its own merge is rebaselined manually (the last manual one) per the transition note.

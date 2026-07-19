# Codex Review #1 (post-plan) — findings & resolutions

Independent Codex review (`spec-kitty-review` profile, gpt-5.5) over spec + plan + research +
data-model + quickstart, ~164K tokens, clean exit. Verdict: **not ready to decompose** until the
three HIGH items were fixed. All findings below were verified against the real code and folded into
the artifacts before `/spec-kitty.tasks`.

## HIGH (all fixed)

- **H1 — Timer enable was best-effort → could ship installed-but-not-running (the stranded-edit
  failure this mission eliminates).** VERIFIED: `deploy-felix-canary.py` / `deploy-habits-weekly-driver.py`
  prove `systemctl --user` works from the deploy pipeline with a verify-before-enable gate.
  **Fix**: deploy is now a HARD gate — daemon-reload → real-unit smoke (assert `skills-last-tick.json`
  written) → `enable --now` → assert `is-enabled`/`list-timers`; failed smoke/enable fails the deploy
  loudly. (spec FR-012/SC-008, plan D-5/IC-04, research D-5, quickstart.)

- **H2 — Notifier used `AlertResult.delivered`, which does not exist (field is `.ok`).** VERIFIED in
  `scripts/common/alert_bus/model.py`: `AlertResult` = `{ok, reason, topic_configured}`; `.delivered`
  would raise `AttributeError`, be swallowed by `health.record`, and **never alert**. **Fix**:
  notifier returns `emit(Alert(source,severity,title,description)).ok`. (plan D-2, research D-3,
  data-model INV-9.)

- **H3 — FR-009 drift check was the sync's own `--dry-run` → circular + maskable by the remediating
  sync.** VERIFIED `scripts/canary/{registry,probes}.py` is the independent-observer surface. **Fix**:
  drift check is now a standalone comparator `scripts/openclaw/enforcement/skills_drift_check.py`
  (independent of the sync), registered as a canary probe, alert-only, ignoring `*.backup*`, and it
  reports orphans. (spec FR-009/FR-014, plan D-3/IC-02, research D-4, data-model.)

## MEDIUM (all fixed)

- **M1 — Audited-surface globs don't match the new paths.** VERIFIED `audited-surfaces.json`
  `systemd-user-units` = `scripts/office2/*` and `deploy-pipeline` = `scripts/deploy/lib/**`. **Fix**:
  mission extends globs to cover `scripts/openclaw/deploy/*.{service,timer}` +
  `scripts/deploy/deploy-skills-sync.sh` so C-002 rebaseline actually holds. (plan IC-05, research D-5.)
- **M2 — Manifest tier inconsistent (Tier 3 vs "tier 1/3").** **Fix**: `tier: 3` everywhere.
- **M3 — Repo-removed skill → silent deployed orphan.** **Fix**: FR-014 orphan detection (alert-only,
  no prune) in the independent drift check.
- **M4 — Future multi-file skill dir silently strands support files.** **Fix**: FR-015 multi-file
  warning-audit guard + test.
- **M5 — First-run dest-dir creation implicit.** **Fix**: FR-016 / INV-7 create `dest.parent` before copy.

## LOW (addressed)

- **L1 — Freshness filename consistency.** **Fix**: explicit `skills-last-tick.json` health_check shape
  (`max_age_seconds: 600`) in data-model + service-inventory task.
- **L2 — `atomic_copy` whole-file read.** **Fix**: documented acceptable (small markdown); revisit if
  skills gain large assets (paired with the multi-file guard).

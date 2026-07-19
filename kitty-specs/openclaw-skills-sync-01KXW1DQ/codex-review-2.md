# Codex Review #2 (post-merge, whole-diff) — findings & resolutions

Independent Codex review of the complete merged diff on `feat/openclaw-skills-sync`
(main...feat, ~1.4K-line source diff), before landing on `main`. ~143K tokens, clean exit.
Verdict: **FIX-FIRST**. Both findings verified against the real felix-deployer code and fixed in the
feature branch (commit `4ef4a1df`) before feat→main.

## HIGH (fixed)

- **H1 — the hard verify-before-enable smoke could pass on a lock-deferred no-op.** VERIFIED:
  `scripts/deploy/felix-deployer/_tick.py` wraps the whole manifest apply (incl. the entrypoint) in
  `with deploylock()`; `scripts/deploy/lib/apply.py` runs `[entrypoint, --dry-run]` then
  `[entrypoint, --apply]`. The old smoke's `systemctl --user start agent-skill-sync.service` spawned a
  **separate** process that contended the same checkout lock → `LockUnavailable` → `status="deferred"`
  → still wrote `skills-last-tick.json` → the mtime-only check passed on a no-op → the timer was
  enabled having proved only "the unit can defer under lock." This silently defeats the mission's core
  guarantee (the same guarantee Codex #1 HIGH-1 hardened). **Fix**: new lock-free
  `deploy_agent_skills --smoke` mode does REAL `SKILL.md` copies without the deploylock/git-advance
  (safe: it only reads the checkout felix-deployer already advanced + writes the deployed skills dir,
  which the checkout lock does not protect) and writes `status="smoke"`. The deploy script runs
  `--smoke` in-process (not via systemctl) and asserts `status=="smoke"` (never `"deferred"`). Copy
  loop refactored into `_run_skill_copies` (shared by the locked tick + smoke). +2 tests.

## MEDIUM (fixed)

- **M1 — the entrypoint ignored `--dry-run`/`--apply`.** VERIFIED: `apply.py` calls the entrypoint
  with `--dry-run` then `--apply`; the arg-ignoring script performed the **live** install+enable
  during the supposed-non-mutating dry-run phase. **Fix**: the script now parses `--dry-run` (validate
  + print plan, zero side effects, exit 0) / `--apply` (do the work) / else exit 2. Verified locally:
  `--dry-run` prints the plan and mutates nothing; unknown mode → exit 2.

## Cross-checks Codex confirmed PASSED (no fix needed)

- Path constants byte-identical across helper / deploy script / manifest post-check / service
  inventory: `/data/services/openclaw/deploy/skills-last-tick.json`.
- Canary wiring live: `systemd_user_timer` is a probeable SERVICE_TYPE, `self-check-command` is in
  HANDLED_METHODS, and the runner shells the static endpoint so
  `cd /home/claude/kg-automation && python3 -m scripts.openclaw.enforcement.skills_drift_check`
  resolves.
- Audited-surface globs match the new files (`scripts/openclaw/deploy/*.{service,timer}`,
  `scripts/deploy/*.sh`); `scripts/deploy/*.sh` matches only the bootstrap + skills-sync scripts.
- Helper correctness (AdvanceResult invariants, deploylock/dry-run/exit-code contract, copy-only,
  `.ok` notifier) — clean. 196 tests passed in Codex's run.

Docs aligned: `docs/runbooks/agent-skill-sync-ops.md` updated to describe the `--dry-run`/`--apply`
invocation + the lock-free `--smoke` gate.

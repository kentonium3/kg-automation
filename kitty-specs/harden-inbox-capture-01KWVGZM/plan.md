# Implementation Plan — Harden Inbox Capture on Sonnet

**Mission**: harden-inbox-capture-01KWVGZM
**Branch**: `feat/harden-inbox-capture` (planning base + mission merge target;
later `feat → main` after post-merge Codex review)
**Spec**: [spec.md](./spec.md) · **Research**: [research.md](./research.md)

## Summary

Fix Felix's fleet-wide agent-helper-invocation defect: OpenClaw's `exec` tool
strips `PYTHONPATH`, so #658's `cd "${PYTHONPATH:?…}"` form fails on every cron run
(exit 127 → ModuleNotFoundError), and weak-model capture then hallucinates "scripts
don't exist" and emits false phone alarms. Swap the invocation form fleet-wide to
the self-contained `cd /home/claude/kg-automation && python3 -m scripts.<pkg>.<mod>`,
invert the `env_assumptions.py` checker that currently *bans* that form (correcting
#658), move `felix-admin-capture` to `anthropic/claude-sonnet-4-6`, and reword the
capture prompt so no model can negate helper existence. Phase 1 of #662.

## Technical Context

- **Language/Version**: Python 3.11+ (checker `env_assumptions.py` is stdlib-only,
  3.11-compatible); Markdown (agent prompts); JSON (openclaw.json, service-inventory).
- **Primary Dependencies**: pytest (`--cov-branch`), spec-kitty (workflow), OpenClaw
  runtime (office2 gateway + cron scheduler), systemd user units, gh CLI.
- **Storage**: N/A (config + prompt files; no DB schema change).
- **Testing**: `pytest scripts/openclaw/agents/tests/`; fleet checker CLI
  `python3 -m scripts.openclaw.agents.env_assumptions`; live behavioral verification
  on office2 (empty-inbox IDLE + real-note routing + calendar clarification).
- **Target Platform**: office2 (Ubuntu 24.04, `claude` user); repo checkout
  `/home/claude/kg-automation`; agents capture/escalation/habits/calendar/tasker/main.
- **Deploy**: agent prompts via agent-prompt-sync timer (auto on merge to main);
  `openclaw.json` model change = manual out-of-band office2 edit + gateway restart +
  **manual** security-baseline rebaseline. No `deploys/queued/` manifest.

## Constitution / Charter Check

- **Directive 6 (deterministic vs stochastic)**: corrected application — helper
  resolution becomes deterministic in the invocation itself; LLM keeps only
  comprehension/interaction. ✅
- **Directive 8 (symptom/observer/cost)**: stated in spec + #662 with live evidence. ✅
- **Change-risk taxonomy**: Tier 3 (prompt/config/checker logic) + Tier 4 (arch docs).
  No Tier 0/1 host/fabric changes. The openclaw.json single-value model flip needs no
  state migration.
- **Rebaseline (#557)**: YES (manual, out-of-band) for the openclaw.json model change
  (monitored surface); NOT required for prompt changes (unmonitored surface). Merge
  records the outcome (SC-007).
- **Bulk-edit (DIRECTIVE_035)**: `change_mode: bulk_edit`; `occurrence_map.yaml`
  authored + schema-validated (prompts = `rename`; checker/tests/docs = `manual_review`).

## Architecture & Design

### The fix, in two layers
1. **Deterministic layer (the real fix)** — swap the helper-invocation prefix
   fleet-wide from `cd "${PYTHONPATH:?PYTHONPATH unset}"` to
   `cd /home/claude/kg-automation` (self-contained; immune to exec env sanitization).
   Invert `env_assumptions.py` so this is the compliant canonical form and CI enforces it.
2. **Comprehension layer** — capture → sonnet-4-6; reword `AGENTS.md:74` so no model
   can read "helpers live at `<path>`" and negate it; `:haiku`→`:sonnet` identity.

Contracts: [contracts/invocation-form.md](./contracts/invocation-form.md),
[contracts/env-assumptions-policy.md](./contracts/env-assumptions-policy.md).
Data/entities: [data-model.md](./data-model.md). Verification: [quickstart.md](./quickstart.md).

## Implementation Concern Map (WP outline)

| IC / WP | Concern | Key files | Notes |
|---------|---------|-----------|-------|
| IC-01 / WP01 | Invert the env-assumption checker + tests + correct the authoring runbook (FIRST — it defines "compliant" and gates the fleet swap) | `scripts/openclaw/agents/env_assumptions.py`, `tests/test_env_assumptions.py`, `tests/test_validate_workspace.py`, Test-CI env-guard test, `docs/runbooks/openclaw-agent-setup.md` | Semantic inversion (manual_review). New: **exact** checkout-cd (`/home/claude/kg-automation`) compliant; `${PYTHONPATH:?}` flagged (renamed from HARDCODED_CD → `PYTHONPATH_ANCHOR`); **new `RELATIVE_SCRIPT` class** for `python3 scripts/x.py` / bare `scripts/x.py` without checkout-cd (Codex HIGH-2); bare `-m scripts` still flagged; retain HOME_RELATIVE_WRITE (#659). Single `CANONICAL_CHECKOUT` constant, exact-match (Codex MED-4). Runbook stops teaching the broken form (Codex HIGH-3). |
| IC-02 / WP02 | Fleet prompt invocation-form swap (rename) | `scripts/openclaw/agents/{capture,escalation,habits,calendar,tasker,main}/AGENTS.md` (+ capture/tasker `.tmpl`) | 44 `${PYTHONPATH:?}` occurrences **plus** bare/relative script forms the checker now flags (e.g. capture `AGENTS.md:97` `invoke scripts/.../felix-file-issue.py`; `python scripts/x.py` in main/calendar/tasker). Gate: `python3 -m scripts.openclaw.agents.env_assumptions` reports **ok** fleet-wide (SC-001, SC-008); full `pytest` green. |
| IC-03 / WP03 | Capture comprehension hardening + model doc updates | capture `AGENTS.md` (+ `.tmpl`): line-74 reword, `:haiku`→`:sonnet`; docs: `service-inventory.json`+md (model **and** the PYTHONPATH-drop-in claim), `AGENT-REGISTRY.md` **and** authoritative `agent-registry.json` (Codex MED-5) model haiku→sonnet | openclaw.json is office2-only; the runtime model VALUE flip is applied in WP04, docs here. |
| IC-04 / WP04 | Deploy + verify + rebaseline | office2 manual steps ([quickstart.md](./quickstart.md)) | After feat→main: prompt-sync auto-deploys prompts (**verify all six** deployed AGENTS.md + the prompt-sync log — Codex MED-6); backup+`jq`-validate openclaw.json, edit model, restart gateway, **confirm model-in-effect, THEN manual rebaseline** (Codex LOW-7); run SC-001..008. |

Dependencies: WP01 → WP02 → WP03 → WP04. WP03's doc edits are independent of the
WP02 prompt swap and may proceed in parallel with WP02 once WP01 lands. The
`openclaw-agent-setup.md` runbook correction is in WP01 (co-located with the policy it
documents).

## Risks & Mitigations

- **R1 — a prompt occurrence missed** → the inverted checker (WP01) flags any remaining
  `${PYTHONPATH:?}`/bare form fleet-wide; WP02 gate is `env_assumptions` = ok.
- **R2 — sonnet still hits `🛠️ … failed`** (sibling sonnet crons do today) → the true
  cause is the exec-env form (D1/D2); the WP02 swap removes it for those agents too;
  verify escalation/habits post-deploy as non-regression.
- **R3 — `.tmpl` divergence** (capture `.tmpl` stale: 923 vs 223 lines) → swap only the
  invocation-form occurrences in `.tmpl` (keeps `validate_workspace` env-scan clean); a
  full `.tmpl` re-sync is pre-existing debt, out of scope, noted.
- **R4 — manual rebaseline missed** → quickstart + merge checklist require
  `Rebaseline: completed at <ts>` (SC-007).
- **R5 — gateway not restarted** → model change silent; quickstart makes restart +
  `openclaw cron runs` model check explicit (SC-002).

## Post-plan Codex review

Run 2026-07-06 (`codex -s read-only`): no CRITICAL findings; root cause + fix
validated. 7 findings folded in-plan before task decomposition — HIGH-1/2
(bare/relative script forms + new `RELATIVE_SCRIPT` checker class), HIGH-3 (correct
`openclaw-agent-setup.md` in-mission → WP01), MED-4 (exact `CANONICAL_CHECKOUT`
constant), MED-5 (`agent-registry.json` → WP03), MED-6 (fleet-wide deploy verify),
LOW-7 (validate model-in-effect before rebaseline). No scope-changing decisions
required.

## Follow-ups to file (post-merge)

- **Phase 2 of #662** (its original fifth requirement) — richer multi-intent decomposition (separate issue).
- **Fleetwide model-selection framework** — deferred (separate issue).
- **capture `AGENTS.md.tmpl` full re-sync** — stale vs the 223-line deployed prompt.

## Branch contract (restated)

Current branch: `feat/harden-inbox-capture`. Planning/base branch:
`feat/harden-inbox-capture`. Mission merge target: `feat/harden-inbox-capture`
(`branch_matches_target = true`). After the mission merges internally and the
post-merge Codex review passes, `feat/harden-inbox-capture → main`. Next command:
`/spec-kitty.tasks`.

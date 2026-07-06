# Data Model — Harden Inbox Capture on Sonnet

No database schema. The "entities" here are the configuration/prompt surfaces the
mission mutates and the checker policy that governs them.

## Entities

### AgentPrompt (×6 active)
- **Files**: `scripts/openclaw/agents/<slug>/AGENTS.md` (+ some `AGENTS.md.tmpl`).
- **Slugs**: `felix-admin-capture`, `felix-admin-escalation`, `felix-admin-habits`,
  `felix-admin-calendar`, `felix-admin-tasker`, `main`. Excluded: `felix-doc-auditor`
  (suspended).
- **Mutated field**: every helper-invocation command line.
  - Before: `cd "${PYTHONPATH:?PYTHONPATH unset}" && python3 -m scripts.<pkg>.<mod> …`
  - After:  `cd /home/claude/kg-automation && python3 -m scripts.<pkg>.<mod> …`
- **Invariant**: no invocation depends on an inherited `PYTHONPATH`; the deployed
  workspace cwd is irrelevant because the command `cd`s to the checkout.
- **Deploy**: agent-prompt-sync timer (auto); unmonitored audited surface.

### CaptureIdentity (capture only)
- **String**: `Sent by felix-admin-capture:haiku` → `Sent by felix-admin-capture:sonnet`.
- **Occurrences**: capture `AGENTS.md` lines ~21, ~114, ~212 (+ `.tmpl`). User-visible
  (WhatsApp). Kept as short model name per fleet convention (`<agent>:<model>`).

### CaptureComprehensionProse (capture only)
- **Location**: `AGENTS.md:74` — "Helpers under `scripts/inbox/` do the deterministic
  work. Invoke via `python3 -m scripts.inbox.<helper>` form".
- **Change**: reword so the model cannot read a "helpers live at `<path>`" claim and
  negate it. Reference helpers only as opaque, self-contained invocations. On a helper
  non-zero exit the agent reports actual stderr, never "missing infrastructure".

### AgentModelConfig (capture only; office2)
- **File**: `/home/claude/.openclaw/openclaw.json` → `agents.list[]` entry
  `id: felix-admin-capture`, field `model`.
- **Change**: `anthropic/claude-haiku-4-5` → `anthropic/claude-sonnet-4-6`.
- **Precondition (verified)**: `anthropic/claude-sonnet-4-6` already in
  `models.providers.anthropic.models[]` and `agents.defaults.models`; no providers edit.
- **Deploy**: manual out-of-band edit + gateway restart; monitored audited surface →
  **manual** rebaseline.
- **Doc mirrors**: `docs/design/architecture/data/service-inventory.json`
  (`services.openclaw.agents.felix-admin-capture.model` / registry entry) + its md view;
  `docs/constitution/AGENT-REGISTRY.md`.

### EnvAssumptionPolicy (the checker)
- **File**: `scripts/openclaw/agents/env_assumptions.py`; consumers
  `tests/test_env_assumptions.py`, `validate_workspace.check_runtime_env_assumptions`,
  the Test-CI env-guard test, `tests/test_validate_workspace.py`.
- **Policy transition** (see [contracts/env-assumptions-policy.md](./contracts/env-assumptions-policy.md)):

  | Form | #658 (before) | This mission (after) |
  |------|---------------|----------------------|
  | `cd /home/claude/kg-automation && python3 -m scripts.…` | VIOLATION (`HARDCODED_CD`) | **COMPLIANT** |
  | `cd "${PYTHONPATH:?…}" && python3 -m scripts.…` | COMPLIANT | **VIOLATION** (fails under exec) |
  | bare `python3 -m scripts.…` (unanchored) | VIOLATION (`BARE_M_SCRIPTS`) | VIOLATION (unchanged) |
  | `>>`/`tee` to `~`/`$HOME` path | VIOLATION (`HOME_RELATIVE_WRITE`) | VIOLATION (unchanged, #659) |

## State transitions

None (stateless config/prompt edits). The only runtime "state" is the OpenClaw
gateway which must be restarted to load the new capture model.

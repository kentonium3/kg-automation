# Implementation Plan: Felix-admin cron path robustness fix

**Branch**: `fix/felix-admin-cron-path-fix` | **Date**: 2026-07-04 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `kitty-specs/felix-admin-cron-path-fix-01KWQTY3/spec.md`
**Source issue**: kentonium3/kg-automation#656

## Summary

Fix two related path-handling defects in the felix-admin cron agents on office2:
(1) `python3 -m scripts.*` invocations fail `ModuleNotFoundError` when the agent's
working directory drifts off the repo root, and (2) the inbox agent's dedup state
and forensic logs land in a stray, unsynced `/home/claude/second-brain/`.

**Technical approach (from research + decisions):**

- **FR1 — cwd-independence via an environment guardrail (not per-invocation prompt edits).**
  Add `Environment=PYTHONPATH=/home/claude/kg-automation` to
  `scripts/openclaw/openclaw-gateway.service`. This is inherited by every agent
  subprocess through the same mechanism that already delivers `HOME=/home/claude`
  (the root cause of defect 2 — see line 14 of that unit), so `python3 -m scripts.*`
  resolves from any cwd for **all** agents, not just felix-admin. The invariant
  moves from the stochastic layer (LLM prompt adherence) to the deterministic layer
  (process environment) — a true guardrail. Decision: `DM 01KWR0CRKY6G91P715GD375YKC`.
  **This fix is fleet-wide by construction**; the broader audit of the same
  runtime-environment-assumption *class* (other cwd/HOME/checkout-path cases) is
  tracked separately as **#658** (follow-on, sequenced after this mission).

- **FR2/FR4/FR5 — relocate BOTH stray-dir state files.** Research surfaced a second
  live state file the issue did not name: `pending-calendar-clarifications.json`
  (`scripts/inbox/handle_clarification_state.py`) writes to the same
  `Path.home()/second-brain/agents/state/`. Both it and `inbox-routing.jsonl`
  (`scripts/inbox/routing_log.py`) are repointed to `/data/services/openclaw/state/`;
  both live files are migrated. Repointing only the ledger would leave the
  clarification writer resurrecting the stray dir, failing SC-5.

- **FR3/FR6/FR7 — repoint forensic logs to the canonical vault.** Fix
  `DEFAULT_LOG_DIR` in `scripts/inbox/prescan.py` and the `~/second-brain`
  ambiguity in `scripts/openclaw/agents/felix-admin-capture/AGENTS.md.tmpl`;
  reconcile `AGENTS.md`/`TOOLS.md` copies to
  `/home/kgale/second-brain/agents/logs/`.

- **FR3 (prose) / FR9 — remove now-inert cwd prose + stale ref.** With the env
  guardrail in place, the per-agent `cd … &&` prefixes and "cwd matters" /
  "Working dir: …" prose become inert; remove them so they don't mislead future
  readers. Fix the stale `~/repos/kg-automation` reference in the escalation prompt.

- **FR8 — decommission the stray dir** after migrating its live state and
  preserving its historical logs, via the deploy manifest.

- **Deploy:** all code/prompt/unit changes flow through git → agent-prompt-sync +
  felix-deployer. The one-time office2 data migration (state files + historical
  logs + stray-dir removal) is a Tier-2 `deploys/queued/<n>.yaml` manifest with a
  Python entrypoint built on `scripts/deploy/lib/` primitives (snapshot-verify first).

## Technical Context

**Language/Version**: Python 3.12 (office2 system `python3`); Bash; systemd unit file; Markdown agent prompts.
**Primary Dependencies**: PyYAML (prescan); Python stdlib (`pathlib`, `json`); `scripts/deploy/lib/` primitives (`snapshot`, `verify`, `tier`, `manifest`, `applied`); OpenClaw runtime (agent host, launched by `openclaw-gateway.service`); felix-deployer applier + agent-prompt-sync.
**Storage**: JSONL/JSON state files on office2 at `/data/services/openclaw/state/` (target); Markdown forensic logs in the Obsidian-synced vault at `/home/kgale/second-brain/agents/logs/` (target).
**Testing**: pytest. Path-resolution unit tests that monkeypatch `HOME`/cwd and assert the resolved absolute path is independent of both (NFR-002); reader/writer round-trip tests for both relocated state files; deploy-entrypoint dry-run test.
**Target Platform**: office2 (Ubuntu 24.04 LTS). Agents run as the `claude` user as subprocesses of `openclaw-gateway.service`.
**Project Type**: single (Python helpers + agent-prompt assets + deploy manifest).
**Performance Goals**: N/A — cron cadence (inbox 4×/day, escalation 1×/day). No latency budget.
**Constraints**: Tier-2 (state migration → snapshot-required, C-003); audited surfaces touched (systemd unit + agent prompts) → rebaseline obligation; no hand-edits on office2 (deploy via manifest, C-002); canonical target locations fixed (C-004).
**Scale/Scope**: ~4 agent prompt files; 3 helper path constants (`routing_log.py`, `handle_clarification_state.py`, `prescan.py`); 1 systemd unit line; 1 deploy manifest + entrypoint; migration of 2 live state files + historical forensic logs.

## Charter Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Active builtin directives (from `charter context --action plan`): DIRECTIVE_001, 003, 010, 024, 031, 033, 034. Project directive DIR-001 (production on office2).

- **DIRECTIVE_024 (Locality of Change)** — ✅ blast radius kept tight; the broader class extracted to #658 rather than expanded here.
- **DIRECTIVE_001 (Architectural Integrity)** — ✅ invariant relocated to the environment (guardrail), separation of state (`/data/...`) vs logs (vault) respected.
- **DIRECTIVE_034 (Test-First)** — ✅ NFR-002 path-independence tests written before the path-constant changes; migration entrypoint has a dry-run test.
- **DIRECTIVE_033 (Targeted Staging)** — ✅ per-WP staging; no blanket adds (state files are office2-only, never committed).
- **DIRECTIVE_003 / 010 (Decision docs / Spec fidelity)** — ✅ FR1 mechanism recorded as a decision; spec FRs preserved (env approach satisfies FR1's "guardrail not prose" intent).
- **DIRECTIVE_031 (Context-Aware Design)** — ✅ office2 `claude`-user context (HOME=/home/claude) is the crux; canonical vault is the kgale context; translation is explicit (absolute anchors).
- **DIR-001** — ✅ all runtime effects on office2; Mac is authoring only.

No violations → Complexity Tracking not required.

## Project Structure

### Documentation (this mission)

```
kitty-specs/felix-admin-cron-path-fix-01KWQTY3/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output — state/log entities + path contract
├── quickstart.md        # Phase 1 output — verification steps mapped to SC-1..SC-7
├── contracts/           # Phase 1 output — path-resolution + migration contract
└── tasks.md             # Phase 2 (/spec-kitty.tasks — NOT created here)
```

### Source Code (repository root)

```
scripts/
├── openclaw/
│   ├── openclaw-gateway.service                 # FR1: add Environment=PYTHONPATH (guardrail)
│   └── agents/
│       ├── felix-admin-capture/
│       │   ├── AGENTS.md, AGENTS.md.tmpl         # FR3/FR6/FR7: log path; remove "Working dir" prose
│       │   └── TOOLS.md, TOOLS.md.tmpl           # FR7: reconcile log-path copy
│       ├── felix-admin-escalation/AGENTS.md      # FR9: stale ~/repos ref; remove inert cwd prose
│       ├── felix-admin-habits/AGENTS.md          # FR3: remove `cd … &&` + "cwd matters" prose
│       └── felix-admin-tasker/AGENTS.md          # FR3: (scripts.enrichment.*) remove any cwd prose
├── inbox/
│   ├── routing_log.py                            # FR2/FR4/FR5: DEFAULT_ROUTING_LOG_PATH → /data/...
│   ├── handle_clarification_state.py             # FR2/FR4/FR5: STATE_PATH_DEFAULT → /data/... (2nd file)
│   └── prescan.py                                # FR6: DEFAULT_LOG_DIR → /home/kgale/.../logs
└── deploy/
    └── migrate-inbox-state-and-logs.py           # FR5/FR8: Tier-2 migration entrypoint (new)

deploys/queued/
└── 000N-migrate-inbox-state-and-logs.yaml        # FR5/FR8: manifest (snapshot → migrate → verify → decommission)

tests/inbox/                                       # NFR-002 path-independence + round-trip tests
```

**Structure Decision**: Single-project layout. Changes cluster in three surfaces —
the systemd unit (guardrail), the inbox helpers' path constants, and the agent
prompt assets — plus one deploy manifest for the office2 data migration.

## Complexity Tracking

*Not required — Charter Check has no violations.*

## Implementation Concern Map

> Concerns, not work packages. `/spec-kitty.tasks` maps these to WPs.

### IC-01 — Fleet-wide cwd guardrail (systemd env)

- **Purpose**: Move the `scripts`-import invariant into the process environment so no agent depends on cwd.
- **Relevant requirements**: FR-001, FR-002, NFR-002.
- **Affected surfaces**: `scripts/openclaw/openclaw-gateway.service` (one `Environment=` line); deploy of the unit.
- **Sequencing/depends-on**: none (foundational). Must deploy **before** IC-04 removes the cwd prose.
- **Risks**: **#653 collision** — the same unit's `ExecStart` (line 7) is mid-relocation `/usr/lib` → `~/.local` under #653's pending closeout; add only the `Environment=` line and coordinate so this edit doesn't stomp #653's ExecStart change. Audited surface → rebaseline obligation. Verify inheritance holds (KillMode=control-group ⇒ children inherit env).

### IC-02 — Relocate dedup + clarification state to `/data/services/openclaw/state/`

- **Purpose**: Serve both live state files from the canonical JSONL-state directory; kill the stray-dir writers.
- **Relevant requirements**: FR-004, FR-005 (+ the second state file found in research).
- **Affected surfaces**: `scripts/inbox/routing_log.py` (`DEFAULT_ROUTING_LOG_PATH`), `scripts/inbox/handle_clarification_state.py` (`STATE_PATH_DEFAULT`), plus their readers/writers and monkeypatch-based tests.
- **Sequencing/depends-on**: pairs with IC-05 (migration) — code cutover and data move must be consistent.
- **Risks**: both modules resolve the default at call time (good for monkeypatching); ensure no other reader hardcodes the old path (grep confirmed only these two + prescan docstring).

### IC-03 — Repoint forensic logs to the canonical vault

- **Purpose**: Forensic logs land where Obsidian sync carries them to Kent's devices.
- **Relevant requirements**: FR-006, FR-007.
- **Affected surfaces**: `scripts/inbox/prescan.py` (`DEFAULT_LOG_DIR` + docstring), capture `AGENTS.md.tmpl` (`~/second-brain` line ~565), and the deployed `AGENTS.md`/`TOOLS.md`/`TOOLS.md.tmpl` copies (reconcile to `/home/kgale/second-brain/agents/logs/`).
- **Sequencing/depends-on**: none.
- **Risks**: `~` ambiguity — must use the absolute `/home/kgale/...`, never `~`, since the writer runs as `claude`. `file_inbox_quality_issue.py:37` already uses the correct path (leave as the reference).

### IC-04 — Remove now-inert cwd prose + stale checkout ref

- **Purpose**: Delete instructions the guardrail makes unnecessary so prompts stay truthful.
- **Relevant requirements**: FR-003, FR-009.
- **Affected surfaces**: habits `AGENTS.md` (`cd … &&` prefixes + line ~90 "cwd matters"), capture `AGENTS.md` (line ~74 "Working dir: …"), escalation `AGENTS.md` (line ~265 stale `~/repos/kg-automation`).
- **Sequencing/depends-on**: **must follow IC-01 deploy** — removing "you must cd" prose before the env guardrail is live would reintroduce the bug with no safety net.
- **Risks**: agent-prompt audited surface; keep edits prose-only (no behavior change beyond removing the redundant `cd`).

### IC-05 — One-time office2 data migration + stray-dir decommission

- **Purpose**: Move the two live state files, preserve historical logs into the vault, then remove `/home/claude/second-brain/`.
- **Relevant requirements**: FR-005, FR-008; C-003 (Tier-2), NFR-003 (manifest-driven).
- **Affected surfaces**: new `scripts/deploy/migrate-inbox-state-and-logs.py` (built on `scripts/deploy/lib/snapshot|verify|tier`); new `deploys/queued/000N-…yaml` (pre: snapshot-verify; post: assert new-path files present + stray dir gone).
- **Sequencing/depends-on**: state-file copy must be present at the new path **before** IC-02's readers rely on it.
- **Risks**: **migration/cutover window** — if code lands before the copy, a reader sees the new path empty. Mitigations: (a) readers are already fail-safe (missing file → empty set) AND notes carry `status: processed` frontmatter (mark_processed), so already-routed notes are still skipped even with an empty ledger — bounding worst-case to at most re-evaluation, not duplication; (b) manifest copies state **first** and its `post` check asserts presence; (c) decommission only after verify. Tasks phase decides whether a one-release transitional new→old read-fallback is warranted (with an explicit removal forcing function per the no-vestiges rule) or (a)+(b) suffice.

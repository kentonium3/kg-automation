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

> **Post-plan Codex review (#1) folded in (2026-07-04).** An independent Codex
> pass found several material issues, all confirmed against code/live office2
> state; this plan already incorporates them: FR1 delivered as a **systemd
> drop-in** (not an inline unit edit) with a **live in-agent verification gate**;
> a package-import fix so dedup actually works under the guardrail (FR-011);
> **atomic copy-before-cutover** + **quarantine** decommission; state-dir
> **ownership/mode** convention (FR-012); and a **broadened prompt sweep** incl.
> the calendar `.jsonl` clarification writer (FR-010) and tasker refs (FR-009).

- **FR1 — cwd-independence via an environment guardrail (not per-invocation prompt edits).**
  Ship `Environment=PYTHONPATH=/home/claude/kg-automation` as a dedicated systemd
  **drop-in** — `scripts/openclaw/openclaw-gateway.service.d/pythonpath.conf` with
  `[Service]\nEnvironment=PYTHONPATH=/home/claude/kg-automation` — rather than
  editing the unit's `Environment=` line inline. The drop-in composes with the
  existing unit (systemd merges `.d/*.conf`) and **avoids any source-line collision
  with #653's in-flight `ExecStart` relocation**. The value is inherited by every
  agent subprocess (Node `child_process` inherits `process.env` by default; the
  gateway carries the systemd env), so `python3 -m scripts.*` resolves from any cwd
  for **all** agents. The invariant moves from the stochastic layer (LLM prompt
  adherence) to the deterministic layer (process environment) — a true guardrail.
  Decision: `DM 01KWR0CRKY6G91P715GD375YKC`.
  **Verification gate (Codex #1, critical):** inheritance is *asserted, not proven*
  by the `HOME` precedent (HOME also comes from `/etc/passwd`). Before the mission
  relies on the guardrail and before removing any cwd prose, a step MUST verify
  `PYTHONPATH` is present inside a **real OpenClaw-launched agent/cron subprocess**
  (not an SSH login shell — the wrong surface). If inheritance does NOT hold, fall
  back to the openclaw agent-env path (out-of-repo) — but the drop-in is expected to work.
  **Fleet-wide by construction**; the broader runtime-environment-assumption *class*
  is tracked as **#658** (follow-on, after this mission).

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
│   ├── openclaw-gateway.service.d/
│   │   └── pythonpath.conf                        # FR1: drop-in Environment=PYTHONPATH (guardrail; avoids #653 collision)
│   └── agents/
│       ├── felix-admin-capture/
│       │   ├── AGENTS.md, AGENTS.md.tmpl          # FR3/FR6/FR7: log path; remove "Working dir" prose
│       │   └── TOOLS.md, TOOLS.md.tmpl            # FR7: reconcile log-path copy
│       ├── felix-admin-calendar/AGENTS.md         # FR10: repoint inline .jsonl clarification writer → /data/...
│       ├── felix-admin-escalation/AGENTS.md       # FR9: stale ~/repos ref; remove inert cwd prose
│       ├── felix-admin-habits/AGENTS.md           # FR3: remove `cd … &&` + "cwd matters" prose
│       ├── felix-admin-tasker/{AGENTS.md,TOOLS.md} # FR9: ~/repos + ~/second-brain refs (not _private)
│       └── main/AGENTS.md                          # FR10: calendar clarification .jsonl path ref → /data/...
├── inbox/
│   ├── routing_log.py                            # FR10/FR12: DEFAULT_ROUTING_LOG_PATH → /data/...; parent mode
│   ├── handle_clarification_state.py             # FR10/FR12: STATE_PATH_DEFAULT (.json) → /data/...; mode
│   ├── prescan.py                                # FR6: DEFAULT_LOG_DIR → vault; FR11: package-absolute import
│   └── append_routing_entry.py                   # FR11: align sys.path hack → package import (optional)
└── deploy/
    └── migrate-inbox-state-and-logs.py           # FR5/FR8/FR12: Tier-2 migration entrypoint (new)

deploys/queued/
└── 000N-migrate-inbox-state-and-logs.yaml        # manifest (snapshot → atomic copy+perms → verify → quarantine → decommission)

tests/inbox/                                       # NFR-002 path-independence; FR11 dedup-active-from-/tmp; frontmatter-only dedup
```

**Structure Decision**: Single-project layout. Changes cluster in three surfaces —
the systemd unit (guardrail), the inbox helpers' path constants, and the agent
prompt assets — plus one deploy manifest for the office2 data migration.

## Complexity Tracking

*Not required — Charter Check has no violations.*

## Implementation Concern Map

> Concerns, not work packages. `/spec-kitty.tasks` maps these to WPs.

### IC-01 — Fleet-wide cwd guardrail (systemd drop-in) + verification gate

- **Purpose**: Move the `scripts`-import invariant into the process environment so no agent depends on cwd.
- **Relevant requirements**: FR-001, FR-002, NFR-002, SC-10.
- **Affected surfaces**: new `scripts/openclaw/openclaw-gateway.service.d/pythonpath.conf` (drop-in, not an edit to the base unit); its deploy.
- **Sequencing/depends-on**: none (foundational). Must deploy + **pass the verification gate before** IC-04 removes any cwd prose.
- **Verification gate (Codex #1)**: prove `PYTHONPATH` is present in a **real agent/cron subprocess** (run an agent/cron payload that prints `os.environ["PYTHONPATH"]` from a non-repo cwd) — SSH login shells are the wrong surface. Only after this passes may IC-04 proceed.
- **Risks**: **#653 collision AVOIDED** by using a drop-in (`.d/*.conf`) rather than editing the base unit's `ExecStart`-bearing source. Audited surface (systemd unit) → rebaseline obligation. If openclaw scrubs env when spawning tool shells, the guardrail fails → fall back to openclaw agent-env (out-of-repo); the gate catches this before reliance.

### IC-02 — Relocate ALL stray-dir state writers + fix package imports

- **Purpose**: Serve state from the canonical dir; kill **every** stray-dir writer (so decommission holds); make dedup actually resolve under the guardrail.
- **Relevant requirements**: FR-004, FR-005, FR-010, FR-011, FR-012, SC-8, SC-9.
- **Affected surfaces**:
  - `scripts/inbox/routing_log.py` (`DEFAULT_ROUTING_LOG_PATH` → `/data/...`; fix parent-dir mode 0700 → convention).
  - `scripts/inbox/handle_clarification_state.py` (`STATE_PATH_DEFAULT` `.json` → `/data/...`; explicit mode).
  - **calendar `.jsonl` writer** — `scripts/openclaw/agents/felix-admin-calendar/AGENTS.md` (inline `os.path.expanduser("~/...pending-calendar-clarifications.jsonl")`) + `scripts/openclaw/agents/main/AGENTS.md` + calendar `TOOLS.md` — repoint path to `/data/...` (format left as-is; FR-010 follow-up tracks unification).
  - `scripts/inbox/prescan.py` — convert bare `from routing_log import …` → `from scripts.inbox.routing_log import …` (FR-011); consider aligning `append_routing_entry.py`'s `sys.path` hack to the package form too.
- **Sequencing/depends-on**: pairs with IC-05 (migration) — code cutover and data move must be consistent.
- **Risks**: dedup was silently import-degradable (Codex #1 C2) — add a test running a full prescan from `/tmp` asserting no "dedup-disabled" warning. Both state modules resolve defaults at call time (monkeypatch-friendly). Ownership convention: owner `claude`, group `secondbrain`, dir `0750`, files `0640`.

### IC-03 — Repoint forensic logs to the canonical vault

- **Purpose**: Forensic logs land where Obsidian sync carries them to Kent's devices.
- **Relevant requirements**: FR-006, FR-007.
- **Affected surfaces**: `scripts/inbox/prescan.py` (`DEFAULT_LOG_DIR` + docstring), capture `AGENTS.md.tmpl` (`~/second-brain` line ~565), and the deployed `AGENTS.md`/`TOOLS.md`/`TOOLS.md.tmpl` copies (reconcile to `/home/kgale/second-brain/agents/logs/`).
- **Sequencing/depends-on**: none.
- **Risks**: `~` ambiguity — must use the absolute `/home/kgale/...`, never `~`, since the writer runs as `claude`. `file_inbox_quality_issue.py:37` already uses the correct path (leave as the reference).

### IC-04 — Remove now-inert cwd prose + stale checkout ref

- **Purpose**: Delete instructions the guardrail makes unnecessary so prompts stay truthful.
- **Relevant requirements**: FR-003, FR-009.
- **Affected surfaces**: habits `AGENTS.md` (`cd … &&` prefixes + line ~90 "cwd matters"), capture `AGENTS.md` (line ~74 "Working dir: …"); **broadened sweep (Codex #1 M1)** across **all** felix-admin `AGENTS.md*`/`TOOLS.md*` for `~/repos/kg-automation` and `~/second-brain` write/checkout refs — confirmed extras: escalation `AGENTS.md:265`, tasker `AGENTS.md:283` + `TOOLS.md:30`. **Do NOT touch** the `_private/` boundary references.
- **Sequencing/depends-on**: **must follow IC-01 deploy + verification gate** — removing "you must cd" prose before the env guardrail is proven live would reintroduce the bug with no safety net.
- **Risks**: agent-prompt audited surface; keep edits prose/path-only. Distinguish log-path refs (repoint) from checkout refs (repoint to `/home/claude/kg-automation`) from `_private` boundary refs (leave).

### IC-05 — One-time office2 data migration + stray-dir decommission

- **Purpose**: Move the two live state files, preserve historical logs into the vault, then remove `/home/claude/second-brain/`.
- **Relevant requirements**: FR-005, FR-008; C-003 (Tier-2), NFR-003 (manifest-driven).
- **Affected surfaces**: new `scripts/deploy/migrate-inbox-state-and-logs.py` (built on `scripts/deploy/lib/snapshot|verify|tier`); new `deploys/queued/000N-…yaml` (pre: snapshot-verify; post: assert new-path files present + correct ownership/modes + stray dir gone).
- **Sequencing/depends-on**: state-file copy must be present (with correct perms, FR-012) at the new path **before** IC-02's readers rely on it.
- **Cutover safety (Codex #1 H1 — corrected)**: the earlier "notes carry `status: processed`, so worst case is re-evaluation" claim is **overbroad** — `prescan.py` treats missing/unknown frontmatter as *unprocessed*, so the ledger is the sole dedup guard for that class → an empty ledger during the window **can** cause duplicate routing. Therefore make cutover **atomic**: the migration copies/merges state **before** any code that reads the new path can run (manifest `pre`/ordering guarantees it), and/or ship a one-release transitional new→old read-fallback with an explicit removal forcing function (no-vestiges rule). Add tests for the malformed/missing-frontmatter case where the ledger is the only guard.
- **Decommission safety (Codex #1 H2)**: do **not** blind-`rm`. Inventory the entire stray tree, classify + copy every path with size/count verification, **quarantine-rename** (`/home/claude/second-brain.quarantine-<ts>`), verify, and remove only if nothing unclassified remains. Note the stray `agents/logs/` has per-agent subdirs (enrichment, felix-admin-*, …) beyond top-level `*.md`, per live probe — the copy must recurse.

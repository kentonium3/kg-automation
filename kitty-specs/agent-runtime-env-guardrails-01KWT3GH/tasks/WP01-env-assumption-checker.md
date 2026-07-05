---
work_package_id: WP01
title: Shared env-assumption checker + unit tests
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-007
- NFR-001
tracker_refs: []
planning_base_branch: feat/agent-runtime-env-guardrails
merge_target_branch: feat/agent-runtime-env-guardrails
branch_strategy: Planning artifacts for this mission were generated on feat/agent-runtime-env-guardrails. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/agent-runtime-env-guardrails unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
agent: claude
history:
- 2026-07-05 authored from plan IC-01 (+ post-plan Codex fixes)
agent_profile: python-pedro
authoritative_surface: scripts/openclaw/agents/env_assumptions.py
create_intent:
- scripts/openclaw/agents/env_assumptions.py
- scripts/openclaw/agents/tests/test_env_assumptions.py
execution_mode: code_change
model: claude-sonnet-4-6
owned_files:
- scripts/openclaw/agents/env_assumptions.py
- scripts/openclaw/agents/tests/test_env_assumptions.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your agent profile: run `/ad-hoc-profile-load python-pedro`
(role: implementer). Then read this WP top to bottom.

## Objective

Deliver `scripts/openclaw/agents/env_assumptions.py` — the single deterministic detector that
classifies each invocation in an agent prompt as compliant (canonical form) or a violation.
Both downstream consumers (the Test-CI fleet guard, WP05; the workspace validator fold, WP05)
import THIS module. Plus its unit tests over fixtures (green immediately — they do NOT scan
the live fleet).

**Read first**: `../data-model.md` (Finding/ViolationKind, canonical forms, the recognizer),
`../contracts/checker-contract.md` (public API, waiver mechanism), `../research.md` R-02/R-03
(the cd-form and recognizer decisions, incl. the Codex HIGH-1/HIGH-3/MED-2 rationale).

**Python 3.11-compatible, stdlib only** (Test CI runs 3.11; no 3.12-only syntax). Deterministic:
no network, no subprocess, no env reads, no clock (NFR-001).

## Subtasks

### T001 — Finding + ViolationKind
- `@dataclass(frozen=True) class Finding`: `path: str`, `line: int` (1-based, starting line of
  the logical command), `kind: ViolationKind`, `snippet: str`, `remediation: str`.
- `class ViolationKind(enum.Enum)`: `BARE_M_SCRIPTS`, `HARDCODED_CD`, `HARDCODED_ABS_PATH`,
  `HOME_RELATIVE_WRITE`. See data-model.md for exact definitions. **`HARDCODED_ABS_PATH` covers
  BOTH `python` and `python3`** (Codex MED-1).

### T002 — Logical-command recognizer (Codex HIGH-1 + MED-2)
Operate on logical commands, not raw lines:
- Join backslash-continued lines and fenced ```bash/```sh blocks into one logical command;
  remember the STARTING line number.
- Extract invocation candidates from BOTH fenced commands AND **inline single-backtick spans in
  prose** — capture's real commands are inline imperatives, e.g. `AGENTS.md:78` "Invoke
  `python3 -m scripts.inbox.prescan`". Do NOT restrict to fenced blocks or first-token lines.
- A candidate is an invocation iff it contains a **concrete** `-m scripts.<mod>` OR a
  `python`/`python3 <abs>/scripts/<file>.py` path.
- EXCLUDE (never flag): candidates whose module/path holds an unresolved `<placeholder>` (e.g.
  `python3 -m scripts.inbox.<helper>`, capture `:74` — documentation of the pattern); HTML
  comments (`<!-- … -->`).

### T003 — Classification (cd-form compliance predicate + detectors)
- **Compliant** iff the invocation's repo-root reference is `${PYTHONPATH...}` guarded with
  `:?` (fail-loud) AND it contains no hardcoded `/home/claude/kg-automation` (or sibling
  checkout) literal. Canonical: `cd "${PYTHONPATH:?…}" && python3 -m scripts.X.Y` /
  `cd "${PYTHONPATH:?…}" && python3 scripts/….py` / `python "${PYTHONPATH:?…}/scripts/….py"`.
- Detect `BARE_M_SCRIPTS` (a `-m scripts.` with no `${PYTHONPATH…}` guard in its logical
  command), `HARDCODED_CD` (`cd <hardcoded checkout>`), `HARDCODED_ABS_PATH`
  (`python`/`python3 <hardcoded checkout>/scripts/….py`), `HOME_RELATIVE_WRITE` (write sink to
  a `~`/`$HOME` path; a READ of `~/.openclaw/…` is NOT flagged).
- Each Finding carries a `remediation` string naming the canonical form (NFR-004).

### T004 — Waivers
- A line may carry `# env-guard: waive <ViolationKind> — <reason>` (same or preceding line).
  Waived candidates are excluded from Findings but returned in a separate counted list so
  waivers are VISIBLE, never silent (see contract).

### T005 — Public API
- `scan_text(text: str, path: str = "<memory>") -> list[Finding]`
- `scan_file(path: Path) -> list[Finding]`
- `scan_agents_root(root: Path) -> list[Finding]` — scan every `AGENTS.md` and `AGENTS.md.tmpl`
  under the agents root, EXCLUDING the retired `felix-doc-auditor` workspace (reuse
  `validate_workspace.EXCLUDED` — import it; do not duplicate the set).
- A `_default_root()` mirroring validate_workspace's, and a `main(argv)` that prints findings +
  exits non-zero on any non-waived finding (handy for ad-hoc scans).

### T006 — Unit tests (`tests/test_env_assumptions.py`)
Fixtures (inline strings, NOT the live fleet) pinning: each ViolationKind true-positive; each
canonical-form true-negative; the must-not-flag set (`<helper>` placeholder line; `<!-- … -->`
comment); an inline-imperative TP ("Invoke `python3 -m scripts.inbox.prescan`"); a
backslash-continuation multiline TP; a `python` (not `python3`) abs-path TP; the two #656 seed
shapes (NFR-003); waiver parsing. Assert determinism (same input → same output).

## Branch Strategy
Planning/base + merge target: `feat/agent-runtime-env-guardrails`. Execution worktree is
allocated for this WP's lane from `lanes.json` at implement time — do not create it manually.

## Definition of Done
- `env_assumptions.py` implements the full contract; `pytest scripts/openclaw/agents/tests/test_env_assumptions.py`
  green; no network/subprocess/env/clock; Python 3.11-compatible.
- Reused `validate_workspace.EXCLUDED` (no duplicated exclusion set).
- All six subtasks' behaviors covered by a fixture.

## Reviewer guidance
- Verify the recognizer flags capture's INLINE imperative commands (not just fenced) and does
  NOT flag the `<helper>` placeholder or HTML comments (Codex HIGH-1 — the make-or-break point).
- Verify multiline/continuation joining (Codex MED-2) and `python`+`python3` coverage (MED-1).
- Verify the compliance predicate accepts the cd form and rejects bare/hardcoded (HIGH-3).
- Confirm determinism and stdlib-only / 3.11-compat.

# Research — Agent runtime-env guardrails

Phase 0 output. Resolves the open design questions before Phase 1 design. Findings are
grounded in a live scan of `scripts/openclaw/agents/**` (2026-07-05).

## R-01 — Scope: which invocation shapes are in scope (Decision D1)

- **Decision**: In scope = BOTH `python3 -m scripts.<pkg>` invocations AND
  `python3 /home/claude/kg-automation/scripts/…py` absolute-path invocations.
- **Rationale**: #658's third concern axis is "which of office2's two checkouts is the
  checkout." A live scan shows that axis manifests in TWO shapes, not one: hardcoded `cd
  /home/claude/kg-automation && …` (habits) and direct `python3
  /home/claude/kg-automation/scripts/…py` (calendar, tasker, habits, `.tmpl`s). Converting
  only the `-m scripts.` set would leave the abs-path invocations as residual cruft on the
  same axis — contrary to the operator's "no cruft in this area" goal.
- **Alternatives**: hold to the literal `-m scripts.` set (rejected — leaves the axis
  half-cleared, needs a follow-up).

## R-02 — Canonical anchor form (Decision D2)

- **Decision**: Reuse the gateway-declared `PYTHONPATH` (= repo root, set by the #656
  drop-in `deploys/applied/0006-gateway-pythonpath-dropin.yaml`) as the explicit,
  fail-loud root anchor. No new env var, no gateway/systemd change.
- **Canonical forms**:
  - `-m scripts.` form (retain the module form per C-003):
    ```bash
    PYTHONPATH="${PYTHONPATH:?PYTHONPATH not set — run under openclaw-gateway or export the kg-automation checkout root}" python3 -m scripts.<pkg>.<mod> [args]
    ```
    Preferred over `cd "${PYTHONPATH:?…}" && python3 -m …` because it does NOT change cwd,
    so cwd-relative arguments the agent passes (tempfiles, `--content-file <path>`) are
    unaffected. Both forms are acceptable to the guard; the non-cd form is the documented
    default.
  - abs-path form (de-hardcode the checkout):
    ```bash
    python3 "${PYTHONPATH:?…}/scripts/<path>.py" [args]
    ```
- **Why this honors the constraints**: no hardcoded checkout (C-003 sibling); works under
  the gateway (PYTHONPATH set) and fails LOUD outside it (`:?`) rather than silently
  picking the wrong cwd/checkout — the #656 failure mode inverted from silent to explicit;
  portable to any checkout (set PYTHONPATH to whichever root).
- **Known trade-off (Codex-review target)**: reusing `PYTHONPATH` assumes it is a
  SINGLE path (the repo root). If PYTHONPATH ever became a colon-list, `${PYTHONPATH}/scripts/…`
  would break. In this deployment it is a single path (`/home/claude/kg-automation`). The
  checker MAY additionally assert single-path PYTHONPATH at the guard. A dedicated
  `FELIX_REPO_ROOT` var would be semantically cleaner but was rejected (D2) to avoid a
  gateway-unit change / extra deploy+audited surface (DIRECTIVE_024 locality).
- **Alternatives**: `git rev-parse --show-toplevel` (rejected — fails when cwd has drifted
  OUTSIDE the repo, i.e. the exact #656 scenario); add `FELIX_REPO_ROOT` (rejected per D2).

## R-03 — Checker must distinguish commands from prose (false-positive avoidance)

- **Decision**: The checker classifies only **actual command invocations**, not prose
  mentions or documentation of the pattern.
- **Rationale**: agent prompts document the pattern in prose — e.g. capture line 74:
  "Invoke via `python3 -m scripts.inbox.<helper>` form" — and in comments (`<!-- helper at
  /home/claude/kg-automation/scripts/inbox/prescan.py -->`). Flagging those would be the
  v323 **F4 mis-flag class** (an example bullet mistaken for a finding). The checker must
  therefore only evaluate lines that are real shell commands.
- **Approach**: treat a line as an invocation candidate when it is a shell-command line
  (inside a fenced ```bash/```sh block, or a line whose leading non-whitespace token is
  `python3`/`python`/`cd` followed by the invocation), and EXCLUDE inline-code spans in
  prose (single-backtick mentions with surrounding sentence text), HTML comments, and
  `<placeholder>`-bearing template illustrations. The exact recognizer is specified in
  `data-model.md`; fixtures in IC-02 pin both the true-positive and the
  must-not-flag-prose cases.

## R-04 — Fleet inventory (ground truth, 2026-07-05)

`grep` over `scripts/openclaw/agents/`:

| Agent | `-m scripts.` | invocation style | abs-path `python3 /home/claude/...` |
|---|---|---|---|
| felix-admin-capture | 14 (AGENTS.md) + 1 (.tmpl) | **bare** | prescan/handle_*/append_* in `.tmpl` |
| felix-admin-escalation | 7 | **bare** (indented) | — |
| felix-admin-habits | 5 | **hardcoded `cd …`** | felix-file-issue.py ×3 |
| felix-admin-tasker | 2 + `.tmpl` | **bare** | log_action.py (+ `.tmpl`) |
| felix-admin-calendar | 0 | — | log_action.py ×3, validate_calendar_event.py |
| felix-doc-auditor | 0 | (scripts-first driver, no live agent) | — |
| main | 0 | — | (verify during audit) |

Implications: conversion targets = capture, habits, escalation, tasker (+ `.tmpl`s); calendar
is audit-that-becomes-conversion (abs-path only); doc-auditor is retired (excluded set in
`validate_workspace.py`), main needs an audit pass.

## R-05 — `~`/HOME **write** sub-class is already clean

- **Finding**: agent-prompt writes to the vault use ABSOLUTE `/home/kgale/second-brain/…`
  paths (post-#659 repoint), not `~`-relative. The remaining `~` references are READS
  (`~/.openclaw/skills/…`, permitted) or the `_private/` never-touch prohibition. No
  `~`/HOME-relative WRITE was found in the current prompts.
- **Consequence**: FR-006 is a **confirm-clean audit** with the guard asserting the absence
  going forward, not a conversion. The guard still implements `~`/HOME-write detection
  (NFR-003 requires the fixture) so the class cannot re-enter.

## R-06 — `.tmpl` ↔ rendered lockstep

- **Finding**: capture and tasker carry `AGENTS.md.tmpl` sources; a rendered `AGENTS.md`
  fixed without its `.tmpl` regresses on the next render (the v323 lesson — WP02 there
  found a stale inline-Edit finalize in a `.tmpl`).
- **Decision**: every conversion edits BOTH the `.tmpl` and the rendered `AGENTS.md`; the
  guard scans `.tmpl` files too so drift is caught in CI.

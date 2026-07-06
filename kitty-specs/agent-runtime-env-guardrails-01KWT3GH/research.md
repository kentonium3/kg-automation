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

## R-02 — Canonical anchor form (Decision D2, refined post-Codex)

- **Decision**: Reuse the gateway-declared `PYTHONPATH` (= repo root, set by the #656
  drop-in `deploys/applied/0006-gateway-pythonpath-dropin.yaml`) as the explicit,
  fail-loud root anchor. No new env var, no gateway/systemd change.
- **Canonical form — the `cd` form (REVISED per Codex HIGH-3):**
  - `-m scripts.` form (retain the module form per C-003):
    ```bash
    cd "${PYTHONPATH:?PYTHONPATH not set — run under openclaw-gateway or export the kg-automation checkout root}" && python3 -m scripts.<pkg>.<mod> [args]
    ```
  - abs-path form (de-hardcode the checkout; covers BOTH `python` and `python3` per MED-1):
    ```bash
    cd "${PYTHONPATH:?…}" && python3 scripts/<path>.py [args]     # or: python "${PYTHONPATH:?…}/scripts/<path>.py"
    ```
- **Why the cd form, not the non-cd form (Codex HIGH-3).** An earlier draft preferred
  `PYTHONPATH="${PYTHONPATH:?}" python3 -m …` (no cd) to preserve cwd. Codex correctly
  observed that fixes IMPORTS but leaves **cwd drift intact** — a helper doing relative
  file I/O, or receiving a cwd-relative path arg, still breaks from a drifted cwd (the very
  #656 failure mode). The `cd "${PYTHONPATH}"` form makes cwd DETERMINISTIC (repo root),
  fixing both imports and cwd in one move. **Companion requirement:** helper path arguments
  MUST be absolute (tempfiles under `/tmp`, absolute vault paths) — which the live prompts
  already satisfy; a WP smoke test runs representative converted helpers from a **non-repo
  cwd** (e.g. `/tmp`) to prove cwd-independence.
- **"Works without the gateway" — reconciled semantics (Codex HIGH-2).** The spec's
  "works with or without the gateway" is made precise: the canonical form works (a) under
  `openclaw-gateway.service` (PYTHONPATH set by #656), OR (b) with an explicitly-exported
  `PYTHONPATH` when run outside the gateway; and (c) **fails LOUD** (`:?`) — never
  silent-wrong / wrong-checkout — when neither holds. Fail-loud IS the designed
  out-of-gateway behavior (the operator's "allow for running outside the gateway" intent is
  "don't silently break," not "magically resolve with zero env"). Spec FR-005 + SC wording
  updated to say so.
- **Known trade-off (still a review target)**: reusing `PYTHONPATH` assumes a SINGLE path
  (the repo root). If it ever became a colon-list, `cd "${PYTHONPATH}"` and
  `${PYTHONPATH}/scripts/…` break. In this deployment it is a single path
  (`/home/claude/kg-automation`); the checker asserts single-path PYTHONPATH usage in its
  fixtures. A dedicated `FELIX_REPO_ROOT` var would be semantically cleaner but was rejected
  (D2) to avoid a gateway-unit change / extra deploy+audited surface (DIRECTIVE_024).
- **Alternatives**: non-cd form (rejected per HIGH-3 above); `git rev-parse --show-toplevel`
  (rejected — fails when cwd has drifted OUTSIDE the repo); add `FELIX_REPO_ROOT` (rejected
  per D2).

## R-03 — Checker must distinguish real commands from documentation (REVISED per Codex HIGH-1)

- **Decision**: The checker classifies **actual command invocations, including inline
  imperative commands in prose**, and excludes only genuine documentation-of-the-pattern.
- **The trap Codex caught (HIGH-1).** An earlier draft said "exclude inline-code spans in
  prose." But capture's REAL operational commands ARE inline-backtick imperatives —
  `AGENTS.md:78` "Invoke `python3 -m scripts.inbox.prescan`", `:82`, `:90`, `:94-96`,
  `:113`, `:115`, `:127`, `:131`, `:135`, `:152`, `:221` — not fenced blocks. Excluding
  inline spans would **false-green ~14 of capture's invocations** while SC-003 claims all
  are converted. The fenced-vs-inline axis is the WRONG discriminator.
- **The right discriminator = concrete-invocation vs placeholder/doc.** Flag an inline or
  fenced backtick command when it contains a **concrete** `-m scripts.<mod>` or
  `<abs>/scripts/<file>.py` invocation, whether introduced by an imperative
  ("Invoke `…`", "route → `…`", "For each …: `…`") or standing alone. EXCLUDE only:
  - lines whose invocation carries an unresolved `<placeholder>` in the module/path
    position (e.g. capture `:74` "`python3 -m scripts.inbox.<helper>` form" — the `<helper>`
    marks it as documentation of the pattern), and
  - HTML comments (`<!-- … -->`).
- **Multiline / continuation handling (MED-2).** Commands span backslash continuations and
  pipelines (capture `.tmpl:68-69`, habits `:93-94`, escalation `:136-137`, tasker
  `:142-144`). The recognizer joins backslash-continued lines (and fenced-bash blocks) into
  ONE logical command before classifying, and reports the STARTING line — so a hardcoded
  path or canonical prefix split across a continuation is not missed or double-counted.
- Fixtures in IC-02 pin: each true-positive (inline imperative + fenced + multiline), the
  `<helper>` placeholder true-negative, the HTML-comment true-negative, and a
  continuation-spanning command. This is the v323 **F4 mis-flag class** handled in both
  directions (don't miss real commands; don't flag docs).

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

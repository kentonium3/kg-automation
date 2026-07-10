---
work_package_id: WP01
title: Alert bus library (schema · render · delivery · CLI · shim)
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-005
- FR-008
tracker_refs:
- kentonium3/kg-automation#701
planning_base_branch: feat/unified-alert-bus
merge_target_branch: feat/unified-alert-bus
branch_strategy: Planning artifacts for this mission were generated on feat/unified-alert-bus. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into feat/unified-alert-bus unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
- T006
- T007
agent: "claude:opus:reviewer-renata:reviewer"
shell_pid: "99631"
history:
- at: '2026-07-10T11:30:00Z'
  actor: spec-kitty agent mission tasks
  event: WP created from /spec-kitty.tasks
agent_profile: python-pedro
authoritative_surface: scripts/common/alert_bus/
create_intent:
- scripts/common/alert_bus/__init__.py
- scripts/common/alert_bus/model.py
- scripts/common/alert_bus/render.py
- scripts/common/alert_bus/delivery.py
- scripts/common/alert_bus/__main__.py
- scripts/common/alert_bus.sh
- tests/common/alert_bus/__init__.py
- tests/common/alert_bus/test_model.py
- tests/common/alert_bus/test_render.py
- tests/common/alert_bus/test_delivery.py
- tests/common/alert_bus/test_cli.py
execution_mode: code_change
owned_files:
- scripts/common/alert_bus/__init__.py
- scripts/common/alert_bus/model.py
- scripts/common/alert_bus/render.py
- scripts/common/alert_bus/delivery.py
- scripts/common/alert_bus/__main__.py
- scripts/common/alert_bus.sh
- tests/common/alert_bus/__init__.py
- tests/common/alert_bus/test_model.py
- tests/common/alert_bus/test_render.py
- tests/common/alert_bus/test_delivery.py
- tests/common/alert_bus/test_cli.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Before reading anything else, load your assigned profile via `/ad-hoc-profile-load python-pedro`
(or your harness's profile loader). It carries your identity, governance scope, and boundaries.

## Objective

Build the **`felix-alert` bus** — the single shared library every Felix component will call to send an
ntfy alert — plus its CLI and bash shim. This WP is the foundation; WP02–WP04 migrate emitters onto the
public API you define here. No emitter code is touched in this WP.

Read first: `../spec.md`, `../plan.md` (Technical Context + IC-01..04), `../research.md` (D2/D3/D4/D6/D7/D8/D10),
`../data-model.md` (Alert / Severity / SEVERITY_MAP / AlertResult), `../contracts/alert-bus-api.md`.

## Context

- **Home**: `scripts/common/` is the repo's cross-domain shared-library package (holds `state_log`,
  `vikunja_client`). The bus is a new **package** `scripts/common/alert_bus/` so model/render/delivery
  are each unit-testable to ≥90%.
- **Transport**: `curl` via `subprocess` (no new dependency — every existing emitter already uses curl).
- **No auth**: ntfy topics are public-subscribe; security is topic secrecy. Do not add auth headers.
- **Invocation**: importable as `from scripts.common.alert_bus import emit, Alert, Severity, AlertResult`
  and runnable as `python3 -m scripts.common.alert_bus`.

## Subtasks

### T001 — `model.py`: Alert, Severity, SEVERITY_MAP, AlertResult
- `Severity` enum: `INFO < WARN < ERROR < CRITICAL` (string values `info|warn|error|critical`).
- `SEVERITY_MAP: dict[Severity, tuple[priority, tags]]` per data-model.md:
  `info→("low","information_source")`, `warn→("default","warning")`, `error→("high","rotating_light")`,
  `critical→("max","rotating_light,sos")`.
- `Alert` dataclass: `source, severity, title, description` (required, non-empty — raise `ValueError` in
  `__post_init__` if any is empty); `action: str|None=None`; `details: dict[str,str]=field(default_factory=dict)`;
  `timestamp: datetime` defaulted at construction (UTC-aware).
- `AlertResult` dataclass: `ok: bool`, `reason: str|None=None`, `topic_configured: bool=True`.

### T002 — `render.py`: title/body rendering
- `render_title(alert) -> str` and `render_body(alert) -> str`.
- Body includes, in order: timestamp as **UTC + local**, `source`, `severity`, a blank line, the
  `description`, then `Action: <action>` only if `action` is set, then a `Details:` block of
  `key=value` lines for each `details` entry (omit the block entirely if `details` is empty — NFR-003).
- **Redact before truncate**: run values through the redactor, then truncate to a bounded length
  (reuse `scripts/deploy/felix-deployer/_verify.redact_secrets`; import it, or if awkward across the
  package boundary, factor a thin shared redactor — keep behavior identical). Never emit a placeholder
  for an absent optional field.

### T003 — `delivery.py`: topic resolution + POST + fail-safe
- `resolve_topic() -> str` reads `FELIX_ALERT_NTFY_TOPIC` from env (stripped). Blank → treated as
  missing by `emit()`.
- `deliver(alert) -> AlertResult`: if topic blank → `AlertResult(ok=False, reason="NTFY_MISSING_TOPIC",
  topic_configured=False)` (no POST). Else POST to `https://ntfy.sh/<topic>` via
  `subprocess.run(["curl","--silent","--show-error","--fail","--max-time","10","--data-binary","@-",
  "-H",f"Title: {title}","-H",f"Priority: {priority}","-H",f"Tags: {tags}", url], input=body, timeout=…)`.
  Map curl failures to `AlertResult(ok=False, reason=…)` (e.g. `CURL_TIMEOUT`, `CURL_CONNECT`,
  `CURL_HTTP`). **Never raise** — catch `subprocess.TimeoutExpired`/`OSError` and return a result.
- Base URL a module constant (default `https://ntfy.sh`), overridable via env for tests.

### T004 — `__init__.py`: public API
- Export `emit`, `Alert`, `Severity`, `AlertResult`. `emit(alert) -> AlertResult` = render + deliver;
  it is the ONLY entry point callers use. Never raises.

### T005 — `__main__.py`: CLI
- `argparse` with subcommands `emit` and `self-test`.
- `emit`: `--source --severity {info,warn,error,critical} --title --description [--action]
  [--detail key=value ...] [--detail-stdin] [--strict]`. Build an `Alert`, call `emit()`, log the
  `AlertResult`. **Exit 0 by default** (best-effort); with `--strict`, exit non-zero when `not ok`.
  `--detail-stdin` folds piped text into `details["stdin"]`.
- `self-test`: emit a known `info` alert; **exit non-zero if not delivered** (it exists to prove the path).
- Ensure `python3 -m scripts.common.alert_bus <sub> …` runs this (a package `__main__.py`).

### T006 — `alert_bus.sh`: bash shim
- `#!/usr/bin/env bash`, `set -uo pipefail` (NOT `-e` — best-effort).
- **Source the topic env-file if present**: `[ -f /home/claude/.config/felix/alert-bus/env ] && . /home/claude/.config/felix/alert-bus/env`.
- Then `cd /home/claude/kg-automation && python3 -m scripts.common.alert_bus "$@"` (proven checkout-cd
  form; office2 has only `python3` — never bare `python`).
- **Always exit 0** after attempting (best-effort at the shell boundary), so cron/audit callers never
  fail regardless of `|| true` discipline. Make it executable (`chmod +x`) — a felix-deploy lesson:
  scripts invoked directly must carry the executable bit.

### T007 — Unit tests (≥90% line+branch)
- `tests/common/alert_bus/` package. Mock `subprocess.run` — **no live ntfy**.
- Cover: severity map completeness; Alert validation (empty required field raises); render with/without
  action + details (NFR-003); redaction-before-truncation; topic missing → `NTFY_MISSING_TOPIC` no POST;
  curl rc≠0 / timeout → `ok=False` no raise (NFR-001); CLI exit-code semantics (best-effort vs `--strict`
  vs `self-test`); `--detail-stdin` folding. Aim module coverage ≥90% and do not lower the repo gate.

## Branch Strategy

Planning base and merge target are both `feat/unified-alert-bus`. `/spec-kitty.implement` allocates this
WP's execution worktree per the computed lane in `lanes.json`; commit there. Completed work merges back
to `feat/unified-alert-bus`.

## Definition of Done

- [ ] `from scripts.common.alert_bus import emit, Alert, Severity, AlertResult` works; `emit()` never raises.
- [ ] `python3 -m scripts.common.alert_bus self-test` and `emit …` behave per the CLI contract.
- [ ] `scripts/common/alert_bus.sh` sources the env-file, uses checkout-cd `python3 -m`, is `chmod +x`, exits 0.
- [ ] Severity map, fail-safe delivery, missing-topic, and redaction all covered by tests; `pytest tests/common/alert_bus` green; module coverage ≥90%; repo coverage gate not reduced.
- [ ] No auth header; no new pip dependency; no live ntfy in tests.

## Reviewer guidance

Verify: `emit()` truly never raises (grep for uncaught paths); the severity→priority/tag map matches
data-model.md exactly; redaction runs BEFORE truncation; the shim is `set -uo pipefail` (not `-e`) and
exits 0; tests mock subprocess and assert the curl argv (flags + headers). Confirm the package is
importable as `scripts.common.alert_bus` (has `__init__.py`).

## Activity Log

- 2026-07-10T12:01:10Z – claude:sonnet:python-pedro:implementer – shell_pid=95966 – Assigned agent via action command
- 2026-07-10T12:10:30Z – claude:sonnet:python-pedro:implementer – shell_pid=95966 – Ready for review: felix-alert bus library (model/render/delivery/CLI/shim). ruff clean (exit 0); pytest 55 passed, 100% line+branch coverage on the package.
- 2026-07-10T12:11:29Z – claude:opus:reviewer-renata:reviewer – shell_pid=99631 – Started review via action command
- 2026-07-10T12:19:25Z – user – shell_pid=99631 – Review passed (reviewer-renata): 100% cov, all DoD met, scope clean; matrix verdicts filled

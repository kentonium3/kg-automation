---
work_package_id: WP02
title: Deploy library foundation
dependencies:
- WP01
requirement_refs:
- FR-005
- FR-017
tracker_refs: []
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T006
- T007
- T008
- T009
- T010
agent: claude
history:
- ts: '2026-06-12T20:30:00Z'
  actor: spec-kitty.tasks
  event: created
agent_profile: implementer-ivan
authoritative_surface: scripts/deploy/lib/
execution_mode: code_change
mission_slug: pull-based-deploy-pipeline-01KTYQQS
owned_files:
- scripts/deploy/lib/__init__.py
- scripts/deploy/lib/cron.py
- scripts/deploy/lib/snapshot.py
- scripts/deploy/lib/verify.py
- scripts/deploy/lib/manifest.py
- scripts/deploy/lib/applied.py
- tests/deploy/test_cron.py
- tests/deploy/test_snapshot.py
- tests/deploy/test_verify.py
- tests/deploy/test_manifest.py
- tests/deploy/test_applied.py
role: implementer
tags: []
---

## ⚡ Do This First: Load Agent Profile

Invoke `/ad-hoc-profile-load implementer-ivan` BEFORE reading anything else. The profile sets your identity, governance scope, and boundaries.

## Objective

Implement the foundational primitives in the deploy library: `LibResult` return type, OpenClaw cron wrappers, Restic snapshot verification, file/content verification, manifest loading + validation, and applied-entry writing.

## Context

The library is the canonical surface for all deploy work in kg-automation going forward. Bash one-shots and the Python applier both consume it. The full API contract is at `kitty-specs/pull-based-deploy-pipeline-01KTYQQS/contracts/deploy-library-api.md` — read it first; this WP implements the modules listed in its "Public surface" section, minus `tier.py` and `apply.py` (those are WP03).

**Critical invariant (FR-017)**: the library NEVER touches `/etc/crontab` or `crontab -l`. Every cron operation routes through `openclaw cron` subcommands. CI (WP06) will grep for the literal `crontab` token in `scripts/deploy/lib/` and fail the build if any hit exists outside a comment.

## Branch Strategy

- planning_base_branch: `main`
- merge_target_branch: `main`
- Execution worktree per `lanes.json`.

## Subtask guidance

### T006 — `__init__.py` and LibResult

`scripts/deploy/lib/__init__.py`:

```python
"""Felix deploy library — vetted primitives for deploy scripts and the applier.

NEVER imports or shells to `crontab`. All cron ops route through `openclaw cron`.
See contracts/deploy-library-api.md for the full API.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Mapping

@dataclass(frozen=True)
class LibResult:
    ok: bool
    summary: str
    details: Mapping[str, Any] = field(default_factory=dict)

__all__ = ["LibResult"]
```

### T007 — `lib/cron.py` — OpenClaw cron primitives

Implement `openclaw_cron_disable(cron_name)`, `openclaw_cron_enable(cron_name)`, `openclaw_cron_edit(cron_name, payload_path=None, schedule=None)`, `openclaw_cron_list()` per `contracts/deploy-library-api.md`.

All are thin subprocess wrappers around `openclaw cron <subcommand>`. Use `subprocess.run([...], capture_output=True, text=True, check=False)`. Map non-zero exit to `LibResult(ok=False, ...)` with `details['stderr_excerpt']`. Idempotent: disable/enable are no-ops when already in target state — detect via `openclaw cron list` first.

Tests (`tests/deploy/test_cron.py`): mock `subprocess.run`; assert correct argv was constructed; assert LibResult shape on success / failure / already-in-state.

**Hard rule**: the literal token `crontab` MUST NOT appear in `cron.py` source. Any `crontab` reference must be in a COMMENT explaining the prohibition (e.g., `# DO NOT use crontab here — see kentonium3/kg-automation#162`). CI greps for this.

### T008 — `lib/snapshot.py` — Restic recency

Implement `verify_restic_recent(max_age_hours=24)`.

The `claude` user on office2 cannot query Restic directly. Per the charter Deployment Constraints, fall back to reading `/data/services/backup/logs/backup-YYYY-MM-DD.log` and looking for a "completed" line within the window. Returns `LibResult(ok=False, ...)` with a clear summary if no recent log is found.

Tests: mock filesystem reads via `pathlib.Path.read_text` + `pathlib.Path.exists`; cover (a) recent log present, (b) stale log only, (c) no log at all.

### T009 — `lib/verify.py` — File and content checks

Implement `verify_file_present(path, executable=False)`, `verify_no_stale_literal(path, literal)`, `redact_secrets(text)`.

- `verify_file_present`: `pathlib.Path.exists`; if `executable`, also check `os.access(path, os.X_OK)`.
- `verify_no_stale_literal`: read file text; assert literal substring not present. Used for confirming an old version string is gone post-deploy.
- `redact_secrets(text)`: best-effort regex pass. Strip patterns matching `[A-Za-z0-9+/]{32,}` (token-shaped substrings), `password=\S+`, `Bearer \S+`. Return new text. Conservative: better to over-redact than leak.

Tests: cover present/absent files, executable bit, stale-literal hit/miss, redact_secrets across token + password + bearer fixtures.

### T010 — `lib/manifest.py` and `lib/applied.py`

`manifest.py`:
- `load_manifest(path) -> dict` — read YAML, raise `ValueError` on parse failure
- `validate_manifest(data, schema_path=None) -> LibResult` — uses `jsonschema.Draft202012Validator`; schema_path defaults to `deploys/schema/manifest-v1.schema.json`
- `next_applied_seq() -> int` — scans `deploys/applied/*.yaml`; returns max prefix + 1, or 1 if empty

`applied.py`:
- `write_applied(manifest, apply_mode, applied_at=None) -> LibResult` — augments manifest with `apply_mode` + `applied_at` (default `now UTC`); validates against schema; writes to `deploys/applied/<NNNN>-<name>.yaml` where NNNN comes from `manifest.next_applied_seq()`

Tests cover: YAML parse error → ValueError; valid schema → ok=True; invalid schema → ok=False with error_code; write_applied creates correctly-prefixed file; concurrent next_applied_seq returns monotonic values.

CLI shim for `applied`: `python3 -m scripts.deploy.lib.applied write_applied --name <name> --apply-mode <bootstrap|manifest>`. (Used by the bootstrap wrapper in WP05.)

## Test strategy

- `pytest tests/deploy/test_cron.py tests/deploy/test_snapshot.py tests/deploy/test_verify.py tests/deploy/test_manifest.py tests/deploy/test_applied.py -v` — green
- `grep -rn '\bcrontab\b' scripts/deploy/lib/` — zero hits OR hits are all comments
- Module-as-CLI smoke: `python3 -m scripts.deploy.lib.cron openclaw_cron_list --json` returns LibResult.details['crons'] (mock the subprocess in tests)

## Definition of Done

- All 11 owned files exist
- All tests pass with subprocess mocks
- No `crontab` literal outside comments
- Each public function in `contracts/deploy-library-api.md` is implemented and tested
- `redact_secrets` is conservative enough to strip token-like substrings of length ≥32
- No deps added beyond PyYAML and jsonschema (both already in project requirements)

## Risks

- **openclaw CLI surface drift**: per memory `reference_openclaw_upgrade_gotchas`, OpenClaw's command surface has shifted across versions. Mock all subprocess calls in tests; do not call live `openclaw cron` from tests. Manual verification against `openclaw cron --help` on office2 is reasonable but not gating.
- **YAML safe-loader**: use `yaml.safe_load`, never `yaml.load` — security and stability.
- **redact_secrets false positives**: a 32-char hex hash in an error message will be redacted. That's the acceptable trade-off; document it in the function docstring.
- **Concurrent next_applied_seq()**: there's a TOCTOU window between scanning the directory and writing. The applier is `Type=oneshot` (per WP04 design), so concurrent execution shouldn't occur in production; tests should still cover deterministic ordering.

## Reviewer guidance

1. Run the static check: `grep -rn '\bcrontab\b' scripts/deploy/lib/` — must be empty or comment-only.
2. Verify every public function in `contracts/deploy-library-api.md` is present and matches the documented signature.
3. Confirm `jsonschema.Draft202012Validator` is explicitly used in `manifest.py` (not the default validator).
4. Confirm no live subprocess calls in tests — all are mocked.
5. Confirm `redact_secrets` is tested against at least 3 distinct patterns (token, password=, Bearer).

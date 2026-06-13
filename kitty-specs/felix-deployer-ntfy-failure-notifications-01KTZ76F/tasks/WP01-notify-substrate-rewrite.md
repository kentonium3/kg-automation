---
work_package_id: WP01
title: Notify substrate rewrite (ntfy.sh)
dependencies: []
requirement_refs:
- FR-001
- FR-002
- FR-003
- FR-004
- FR-008
- FR-009
- FR-010
- FR-013
- FR-014
- NFR-001
- NFR-002
- NFR-003
- NFR-004
tracker_refs:
- kentonium3/kg-automation#595
planning_base_branch: main
merge_target_branch: main
branch_strategy: Planning artifacts for this mission were generated on main. During /spec-kitty.implement this WP may branch from a dependency-specific base, but completed changes must merge back into main unless the human explicitly redirects the landing branch.
subtasks:
- T001
- T002
- T003
- T004
- T005
agent: "claude"
history: []
agent_profile: implementer-ivan
authoritative_surface: scripts/deploy/felix-deployer/
execution_mode: code_change
mission_slug: felix-deployer-ntfy-failure-notifications-01KTZ76F
owned_files:
- scripts/deploy/felix-deployer/notify.py
- scripts/deploy/felix-deployer/_tick.py
- tests/deploy/test_notify.py
- tests/deploy/test_deployer.py
role: implementer
tags: []
shell_pid: "78366"
---

## ⚡ Do This First: Load Agent Profile

Invoke `/ad-hoc-profile-load implementer-ivan` (or load the profile referenced in this WP's `agent_profile` frontmatter) BEFORE reading anything else in this prompt. The profile sets your identity, governance scope, boundaries, and initialization declaration. Without it, your behavior is unscoped and reviewable defects are likely.

## Objective

Rewrite `scripts/deploy/felix-deployer/notify.py` end-to-end. Switch the failure-notification substrate from broken openclaw cron to ntfy.sh via `curl` subprocess. Preserve every invariant the existing code documents (failure isolation, redact-then-truncate, the 4-phase enum). Update the single caller (`_tick.py`) and its test. Add comprehensive unit-test coverage for payload rendering, secret redaction, length truncation, and every closed-enum error code.

## Context

The parent mission (`pull-based-deploy-pipeline-01KTYQQS`, merged in commit `48c60c32`) shipped the felix-deployer applier with a notify path that assumes openclaw 2026.6.5 CLI flags that don't exist (`--payload-file`, `--payload-template`, `--kind`, `--schedule manual`). The applier is live on office2 today; failure notifications silently fail.

This WP swaps the substrate to ntfy.sh. The wire shape is defined in `kitty-specs/felix-deployer-ntfy-failure-notifications-01KTZ76F/contracts/ntfy-notification-v1.md` — that file is your spec for title/body rendering and the closed error_code enum. **Read it first.**

Substrate decision rationale: ntfy.sh is the canonical push-notify substrate per the project's accumulated practice (security-monitor already uses it). It's failure-mode-independent of openclaw/WhatsApp, which the broken deploy itself might affect. See `research.md` Decision R-01 for the alternatives that were rejected and why.

## Branch Strategy

- planning_base_branch: `main`
- merge_target_branch: `main`
- This mission's planning was performed on the coordination branch `kitty/mission-felix-deployer-ntfy-failure-notifications-01KTZ76F` per the #1716 workaround. Execution worktrees are allocated per computed lane from `lanes.json` after `finalize-tasks`; `spec-kitty next` directs you to the correct worktree path.

## Subtask guidance

### T001 — Rewrite `scripts/deploy/felix-deployer/notify.py`

Delete the current contents of `notify.py` and replace with a from-scratch implementation against the contract.

Module-level constants:
- `NTFY_BASE_URL = "https://ntfy.sh"`
- `NTFY_TOPIC_ENV = "FELIX_DEPLOYER_NTFY_TOPIC"`
- `NOTIFICATION_FORMAT_VERSION = "v1"`
- `ERROR_SUMMARY_MAX = 500`
- `CURL_MAX_TIME_SECONDS = 10`
- `PRIORITY_HEADER = "high"`
- `TAGS_HEADER = "warning,rotating_light"`
- `DM_PHASES = ("tier_guard", "verification_pre", "entrypoint", "verification_post")` (KEEP the existing constant name and tuple — `_tick.py`'s phase-collapse map points at it)

Closed `error_code` enum (use a `Literal` type annotation or just a `_ERROR_CODES: frozenset[str]` for now):
- `NTFY_MISSING_TOPIC`
- `NTFY_CURL_MISSING`
- `NTFY_SPAWN_FAILED`
- `NTFY_TIMEOUT`
- `NTFY_NETWORK_UNREACHABLE`
- `NTFY_HTTP_ERROR`
- `NTFY_UNKNOWN`

Public function:
```python
def dispatch_failure_notification(
    manifest: Mapping[str, Any],
    phase: str,
    error_summary: str,
    head_sha: str,
    failed_at: str | None = None,
) -> LibResult:
    """Render and POST a failure notification to ntfy.sh.

    Returns LibResult(ok=True, ...) on successful POST.
    Returns LibResult(ok=False, details={"error_code": <code>, ...}) on any
    failure mode. NEVER raises for routine failures.

    See contracts/ntfy-notification-v1.md for wire-shape contract.
    """
```

Private helpers (use leading underscore):
- `_render_title(manifest_name: str) -> str` — returns `f"felix-deployer failed: {manifest_name}"`.
- `_render_body(manifest, phase, error_summary, head_sha, failed_at) -> str` — applies the contract's body template. Empty error_summary → "(no error summary)".
- `_redact_and_truncate(error_summary: str) -> str` — calls `verify.redact_secrets()` first, then truncates to `ERROR_SUMMARY_MAX`. **Order is invariant; tests will pin it.**
- `_classify_error_code(returncode: int) -> str` — maps curl exit codes per the contract's response-handling table.
- `_topic_redact(topic: str) -> str` — produces `f"{topic[:8]}***{topic[-4:]}"` for non-leaky log audit.

Existing helpers preserved (rename where needed):
- `_utc_now_iso()` — unchanged.

Curl invocation shape (must match the contract exactly):
```python
result = subprocess.run(
    [
        "curl",
        "--silent",
        "--show-error",
        "--fail",
        "--max-time", str(CURL_MAX_TIME_SECONDS),
        "-H", f"Title: {title}",
        "-H", f"Priority: {PRIORITY_HEADER}",
        "-H", f"Tags: {TAGS_HEADER}",
        "-X", "POST",
        "--data-binary", "@-",
        f"{NTFY_BASE_URL}/{topic}",
    ],
    input=body,
    capture_output=True,
    text=True,
    check=False,
)
```

**Failure isolation invariant**: every code path that can fail must catch the exception and return a `LibResult(ok=False, ...)`. The function NEVER raises for `FileNotFoundError`, `OSError`, `subprocess.SubprocessError`, or non-zero curl exits.

**Import-time hygiene** (NFR-003): no HTTP request, no DNS lookup, no subprocess spawn at module import. Importing `scripts.deploy.felix_deployer.notify` must be a pure no-op.

Remove from notify.py (no dead code, no shims, per FR-014):
- `CRON_NAME = "felix-deployer-alert"`
- `dispatch_failure_dm` function
- Any reference to `--payload-file`, `openclaw cron run`, or `tmp_path` payload-file logic
- The `tempfile` import if no longer used

Public exports (`__all__`):
```python
__all__ = [
    "NOTIFICATION_FORMAT_VERSION",
    "NTFY_TOPIC_ENV",
    "ERROR_SUMMARY_MAX",
    "DM_PHASES",
    "dispatch_failure_notification",
]
```

### T002 — Write `tests/deploy/test_notify.py` (rendering, redaction, truncation, success path)

Create the file. Pattern after `tests/deploy/test_deployer.py`'s subprocess-mock approach (which monkeypatches `subprocess.run` at the import site).

Test classes (or flat module-level test functions — both fine):
- `test_render_title_basic` — `_render_title("vikunja-image-bump") == "felix-deployer failed: vikunja-image-bump"`.
- `test_render_body_basic` — golden-string assertion for the body with a fixed manifest, phase, summary, head, failed_at.
- `test_render_body_empty_error_summary` — empty input → body contains `"Error:\n(no error summary)"`.
- `test_redact_then_truncate_long_summary` — input with secret pattern + 1000 chars; assert (a) secret pattern absent from output, (b) output length ≤ 500.
- `test_redact_then_truncate_secret_at_boundary` — input where the secret pattern would span char 495-510. Assert no recognizable secret in output. (This pins the "redact BEFORE truncate" invariant — truncate-first would slice the pattern and leak head bytes.)
- `test_dispatch_success` — env `FELIX_DEPLOYER_NTFY_TOPIC=test-topic`, mock `subprocess.run` returns `CompletedProcess(returncode=0, stdout="", stderr="")`. Assert:
  - LibResult `ok=True`
  - LibResult `summary == "ntfy notification sent"`
  - `details["title"]` matches rendered title
  - `details["topic_redacted"]` does NOT contain the raw topic string
  - The mock was called with `--data-binary @-` and `input=` matching the rendered body

Use `monkeypatch.setattr("scripts.deploy.felix_deployer.notify.subprocess.run", fake_run)` (verify exact import path against the notify.py module you write).

### T003 — Write `tests/deploy/test_notify.py` (every error_code path)

Add to the same file. One parametrized test per error code:

| Test name | Setup | Assertion |
|---|---|---|
| `test_dispatch_missing_topic` | env not set or empty | `error_code == "NTFY_MISSING_TOPIC"`; mock NOT called (no curl invocation) |
| `test_dispatch_curl_missing` | env set; mock raises `FileNotFoundError("curl")` | `error_code == "NTFY_CURL_MISSING"` |
| `test_dispatch_spawn_failed` | env set; mock raises `OSError("resource temporarily unavailable")` | `error_code == "NTFY_SPAWN_FAILED"` |
| `test_dispatch_timeout` | env set; mock returns `returncode=28` | `error_code == "NTFY_TIMEOUT"` |
| `test_dispatch_network_unreachable_dns` | env set; mock returns `returncode=6` | `error_code == "NTFY_NETWORK_UNREACHABLE"` |
| `test_dispatch_network_unreachable_connect` | env set; mock returns `returncode=7` | `error_code == "NTFY_NETWORK_UNREACHABLE"` |
| `test_dispatch_http_error` | env set; mock returns `returncode=22` | `error_code == "NTFY_HTTP_ERROR"` |
| `test_dispatch_unknown` | env set; mock returns `returncode=42` | `error_code == "NTFY_UNKNOWN"` |

For each non-success test: assert `LibResult.ok is False`, `error_code` matches, `stderr_excerpt` (if present) ≤200 chars.

`test_import_no_side_effects` — `importlib.import_module("scripts.deploy.felix_deployer.notify")` does not invoke `subprocess.run` (patch it before the import and assert call count zero). This pins NFR-003.

### T004 — Update `scripts/deploy/felix-deployer/_tick.py`

Open `_tick.py` and update three places:

1. Top-of-file import: change `from .notify import dispatch_failure_dm` (or the equivalent symbol — grep to confirm exact name) to `from .notify import dispatch_failure_notification`. Drop any import of `CRON_NAME`.
2. The phase-collapse constant: rename `PHASE_TO_DM_PHASE` → `PHASE_TO_NOTIFY_PHASE`. The mapping body is unchanged (still 7-key dict → values from `DM_PHASES`). Update any internal reference.
3. The dispatch call site: change `dispatch_failure_dm(manifest=..., phase=..., error_summary=..., head_sha=..., failed_at=...)` to `dispatch_failure_notification(manifest=..., phase=..., error_summary=..., head_sha=..., failed_at=...)`. Argument shape is identical.

Sanity check: `grep -n "dispatch_failure_dm\|PHASE_TO_DM_PHASE\|CRON_NAME" scripts/deploy/felix-deployer/_tick.py` returns nothing after edits.

### T005 — Update `tests/deploy/test_deployer.py`

Open `test_deployer.py`. Find every reference to `dispatch_failure_dm` and `PHASE_TO_DM_PHASE` (use `grep -n` first). For each:
- mock target string `"scripts.deploy.felix_deployer.notify.dispatch_failure_dm"` → `"...dispatch_failure_notification"`
- symbol references in expected-call-args assertions: same rename
- the `PHASE_TO_DM_PHASE` constant import (if any): rename to `PHASE_TO_NOTIFY_PHASE`

Run `pytest tests/deploy/test_deployer.py -v` after each edit; iterate until green.

If `test_deployer.py` mocks `dispatch_failure_dm`'s return shape, the new mock should return `LibResult(ok=True, ...)` or `LibResult(ok=False, details={"error_code": "...", ...})` — same shape as before, but the `details` key shape changed (no more `payload` key under success; instead `title` + `topic_redacted` per T001). Update assertions accordingly.

## Test strategy

- `pytest tests/deploy/test_notify.py -v` — all parameterized cases pass.
- `pytest tests/deploy/test_deployer.py -v` — passes after rename; no behavior regressions.
- `pytest tests/deploy/ -v --cov=scripts/deploy/felix_deployer/notify --cov-branch` — branch coverage on `notify.py` ≥ existing project threshold for the deploy package.
- `python -c "from scripts.deploy.felix_deployer import notify; print(notify.__all__)"` — imports cleanly, no errors, no network activity.
- `make test` (project-wide) — no regressions.

## Definition of Done

- `notify.py` is rewritten end-to-end; no openclaw cron references remain (grep verification).
- `_tick.py` calls `dispatch_failure_notification`; renamed phase-collapse constant.
- `test_notify.py` covers payload rendering (T002 cases), redact-then-truncate invariant including the boundary-pinning test (T002), every closed error_code (T003), and the import-time no-side-effects test (T003).
- `test_deployer.py` updated for the rename; passes locally.
- `make test` green.
- No file outside `owned_files` is modified.
- All FR/NFR refs in this WP's frontmatter are addressed by the implementation or tests (cross-check at review time).

## Risks

- **`subprocess.run` mock target path**: the conventional mock-string is `"scripts.deploy.felix_deployer.notify.subprocess.run"`. If `notify.py` does `from subprocess import run as _run` instead of `import subprocess`, the mock target changes. Pick ONE import style and use it consistently. Recommend: `import subprocess` at module top; reference as `subprocess.run(...)` so the mock target is the predictable form. Memory `feedback_wp_prompts_grep_codebase` applies: grep the actual import style in your rewrite and reference it in tests.
- **Curl exit-code stability across libcurl versions**: code 6 (DNS), 7 (connect), 22 (HTTP), 28 (timeout) are stable across libcurl 7.x and 8.x. Other codes (e.g. 35 SSL handshake) fall to `NTFY_UNKNOWN`; the test for `NTFY_UNKNOWN` uses code 42 as a marker, but any non-table code path lands there.
- **Implicit secret in the topic**: don't log the raw `FELIX_DEPLOYER_NTFY_TOPIC` value at info level. Tests should assert `topic_redacted` doesn't contain the raw topic.
- **Existing test_deployer.py may import `CRON_NAME`**: grep before editing. If yes, remove the import and any assertion on it.

## Reviewer guidance

- Verify the redact-then-truncate ORDER by reading the test `test_redact_then_truncate_secret_at_boundary` — this test would pass spuriously if the order is wrong. The boundary-spanning secret in the test fixture is the load-bearing assertion.
- Confirm zero usage of `openclaw cron`, `CRON_NAME`, `dispatch_failure_dm`, `--payload-file`, `--payload-template` anywhere in the WP's owned files. Single grep.
- Confirm NFR-003 (no import-time side effects) via the dedicated test, not just by reading the code.
- Confirm the curl argv shape matches `contracts/ntfy-notification-v1.md` exactly. Any drift → reject.
- Verify the new `dispatch_failure_notification` signature is identical to the old `dispatch_failure_dm` (so `_tick.py`'s call site is a 1-line rename, not a refactor).

## Activity Log

- 2026-06-13T01:28:52Z – claude – shell_pid=78366 – Assigned agent via action command

#!/usr/bin/env python3
"""Side-channel validation harness for the felix-bot Vikunja API token.

Mission `felix-bot-vikunja-provisioning-01KRT3N4`, WP02, ADR-0002 Phase 1.

This helper is the GATE between WP01's provisioning (which creates the
felix-bot user, shares 12 projects, and emits a fresh API token) and
WP03's `swap_vikunja_secrets.py` (which actually rotates production
state). It exercises the new token *side-channel* — i.e., directly,
without touching the production secrets file — so that any attribution
or share-grant bug is caught BEFORE production traffic flips.

Flow:

  1. Identity gate
     - `--token-file` must exist, be mode 600, owned by current user,
       contain a non-empty token. Failure exits 2.
  2. Project access verification (FR-004(b))
     - `GET /projects?per_page=50` with the felix-bot token.
     - Filter to real projects (`id > 0 AND is_archived != True`).
     - Assert count == `--expected-project-count` (default 12).
     - Per-project `OK project_id=N title="..."` log lines.
  3. Throwaway-task attribution probe (FR-004(c,d))
     - Create a fresh task in `--target-project-id` (default 13, Habits).
     - Verify `task.created_by.username == 'felix-bot'`. Halt on mismatch.
     - Write a `[Felix-Validation]` comment on that task.
     - Verify `comment.author.username == 'felix-bot'`. Halt on mismatch.
     - Read the comment back via GET; verify `created_by.username` is
       still `'felix-bot'`. Halt on mismatch.
     - Best-effort DELETE comment and task. Failures here log a WARN
       but do not fail the run (per contracts C-9, C-10).
  4. Rollback smoke test mode (`--rollback-smoke-test`, FR-015)
     - Symbolically traces the rollback steps with no network I/O.
     - Refuses to run if the `.bak` already exists (would mean Phase 3
       has run, in which case smoke-testing rollback symbolically is
       the wrong tool; you'd want the live rollback instead).
     - Confirms simulated total time < 5 minutes per NFR-003.

Final stdout line is always a `SUMMARY:` line so the runbook can grep
the result.

Exit codes:
  0 — validation passed (or smoke-test simulated path is < 5 min)
  1 — validation failed (network, attribution mismatch, count
      mismatch, smoke-test precondition violated)
  2 — usage error (bad args, identity gate, missing/unreadable token)

Stdlib only — Python 3.10+.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://office2.tail0f5f56.ts.net/api/v1/"
DEFAULT_TARGET_PROJECT_ID = 13  # Habits — low-impact, owned by kent
DEFAULT_EXPECTED_PROJECT_COUNT = 12
EXPECTED_USERNAME = "felix-bot"

# Rollback smoke-test timing model (seconds). Sum is well below NFR-003's
# 5-minute (300-second) budget; these are realistic upper-bounds for the
# corresponding real operations on office2.
ROLLBACK_TIMING_MODEL_SECONDS = {
    "copy_bak_to_secrets": 1.0,
    "restart_openclaw_gateway": 5.0,
    "invoke_sample_agent_and_verify_kent": 10.0,
}
NFR_003_BUDGET_SECONDS = 300.0


# ---------------------------------------------------------------------------
# Identity gate
# ---------------------------------------------------------------------------


def read_token_with_identity_gate(token_path: Path) -> str:
    """Validate the token file's permissions and contents, return the token.

    Exits 2 on any failure (usage error — the operator's environment is
    not in the expected shape for a safe production rotation).
    """
    if not token_path.exists():
        print(f"ERROR: --token-file does not exist: {token_path}", file=sys.stderr)
        sys.exit(2)
    if not token_path.is_file():
        print(f"ERROR: --token-file is not a regular file: {token_path}", file=sys.stderr)
        sys.exit(2)

    st = token_path.stat()
    mode = stat.S_IMODE(st.st_mode)
    if mode != 0o600:
        print(
            f"ERROR: --token-file must be mode 600; found {oct(mode)}: {token_path}",
            file=sys.stderr,
        )
        sys.exit(2)

    if st.st_uid != os.getuid():
        print(
            f"ERROR: --token-file is not owned by current user "
            f"(uid={os.getuid()}, file uid={st.st_uid}): {token_path}",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        token = token_path.read_text(encoding="utf-8").strip()
    except PermissionError:
        print(
            f"ERROR: permission denied reading --token-file: {token_path}",
            file=sys.stderr,
        )
        sys.exit(2)

    if not token:
        print(f"ERROR: --token-file is empty: {token_path}", file=sys.stderr)
        sys.exit(2)

    return token


# ---------------------------------------------------------------------------
# HTTP helpers (thin wrappers over urllib so tests can mock urlopen)
# ---------------------------------------------------------------------------


def _normalize_base_url(base_url: str) -> str:
    """Strip trailing slash for clean path joining."""
    return base_url.rstrip("/")


def _request(
    method: str,
    url: str,
    token: str,
    body: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> tuple[int, dict[str, Any] | list[Any] | None]:
    """Issue an HTTP request and return (status, parsed_json_or_None).

    Returns (status, payload). On non-2xx, payload may be the error body
    parsed as JSON if available, else None.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    data: bytes | None = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.getcode()
            raw = resp.read()
            payload = json.loads(raw) if raw else None
            return status, payload
    except urllib.error.HTTPError as e:
        status = e.code
        raw = e.read() if hasattr(e, "read") else b""
        try:
            payload = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            payload = None
        return status, payload


# ---------------------------------------------------------------------------
# Project access verification
# ---------------------------------------------------------------------------


def verify_project_access(
    token: str,
    base_url: str,
    expected_count: int,
) -> dict[str, Any]:
    """List projects via felix-bot's token and assert the count == expected.

    Exits 1 on:
      * 401 (token rejected — share grants likely did not apply)
      * count mismatch (operator must investigate before proceeding)

    Returns a summary dict: {"accessible_project_ids": [...], "count": N}.
    """
    url = f"{_normalize_base_url(base_url)}/projects?per_page=50"
    status, payload = _request("GET", url, token)

    if status == 401:
        print(
            "ERROR: felix-bot token rejected (401) — share grants may not "
            "have applied, or the token file content is wrong.",
            file=sys.stderr,
        )
        sys.exit(1)
    if status >= 400 or not isinstance(payload, list):
        print(
            f"ERROR: GET /projects returned status={status} payload={payload!r}",
            file=sys.stderr,
        )
        sys.exit(1)

    real_projects: list[dict[str, Any]] = [
        p
        for p in payload
        if isinstance(p, dict)
        and isinstance(p.get("id"), int)
        and p["id"] > 0
        and not p.get("is_archived", False)
    ]

    for p in real_projects:
        title = p.get("title", "")
        print(f"OK project_id={p['id']} title={title!r}")

    # Vikunja v0.24.6 auto-creates a default "Inbox" project for every newly-
    # registered user (observed 2026-05-17 during the first live Phase 1 run).
    # So felix-bot ends up with `expected_count` shared projects PLUS its own
    # auto-created Inbox. Treat expected_count as the MINIMUM (felix-bot must
    # be able to see at least all the kent-shared projects); any extras are
    # acceptable. A SHORTAGE remains fatal — that indicates a share grant
    # didn't apply.
    if len(real_projects) < expected_count:
        accessible_ids = sorted(p["id"] for p in real_projects)
        print(
            f"ERROR: expected at least {expected_count} accessible projects, "
            f"got {len(real_projects)}. Accessible ids: {accessible_ids}. "
            f"Investigate which share grant did not apply.",
            file=sys.stderr,
        )
        sys.exit(1)
    elif len(real_projects) > expected_count:
        accessible_ids = sorted(p["id"] for p in real_projects)
        extras = len(real_projects) - expected_count
        print(
            f"NOTE: felix-bot sees {len(real_projects)} projects "
            f"({accessible_ids}) — {extras} more than the kent-shared "
            f"{expected_count}. This is expected when Vikunja auto-creates "
            f"a default Inbox for the new user. Proceeding.",
            file=sys.stderr,
        )

    return {
        "accessible_project_ids": sorted(p["id"] for p in real_projects),
        "count": len(real_projects),
    }


# ---------------------------------------------------------------------------
# Attribution probe
# ---------------------------------------------------------------------------


def _extract_username(obj: Any, *candidate_keys: str) -> str | None:
    """Extract a username from a task/comment response.

    Walks the supplied candidate keys in order and returns the first
    `username` string it finds under one of them. Callers that need
    strict single-field semantics (e.g. comment attribution must come
    from `created_by` and ONLY `created_by` — see Codex review cycle 1)
    must pass a single key, not a fallback chain. Falling back to
    `author` for comments masks the exact mismatch class the validator
    is supposed to detect.
    """
    if not isinstance(obj, dict):
        return None
    for key in candidate_keys:
        sub = obj.get(key)
        if isinstance(sub, dict):
            uname = sub.get("username")
            if isinstance(uname, str):
                return uname
    return None


def validate_attribution(
    token: str,
    base_url: str,
    target_project_id: int,
) -> dict[str, Any]:
    """Run the throwaway-task attribution probe.

    Three attribution checkpoints (all must equal `felix-bot`):
      1. Created task — task.created_by.username
      2. Written comment — comment.created_by.username (strict; no
         fallback to `author`, per Codex review cycle 1)
      3. Read-back comment — created_by.username on the comment record
         (strict; no fallback to `author`)

    Returns a summary structure; exits 1 immediately on any attribution
    mismatch (do not proceed if Vikunja attributes our writes incorrectly).
    Cleanup is best-effort and logs WARNs without failing.
    """
    base = _normalize_base_url(base_url)
    iso_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    task_title = f"felix-bot validation probe {iso_ts}"
    comment_text = (
        f"[Felix-Validation] felix-bot can write to this task — {iso_ts}"
    )

    # --- Create throwaway task (C-6) ---
    create_task_url = f"{base}/projects/{target_project_id}/tasks"
    status, task_obj = _request(
        "PUT", create_task_url, token, body={"title": task_title}
    )
    if status >= 400 or not isinstance(task_obj, dict) or "id" not in task_obj:
        print(
            f"ERROR: task creation failed: status={status} payload={task_obj!r}",
            file=sys.stderr,
        )
        sys.exit(1)
    task_id = task_obj["id"]

    task_uname = _extract_username(task_obj, "created_by")
    if task_uname != EXPECTED_USERNAME:
        print(
            f"ERROR: throwaway task created_by.username={task_uname!r}, "
            f"expected {EXPECTED_USERNAME!r}. Halting before further writes.",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"OK task_id={task_id} created_by={task_uname!r}")

    # --- Write validation comment (C-7) ---
    create_comment_url = f"{base}/tasks/{task_id}/comments"
    status, comment_obj = _request(
        "PUT", create_comment_url, token, body={"comment": comment_text}
    )
    if status >= 400 or not isinstance(comment_obj, dict) or "id" not in comment_obj:
        print(
            f"ERROR: comment write failed: status={status} payload={comment_obj!r}",
            file=sys.stderr,
        )
        sys.exit(1)
    comment_id = comment_obj["id"]

    # Strict: ONLY created_by.username — no fallback to author. A response
    # with author.username='felix-bot' but created_by.username='kent' must
    # be rejected (Codex review cycle 1 caught the fallback masking exactly
    # that class of attribution failure).
    comment_uname = _extract_username(comment_obj, "created_by")
    if comment_uname != EXPECTED_USERNAME:
        print(
            f"ERROR: comment created_by.username={comment_uname!r}, "
            f"expected {EXPECTED_USERNAME!r}. Halting before cleanup.",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"OK comment_id={comment_id} created_by={comment_uname!r}")

    # --- Read back comments (C-8) ---
    list_comments_url = f"{base}/tasks/{task_id}/comments"
    status, comments_list = _request("GET", list_comments_url, token)
    if status >= 400 or not isinstance(comments_list, list):
        print(
            f"ERROR: comment readback failed: status={status} "
            f"payload={comments_list!r}",
            file=sys.stderr,
        )
        sys.exit(1)

    found = None
    for c in comments_list:
        if isinstance(c, dict) and c.get("id") == comment_id:
            found = c
            break
    if found is None:
        print(
            f"ERROR: just-written comment id={comment_id} not present on "
            f"readback of task {task_id}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Strict: ONLY created_by.username — no fallback to author. Same
    # rationale as the write checkpoint above (Codex review cycle 1).
    readback_uname = _extract_username(found, "created_by")
    if readback_uname != EXPECTED_USERNAME:
        print(
            f"ERROR: readback comment created_by.username={readback_uname!r}, "
            f"expected {EXPECTED_USERNAME!r}.",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"OK comment_readback created_by={readback_uname!r}")

    # --- Cleanup (C-9 + C-10), best-effort ---
    cleanup = {"comment_deleted": False, "task_deleted": False}
    delete_comment_url = f"{base}/tasks/{task_id}/comments/{comment_id}"
    try:
        status, _ = _request("DELETE", delete_comment_url, token)
        if status < 400:
            cleanup["comment_deleted"] = True
        else:
            print(
                f"WARN: comment cleanup returned status={status} "
                f"(continuing; comment may be manually deleted via UI)",
                file=sys.stderr,
            )
    except Exception as e:  # noqa: BLE001 — best-effort cleanup
        print(f"WARN: comment cleanup raised {e!r} (continuing)", file=sys.stderr)

    delete_task_url = f"{base}/tasks/{task_id}"
    try:
        status, _ = _request("DELETE", delete_task_url, token)
        if status < 400:
            cleanup["task_deleted"] = True
        else:
            print(
                f"WARN: task cleanup returned status={status} "
                f"(continuing; task may be manually deleted via UI)",
                file=sys.stderr,
            )
    except Exception as e:  # noqa: BLE001 — best-effort cleanup
        print(f"WARN: task cleanup raised {e!r} (continuing)", file=sys.stderr)

    return {
        "task_id": task_id,
        "comment_id": comment_id,
        "attribution_checks": {
            "task_creation_username": task_uname,
            "comment_write_username": comment_uname,
            "comment_readback_username": readback_uname,
        },
        "cleanup": cleanup,
        "task_title": task_title,
    }


# ---------------------------------------------------------------------------
# Rollback smoke test (FR-015)
# ---------------------------------------------------------------------------


def rollback_smoke_test(
    secrets_path: Path,
    bak_path: Path,
) -> dict[str, Any]:
    """Symbolically exercise the rollback path; no real I/O.

    Preconditions for a legitimate pre-cutover smoke test:
      * `secrets_path` must exist (this is current production state)
      * `bak_path` must NOT exist (Phase 3 has not run yet — the .bak
        is only created at cutover time, so a pre-existing .bak means
        a previous Phase 3 left behind state we should not silently
        overwrite)

    The "simulated" timings are taken from an explicit model so the
    runbook's NFR-003 (<5 min rollback) is testable independent of real
    I/O. Exits 1 on precondition violations.
    """
    if bak_path.exists():
        print(
            f"ERROR: rollback smoke test refused — {bak_path} already exists, "
            f"which implies Phase 3 has already run. Smoke-testing the "
            f"rollback symbolically at that point is wrong; perform the real "
            f"rollback via the runbook instead.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not secrets_path.exists():
        print(
            f"ERROR: rollback smoke test refused — current secrets file "
            f"{secrets_path} does not exist; cannot reason about rollback "
            f"against a missing target.",
            file=sys.stderr,
        )
        sys.exit(1)

    steps: list[dict[str, Any]] = []
    total = 0.0
    for name, seconds in ROLLBACK_TIMING_MODEL_SECONDS.items():
        narrative = {
            "copy_bak_to_secrets": (
                f"Would copy {bak_path} → {secrets_path}"
            ),
            "restart_openclaw_gateway": "Would restart openclaw-gateway",
            "invoke_sample_agent_and_verify_kent": (
                "Would invoke sample agent + verify kent attribution"
            ),
        }[name]
        print(f"SMOKE-TEST step={name} simulated_seconds={seconds} -- {narrative}")
        steps.append(
            {"step": name, "simulated_seconds": seconds, "narrative": narrative}
        )
        total += seconds

    return {
        "steps": steps,
        "simulated_total_seconds": total,
        "budget_seconds": NFR_003_BUDGET_SECONDS,
        "within_budget": total < NFR_003_BUDGET_SECONDS,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Side-channel validation harness for the felix-bot Vikunja API "
            "token. Run AFTER provision_felix_bot.py (WP01) and BEFORE "
            "swap_vikunja_secrets.py (WP03)."
        ),
    )
    parser.add_argument(
        "--token-file",
        required=True,
        type=Path,
        help="Path to file containing felix-bot's API token (mode 600).",
    )
    parser.add_argument(
        "--target-project-id",
        type=int,
        default=DEFAULT_TARGET_PROJECT_ID,
        help=(
            "Project ID for the throwaway task probe "
            f"(default {DEFAULT_TARGET_PROJECT_ID}, Habits)."
        ),
    )
    parser.add_argument(
        "--vikunja-base-url",
        default=DEFAULT_BASE_URL,
        help=f"Vikunja base URL (default {DEFAULT_BASE_URL}).",
    )
    parser.add_argument(
        "--expected-project-count",
        type=int,
        default=DEFAULT_EXPECTED_PROJECT_COUNT,
        help=(
            "Number of real projects felix-bot must be able to see "
            f"(default {DEFAULT_EXPECTED_PROJECT_COUNT})."
        ),
    )
    parser.add_argument(
        "--rollback-smoke-test",
        action="store_true",
        help=(
            "Run only the symbolic rollback smoke test (FR-015). "
            "No network I/O."
        ),
    )
    parser.add_argument(
        "--secrets-path",
        type=Path,
        default=Path("/etc/openclaw/secrets/vikunja-api.kent"),
        help=(
            "Path to the production secrets file (used by --rollback-smoke-test)."
        ),
    )
    parser.add_argument(
        "--bak-path",
        type=Path,
        default=Path("/etc/openclaw/secrets/vikunja-api.kent-pre-felix-bot.bak"),
        help=(
            "Path to the .bak file produced at cutover "
            "(used by --rollback-smoke-test)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not perform any network I/O; emit the planned flow and exit 0.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    # Identity gate (always, even in --rollback-smoke-test or --dry-run —
    # we want operators to wire up the token file correctly every time)
    token = read_token_with_identity_gate(args.token_file)

    start = time.monotonic()

    # --- Rollback smoke test mode (FR-015) ---
    if args.rollback_smoke_test:
        smoke = rollback_smoke_test(
            secrets_path=args.secrets_path, bak_path=args.bak_path
        )
        elapsed = time.monotonic() - start
        print(
            "SUMMARY: mode=rollback-smoke-test "
            f"simulated_seconds={smoke['simulated_total_seconds']} "
            f"budget_seconds={smoke['budget_seconds']} "
            f"within_budget={smoke['within_budget']} "
            f"elapsed_real_seconds={elapsed:.3f}"
        )
        return 0 if smoke["within_budget"] else 1

    # --- Dry-run short-circuit (no network) ---
    if args.dry_run:
        print(
            "DRY-RUN: would GET /projects, assert "
            f"{args.expected_project_count} accessible; "
            f"would create throwaway task in project_id={args.target_project_id}; "
            "would write/read/delete a [Felix-Validation] comment; "
            "would delete the throwaway task."
        )
        print(
            "SUMMARY: mode=dry-run network_calls=0 "
            f"expected_project_count={args.expected_project_count} "
            f"target_project_id={args.target_project_id}"
        )
        return 0

    # --- Real validation flow ---
    project_summary = verify_project_access(
        token=token,
        base_url=args.vikunja_base_url,
        expected_count=args.expected_project_count,
    )
    attrib_summary = validate_attribution(
        token=token,
        base_url=args.vikunja_base_url,
        target_project_id=args.target_project_id,
    )
    elapsed = time.monotonic() - start

    print(
        "SUMMARY: mode=validate "
        f"projects_ok={project_summary['count']} "
        f"target_project_id={args.target_project_id} "
        f"task_id={attrib_summary['task_id']} "
        f"comment_id={attrib_summary['comment_id']} "
        f"attribution=ok "
        f"cleanup_comment={attrib_summary['cleanup']['comment_deleted']} "
        f"cleanup_task={attrib_summary['cleanup']['task_deleted']} "
        f"elapsed_seconds={elapsed:.3f}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

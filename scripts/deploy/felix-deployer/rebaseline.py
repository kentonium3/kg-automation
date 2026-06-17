"""Deferred-confirm rebaseline engine for felix-deployer (#618 / WP02).

Implements the C1–C5 contract from
``kitty-specs/auto-rebaseline-on-deploy-01KVAYJN/contracts/rebaseline-lifecycle-v1.md``.

Lifecycle summary
-----------------
- **observe(pre, post)** — Called after each ``git pull``. Computes the
  pulled range; if audited-surface patterns matched, writes/merges the
  pending token and returns ``pending_set``. Returns ``not_required`` when
  nothing matched or heads are equal (C1).
- **reconcile(...)** — Called each tick when a pending token exists. Runs the
  read-only audit, classifies drift, and dispatches C3 rebaseline on
  expected drift, leaving the token on ``unexpected_drift`` / inconclusive (C2).
- **rebaseline_and_verify(...)** — Runs the delete-then-regenerate command,
  counts the regenerated baseline FILES in the baselines directory, and
  verifies the audit reports clean. Returns ``completed`` or ``failed``; never
  raises to the caller (C3).

Import note
-----------
``tooling/scripts/audited_surfaces.py`` is not a package — the directory
carries no ``__init__.py``. We replicate the pattern used by sibling scripts
in this repo (e.g. ``check_audited_surface_drift.py``, see line 37 of that
file): ``sys.path.insert(0, str(TOOLING_SCRIPTS_DIR))`` followed by a plain
``from audited_surfaces import ...``.  The import is done lazily at the
bottom of this file (after the ``sys.path`` mutation) so tests that stub
``audited_surfaces`` can insert their stub BEFORE the module-level import.

Audit-shell contract (DIRECTIVE_031 — verified against in-repo audit.sh)
-------------------------------------------------------------------------
Verified by reading ``scripts/office2/security-monitor/audit.sh`` directly.

Clean run (no drift):
  - exit code 0
  - stdout: ``Security audit YYYY-MM-DD: All clear``  (single line)

Drifted run (one or more baselines changed):
  - exit code 1
  - stdout includes one line per drifted baseline:
      ``[ALERT] <baseline-name> changed since baseline: <diff>``
    (produced by the ``alert()`` shell function via ``tee`` to stdout)

The exit code is the primary signal: 0 → D=∅; 1 → parse ``[ALERT] <name>``
first token from stdout into D.  Entirely unparseable/ambiguous output
(e.g., empty stdout on exit 0/1 with no recognisable markers) → inconclusive.

Command derivation (F3):
  felix-deployer runs ON office2, so the SSH wrapper in the registry's
  ``rebaseline_command`` must be stripped.  The registry stores the operator
  form used from the Mac:
      ssh office2-claude 'rm /data/.../baselines/* && sg docker -c /data/.../scripts/audit.sh'
  We extract the inner single-quoted string and parse it locally.  The
  read-only audit uses only ``sg docker -c /data/.../scripts/audit.sh``
  (baselines present → diff-only, no regeneration).  The full rebaseline
  uses ``rm <baselines>/* && sg docker -c <audit.sh>`` run via ``sh -c``.

Baseline count verification (F2):
  After regeneration we count files in the baselines directory on disk
  (``ls <baselines_dir>``), NOT stdout lines.  The baselines directory is
  injectable for tests via the ``baselines_dir`` parameter.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import pathlib
import re
import subprocess
import sys
from typing import Any, Callable

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths — injectable for tests
# ---------------------------------------------------------------------------

DEFAULT_STATE_DIR = pathlib.Path("/data/services/felix-deployer/state")
DEFAULT_TOKEN_PATH = DEFAULT_STATE_DIR / "rebaseline-pending.json"
DEFAULT_BASELINES_DIR = pathlib.Path("/data/services/security-monitor/baselines")

# Stale-token alert threshold (seconds).  24 h matches the daily-audit cycle.
MAX_AGE_SECONDS: int = 86_400

# ---------------------------------------------------------------------------
# Tooling-scripts path bootstrap so ``audited_surfaces`` resolves
# ---------------------------------------------------------------------------

_HERE = pathlib.Path(__file__).resolve().parent  # felix-deployer/
_REPO_ROOT = _HERE.parents[2]                   # kg-automation/
_TOOLING_SCRIPTS = _REPO_ROOT / "tooling" / "scripts"

if str(_TOOLING_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_TOOLING_SCRIPTS))

# Late import after sys.path bootstrap (same pattern as check_audited_surface_drift.py).
from audited_surfaces import (  # noqa: E402  # type: ignore[import-not-found]
    load_audited_surfaces,
    match_surfaces,
)

# ---------------------------------------------------------------------------
# Outcome constants
# ---------------------------------------------------------------------------

OUTCOME_NOT_REQUIRED = "not_required"
OUTCOME_PENDING_SET = "pending_set"
OUTCOME_COMPLETED = "completed"
OUTCOME_CLEARED_CLEAN = "cleared_clean"
OUTCOME_UNEXPECTED_DRIFT = "unexpected_drift"
OUTCOME_FAILED = "failed"
OUTCOME_STALE = "stale"
OUTCOME_INCONCLUSIVE = "inconclusive"

# ---------------------------------------------------------------------------
# T4 — Pending-token store (atomic)
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1

_TokenDict = dict[str, Any]


def read_token(token_path: pathlib.Path | None = None) -> _TokenDict | None:
    """Return the parsed token dict, or ``None`` if absent or unreadable.

    Absent file == nothing pending (data-model.md invariant).
    Malformed JSON is treated as absent (logged at WARNING level) so a
    corrupt token never crashes the tick.
    """
    path = token_path if token_path is not None else DEFAULT_TOKEN_PATH
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(text)
    except (OSError, json.JSONDecodeError) as exc:
        _log.warning("rebaseline: could not read token at %s: %s", path, exc)
        return None


def write_token(token: _TokenDict, token_path: pathlib.Path | None = None) -> None:
    """Atomically write *token* to *token_path* (``.tmp`` + ``os.replace``).

    Creates the parent directory if needed.  On OS failure the error is
    logged and swallowed so the tick continues.
    """
    path = token_path if token_path is not None else DEFAULT_TOKEN_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(token, indent=2, default=str), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        _log.error("rebaseline: failed to write token to %s: %s", path, exc)


def clear_token(token_path: pathlib.Path | None = None) -> None:
    """Remove the pending token.  No-op if already absent."""
    path = token_path if token_path is not None else DEFAULT_TOKEN_PATH
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        _log.warning("rebaseline: failed to clear token at %s: %s", path, exc)


# ---------------------------------------------------------------------------
# T5 — Observe
# ---------------------------------------------------------------------------

RunnerFn = Callable[[list[str]], subprocess.CompletedProcess[str]]


def _default_git_runner(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["git", *args],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def _utc_now_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def observe(
    pre_pull_head: str,
    post_pull_head: str,
    *,
    token_path: pathlib.Path | None = None,
    git_runner: RunnerFn | None = None,
    registry: dict | None = None,
) -> dict[str, Any]:
    """Observe a pull range and update the pending token if needed (C1).

    Args:
        pre_pull_head: HEAD SHA before ``git pull``.
        post_pull_head: HEAD SHA after ``git pull``.
        token_path: override the default token path (tests).
        git_runner: injectable git subprocess runner (tests).
        registry: injectable audited-surfaces registry (tests/CI).

    Returns a dict with at least ``{"outcome": <str>}``.  On ``pending_set``
    the dict also contains ``surface_ids`` and ``matched_files``.
    """
    if pre_pull_head == post_pull_head:
        _log.debug("rebaseline.observe: heads equal — not_required")
        return {"outcome": OUTCOME_NOT_REQUIRED}

    runner = git_runner if git_runner is not None else _default_git_runner
    reg = registry if registry is not None else load_audited_surfaces()

    # Compute changed paths for the pulled range.
    diff_range = f"{pre_pull_head}..{post_pull_head}"
    proc = runner(["diff", "--name-only", diff_range])
    if proc.returncode != 0:
        _log.warning(
            "rebaseline.observe: git diff failed (rc=%d): %s",
            proc.returncode,
            (proc.stderr or "")[:200],
        )
        # Treat as not_required — can't determine changes; next tick retries.
        return {"outcome": OUTCOME_NOT_REQUIRED}

    changed = [line for line in proc.stdout.splitlines() if line.strip()]
    matched = match_surfaces(changed, reg)

    if not matched:
        _log.debug("rebaseline.observe: no audited-surface match — not_required")
        return {"outcome": OUTCOME_NOT_REQUIRED}

    # Union surface_ids and expected_baselines across all matched surfaces.
    new_surface_ids: set[str] = {s["id"] for s in matched}
    new_expected: set[str] = set()
    new_matched_files: set[str] = set()
    for s in matched:
        new_expected.update(s.get("affected_baselines", []))
        new_matched_files.update(s.get("matched_files", []))

    now_iso = _utc_now_iso()

    existing = read_token(token_path)
    if existing is not None:
        # Merge: union ids + baselines, keep earliest pending_since_utc,
        # refresh matched_files (replace with latest union).
        merged_surface_ids = sorted(
            new_surface_ids | set(existing.get("surface_ids", []))
        )
        merged_expected = sorted(
            new_expected | set(existing.get("expected_baselines", []))
        )
        merged_matched = sorted(
            new_matched_files | set(existing.get("matched_files", []))
        )
        pending_since = existing.get("pending_since_utc") or now_iso
        observed_head = post_pull_head
        alerts_emitted: list[str] = existing.get("alerts_emitted", [])
        last_check_utc = existing.get("last_check_utc", None)
    else:
        merged_surface_ids = sorted(new_surface_ids)
        merged_expected = sorted(new_expected)
        merged_matched = sorted(new_matched_files)
        pending_since = now_iso
        observed_head = post_pull_head
        alerts_emitted = []
        last_check_utc = None

    token: _TokenDict = {
        "schema_version": SCHEMA_VERSION,
        "pending_since_utc": pending_since,
        "observed_head_sha": observed_head,
        "surface_ids": merged_surface_ids,
        "expected_baselines": merged_expected,
        "matched_files": merged_matched,
        "last_check_utc": last_check_utc,
        "alerts_emitted": alerts_emitted,
    }
    write_token(token, token_path)

    _log.info(
        "rebaseline.observe: pending_set surfaces=%s",
        merged_surface_ids,
    )
    return {
        "outcome": OUTCOME_PENDING_SET,
        "surface_ids": merged_surface_ids,
        "matched_files": merged_matched,
    }


# ---------------------------------------------------------------------------
# Command derivation helpers
# ---------------------------------------------------------------------------

# Regex to extract the inner command from: ssh <host> '<inner>'
_SSH_INNER_RE = re.compile(r"""^ssh\s+\S+\s+'(.+)'$""", re.DOTALL)


def _strip_ssh_wrapper(cmd_str: str) -> str:
    """Extract the inner command from an ``ssh <host> '<inner>'`` wrapper.

    If the string does not match the ssh pattern it is returned unchanged
    (already a local command).

    Example::
        "ssh office2-claude 'rm .../baselines/* && sg docker -c .../audit.sh'"
        →  "rm .../baselines/* && sg docker -c .../audit.sh"
    """
    m = _SSH_INNER_RE.match(cmd_str.strip())
    if m:
        return m.group(1)
    return cmd_str


def _parse_local_commands(rebaseline_command: str) -> tuple[str, str, str]:
    """Parse the registry ``rebaseline_command`` into local path components.

    The canonical operator command (after SSH-wrapper stripping) is:
        rm /data/.../baselines/* && sg docker -c /data/.../scripts/audit.sh

    Returns:
        (baselines_glob, audit_script_path, sg_docker_prefix) where:
        - baselines_glob:      ``/data/.../baselines/*``  (the rm target)
        - audit_script_path:   ``/data/.../scripts/audit.sh``
        - sg_docker_prefix:    ``sg docker -c``  (the wrapper command)

    On parse failure returns ("", "", "") and the caller falls back to a safe
    no-op.
    """
    inner = _strip_ssh_wrapper(rebaseline_command)
    # Split on && to get [rm_part, sg_part]
    if "&&" not in inner:
        return ("", "", "")
    rm_part, _, sg_part = inner.partition("&&")
    rm_part = rm_part.strip()
    sg_part = sg_part.strip()

    # Extract baselines glob from: rm /data/.../baselines/*
    rm_tokens = rm_part.split()
    if len(rm_tokens) < 2 or rm_tokens[0] != "rm":
        return ("", "", "")
    baselines_glob = rm_tokens[-1]  # e.g. /data/services/security-monitor/baselines/*

    # Extract audit.sh path from: sg docker -c /data/.../scripts/audit.sh
    # Pattern: sg <group> -c <script>
    sg_tokens = sg_part.split()
    if len(sg_tokens) < 4 or sg_tokens[0] != "sg" or sg_tokens[2] != "-c":
        return ("", "", "")
    audit_script = sg_tokens[3]
    sg_prefix = " ".join(sg_tokens[:3])  # "sg docker -c"

    return (baselines_glob, audit_script, sg_prefix)


def _build_readonly_audit_cmd(rebaseline_command: str) -> list[str]:
    """Derive the read-only local audit command from the registry ``rebaseline_command``.

    The registry stores the operator (Mac-side) form:
        ssh office2-claude 'rm .../baselines/* && sg docker -c .../audit.sh'

    felix-deployer runs ON office2, so we strip the SSH wrapper and use only
    the ``sg docker -c <audit.sh>`` portion (baselines already present → diff-only).

    Returns an argv list suitable for ``subprocess.run``.  Falls back to
    ``["true"]`` (produces no output → inconclusive) on parse failure.
    """
    _, audit_script, sg_prefix = _parse_local_commands(rebaseline_command)
    if not audit_script:
        _log.warning(
            "rebaseline: could not parse read-only audit cmd from: %r",
            rebaseline_command,
        )
        return ["true"]
    # Build: ["sg", "docker", "-c", "/data/.../scripts/audit.sh"]
    prefix_tokens = sg_prefix.split()
    return prefix_tokens + [audit_script]


def _build_rebaseline_cmd(rebaseline_command: str) -> list[str]:
    """Convert the registry's ``rebaseline_command`` to a local argv list.

    Strips the SSH wrapper and runs the inner command (``rm ... && sg ...``)
    via ``sh -c`` so the shell handles glob expansion and ``&&`` chaining.

    Falls back to ``["true"]`` on empty/unparseable input.
    """
    inner = _strip_ssh_wrapper(rebaseline_command)
    if inner.strip():
        return ["sh", "-c", inner]
    _log.warning("rebaseline: rebaseline_command is empty or unparseable in registry")
    return ["true"]


# ---------------------------------------------------------------------------
# Audit output parser
# ---------------------------------------------------------------------------

def _parse_drifted_baselines(
    audit_stdout: str, returncode: int
) -> set[str] | None:
    """Extract the set of drifted baseline names from real audit.sh output.

    Real contract (verified from scripts/office2/security-monitor/audit.sh):

    Clean run:
      - exit code 0
      - stdout: ``Security audit YYYY-MM-DD: All clear``

    Drifted run:
      - exit code 1
      - stdout includes per-baseline lines:
          ``[ALERT] <baseline-name> changed since baseline: <diff>``
        (emitted by the shell ``alert()`` function via ``tee`` to stdout)

    The exit code is the primary signal:
      - returncode == 0 → D = ∅ (empty set, audit clean)
      - returncode == 1 → parse ``[ALERT] <name>`` lines from stdout to build D
      - other returncode → inconclusive (command failure, not an audit verdict)

    Fallback for inconclusive:
      - returncode 0 but stdout is entirely blank → inconclusive
      - returncode 1 but stdout has no ``[ALERT]`` lines and no ``All clear``
        marker → inconclusive (unexpected output format)

    Returns:
        A (possibly empty) ``set[str]`` of drifted baseline filenames, or
        ``None`` if the output is inconclusive.  An empty set means clean.
    """
    stdout = audit_stdout or ""

    if returncode == 0:
        # Clean path: stdout should contain "All clear".  Accept even if it
        # doesn't (e.g. verbose prefix lines) as long as we have a zero exit.
        # Treat completely empty stdout on exit 0 as inconclusive.
        if not stdout.strip():
            return None
        return set()  # D = ∅

    if returncode == 1:
        # Drift path: parse [ALERT] lines.
        drifted: set[str] = set()
        for raw_line in stdout.splitlines():
            line = raw_line.strip()
            if line.startswith("[ALERT]"):
                # Format: [ALERT] <name> changed since baseline: <diff>
                # Extract the first token after "[ALERT]"
                rest = line[len("[ALERT]"):].strip()
                name = rest.split()[0] if rest.split() else ""
                if name:
                    drifted.add(name)
        if not drifted:
            # exit 1 but no parseable [ALERT] lines → inconclusive
            _log.warning(
                "rebaseline: exit 1 but no [ALERT] lines found in audit output"
            )
            return None
        return drifted

    # Non-0/1 exit code → command-level failure, not an audit verdict.
    _log.warning(
        "rebaseline: unexpected audit exit code %d; treating as inconclusive",
        returncode,
    )
    return None


# ---------------------------------------------------------------------------
# Baseline file counter
# ---------------------------------------------------------------------------

def _count_baseline_files(
    baselines_dir: pathlib.Path | None,
) -> int:
    """Count the number of files in the baselines directory on disk.

    This is used after regeneration to verify that the expected number of
    baseline files were created.  We count files (not directories or symlinks)
    to match the ``ls <dir> | wc -l`` behaviour described in the runbook.

    Returns 0 if the directory does not exist or cannot be read.
    """
    d = baselines_dir if baselines_dir is not None else DEFAULT_BASELINES_DIR
    try:
        return sum(1 for p in d.iterdir() if p.is_file())
    except OSError as exc:
        _log.warning(
            "rebaseline: could not list baselines dir %s: %s", d, exc
        )
        return 0


# ---------------------------------------------------------------------------
# T6 — Reconcile (classification core)
# ---------------------------------------------------------------------------

AuditRunnerFn = Callable[[list[str]], subprocess.CompletedProcess[str]]


def _default_audit_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Run the audit command locally (no SSH — office2-local context)."""
    return subprocess.run(  # noqa: S603
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )


def reconcile(
    *,
    token_path: pathlib.Path | None = None,
    audit_runner: AuditRunnerFn | None = None,
    registry: dict | None = None,
    max_age_seconds: int = MAX_AGE_SECONDS,
    baselines_dir: pathlib.Path | None = None,
) -> dict[str, Any]:
    """Classify pending drift and act (C2).

    If no pending token exists, returns ``{"outcome": "not_required"}``.

    Args:
        token_path: injectable token path (tests).
        audit_runner: injectable audit subprocess runner (tests).
        registry: injectable audited-surfaces registry (tests).
        max_age_seconds: threshold for stale-token alert.
        baselines_dir: injectable baselines directory for file-count (tests).

    Returns a dict with at least ``{"outcome": <str>}``.  On
    ``completed`` the dict carries ``rebaselined_at_utc`` and
    ``baseline_count``.  On ``failed`` it carries ``error_summary``.
    """
    token = read_token(token_path)
    if token is None:
        return {"outcome": OUTCOME_NOT_REQUIRED}

    reg = registry if registry is not None else load_audited_surfaces()
    runner = audit_runner if audit_runner is not None else _default_audit_runner

    # Build the read-only audit command (local, no SSH wrapper).
    audit_cmd_str = reg.get("rebaseline_command", "")
    audit_cmd = _build_readonly_audit_cmd(audit_cmd_str)

    proc = runner(audit_cmd)
    now_iso = _utc_now_iso()

    # Update last_check_utc regardless of audit outcome.
    token = dict(token)
    token["last_check_utc"] = now_iso

    # Parse the audit output using exit code as primary signal.
    drifted: set[str] | None = _parse_drifted_baselines(
        proc.stdout or "", proc.returncode
    )

    if drifted is None:
        # Inconclusive — leave token, no reset.
        write_token(token, token_path)
        _log.warning(
            "rebaseline.reconcile: inconclusive audit output (rc=%d)",
            proc.returncode,
        )
        result: dict[str, Any] = {"outcome": OUTCOME_INCONCLUSIVE}
        result.update(_maybe_stale(token, token_path, now_iso, max_age_seconds))
        return result

    expected: set[str] = set(token.get("expected_baselines", []))

    if drifted == set():
        # D = ∅ → cleared_clean: delete token.
        clear_token(token_path)
        _log.info("rebaseline.reconcile: cleared_clean (D=∅)")
        return {"outcome": OUTCOME_CLEARED_CLEAN}

    if drifted <= expected:
        # D ⊆ E, D ≠ ∅ → trigger rebaseline.
        _log.info(
            "rebaseline.reconcile: expected drift D=%s E=%s → rebaseline",
            sorted(drifted),
            sorted(expected),
        )
        rbl_result = rebaseline_and_verify(
            token=token,
            drifted=drifted,
            token_path=token_path,
            audit_runner=audit_runner,
            registry=reg,
            baselines_dir=baselines_dir,
        )
        return rbl_result

    # D ⊄ E → unexpected drift (FR-009: do NOT reset).
    write_token(token, token_path)
    _log.warning(
        "rebaseline.reconcile: unexpected_drift D=%s E=%s",
        sorted(drifted),
        sorted(expected),
    )
    result = {
        "outcome": OUTCOME_UNEXPECTED_DRIFT,
        "drifted": sorted(drifted),
        "expected": sorted(expected),
        "unexpected": sorted(drifted - expected),
    }
    result.update(_maybe_stale(token, token_path, now_iso, max_age_seconds))
    return result


def _maybe_stale(
    token: _TokenDict,
    token_path: pathlib.Path | None,
    now_iso: str,
    max_age_seconds: int,
) -> dict[str, Any]:
    """Check staleness and update ``alerts_emitted`` if threshold exceeded.

    Returns a dict to merge into the caller's result (may be empty).
    Mutates *token* in place and persists it if stale alert is new.
    """
    pending_since = token.get("pending_since_utc")
    if not pending_since:
        return {}
    try:
        since_dt = _dt.datetime.fromisoformat(pending_since.replace("Z", "+00:00"))
        now_dt = _dt.datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
        age_seconds = (now_dt - since_dt).total_seconds()
    except (ValueError, TypeError):
        return {}

    if age_seconds <= max_age_seconds:
        return {}

    alerts: list[str] = list(token.get("alerts_emitted", []))
    if "stale" not in alerts:
        alerts.append("stale")
        token["alerts_emitted"] = alerts
        write_token(token, token_path)
        _log.warning(
            "rebaseline.reconcile: stale token (age=%.0fs > %ds)",
            age_seconds,
            max_age_seconds,
        )
        return {"stale": True}
    return {}


# ---------------------------------------------------------------------------
# T7 — Rebaseline + verify
# ---------------------------------------------------------------------------

def rebaseline_and_verify(
    *,
    token: _TokenDict,
    drifted: set[str],
    token_path: pathlib.Path | None = None,
    audit_runner: AuditRunnerFn | None = None,
    registry: dict | None = None,
    baselines_dir: pathlib.Path | None = None,
) -> dict[str, Any]:
    """Run the delete-then-regenerate rebaseline and verify the result (C3).

    The rebaseline command is taken from ``registry.rebaseline_command``
    (operator form with SSH wrapper; the SSH wrapper is stripped locally).
    After running it we verify:

    1. The regenerated baseline count == ``registry.expected_baseline_count``
       (counted by listing files in ``baselines_dir``, not parsing stdout).
    2. A follow-up read-only audit reports clean (D = ∅).

    On success: clear token, return ``completed`` + ``rebaselined_at_utc``.
    On failure: leave token, return ``failed`` + ``error_summary``.

    **Never raises** to the caller — all exceptions are caught and converted
    to ``failed`` outcomes.
    """
    try:
        return _rebaseline_and_verify_inner(
            token=token,
            drifted=drifted,
            token_path=token_path,
            audit_runner=audit_runner,
            registry=registry,
            baselines_dir=baselines_dir,
        )
    except Exception as exc:  # pragma: no cover — defence in depth
        _log.exception("rebaseline_and_verify: unexpected exception: %s", exc)
        return {"outcome": OUTCOME_FAILED, "error_summary": str(exc)[:500]}


def _rebaseline_and_verify_inner(
    *,
    token: _TokenDict,
    drifted: set[str],
    token_path: pathlib.Path | None,
    audit_runner: AuditRunnerFn | None,
    registry: dict | None,
    baselines_dir: pathlib.Path | None,
) -> dict[str, Any]:
    reg = registry if registry is not None else load_audited_surfaces()
    runner = audit_runner if audit_runner is not None else _default_audit_runner
    expected_count: int = reg.get("expected_baseline_count", 0)
    rebaseline_cmd_str: str = reg.get("rebaseline_command", "")

    # Build the full local rebaseline command (strip SSH wrapper, run via sh -c).
    rbl_cmd = _build_rebaseline_cmd(rebaseline_cmd_str)

    proc = runner(rbl_cmd)
    rebaselined_at = _utc_now_iso()

    if proc.returncode != 0:
        error_summary = (
            f"rebaseline command exited rc={proc.returncode}: "
            f"{(proc.stderr or '')[:400]}"
        )
        _log.error("rebaseline_and_verify: %s", error_summary)
        # Leave token — operator must intervene.
        return {"outcome": OUTCOME_FAILED, "error_summary": error_summary}

    # Verify step 1: count baseline FILES on disk (not stdout lines).
    baseline_count = _count_baseline_files(baselines_dir)
    if baseline_count != expected_count:
        error_summary = (
            f"baseline count mismatch: got {baseline_count}, "
            f"expected {expected_count}"
        )
        _log.error("rebaseline_and_verify: %s", error_summary)
        return {"outcome": OUTCOME_FAILED, "error_summary": error_summary}

    # Verify step 2: follow-up read-only audit must be clean (exit 0, D=∅).
    audit_cmd = _build_readonly_audit_cmd(rebaseline_cmd_str)
    verify_proc = runner(audit_cmd)
    post_drifted = _parse_drifted_baselines(
        verify_proc.stdout or "", verify_proc.returncode
    )

    if post_drifted is None or post_drifted != set():
        error_summary = (
            f"post-rebaseline audit not clean: "
            f"drifted={sorted(post_drifted) if post_drifted is not None else 'inconclusive'}"
        )
        _log.error("rebaseline_and_verify: %s", error_summary)
        return {"outcome": OUTCOME_FAILED, "error_summary": error_summary}

    # Success.
    clear_token(token_path)
    _log.info(
        "rebaseline_and_verify: completed at %s count=%d",
        rebaselined_at,
        baseline_count,
    )
    return {
        "outcome": OUTCOME_COMPLETED,
        "rebaselined_at_utc": rebaselined_at,
        "baseline_count": baseline_count,
    }


# ---------------------------------------------------------------------------
# Public API surface
# ---------------------------------------------------------------------------

__all__ = [
    # Constants
    "DEFAULT_STATE_DIR",
    "DEFAULT_TOKEN_PATH",
    "DEFAULT_BASELINES_DIR",
    "MAX_AGE_SECONDS",
    "SCHEMA_VERSION",
    # Outcome strings
    "OUTCOME_NOT_REQUIRED",
    "OUTCOME_PENDING_SET",
    "OUTCOME_COMPLETED",
    "OUTCOME_CLEARED_CLEAN",
    "OUTCOME_UNEXPECTED_DRIFT",
    "OUTCOME_FAILED",
    "OUTCOME_STALE",
    "OUTCOME_INCONCLUSIVE",
    # Token store
    "read_token",
    "write_token",
    "clear_token",
    # Engine
    "observe",
    "reconcile",
    "rebaseline_and_verify",
]

"""Tests for the WP02 deferred-confirm rebaseline engine (#618).

Covers every classification branch in the contract
(``rebaseline-lifecycle-v1.md``) and data-model drift rules
(D=∅, D⊆E, D⊄E, inconclusive, stale) plus token store atomicity.

All subprocess / filesystem / audited-surfaces side-effects are injected via
parameters — no real git, no office2, no ``/data`` paths touched.

Real audit.sh contract (verified from scripts/office2/security-monitor/audit.sh)
---------------------------------------------------------------------------------
Clean run (exit 0):
  stdout: "Security audit YYYY-MM-DD: All clear"

Drifted run (exit 1):
  stdout includes one line per drifted baseline:
      "[ALERT] <baseline-name> changed since baseline: <diff>"
  (produced by the shell ``alert()`` function via ``tee -a $ALERT_FILE``
  to stdout; the ``alert()`` function at line 38 of audit.sh)

_REGISTRY fixture: mirrors the REAL registry rebaseline_command WITH the
  ssh wrapper so that _strip_ssh_wrapper / _build_readonly_audit_cmd /
  _build_rebaseline_cmd are exercised end-to-end.

Import approach
---------------
``rebaseline.py`` lives under ``scripts/deploy/felix-deployer/`` — a
hyphenated directory that is not importable as a dotted Python package.
We use the same ``importlib.util.spec_from_file_location`` pattern that
``test_notify.py`` and ``test_audited_surfaces.py`` use in this repo.

The module-level ``sys.path`` mutation in ``rebaseline.py`` (adding
``tooling/scripts/``) happens at import time.  We load the module before
constructing any fixtures that need it, so ``audited_surfaces`` resolves
correctly.
"""

from __future__ import annotations

import datetime as _dt
import importlib.util
import json
import pathlib
import subprocess
import sys
from typing import Any
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Module loader — same pattern as test_notify.py
# ---------------------------------------------------------------------------

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
FELIX_DEPLOYER_DIR = REPO_ROOT / "scripts" / "deploy" / "felix-deployer"


def _load_rebaseline():
    """Import rebaseline.py from the hyphenated felix-deployer/ dir."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    if str(FELIX_DEPLOYER_DIR) not in sys.path:
        sys.path.insert(0, str(FELIX_DEPLOYER_DIR))
    spec = importlib.util.spec_from_file_location(
        "felix_deployer_rebaseline_under_test",
        FELIX_DEPLOYER_DIR / "rebaseline.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["felix_deployer_rebaseline_under_test"] = module
    spec.loader.exec_module(module)
    return module


rbl = _load_rebaseline()

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

SHA_A = "aaaa0000" * 5  # pre-pull HEAD
SHA_B = "bbbb1111" * 5  # post-pull HEAD (different → observe should fire)

# Minimal audited-surfaces registry fixture.
# Mirrors the REAL registry rebaseline_command (with ssh wrapper) so that
# _strip_ssh_wrapper / command-derivation logic is exercised in tests.
_REGISTRY = {
    "schema_version": "1.0",
    "expected_baseline_count": 14,
    "rebaseline_command": (
        "ssh office2-claude 'rm /data/services/security-monitor/baselines/* "
        "&& sg docker -c /data/services/security-monitor/scripts/audit.sh'"
    ),
    "audited_surfaces": [
        {
            "id": "openclaw-config",
            "description": "OpenClaw runtime config",
            "patterns": ["scripts/openclaw/openclaw.json"],
            "affected_baselines": ["openclaw-config.txt", "openclaw-cron.txt"],
        },
        {
            "id": "python-dependencies",
            "description": "Python deps",
            "patterns": ["requirements.txt"],
            "affected_baselines": ["pip-packages.txt"],
        },
    ],
}

# Date for use in "All clear" lines that mirror real audit.sh output.
_AUDIT_DATE = "2026-06-17"


def _clean_audit_stdout() -> str:
    """Real audit.sh clean output: 'Security audit YYYY-MM-DD: All clear'."""
    return f"Security audit {_AUDIT_DATE}: All clear"


def _drift_stdout(*baseline_names: str) -> str:
    """Real audit.sh drift output: '[ALERT] <name> changed since baseline: <diff>'."""
    lines = [
        f"[ALERT] {name} changed since baseline: -old_value\n+new_value"
        for name in baseline_names
    ]
    return "\n".join(lines)


def _make_proc(stdout: str = "", stderr: str = "", returncode: int = 0):
    """Return a mock CompletedProcess."""
    p = MagicMock(spec=subprocess.CompletedProcess)
    p.stdout = stdout
    p.stderr = stderr
    p.returncode = returncode
    return p


def _git_runner_no_match(args: list[str]) -> subprocess.CompletedProcess:
    """Git runner that returns no changed files."""
    if args[0] == "diff":
        return _make_proc(stdout="")
    return _make_proc()


def _git_runner_match_openclaw(args: list[str]) -> subprocess.CompletedProcess:
    """Git runner that returns a single openclaw-config change."""
    if args[0] == "diff":
        return _make_proc(stdout="scripts/openclaw/openclaw.json\n")
    return _make_proc()


def _clean_audit_runner(cmd: list[str]) -> subprocess.CompletedProcess:
    """Audit runner: exit 0 with real 'All clear' line (no drift)."""
    return _make_proc(stdout=_clean_audit_stdout(), returncode=0)


def _drift_openclaw_runner(cmd: list[str]) -> subprocess.CompletedProcess:
    """Audit runner: exit 1 with openclaw-config.txt drift (within expected)."""
    return _make_proc(
        stdout=_drift_stdout("openclaw-config.txt"),
        returncode=1,
    )


def _drift_unexpected_runner(cmd: list[str]) -> subprocess.CompletedProcess:
    """Audit runner: exit 1 with both expected (openclaw) and unexpected (ssh-keys) drift."""
    return _make_proc(
        stdout=_drift_stdout("openclaw-config.txt", "ssh-keys.txt"),
        returncode=1,
    )


def _unparseable_audit_runner(cmd: list[str]) -> subprocess.CompletedProcess:
    """Audit runner: exit 2 (unexpected code) → inconclusive."""
    return _make_proc(
        stdout="some random output without recognised markers\n",
        returncode=2,
    )


def _empty_audit_runner(cmd: list[str]) -> subprocess.CompletedProcess:
    """Audit runner: exit 0 with empty stdout → inconclusive."""
    return _make_proc(stdout="", returncode=0)


def _exit1_no_alert_runner(cmd: list[str]) -> subprocess.CompletedProcess:
    """Audit runner: exit 1 but no [ALERT] lines → inconclusive."""
    return _make_proc(
        stdout="something unexpected happened\n",
        returncode=1,
    )


def _token_with_openclaw(pending_since: str | None = None) -> dict[str, Any]:
    """Minimal valid token with openclaw-config surface pending."""
    if pending_since is None:
        pending_since = "2026-06-17T10:00:00Z"
    return {
        "schema_version": 1,
        "pending_since_utc": pending_since,
        "observed_head_sha": SHA_B,
        "surface_ids": ["openclaw-config"],
        "expected_baselines": ["openclaw-config.txt", "openclaw-cron.txt"],
        "matched_files": ["scripts/openclaw/openclaw.json"],
        "last_check_utc": None,
        "alerts_emitted": [],
    }


def _make_baselines_dir(tmp_path: pathlib.Path, count: int) -> pathlib.Path:
    """Create a temporary baselines directory with ``count`` stub files."""
    d = tmp_path / "baselines"
    d.mkdir()
    for i in range(count):
        (d / f"baseline-{i:02d}.txt").write_text(f"content-{i}", encoding="utf-8")
    return d


# ---------------------------------------------------------------------------
# T4 — Token store: read / write / clear + atomicity
# ---------------------------------------------------------------------------


class TestTokenStore:
    def test_read_absent_returns_none(self, tmp_path):
        """Absent file → None (nothing pending)."""
        token_path = tmp_path / "rebaseline-pending.json"
        assert rbl.read_token(token_path) is None

    def test_write_then_read_round_trip(self, tmp_path):
        """write_token + read_token round-trip preserves all fields."""
        token_path = tmp_path / "rebaseline-pending.json"
        token = _token_with_openclaw()
        rbl.write_token(token, token_path)
        result = rbl.read_token(token_path)
        assert result is not None
        assert result["schema_version"] == 1
        assert result["surface_ids"] == ["openclaw-config"]
        assert result["expected_baselines"] == [
            "openclaw-config.txt",
            "openclaw-cron.txt",
        ]

    def test_write_is_atomic_tmp_then_replace(self, tmp_path):
        """write_token leaves no .tmp file after completion."""
        token_path = tmp_path / "rebaseline-pending.json"
        rbl.write_token(_token_with_openclaw(), token_path)
        tmp_path_tmp = tmp_path / "rebaseline-pending.tmp"
        assert not tmp_path_tmp.exists(), ".tmp file should have been replaced"
        assert token_path.exists()

    def test_clear_removes_file(self, tmp_path):
        """clear_token removes the file; absent file is a no-op."""
        token_path = tmp_path / "rebaseline-pending.json"
        rbl.write_token(_token_with_openclaw(), token_path)
        assert token_path.exists()
        rbl.clear_token(token_path)
        assert not token_path.exists()

    def test_clear_absent_is_noop(self, tmp_path):
        """clear_token on a non-existent token does not raise."""
        token_path = tmp_path / "rebaseline-pending.json"
        rbl.clear_token(token_path)  # must not raise

    def test_read_malformed_json_returns_none(self, tmp_path):
        """Corrupt JSON → read_token returns None (not raise)."""
        token_path = tmp_path / "rebaseline-pending.json"
        token_path.write_text("{not valid json", encoding="utf-8")
        assert rbl.read_token(token_path) is None

    def test_write_creates_parent_dir(self, tmp_path):
        """write_token creates parent directories if needed."""
        token_path = tmp_path / "state" / "subdir" / "rebaseline-pending.json"
        rbl.write_token(_token_with_openclaw(), token_path)
        assert token_path.exists()


# ---------------------------------------------------------------------------
# T5 — Observe
# ---------------------------------------------------------------------------


class TestObserve:
    def test_equal_heads_returns_not_required(self, tmp_path):
        """Equal pre/post heads → not_required, no token written."""
        token_path = tmp_path / "token.json"
        result = rbl.observe(
            SHA_A, SHA_A, token_path=token_path, registry=_REGISTRY
        )
        assert result["outcome"] == rbl.OUTCOME_NOT_REQUIRED
        assert not token_path.exists()

    def test_no_match_returns_not_required(self, tmp_path):
        """Changed files that don't match any surface → not_required."""
        token_path = tmp_path / "token.json"
        result = rbl.observe(
            SHA_A,
            SHA_B,
            token_path=token_path,
            git_runner=_git_runner_no_match,
            registry=_REGISTRY,
        )
        assert result["outcome"] == rbl.OUTCOME_NOT_REQUIRED
        assert not token_path.exists()

    def test_match_creates_token_pending_set(self, tmp_path):
        """Matched surface → pending_set outcome and token written."""
        token_path = tmp_path / "token.json"
        result = rbl.observe(
            SHA_A,
            SHA_B,
            token_path=token_path,
            git_runner=_git_runner_match_openclaw,
            registry=_REGISTRY,
        )
        assert result["outcome"] == rbl.OUTCOME_PENDING_SET
        assert "openclaw-config" in result["surface_ids"]
        token = rbl.read_token(token_path)
        assert token is not None
        assert "openclaw-config" in token["surface_ids"]
        assert "openclaw-config.txt" in token["expected_baselines"]
        assert "openclaw-cron.txt" in token["expected_baselines"]
        assert token["schema_version"] == rbl.SCHEMA_VERSION

    def test_merge_into_existing_token(self, tmp_path):
        """Second observe merges surface_ids + expected_baselines; keeps earliest pending_since."""
        token_path = tmp_path / "token.json"

        # First observe: openclaw-config surface.
        rbl.observe(
            SHA_A,
            SHA_B,
            token_path=token_path,
            git_runner=_git_runner_match_openclaw,
            registry=_REGISTRY,
        )
        first_token = rbl.read_token(token_path)
        assert first_token is not None
        first_pending_since = first_token["pending_since_utc"]

        # Second observe: requirements.txt (python-dependencies surface).
        def git_runner_req(args):
            if args[0] == "diff":
                return _make_proc(stdout="requirements.txt\n")
            return _make_proc()

        SHA_C = "cccc2222" * 5
        rbl.observe(
            SHA_B,
            SHA_C,
            token_path=token_path,
            git_runner=git_runner_req,
            registry=_REGISTRY,
        )
        merged = rbl.read_token(token_path)
        assert merged is not None
        assert "openclaw-config" in merged["surface_ids"]
        assert "python-dependencies" in merged["surface_ids"]
        assert "openclaw-config.txt" in merged["expected_baselines"]
        assert "pip-packages.txt" in merged["expected_baselines"]
        # Earliest pending_since_utc preserved.
        assert merged["pending_since_utc"] == first_pending_since

    def test_git_diff_failure_returns_not_required(self, tmp_path):
        """If git diff fails, observe returns not_required (no crash)."""
        token_path = tmp_path / "token.json"

        def failing_git(args):
            return _make_proc(returncode=1, stderr="fatal: bad revision")

        result = rbl.observe(
            SHA_A,
            SHA_B,
            token_path=token_path,
            git_runner=failing_git,
            registry=_REGISTRY,
        )
        assert result["outcome"] == rbl.OUTCOME_NOT_REQUIRED


# ---------------------------------------------------------------------------
# Audit output parser unit tests (real audit.sh format)
# ---------------------------------------------------------------------------


class TestParseAuditOutput:
    """Unit tests for _parse_drifted_baselines against real audit.sh output."""

    def test_exit0_all_clear_returns_empty_set(self):
        """exit 0 + 'All clear' stdout → D=∅ (clean)."""
        result = rbl._parse_drifted_baselines(_clean_audit_stdout(), returncode=0)
        assert result == set()

    def test_exit0_empty_stdout_inconclusive(self):
        """exit 0 + empty stdout → inconclusive (None)."""
        result = rbl._parse_drifted_baselines("", returncode=0)
        assert result is None

    def test_exit1_with_alert_lines_returns_names(self):
        """exit 1 + [ALERT] lines → set of drifted names."""
        stdout = _drift_stdout("openclaw-config.txt", "pip-packages.txt")
        result = rbl._parse_drifted_baselines(stdout, returncode=1)
        assert result == {"openclaw-config.txt", "pip-packages.txt"}

    def test_exit1_single_alert_returns_single_name(self):
        """exit 1 + single [ALERT] → singleton set."""
        stdout = _drift_stdout("openclaw-config.txt")
        result = rbl._parse_drifted_baselines(stdout, returncode=1)
        assert result == {"openclaw-config.txt"}

    def test_exit1_no_alert_lines_inconclusive(self):
        """exit 1 but no [ALERT] lines → inconclusive (None)."""
        result = rbl._parse_drifted_baselines("unexpected output\n", returncode=1)
        assert result is None

    def test_exit2_unexpected_returncode_inconclusive(self):
        """Non 0/1 exit code → inconclusive (command-level failure)."""
        result = rbl._parse_drifted_baselines("whatever\n", returncode=2)
        assert result is None

    def test_exit1_alert_with_multiline_diff_parses_name(self):
        """[ALERT] lines with diff content → name extracted correctly."""
        stdout = (
            "[ALERT] openclaw-config.txt changed since baseline: "
            "-old_hash\n+new_hash\n"
            "[ALERT] pip-packages.txt changed since baseline: "
            "-requests==2.0\n+requests==2.1\n"
        )
        result = rbl._parse_drifted_baselines(stdout, returncode=1)
        assert result == {"openclaw-config.txt", "pip-packages.txt"}


# ---------------------------------------------------------------------------
# Command derivation unit tests
# ---------------------------------------------------------------------------


class TestCommandDerivation:
    """Unit tests for SSH stripping and local command construction."""

    def test_strip_ssh_wrapper_extracts_inner(self):
        """_strip_ssh_wrapper extracts the inner command from ssh '...' form."""
        cmd = (
            "ssh office2-claude 'rm /data/services/security-monitor/baselines/* "
            "&& sg docker -c /data/services/security-monitor/scripts/audit.sh'"
        )
        inner = rbl._strip_ssh_wrapper(cmd)
        assert inner == (
            "rm /data/services/security-monitor/baselines/* "
            "&& sg docker -c /data/services/security-monitor/scripts/audit.sh"
        )

    def test_strip_ssh_wrapper_non_ssh_passthrough(self):
        """Non-SSH command passes through unchanged."""
        cmd = "rm /baselines/* && sg docker -c /audit.sh"
        assert rbl._strip_ssh_wrapper(cmd) == cmd

    def test_build_readonly_audit_cmd_no_ssh(self):
        """_build_readonly_audit_cmd returns local sg docker argv (no ssh)."""
        cmd = rbl._build_readonly_audit_cmd(_REGISTRY["rebaseline_command"])
        assert cmd == [
            "sg", "docker", "-c",
            "/data/services/security-monitor/scripts/audit.sh",
        ]
        # Must NOT contain 'ssh' anywhere.
        assert "ssh" not in cmd

    def test_build_rebaseline_cmd_no_ssh(self):
        """_build_rebaseline_cmd returns sh -c <inner> without ssh."""
        cmd = rbl._build_rebaseline_cmd(_REGISTRY["rebaseline_command"])
        # sh -c <inner-without-ssh>
        assert cmd[0] == "sh"
        assert cmd[1] == "-c"
        assert "ssh" not in cmd[2]
        assert "rm" in cmd[2]
        assert "sg docker -c" in cmd[2]

    def test_build_readonly_fallback_on_empty(self):
        """Empty rebaseline_command → fallback ['true'] (safe no-op)."""
        cmd = rbl._build_readonly_audit_cmd("")
        assert cmd == ["true"]

    def test_build_rebaseline_fallback_on_empty(self):
        """Empty rebaseline_command → fallback ['true']."""
        cmd = rbl._build_rebaseline_cmd("")
        assert cmd == ["true"]


# ---------------------------------------------------------------------------
# Baseline file counter unit tests
# ---------------------------------------------------------------------------


class TestBaselineFileCounter:
    def test_count_files_in_directory(self, tmp_path):
        """_count_baseline_files counts regular files in the directory."""
        d = _make_baselines_dir(tmp_path, 14)
        assert rbl._count_baseline_files(d) == 14

    def test_count_zero_for_empty_dir(self, tmp_path):
        """Empty baselines dir → 0."""
        d = tmp_path / "baselines"
        d.mkdir()
        assert rbl._count_baseline_files(d) == 0

    def test_count_zero_for_missing_dir(self, tmp_path):
        """Missing baselines dir → 0 (no crash)."""
        d = tmp_path / "nonexistent"
        assert rbl._count_baseline_files(d) == 0

    def test_count_ignores_subdirectories(self, tmp_path):
        """Subdirectories are not counted (only regular files)."""
        d = tmp_path / "baselines"
        d.mkdir()
        (d / "file.txt").write_text("x", encoding="utf-8")
        (d / "subdir").mkdir()
        assert rbl._count_baseline_files(d) == 1


# ---------------------------------------------------------------------------
# T6 — Reconcile classification
# ---------------------------------------------------------------------------


class TestReconcile:
    def test_no_token_returns_not_required(self, tmp_path):
        """No pending token → reconcile is a no-op."""
        token_path = tmp_path / "token.json"
        result = rbl.reconcile(token_path=token_path, registry=_REGISTRY)
        assert result["outcome"] == rbl.OUTCOME_NOT_REQUIRED

    def test_cleared_clean_D_empty(self, tmp_path):
        """D=∅ (exit 0, All clear) → cleared_clean; token deleted."""
        token_path = tmp_path / "token.json"
        rbl.write_token(_token_with_openclaw(), token_path)
        result = rbl.reconcile(
            token_path=token_path,
            audit_runner=_clean_audit_runner,
            registry=_REGISTRY,
        )
        assert result["outcome"] == rbl.OUTCOME_CLEARED_CLEAN
        assert not token_path.exists()

    def test_completed_D_subset_E(self, tmp_path):
        """D⊆E, D≠∅ (exit 1, [ALERT] openclaw-config.txt) → triggers rebaseline → completed."""
        token_path = tmp_path / "token.json"
        rbl.write_token(_token_with_openclaw(), token_path)

        # Build a 14-file baselines directory to satisfy file-count verification.
        baselines_dir = _make_baselines_dir(tmp_path, 14)
        expected_count = _REGISTRY["expected_baseline_count"]

        call_tracker: list[int] = [0]

        def audit_runner(cmd: list[str]) -> subprocess.CompletedProcess:
            call_tracker[0] += 1
            if call_tracker[0] == 1:
                # First call: read-only audit → expected drift (exit 1)
                return _make_proc(
                    stdout=_drift_stdout("openclaw-config.txt"),
                    returncode=1,
                )
            if call_tracker[0] == 2:
                # Second call: rebaseline command (sh -c rm && sg) → exit 0
                return _make_proc(
                    stdout=f"Security audit {_AUDIT_DATE}: All clear",
                    returncode=0,
                )
            # Third call: post-rebaseline verify → clean (exit 0)
            return _make_proc(
                stdout=_clean_audit_stdout(),
                returncode=0,
            )

        result = rbl.reconcile(
            token_path=token_path,
            audit_runner=audit_runner,
            registry=_REGISTRY,
            baselines_dir=baselines_dir,
        )
        assert result["outcome"] == rbl.OUTCOME_COMPLETED
        assert "rebaselined_at_utc" in result
        assert result["baseline_count"] == expected_count
        assert not token_path.exists()

    def test_failed_count_mismatch(self, tmp_path):
        """D⊆E but baselines dir has wrong file count → failed; token kept."""
        token_path = tmp_path / "token.json"
        rbl.write_token(_token_with_openclaw(), token_path)

        # Only 5 files instead of 14.
        baselines_dir = _make_baselines_dir(tmp_path, 5)

        call_tracker: list[int] = [0]

        def audit_runner(cmd: list[str]) -> subprocess.CompletedProcess:
            call_tracker[0] += 1
            if call_tracker[0] == 1:
                # Read-only audit: expected drift (exit 1)
                return _make_proc(
                    stdout=_drift_stdout("openclaw-config.txt"),
                    returncode=1,
                )
            # Rebaseline call: exit 0 (success), but baselines_dir has only 5 files.
            return _make_proc(
                stdout=_clean_audit_stdout(),
                returncode=0,
            )

        result = rbl.reconcile(
            token_path=token_path,
            audit_runner=audit_runner,
            registry=_REGISTRY,
            baselines_dir=baselines_dir,
        )
        assert result["outcome"] == rbl.OUTCOME_FAILED
        assert "error_summary" in result
        assert "count mismatch" in result["error_summary"].lower()
        # Token must be preserved on failure.
        assert token_path.exists()

    def test_failed_audit_not_clear_after_rebaseline(self, tmp_path):
        """D⊆E, correct file count but post-verify shows drift (exit 1) → failed."""
        token_path = tmp_path / "token.json"
        rbl.write_token(_token_with_openclaw(), token_path)

        baselines_dir = _make_baselines_dir(tmp_path, 14)
        call_tracker: list[int] = [0]

        def audit_runner(cmd: list[str]) -> subprocess.CompletedProcess:
            call_tracker[0] += 1
            if call_tracker[0] == 1:
                # Read-only: expected drift (exit 1)
                return _make_proc(
                    stdout=_drift_stdout("openclaw-config.txt"),
                    returncode=1,
                )
            if call_tracker[0] == 2:
                # Rebaseline: exit 0 (success)
                return _make_proc(
                    stdout=_clean_audit_stdout(),
                    returncode=0,
                )
            # Post-rebaseline verify: still drifted (exit 1, not clean).
            return _make_proc(
                stdout=_drift_stdout("openclaw-config.txt"),
                returncode=1,
            )

        result = rbl.reconcile(
            token_path=token_path,
            audit_runner=audit_runner,
            registry=_REGISTRY,
            baselines_dir=baselines_dir,
        )
        assert result["outcome"] == rbl.OUTCOME_FAILED
        assert "error_summary" in result
        assert token_path.exists()

    def test_unexpected_drift_D_not_subset_E(self, tmp_path):
        """D⊄E → unexpected_drift; token is NOT cleared (FR-009)."""
        token_path = tmp_path / "token.json"
        rbl.write_token(_token_with_openclaw(), token_path)

        result = rbl.reconcile(
            token_path=token_path,
            audit_runner=_drift_unexpected_runner,
            registry=_REGISTRY,
        )
        assert result["outcome"] == rbl.OUTCOME_UNEXPECTED_DRIFT
        # FR-009: do NOT reset.
        assert token_path.exists(), "token must be kept on unexpected_drift"
        # The unexpected baselines are identified.
        assert "ssh-keys.txt" in result.get("unexpected", [])

    def test_inconclusive_leaves_token_no_reset(self, tmp_path):
        """Unparseable audit output (exit 2) → inconclusive; token preserved, no reset."""
        token_path = tmp_path / "token.json"
        rbl.write_token(_token_with_openclaw(), token_path)

        result = rbl.reconcile(
            token_path=token_path,
            audit_runner=_unparseable_audit_runner,
            registry=_REGISTRY,
        )
        assert result["outcome"] == rbl.OUTCOME_INCONCLUSIVE
        assert token_path.exists()

    def test_empty_audit_output_inconclusive(self, tmp_path):
        """Empty audit stdout + exit 0 → inconclusive (cannot parse D)."""
        token_path = tmp_path / "token.json"
        rbl.write_token(_token_with_openclaw(), token_path)

        result = rbl.reconcile(
            token_path=token_path,
            audit_runner=_empty_audit_runner,
            registry=_REGISTRY,
        )
        assert result["outcome"] == rbl.OUTCOME_INCONCLUSIVE
        assert token_path.exists()

    def test_exit1_no_alert_lines_inconclusive(self, tmp_path):
        """exit 1 but no [ALERT] lines → inconclusive."""
        token_path = tmp_path / "token.json"
        rbl.write_token(_token_with_openclaw(), token_path)

        result = rbl.reconcile(
            token_path=token_path,
            audit_runner=_exit1_no_alert_runner,
            registry=_REGISTRY,
        )
        assert result["outcome"] == rbl.OUTCOME_INCONCLUSIVE
        assert token_path.exists()

    def test_stale_token_sets_stale_flag(self, tmp_path):
        """Token older than max_age_seconds triggers stale result."""
        token_path = tmp_path / "token.json"
        # Pending since 25 hours ago.
        old_since = (
            _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=25)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        rbl.write_token(_token_with_openclaw(pending_since=old_since), token_path)

        result = rbl.reconcile(
            token_path=token_path,
            audit_runner=_unparseable_audit_runner,  # inconclusive → we see stale check
            registry=_REGISTRY,
            max_age_seconds=86_400,
        )
        # Outcome is inconclusive but stale flag should be set.
        assert result.get("stale") is True

    def test_stale_alert_emitted_only_once(self, tmp_path):
        """Stale alert is emitted at most once (dedup via alerts_emitted)."""
        token_path = tmp_path / "token.json"
        old_since = (
            _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=25)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        token = _token_with_openclaw(pending_since=old_since)
        token["alerts_emitted"] = ["stale"]  # already alerted
        rbl.write_token(token, token_path)

        result = rbl.reconcile(
            token_path=token_path,
            audit_runner=_unparseable_audit_runner,
            registry=_REGISTRY,
            max_age_seconds=86_400,
        )
        # stale not in result because already alerted.
        assert not result.get("stale")

    def test_last_check_utc_updated(self, tmp_path):
        """reconcile updates last_check_utc in the token."""
        token_path = tmp_path / "token.json"
        rbl.write_token(_token_with_openclaw(), token_path)

        rbl.reconcile(
            token_path=token_path,
            audit_runner=_unparseable_audit_runner,  # inconclusive keeps token
            registry=_REGISTRY,
        )
        updated_token = rbl.read_token(token_path)
        assert updated_token is not None
        assert updated_token.get("last_check_utc") is not None

    def test_unexpected_drift_no_rebaseline_ran(self, tmp_path):
        """D⊄E → audit runner called once only (no rebaseline attempt)."""
        token_path = tmp_path / "token.json"
        rbl.write_token(_token_with_openclaw(), token_path)

        call_tracker: list[int] = [0]

        def counting_runner(cmd: list[str]) -> subprocess.CompletedProcess:
            call_tracker[0] += 1
            return _make_proc(
                stdout=_drift_stdout("openclaw-config.txt", "ssh-keys.txt"),
                returncode=1,
            )

        result = rbl.reconcile(
            token_path=token_path,
            audit_runner=counting_runner,
            registry=_REGISTRY,
        )
        assert result["outcome"] == rbl.OUTCOME_UNEXPECTED_DRIFT
        # Only one audit call — no rebaseline attempt.
        assert call_tracker[0] == 1


# ---------------------------------------------------------------------------
# T7 — rebaseline_and_verify
# ---------------------------------------------------------------------------


class TestRebaselineAndVerify:
    def test_completed_on_success(self, tmp_path):
        """Full success: exit 0 rebaseline + correct file count + clean verify → completed."""
        token_path = tmp_path / "token.json"
        token = _token_with_openclaw()
        expected_count = _REGISTRY["expected_baseline_count"]

        baselines_dir = _make_baselines_dir(tmp_path, expected_count)

        call_tracker: list[int] = [0]

        def runner(cmd: list[str]) -> subprocess.CompletedProcess:
            call_tracker[0] += 1
            if call_tracker[0] == 1:
                # Rebaseline run: exit 0.
                return _make_proc(
                    stdout=_clean_audit_stdout(),
                    returncode=0,
                )
            # Follow-up verify: clean (exit 0).
            return _make_proc(
                stdout=_clean_audit_stdout(),
                returncode=0,
            )

        result = rbl.rebaseline_and_verify(
            token=token,
            drifted={"openclaw-config.txt"},
            token_path=token_path,
            audit_runner=runner,
            registry=_REGISTRY,
            baselines_dir=baselines_dir,
        )
        assert result["outcome"] == rbl.OUTCOME_COMPLETED
        assert result["baseline_count"] == expected_count
        assert "rebaselined_at_utc" in result
        assert not token_path.exists()

    def test_failed_on_nonzero_exit(self, tmp_path):
        """Rebaseline command exits non-zero → failed; token kept."""
        token_path = tmp_path / "token.json"
        rbl.write_token(_token_with_openclaw(), token_path)

        def runner(cmd: list[str]) -> subprocess.CompletedProcess:
            return _make_proc(returncode=1, stderr="permission denied")

        result = rbl.rebaseline_and_verify(
            token=_token_with_openclaw(),
            drifted={"openclaw-config.txt"},
            token_path=token_path,
            audit_runner=runner,
            registry=_REGISTRY,
        )
        assert result["outcome"] == rbl.OUTCOME_FAILED
        assert "error_summary" in result
        # Token preserved.
        assert token_path.exists()

    def test_failed_on_count_mismatch(self, tmp_path):
        """Wrong file count in baselines dir → failed; token kept."""
        token_path = tmp_path / "token.json"
        rbl.write_token(_token_with_openclaw(), token_path)

        # Only 5 files (expected 14).
        baselines_dir = _make_baselines_dir(tmp_path, 5)

        def runner(cmd: list[str]) -> subprocess.CompletedProcess:
            return _make_proc(stdout=_clean_audit_stdout(), returncode=0)

        result = rbl.rebaseline_and_verify(
            token=_token_with_openclaw(),
            drifted={"openclaw-config.txt"},
            token_path=token_path,
            audit_runner=runner,
            registry=_REGISTRY,
            baselines_dir=baselines_dir,
        )
        assert result["outcome"] == rbl.OUTCOME_FAILED
        assert "count mismatch" in result["error_summary"].lower()
        assert token_path.exists()

    def test_failed_on_audit_not_clear(self, tmp_path):
        """Correct count but post-verify shows drift (exit 1) → failed; token kept."""
        token_path = tmp_path / "token.json"
        rbl.write_token(_token_with_openclaw(), token_path)

        expected_count = _REGISTRY["expected_baseline_count"]
        baselines_dir = _make_baselines_dir(tmp_path, expected_count)

        call_tracker: list[int] = [0]

        def runner(cmd: list[str]) -> subprocess.CompletedProcess:
            call_tracker[0] += 1
            if call_tracker[0] == 1:
                # Rebaseline run: exit 0.
                return _make_proc(stdout=_clean_audit_stdout(), returncode=0)
            # Post-verify: still drifted (exit 1).
            return _make_proc(
                stdout=_drift_stdout("openclaw-config.txt"),
                returncode=1,
            )

        result = rbl.rebaseline_and_verify(
            token=_token_with_openclaw(),
            drifted={"openclaw-config.txt"},
            token_path=token_path,
            audit_runner=runner,
            registry=_REGISTRY,
            baselines_dir=baselines_dir,
        )
        assert result["outcome"] == rbl.OUTCOME_FAILED
        assert token_path.exists()

    def test_never_raises(self, tmp_path):
        """rebaseline_and_verify must never propagate exceptions to the caller."""
        def exploding_runner(cmd: list[str]) -> subprocess.CompletedProcess:
            raise RuntimeError("simulated infrastructure explosion")

        result = rbl.rebaseline_and_verify(
            token=_token_with_openclaw(),
            drifted={"openclaw-config.txt"},
            token_path=tmp_path / "token.json",
            audit_runner=exploding_runner,
            registry=_REGISTRY,
        )
        # Must return a dict with outcome, not raise.
        assert isinstance(result, dict)
        assert "outcome" in result

    def test_count_uses_file_system_not_stdout(self, tmp_path):
        """Baseline count is from files on disk, not stdout parsing."""
        token_path = tmp_path / "token.json"
        rbl.write_token(_token_with_openclaw(), token_path)

        # Baselines dir has 14 files — correct count.
        baselines_dir = _make_baselines_dir(tmp_path, 14)

        # Runner returns exit 0 with NO OK: or DRIFT: lines (real audit.sh behaviour).
        # If count were based on stdout this would fail; file-based count passes.
        call_tracker: list[int] = [0]

        def runner(cmd: list[str]) -> subprocess.CompletedProcess:
            call_tracker[0] += 1
            if call_tracker[0] == 1:
                # Rebaseline: exit 0, real 'All clear' stdout (no per-baseline lines).
                return _make_proc(stdout=_clean_audit_stdout(), returncode=0)
            # Post-verify: clean.
            return _make_proc(stdout=_clean_audit_stdout(), returncode=0)

        result = rbl.rebaseline_and_verify(
            token=_token_with_openclaw(),
            drifted={"openclaw-config.txt"},
            token_path=token_path,
            audit_runner=runner,
            registry=_REGISTRY,
            baselines_dir=baselines_dir,
        )
        assert result["outcome"] == rbl.OUTCOME_COMPLETED
        assert result["baseline_count"] == 14


# ---------------------------------------------------------------------------
# End-to-end: observe → reconcile → completed (happy path)
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_observe_then_reconcile_completed(self, tmp_path):
        """Full happy path: observe sets token, reconcile completes it."""
        token_path = tmp_path / "token.json"
        expected_count = _REGISTRY["expected_baseline_count"]
        baselines_dir = _make_baselines_dir(tmp_path, expected_count)

        # Step 1: observe.
        obs = rbl.observe(
            SHA_A,
            SHA_B,
            token_path=token_path,
            git_runner=_git_runner_match_openclaw,
            registry=_REGISTRY,
        )
        assert obs["outcome"] == rbl.OUTCOME_PENDING_SET

        # Step 2: reconcile with audit showing expected drift + successful rebaseline.
        call_tracker: list[int] = [0]

        def audit_runner(cmd: list[str]) -> subprocess.CompletedProcess:
            call_tracker[0] += 1
            if call_tracker[0] == 1:
                # Read-only audit: expected drift (exit 1).
                return _make_proc(
                    stdout=_drift_stdout("openclaw-config.txt"),
                    returncode=1,
                )
            # Rebaseline + post-verify: clean (exit 0).
            return _make_proc(stdout=_clean_audit_stdout(), returncode=0)

        rec = rbl.reconcile(
            token_path=token_path,
            audit_runner=audit_runner,
            registry=_REGISTRY,
            baselines_dir=baselines_dir,
        )
        assert rec["outcome"] == rbl.OUTCOME_COMPLETED
        assert not token_path.exists()


# ---------------------------------------------------------------------------
# expected_baseline_count sourced from registry, not hardcoded
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# T001 — Observe-head watermark store
# ---------------------------------------------------------------------------


class TestWatermarkStore:
    def test_read_absent_returns_none(self, tmp_path):
        """Absent watermark file → None (first tick fallback)."""
        wm = tmp_path / "rebaseline-observed-head.json"
        assert rbl.read_observed_head(wm) is None

    def test_write_then_read_round_trip(self, tmp_path):
        """write_observed_head + read_observed_head round-trips the SHA."""
        wm = tmp_path / "rebaseline-observed-head.json"
        rbl.write_observed_head(SHA_B, wm)
        assert rbl.read_observed_head(wm) == SHA_B

    def test_write_payload_shape(self, tmp_path):
        """Watermark file carries schema_version + observed_head_sha + updated_at."""
        wm = tmp_path / "rebaseline-observed-head.json"
        rbl.write_observed_head(SHA_B, wm)
        data = json.loads(wm.read_text(encoding="utf-8"))
        assert data["schema_version"] == rbl.SCHEMA_VERSION
        assert data["observed_head_sha"] == SHA_B
        assert "updated_at" in data

    def test_write_is_atomic_no_tmp_left(self, tmp_path):
        """No .tmp file remains after a successful atomic write."""
        wm = tmp_path / "rebaseline-observed-head.json"
        rbl.write_observed_head(SHA_B, wm)
        assert not (tmp_path / "rebaseline-observed-head.tmp").exists()
        assert wm.exists()

    def test_write_creates_parent_dir(self, tmp_path):
        """Parent directories are created on write."""
        wm = tmp_path / "state" / "deep" / "rebaseline-observed-head.json"
        rbl.write_observed_head(SHA_A, wm)
        assert rbl.read_observed_head(wm) == SHA_A

    def test_read_corrupt_returns_none(self, tmp_path):
        """Corrupt JSON → None (not raise)."""
        wm = tmp_path / "rebaseline-observed-head.json"
        wm.write_text("{ not json", encoding="utf-8")
        assert rbl.read_observed_head(wm) is None

    def test_read_missing_key_returns_none(self, tmp_path):
        """Valid JSON without observed_head_sha → None."""
        wm = tmp_path / "rebaseline-observed-head.json"
        wm.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
        assert rbl.read_observed_head(wm) is None

    def test_write_to_unwritable_dir_does_not_raise(self, tmp_path):
        """OSError on write is swallowed (never raises)."""
        # Point at a path whose parent is a file → mkdir/replace fails.
        blocker = tmp_path / "blocker"
        blocker.write_text("x", encoding="utf-8")
        wm = blocker / "rebaseline-observed-head.json"
        # Must not raise.
        rbl.write_observed_head(SHA_A, wm)


# ---------------------------------------------------------------------------
# T002 — Watermark validity classification
# ---------------------------------------------------------------------------

WM_W = "wwww9999" * 5  # a watermark SHA
WM_POST = "pppp8888" * 5  # post_pull_head


def _make_git_runner(cat_file_rc: int = 0, ancestor_rc: int = 0, raise_on: str | None = None):
    """Build a fake git runner for classify_watermark branches."""

    def _runner(args: list[str]) -> subprocess.CompletedProcess:
        sub = args[0] if args else ""
        if raise_on == sub:
            raise RuntimeError(f"simulated {sub} failure")
        if sub == "cat-file":
            return _make_proc(returncode=cat_file_rc)
        if sub == "merge-base":
            return _make_proc(returncode=ancestor_rc)
        return _make_proc(returncode=0)

    return _runner


class TestClassifyWatermark:
    def test_none_watermark_is_fallback(self):
        cls, base = rbl.classify_watermark(None, WM_POST, git_runner=_make_git_runner())
        assert cls == rbl.WATERMARK_FALLBACK
        assert base is None

    def test_valid_ancestor(self):
        cls, base = rbl.classify_watermark(
            WM_W, WM_POST, git_runner=_make_git_runner(cat_file_rc=0, ancestor_rc=0)
        )
        assert cls == rbl.WATERMARK_VALID
        assert base == WM_W

    def test_unknown_commit_is_self_heal(self):
        """cat-file non-zero → provably invalid → self_heal to post."""
        cls, base = rbl.classify_watermark(
            WM_W, WM_POST, git_runner=_make_git_runner(cat_file_rc=1)
        )
        assert cls == rbl.WATERMARK_SELF_HEAL
        assert base == WM_POST

    def test_non_ancestor_is_self_heal(self):
        """merge-base --is-ancestor rc=1 → non-ancestor → self_heal."""
        cls, base = rbl.classify_watermark(
            WM_W, WM_POST, git_runner=_make_git_runner(cat_file_rc=0, ancestor_rc=1)
        )
        assert cls == rbl.WATERMARK_SELF_HEAL
        assert base == WM_POST

    def test_cat_file_raises_is_transient(self):
        cls, base = rbl.classify_watermark(
            WM_W, WM_POST, git_runner=_make_git_runner(raise_on="cat-file")
        )
        assert cls == rbl.WATERMARK_TRANSIENT
        assert base is None

    def test_merge_base_raises_is_transient(self):
        cls, base = rbl.classify_watermark(
            WM_W, WM_POST, git_runner=_make_git_runner(raise_on="merge-base")
        )
        assert cls == rbl.WATERMARK_TRANSIENT
        assert base is None

    def test_merge_base_error_code_is_transient(self):
        """merge-base rc=128 (neither 0 nor 1) → transient, not self_heal."""
        cls, base = rbl.classify_watermark(
            WM_W, WM_POST, git_runner=_make_git_runner(cat_file_rc=0, ancestor_rc=128)
        )
        assert cls == rbl.WATERMARK_TRANSIENT
        assert base is None


# ---------------------------------------------------------------------------
# T005 — Same-tick clear grace rule
# ---------------------------------------------------------------------------


class TestGraceRule:
    def test_fresh_token_D_empty_is_pending_clean(self, tmp_path):
        """A token created this tick + D=∅ → pending_clean; token retained."""
        token_path = tmp_path / "token.json"
        fresh = rbl._utc_now_iso()
        rbl.write_token(_token_with_openclaw(pending_since=fresh), token_path)

        result = rbl.reconcile(
            token_path=token_path,
            audit_runner=_clean_audit_runner,
            registry=_REGISTRY,
        )
        assert result["outcome"] == rbl.OUTCOME_PENDING_CLEAN
        assert token_path.exists(), "fresh token must be retained under grace"

    def test_aged_token_D_empty_is_cleared_clean(self, tmp_path):
        """A token older than the grace window + D=∅ → cleared_clean."""
        token_path = tmp_path / "token.json"
        old = (
            _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(seconds=1000)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        rbl.write_token(_token_with_openclaw(pending_since=old), token_path)

        result = rbl.reconcile(
            token_path=token_path,
            audit_runner=_clean_audit_runner,
            registry=_REGISTRY,
        )
        assert result["outcome"] == rbl.OUTCOME_CLEARED_CLEAN
        assert not token_path.exists()

    def test_grace_seconds_override(self, tmp_path):
        """grace_seconds=0 disables the grace window (legacy behavior)."""
        token_path = tmp_path / "token.json"
        fresh = rbl._utc_now_iso()
        rbl.write_token(_token_with_openclaw(pending_since=fresh), token_path)

        result = rbl.reconcile(
            token_path=token_path,
            audit_runner=_clean_audit_runner,
            registry=_REGISTRY,
            grace_seconds=0,
        )
        assert result["outcome"] == rbl.OUTCOME_CLEARED_CLEAN
        assert not token_path.exists()


# ---------------------------------------------------------------------------
# T006 — fold_manifest_baselines
# ---------------------------------------------------------------------------


class TestFoldManifestBaselines:
    def test_empty_declared_is_not_required(self, tmp_path):
        """Empty declared set → not_required, no token written."""
        token_path = tmp_path / "token.json"
        result = rbl.fold_manifest_baselines(
            set(), observed_head_sha=SHA_B, token_path=token_path
        )
        assert result["outcome"] == rbl.OUTCOME_NOT_REQUIRED
        assert not token_path.exists()

    def test_no_token_creates_synthetic(self, tmp_path):
        """No token → create with manifest-declared surface + declared baselines."""
        token_path = tmp_path / "token.json"
        result = rbl.fold_manifest_baselines(
            {"openclaw-cron.txt"},
            observed_head_sha=SHA_B,
            manifest_names=["0099-cron-deploy"],
            token_path=token_path,
        )
        assert result["outcome"] == "created"
        token = rbl.read_token(token_path)
        assert token is not None
        assert token["surface_ids"] == ["manifest-declared"]
        assert token["expected_baselines"] == ["openclaw-cron.txt"]
        assert token["observed_head_sha"] == SHA_B
        assert token["matched_files"] == []
        assert token["last_check_utc"] is None
        assert token["alerts_emitted"] == []
        assert token["manifest_names"] == ["0099-cron-deploy"]

    def test_existing_token_merges(self, tmp_path):
        """Existing token → union declared into expected_baselines."""
        token_path = tmp_path / "token.json"
        rbl.write_token(_token_with_openclaw(), token_path)
        result = rbl.fold_manifest_baselines(
            {"openclaw-cron.txt", "crontabs.txt"},
            observed_head_sha=SHA_B,
            token_path=token_path,
        )
        assert result["outcome"] == "merged"
        token = rbl.read_token(token_path)
        assert token is not None
        # Original openclaw baselines preserved + new ones unioned.
        assert "openclaw-config.txt" in token["expected_baselines"]
        assert "openclaw-cron.txt" in token["expected_baselines"]
        assert "crontabs.txt" in token["expected_baselines"]
        # Original surface_ids preserved (not overwritten with manifest-declared).
        assert token["surface_ids"] == ["openclaw-config"]

    def test_fold_never_raises_on_bad_declared(self, tmp_path):
        """None/empty entries in declared are filtered; never raises."""
        token_path = tmp_path / "token.json"
        result = rbl.fold_manifest_baselines(
            ["", "openclaw-cron.txt"],
            observed_head_sha=SHA_B,
            token_path=token_path,
        )
        assert result["outcome"] == "created"
        token = rbl.read_token(token_path)
        assert token["expected_baselines"] == ["openclaw-cron.txt"]


class TestRegistryDrivenCount:
    def test_count_from_registry_not_hardcoded(self, tmp_path):
        """expected_baseline_count is read from registry; varying it changes behaviour."""
        # Use a registry with count=3 instead of 14.
        small_registry = dict(_REGISTRY)
        small_registry["expected_baseline_count"] = 3

        token_path = tmp_path / "token.json"
        rbl.write_token(_token_with_openclaw(), token_path)

        # Build a baselines dir with 3 files.
        baselines_dir = _make_baselines_dir(tmp_path, 3)

        call_tracker: list[int] = [0]

        def audit_runner(cmd: list[str]) -> subprocess.CompletedProcess:
            call_tracker[0] += 1
            if call_tracker[0] == 1:
                # Read-only audit: drift (exit 1).
                return _make_proc(
                    stdout=_drift_stdout("openclaw-config.txt"),
                    returncode=1,
                )
            # Rebaseline + post-verify: clean (exit 0).
            return _make_proc(stdout=_clean_audit_stdout(), returncode=0)

        result = rbl.reconcile(
            token_path=token_path,
            audit_runner=audit_runner,
            registry=small_registry,
            baselines_dir=baselines_dir,
        )
        # With 3-count registry and 3 files on disk → completed.
        assert result["outcome"] == rbl.OUTCOME_COMPLETED

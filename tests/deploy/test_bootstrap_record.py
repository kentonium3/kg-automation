"""Tests for ``scripts/deploy/deploy-felix-deployer-bootstrap.sh``.

The bootstrap wrapper is a bash script that drives an `ssh office2-claude`
session. To exercise it without a live office2 connection, each test
prepends a ``PATH`` with stub ``ssh``, ``scp``, ``rsync``, and ``python3``
shims that record their invocations to a log file and return success.

Three scenarios per the WP05 prompt:

1. ``test_bootstrap_dry_run_lists_expected_actions``
   — ``--dry-run`` prints the planned actions (no mutating subprocess calls).
2. ``test_bootstrap_apply_constructs_correct_applied_yaml``
   — verifies the manifest YAML the script generates inline validates against
     the v1 schema with ``apply_mode: bootstrap``.
3. ``test_bootstrap_rollback_disables_timer``
   — ``--rollback`` dispatches the exact systemctl commands documented in
     the script header (header + behavior stay in sync).
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
import textwrap

import pytest
import yaml

from scripts.deploy.lib import manifest as manifest_lib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
BOOTSTRAP_SCRIPT = REPO_ROOT / "scripts" / "deploy" / "deploy-felix-deployer-bootstrap.sh"
SCHEMA_PATH = REPO_ROOT / "deploys" / "schema" / "manifest-v1.schema.json"


# ---------------------------------------------------------------------------
# Stub PATH helpers
# ---------------------------------------------------------------------------


def _write_stub(stub_dir: pathlib.Path, name: str, body: str) -> pathlib.Path:
    """Write an executable POSIX-shell stub at ``stub_dir/<name>``."""
    path = stub_dir / name
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


def _build_stub_path(tmp_path: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    """Return ``(stub_dir, log_file)`` with ssh/scp/rsync/python3 stubs.

    Each stub appends ``<cmd>:<args>`` to ``log_file`` (one line per call)
    and exits 0 — except the real python3 we shim, which we route to the
    system python3 only for the explicit verify_file_present lookups
    (those must succeed against the actual repo files for the script's
    pre-flight to pass).
    """
    stub_dir = tmp_path / "stubs"
    stub_dir.mkdir()
    log_file = tmp_path / "calls.log"
    log_file.touch()

    real_python = sys.executable

    # ssh stub: succeed silently for all probes, including systemctl status.
    # The post-flight check greps stdout for ``active (waiting|running)`` — we
    # emit that line when the args include ``systemctl --user status``.
    _write_stub(
        stub_dir,
        "ssh",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            printf 'ssh:%s\\n' "$*" >> {log_file}
            # If the remote command asks for status of felix-deployer.timer,
            # emit a synthesized active line so the post-flight check passes.
            for arg in "$@"; do
              case "$arg" in
                *"systemctl --user status felix-deployer.timer"*)
                  printf 'Active: active (waiting) since Fri 2026-06-12 12:00:00 UTC\\n'
                  ;;
                *"openclaw cron list --json"*)
                  printf '[]\\n'
                  ;;
              esac
            done
            exit 0
            """
        ),
    )

    # scp stub
    _write_stub(
        stub_dir,
        "scp",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            printf 'scp:%s\\n' "$*" >> {log_file}
            exit 0
            """
        ),
    )

    # rsync stub
    _write_stub(
        stub_dir,
        "rsync",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            printf 'rsync:%s\\n' "$*" >> {log_file}
            exit 0
            """
        ),
    )

    # python3 stub: must succeed for the verify_file_present pre-flight
    # because the source files are real on disk. We route python3 through
    # the real interpreter so module-as-CLI invocations work.
    _write_stub(
        stub_dir,
        "python3",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            printf 'python3:%s\\n' "$*" >> {log_file}
            exec {real_python} "$@"
            """
        ),
    )

    return stub_dir, log_file


def _run_bootstrap(
    mode: str,
    tmp_path: pathlib.Path,
) -> tuple[subprocess.CompletedProcess[str], pathlib.Path]:
    """Run the bootstrap script with the stub PATH and return its result + log."""
    stub_dir, log_file = _build_stub_path(tmp_path)
    env = os.environ.copy()
    # Prepend stub dir so our shims win; keep the rest for builtin tools (bash).
    env["PATH"] = f"{stub_dir}:{env.get('PATH', '')}"
    # Run from repo root so the script's REPO_ROOT computation is correct.
    proc = subprocess.run(
        ["bash", str(BOOTSTRAP_SCRIPT), mode],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    return proc, log_file


# ---------------------------------------------------------------------------
# Scenario 1: --dry-run lists expected actions
# ---------------------------------------------------------------------------


def test_bootstrap_dry_run_lists_expected_actions(tmp_path):
    """``--dry-run`` prints each planned action without mutating anything."""
    proc, log_file = _run_bootstrap("--dry-run", tmp_path)
    assert proc.returncode == 0, (
        f"dry-run exited {proc.returncode}\n"
        f"--- stdout ---\n{proc.stdout}\n"
        f"--- stderr ---\n{proc.stderr}"
    )

    out = proc.stdout
    # Each expected "would do" line must appear.
    expected_phrases = [
        "DRY RUN",
        "rsync scripts/deploy/felix-deployer/",
        "rsync scripts/deploy/lib/",
        "felix-deployer.service",
        "felix-deployer.timer",
        "systemctl --user daemon-reload",
        "systemctl --user enable --now felix-deployer.timer",
        "openclaw cron edit felix-deployer-alert",
        "write_applied",
        "--apply-mode bootstrap",
        "0001-bootstrap-felix-deployer.yaml",
        "DRY RUN COMPLETE",
    ]
    missing = [p for p in expected_phrases if p not in out]
    assert not missing, (
        f"dry-run output missing expected phrases: {missing}\n"
        f"--- stdout ---\n{out}"
    )

    # No mutating remote ops should have run. rsync/scp must not have been
    # invoked at all (only ssh probes for pre-flight openclaw cron list).
    log_text = log_file.read_text(encoding="utf-8")
    assert "rsync:" not in log_text, f"dry-run invoked rsync: {log_text}"
    assert "scp:" not in log_text, f"dry-run invoked scp: {log_text}"


# ---------------------------------------------------------------------------
# Scenario 2: --apply constructs a Tier 1 bootstrap manifest that validates
# ---------------------------------------------------------------------------


def test_bootstrap_apply_constructs_correct_applied_yaml(tmp_path):
    """The manifest the script generates inline must validate against the v1
    schema with ``apply_mode: bootstrap``.

    Rather than running --apply end-to-end (which would commit + push from
    office2), we reconstruct the manifest body the script writes via its
    heredoc, augment it with ``apply_mode`` + ``applied_at`` exactly as
    ``lib.applied.write_applied`` does, and assert the result is schema-valid.

    This is the same shape of test as exists in ``test_applied.py``, but
    pinned to the literal manifest body the bootstrap script generates.
    """
    # Extract the heredoc literal from the bootstrap script. It is the only
    # ``schema_version: v1`` block in the file, between ``<<EOF`` and ``EOF``.
    script_text = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")
    match = re.search(
        r'<<EOF\n(schema_version: v1.*?)\nEOF\n',
        script_text,
        re.DOTALL,
    )
    assert match, "bootstrap script must contain the manifest heredoc body"
    manifest_body = match.group(1)

    # Substitute the bash variable placeholders the script expands at runtime.
    # Each known bash variable maps to its production value (or, for the
    # timestamp, a fixed test value).
    substitutions = {
        "${CREATED_AT}": "2026-06-12T00:00:00Z",
        "${ISSUE_REF}": "kentonium3/kg-automation#136",
        "${REMOTE_SYSTEMD_USER_DIR}": "/home/claude/.config/systemd/user",
    }
    for key, value in substitutions.items():
        manifest_body = manifest_body.replace(key, value)

    # Any remaining ${...} placeholders mean the script grew a new bash
    # variable that the test doesn't yet know about. Fail loudly so the
    # operator updates the substitution map.
    leftover = re.findall(r"\$\{[A-Z_]+\}", manifest_body)
    assert not leftover, f"unmapped bash variables in heredoc: {leftover}"

    base_manifest = yaml.safe_load(manifest_body)
    assert isinstance(base_manifest, dict), "manifest heredoc must parse to a mapping"

    # Pin the fields a bootstrap manifest MUST have.
    assert base_manifest["schema_version"] == "v1"
    assert base_manifest["name"] == "bootstrap-felix-deployer"
    assert base_manifest["tier"] == 1
    assert base_manifest["audited_surface"] is True
    assert base_manifest["entrypoint"] == "scripts/deploy/deploy-felix-deployer-bootstrap.sh"
    assert base_manifest["issue"] == "kentonium3/kg-automation#136"
    assert base_manifest["created_by"] == "operator-bootstrap"
    # Tier 1 requires a verification block (schema enforces this).
    assert "verification" in base_manifest
    assert isinstance(base_manifest["verification"].get("pre"), list)
    assert isinstance(base_manifest["verification"].get("post"), list)

    # Mirror exactly what lib.applied.write_applied does to construct the
    # final on-disk record.
    augmented = dict(base_manifest)
    augmented["apply_mode"] = "bootstrap"
    augmented["applied_at"] = "2026-06-12T00:00:01Z"

    # Validate against the canonical schema.
    result = manifest_lib.validate_manifest(augmented, schema_path=SCHEMA_PATH)
    assert result.ok, (
        f"bootstrap manifest failed schema validation: {result.summary}\n"
        f"details: {dict(result.details)}"
    )
    assert augmented["apply_mode"] == "bootstrap"


# ---------------------------------------------------------------------------
# Scenario 3: --rollback dispatches the systemctl commands documented in header
# ---------------------------------------------------------------------------


def test_bootstrap_rollback_disables_timer(tmp_path):
    """``--rollback`` issues the three documented systemctl/rm commands."""
    proc, log_file = _run_bootstrap("--rollback", tmp_path)
    assert proc.returncode == 0, (
        f"rollback exited {proc.returncode}\n"
        f"--- stdout ---\n{proc.stdout}\n"
        f"--- stderr ---\n{proc.stderr}"
    )

    log_text = log_file.read_text(encoding="utf-8")
    ssh_calls = [
        line for line in log_text.splitlines() if line.startswith("ssh:")
    ]
    assert ssh_calls, f"rollback never invoked ssh; log:\n{log_text}"

    # Required commands per the script header rollback recipe:
    #   1) systemctl --user disable --now felix-deployer.timer felix-deployer.service
    #   2) rm -f .../felix-deployer.service .../felix-deployer.timer
    #   3) systemctl --user daemon-reload
    joined = "\n".join(ssh_calls)
    assert "systemctl --user disable --now felix-deployer.timer felix-deployer.service" in joined, (
        f"rollback missing disable+stop command:\n{joined}"
    )
    assert "rm -f" in joined and "felix-deployer.service" in joined and "felix-deployer.timer" in joined, (
        f"rollback missing rm of unit files:\n{joined}"
    )
    assert "systemctl --user daemon-reload" in joined, (
        f"rollback missing daemon-reload:\n{joined}"
    )

    # And no mutating non-ssh operations (no rsync, scp).
    assert "rsync:" not in log_text, f"rollback wrongly invoked rsync:\n{log_text}"
    assert "scp:" not in log_text, f"rollback wrongly invoked scp:\n{log_text}"

    # Confirm completion line.
    assert "ROLLBACK COMPLETE" in proc.stdout

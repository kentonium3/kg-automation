"""Tests for the anthropic-rotate.sh WP03 verify gate and --rollback mode.

Covers FR-012 (verifier invoked at rotation end), FR-013 (failure surfaces
rollback hint + structured manifest update), FR-014 (--rollback restores all
three artifacts), NFR-006 (verifier overhead ≤ 5 s).

Strategy:
  * Drive ``scripts/security/anthropic-rotate.sh`` via ``subprocess.run``.
  * Inject stub binaries (``openclaw``, ``systemctl``, ``anthropic-verify.sh``,
    ``stat``) via a per-test ``tmp_bin`` directory placed first on ``PATH``.
  * Redirect ``$HOME`` to ``tmp_path`` so the manifest cache and openclaw
    home directory don't pollute the developer's real environment.
  * Bypass the script's self-update / TTY / re-exec guards with
    ``ANTHROPIC_ROTATE_SKIP_SELF_UPDATE=1`` and
    ``ANTHROPIC_ROTATE_SKIP_TTY_CHECK=1``.
  * Supply a synthetic ``sk-ant-...`` key on stdin to clear the shape check.

The script itself is the system-under-test. No Python module under
``anthropic_verify`` is exercised by these tests — that surface is
covered by WP01/WP02 tests.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import time
from pathlib import Path
from textwrap import dedent

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ROTATE_SCRIPT = REPO_ROOT / "scripts" / "security" / "anthropic-rotate.sh"
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "security" / "anthropic-verify.sh"

# A synthetic, fixed-format value that satisfies the script's `sk-ant-*` shape
# check. Not a real Anthropic key.
TEST_KEY = "sk-ant-test-WP03-rotation-gate-key-value-padding-to-real-length-xxxx"


# --------------------------------------------------------------------------- #
# Stub-binary helpers
# --------------------------------------------------------------------------- #


def _write_stub(path: Path, body: str) -> None:
    path.write_text(dedent(body).lstrip())
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _make_tmp_bin(tmp_path: Path, *, verify_exit: int = 0, verify_stdout: str = "") -> Path:
    """Create a tmp_bin/ holding stubs for openclaw, systemctl, stat,
    and a synthetic anthropic-verify wrapper.

    The verify stub respects ``verify_exit`` and emits ``verify_stdout`` on
    stdout. Tests that want shadow behavior pass ``verify_exit=2`` and a
    canned FIND line.
    """
    tmp_bin = tmp_path / "bin"
    tmp_bin.mkdir()
    # openclaw: dispatch a fixed JSON for `cron run --wait`, no-op everything else.
    _write_stub(
        tmp_bin / "openclaw",
        """
        #!/usr/bin/env bash
        # Stub for tests. Real openclaw is not on PATH in CI / mac dev boxes.
        case "$1 $2 $3" in
          "cron run --wait")
            # `openclaw cron run --wait --wait-timeout 90s <ID>` arg shape.
            echo '{"status":"ok","output":"stub liveness probe"}'
            exit 0
            ;;
          "doctor --fix "*|"doctor --fix")
            exit 0
            ;;
          "models auth "*)
            # Drain stdin (the key) so the upstream pipe doesn't SIGPIPE.
            cat >/dev/null
            exit 0
            ;;
        esac
        # Default no-op success.
        cat >/dev/null 2>&1 || true
        exit 0
        """,
    )
    # systemctl: report "active" for is-active queries, no-op for restart.
    _write_stub(
        tmp_bin / "systemctl",
        """
        #!/usr/bin/env bash
        for arg in "$@"; do
          if [[ "$arg" == "is-active" ]]; then
            exit 0
          fi
        done
        exit 0
        """,
    )
    # stat: emit a one-liner that matches the script's diagnostic format.
    # The script already falls back to ``|| true`` for cross-platform safety,
    # but providing the stub keeps stdout predictable.
    _write_stub(
        tmp_bin / "stat",
        """
        #!/usr/bin/env bash
        # Minimal stub of GNU `stat -c FMT FILE`. Tests do not validate this
        # output beyond requiring it not abort the script.
        echo "  600 claude:claude $* (stub)"
        exit 0
        """,
    )
    # anthropic-verify stub: exit with the configured code; emit the canned
    # body on stdout (the script captures stdout+stderr together).
    verify_body = verify_stdout if verify_stdout else "ok    stub verify\n==> verify result: green (exit 0)"
    _write_stub(
        tmp_bin / "anthropic-verify-stub",
        f"""
        #!/usr/bin/env bash
        cat <<'VEND'
{verify_body}
VEND
        exit {verify_exit}
        """,
    )
    return tmp_bin


def _rotate_env(tmp_path: Path, tmp_bin: Path, *, verify_bin: Path | None = None) -> dict[str, str]:
    """Return an env dict for invoking the rotation script under test."""
    plaintext = tmp_path / "secrets" / "anthropic"
    plaintext.parent.mkdir(parents=True, exist_ok=True)
    return {
        "HOME": str(tmp_path),
        "PATH": f"{tmp_bin}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        "ANTHROPIC_ROTATE_PLAINTEXT_FILE": str(plaintext),
        "ANTHROPIC_VERIFY_BIN": str(verify_bin or (tmp_bin / "anthropic-verify-stub")),
        "ANTHROPIC_ROTATE_OPENCLAW_HOME": str(tmp_path / ".openclaw"),
        "ANTHROPIC_ROTATE_GATEWAY_RESTART_CMD": "true",
        "ANTHROPIC_ROTATE_SKIP_SELF_UPDATE": "1",
        "ANTHROPIC_ROTATE_SKIP_TTY_CHECK": "1",
        "LANG": "C",
        "LC_ALL": "C",
    }


def _run_rotation(env: dict[str, str], *args: str, stdin: str = TEST_KEY + "\n",
                  timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(ROTATE_SCRIPT), *args],
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _read_manifest(tmp_path: Path) -> tuple[Path, dict]:
    cache = tmp_path / ".cache" / "anthropic-rotate"
    manifests = sorted(cache.glob("manifest.*.json"))
    assert manifests, f"no manifest written under {cache}"
    assert len(manifests) == 1, f"expected one manifest, found {manifests}"
    return manifests[0], json.loads(manifests[0].read_text())


# --------------------------------------------------------------------------- #
# T013 — manifest written before any artifact is touched
# --------------------------------------------------------------------------- #


def test_manifest_written_at_rotation_start(tmp_path):
    """Manifest exists with expected JSON shape (FR-013 transitively)."""
    tmp_bin = _make_tmp_bin(tmp_path, verify_exit=0)
    env = _rotate_env(tmp_path, tmp_bin)
    proc = _run_rotation(env)
    assert proc.returncode == 0, f"stderr=\n{proc.stderr}\nstdout=\n{proc.stdout}"

    manifest_path, manifest = _read_manifest(tmp_path)
    assert manifest_path.parent == tmp_path / ".cache" / "anthropic-rotate"
    assert manifest_path.stat().st_mode & 0o777 == 0o600
    # Shape
    assert isinstance(manifest["rotation_ts"], int)
    assert manifest["rotation_ts"] > 0
    assert manifest["started_at_iso"].endswith("Z")
    backups = manifest["backups"]
    assert set(backups.keys()) == {"plaintext_file", "openclaw_json", "sqlite_import_bak"}
    # All three backup paths are computed in advance and recorded.
    assert backups["plaintext_file"].endswith(f".pre-rotate.{manifest['rotation_ts']}.bak")
    assert backups["openclaw_json"].endswith("openclaw.json.bak")
    assert backups["sqlite_import_bak"].endswith(
        f"auth-profiles.json.sqlite-import.{manifest['rotation_ts']}.bak"
    )


# --------------------------------------------------------------------------- #
# T013 — verify gate, green path
# --------------------------------------------------------------------------- #


def test_verify_gate_green_path_exits_0_and_marks_manifest_passed(tmp_path):
    tmp_bin = _make_tmp_bin(tmp_path, verify_exit=0,
                            verify_stdout="==> stub verify\nok    everything\n==> verify result: green (exit 0)")
    env = _rotate_env(tmp_path, tmp_bin)
    proc = _run_rotation(env)
    assert proc.returncode == 0, f"stderr=\n{proc.stderr}\nstdout=\n{proc.stdout}"
    assert "verify: green" in proc.stdout
    assert "anthropic-rotate complete" in proc.stdout

    _, manifest = _read_manifest(tmp_path)
    assert manifest["verify_outcome"] == "passed"
    assert manifest["rotation_completed_at_iso"] is not None
    assert manifest["rotation_completed_at_iso"].endswith("Z")


# --------------------------------------------------------------------------- #
# T013 — verify gate, shadow path (exit 2)
# --------------------------------------------------------------------------- #


def test_verify_gate_shadow_path_exits_2_emits_rollback_and_marks_failed(tmp_path):
    canned_finding = (
        "==> anthropic-verify --check\n"
        "FIND  shadow felix-admin-capture: auth_profile_store=1 auth_profile_state=1\n"
        "==> verify result: shadow detected (exit 2)"
    )
    tmp_bin = _make_tmp_bin(tmp_path, verify_exit=2, verify_stdout=canned_finding)
    env = _rotate_env(tmp_path, tmp_bin)
    proc = _run_rotation(env)
    assert proc.returncode == 2, f"stderr=\n{proc.stderr}\nstdout=\n{proc.stdout}"

    # The verifier's stdout body is piped to stderr, then the rotation-script
    # heredoc with the rollback command is appended.
    manifest_path, manifest = _read_manifest(tmp_path)
    rotation_ts = manifest["rotation_ts"]

    assert "FIND  shadow felix-admin-capture" in proc.stderr
    assert "ROTATION VERIFY FAILED" in proc.stderr
    assert f"--rollback {rotation_ts}" in proc.stderr
    # The exact one-line invocation form must appear (operator copy-pastes it).
    assert (
        f"/home/claude/kg-automation/scripts/security/anthropic-rotate.sh --rollback {rotation_ts}"
        in proc.stderr
    )

    assert manifest["verify_outcome"] == "failed"
    assert manifest["rotation_completed_at_iso"] is None


# --------------------------------------------------------------------------- #
# T013 — rollback, manifest missing
# --------------------------------------------------------------------------- #


def test_rollback_manifest_missing_exits_1(tmp_path):
    tmp_bin = _make_tmp_bin(tmp_path)
    env = _rotate_env(tmp_path, tmp_bin)
    proc = subprocess.run(
        ["bash", str(ROTATE_SCRIPT), "--rollback", "9999999999"],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert proc.returncode == 1
    assert "manifest not found" in proc.stderr


# --------------------------------------------------------------------------- #
# T013 — rollback, all three backups present
# --------------------------------------------------------------------------- #


def _seed_post_rotation_state(tmp_path: Path, rotation_ts: int, plaintext_file: Path) -> dict:
    """Build a synthetic post-rotation state on disk + manifest, mimicking
    what a real rotation would have left behind. Returns the manifest dict."""
    openclaw_home = tmp_path / ".openclaw"
    agents_main = openclaw_home / "agents" / "main" / "agent"
    agents_main.mkdir(parents=True, exist_ok=True)
    plaintext_file.parent.mkdir(parents=True, exist_ok=True)

    plaintext_bak = Path(f"{plaintext_file}.pre-rotate.{rotation_ts}.bak")
    openclaw_json = openclaw_home / "openclaw.json"
    openclaw_json_bak = Path(f"{openclaw_json}.bak")
    sqlite_import_bak = agents_main / f"auth-profiles.json.sqlite-import.{rotation_ts}.bak"

    # Pre-rotation values (what we want to restore TO)
    plaintext_bak.write_text("PRE-ROTATION-PLAINTEXT")
    plaintext_bak.chmod(0o600)
    openclaw_json_bak.write_text('{"pre":"rotation","ok":true}')
    openclaw_json_bak.chmod(0o600)
    sqlite_import_bak.write_text('{"profiles":{"anthropic:default":{"key":"PRE-ROTATION-KEY"}}}')
    sqlite_import_bak.chmod(0o600)

    # Post-rotation values (what we want to overwrite OUT OF)
    plaintext_file.write_text("POST-ROTATION-PLAINTEXT")
    plaintext_file.chmod(0o600)
    openclaw_json.write_text('{"post":"rotation","drifted":true}')
    openclaw_json.chmod(0o600)
    auth_profiles_current = agents_main / "auth-profiles.json"
    auth_profiles_current.write_text('{"profiles":{"anthropic:default":{"key":"POST-ROTATION-KEY"}}}')
    auth_profiles_current.chmod(0o600)

    manifest_dir = tmp_path / ".cache" / "anthropic-rotate"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "rotation_ts": rotation_ts,
        "started_at_iso": "2026-06-13T18:00:00Z",
        "backups": {
            "plaintext_file": str(plaintext_bak),
            "openclaw_json": str(openclaw_json_bak),
            "sqlite_import_bak": str(sqlite_import_bak),
        },
        "rotation_completed_at_iso": None,
        "verify_outcome": "failed",
    }
    manifest_path = manifest_dir / f"manifest.{rotation_ts}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    manifest_path.chmod(0o600)
    return manifest


def test_rollback_restores_all_three_artifacts(tmp_path):
    tmp_bin = _make_tmp_bin(tmp_path)
    env = _rotate_env(tmp_path, tmp_bin)
    plaintext_file = Path(env["ANTHROPIC_ROTATE_PLAINTEXT_FILE"])
    rotation_ts = 1700000000
    _seed_post_rotation_state(tmp_path, rotation_ts, plaintext_file)

    proc = subprocess.run(
        ["bash", str(ROTATE_SCRIPT), "--rollback", str(rotation_ts)],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert proc.returncode == 0, f"stderr=\n{proc.stderr}\nstdout=\n{proc.stdout}"

    # 1. plaintext restored to pre-rotation value
    assert plaintext_file.read_text() == "PRE-ROTATION-PLAINTEXT"
    # 2. openclaw.json restored
    assert (tmp_path / ".openclaw" / "openclaw.json").read_text() == '{"pre":"rotation","ok":true}'
    # 3. SQLite import bak content restored at the canonical auth-profiles.json path
    auth_profiles = tmp_path / ".openclaw" / "agents" / "main" / "agent" / "auth-profiles.json"
    assert "PRE-ROTATION-KEY" in auth_profiles.read_text()


# --------------------------------------------------------------------------- #
# T013 — rollback, one backup missing → no mutation
# --------------------------------------------------------------------------- #


def test_rollback_backup_missing_exits_1_and_no_mutation(tmp_path):
    tmp_bin = _make_tmp_bin(tmp_path)
    env = _rotate_env(tmp_path, tmp_bin)
    plaintext_file = Path(env["ANTHROPIC_ROTATE_PLAINTEXT_FILE"])
    rotation_ts = 1700000001
    _seed_post_rotation_state(tmp_path, rotation_ts, plaintext_file)

    # Delete the plaintext backup; rollback should refuse partial restoration.
    plaintext_bak = Path(f"{plaintext_file}.pre-rotate.{rotation_ts}.bak")
    plaintext_bak.unlink()

    # Capture post-rotation contents to compare after the failed rollback.
    plaintext_before = plaintext_file.read_text()
    openclaw_json_path = tmp_path / ".openclaw" / "openclaw.json"
    openclaw_json_before = openclaw_json_path.read_text()
    auth_profiles_path = tmp_path / ".openclaw" / "agents" / "main" / "agent" / "auth-profiles.json"
    auth_profiles_before = auth_profiles_path.read_text()

    proc = subprocess.run(
        ["bash", str(ROTATE_SCRIPT), "--rollback", str(rotation_ts)],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert proc.returncode == 1
    assert "backup(s) missing" in proc.stderr
    assert str(plaintext_bak) in proc.stderr

    # No mutation: each of the three artifacts still holds its pre-rollback value.
    assert plaintext_file.read_text() == plaintext_before
    assert openclaw_json_path.read_text() == openclaw_json_before
    assert auth_profiles_path.read_text() == auth_profiles_before


# --------------------------------------------------------------------------- #
# T013 — NFR-006: verify-gate overhead ≤ 5 s
# --------------------------------------------------------------------------- #


def test_verify_gate_overhead_under_5_seconds(tmp_path):
    """The verify-gate spawn must add ≤ 5 s to a successful rotation.

    The stub verifier returns immediately, so this measures the rotation
    script's own gate-handling cost (subprocess spawn + manifest update).
    The whole rotation must complete well under 5 s on a healthy laptop.
    """
    tmp_bin = _make_tmp_bin(tmp_path, verify_exit=0)
    env = _rotate_env(tmp_path, tmp_bin)

    t0 = time.monotonic()
    proc = _run_rotation(env)
    elapsed = time.monotonic() - t0

    assert proc.returncode == 0, f"stderr=\n{proc.stderr}\nstdout=\n{proc.stdout}"
    # Whole rotation; the bar is lenient — NFR-006 specifies ≤ 5 s
    # overhead from the verify step alone. With stub binaries the whole
    # rotation should complete in ~1 s; we assert well under 5 s.
    assert elapsed < 5.0, f"rotation took {elapsed:.2f}s (NFR-006 budget is 5 s)"


# --------------------------------------------------------------------------- #
# Edge case — argparse: --rollback without a timestamp fails fast
# --------------------------------------------------------------------------- #


def test_rollback_requires_timestamp_argument(tmp_path):
    tmp_bin = _make_tmp_bin(tmp_path)
    env = _rotate_env(tmp_path, tmp_bin)
    proc = subprocess.run(
        ["bash", str(ROTATE_SCRIPT), "--rollback"],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert proc.returncode == 2
    assert "requires a timestamp argument" in proc.stderr

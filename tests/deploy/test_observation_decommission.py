"""Tests for the Phase-2 observation stray-tree decommission (WP03 / T011).

Mission: observation-digest-repoint-01KWS2E2 (fast-follow of #656 → #659)

This is the highest-risk WP: an irreversible whole-tree deletion.  Every
external effect is mocked — ``verify_restic_recent``, all subprocess calls
(git / systemctl / pgrep / restic), and ``shutil.rmtree`` — so no test ever
deletes anything real or touches office2.

Control-flow guarantee under test: ``shutil.rmtree`` is unreachable unless ALL
four precondition gates pass.  For EACH gate there is a failing-case test that
asserts the module exits non-zero AND ``rmtree`` was never called (the target
dir still exists).

Test matrix
-----------
T-GATE-A     No recent Restic snapshot (and no attestation) → abort, no delete.
T-GATE-B     HEAD not on origin → abort, no delete.
T-GATE-C     A live writer is running → abort, no delete.
T-GATE-D     inbox-prescan-*.md newer than the cutover → abort, no delete.
T-DRY-SUB    --dry-run via subprocess exits 0 and mutates nothing.
T-XBIT       The entrypoint has +x and the sys.path shim.
T-PRIVACY    No _private / secret / descendant path leaks to stdout/stderr/dict.
T-HAPPY      All gates pass → rmtree called once with source_root; timer
             stopped before + started after.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace
from pathlib import Path

import pytest

from scripts.deploy import observation_decommission as od
from scripts.deploy.lib import LibResult

_WORKTREE_ROOT = Path(__file__).resolve().parents[2]
_ENTRYPOINT = (
    _WORKTREE_ROOT / "scripts" / "deploy" / "decommission-observation-stray-tree.py"
)


# ---------------------------------------------------------------------------
# Fake stray-tree builder (mirrors the WP02 test fixture)
# ---------------------------------------------------------------------------

def _make_stray_tree(root: Path, *, prescan_mtime: float | None = None) -> None:
    """Build a minimal fake /home/claude/second-brain tree.

    Includes per-agent JSONL logs (in scope for the final merge), a top-level
    inbox-prescan markdown, and a ``_private`` growth dir that must never be
    read, walked, or logged.
    """
    logs = root / "agents" / "logs"
    (logs / "felixtest").mkdir(parents=True)
    (logs / "felixtest" / "2026-01-01.jsonl").write_text(
        '{"agent": "felixtest", "action": "run"}\n', encoding="utf-8"
    )

    prescan = logs / "inbox-prescan-2026-06-30.md"
    prescan.write_text("# forensic\n", encoding="utf-8")
    # Default to a pre-cutover mtime (2026-06-30) so the mtime gate passes unless
    # a test explicitly requests a post-cutover timestamp.
    if prescan_mtime is None:
        prescan_mtime = time.mktime(time.strptime("2026-06-30", "%Y-%m-%d"))
    os.utime(prescan, (prescan_mtime, prescan_mtime))

    # A _private path that must never be walked toward or emitted anywhere.
    private = root / "vault" / "02-Growth" / "_private"
    private.mkdir(parents=True)
    (private / "secret.md").write_text("TOP SECRET\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Command-fake factory: dispatches on argv so a single monkeypatch of
# ``od._run_cmd`` controls git / systemctl / pgrep / restic behaviour.
# ---------------------------------------------------------------------------

def _make_fake_run(
    call_log: list[str],
    *,
    git_origin: bool = True,
    writer: bool = False,
    timer_stop_ok: bool = True,
):
    def _fake(cmd, timeout=None):  # noqa: ANN001
        prog = cmd[0]
        if prog == "git":
            out = "  origin/main\n" if git_origin else "  backup/mirror\n"
            return SimpleNamespace(returncode=0, stdout=out, stderr="")
        if prog == "systemctl":
            # ["systemctl", "--user", "stop"|"start", TIMER]
            action = cmd[2]
            call_log.append(f"systemctl-{action}")
            rc = 0 if (action == "start" or timer_stop_ok) else 1
            return SimpleNamespace(returncode=rc, stdout="", stderr="")
        if prog == "pgrep":
            rc = 0 if writer else 1
            out = "4242\n" if writer else ""
            return SimpleNamespace(returncode=rc, stdout=out, stderr="")
        # restic and anything else: benign default.
        return SimpleNamespace(returncode=0, stdout="[]", stderr="")

    return _fake


def _spy_rmtree(call_log: list[str], *, really_delete: bool):
    real_rmtree = shutil.rmtree
    calls: list[Path] = []

    def _spy(path, *args, **kwargs):  # noqa: ANN001
        calls.append(Path(path))
        call_log.append("rmtree")
        if really_delete:
            real_rmtree(path, *args, **kwargs)

    _spy.calls = calls  # type: ignore[attr-defined]
    return _spy


def _ok_snapshot(*args, **kwargs):
    return LibResult(ok=True, summary="snapshot 1.0h ago", details={})


def _stale_snapshot(*args, **kwargs):
    return LibResult(
        ok=False, summary="no recent snapshot", details={"error_code": "RESTIC_TOO_OLD"}
    )


# ---------------------------------------------------------------------------
# T-GATE-A: no recent Restic snapshot (and no attestation) → abort, no delete
# ---------------------------------------------------------------------------

def test_gate_a_no_snapshot_aborts_without_delete(tmp_path, monkeypatch):
    root = tmp_path / "second-brain"
    vault = tmp_path / "vault-logs"
    _make_stray_tree(root)

    call_log: list[str] = []
    monkeypatch.setattr(od, "verify_restic_recent", _stale_snapshot)
    monkeypatch.setattr(od, "_run_cmd", _make_fake_run(call_log))
    spy = _spy_rmtree(call_log, really_delete=False)
    monkeypatch.setattr(od.shutil, "rmtree", spy)

    # No --attest-backup-coverage: recency alone is insufficient AND stale.
    rc = od.main(
        ["--apply", "--source-root", str(root), "--vault-logs-dir", str(vault)]
    )

    assert rc != 0, "stale snapshot must abort non-zero"
    assert spy.calls == [], "rmtree must NOT be called when a gate fails"
    assert root.exists(), "source tree must remain intact"
    assert "rmtree" not in call_log


# ---------------------------------------------------------------------------
# T-GATE-B: HEAD not present on origin → abort, no delete
# ---------------------------------------------------------------------------

def test_gate_b_head_not_on_origin_aborts_without_delete(tmp_path, monkeypatch):
    root = tmp_path / "second-brain"
    vault = tmp_path / "vault-logs"
    _make_stray_tree(root)

    call_log: list[str] = []
    monkeypatch.setattr(od, "verify_restic_recent", _ok_snapshot)
    monkeypatch.setattr(od, "_run_cmd", _make_fake_run(call_log, git_origin=False))
    spy = _spy_rmtree(call_log, really_delete=False)
    monkeypatch.setattr(od.shutil, "rmtree", spy)

    rc = od.main(
        [
            "--apply",
            "--attest-backup-coverage",
            "--source-root", str(root),
            "--vault-logs-dir", str(vault),
        ]
    )

    assert rc != 0, "HEAD not on origin must abort non-zero"
    assert spy.calls == [], "rmtree must NOT be called when a gate fails"
    assert root.exists()
    # Origin gate is read-only and precedes quiesce: the timer is never stopped.
    assert "systemctl-stop" not in call_log


# ---------------------------------------------------------------------------
# T-GATE-C: a live writer is running → abort, no delete
# ---------------------------------------------------------------------------

def test_gate_c_live_writer_aborts_without_delete(tmp_path, monkeypatch):
    root = tmp_path / "second-brain"
    vault = tmp_path / "vault-logs"
    _make_stray_tree(root)

    call_log: list[str] = []
    monkeypatch.setattr(od, "verify_restic_recent", _ok_snapshot)
    monkeypatch.setattr(od, "_run_cmd", _make_fake_run(call_log, writer=True))
    spy = _spy_rmtree(call_log, really_delete=False)
    monkeypatch.setattr(od.shutil, "rmtree", spy)

    # Keep the bounded quiesce wait fast: no real sleeping, deadline elapses at once.
    monkeypatch.setattr(od.time, "sleep", lambda *_a, **_k: None)
    ticks = iter([0.0, 1000.0, 2000.0, 3000.0])
    monkeypatch.setattr(od.time, "monotonic", lambda: next(ticks))

    rc = od.main(
        [
            "--apply",
            "--attest-backup-coverage",
            "--source-root", str(root),
            "--vault-logs-dir", str(vault),
        ]
    )

    assert rc != 0, "an active writer must abort non-zero"
    assert spy.calls == [], "rmtree must NOT be called when a writer is active"
    assert root.exists()
    # The timer was stopped for quiesce, so it MUST be restarted on the abort path.
    assert "systemctl-stop" in call_log
    assert "systemctl-start" in call_log
    assert call_log.index("systemctl-start") > call_log.index("systemctl-stop")


# ---------------------------------------------------------------------------
# T-GATE-D: inbox-prescan-*.md newer than the cutover → abort, no delete
# ---------------------------------------------------------------------------

def test_gate_d_fresh_prescan_aborts_without_delete(tmp_path, monkeypatch):
    root = tmp_path / "second-brain"
    vault = tmp_path / "vault-logs"
    # mtime set to well AFTER INBOX_PRESCAN_CUTOFF (2026-07-04).
    fresh = time.mktime(time.strptime("2026-07-05", "%Y-%m-%d"))
    _make_stray_tree(root, prescan_mtime=fresh)

    call_log: list[str] = []
    monkeypatch.setattr(od, "verify_restic_recent", _ok_snapshot)
    monkeypatch.setattr(od, "_run_cmd", _make_fake_run(call_log))
    spy = _spy_rmtree(call_log, really_delete=False)
    monkeypatch.setattr(od.shutil, "rmtree", spy)

    rc = od.main(
        [
            "--apply",
            "--attest-backup-coverage",
            "--source-root", str(root),
            "--vault-logs-dir", str(vault),
        ]
    )

    assert rc != 0, "a post-cutover inbox-prescan must abort non-zero"
    assert spy.calls == [], "rmtree must NOT be called when a gate fails"
    assert root.exists()
    # inbox-prescan gate is read-only and precedes quiesce.
    assert "systemctl-stop" not in call_log


# ---------------------------------------------------------------------------
# T-XBIT: entrypoint executable bit + sys.path shim
# ---------------------------------------------------------------------------

def test_entrypoint_has_exec_bit_and_shim():
    assert os.access(_ENTRYPOINT, os.X_OK), "entrypoint must be executable (git mode 100755)"
    text = _ENTRYPOINT.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env python3"), "missing shebang"
    assert "_REPO_ROOT = Path(__file__).resolve().parents[2]" in text, "missing sys.path shim"
    assert "sys.path.insert(0, str(_REPO_ROOT))" in text, "shim does not insert repo root"


# ---------------------------------------------------------------------------
# T-DRY-SUB: subprocess dry-run exits 0, mutates nothing
# ---------------------------------------------------------------------------

def test_dry_run_via_subprocess_exits_zero_and_no_mutation(tmp_path):
    root = tmp_path / "second-brain"
    vault = tmp_path / "vault-logs"
    _make_stray_tree(root)

    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run(
        [
            str(_ENTRYPOINT),
            "--dry-run",
            "--source-root", str(root),
            "--vault-logs-dir", str(vault),
        ],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, f"dry-run must exit 0.\nSTDERR:\n{proc.stderr}\nSTDOUT:\n{proc.stdout}"

    plan = json.loads(proc.stdout.strip())
    assert plan["dry_run"] is True
    assert plan["plan_only"] is True
    assert plan["deleted"] is False

    # No mutation whatsoever.
    assert root.exists(), "dry-run must not touch the source tree"
    assert (root / "vault" / "02-Growth" / "_private" / "secret.md").exists()
    assert not vault.exists(), "dry-run must not create the vault dir"

    # No _private / descendant leakage in a dry-run.
    assert "_private" not in proc.stdout
    assert "_private" not in proc.stderr
    assert "secret" not in proc.stdout


# ---------------------------------------------------------------------------
# T-PRIVACY: no _private / secret / descendant path leaks (dry-run + mocked apply)
# ---------------------------------------------------------------------------

_FORBIDDEN = ("_private", "secret", "02-Growth", "vault/02-Growth")


def _assert_clean(*blobs: str, source_root: Path) -> None:
    combined = "\n".join(blobs)
    for needle in _FORBIDDEN:
        assert needle not in combined, f"leaked forbidden token {needle!r}"
    # The only descendant path family permitted is agents/logs/*; source_root
    # itself is allowed. Assert no other descendant of source_root appears.
    for line in combined.splitlines():
        for token in line.replace("=", " ").split():
            if token.startswith(str(source_root)) and token != str(source_root):
                rel = token[len(str(source_root)):].lstrip("/")
                assert rel.startswith("agents/logs/"), f"leaked descendant path: {token}"


def test_privacy_no_descendant_or_private_leak(tmp_path, monkeypatch, capsys):
    root = tmp_path / "second-brain"
    vault = tmp_path / "vault-logs"
    _make_stray_tree(root)

    # --- dry-run (fully in-process) ---
    monkeypatch.setattr(od, "verify_restic_recent", _stale_snapshot)
    rc_dry = od.main(
        ["--dry-run", "--source-root", str(root), "--vault-logs-dir", str(vault)]
    )
    out = capsys.readouterr()
    assert rc_dry == 0
    dry_dict = json.dumps(json.loads(out.out.strip()))
    _assert_clean(out.out, out.err, dry_dict, source_root=root)

    # --- mocked apply (all gates pass; rmtree mocked to really remove) ---
    call_log: list[str] = []
    monkeypatch.setattr(od, "verify_restic_recent", _ok_snapshot)
    monkeypatch.setattr(od, "_run_cmd", _make_fake_run(call_log))
    spy = _spy_rmtree(call_log, really_delete=True)
    monkeypatch.setattr(od.shutil, "rmtree", spy)

    result = od.decommission(
        root, vault, dry_run=False, attest_backup_coverage=True, wait_s=0.0
    )
    out = capsys.readouterr()
    assert result["deleted"] is True
    _assert_clean(out.out, out.err, json.dumps(result), source_root=root)


# ---------------------------------------------------------------------------
# T-HAPPY: all gates pass → single root-level rmtree; timer stop→delete→start
# ---------------------------------------------------------------------------

def test_happy_path_single_root_delete_and_timer_cycle(tmp_path, monkeypatch):
    root = tmp_path / "second-brain"
    vault = tmp_path / "vault-logs"
    _make_stray_tree(root)

    call_log: list[str] = []
    monkeypatch.setattr(od, "verify_restic_recent", _ok_snapshot)
    monkeypatch.setattr(od, "_run_cmd", _make_fake_run(call_log))
    spy = _spy_rmtree(call_log, really_delete=True)
    monkeypatch.setattr(od.shutil, "rmtree", spy)

    rc = od.main(
        [
            "--apply",
            "--attest-backup-coverage",
            "--source-root", str(root),
            "--vault-logs-dir", str(vault),
        ]
    )

    assert rc == 0, "all gates pass → success exit 0"
    # Exactly one root-level delete, targeting source_root (never a descendant).
    assert spy.calls == [root], f"expected single rmtree(source_root); got {spy.calls}"
    assert not root.exists(), "post-check: source_root must be absent"

    # Timer stopped BEFORE the delete and restarted AFTER it.
    assert call_log.count("systemctl-stop") == 1
    assert call_log.count("systemctl-start") == 1
    i_stop = call_log.index("systemctl-stop")
    i_del = call_log.index("rmtree")
    i_start = call_log.index("systemctl-start")
    assert i_stop < i_del < i_start, f"bad ordering: {call_log}"


# ---------------------------------------------------------------------------
# Coverage gate: recency alone is insufficient without attestation.
# ---------------------------------------------------------------------------

def test_coverage_required_when_not_attested(tmp_path, monkeypatch):
    """A fresh snapshot but no coverage proof and no attestation → gate a fails."""
    root = tmp_path / "second-brain"
    _make_stray_tree(root)

    # Recency passes, but restic reports no snapshot covering source_root.
    monkeypatch.setattr(od, "verify_restic_recent", _ok_snapshot)

    def _fake_run(cmd, timeout=None):  # noqa: ANN001
        if cmd[0] == "restic":
            return SimpleNamespace(
                returncode=0, stdout=json.dumps([{"paths": ["/somewhere/else"]}]), stderr=""
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(od, "_run_cmd", _fake_run)

    ok, detail = od.check_snapshot_coverage(root, attest_backup_coverage=False)
    assert ok is False
    assert detail["reason"] == "backup_coverage_unproven"


# ---------------------------------------------------------------------------
# T-QUIESCE-ERR (post-merge Codex finding): the writer-check subprocess errors
# AFTER the timer is stopped. _run_cmd must not raise (maps to rc 124), the
# gate must fail-safe, and the timer MUST still be restarted — never left
# stopped after a failed destructive deploy.
# ---------------------------------------------------------------------------

def test_run_cmd_maps_timeout_to_nonzero(monkeypatch):
    """_run_cmd converts TimeoutExpired/OSError into a synthetic non-zero result
    instead of raising, so an exception can never escape after the timer stop."""
    def _raise_timeout(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd=["pgrep"], timeout=10.0)

    monkeypatch.setattr(od.subprocess, "run", _raise_timeout)
    proc = od._run_cmd(["pgrep", "-f", "summarize.py"], timeout=10.0)
    assert proc.returncode == 124

    def _raise_oserror(*_a, **_k):
        raise OSError("boom")

    monkeypatch.setattr(od.subprocess, "run", _raise_oserror)
    proc2 = od._run_cmd(["systemctl", "--user", "stop", "x"])
    assert proc2.returncode == 124


def test_quiesce_writer_check_error_aborts_and_restarts_timer(tmp_path, monkeypatch):
    """systemctl-stop succeeds, then pgrep is unconfirmable (rc 124). The gate
    must abort (no delete) AND the timer must be restarted on the abort path."""
    root = tmp_path / "second-brain"
    vault = tmp_path / "vault-logs"
    _make_stray_tree(root)

    call_log: list[str] = []

    def _fake(cmd, timeout=None):  # noqa: ANN001
        prog = cmd[0]
        if prog == "git":
            return SimpleNamespace(returncode=0, stdout="  origin/main\n", stderr="")
        if prog == "systemctl":
            action = cmd[2]
            call_log.append(f"systemctl-{action}")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if prog == "pgrep":
            # Unconfirmable: mirrors _run_cmd's synthetic timeout result (rc 124).
            call_log.append("pgrep-error")
            return SimpleNamespace(returncode=124, stdout="", stderr="timeout")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(od, "verify_restic_recent", _ok_snapshot)
    monkeypatch.setattr(od, "_run_cmd", _fake)
    spy = _spy_rmtree(call_log, really_delete=False)
    monkeypatch.setattr(od.shutil, "rmtree", spy)
    monkeypatch.setattr(od.time, "sleep", lambda *_a, **_k: None)

    rc = od.main(
        [
            "--apply",
            "--attest-backup-coverage",
            "--source-root", str(root),
            "--vault-logs-dir", str(vault),
        ]
    )

    assert rc != 0, "an unconfirmable writer check must abort non-zero (fail-safe)"
    assert spy.calls == [], "rmtree must NOT run when quiesce cannot be confirmed"
    assert root.exists()
    assert "systemctl-stop" in call_log
    assert "systemctl-start" in call_log, "timer MUST be restarted even on the error path"
    assert call_log.index("systemctl-start") > call_log.index("systemctl-stop")

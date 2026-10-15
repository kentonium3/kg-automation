"""dry_run_then_apply_gate and the installed-file report channel (#1072 WP03).

Real throwaway entrypoints: each one logs, per invocation, the report variable
it saw, and on ``--apply`` behaves as the test asks.
"""
from __future__ import annotations

import json
import os
import pathlib

import pytest

from scripts.deploy.lib import apply, installed_report as ir

CHANNEL_KEYS = {"installed_report", "installed_report_write_failed"}

A = {"source": "/repo/scripts/sync/systemd/a.timer", "dest": "/home/u/.config/systemd/user/a.timer"}
B = {"source": "/repo/scripts/sync/systemd/b.timer", "dest": "/home/u/.config/systemd/user/b.timer"}


def _entrypoint(tmp_path, *, apply_lines=(), exit_code=0):
    """Write an entrypoint; *apply_lines* are Python statements run on --apply,
    with ``report`` bound to the variable's value."""
    log = tmp_path / "seen.jsonl"
    ep = tmp_path / "ep.py"
    lines = [
        "#!/usr/bin/env python3",
        "import json, os, sys",
        f"with open({str(log)!r}, 'a') as fh:",
        f"    fh.write(json.dumps({{'mode': sys.argv[1], 'var': os.environ.get({ir.ENV_VAR!r}),"
        " 'foo': os.environ.get('FOO')}) + '\\n')",
        "if sys.argv[1] == '--apply':",
        f"    report = os.environ.get({ir.ENV_VAR!r})",
        *(f"    {line}" for line in apply_lines),
        f"    sys.exit({exit_code})",
    ]
    ep.write_text("\n".join(lines) + "\n")
    ep.chmod(0o755)
    return ep, log


def _write_lines(*entries):
    return [f"open(report, 'a').write({json.dumps(json.dumps(e))} + '\\n')" for e in entries]


def _seen(log):
    return [json.loads(line) for line in log.read_text().splitlines()]


def _manifest(ep, **over):
    m = {
        "schema_version": "v1",
        "name": "report-test",
        "mission_slug": "deploy-runtime-installed-report-01M4ZP8E",
        "tier": 3,
        "entrypoint": str(ep),
        "audited_surface": False,
        "created_at": "2026-10-15T00:00:00Z",
        "created_by": "kent@intentional.biz",
    }
    m.update(over)
    return m


@pytest.fixture(autouse=True)
def parent_env(monkeypatch, tmp_path):
    # The parent already holds a stale report path; nothing may inherit it.
    monkeypatch.setenv(ir.ENV_VAR, str(tmp_path / "stale-parent.jsonl"))
    monkeypatch.setenv("FOO", "bar")


def test_only_apply_sees_a_fresh_report_path(tmp_path):
    ep, log = _entrypoint(tmp_path, apply_lines=_write_lines(A, B))
    res = apply.dry_run_then_apply_gate(_manifest(ep), "m.yaml")
    assert res.ok, res
    seen = {s["mode"]: s for s in _seen(log)}
    assert seen["--dry-run"]["var"] is None
    path = seen["--apply"]["var"]
    assert path and path != str(tmp_path / "stale-parent.jsonl")
    assert os.path.basename(os.path.dirname(path)).startswith("felix-installed-report-")
    assert not os.path.exists(os.path.dirname(path)), "temp dir removed afterwards"
    assert res.details["installed_report"]["entries"] == [A, B]
    assert res.details["installed_report_write_failed"] is False


def test_other_variables_are_preserved(tmp_path):
    ep, log = _entrypoint(tmp_path)
    assert apply.dry_run_then_apply_gate(_manifest(ep), "m.yaml").ok
    assert {s["foo"] for s in _seen(log)} == {"bar"}


def test_pre_and_post_commands_never_see_the_variable(tmp_path):
    ep, _ = _entrypoint(tmp_path, apply_lines=_write_lines(A))
    check = f'test -z "${ir.ENV_VAR}"'
    res = apply.dry_run_then_apply_gate(
        _manifest(ep, verification={"pre": [check], "post": [check]}), "m.yaml")
    assert res.ok, res.summary


def test_apply_failure_still_carries_the_report(tmp_path):
    ep, _ = _entrypoint(tmp_path, apply_lines=_write_lines(A), exit_code=1)
    res = apply.dry_run_then_apply_gate(_manifest(ep), "m.yaml")
    assert not res.ok and res.details["phase"] == apply.PHASE_ENTRYPOINT_APPLY
    assert res.details["installed_report"]["entries"] == [A]


def test_post_verification_failure_still_carries_the_report(tmp_path):
    ep, _ = _entrypoint(tmp_path, apply_lines=_write_lines(A))
    res = apply.dry_run_then_apply_gate(_manifest(ep, verification={"post": ["false"]}), "m.yaml")
    assert not res.ok and res.details["phase"] == apply.PHASE_VERIFICATION_POST
    assert res.details["installed_report"]["entries"] == [A]


def test_write_failed_marker_is_found_after_long_stderr(tmp_path):
    body = [
        "sys.stderr.write('x' * 5000 + '\\n')",
        f"sys.stderr.write({ir.WRITE_FAILED_MARKER!r} + ': OSError: nope\\n')",
    ]
    ep, _ = _entrypoint(tmp_path, apply_lines=body)
    res = apply.dry_run_then_apply_gate(_manifest(ep), "m.yaml")
    assert res.ok
    assert res.details["installed_report_write_failed"] is True


def test_an_entrypoint_that_reports_nothing_is_missing(tmp_path):
    ep, _ = _entrypoint(tmp_path)
    res = apply.dry_run_then_apply_gate(_manifest(ep), "m.yaml")
    assert res.details["installed_report"]["missing"] is True
    assert res.details["installed_report"]["entries"] == []


@pytest.mark.parametrize("over", [
    {"tier": 0},                                  # tier guard
    {"verification": {"pre": ["false"]}},         # pre-check
])
def test_returns_before_apply_never_carry_the_channel(tmp_path, over):
    ep, _ = _entrypoint(tmp_path)
    res = apply.dry_run_then_apply_gate(_manifest(ep, **over), "m.yaml")
    assert not res.ok and not (CHANNEL_KEYS & set(res.details))


def test_dry_run_failure_never_carries_the_channel(tmp_path):
    ep = tmp_path / "ep.sh"
    ep.write_text('#!/bin/bash\n[ "$1" = "--dry-run" ] && exit 3\nexit 0\n')
    ep.chmod(0o755)
    res = apply.dry_run_then_apply_gate(_manifest(ep), "m.yaml")
    assert res.details["phase"] == apply.PHASE_ENTRYPOINT_DRY_RUN
    assert not (CHANNEL_KEYS & set(res.details))


def test_mkdtemp_failure_is_a_warning_not_a_crash(tmp_path, monkeypatch):
    ep, log = _entrypoint(tmp_path)

    def boom(*a, **k):
        raise OSError("no tmp")

    monkeypatch.setattr(apply.tempfile, "mkdtemp", boom)
    res = apply.dry_run_then_apply_gate(_manifest(ep), "m.yaml")
    assert res.ok
    assert any("no tmp" in w for w in res.details["installed_report"]["warnings"])
    assert {s["var"] for s in _seen(log)} == {None}

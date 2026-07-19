"""Tests for scripts.openclaw.deploy.deploy_agent_skills (#775, WP01).

Mirrors the tests/openclaw/test_deploy_agent_prompts.py conventions (AdvanceResult
mock helper, patching the advance_checkout/deploylock seams). The alert bus
``emit`` is patched so the health path never touches the network. A NORMALIZING
deployed-side fixture is used (real bytes on both sides) so an echo can't hide a
divergence (banked #757 lesson).
"""
from __future__ import annotations

import contextlib
import json
import os
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.deploy.lib.gitsync import AdvanceResult
from scripts.deploy.lib.deploylock import LockUnavailable
from scripts.common.alert_bus.model import AlertResult
from scripts.openclaw.deploy import deploy_agent_skills as das


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_repo(tmp_path: Path, skills: dict[str, dict]) -> Path:
    """Build a fake repo checkout. ``skills`` maps skill -> {files: {name: content}}."""
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    for skill, spec in skills.items():
        d = repo / "scripts" / "openclaw" / "skills" / skill
        d.mkdir(parents=True)
        for name, content in spec.get("files", {}).items():
            (d / name).write_text(content, encoding="utf-8")
    return repo


def _point_dest(monkeypatch, tmp_path: Path) -> Path:
    """Redirect the deployed skills base into tmp and return it."""
    dest_base = tmp_path / "deployed" / "skills"
    monkeypatch.setattr(das, "SKILLS_DEST_BASE", dest_base)
    return dest_base


def _advance(**kw):
    base = dict(
        ok=True, advanced=False, pre_head="aaaaaaa", post_head="aaaaaaa",
        origin_head="aaaaaaa", behind=0, ahead=0, diverged=False, reason=None, stderr="",
    )
    base.update(kw)
    return AdvanceResult(**base)


@contextlib.contextmanager
def _fake_lock():
    yield


# ---------------------------------------------------------------------------
# compute_md5 / atomic_copy
# ---------------------------------------------------------------------------


def test_compute_md5_known(tmp_path):
    p = tmp_path / "f"
    p.write_bytes(b"hello")
    import hashlib
    assert das.compute_md5(p) == hashlib.md5(b"hello").hexdigest()


def test_compute_md5_large_chunked(tmp_path):
    p = tmp_path / "f"
    data = b"x" * (das.MD5_CHUNK_BYTES * 3 + 7)
    p.write_bytes(data)
    import hashlib
    assert das.compute_md5(p) == hashlib.md5(data).hexdigest()


def test_atomic_copy_new_dest(tmp_path):
    src = tmp_path / "s"; src.write_text("v1")
    dst = tmp_path / "d"
    das.atomic_copy(src, dst)
    assert dst.read_text() == "v1"
    # no temp left behind
    assert not list(tmp_path.glob("*.tmp.*"))


def test_atomic_copy_preserves_existing_mode(tmp_path):
    src = tmp_path / "s"; src.write_text("new")
    dst = tmp_path / "d"; dst.write_text("old"); os.chmod(dst, 0o600)
    das.atomic_copy(src, dst)
    assert dst.read_text() == "new"
    assert stat.S_IMODE(dst.stat().st_mode) == 0o600


def test_atomic_copy_raises_and_cleans_temp(tmp_path):
    src = tmp_path / "s"; src.write_text("x")
    dst = tmp_path / "sub" / "d"  # parent missing → open() raises
    with pytest.raises(OSError):
        das.atomic_copy(src, dst)
    assert not list((tmp_path).rglob("*.tmp.*"))


# ---------------------------------------------------------------------------
# is_backup
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,expected", [
    ("SKILL.md", False),
    ("SKILL.md.backup", True),
    ("SKILL.md.backup.2026-04-10", True),
    ("notes.txt", False),
])
def test_is_backup(name, expected):
    assert das.is_backup(name) is expected


# ---------------------------------------------------------------------------
# iter_skills / missing / multi-file
# ---------------------------------------------------------------------------


def test_iter_skills_derivation(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path, {
        "alpha": {"files": {"SKILL.md": "A"}},
        "beta": {"files": {"SKILL.md": "B"}},
    })
    dest_base = _point_dest(monkeypatch, tmp_path)
    units = list(das.iter_skills(repo))
    assert [u.skill for u in units] == ["alpha", "beta"]  # sorted
    assert units[0].source == repo / "scripts/openclaw/skills/alpha/SKILL.md"
    assert units[0].dest == dest_base / "alpha" / "SKILL.md"
    assert all(u.extra_files == () for u in units)


def test_iter_skills_missing_skillmd_is_skipped_and_reported(tmp_path):
    repo = _make_repo(tmp_path, {
        "good": {"files": {"SKILL.md": "G"}},
        "empty": {"files": {"README.md": "no skill here"}},
    })
    assert [u.skill for u in das.iter_skills(repo)] == ["good"]
    assert list(das.iter_skill_dirs_missing_skillmd(repo)) == ["empty"]


def test_iter_skills_multi_file_populates_extra(tmp_path):
    repo = _make_repo(tmp_path, {
        "multi": {"files": {"SKILL.md": "M", "helper.py": "code", "SKILL.md.backup": "old"}},
    })
    unit = next(das.iter_skills(repo))
    # backup ignored; only the real extra file is surfaced
    assert unit.extra_files == ("helper.py",)


def test_iter_skills_filter(tmp_path):
    repo = _make_repo(tmp_path, {
        "alpha": {"files": {"SKILL.md": "A"}},
        "beta": {"files": {"SKILL.md": "B"}},
    })
    assert [u.skill for u in das.iter_skills(repo, skill_filter="beta")] == ["beta"]


# ---------------------------------------------------------------------------
# sync_skill
# ---------------------------------------------------------------------------


def _unit(repo, dest_base, skill, extra=()):
    return das.SkillSyncUnit(
        skill=skill,
        source=repo / "scripts/openclaw/skills" / skill / "SKILL.md",
        dest=dest_base / skill / "SKILL.md",
        extra_files=tuple(extra),
    )


def test_sync_skill_no_drift_skips(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path, {"a": {"files": {"SKILL.md": "same"}}})
    dest_base = _point_dest(monkeypatch, tmp_path)
    unit = _unit(repo, dest_base, "a")
    unit.dest.parent.mkdir(parents=True)
    unit.dest.write_text("same")  # normalizing: real bytes on the dest side
    log = tmp_path / "audit.jsonl"
    counts = das.sync_skill(unit, log, "tick1", dry_run=False)
    assert counts.skipped == 1 and counts.copied == 0
    kinds = [json.loads(l)["kind"] for l in log.read_text().splitlines()]
    assert kinds == ["skip"]


def test_sync_skill_drift_copies_and_creates_parent(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path, {"a": {"files": {"SKILL.md": "new-content"}}})
    dest_base = _point_dest(monkeypatch, tmp_path)
    unit = _unit(repo, dest_base, "a")
    assert not unit.dest.parent.exists()  # FR-016: parent missing
    log = tmp_path / "audit.jsonl"
    counts = das.sync_skill(unit, log, "tick1", dry_run=False)
    assert counts.copied == 1
    assert unit.dest.read_text() == "new-content"  # parent created + copied
    rec = json.loads(log.read_text().splitlines()[-1])
    assert rec["kind"] == "copy" and rec["skill"] == "a"


def test_sync_skill_dry_run_writes_nothing(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path, {"a": {"files": {"SKILL.md": "new"}}})
    dest_base = _point_dest(monkeypatch, tmp_path)
    unit = _unit(repo, dest_base, "a")
    log = tmp_path / "audit.jsonl"
    sink: list[str] = []
    counts = das.sync_skill(unit, log, "tick1", dry_run=True, dry_run_sink=sink)
    assert counts.copied == 1
    assert not log.exists()  # no audit writes
    assert not unit.dest.exists()  # no file modification
    assert sink and sink[0].startswith("DRIFT a SKILL.md src_md5=")
    assert "dst_md5=absent" in sink[0]


def test_sync_skill_multi_file_warns(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path, {"a": {"files": {"SKILL.md": "x"}}})
    dest_base = _point_dest(monkeypatch, tmp_path)
    unit = _unit(repo, dest_base, "a", extra=("helper.py",))
    unit.dest.parent.mkdir(parents=True); unit.dest.write_text("x")
    log = tmp_path / "audit.jsonl"
    counts = das.sync_skill(unit, log, "tick1", dry_run=False)
    assert counts.warned == 1
    kinds = [json.loads(l)["kind"] for l in log.read_text().splitlines()]
    assert "warning" in kinds


def test_sync_skill_copy_error_records_error(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path, {"a": {"files": {"SKILL.md": "new"}}})
    dest_base = _point_dest(monkeypatch, tmp_path)
    unit = _unit(repo, dest_base, "a")
    log = tmp_path / "audit.jsonl"
    with patch.object(das, "atomic_copy", side_effect=OSError("disk full")):
        counts = das.sync_skill(unit, log, "tick1", dry_run=False)
    assert counts.errored == 1 and counts.copied == 0
    rec = json.loads(log.read_text().splitlines()[-1])
    assert rec["kind"] == "error" and rec["error_class"] == "OSError"


# ---------------------------------------------------------------------------
# git_pull mapping
# ---------------------------------------------------------------------------


def test_git_pull_success(tmp_path):
    adv = _advance(advanced=True, post_head="bbb", origin_head="bbb", behind=2)
    with patch.object(das, "advance_checkout", return_value=adv) as p:
        r = das.git_pull(tmp_path)
    assert p.call_args.kwargs.get("assume_locked") is True
    assert r.success and r.head_sha == "bbb" and r.stage is None


def test_git_pull_diverged_fails(tmp_path):
    adv = _advance(ok=False, diverged=True, reason="diverged")
    with patch.object(das, "advance_checkout", return_value=adv):
        r = das.git_pull(tmp_path)
    assert not r.success and r.stage == "diverged"


# ---------------------------------------------------------------------------
# _validate
# ---------------------------------------------------------------------------


def test_validate_missing_git(tmp_path):
    (tmp_path / "scripts/openclaw/skills").mkdir(parents=True)
    assert "no .git" in das._validate(tmp_path, None)


def test_validate_missing_skills_dir(tmp_path):
    (tmp_path / ".git").mkdir()
    assert "skills source dir not found" in das._validate(tmp_path, None)


def test_validate_unknown_skill(tmp_path):
    repo = _make_repo(tmp_path, {"a": {"files": {"SKILL.md": "x"}}})
    assert "unknown skill: zzz" in das._validate(repo, "zzz")
    assert das._validate(repo, "a") is None


# ---------------------------------------------------------------------------
# run_tick (integration)
# ---------------------------------------------------------------------------


def _fake_result(ok=True):
    return AlertResult(ok=ok)


def test_run_tick_dry_run_prints_and_no_writes(tmp_path, monkeypatch, capsys):
    repo = _make_repo(tmp_path, {"a": {"files": {"SKILL.md": "new"}}})
    _point_dest(monkeypatch, tmp_path)
    audit = tmp_path / "deploy" / "audit.jsonl"
    args = das.parse_args(["--dry-run"])
    rc = das.run_tick(args, repo_root=repo, audit_path=audit)
    assert rc == das.EXIT_SUCCESS
    out = capsys.readouterr().out
    assert "DRIFT a SKILL.md" in out
    assert not audit.exists()  # dry-run writes nothing
    assert not (audit.parent / das.LAST_TICK_FILENAME).exists()


def test_run_tick_real_converges_and_writes_freshness(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path, {"a": {"files": {"SKILL.md": "fresh"}}})
    dest_base = _point_dest(monkeypatch, tmp_path)
    audit = tmp_path / "deploy" / "audit.jsonl"
    health = tmp_path / "deploy" / "git-health.json"
    monkeypatch.setattr(das, "advance_checkout", lambda *a, **k: _advance(behind=0))
    monkeypatch.setattr(das, "deploylock", _fake_lock)
    monkeypatch.setattr(das, "emit", lambda alert: _fake_result(ok=True))
    args = das.parse_args([])
    rc = das.run_tick(args, repo_root=repo, audit_path=audit, health_state_path=health)
    assert rc == das.EXIT_SUCCESS
    assert (dest_base / "a" / "SKILL.md").read_text() == "fresh"
    # freshness pointer written, exit_code 0
    lt = json.loads((audit.parent / das.LAST_TICK_FILENAME).read_text())
    assert lt["exit_code"] == 0 and lt["status"] == "success" and "completed_at_utc" in lt
    kinds = [json.loads(l)["kind"] for l in audit.read_text().splitlines()]
    assert "copy" in kinds and "tick_summary" in kinds


def test_run_tick_idempotent_noop(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path, {"a": {"files": {"SKILL.md": "same"}}})
    dest_base = _point_dest(monkeypatch, tmp_path)
    (dest_base / "a").mkdir(parents=True); (dest_base / "a" / "SKILL.md").write_text("same")
    audit = tmp_path / "deploy" / "audit.jsonl"
    monkeypatch.setattr(das, "advance_checkout", lambda *a, **k: _advance(behind=0))
    monkeypatch.setattr(das, "deploylock", _fake_lock)
    monkeypatch.setattr(das, "emit", lambda alert: _fake_result(ok=True))
    rc = das.run_tick(das.parse_args([]), repo_root=repo, audit_path=audit,
                      health_state_path=tmp_path / "h.json")
    assert rc == das.EXIT_SUCCESS
    kinds = [json.loads(l)["kind"] for l in audit.read_text().splitlines()]
    assert "copy" not in kinds and "skip" in kinds  # 0 writes to dest


def test_run_tick_lock_unavailable_defers(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path, {"a": {"files": {"SKILL.md": "x"}}})
    _point_dest(monkeypatch, tmp_path)
    audit = tmp_path / "deploy" / "audit.jsonl"

    @contextlib.contextmanager
    def _boom():
        raise LockUnavailable("held")
        yield  # pragma: no cover

    monkeypatch.setattr(das, "deploylock", _boom)
    rc = das.run_tick(das.parse_args([]), repo_root=repo, audit_path=audit,
                      health_state_path=tmp_path / "h.json")
    assert rc == das.EXIT_SUCCESS
    kinds = [json.loads(l)["kind"] for l in audit.read_text().splitlines()]
    assert kinds == ["git_pull_skipped"]
    lt = json.loads((audit.parent / das.LAST_TICK_FILENAME).read_text())
    assert lt["status"] == "deferred" and lt["exit_code"] == 0


def test_run_tick_git_advance_failed(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path, {"a": {"files": {"SKILL.md": "x"}}})
    _point_dest(monkeypatch, tmp_path)
    audit = tmp_path / "deploy" / "audit.jsonl"
    monkeypatch.setattr(das, "advance_checkout",
                        lambda *a, **k: _advance(ok=False, reason="fetch_failed", stderr="no net"))
    monkeypatch.setattr(das, "deploylock", _fake_lock)
    monkeypatch.setattr(das, "emit", lambda alert: _fake_result(ok=True))
    rc = das.run_tick(das.parse_args([]), repo_root=repo, audit_path=audit,
                      health_state_path=tmp_path / "h.json")
    assert rc == das.EXIT_GIT_PULL_FAILED
    kinds = [json.loads(l)["kind"] for l in audit.read_text().splitlines()]
    assert "git_pull_failed" in kinds


def test_run_tick_copy_failure_returns_partial(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path, {"a": {"files": {"SKILL.md": "new"}}})
    _point_dest(monkeypatch, tmp_path)
    audit = tmp_path / "deploy" / "audit.jsonl"
    monkeypatch.setattr(das, "advance_checkout", lambda *a, **k: _advance(behind=0))
    monkeypatch.setattr(das, "deploylock", _fake_lock)
    monkeypatch.setattr(das, "emit", lambda alert: _fake_result(ok=True))
    monkeypatch.setattr(das, "atomic_copy", lambda s, d: (_ for _ in ()).throw(OSError("boom")))
    rc = das.run_tick(das.parse_args([]), repo_root=repo, audit_path=audit,
                      health_state_path=tmp_path / "h.json")
    assert rc == das.EXIT_PARTIAL_FAILURE


def test_run_tick_validation_error_returns_3(tmp_path):
    # repo with no skills dir → exit 3
    repo = tmp_path / "repo"; (repo / ".git").mkdir(parents=True)
    rc = das.run_tick(das.parse_args([]), repo_root=repo, audit_path=tmp_path / "a.jsonl")
    assert rc == das.EXIT_VALIDATION_ERROR


# ---------------------------------------------------------------------------
# health notifier + freshness shape
# ---------------------------------------------------------------------------


def test_health_notifier_returns_emit_ok(monkeypatch):
    captured = {}
    def _fake_emit(alert):
        captured["alert"] = alert
        return _fake_result(ok=True)
    monkeypatch.setattr(das, "emit", _fake_emit)
    assert das._health_notifier("t", "b") is True
    assert captured["alert"].source == das.HEALTH_ACTOR
    assert captured["alert"].title == "t" and captured["alert"].description == "b"


def test_health_notifier_undelivered_returns_false(monkeypatch):
    monkeypatch.setattr(das, "emit", lambda alert: _fake_result(ok=False))
    assert das._health_notifier("t", "b") is False


def test_write_last_tick_shape(tmp_path):
    das.write_last_tick(tmp_path, status="success")
    payload = json.loads((tmp_path / das.LAST_TICK_FILENAME).read_text())
    assert payload["exit_code"] == 0
    assert payload["status"] == "success"
    assert payload["completed_at_utc"].endswith("Z")


# ---------------------------------------------------------------------------
# Copy-failure → alert wiring (the mission's core anti-silent-drift guarantee).
# renata review M1/M2/L3/L4: the copy-failure watermark uses a NON-default
# confirmed_reasons; if that wiring regressed, a persistent copy failure would
# silently never alert (the #563 class #775 exists to prevent). Pin it.
# ---------------------------------------------------------------------------


def _run_one_tick(repo, audit, health, monkeypatch, *, copy_raises=False):
    monkeypatch.setattr(das, "advance_checkout", lambda *a, **k: _advance(behind=0))
    monkeypatch.setattr(das, "deploylock", _fake_lock)
    if copy_raises:
        monkeypatch.setattr(
            das, "atomic_copy", lambda s, d: (_ for _ in ()).throw(OSError("boom"))
        )
    return das.run_tick(das.parse_args([]), repo_root=repo, audit_path=audit,
                        health_state_path=health)


def test_copy_failure_streak_fires_exactly_one_alert(tmp_path, monkeypatch):
    """DEFAULT_THRESHOLD consecutive copy-failure ticks → exactly one alert whose
    title comes from _copy_render (proves confirmed_reasons + render are wired)."""
    from scripts.deploy.lib.health import DEFAULT_THRESHOLD
    repo = _make_repo(tmp_path, {"a": {"files": {"SKILL.md": "new"}}})
    _point_dest(monkeypatch, tmp_path)
    audit = tmp_path / "deploy" / "audit.jsonl"
    health = tmp_path / "deploy" / "git-health.json"

    alerts: list = []
    monkeypatch.setattr(das, "emit", lambda alert: (alerts.append(alert) or _fake_result(ok=True)))

    for _ in range(DEFAULT_THRESHOLD):
        rc = _run_one_tick(repo, audit, health, monkeypatch, copy_raises=True)
        assert rc == das.EXIT_PARTIAL_FAILURE

    # Exactly one alert, from the COPY watermark (title via _copy_render).
    assert len(alerts) == 1
    assert "skill-copy failing" in alerts[0].title


def test_copy_watermark_uses_copy_confirmed_reasons(tmp_path, monkeypatch):
    """Guard the load-bearing kwargs: the copy watermark must pass
    confirmed_reasons=COPY_CONFIRMED_REASONS and render=_copy_render."""
    repo = _make_repo(tmp_path, {"a": {"files": {"SKILL.md": "new"}}})
    _point_dest(monkeypatch, tmp_path)
    calls: list = []
    real_record = das._health.record

    def _spy(actor, result, **kw):
        calls.append((actor, kw))
        return real_record(actor, result, **kw)

    monkeypatch.setattr(das._health, "record", _spy)
    monkeypatch.setattr(das, "emit", lambda alert: _fake_result(ok=True))
    _run_one_tick(repo, tmp_path / "a.jsonl", tmp_path / "h.json", monkeypatch, copy_raises=True)

    copy_calls = [kw for actor, kw in calls if actor == das.COPY_HEALTH_ACTOR]
    assert copy_calls, "copy-health watermark was never recorded"
    assert copy_calls[0]["confirmed_reasons"] == das.COPY_CONFIRMED_REASONS
    assert copy_calls[0]["render"] is das._copy_render


def test_copy_only_preserves_dest_orphan(tmp_path, monkeypatch):
    """FR-004: a deployed skill with no repo counterpart is never pruned."""
    repo = _make_repo(tmp_path, {"a": {"files": {"SKILL.md": "x"}}})
    dest_base = _point_dest(monkeypatch, tmp_path)
    # an orphan deployed skill with no repo dir
    (dest_base / "gone").mkdir(parents=True)
    (dest_base / "gone" / "SKILL.md").write_text("orphaned")
    (dest_base / "a").mkdir(parents=True); (dest_base / "a" / "SKILL.md").write_text("x")
    monkeypatch.setattr(das, "emit", lambda alert: _fake_result(ok=True))
    _run_one_tick(repo, tmp_path / "a.jsonl", tmp_path / "h.json", monkeypatch)
    assert (dest_base / "gone" / "SKILL.md").read_text() == "orphaned"  # survived


def test_copy_failure_writes_error_audit_and_partial_status(tmp_path, monkeypatch):
    """L4: a copy failure records an `error` audit AND status=partial in the freshness pointer."""
    repo = _make_repo(tmp_path, {"a": {"files": {"SKILL.md": "new"}}})
    _point_dest(monkeypatch, tmp_path)
    audit = tmp_path / "deploy" / "audit.jsonl"
    monkeypatch.setattr(das, "emit", lambda alert: _fake_result(ok=True))
    rc = _run_one_tick(repo, audit, tmp_path / "h.json", monkeypatch, copy_raises=True)
    assert rc == das.EXIT_PARTIAL_FAILURE
    kinds = [json.loads(l)["kind"] for l in audit.read_text().splitlines()]
    assert "error" in kinds
    lt = json.loads((audit.parent / das.LAST_TICK_FILENAME).read_text())
    assert lt["status"] == "partial" and lt["exit_code"] == 0


def test_smoke_does_real_copy_without_lock_or_git_advance(tmp_path, monkeypatch):
    """--smoke (deploy-time gate, Codex #2 HIGH-1): real copies, NO deploylock, NO
    git advance; writes status='smoke' so the deploy script proves a real sync ran."""
    repo = _make_repo(tmp_path, {"a": {"files": {"SKILL.md": "fresh"}}})
    dest_base = _point_dest(monkeypatch, tmp_path)
    audit = tmp_path / "deploy" / "audit.jsonl"

    # Fail loudly if smoke touches the lock or the git advance.
    def _boom_lock():
        raise AssertionError("smoke must NOT acquire the deploylock")
    monkeypatch.setattr(das, "deploylock", _boom_lock)
    monkeypatch.setattr(das, "advance_checkout",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("smoke must NOT git-advance")))
    monkeypatch.setattr(das, "emit", lambda alert: _fake_result(ok=True))

    rc = das.run_tick(das.parse_args(["--smoke"]), repo_root=repo, audit_path=audit,
                      health_state_path=tmp_path / "h.json")
    assert rc == das.EXIT_SUCCESS
    assert (dest_base / "a" / "SKILL.md").read_text() == "fresh"  # real copy happened
    lt = json.loads((audit.parent / das.LAST_TICK_FILENAME).read_text())
    assert lt["status"] == "smoke"  # never 'deferred'
    kinds = [json.loads(l)["kind"] for l in audit.read_text().splitlines()]
    assert "copy" in kinds and "tick_summary" in kinds


def test_smoke_copy_failure_sets_smoke_partial(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path, {"a": {"files": {"SKILL.md": "x"}}})
    _point_dest(monkeypatch, tmp_path)
    audit = tmp_path / "deploy" / "audit.jsonl"
    monkeypatch.setattr(das, "atomic_copy", lambda s, d: (_ for _ in ()).throw(OSError("boom")))
    monkeypatch.setattr(das, "emit", lambda alert: _fake_result(ok=True))
    rc = das.run_tick(das.parse_args(["--smoke"]), repo_root=repo, audit_path=audit,
                      health_state_path=tmp_path / "h.json")
    assert rc == das.EXIT_PARTIAL_FAILURE
    lt = json.loads((audit.parent / das.LAST_TICK_FILENAME).read_text())
    assert lt["status"] == "smoke_partial"


def test_git_pull_failed_audit_has_exit_code(tmp_path, monkeypatch):
    """L1: parity with the reference — the git_pull_failed audit carries git_exit_code."""
    repo = _make_repo(tmp_path, {"a": {"files": {"SKILL.md": "x"}}})
    _point_dest(monkeypatch, tmp_path)
    audit = tmp_path / "deploy" / "audit.jsonl"
    monkeypatch.setattr(das, "advance_checkout",
                        lambda *a, **k: _advance(ok=False, reason="fetch_failed", stderr="x"))
    monkeypatch.setattr(das, "deploylock", _fake_lock)
    monkeypatch.setattr(das, "emit", lambda alert: _fake_result(ok=True))
    das.run_tick(das.parse_args([]), repo_root=repo, audit_path=audit,
                 health_state_path=tmp_path / "h.json")
    rec = [json.loads(l) for l in audit.read_text().splitlines() if json.loads(l)["kind"] == "git_pull_failed"][0]
    assert rec["git_exit_code"] == 1

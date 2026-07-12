"""Tests for scripts/deploy/deploy-habits-weekly-driver.py + its manifest (#723 WP04).

Covers T013/T014:
  * cron-id resolution parsing (via scripts.deploy.lib.cron, mocked);
  * the C2 self-test gate: aborts on failure/no-fresh-tick, passes on a clean run;
  * C3 transactional cutover ORDER: units -> self-test -> enable timer ->
    retire legacy cron -> exactly-one-producer postcheck (enable-before-retire,
    post-merge Codex review #723 — fails toward ONE producer, never zero);
  * failure semantics: an enable failure leaves the legacy cron intact (one
    producer, no outage); a retire failure after a successful enable leaves
    BOTH producers active (a recoverable duplicate, not a silent miss);
  * the C3 postcheck itself: FAILS when both producers are present, FAILS when
    neither is present, passes only on exactly-one-producer;
  * legacy-cron removal is idempotent (already-absent = success);
  * manifest schema validity (tier 3, audited_surface, expected_baselines,
    NOT pre-numbered);
  * the entrypoint is executable (felix-deployer runs it directly).

All subprocess / systemctl / openclaw effects are mocked — NO real systemd, NO
office2 access. The entrypoint file is hyphenated
(deploy-habits-weekly-driver.py), which is not importable via dotted form; it
is loaded with importlib, matching the sibling test_deploy_felix_canary.py
pattern.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_ENTRYPOINT_PATH = _REPO_ROOT / "scripts" / "deploy" / "deploy-habits-weekly-driver.py"
_MANIFEST_QUEUED = _REPO_ROOT / "deploys" / "queued" / "habits-weekly-driver.yaml"


def _load_entrypoint():
    """Load the hyphenated-named entrypoint module via importlib."""
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    spec = importlib.util.spec_from_file_location(
        "deploy_habits_weekly_driver",
        _ENTRYPOINT_PATH,
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_entrypoint()


def _resolve_manifest_path() -> pathlib.Path:
    """Locate the manifest — queued pre-deploy, applied (any numbering) post-deploy."""
    if _MANIFEST_QUEUED.exists():
        return _MANIFEST_QUEUED
    applied = sorted(
        (_REPO_ROOT / "deploys" / "applied").glob("*-habits-weekly-driver.yaml")
    )
    if applied:
        return applied[-1]
    return _MANIFEST_QUEUED


# ---------------------------------------------------------------------------
# Fakes: a scripted _run recorder + a fake cron_lib.openclaw_cron_list.
# ---------------------------------------------------------------------------


class _RunRecorder:
    """Callable that records each _run invocation and returns scripted results.

    ``responses`` maps a match-substring (found in the argv) to a
    ``(returncode, stdout, stderr)`` tuple. The first matching key wins; an
    unmatched call defaults to success ``(0, "", "")``. ``calls`` preserves the
    invocation order for ordering assertions.
    """

    def __init__(self, responses: dict[str, tuple[int, str, str]] | None = None):
        self.calls: list[list[str]] = []
        self._responses = responses or {}

    def __call__(self, argv, cwd=None):
        self.calls.append(list(argv))
        joined = " ".join(argv)
        for needle, resp in self._responses.items():
            if needle in joined:
                return resp
        return (0, "", "")


class _FakeLibResult:
    def __init__(self, ok: bool, details: dict):
        self.ok = ok
        self.details = details


def _fake_cron_list(jobs: list[dict]):
    def _list():
        return _FakeLibResult(ok=True, details={"crons": jobs})

    return _list


def _install_fake_units(monkeypatch, tmp_path) -> pathlib.Path:
    systemd_dir = tmp_path / "systemd-user"
    monkeypatch.setattr(_mod, "_SYSTEMD_USER_DIR", systemd_dir)
    return systemd_dir


def _patch_tick(monkeypatch, tmp_path):
    """Patch the SELF-TEST tick path the C2 gate asserts against.

    Renamed from ``_TICK_PATH`` (production last-tick.json) to
    ``_SELF_TEST_TICK_PATH`` (post-merge Codex review, #723): the deploy
    gate must assert freshness of the self-test-scoped tick, never the
    production one.
    """
    tick_path = tmp_path / "state" / "self-test-last-tick.json"
    monkeypatch.setattr(_mod, "_SELF_TEST_TICK_PATH", tick_path)
    return tick_path


def _patch_deploy_user_ok(monkeypatch, home: pathlib.Path | None = None) -> pathlib.Path:
    """Make the Step-0 deploy-user preflight pass regardless of the local
    test-running account, by pointing `_EXPECTED_DEPLOY_HOME` at whatever
    `Path.home()` actually is in this environment (or an explicit `home`).

    Every test that drives `main(["--apply"])` end-to-end must call this
    (post-merge Codex review, #723 — the guard is real and must not be
    accidentally satisfied/unsatisfied by the CI account's home directory).
    """
    expected = home if home is not None else pathlib.Path.home()
    monkeypatch.setattr(_mod, "_EXPECTED_DEPLOY_HOME", expected)
    return expected


def _write_fresh_tick(tick_path: pathlib.Path, ts: str = "2026-07-12T06:00:00+00:00") -> None:
    tick_path.parent.mkdir(parents=True, exist_ok=True)
    tick_path.write_text(json.dumps({"completed_at_utc": ts}), encoding="utf-8")


# ---------------------------------------------------------------------------
# Usage / dry-run.
# ---------------------------------------------------------------------------


def test_usage_error_on_no_mode():
    assert _mod.main([]) == 2


def test_usage_error_on_bad_mode():
    assert _mod.main(["--frobnicate"]) == 2


def test_dry_run_mutates_nothing(monkeypatch):
    """--dry-run must not call _run or emit; exit 0."""
    run = _RunRecorder()
    monkeypatch.setattr(_mod, "_run", run)
    emitted = {"called": False}

    def _no_emit(*a, **k):
        emitted["called"] = True

    monkeypatch.setattr(_mod, "emit", _no_emit)
    assert _mod.main(["--dry-run"]) == 0
    assert run.calls == [], "dry-run must not invoke any subprocess"
    assert not emitted["called"], "dry-run must not emit"


# ---------------------------------------------------------------------------
# Cron-id resolution (via scripts.deploy.lib.cron, mocked).
# ---------------------------------------------------------------------------


def test_resolve_cron_id_finds_matching_job(monkeypatch):
    monkeypatch.setattr(
        _mod.cron_lib,
        "openclaw_cron_list",
        _fake_cron_list([{"name": "habits-weekly-report", "id": "abc-123"}]),
    )
    cron_id, info = _mod._resolve_cron_id("habits-weekly-report")
    assert cron_id == "abc-123"


def test_resolve_cron_id_returns_none_when_absent(monkeypatch):
    monkeypatch.setattr(
        _mod.cron_lib,
        "openclaw_cron_list",
        _fake_cron_list([{"name": "habits-morning-checkin", "id": "xyz"}]),
    )
    cron_id, info = _mod._resolve_cron_id("habits-weekly-report")
    assert cron_id is None
    assert "not registered" in info["error"]


def test_resolve_cron_id_handles_list_failure(monkeypatch):
    monkeypatch.setattr(
        _mod.cron_lib,
        "openclaw_cron_list",
        lambda: _FakeLibResult(ok=False, details={"stderr_excerpt": "boom"}),
    )
    cron_id, info = _mod._resolve_cron_id("habits-weekly-report")
    assert cron_id is None
    assert "openclaw cron list failed" in info["error"]


# ---------------------------------------------------------------------------
# Legacy-cron removal: idempotent + failure handling.
# ---------------------------------------------------------------------------


def test_retire_legacy_cron_removes_and_confirms_absence(monkeypatch, tmp_path):
    """Happy path: cron found, `rm` succeeds, post-rm lookup shows absence."""
    calls = {"list_call": 0}

    def _list():
        calls["list_call"] += 1
        if calls["list_call"] == 1:
            return _FakeLibResult(
                ok=True, details={"crons": [{"name": "habits-weekly-report", "id": "abc-123"}]}
            )
        return _FakeLibResult(ok=True, details={"crons": []})

    monkeypatch.setattr(_mod.cron_lib, "openclaw_cron_list", _list)

    run = _RunRecorder()
    monkeypatch.setattr(_mod, "_run", run)

    ok, details = _mod._step_retire_legacy_cron()
    assert ok is True
    assert details["cron_id"] == "abc-123"
    assert run.calls == [[_mod._OPENCLAW_BIN, "cron", "rm", "abc-123"]]


def test_retire_legacy_cron_idempotent_when_already_absent(monkeypatch):
    """Already-absent cron is treated as success (a prior partial apply may
    have already removed it)."""
    monkeypatch.setattr(_mod.cron_lib, "openclaw_cron_list", _fake_cron_list([]))
    run = _RunRecorder()
    monkeypatch.setattr(_mod, "_run", run)

    ok, details = _mod._step_retire_legacy_cron()
    assert ok is True
    assert details.get("idempotent") is True
    assert run.calls == [], "rm must not be invoked when the cron is already absent"


def test_retire_legacy_cron_fails_when_rm_exits_nonzero(monkeypatch):
    monkeypatch.setattr(
        _mod.cron_lib,
        "openclaw_cron_list",
        _fake_cron_list([{"name": "habits-weekly-report", "id": "abc-123"}]),
    )

    def _run(argv, cwd=None):
        return (1, "", "permission denied")

    monkeypatch.setattr(_mod, "_run", _run)
    ok, details = _mod._step_retire_legacy_cron()
    assert ok is False
    assert "rm failed" in details["error"]


def test_retire_legacy_cron_fails_when_still_present_after_rm(monkeypatch):
    """`rm` exits 0 but a post-rm lookup still finds it — must be flagged."""
    monkeypatch.setattr(
        _mod.cron_lib,
        "openclaw_cron_list",
        _fake_cron_list([{"name": "habits-weekly-report", "id": "abc-123"}]),
    )

    def _run(argv, cwd=None):
        return (0, "", "")

    monkeypatch.setattr(_mod, "_run", _run)
    ok, details = _mod._step_retire_legacy_cron()
    assert ok is False
    assert "still present after rm" in details["error"]


# ---------------------------------------------------------------------------
# C2 self-test gate.
# ---------------------------------------------------------------------------


def test_self_test_passes_on_clean_run(monkeypatch, tmp_path):
    tick_path = _patch_tick(monkeypatch, tmp_path)

    def _run(argv, cwd=None):
        _write_fresh_tick(tick_path)
        return (0, "self-test OK\n", "")

    monkeypatch.setattr(_mod, "_run", _run)
    ok, details = _mod._step_self_test()
    assert ok is True
    assert details["tick_after"] is not None


def test_self_test_fails_on_nonzero_exit(monkeypatch, tmp_path):
    _patch_tick(monkeypatch, tmp_path)

    def _run(argv, cwd=None):
        return (1, "", "helper failed")

    monkeypatch.setattr(_mod, "_run", _run)
    ok, details = _mod._step_self_test()
    assert ok is False
    assert "non-zero" in details["error"]


def test_self_test_fails_when_no_tick_written(monkeypatch, tmp_path):
    _patch_tick(monkeypatch, tmp_path)

    def _run(argv, cwd=None):
        return (0, "", "")  # "succeeded" but wrote nothing

    monkeypatch.setattr(_mod, "_run", _run)
    ok, details = _mod._step_self_test()
    assert ok is False
    assert "absent" in details["error"]


def test_self_test_fails_on_stale_tick(monkeypatch, tmp_path):
    """A pre-existing tick that the self-test does NOT advance fails the gate."""
    tick_path = _patch_tick(monkeypatch, tmp_path)
    _write_fresh_tick(tick_path, ts="2026-07-01T00:00:00+00:00")

    def _run(argv, cwd=None):
        return (0, "", "")  # "ran" but did not rewrite the tick

    monkeypatch.setattr(_mod, "_run", _run)
    ok, details = _mod._step_self_test()
    assert ok is False
    assert "did not advance" in details["error"]


# ---------------------------------------------------------------------------
# C3 exactly-one-producer postcheck.
# ---------------------------------------------------------------------------


def test_postcheck_passes_when_cron_absent_and_timer_enabled(monkeypatch):
    monkeypatch.setattr(_mod.cron_lib, "openclaw_cron_list", _fake_cron_list([]))

    def _run(argv, cwd=None):
        if "is-enabled" in " ".join(argv):
            return (0, "enabled\n", "")
        return (0, "", "")

    monkeypatch.setattr(_mod, "_run", _run)
    ok, details = _mod._step_exactly_one_producer_postcheck()
    assert ok is True


def test_postcheck_fails_when_both_producers_present(monkeypatch):
    monkeypatch.setattr(
        _mod.cron_lib,
        "openclaw_cron_list",
        _fake_cron_list([{"name": "habits-weekly-report", "id": "abc"}]),
    )

    def _run(argv, cwd=None):
        if "is-enabled" in " ".join(argv):
            return (0, "enabled\n", "")
        return (0, "", "")

    monkeypatch.setattr(_mod, "_run", _run)
    ok, details = _mod._step_exactly_one_producer_postcheck()
    assert ok is False
    assert "BOTH producers" in details["error"]


def test_postcheck_fails_when_neither_producer_present(monkeypatch):
    monkeypatch.setattr(_mod.cron_lib, "openclaw_cron_list", _fake_cron_list([]))

    def _run(argv, cwd=None):
        if "is-enabled" in " ".join(argv):
            return (1, "disabled\n", "")
        return (0, "", "")

    monkeypatch.setattr(_mod, "_run", _run)
    ok, details = _mod._step_exactly_one_producer_postcheck()
    assert ok is False
    assert "NEITHER producer" in details["error"]


def test_postcheck_fails_when_cron_present_but_timer_not_enabled(monkeypatch):
    monkeypatch.setattr(
        _mod.cron_lib,
        "openclaw_cron_list",
        _fake_cron_list([{"name": "habits-weekly-report", "id": "abc"}]),
    )

    def _run(argv, cwd=None):
        if "is-enabled" in " ".join(argv):
            return (1, "disabled\n", "")
        return (0, "", "")

    monkeypatch.setattr(_mod, "_run", _run)
    ok, details = _mod._step_exactly_one_producer_postcheck()
    assert ok is False
    assert "cutover incomplete" in details["error"]


# ---------------------------------------------------------------------------
# Step 0 — deploy-user preflight guard (post-merge Codex review, #723).
# ---------------------------------------------------------------------------


def test_step_assert_deploy_user_passes_when_home_matches(monkeypatch, tmp_path):
    monkeypatch.setattr(_mod, "_EXPECTED_DEPLOY_HOME", tmp_path)
    monkeypatch.setattr(_mod.Path, "home", classmethod(lambda cls: tmp_path))
    ok, details = _mod._step_assert_deploy_user()
    assert ok is True
    assert details["actual_home"] == str(tmp_path)


def test_step_assert_deploy_user_fails_when_home_mismatches(monkeypatch, tmp_path):
    other = tmp_path / "not-claude"
    monkeypatch.setattr(_mod, "_EXPECTED_DEPLOY_HOME", tmp_path / "claude-home")
    monkeypatch.setattr(_mod.Path, "home", classmethod(lambda cls: other))
    ok, details = _mod._step_assert_deploy_user()
    assert ok is False
    assert "unexpected deploy user" in details["error"]


def test_apply_aborts_before_any_mutation_when_deploy_user_wrong(monkeypatch, tmp_path):
    """--apply must halt at the Step-0 preflight, before install/self-test/
    cutover, when running under the wrong account."""
    other = tmp_path / "not-claude"
    other.mkdir()
    monkeypatch.setattr(_mod, "_EXPECTED_DEPLOY_HOME", tmp_path / "claude-home")
    monkeypatch.setattr(_mod.Path, "home", classmethod(lambda cls: other))

    run = _RunRecorder()
    monkeypatch.setattr(_mod, "_run", run)
    emitted = {"called": False}

    def _capture_emit(*a, **k):
        emitted["called"] = True

    monkeypatch.setattr(_mod, "emit", _capture_emit)

    assert _mod.main(["--apply"]) == 1
    assert run.calls == [], "no subprocess step may run when the deploy-user guard fails"
    assert emitted["called"] is True


def test_dry_run_not_blocked_by_deploy_user_guard(monkeypatch, tmp_path):
    """--dry-run must NOT be blocked by the deploy-user guard — it is only
    enforced for --apply (per the FIX-4 allowance for local testing)."""
    other = tmp_path / "not-claude"
    monkeypatch.setattr(_mod, "_EXPECTED_DEPLOY_HOME", tmp_path / "claude-home")
    monkeypatch.setattr(_mod.Path, "home", classmethod(lambda cls: other))

    run = _RunRecorder()
    monkeypatch.setattr(_mod, "_run", run)
    monkeypatch.setattr(_mod, "emit", lambda *a, **k: None)

    assert _mod.main(["--dry-run"]) == 0
    assert run.calls == []


# ---------------------------------------------------------------------------
# Full --apply order + halt-on-failure behavior.
# ---------------------------------------------------------------------------


def test_apply_happy_path_order_and_success(monkeypatch, tmp_path):
    """install -> daemon-reload -> self-test -> enable timer -> retire cron ->
    postcheck, in that order (post-merge Codex review #723: enable-before-
    retire so a failure never drops to zero active producers)."""
    _patch_deploy_user_ok(monkeypatch)
    systemd_dir = _install_fake_units(monkeypatch, tmp_path)
    tick_path = _patch_tick(monkeypatch, tmp_path)

    # Unit source files must exist for the real _step_install_units to copy.
    for name in _mod._UNIT_NAMES:
        src = _mod._UNIT_SOURCE_DIR / name
        assert src.exists(), f"fixture assumption: {src} must exist in the repo"

    calls = {"list_call": 0}

    def _list():
        calls["list_call"] += 1
        if calls["list_call"] == 1:
            return _FakeLibResult(
                ok=True, details={"crons": [{"name": "habits-weekly-report", "id": "abc-123"}]}
            )
        return _FakeLibResult(ok=True, details={"crons": []})

    monkeypatch.setattr(_mod.cron_lib, "openclaw_cron_list", _list)

    run = _RunRecorder()

    def _tracked_run(argv, cwd=None):
        run.calls.append(list(argv))
        joined = " ".join(argv)
        if "weekly_report_driver" in joined:
            _write_fresh_tick(tick_path)
            return (0, "self-test OK\n", "")
        if "list-timers" in joined:
            return (0, "felix-habits-weekly.timer  next elapse\n", "")
        if "is-enabled" in joined:
            return (0, "enabled\n", "")
        return (0, "", "")

    monkeypatch.setattr(_mod, "_run", _tracked_run)
    monkeypatch.setattr(_mod, "emit", lambda *a, **k: None)

    assert _mod.main(["--apply"]) == 0

    joined = [" ".join(c) for c in run.calls]
    reload_idx = next(i for i, c in enumerate(joined) if "daemon-reload" in c)
    selftest_idx = next(i for i, c in enumerate(joined) if "weekly_report_driver" in c)
    enable_idx = next(
        i for i, c in enumerate(joined) if "enable" in c and "felix-habits-weekly.timer" in c
    )
    rm_idx = next(i for i, c in enumerate(joined) if "cron rm" in c)
    assert reload_idx < selftest_idx < enable_idx < rm_idx

    for name in _mod._UNIT_NAMES:
        assert (systemd_dir / name).exists()


def test_apply_halts_before_cutover_when_self_test_fails(monkeypatch, tmp_path):
    """A failing self-test must abort BEFORE either producer is touched (C2):
    no timer enable, no legacy cron removal."""
    _patch_deploy_user_ok(monkeypatch)
    _install_fake_units(monkeypatch, tmp_path)
    _patch_tick(monkeypatch, tmp_path)

    run = _RunRecorder()

    def _tracked_run(argv, cwd=None):
        run.calls.append(list(argv))
        if "weekly_report_driver" in " ".join(argv):
            return (1, "", "helper failed")
        return (0, "", "")

    monkeypatch.setattr(_mod, "_run", _tracked_run)
    monkeypatch.setattr(_mod, "emit", lambda *a, **k: None)

    def _list():
        raise AssertionError("openclaw_cron_list must not be called when the self-test fails")

    monkeypatch.setattr(_mod.cron_lib, "openclaw_cron_list", _list)

    assert _mod.main(["--apply"]) == 1
    joined = [" ".join(c) for c in run.calls]
    assert not any("enable" in c and "felix-habits-weekly.timer" in c for c in joined)
    assert not any("cron" in c and "rm" in c for c in joined)


def test_apply_enable_failure_leaves_legacy_cron_untouched(monkeypatch, tmp_path):
    """Enable-timer failure (post-self-test) must NOT touch the legacy cron —
    the cutover fails toward ONE producer (the still-active legacy cron),
    never zero (post-merge Codex review, #723)."""
    _patch_deploy_user_ok(monkeypatch)
    _install_fake_units(monkeypatch, tmp_path)
    tick_path = _patch_tick(monkeypatch, tmp_path)

    def _list():
        raise AssertionError(
            "openclaw_cron_list (cron resolution/removal) must not be called "
            "when the timer enable step fails"
        )

    monkeypatch.setattr(_mod.cron_lib, "openclaw_cron_list", _list)

    def _run(argv, cwd=None):
        joined = " ".join(argv)
        if "weekly_report_driver" in joined:
            _write_fresh_tick(tick_path)
            return (0, "self-test OK\n", "")
        if "enable" in joined and "felix-habits-weekly.timer" in joined:
            return (1, "", "unit not found")
        return (0, "", "")

    monkeypatch.setattr(_mod, "_run", _run)
    monkeypatch.setattr(_mod, "emit", lambda *a, **k: None)

    assert _mod.main(["--apply"]) == 1


def test_apply_retire_failure_after_enable_leaves_both_producers_active(monkeypatch, tmp_path):
    """A retire failure AFTER a successful enable is a recoverable duplicate
    (both producers active), not a silent-miss outage — the deploy still
    fails (so the operator intervenes) but the failure mode is a double,
    not a zero (post-merge Codex review, #723)."""
    _patch_deploy_user_ok(monkeypatch)
    _install_fake_units(monkeypatch, tmp_path)
    tick_path = _patch_tick(monkeypatch, tmp_path)

    monkeypatch.setattr(
        _mod.cron_lib,
        "openclaw_cron_list",
        _fake_cron_list([{"name": "habits-weekly-report", "id": "abc-123"}]),
    )

    def _run(argv, cwd=None):
        joined = " ".join(argv)
        if "weekly_report_driver" in joined:
            _write_fresh_tick(tick_path)
            return (0, "self-test OK\n", "")
        if "list-timers" in joined:
            return (0, "felix-habits-weekly.timer  next elapse\n", "")
        if "enable" in joined and "felix-habits-weekly.timer" in joined:
            return (0, "", "")
        if "cron" in joined and "rm" in joined:
            return (1, "", "permission denied")
        return (0, "", "")

    monkeypatch.setattr(_mod, "_run", _run)
    monkeypatch.setattr(_mod, "emit", lambda *a, **k: None)

    assert _mod.main(["--apply"]) == 1


def test_apply_fails_when_postcheck_detects_double_producer(monkeypatch, tmp_path):
    """Even if the cutover steps individually 'succeed', the final postcheck
    must still catch a double-producer state and fail the deploy."""
    _patch_deploy_user_ok(monkeypatch)
    _install_fake_units(monkeypatch, tmp_path)
    tick_path = _patch_tick(monkeypatch, tmp_path)

    # Simulate: legacy cron never actually gets removed from the listing
    # (e.g. openclaw internal state lag), so the postcheck sees it present.
    def _list():
        return _FakeLibResult(
            ok=True, details={"crons": [{"name": "habits-weekly-report", "id": "abc-123"}]}
        )

    monkeypatch.setattr(_mod.cron_lib, "openclaw_cron_list", _list)

    def _run(argv, cwd=None):
        joined = " ".join(argv)
        if "weekly_report_driver" in joined:
            _write_fresh_tick(tick_path)
            return (0, "self-test OK\n", "")
        if "cron" in joined and "rm" in joined:
            return (0, "", "")
        if "list-timers" in joined:
            return (0, "felix-habits-weekly.timer  next elapse\n", "")
        if "is-enabled" in joined:
            return (0, "enabled\n", "")
        return (0, "", "")

    monkeypatch.setattr(_mod, "_run", _run)
    monkeypatch.setattr(_mod, "emit", lambda *a, **k: None)

    assert _mod.main(["--apply"]) == 1


# ---------------------------------------------------------------------------
# Manifest schema validity + non-numbering.
# ---------------------------------------------------------------------------


def test_manifest_is_schema_valid_tier3_audited():
    import yaml
    from jsonschema import Draft202012Validator

    schema_path = _REPO_ROOT / "deploys" / "schema" / "manifest-v1.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    data = yaml.safe_load(_resolve_manifest_path().read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(data)  # raises on any violation

    assert data["tier"] == 3
    assert data["audited_surface"] is True
    assert data["entrypoint"] == "scripts/deploy/deploy-habits-weekly-driver.py"
    assert data["name"] == "habits-weekly-driver"
    assert data["mission_slug"] == "deterministic-cron-hardening-01KXA4PX"
    assert data["expected_baselines"] == ["openclaw-cron.txt"]


def test_manifest_is_not_pre_numbered():
    """felix-deployer assigns the applied number; a hardcoded 00NN- prefix in
    deploys/queued/ would collide with max(applied)+1 (known gotcha)."""
    assert _MANIFEST_QUEUED.name == "habits-weekly-driver.yaml"
    if _MANIFEST_QUEUED.exists():
        # Still queued: filename must not carry a numeric prefix.
        assert not _MANIFEST_QUEUED.name[0].isdigit()


# ---------------------------------------------------------------------------
# The deploy entrypoint is executable (felix-deployer runs it directly).
# ---------------------------------------------------------------------------


def test_entrypoint_is_executable():
    import os

    assert os.access(_ENTRYPOINT_PATH, os.X_OK), "deploy script must be chmod +x"

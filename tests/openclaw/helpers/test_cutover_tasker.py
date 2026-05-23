"""Unit tests for ``scripts/openclaw/helpers/cutover_tasker.py`` (WP03 T009).

The cutover script is a one-shot operator tool — these tests verify the
contract documented in ``contracts/cli.md`` § cutover_tasker without making
real subprocess calls, touching the operator's real ``~/.config/openclaw``
directory, or writing to office2 deployment paths.

The reconcile subprocess (``python3 -m scripts.enrichment.reconcile_completions``)
is patched at the ``subprocess.run`` boundary. Filesystem deploys are routed
through ``shutil.copyfile`` which is patched per-test. Marker writes go to
``tmp_path`` via the ``marker_path`` override parameter so we can assert on
file contents without touching ``$HOME``.

Mirrors the test shape of ``tests/doc_audit/helpers/test_cutover_362.py``
adapted to the tasker-cutover side-effect mix (file deploys vs gh API calls).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

# Bootstrap sys.path so ``openclaw.helpers.cutover_tasker`` resolves without
# depending on the ``scripts.`` namespace package prefix. Mirrors the
# bootstrap in ``tests/openclaw/helpers/test_rotate_main_session.py``.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from openclaw.helpers import cutover_tasker  # noqa: E402
from openclaw.helpers.cutover_tasker import (  # noqa: E402
    CutoverResult,
    MISSION_ID,
    MISSION_SLUG,
    RECONCILE_MODULE,
    _deploy_file,
    _marker_exists,
    _run_reconcile,
    _write_marker,
    main,
    run,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Override the module-level MARKER_PATH to live under tmp_path."""
    marker = tmp_path / "cutover-310.done"
    monkeypatch.setattr(cutover_tasker, "MARKER_PATH", marker)
    return marker


@pytest.fixture
def tmp_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Synthesize SKILL.md + AGENTS.md sources under tmp_path.

    Overrides the module-level SKILL_SOURCE / AGENTS_SOURCE / SKILL_TARGET /
    AGENTS_TARGET constants so the deploy step writes inside tmp_path rather
    than the office2 paths. Returns a dict so tests can read sources +
    targets back.
    """
    skill_source = tmp_path / "src" / "skill" / "SKILL.md"
    skill_source.parent.mkdir(parents=True, exist_ok=True)
    skill_source.write_text("# task-intelligence SKILL\nfake content\n", encoding="utf-8")

    agents_source = tmp_path / "src" / "agents" / "AGENTS.md"
    agents_source.parent.mkdir(parents=True, exist_ok=True)
    agents_source.write_text("# tasker AGENTS\nfake cut content\n", encoding="utf-8")

    skill_target = tmp_path / "deploy" / "skill" / "SKILL.md"
    agents_target = tmp_path / "deploy" / "agents" / "AGENTS.md"

    monkeypatch.setattr(cutover_tasker, "SKILL_SOURCE", skill_source)
    monkeypatch.setattr(cutover_tasker, "SKILL_TARGET", skill_target)
    monkeypatch.setattr(cutover_tasker, "AGENTS_SOURCE", agents_source)
    monkeypatch.setattr(cutover_tasker, "AGENTS_TARGET", agents_target)

    return {
        "skill_source": skill_source,
        "skill_target": skill_target,
        "agents_source": agents_source,
        "agents_target": agents_target,
    }


@pytest.fixture
def fake_reconcile(monkeypatch: pytest.MonkeyPatch) -> mock.MagicMock:
    """Patch ``subprocess.run`` inside cutover_tasker.

    Default behavior: return a successful CompletedProcess. Tests can override
    by setting the mock's ``side_effect`` to a CalledProcessError.
    """
    runner = mock.MagicMock(
        return_value=subprocess.CompletedProcess(
            args=["python3", "-m", RECONCILE_MODULE],
            returncode=0,
            stdout="",
            stderr="",
        )
    )
    monkeypatch.setattr(cutover_tasker.subprocess, "run", runner)
    return runner


# ---------------------------------------------------------------------------
# 1. Happy path — both deploys + reconcile + marker
# ---------------------------------------------------------------------------


def test_run_happy_path_deploys_skill_agents_and_runs_reconcile(
    tmp_sources: dict[str, Path],
    fake_reconcile: mock.MagicMock,
    tmp_marker: Path,
) -> None:
    result = run(marker_path=tmp_marker)

    assert isinstance(result, CutoverResult)
    assert result.skill_deployed is True
    assert result.agents_deployed is True
    assert result.reconcile_invoked is True
    assert result.marker_written is True
    assert result.dry_run is False
    assert result.already_done is False

    # Files actually copied
    assert tmp_sources["skill_target"].exists()
    assert tmp_sources["agents_target"].exists()
    assert (
        tmp_sources["skill_target"].read_text(encoding="utf-8")
        == tmp_sources["skill_source"].read_text(encoding="utf-8")
    )
    assert (
        tmp_sources["agents_target"].read_text(encoding="utf-8")
        == tmp_sources["agents_source"].read_text(encoding="utf-8")
    )

    # Reconcile subprocess called exactly once with the expected module
    assert fake_reconcile.call_count == 1
    cmd = fake_reconcile.call_args.args[0]
    assert cmd == ["python3", "-m", RECONCILE_MODULE]

    # Marker written with the expected fields
    body = tmp_marker.read_text(encoding="utf-8")
    assert MISSION_SLUG in body
    assert MISSION_ID in body
    assert "skill_deployed: true" in body
    assert "agents_deployed: true" in body
    assert "reconcile_invoked: true" in body


# ---------------------------------------------------------------------------
# 2. Dry-run — no mutations, no subprocess
# ---------------------------------------------------------------------------


def test_run_dry_run_makes_no_mutations(
    tmp_sources: dict[str, Path],
    fake_reconcile: mock.MagicMock,
    tmp_marker: Path,
) -> None:
    result = run(dry_run=True, marker_path=tmp_marker)

    assert result.dry_run is True
    assert result.skill_deployed is True  # "would deploy"
    assert result.agents_deployed is True
    assert result.reconcile_invoked is True
    assert result.marker_written is True
    assert result.already_done is False

    # No files copied, no marker on disk, no subprocess called
    assert not tmp_sources["skill_target"].exists()
    assert not tmp_sources["agents_target"].exists()
    assert not tmp_marker.exists()
    assert fake_reconcile.call_count == 0


# ---------------------------------------------------------------------------
# 3. Idempotent no-op — marker pre-exists, run() returns already_done
# ---------------------------------------------------------------------------


def test_run_idempotent_when_marker_exists(
    tmp_sources: dict[str, Path],
    fake_reconcile: mock.MagicMock,
    tmp_marker: Path,
) -> None:
    tmp_marker.parent.mkdir(parents=True, exist_ok=True)
    tmp_marker.write_text("pre-existing marker\n", encoding="utf-8")

    result = run(marker_path=tmp_marker)

    assert result.already_done is True
    assert result.skill_deployed is False
    assert result.agents_deployed is False
    assert result.reconcile_invoked is False
    assert result.marker_written is False

    # No deploys, no subprocess calls
    assert not tmp_sources["skill_target"].exists()
    assert not tmp_sources["agents_target"].exists()
    assert fake_reconcile.call_count == 0


# ---------------------------------------------------------------------------
# 4. --force overrides the marker
# ---------------------------------------------------------------------------


def test_run_force_overrides_marker(
    tmp_sources: dict[str, Path],
    fake_reconcile: mock.MagicMock,
    tmp_marker: Path,
) -> None:
    tmp_marker.parent.mkdir(parents=True, exist_ok=True)
    tmp_marker.write_text("stale marker\n", encoding="utf-8")

    result = run(force=True, marker_path=tmp_marker)

    assert result.already_done is False
    assert result.skill_deployed is True
    assert result.agents_deployed is True
    assert result.reconcile_invoked is True
    assert result.marker_written is True

    # Fresh marker contents (post-force run wrote a real marker body)
    body = tmp_marker.read_text(encoding="utf-8")
    assert MISSION_SLUG in body
    assert "skill_deployed: true" in body


# ---------------------------------------------------------------------------
# 5. SKILL.md source missing → exit 1
# ---------------------------------------------------------------------------


def test_main_returns_1_on_missing_skill_source(
    tmp_sources: dict[str, Path],
    fake_reconcile: mock.MagicMock,
    tmp_marker: Path,
) -> None:
    tmp_sources["skill_source"].unlink()

    rc = main([])

    assert rc == 1
    assert not tmp_marker.exists()
    # Reconcile should NOT have run (deploy step failed first)
    assert fake_reconcile.call_count == 0


# ---------------------------------------------------------------------------
# 6. AGENTS.md source missing → exit 1
# ---------------------------------------------------------------------------


def test_main_returns_1_on_missing_agents_source(
    tmp_sources: dict[str, Path],
    fake_reconcile: mock.MagicMock,
    tmp_marker: Path,
) -> None:
    tmp_sources["agents_source"].unlink()

    rc = main([])

    assert rc == 1
    assert not tmp_marker.exists()
    # SKILL deployed but AGENTS missing → reconcile never runs
    assert fake_reconcile.call_count == 0


# ---------------------------------------------------------------------------
# 7. Reconcile subprocess failure → exit 2
# ---------------------------------------------------------------------------


def test_main_returns_2_on_reconcile_failure(
    tmp_sources: dict[str, Path],
    fake_reconcile: mock.MagicMock,
    tmp_marker: Path,
) -> None:
    fake_reconcile.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd=["python3", "-m", RECONCILE_MODULE],
        stderr="Vikunja unreachable",
    )

    rc = main([])

    assert rc == 2
    # Marker should NOT be written if reconcile failed
    assert not tmp_marker.exists()
    # But the file deploys DID land (reconcile is step 3)
    assert tmp_sources["skill_target"].exists()
    assert tmp_sources["agents_target"].exists()


# ---------------------------------------------------------------------------
# 8. Marker write failure → exit 1
# ---------------------------------------------------------------------------


def test_main_returns_1_on_marker_write_failure(
    tmp_sources: dict[str, Path],
    fake_reconcile: mock.MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Point MARKER_PATH at a location that fails on parent.mkdir
    # (use an existing file as the parent — mkdir(parents=True) raises
    # NotADirectoryError, a subclass of OSError).
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    bad_marker = blocker / "subdir" / "cutover-310.done"
    monkeypatch.setattr(cutover_tasker, "MARKER_PATH", bad_marker)

    rc = main([])

    assert rc == 1


# ---------------------------------------------------------------------------
# 9. Marker contents verification
# ---------------------------------------------------------------------------


def test_marker_contents_are_well_formed(
    tmp_sources: dict[str, Path],
    fake_reconcile: mock.MagicMock,
    tmp_marker: Path,
) -> None:
    run(marker_path=tmp_marker)

    body = tmp_marker.read_text(encoding="utf-8")
    fields: dict[str, str] = {}
    for line in body.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fields[k.strip()] = v.strip()

    assert fields["mission"] == MISSION_SLUG
    assert fields["mission_id"] == MISSION_ID
    assert fields["run_at_utc"].endswith("Z")
    assert "T" in fields["run_at_utc"]
    assert fields["skill_deployed"] == "true"
    assert fields["agents_deployed"] == "true"
    assert fields["reconcile_invoked"] == "true"
    # Paths recorded
    assert fields["skill_source"].endswith("SKILL.md")
    assert fields["agents_source"].endswith("AGENTS.md")


# ---------------------------------------------------------------------------
# 10. CLI exit codes — 0/0/3
# ---------------------------------------------------------------------------


def test_main_returns_0_on_happy_path(
    tmp_sources: dict[str, Path],
    fake_reconcile: mock.MagicMock,
    tmp_marker: Path,
) -> None:
    rc = main([])

    assert rc == 0
    assert tmp_marker.exists()


def test_main_returns_0_on_idempotent_no_op(
    tmp_sources: dict[str, Path],
    fake_reconcile: mock.MagicMock,
    tmp_marker: Path,
) -> None:
    tmp_marker.parent.mkdir(parents=True, exist_ok=True)
    tmp_marker.write_text("already-done\n", encoding="utf-8")

    rc = main([])

    assert rc == 0
    # Marker untouched
    assert tmp_marker.read_text(encoding="utf-8") == "already-done\n"


def test_main_returns_3_on_bad_flag(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["--unknown-flag"])
    assert rc == 3
    captured = capsys.readouterr()
    assert "error:" in captured.err or "unrecognized" in captured.err.lower()


def test_main_help_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "--dry-run" in out
    assert "--force" in out


# ---------------------------------------------------------------------------
# 11. Helper-level coverage — _deploy_file, _run_reconcile, _marker_exists
# ---------------------------------------------------------------------------


def test_deploy_file_creates_parent_dir(tmp_path: Path) -> None:
    source = tmp_path / "src.md"
    source.write_text("contents\n", encoding="utf-8")
    target = tmp_path / "a" / "b" / "c" / "dst.md"

    _deploy_file(source=source, target=target, dry_run=False, label="test")

    assert target.exists()
    assert target.read_text(encoding="utf-8") == "contents\n"


def test_deploy_file_dry_run_makes_no_changes(tmp_path: Path) -> None:
    source = tmp_path / "src.md"
    source.write_text("contents\n", encoding="utf-8")
    target = tmp_path / "dst.md"

    result = _deploy_file(source=source, target=target, dry_run=True, label="test")

    assert result is True
    assert not target.exists()


def test_deploy_file_raises_filenotfound_when_source_missing(tmp_path: Path) -> None:
    source = tmp_path / "nope.md"
    target = tmp_path / "dst.md"

    with pytest.raises(FileNotFoundError):
        _deploy_file(source=source, target=target, dry_run=False, label="test")


def test_run_reconcile_dry_run_makes_no_subprocess_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No fake_reconcile here — if the real subprocess.run is invoked we'd
    # actually call python3, so install a sentinel that fails loudly.
    def boom(*args, **kwargs):
        raise AssertionError("subprocess.run should not be called in dry-run")

    monkeypatch.setattr(cutover_tasker.subprocess, "run", boom)
    assert _run_reconcile(dry_run=True) is True


def test_run_reconcile_invokes_subprocess(
    fake_reconcile: mock.MagicMock,
) -> None:
    assert _run_reconcile(dry_run=False) is True
    assert fake_reconcile.call_count == 1
    cmd = fake_reconcile.call_args.args[0]
    assert cmd == ["python3", "-m", RECONCILE_MODULE]


def test_marker_exists_default_uses_module_constant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "default-marker.done"
    monkeypatch.setattr(cutover_tasker, "MARKER_PATH", marker)
    assert _marker_exists() is False
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("x", encoding="utf-8")
    assert _marker_exists() is True


def test_marker_exists_with_override(tmp_path: Path) -> None:
    marker = tmp_path / "override.done"
    assert _marker_exists(marker) is False
    marker.write_text("x", encoding="utf-8")
    assert _marker_exists(marker) is True


# ---------------------------------------------------------------------------
# 12. _write_marker — atomic + dry-run + cleanup-on-failure
# ---------------------------------------------------------------------------


def test_write_marker_is_atomic_no_tempfile_left_behind(tmp_path: Path) -> None:
    marker = tmp_path / "atomic-marker.done"
    _write_marker(
        skill_deployed=True,
        agents_deployed=True,
        reconcile_invoked=True,
        dry_run=False,
        marker_path=marker,
    )

    assert marker.exists()
    leftover = [p for p in tmp_path.iterdir() if p.name != marker.name]
    assert leftover == []


def test_write_marker_dry_run_makes_no_filesystem_changes(tmp_path: Path) -> None:
    marker = tmp_path / "would-not-write.done"
    result = _write_marker(
        skill_deployed=True,
        agents_deployed=True,
        reconcile_invoked=True,
        dry_run=True,
        marker_path=marker,
    )
    assert result is True
    assert not marker.exists()


def test_write_marker_cleanup_on_rename_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If os.replace fails, the temporary file is unlinked."""
    marker = tmp_path / "fail-marker.done"

    real_replace = os.replace

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(cutover_tasker.os, "replace", boom)

    with pytest.raises(OSError):
        _write_marker(
            skill_deployed=True,
            agents_deployed=True,
            reconcile_invoked=True,
            dry_run=False,
            marker_path=marker,
        )

    # No stray .tmp file
    leftovers = list(tmp_path.iterdir())
    assert leftovers == []
    monkeypatch.setattr(cutover_tasker.os, "replace", real_replace)


# ---------------------------------------------------------------------------
# 13. CutoverResult is the expected shape
# ---------------------------------------------------------------------------


def test_cutover_result_is_frozen_dataclass() -> None:
    result = CutoverResult(
        skill_deployed=True,
        agents_deployed=True,
        reconcile_invoked=True,
        marker_written=True,
        dry_run=False,
        already_done=False,
    )
    with pytest.raises(dataclass_frozen_error()):
        result.skill_deployed = False  # type: ignore[misc]


def dataclass_frozen_error():
    """Pytest cross-version helper: dataclass mutation raises
    FrozenInstanceError (a subclass of AttributeError in CPython)."""
    import dataclasses as _dc

    return _dc.FrozenInstanceError

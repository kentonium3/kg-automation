"""Tests for the spec-kitty per-repo version-drift check (#599).

Hermetic: every test builds synthetic ``.kittify/metadata.yaml`` repos under a
``tmp_path`` root and injects ``--expected-version``, so nothing depends on
``~/repos`` existing or on ``spec-kitty`` being installed.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.spec_kitty.check_version_drift import (
    STATUS_CURRENT,
    STATUS_DRIFT,
    STATUS_UNKNOWN,
    build_report,
    detect_cli_version,
    discover_kittified_repos,
    has_drift,
    main,
    parse_recorded_version,
)


def _make_repo(root: Path, name: str, *, version: str | None = "3.2.6", metadata: str | None = None) -> Path:
    """Create a synthetic repo dir under ``root`` with a ``.kittify/metadata.yaml``."""
    repo = root / name
    kittify = repo / ".kittify"
    kittify.mkdir(parents=True)
    if metadata is not None:
        (kittify / "metadata.yaml").write_text(metadata, encoding="utf-8")
    elif version is not None:
        (kittify / "metadata.yaml").write_text(
            f"spec_kitty:\n  version: {version}\n  schema_version: 3\n",
            encoding="utf-8",
        )
    return repo


# --- discovery ----------------------------------------------------------------


def test_discover_finds_only_kittified(tmp_path: Path) -> None:
    _make_repo(tmp_path, "a", version="3.2.6")
    _make_repo(tmp_path, "b", version="3.2.3")
    (tmp_path / "not-kittified").mkdir()  # no .kittify
    (tmp_path / "loose-file.txt").write_text("x", encoding="utf-8")
    found = [d.name for d in discover_kittified_repos(tmp_path)]
    assert found == ["a", "b"]  # sorted, non-kittified excluded


def test_discover_missing_root_returns_empty(tmp_path: Path) -> None:
    assert discover_kittified_repos(tmp_path / "nope") == []


def test_discover_excludes_hidden_dirs(tmp_path: Path) -> None:
    _make_repo(tmp_path, "real", version="3.2.6")
    _make_repo(tmp_path, ".autopilot-wt", version="3.2.6")  # hidden scratch/worktree
    found = [d.name for d in discover_kittified_repos(tmp_path)]
    assert found == ["real"]


def test_discover_excludes_linked_worktrees(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, "worktree-checkout", version="3.2.6")
    (repo / ".git").write_text("gitdir: /somewhere/.git/worktrees/x\n", encoding="utf-8")
    _make_repo(tmp_path, "standalone", version="3.2.6")
    (_make_repo(tmp_path, "plain-git", version="3.2.6") / ".git").mkdir()  # .git dir = real repo
    found = [d.name for d in discover_kittified_repos(tmp_path)]
    assert found == ["plain-git", "standalone"]  # worktree-checkout excluded


# --- version parsing ----------------------------------------------------------


def test_parse_recorded_version_reads_value(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, "a", version="3.2.0rc18")
    assert parse_recorded_version(repo / ".kittify" / "metadata.yaml") == "3.2.0rc18"


def test_parse_recorded_version_missing_file(tmp_path: Path) -> None:
    assert parse_recorded_version(tmp_path / "absent.yaml") is None


def test_parse_recorded_version_no_spec_kitty_block(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, "a", metadata="environment:\n  python_version: 3.13\n")
    assert parse_recorded_version(repo / ".kittify" / "metadata.yaml") is None


def test_parse_recorded_version_malformed_yaml(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, "a", metadata="spec_kitty:\n  version: [unclosed\n")
    assert parse_recorded_version(repo / ".kittify" / "metadata.yaml") is None


# --- classification -----------------------------------------------------------


def test_build_report_classifies_all_three_statuses(tmp_path: Path) -> None:
    _make_repo(tmp_path, "current-repo", version="3.2.6")
    _make_repo(tmp_path, "drift-repo", version="3.2.3")
    _make_repo(tmp_path, "unknown-repo", metadata="not_spec_kitty: true\n")
    reports = {r.repo: r for r in build_report(tmp_path, "3.2.6")}
    assert reports["current-repo"].status == STATUS_CURRENT
    assert reports["drift-repo"].status == STATUS_DRIFT
    assert reports["drift-repo"].recorded_version == "3.2.3"
    assert reports["unknown-repo"].status == STATUS_UNKNOWN
    assert reports["unknown-repo"].recorded_version is None


def test_has_drift_true_and_false(tmp_path: Path) -> None:
    _make_repo(tmp_path, "a", version="3.2.6")
    assert not has_drift(build_report(tmp_path, "3.2.6"))
    _make_repo(tmp_path, "b", version="3.2.3")
    assert has_drift(build_report(tmp_path, "3.2.6"))


# --- CLI ----------------------------------------------------------------------


def test_main_no_drift_exit_zero_json(tmp_path: Path, capsys) -> None:
    _make_repo(tmp_path, "a", version="3.2.6")
    _make_repo(tmp_path, "b", version="3.2.6")
    rc = main(["--repos-root", str(tmp_path), "--expected-version", "3.2.6", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["drift"] is False
    assert payload["drift_count"] == 0
    assert payload["repo_count"] == 2


def test_main_drift_exit_one(tmp_path: Path, capsys) -> None:
    _make_repo(tmp_path, "a", version="3.2.6")
    _make_repo(tmp_path, "b", version="3.2.0rc33")
    rc = main(["--repos-root", str(tmp_path), "--expected-version", "3.2.6", "--json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["drift"] is True
    assert payload["drift_count"] == 1
    assert {r["repo"]: r["status"] for r in payload["repos"]}["b"] == STATUS_DRIFT


def test_main_human_output_lists_drift(tmp_path: Path, capsys) -> None:
    _make_repo(tmp_path, "behind", version="3.2.3")
    rc = main(["--repos-root", str(tmp_path), "--expected-version", "3.2.6"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "DRIFT" in out
    assert "behind" in out


def test_main_bad_root_exit_two(tmp_path: Path) -> None:
    rc = main(["--repos-root", str(tmp_path / "missing"), "--expected-version", "3.2.6"])
    assert rc == 2


def test_main_no_expected_and_no_cli_exit_two(tmp_path: Path, monkeypatch) -> None:
    # Force CLI detection to fail so the "undeterminable expected" path is exercised.
    monkeypatch.setattr(
        "scripts.spec_kitty.check_version_drift.detect_cli_version", lambda: None
    )
    rc = main(["--repos-root", str(tmp_path)])
    assert rc == 2


# --- CLI version detection (no network; tolerant of absence) -------------------


def test_detect_cli_version_returns_str_or_none() -> None:
    # In CI spec-kitty may be absent (-> None); locally it returns a version token.
    result = detect_cli_version()
    assert result is None or isinstance(result, str)


class _FakeCompleted:
    def __init__(self, stdout: str = "", stderr: str = "") -> None:
        self.stdout = stdout
        self.stderr = stderr


def test_detect_cli_version_parses_version_line(monkeypatch) -> None:
    # The `... version X` line is preferred over any stray token elsewhere.
    monkeypatch.setattr(
        "scripts.spec_kitty.check_version_drift.subprocess.run",
        lambda *a, **k: _FakeCompleted(stdout="Spec Kitty 999 banner\nspec-kitty-cli version 3.2.6\n"),
    )
    assert detect_cli_version() == "3.2.6"


def test_detect_cli_version_parses_rc_bare_token(monkeypatch) -> None:
    monkeypatch.setattr(
        "scripts.spec_kitty.check_version_drift.subprocess.run",
        lambda *a, **k: _FakeCompleted(stdout="3.2.0rc44\n"),
    )
    assert detect_cli_version() == "3.2.0rc44"


def test_detect_cli_version_no_token_returns_none(monkeypatch) -> None:
    monkeypatch.setattr(
        "scripts.spec_kitty.check_version_drift.subprocess.run",
        lambda *a, **k: _FakeCompleted(stdout="no version here\n"),
    )
    assert detect_cli_version() is None


def test_detect_cli_version_binary_absent_returns_none(monkeypatch) -> None:
    def _raise(*a, **k):
        raise OSError("spec-kitty not found")

    monkeypatch.setattr(
        "scripts.spec_kitty.check_version_drift.subprocess.run", _raise
    )
    assert detect_cli_version() is None

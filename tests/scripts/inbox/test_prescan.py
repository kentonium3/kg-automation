"""Unit tests for scripts/inbox/prescan.py.

All tests use synthetic inboxes + a synthetic vault registry. No real
vault paths, no network, no office2 contact. Fixtures under
``tests/scripts/inbox/fixtures/`` are copied into per-test tmpdirs so
mtimes can be set deterministically.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Make the repo root importable so ``scripts.inbox.prescan`` resolves.
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.inbox import prescan  # noqa: E402
from scripts.inbox.prescan import (  # noqa: E402
    ARCHIVE_SCAN_CAP,
    ArchiveAnomaly,
    ArchiveResult,
    InboxFile,
    PrescanError,
    PrescanResult,
    archive_stale,
    classify_file,
    main,
    resolve_registry,
    run_prescan,
    run_self_check,
    scan_archive_anomalies,
    scan_directory,
)


FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE_NAMES = [
    "processed-recent.md",
    "processed-stale.md",
    "unprocessed.md",
    "no-frontmatter.md",
    "no-status.md",
    "malformed-yaml.md",
    "unknown-status.md",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_registry(tmp_path: Path, inbox: Path, inbox_processed: Path) -> Path:
    registry = tmp_path / "paths.json"
    registry.write_text(
        json.dumps(
            {
                "version": 1,
                "paths": {
                    "inbox": str(inbox),
                    "inbox_processed": str(inbox_processed),
                },
            }
        )
    )
    return registry


def _setup_env(monkeypatch, tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """Create synthetic inbox, inbox_processed, registry, log dir."""
    inbox = tmp_path / "01-Inbox"
    processed = tmp_path / "02-Inbox-Processed"
    logs = tmp_path / "logs"
    inbox.mkdir()
    processed.mkdir()
    logs.mkdir()
    registry = _write_registry(tmp_path, inbox, processed)
    monkeypatch.setenv("PRESCAN_REGISTRY_PATH", str(registry))
    monkeypatch.setenv("PRESCAN_LOG_DIR", str(logs))
    return inbox, processed, registry, logs


def _copy_fixture(name: str, dst_dir: Path, dst_name: str | None = None) -> Path:
    dst = dst_dir / (dst_name or name)
    shutil.copy(FIXTURES_DIR / name, dst)
    return dst


def _set_age(path: Path, age_days: float) -> None:
    """Set a file's mtime to ``age_days`` in the past."""
    target = datetime.now(timezone.utc) - timedelta(days=age_days)
    ts = target.timestamp()
    os.utime(path, (ts, ts))


# ---------------------------------------------------------------------------
# Registry resolution
# ---------------------------------------------------------------------------


def test_registry_missing_raises_prescan_error(monkeypatch, tmp_path):
    monkeypatch.setenv("PRESCAN_REGISTRY_PATH", str(tmp_path / "nope.json"))
    with pytest.raises(PrescanError, match="not found"):
        resolve_registry()


def test_registry_malformed_json_raises_prescan_error(monkeypatch, tmp_path):
    registry = tmp_path / "paths.json"
    registry.write_text("{not json}")
    monkeypatch.setenv("PRESCAN_REGISTRY_PATH", str(registry))
    with pytest.raises(PrescanError, match="not valid JSON"):
        resolve_registry()


def test_registry_missing_inbox_key_raises_prescan_error(monkeypatch, tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    registry = tmp_path / "paths.json"
    registry.write_text(json.dumps({"paths": {"inbox_processed": str(processed)}}))
    monkeypatch.setenv("PRESCAN_REGISTRY_PATH", str(registry))
    with pytest.raises(PrescanError, match="paths.inbox"):
        resolve_registry()


def test_registry_missing_inbox_processed_key_raises_prescan_error(
    monkeypatch, tmp_path
):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    registry = tmp_path / "paths.json"
    registry.write_text(json.dumps({"paths": {"inbox": str(inbox)}}))
    monkeypatch.setenv("PRESCAN_REGISTRY_PATH", str(registry))
    with pytest.raises(PrescanError, match="paths.inbox_processed"):
        resolve_registry()


def test_registry_missing_paths_object_raises_prescan_error(monkeypatch, tmp_path):
    registry = tmp_path / "paths.json"
    registry.write_text(json.dumps({"version": 1}))
    monkeypatch.setenv("PRESCAN_REGISTRY_PATH", str(registry))
    with pytest.raises(PrescanError, match="'paths' object"):
        resolve_registry()


def test_registry_inbox_path_does_not_exist_raises(monkeypatch, tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    registry = tmp_path / "paths.json"
    registry.write_text(
        json.dumps(
            {
                "paths": {
                    "inbox": str(tmp_path / "nope"),
                    "inbox_processed": str(processed),
                }
            }
        )
    )
    monkeypatch.setenv("PRESCAN_REGISTRY_PATH", str(registry))
    with pytest.raises(PrescanError, match="Inbox path does not exist"):
        resolve_registry()


def test_registry_inbox_is_file_not_dir_raises(monkeypatch, tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    bogus = tmp_path / "file_not_dir"
    bogus.write_text("x")
    registry = tmp_path / "paths.json"
    registry.write_text(
        json.dumps(
            {"paths": {"inbox": str(bogus), "inbox_processed": str(processed)}}
        )
    )
    monkeypatch.setenv("PRESCAN_REGISTRY_PATH", str(registry))
    with pytest.raises(PrescanError, match="not a directory"):
        resolve_registry()


def test_registry_happy_path_returns_paths(monkeypatch, tmp_path):
    inbox, processed, _, _ = _setup_env(monkeypatch, tmp_path)
    got_inbox, got_processed = resolve_registry()
    assert got_inbox == inbox
    assert got_processed == processed


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def test_classify_unprocessed(tmp_path):
    f = _copy_fixture("unprocessed.md", tmp_path)
    _set_age(f, 1)
    result = classify_file(f, datetime.now(timezone.utc))
    assert result.classification == "unprocessed"
    assert result.status_raw == "unprocessed"
    assert result.warning is None


def test_classify_processed_recent(tmp_path):
    f = _copy_fixture("processed-recent.md", tmp_path)
    _set_age(f, 3)
    result = classify_file(f, datetime.now(timezone.utc))
    assert result.classification == "processed-recent"
    assert result.status_raw == "processed"


def test_classify_processed_stale(tmp_path):
    f = _copy_fixture("processed-stale.md", tmp_path)
    _set_age(f, 8)
    result = classify_file(f, datetime.now(timezone.utc))
    assert result.classification == "processed-stale"
    assert result.status_raw == "processed"


def test_classify_processed_at_boundary_exactly_7_days(tmp_path):
    """age == 7.0 days is NOT stale — the boundary is exclusive.

    Uses inline frontmatter without processed_at so the boundary is tested
    against filesystem mtime (the legacy fallback path).
    """
    f = tmp_path / "boundary.md"
    f.write_text("---\nstatus: processed\ntitle: boundary\n---\nbody\n")
    # Pin both the reference ``now`` and the mtime so age_days is exactly 7.0.
    now_utc = datetime.now(timezone.utc)
    target = now_utc - timedelta(days=7.0)
    ts = target.timestamp()
    os.utime(f, (ts, ts))
    result = classify_file(f, now_utc)
    assert result.classification == "processed-recent"


def test_classify_processed_at_boundary_just_over_7_days(tmp_path):
    """Uses inline frontmatter without processed_at to test mtime boundary."""
    f = tmp_path / "boundary.md"
    f.write_text("---\nstatus: processed\ntitle: boundary\n---\nbody\n")
    now_utc = datetime.now(timezone.utc)
    target = now_utc - timedelta(days=7.0, seconds=1)
    ts = target.timestamp()
    os.utime(f, (ts, ts))
    result = classify_file(f, now_utc)
    assert result.classification == "processed-stale"


def test_classify_leading_blank_line_before_frontmatter(tmp_path):
    """Real Obsidian/Templater files often start with a blank line before the
    ``---`` fence. The helper must skip leading blank lines and still find
    the frontmatter. Discovered during mission 027 WP05 live deploy."""
    f = tmp_path / "with-leading-blank.md"
    f.write_text(
        "\n---\ndate: 2026-04-11\nstatus: processed\n---\nbody\n",
        encoding="utf-8",
    )
    _set_age(f, 3)  # recent
    result = classify_file(f, datetime.now(timezone.utc))
    assert result.classification == "processed-recent"
    assert result.status_raw == "processed"
    assert result.warning is None


def test_classify_multiple_leading_blank_lines(tmp_path):
    """Two or more leading blank lines must also be skipped."""
    f = tmp_path / "many-blanks.md"
    f.write_text(
        "\n\n\n---\nstatus: unprocessed\n---\n",
        encoding="utf-8",
    )
    _set_age(f, 1)
    result = classify_file(f, datetime.now(timezone.utc))
    assert result.classification == "unprocessed"
    assert result.status_raw == "unprocessed"


def test_classify_no_frontmatter_treated_as_unprocessed(tmp_path):
    f = _copy_fixture("no-frontmatter.md", tmp_path)
    _set_age(f, 1)
    result = classify_file(f, datetime.now(timezone.utc))
    assert result.classification == "unknown-treated-as-unprocessed"
    assert result.warning is not None
    assert "frontmatter" in result.warning.lower()


def test_classify_no_status_treated_as_unprocessed(tmp_path):
    f = _copy_fixture("no-status.md", tmp_path)
    _set_age(f, 1)
    result = classify_file(f, datetime.now(timezone.utc))
    assert result.classification == "unknown-treated-as-unprocessed"
    assert result.warning is not None


def test_classify_unknown_status_treated_as_unprocessed(tmp_path):
    f = _copy_fixture("unknown-status.md", tmp_path)
    _set_age(f, 1)
    result = classify_file(f, datetime.now(timezone.utc))
    assert result.classification == "unknown-treated-as-unprocessed"
    assert "unknown status" in (result.warning or "").lower()


# ---------------------------------------------------------------------------
# processed_at frontmatter (issue #187)
# ---------------------------------------------------------------------------


def test_classify_uses_processed_at_over_mtime(tmp_path):
    """processed_at in frontmatter takes priority over filesystem mtime."""
    now_utc = datetime.now(timezone.utc)
    three_days_ago = now_utc - timedelta(days=3)
    processed_at_str = three_days_ago.isoformat()
    f = tmp_path / "with-processed-at.md"
    f.write_text(
        f'---\nstatus: processed\nprocessed_at: "{processed_at_str}"\n---\nbody\n',
        encoding="utf-8",
    )
    _set_age(f, 10)  # mtime says 10 days — would be stale
    result = classify_file(f, now_utc)
    assert result.classification == "processed-recent"
    assert result.status_raw == "processed"


def test_classify_falls_back_to_mtime_without_processed_at(tmp_path):
    """Without processed_at, age comes from filesystem mtime (backward compat)."""
    f = tmp_path / "no-processed-at.md"
    f.write_text(
        "---\nstatus: processed\ntitle: Legacy note\n---\nbody\n",
        encoding="utf-8",
    )
    _set_age(f, 8)
    result = classify_file(f, datetime.now(timezone.utc))
    assert result.classification == "processed-stale"


def test_classify_falls_back_to_mtime_on_malformed_processed_at(tmp_path):
    """Malformed processed_at falls back to mtime silently."""
    f = tmp_path / "bad-processed-at.md"
    f.write_text(
        '---\nstatus: processed\nprocessed_at: "not-a-date"\n---\nbody\n',
        encoding="utf-8",
    )
    _set_age(f, 3)
    result = classify_file(f, datetime.now(timezone.utc))
    assert result.classification == "processed-recent"
    assert result.warning is None


# ---------------------------------------------------------------------------
# scan_directory
# ---------------------------------------------------------------------------


def test_scan_directory_is_sorted_deterministically(tmp_path):
    _copy_fixture("unprocessed.md", tmp_path, "b.md")
    _copy_fixture("unprocessed.md", tmp_path, "a.md")
    _copy_fixture("unprocessed.md", tmp_path, "c.md")
    for p in tmp_path.iterdir():
        _set_age(p, 1)
    results = scan_directory(tmp_path, datetime.now(timezone.utc))
    assert [r.path.name for r in results] == ["a.md", "b.md", "c.md"]


def test_scan_directory_ignores_non_markdown(tmp_path):
    _copy_fixture("unprocessed.md", tmp_path)
    (tmp_path / "ignore.txt").write_text("plain text")
    (tmp_path / "image.png").write_bytes(b"\x89PNG")
    _set_age(tmp_path / "unprocessed.md", 1)
    results = scan_directory(tmp_path, datetime.now(timezone.utc))
    assert len(results) == 1
    assert results[0].path.name == "unprocessed.md"


def test_private_subdirectory_is_never_walked(tmp_path):
    """Defense-in-depth: _private/ subtrees must be skipped (C-001)."""
    private = tmp_path / "_private"
    private.mkdir()
    shutil.copy(FIXTURES_DIR / "unprocessed.md", private / "secret.md")
    _copy_fixture("unprocessed.md", tmp_path, "public.md")
    _set_age(tmp_path / "public.md", 1)
    results = scan_directory(tmp_path, datetime.now(timezone.utc))
    names = [r.path.name for r in results]
    assert "public.md" in names
    assert "secret.md" not in names
    for r in results:
        assert "_private" not in r.path.parts


# ---------------------------------------------------------------------------
# archive_stale
# ---------------------------------------------------------------------------


def _make_stale_inbox_file(path: Path) -> InboxFile:
    _set_age(path, 8)
    mtime_utc = datetime.fromtimestamp(
        os.path.getmtime(path), tz=timezone.utc
    )
    return InboxFile(
        path=path,
        mtime_utc=mtime_utc,
        status_raw="processed",
        classification="processed-stale",
    )


def test_archive_moves_stale_file_to_processed_dir(tmp_path):
    inbox = tmp_path / "in"
    processed = tmp_path / "out"
    inbox.mkdir()
    processed.mkdir()
    src = _copy_fixture("processed-stale.md", inbox)
    stale = _make_stale_inbox_file(src)
    results = archive_stale([stale], processed)
    assert len(results) == 1
    assert results[0].success is True
    assert not src.exists()
    assert (processed / "processed-stale.md").exists()


def test_archive_skips_when_destination_exists(tmp_path):
    inbox = tmp_path / "in"
    processed = tmp_path / "out"
    inbox.mkdir()
    processed.mkdir()
    src = _copy_fixture("processed-stale.md", inbox)
    # Pre-existing destination:
    (processed / "processed-stale.md").write_text("existing")
    stale = _make_stale_inbox_file(src)
    results = archive_stale([stale], processed)
    assert len(results) == 1
    assert results[0].success is False
    assert "already exists" in (results[0].warning or "")
    # Source still in place (not overwritten):
    assert src.exists()
    assert (processed / "processed-stale.md").read_text() == "existing"


def test_archive_handles_move_failure_gracefully(tmp_path, monkeypatch):
    inbox = tmp_path / "in"
    processed = tmp_path / "out"
    inbox.mkdir()
    processed.mkdir()
    src = _copy_fixture("processed-stale.md", inbox)
    stale = _make_stale_inbox_file(src)

    def fake_move(src_arg, dst_arg):
        raise PermissionError("mocked perm denied")

    monkeypatch.setattr(prescan.shutil, "move", fake_move)
    results = archive_stale([stale], processed)
    assert len(results) == 1
    assert results[0].success is False
    assert "mocked perm denied" in (results[0].warning or "")
    # Source still present because move failed:
    assert src.exists()


def test_archive_never_moves_unprocessed_file(monkeypatch, tmp_path):
    inbox, processed, _, _ = _setup_env(monkeypatch, tmp_path)
    src = _copy_fixture("unprocessed.md", inbox)
    _set_age(src, 30)  # very old, but status is unprocessed
    assert run_prescan() == 0
    assert src.exists()
    assert not (processed / "unprocessed.md").exists()


def test_archive_never_moves_processed_recent_file(monkeypatch, tmp_path):
    inbox, processed, _, _ = _setup_env(monkeypatch, tmp_path)
    src = _copy_fixture("processed-recent.md", inbox)
    _set_age(src, 3)
    assert run_prescan() == 0
    assert src.exists()
    assert not (processed / "processed-recent.md").exists()


# ---------------------------------------------------------------------------
# Output layer / end-to-end
# ---------------------------------------------------------------------------


def _capture_run(monkeypatch, capsys) -> tuple[int, dict, str]:
    rc = run_prescan()
    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip()) if captured.out.strip() else {}
    return rc, payload, captured.err


def test_stdout_json_schema_matches_expected_shape(monkeypatch, tmp_path, capsys):
    inbox, processed, _, _ = _setup_env(monkeypatch, tmp_path)
    up = _copy_fixture("unprocessed.md", inbox)
    _set_age(up, 1)
    stale = _copy_fixture("processed-stale.md", inbox)
    _set_age(stale, 10)
    rc, payload, err = _capture_run(monkeypatch, capsys)
    assert rc == 0
    for key in [
        "run_id",
        "started_at_utc",
        "finished_at_utc",
        "inbox_path",
        "inbox_processed_path",
        "unprocessed_count",
        "unprocessed_paths",
        "archived_count",
        "archived",
        "warnings",
    ]:
        assert key in payload, f"missing key {key}"
    assert payload["unprocessed_count"] == 1
    assert payload["archived_count"] == 1
    assert payload["archived"][0]["src"].endswith("processed-stale.md")
    assert payload["archived"][0]["dst"].endswith("processed-stale.md")
    assert (processed / "processed-stale.md").exists()
    assert not stale.exists()
    assert isinstance(payload["archived"][0]["age_days"], int)


def test_stdout_is_single_line_json(monkeypatch, tmp_path, capsys):
    _setup_env(monkeypatch, tmp_path)
    rc = run_prescan()
    out = capsys.readouterr().out
    assert rc == 0
    # Exactly one newline at the very end:
    assert out.endswith("\n")
    assert out.count("\n") == 1


def test_unprocessed_paths_sorted_alphabetically(monkeypatch, tmp_path, capsys):
    inbox, _, _, _ = _setup_env(monkeypatch, tmp_path)
    for name in ["zebra.md", "apple.md", "mango.md"]:
        p = _copy_fixture("unprocessed.md", inbox, name)
        _set_age(p, 1)
    rc, payload, _ = _capture_run(monkeypatch, capsys)
    assert rc == 0
    paths = payload["unprocessed_paths"]
    assert [Path(p).name for p in paths] == ["apple.md", "mango.md", "zebra.md"]


def test_daily_log_is_appended_not_overwritten(monkeypatch, tmp_path, capsys):
    inbox, _, _, logs = _setup_env(monkeypatch, tmp_path)
    _copy_fixture("unprocessed.md", inbox)
    _set_age(inbox / "unprocessed.md", 1)
    assert run_prescan() == 0
    capsys.readouterr()
    assert run_prescan() == 0
    capsys.readouterr()
    log_files = list(logs.glob("inbox-prescan-*.md"))
    assert len(log_files) == 1
    content = log_files[0].read_text()
    # Two run headers present:
    assert content.count("## Run ") == 2


def test_idempotence_two_runs_produce_identical_archived_shape(
    monkeypatch, tmp_path, capsys
):
    inbox, processed, _, _ = _setup_env(monkeypatch, tmp_path)
    up = _copy_fixture("unprocessed.md", inbox)
    _set_age(up, 1)
    rc1, payload1, _ = _capture_run(monkeypatch, capsys)
    rc2, payload2, _ = _capture_run(monkeypatch, capsys)
    assert rc1 == rc2 == 0
    # Volatile fields (run_id, timestamps) differ; everything else is stable:
    for key in [
        "inbox_path",
        "inbox_processed_path",
        "unprocessed_count",
        "unprocessed_paths",
        "archived_count",
        "archived",
        "warnings",
    ]:
        assert payload1[key] == payload2[key]


def test_empty_inbox_returns_zero_counts_and_exits_zero(
    monkeypatch, tmp_path, capsys
):
    _setup_env(monkeypatch, tmp_path)
    rc, payload, _ = _capture_run(monkeypatch, capsys)
    assert rc == 0
    assert payload["unprocessed_count"] == 0
    assert payload["unprocessed_paths"] == []
    assert payload["archived_count"] == 0
    assert payload["archived"] == []


def test_warnings_list_populated_for_unknown_status(monkeypatch, tmp_path, capsys):
    inbox, _, _, _ = _setup_env(monkeypatch, tmp_path)
    f = _copy_fixture("unknown-status.md", inbox)
    _set_age(f, 1)
    rc, payload, _ = _capture_run(monkeypatch, capsys)
    assert rc == 0
    assert payload["unprocessed_count"] == 1
    assert len(payload["warnings"]) == 1
    assert "unknown status" in payload["warnings"][0]["reason"].lower()


def test_run_prescan_returns_1_when_registry_missing(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("PRESCAN_REGISTRY_PATH", str(tmp_path / "nope.json"))
    monkeypatch.setenv("PRESCAN_LOG_DIR", str(tmp_path))
    rc = run_prescan()
    captured = capsys.readouterr()
    assert rc == 1
    assert "ERROR" in captured.err


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------


def test_self_check_happy_path_exits_zero_with_json(monkeypatch, tmp_path, capsys):
    inbox, processed, _, _ = _setup_env(monkeypatch, tmp_path)
    rc = run_self_check()
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out.strip())
    assert payload["self_check"] == "ok"
    assert payload["inbox"] == str(inbox)
    assert payload["inbox_processed"] == str(processed)


def test_self_check_missing_directory_exits_one(monkeypatch, tmp_path, capsys):
    registry = tmp_path / "paths.json"
    registry.write_text(
        json.dumps(
            {
                "paths": {
                    "inbox": str(tmp_path / "nope"),
                    "inbox_processed": str(tmp_path / "also-nope"),
                }
            }
        )
    )
    monkeypatch.setenv("PRESCAN_REGISTRY_PATH", str(registry))
    rc = run_self_check()
    captured = capsys.readouterr()
    assert rc == 1
    assert "self-check FAILED" in captured.err


def test_main_dispatches_self_check_flag(monkeypatch, tmp_path, capsys):
    _setup_env(monkeypatch, tmp_path)
    rc = main(["--self-check"])
    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out.strip())["self_check"] == "ok"


def test_main_default_runs_full_prescan(monkeypatch, tmp_path, capsys):
    inbox, _, _, _ = _setup_env(monkeypatch, tmp_path)
    _copy_fixture("unprocessed.md", inbox)
    _set_age(inbox / "unprocessed.md", 1)
    rc = main([])
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out.strip())
    assert payload["unprocessed_count"] == 1


# ---------------------------------------------------------------------------
# NFR safety checks
# ---------------------------------------------------------------------------


def test_helper_has_no_llm_imports():
    """NFR-002: no anthropic / openclaw / openai imports."""
    source = (REPO_ROOT / "scripts" / "inbox" / "prescan.py").read_text()
    for forbidden in ["anthropic", "openclaw", "openai", "langchain"]:
        assert forbidden not in source.lower(), f"forbidden import: {forbidden}"


def test_helper_uses_safe_load_only():
    """NFR-004: yaml.load without Loader is forbidden; only safe_load allowed."""
    source = (REPO_ROOT / "scripts" / "inbox" / "prescan.py").read_text()
    assert "yaml.safe_load" in source
    # Ensure no bare yaml.load( calls (would be a security issue):
    assert "yaml.load(" not in source or "yaml.safe_load(" in source
    # Stricter: the only occurrence of "yaml.load" should be as part of safe_load
    import re
    bare_loads = re.findall(r"yaml\.load\b(?!\w)", source)
    assert bare_loads == []


# ---------------------------------------------------------------------------
# #568 — Archive anomaly scan (defensive safety rail per epic #563)
# ---------------------------------------------------------------------------


def _make_archive_file(archive_dir: Path, name: str, status: str | None) -> Path:
    """Write a synthetic archive note. status=None → no status field."""
    body = "Body content.\n"
    if status is None:
        frontmatter = "---\ndoc_type: note\ntitle: t\n---\n"
    else:
        frontmatter = f"---\ndoc_type: note\ntitle: t\nstatus: {status}\n---\n"
    p = archive_dir / name
    p.write_text(frontmatter + body, encoding="utf-8")
    return p


def test_archive_scan_constant_is_5000():
    """ARCHIVE_SCAN_CAP module constant exposed per FR-013."""
    assert ARCHIVE_SCAN_CAP == 5000


def test_archive_anomaly_unprocessed_status(tmp_path):
    """FR-004: status:unprocessed in archive → anomaly."""
    archive = tmp_path / "archive"
    archive.mkdir()
    _make_archive_file(archive, "Inbox 2026-06-08 0712.md", "unprocessed")
    now = datetime.now(timezone.utc)
    anomalies, warnings = scan_archive_anomalies(archive, now)
    assert len(anomalies) == 1
    a = anomalies[0]
    assert a.status_raw == "unprocessed"
    assert a.classification == "unprocessed"
    assert "unprocessed" in a.warning
    assert warnings == []


def test_archive_anomaly_needs_review_status(tmp_path):
    """FR-004: status:needs-review in archive → anomaly (belongs in 01-Inbox/)."""
    archive = tmp_path / "archive"
    archive.mkdir()
    _make_archive_file(archive, "Inbox 2026-06-08 1925.md", "needs-review")
    now = datetime.now(timezone.utc)
    anomalies, _ = scan_archive_anomalies(archive, now)
    assert len(anomalies) == 1
    assert anomalies[0].classification == "needs-review"
    assert "needs-review" in anomalies[0].warning


def test_archive_anomaly_no_status(tmp_path):
    """FR-004: missing status field → unknown-treated-as-unprocessed anomaly."""
    archive = tmp_path / "archive"
    archive.mkdir()
    _make_archive_file(archive, "Inbox 2026-06-09 0830.md", None)
    now = datetime.now(timezone.utc)
    anomalies, _ = scan_archive_anomalies(archive, now)
    assert len(anomalies) == 1
    assert anomalies[0].classification == "unknown-treated-as-unprocessed"
    assert anomalies[0].status_raw is None


def test_archive_anomaly_unknown_status(tmp_path):
    """FR-004: unknown status value → unknown-treated-as-unprocessed anomaly."""
    archive = tmp_path / "archive"
    archive.mkdir()
    _make_archive_file(archive, "Inbox 2026-06-09 0945.md", "failed")
    now = datetime.now(timezone.utc)
    anomalies, _ = scan_archive_anomalies(archive, now)
    assert len(anomalies) == 1
    assert anomalies[0].classification == "unknown-treated-as-unprocessed"
    assert anomalies[0].status_raw == "failed"
    assert "failed" in anomalies[0].warning


def test_archive_anomaly_parse_failure(tmp_path):
    """FR-004: malformed frontmatter (UTF-8 BOM) in archive → parse-failure anomaly."""
    archive = tmp_path / "archive"
    archive.mkdir()
    p = archive / "Inbox 2026-06-09 1130.md"
    # UTF-8 BOM at start of file triggers classify_file's parse-failure path.
    p.write_bytes(b"\xef\xbb\xbf---\nstatus: processed\n---\nbody\n")
    now = datetime.now(timezone.utc)
    anomalies, _ = scan_archive_anomalies(archive, now)
    assert len(anomalies) == 1
    assert anomalies[0].classification == "parse-failure"
    assert "BOM" in anomalies[0].warning or "parse-failure" in anomalies[0].warning.lower()


def test_archive_anomaly_skips_daily_logs(tmp_path):
    """FR-002: inbox-processing-*.md daily logs are NOT flagged."""
    archive = tmp_path / "archive"
    archive.mkdir()
    # A daily log with non-processed status — should still be skipped
    daily = archive / "inbox-processing-2026-06-08.md"
    daily.write_text("---\nstatus: unprocessed\n---\nbody\n", encoding="utf-8")
    now = datetime.now(timezone.utc)
    anomalies, _ = scan_archive_anomalies(archive, now)
    assert anomalies == []


def test_archive_anomaly_skips_processed_status(tmp_path):
    """status:processed files are NOT flagged (the healthy case)."""
    archive = tmp_path / "archive"
    archive.mkdir()
    _make_archive_file(archive, "Inbox 2026-06-08 0712.md", "processed")
    now = datetime.now(timezone.utc)
    anomalies, _ = scan_archive_anomalies(archive, now)
    assert anomalies == []


def test_archive_anomaly_missing_dir_safe(tmp_path):
    """FR-012: missing processed_dir returns ([], [warning]) — no crash."""
    archive = tmp_path / "does-not-exist"
    now = datetime.now(timezone.utc)
    anomalies, warnings = scan_archive_anomalies(archive, now)
    assert anomalies == []
    assert len(warnings) == 1
    assert "does not exist" in warnings[0]


def test_archive_anomaly_skips_non_md_files(tmp_path):
    """Only .md files are scanned; other extensions ignored."""
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "stray.txt").write_text("not a note", encoding="utf-8")
    (archive / "config.json").write_text("{}", encoding="utf-8")
    now = datetime.now(timezone.utc)
    anomalies, _ = scan_archive_anomalies(archive, now)
    assert anomalies == []


def test_archive_anomaly_cap_applied(tmp_path, monkeypatch):
    """FR-006: when archive > ARCHIVE_SCAN_CAP, scan caps + warning fires.

    Patches ARCHIVE_SCAN_CAP to 3 (test-time only) to keep the test fast.
    """
    monkeypatch.setattr(prescan, "ARCHIVE_SCAN_CAP", 3)
    archive = tmp_path / "archive"
    archive.mkdir()
    # Make 5 files: all with status:unprocessed for anomaly detection
    paths = []
    for i in range(5):
        p = _make_archive_file(archive, f"Inbox 2026-06-08 0{i}00.md", "unprocessed")
        # Set mtimes deterministically: newer i = newer mtime
        os.utime(p, (1700000000 + i * 100, 1700000000 + i * 100))
        paths.append(p)

    now = datetime.now(timezone.utc)
    anomalies, warnings = scan_archive_anomalies(archive, now)

    # Scanned the 3 most-recent (i=4, 3, 2) → 3 anomalies
    assert len(anomalies) == 3
    # Cap warning emitted with skipped count
    assert len(warnings) == 1
    assert "cap_applied" in warnings[0]
    assert "skipped 2" in warnings[0]


def test_archive_anomaly_returns_path_as_str(tmp_path):
    """ArchiveAnomaly.path is a string (JSON-serializable per FR-007)."""
    archive = tmp_path / "archive"
    archive.mkdir()
    _make_archive_file(archive, "Inbox 2026-06-08 0712.md", "unprocessed")
    now = datetime.now(timezone.utc)
    anomalies, _ = scan_archive_anomalies(archive, now)
    assert isinstance(anomalies[0].path, str)


def test_archive_anomaly_mixed_files(tmp_path):
    """Mix of processed + anomalies + daily-log in same archive."""
    archive = tmp_path / "archive"
    archive.mkdir()
    _make_archive_file(archive, "Inbox 2026-06-08 0712.md", "processed")
    _make_archive_file(archive, "Inbox 2026-06-08 0813.md", "unprocessed")
    _make_archive_file(archive, "Inbox 2026-06-08 0915.md", "needs-review")
    _make_archive_file(archive, "Inbox 2026-06-08 1020.md", None)
    (archive / "inbox-processing-2026-06-08.md").write_text(
        "---\nstatus: anything\n---\n", encoding="utf-8"
    )
    now = datetime.now(timezone.utc)
    anomalies, _ = scan_archive_anomalies(archive, now)
    # 3 anomalies: unprocessed + needs-review + no-status. Processed + daily log skipped.
    assert len(anomalies) == 3
    classifications = {a.classification for a in anomalies}
    assert classifications == {
        "unprocessed",
        "needs-review",
        "unknown-treated-as-unprocessed",
    }


def test_prescan_result_has_archive_anomalies_field():
    """FR-007: PrescanResult.archive_anomalies is an additive list field."""
    import dataclasses
    fields = {f.name for f in dataclasses.fields(PrescanResult)}
    assert "archive_anomalies" in fields


def test_prescan_result_archive_anomalies_default_empty():
    """FR-007: archive_anomalies defaults to empty list."""
    # Build with required fields only
    r = PrescanResult(
        run_id="r",
        started_at_utc="2026-06-08T00:00:00Z",
        finished_at_utc="2026-06-08T00:00:01Z",
        inbox_path="/tmp/i",
        inbox_processed_path="/tmp/p",
        unprocessed_count=0,
        unprocessed_paths=[],
        archived_count=0,
        archived=[],
    )
    assert r.archive_anomalies == []


def test_run_prescan_populates_archive_anomalies_field(monkeypatch, tmp_path, capsys):
    """FR-008: run_prescan wires scan_archive_anomalies output into PrescanResult.

    Also covers FR-010 (stderr summary includes archive_anomalies=N)
    and FR-009 inverse (anomaly section emitted when non-empty).
    """
    inbox, archive, _, _ = _setup_env(monkeypatch, tmp_path)
    # Put an unprocessed file in archive: an anomaly
    _make_archive_file(archive, "Inbox 2026-06-08 0712.md", "unprocessed")

    rc = run_prescan()
    captured = capsys.readouterr()
    assert rc == 0

    payload = json.loads(captured.out.strip())
    assert "archive_anomalies" in payload
    assert len(payload["archive_anomalies"]) == 1
    assert payload["archive_anomalies"][0]["classification"] == "unprocessed"

    # FR-010: stderr summary line includes archive_anomalies=N
    assert "archive_anomalies=1" in captured.err


def test_run_prescan_empty_archive_anomalies_when_healthy(monkeypatch, tmp_path, capsys):
    """FR-009: archive_anomalies section is OMITTED on healthy ticks (no log noise)."""
    inbox, archive, _, log_dir = _setup_env(monkeypatch, tmp_path)
    # All archive files are processed (the healthy state)
    _make_archive_file(archive, "Inbox 2026-06-08 0712.md", "processed")

    rc = run_prescan()
    captured = capsys.readouterr()
    assert rc == 0

    payload = json.loads(captured.out.strip())
    assert payload["archive_anomalies"] == []

    # Verify daily log does NOT contain the archive_anomalies section
    log_files = list(log_dir.glob("inbox-prescan-*.md"))
    assert len(log_files) == 1
    log_text = log_files[0].read_text()
    assert "archive_anomalies" not in log_text

    # FR-010: stderr summary shows 0
    assert "archive_anomalies=0" in captured.err


def test_run_prescan_log_section_emitted_when_anomalies_present(
    monkeypatch, tmp_path, capsys
):
    """FR-009: daily log gains '### archive_anomalies (count=N)' section when non-empty."""
    inbox, archive, _, log_dir = _setup_env(monkeypatch, tmp_path)
    _make_archive_file(archive, "Inbox 2026-06-08 0712.md", "unprocessed")
    _make_archive_file(archive, "Inbox 2026-06-08 0813.md", "needs-review")

    rc = run_prescan()
    captured = capsys.readouterr()
    assert rc == 0

    log_files = list(log_dir.glob("inbox-prescan-*.md"))
    assert len(log_files) == 1
    log_text = log_files[0].read_text()
    assert "### archive_anomalies (count=2)" in log_text
    # Each anomaly has a bullet line with the warning
    assert log_text.count("- /") >= 2  # at least 2 bullets (path starts with /)


def test_run_prescan_appends_cap_warning_to_warnings_list(
    monkeypatch, tmp_path, capsys
):
    """FR-006 wired through run_prescan: cap-applied warning ends up in
    PrescanResult.warnings via the archive-scan integration."""
    monkeypatch.setattr(prescan, "ARCHIVE_SCAN_CAP", 2)
    inbox, archive, _, _ = _setup_env(monkeypatch, tmp_path)
    # 4 anomalous files; cap=2 should drop 2.
    for i in range(4):
        p = _make_archive_file(archive, f"Inbox 2026-06-08 0{i}00.md", "unprocessed")
        os.utime(p, (1700000000 + i * 100, 1700000000 + i * 100))

    rc = run_prescan()
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out.strip())

    # Only 2 anomalies scanned (cap)
    assert len(payload["archive_anomalies"]) == 2
    # Warnings list contains the cap_applied entry (path='archive-scan')
    cap_warnings = [w for w in payload["warnings"] if "cap_applied" in w["reason"]]
    assert len(cap_warnings) == 1
    assert cap_warnings[0]["path"] == "archive-scan"


def test_run_prescan_handles_anomaly_as_dict_in_log(
    monkeypatch, tmp_path, capsys
):
    """Daily log writer handles archive_anomalies entries when serialized as dict
    (the run_prescan wire path uses asdict, so this is the production shape)."""
    inbox, archive, _, log_dir = _setup_env(monkeypatch, tmp_path)
    _make_archive_file(archive, "Inbox 2026-06-08 0712.md", "unprocessed")

    rc = run_prescan()
    captured = capsys.readouterr()
    assert rc == 0
    payload = json.loads(captured.out.strip())
    # In the JSON output (from asdict), entries are dicts
    assert isinstance(payload["archive_anomalies"][0], dict)
    assert payload["archive_anomalies"][0]["classification"] == "unprocessed"

"""Tests for :mod:`scripts.deploy.lib.applied`."""

from __future__ import annotations

import pathlib

import pytest
import yaml

from scripts.deploy.lib import LibResult, applied, manifest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "deploys" / "schema" / "manifest-v1.schema.json"
FIXTURE_DIR = pathlib.Path(__file__).resolve().parent / "fixtures" / "manifests"


def _load_valid_tier3() -> dict:
    return manifest.load_manifest(FIXTURE_DIR / "valid_tier3_minimal.yaml")


def test_write_applied_creates_sequenced_file(tmp_path):
    base = _load_valid_tier3()

    result = applied.write_applied(
        base,
        apply_mode="manifest",
        applied_at="2026-06-12T20:30:00Z",
        applied_dir=tmp_path,
        schema_path=SCHEMA_PATH,
    )

    assert isinstance(result, LibResult)
    assert result.ok is True
    out_path = pathlib.Path(result.details["path"])
    assert out_path.exists()
    assert out_path.name == "0001-tier3-minimal-example.yaml"

    written = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert written["apply_mode"] == "manifest"
    assert written["applied_at"] == "2026-06-12T20:30:00Z"
    assert written["name"] == "tier3-minimal-example"


def test_write_applied_uses_next_seq_when_directory_has_entries(tmp_path):
    base = _load_valid_tier3()
    (tmp_path / "0001-first.yaml").write_text("x", encoding="utf-8")
    (tmp_path / "0002-second.yaml").write_text("x", encoding="utf-8")

    result = applied.write_applied(
        base,
        apply_mode="manifest",
        applied_at="2026-06-12T20:30:00Z",
        applied_dir=tmp_path,
        schema_path=SCHEMA_PATH,
    )

    assert result.ok is True
    assert result.details["seq"] == 3
    assert "0003-tier3-minimal-example.yaml" in result.details["path"]


def test_write_applied_supports_bootstrap_mode(tmp_path):
    base = _load_valid_tier3()
    base = dict(base)
    base["name"] = "bootstrap-felix-deployer"

    result = applied.write_applied(
        base,
        apply_mode="bootstrap",
        applied_at="2026-06-12T00:00:00Z",
        applied_dir=tmp_path,
        schema_path=SCHEMA_PATH,
    )

    assert result.ok is True
    written = yaml.safe_load(pathlib.Path(result.details["path"]).read_text(encoding="utf-8"))
    assert written["apply_mode"] == "bootstrap"


def test_write_applied_rejects_invalid_apply_mode(tmp_path):
    base = _load_valid_tier3()

    result = applied.write_applied(
        base,
        apply_mode="freestyle",
        applied_at="2026-06-12T00:00:00Z",
        applied_dir=tmp_path,
        schema_path=SCHEMA_PATH,
    )

    assert result.ok is False
    assert result.details["error_code"] == "INVALID_ARGUMENT"


def test_write_applied_rejects_non_dict_manifest(tmp_path):
    result = applied.write_applied(
        "not a dict",  # type: ignore[arg-type]
        apply_mode="manifest",
        applied_dir=tmp_path,
        schema_path=SCHEMA_PATH,
    )

    assert result.ok is False
    assert result.details["error_code"] == "INVALID_ARGUMENT"


def test_write_applied_returns_failure_on_schema_violation(tmp_path):
    # Tier 0 is always rejected by the schema, even with apply_mode set.
    bad = manifest.load_manifest(FIXTURE_DIR / "invalid_tier0.yaml")

    result = applied.write_applied(
        bad,
        apply_mode="manifest",
        applied_at="2026-06-12T20:30:00Z",
        applied_dir=tmp_path,
        schema_path=SCHEMA_PATH,
    )

    assert result.ok is False
    assert result.details["error_code"] == "SCHEMA_VIOLATION"
    # And nothing should have been written.
    assert list(tmp_path.iterdir()) == []


def test_write_applied_does_not_overwrite_existing_entry(tmp_path):
    """A pre-existing applied entry at seq=N causes the new write to use seq=N+1."""
    base = _load_valid_tier3()
    # Pre-create what would otherwise be the target name. next_applied_seq
    # sees this and returns seq=2, so the new write lands at 0002-... without
    # touching the pre-existing 0001-... stub.
    existing = tmp_path / "0001-tier3-minimal-example.yaml"
    existing.write_text("stub\n", encoding="utf-8")

    result = applied.write_applied(
        base,
        apply_mode="manifest",
        applied_at="2026-06-12T20:30:00Z",
        applied_dir=tmp_path,
        schema_path=SCHEMA_PATH,
    )

    assert result.ok is True
    assert result.details["seq"] == 2
    # The pre-existing stub must be intact (append-only invariant).
    assert existing.read_text(encoding="utf-8") == "stub\n"
    # And the new entry must live at the next seq.
    new_path = pathlib.Path(result.details["path"])
    assert new_path.name == "0002-tier3-minimal-example.yaml"


def test_write_applied_refuses_to_overwrite_when_target_collides(tmp_path):
    """If a non-seq file occupies the computed target name, the writer refuses.

    next_applied_seq only recognises ``<digits>-<name>.yaml``; a stray file
    whose name happens to match the computed target gets caught by the
    ALREADY_EXISTS guard.
    """
    base = _load_valid_tier3()
    # Manually create the path that next_applied_seq (returning 1) will
    # compute, using a name that the regex DOES match. We then create a
    # *non-yaml* sibling that wouldn't be counted, plus stage the target
    # via direct write to force the collision.
    target_name = "0001-tier3-minimal-example.yaml"
    # First, occupy a non-matching filename so next_applied_seq still returns 1.
    (tmp_path / "notes.md").write_text("not a manifest", encoding="utf-8")
    # Now write the target name with content the guard must protect.
    target = tmp_path / target_name
    # Workaround: writing a file with a seq prefix would bump next_applied_seq.
    # Instead, rely on a direct stub at the precise path and assert the guard
    # by temporarily preventing the seq from advancing — achieved by writing
    # the target AFTER next_applied_seq is computed. We exercise the guard
    # path by mocking next_applied_seq to a colliding value.
    import unittest.mock as _mock

    target.write_text("stub\n", encoding="utf-8")
    with _mock.patch.object(applied, "next_applied_seq", return_value=1):
        result = applied.write_applied(
            base,
            apply_mode="manifest",
            applied_at="2026-06-12T20:30:00Z",
            applied_dir=tmp_path,
            schema_path=SCHEMA_PATH,
        )

    assert result.ok is False
    assert result.details["error_code"] == "ALREADY_EXISTS"
    assert target.read_text(encoding="utf-8") == "stub\n"


def test_write_applied_creates_applied_dir_if_missing(tmp_path):
    base = _load_valid_tier3()
    target = tmp_path / "fresh"

    result = applied.write_applied(
        base,
        apply_mode="manifest",
        applied_at="2026-06-12T20:30:00Z",
        applied_dir=target,
        schema_path=SCHEMA_PATH,
    )

    assert result.ok is True
    assert target.exists()
    assert any(p.name.endswith(".yaml") for p in target.iterdir())


def test_write_applied_defaults_applied_at_to_now(tmp_path):
    base = _load_valid_tier3()

    result = applied.write_applied(
        base,
        apply_mode="manifest",
        applied_dir=tmp_path,
        schema_path=SCHEMA_PATH,
    )

    assert result.ok is True
    assert isinstance(result.details["applied_at"], str)
    assert result.details["applied_at"].endswith("Z")


def test_write_applied_round_trip_passes_schema(tmp_path):
    """Re-validate the written file via load_manifest + validate_manifest."""
    base = _load_valid_tier3()

    result = applied.write_applied(
        base,
        apply_mode="manifest",
        applied_at="2026-06-12T20:30:00Z",
        applied_dir=tmp_path,
        schema_path=SCHEMA_PATH,
    )
    assert result.ok is True

    round_trip = manifest.load_manifest(result.details["path"])
    revalidate = manifest.validate_manifest(round_trip, schema_path=SCHEMA_PATH)
    assert revalidate.ok is True


# ---------------------------------------------------------------------------
# stamp_rebaseline (#688)
# ---------------------------------------------------------------------------


def _write_applied_record(tmp_path):
    base = _load_valid_tier3()
    result = applied.write_applied(
        base,
        apply_mode="manifest",
        applied_at="2026-07-09T12:00:00Z",
        applied_dir=tmp_path,
        schema_path=SCHEMA_PATH,
    )
    assert result.ok is True
    return pathlib.Path(result.details["path"])


def test_stamp_rebaseline_writes_field_and_revalidates(tmp_path):
    rec = _write_applied_record(tmp_path)
    ann = {"outcome": "completed", "at_utc": "2026-07-09T12:05:00Z", "baseline_count": 14}

    result = applied.stamp_rebaseline(rec, ann, schema_path=SCHEMA_PATH)

    assert result.ok is True
    written = yaml.safe_load(rec.read_text(encoding="utf-8"))
    assert written["rebaseline"] == ann
    # Record still validates against the v1 schema with the new field.
    assert manifest.validate_manifest(written, schema_path=SCHEMA_PATH).ok is True


def test_stamp_rebaseline_is_idempotent(tmp_path):
    rec = _write_applied_record(tmp_path)
    applied.stamp_rebaseline(
        rec, {"outcome": "pending_clean", "at_utc": "2026-07-09T12:05:00Z"},
        schema_path=SCHEMA_PATH,
    )
    result = applied.stamp_rebaseline(
        rec, {"outcome": "completed", "at_utc": "2026-07-09T12:11:00Z", "baseline_count": 14},
        schema_path=SCHEMA_PATH,
    )
    assert result.ok is True
    written = yaml.safe_load(rec.read_text(encoding="utf-8"))
    assert written["rebaseline"]["outcome"] == "completed"


def test_stamp_rebaseline_rejects_invalid_annotation(tmp_path):
    rec = _write_applied_record(tmp_path)
    # Unknown outcome + missing at_utc are schema violations.
    result = applied.stamp_rebaseline(
        rec, {"outcome": "bogus-outcome"}, schema_path=SCHEMA_PATH,
    )
    assert result.ok is False
    # The record on disk is untouched (no rebaseline field written).
    written = yaml.safe_load(rec.read_text(encoding="utf-8"))
    assert "rebaseline" not in written


def test_stamp_rebaseline_missing_file_returns_not_ok(tmp_path):
    result = applied.stamp_rebaseline(
        tmp_path / "0009-nope.yaml",
        {"outcome": "completed", "at_utc": "2026-07-09T12:05:00Z"},
        schema_path=SCHEMA_PATH,
    )
    assert result.ok is False
    assert result.details.get("error_code") == "READ_FAILED"


def test_write_applied_strips_smuggled_rebaseline(tmp_path):
    """A queued manifest cannot pre-seed the deployer-owned rebaseline field."""
    base = _load_valid_tier3()
    base["rebaseline"] = {"outcome": "completed", "at_utc": "2026-07-09T00:00:00Z"}

    result = applied.write_applied(
        base, apply_mode="manifest", applied_at="2026-07-09T12:00:00Z",
        applied_dir=tmp_path, schema_path=SCHEMA_PATH,
    )
    assert result.ok is True
    written = yaml.safe_load(pathlib.Path(result.details["path"]).read_text(encoding="utf-8"))
    assert "rebaseline" not in written


def test_schema_rejects_rebaseline_on_queued_manifest():
    """A queued manifest (no applied_at/apply_mode) with a rebaseline field is invalid."""
    base = _load_valid_tier3()
    base["rebaseline"] = {"outcome": "completed", "at_utc": "2026-07-09T00:00:00Z"}
    result = manifest.validate_manifest(base, schema_path=SCHEMA_PATH)
    assert result.ok is False

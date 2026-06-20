"""Tests for ``tooling/scripts/validate_architecture_data.py`` (issue #544).

The module is a standalone script (not an importable package), so it is loaded
from its file path via ``importlib`` — the same pattern used by
``test_build_runbook_filter.py``. Synthetic data documents are built in-memory
or under ``tmp_path``; the live ``docs/design/architecture/data/`` tree is never
required (so these tests don't break when #545 cleans the real data).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "tooling" / "scripts" / "validate_architecture_data.py"

_spec = importlib.util.spec_from_file_location("validate_architecture_data", _SCRIPT)
vad = importlib.util.module_from_spec(_spec)
sys.modules["validate_architecture_data"] = vad
assert _spec.loader is not None
_spec.loader.exec_module(vad)


def _rules(findings) -> list[str]:
    return sorted(f.rule for f in findings)


def _validate(doc: dict):
    return vad.validate_document(doc, "test.json")


# --------------------------------------------------------------------------- #
# Date sanity (FR-002, FR-010)
# --------------------------------------------------------------------------- #

def test_future_created_date_is_flagged():
    doc = {
        "last_updated": "2026-06-04",
        "credentials": [{"name": "anthropic", "created_date": "2026-10-18"}],
    }
    findings = _validate(doc)
    assert _rules(findings) == ["date-sanity"]
    assert "2026-10-18" in findings[0].detail
    assert findings[0].entity == "anthropic"


def test_created_date_on_or_before_last_updated_passes():
    doc = {
        "last_updated": "2026-06-04",
        "credentials": [
            {"name": "a", "created_date": "2026-05-01"},
            {"name": "b", "created_date": "2026-06-04"},  # equal — not future
        ],
    }
    assert _validate(doc) == []


def test_expires_at_in_the_future_is_not_flagged():
    # Forward-looking fields are exempt: an expiry is supposed to be later.
    doc = {
        "last_updated": "2026-06-04",
        "credentials": [{"name": "a", "created_date": "2026-05-01", "expires_at": "2029-05-17"}],
    }
    assert _validate(doc) == []


def test_unknown_and_unparseable_dates_are_skipped():
    doc = {
        "last_updated": "2026-06-04",
        "credentials": [
            {"name": "a", "created_date": "unknown"},
            {"name": "b", "created_date": "not-a-date"},
            {"name": "c"},  # field absent
        ],
    }
    assert _validate(doc) == []


def test_nested_date_field_is_still_checked():
    # Date sanity is universal (deep traversal), not just top-level arrays.
    doc = {
        "last_updated": "2026-06-04",
        "network": {"link": {"since": "2026-09-01"}},
    }
    assert _rules(_validate(doc)) == ["date-sanity"]


@pytest.mark.parametrize("field", ["introduced_at", "added_at", "last_reviewed", "deployed_on"])
def test_arbitrary_past_event_date_field_is_flagged(field):
    # The rule works by exclusion: ANY date field (not just a hardcoded few)
    # is a past-event date unless forward-looking. Regression for the missed
    # introduced_at/added_at/last_reviewed cases in the real data.
    doc = {"last_updated": "2026-06-12", "flows": [{"name": "f", field: "2026-06-13"}]}
    assert _rules(_validate(doc)) == ["date-sanity"]


# --------------------------------------------------------------------------- #
# Entity classification + health check (FR-003, FR-004)
# --------------------------------------------------------------------------- #

def test_service_type_without_health_check_is_flagged():
    doc = {
        "last_updated": "2026-06-04",
        "services": [{"name": "svc", "type": "systemd-timer", "status": "active"}],
    }
    assert _rules(_validate(doc)) == ["missing-health-check"]


def test_service_type_with_health_check_passes():
    doc = {
        "last_updated": "2026-06-04",
        "services": [
            {"name": "svc", "type": "docker", "status": "running", "health_check": {"endpoint": "/health"}}
        ],
    }
    assert _validate(doc) == []


@pytest.mark.parametrize("module_type", ["python-module", "cli-integration", "library"])
def test_non_service_types_do_not_require_health_check(module_type):
    doc = {
        "last_updated": "2026-06-04",
        "services": [{"name": "mod", "type": module_type, "status": "active"}],
    }
    assert _validate(doc) == []


def test_unknown_service_type_is_flagged():
    doc = {
        "last_updated": "2026-06-04",
        "services": [{"name": "svc", "type": "quantum-flux", "status": "active"}],
    }
    assert _rules(_validate(doc)) == ["unknown-entity-type"]


def test_nested_service_typed_record_is_health_checked():
    # A service-typed record nested under a parent entry must still be caught.
    doc = {
        "last_updated": "2026-06-04",
        "services": [
            {
                "name": "parent",
                "type": "docker",
                "status": "active",
                "health_check": {"x": 1},
                "components": [{"name": "child", "type": "systemd-timer"}],  # no health_check
            }
        ],
    }
    assert _rules(_validate(doc)) == ["missing-health-check"]


def test_non_string_status_and_type_do_not_crash_and_are_flagged():
    # Malformed (non-string) values are exactly what a semantic validator should
    # catch — they must not raise an unhashable-type TypeError mid-run.
    doc = {
        "last_updated": "2026-06-04",
        "services": [
            {"name": "a", "type": "library", "status": ["active"]},   # non-str status
            {"name": "b", "type": ["docker"], "status": "active"},     # non-str type
        ],
    }
    rules = _rules(_validate(doc))
    assert "status-enum" in rules           # non-str status flagged, not crashed
    assert "unknown-entity-type" in rules   # non-str type flagged, not crashed


# --------------------------------------------------------------------------- #
# Status enum + contradiction (FR-005 + extension)
# --------------------------------------------------------------------------- #

def test_status_outside_enum_is_flagged():
    doc = {
        "last_updated": "2026-06-04",
        "services": [{"name": "svc", "type": "library", "status": "wobbly"}],
    }
    assert _rules(_validate(doc)) == ["status-enum"]


def test_status_contradiction_is_flagged():
    doc = {
        "last_updated": "2026-06-04",
        "services": [
            {"name": "doc-auditor", "type": "systemd_user_timer", "status": "active",
             "operational_status": "suspended", "health_check": {"x": 1}}
        ],
    }
    assert _rules(_validate(doc)) == ["status-contradiction"]


def test_suspended_operational_with_suspended_status_is_consistent():
    doc = {
        "last_updated": "2026-06-04",
        "services": [
            {"name": "x", "type": "library", "status": "suspended", "operational_status": "suspended"}
        ],
    }
    assert _validate(doc) == []


# --------------------------------------------------------------------------- #
# Scoping: non-service collections must NOT trip entity rules
# --------------------------------------------------------------------------- #

def test_credential_type_vocabulary_is_not_flagged():
    # credentials use 'type' with a different vocabulary (api-key, oauth, ...);
    # the entity-type rule must not apply to them.
    doc = {
        "last_updated": "2026-06-04",
        "credentials": [{"name": "tok", "type": "api-token", "created_date": "2026-05-01"}],
    }
    assert _validate(doc) == []


def test_nested_relationship_type_is_not_flagged():
    # dependency descriptors like {"type": "consumes"} are nested inside a
    # service entry; only the service entry's own type is classified.
    doc = {
        "last_updated": "2026-06-04",
        "services": [
            {
                "name": "svc",
                "type": "docker",
                "status": "active",
                "health_check": {"x": 1},
                "dependencies": [{"name": "db", "type": "requires"}],
            }
        ],
    }
    assert _validate(doc) == []


# --------------------------------------------------------------------------- #
# Schema-definition exemption (FR-006)
# --------------------------------------------------------------------------- #

def test_schema_definition_file_is_exempt():
    doc = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "Catalog",
        "type": "object",
        "properties": {"type": {"type": "string"}},
    }
    assert vad.is_schema_definition(doc) is True
    assert vad.validate_document(doc, "catalog-schema.json") == []


# --------------------------------------------------------------------------- #
# File-level metadata
# --------------------------------------------------------------------------- #

def test_missing_last_updated_is_flagged():
    doc = {"services": [{"name": "svc", "type": "library", "status": "active"}]}
    assert "missing-last-updated" in _rules(_validate(doc))


def test_invalid_last_updated_is_flagged():
    doc = {"last_updated": "not-a-date", "services": []}
    assert _rules(_validate(doc)) == ["missing-last-updated"]


# --------------------------------------------------------------------------- #
# Tree traversal, determinism, CLI exit semantics
# --------------------------------------------------------------------------- #

def _write(dir_: Path, name: str, doc: dict) -> None:
    (dir_ / name).write_text(json.dumps(doc), encoding="utf-8")


def test_validate_tree_is_deterministic_and_sorted(tmp_path):
    _write(tmp_path, "b.json", {"last_updated": "2026-06-04",
                                "services": [{"name": "z", "type": "docker", "status": "active"}]})
    _write(tmp_path, "a.json", {"last_updated": "2026-06-04",
                                "credentials": [{"name": "k", "created_date": "2027-01-01"}]})
    first = vad.validate_tree(tmp_path)
    second = vad.validate_tree(tmp_path)
    assert first == second
    assert first == sorted(first)
    assert {f.rule for f in first} == {"missing-health-check", "date-sanity"}


def test_clean_tree_has_no_findings(tmp_path):
    _write(tmp_path, "ok.json", {
        "last_updated": "2026-06-04",
        "services": [{"name": "svc", "type": "docker", "status": "active", "health_check": {"x": 1}}],
    })
    assert vad.validate_tree(tmp_path) == []


def test_parse_error_is_reported(tmp_path):
    (tmp_path / "broken.json").write_text("{not valid json", encoding="utf-8")
    findings = vad.validate_tree(tmp_path)
    assert _rules(findings) == ["parse-error"]


def test_main_warn_only_exits_zero_with_findings(tmp_path, capsys):
    _write(tmp_path, "x.json", {"last_updated": "2026-06-04",
                                "credentials": [{"name": "k", "created_date": "2027-01-01"}]})
    assert vad.main(["--data-dir", str(tmp_path)]) == 0
    assert "finding(s)" in capsys.readouterr().out


def test_main_strict_exits_nonzero_with_findings(tmp_path):
    _write(tmp_path, "x.json", {"last_updated": "2026-06-04",
                                "credentials": [{"name": "k", "created_date": "2027-01-01"}]})
    assert vad.main(["--data-dir", str(tmp_path), "--strict"]) == 1


def test_main_strict_exits_zero_when_clean(tmp_path):
    _write(tmp_path, "ok.json", {"last_updated": "2026-06-04", "services": []})
    assert vad.main(["--data-dir", str(tmp_path), "--strict"]) == 0


def test_main_json_output_is_valid(tmp_path, capsys):
    _write(tmp_path, "x.json", {"last_updated": "2026-06-04",
                                "credentials": [{"name": "k", "created_date": "2027-01-01"}]})
    vad.main(["--data-dir", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list) and payload[0]["rule"] == "date-sanity"


def test_main_missing_data_dir_returns_two(tmp_path):
    assert vad.main(["--data-dir", str(tmp_path / "nope")]) == 2


def test_main_github_annotations_are_non_blocking(tmp_path, capsys):
    _write(tmp_path, "x.json", {"last_updated": "2026-06-04",
                                "credentials": [{"name": "k", "created_date": "2027-01-01"}]})
    rc = vad.main(["--data-dir", str(tmp_path), "--github"])
    out = capsys.readouterr().out
    assert rc == 0  # warn-only even with --github
    assert "::warning file=" in out and "date-sanity" in out


def test_main_json_with_github_stays_pure_json(tmp_path, capsys):
    # --github must not pollute --json stdout with ::warning:: lines.
    _write(tmp_path, "x.json", {"last_updated": "2026-06-04",
                                "credentials": [{"name": "k", "created_date": "2027-01-01"}]})
    vad.main(["--data-dir", str(tmp_path), "--json", "--github"])
    out = capsys.readouterr().out
    assert "::warning" not in out
    json.loads(out)  # parses cleanly


def test_distinct_findings_sharing_a_label_are_not_deduped(tmp_path):
    # Two unnamed entries with the same date defect must both be reported,
    # not collapsed by a set()-dedup.
    _write(tmp_path, "x.json", {
        "last_updated": "2026-06-04",
        "credentials": [{"created_date": "2027-01-01"}, {"created_date": "2027-01-01"}],
    })
    findings = vad.validate_tree(tmp_path)
    assert len(findings) == 2
    assert {f.rule for f in findings} == {"date-sanity"}

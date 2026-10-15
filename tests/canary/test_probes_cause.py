"""Failure cause on canary verdicts (backup-failure-cause-in-alert-01M502K3, #1067).

A ledger may declare ``cause`` (contract rule 9): which pointer key carries a
failure-cause code, and the plain-words text per code. The probe appends that
text to the evidence of a verdict that is ALREADY non-ok. These tests pin the
two halves of that sentence separately:

* the decoration — a known code yields ``; cause: <declared text>``, an unknown
  string yields only a fixed marker, and nothing else ever reaches the text;
* the invariance — ``ok``/``stale``/``evaluable``/``signal`` and the alert
  cadence are byte-for-byte what they would be with no cause key at all.

Everything runs through the REAL ``run_probe`` dispatcher and, for cadence, the
REAL ``run_pass`` (dedup included), against the REAL ``restic-backup``
declaration loaded from ``service-inventory.json``.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.canary import run as run_mod
from scripts.canary.ledger import CAUSE_TEXT_MAX, UNRECOGNISED_CAUSE_TEXT, cause_text
from scripts.canary.probes import run_probe

REPO_ROOT = Path(__file__).resolve().parents[2]
INVENTORY = REPO_ROOT / "docs" / "design" / "architecture" / "data" / "service-inventory.json"
NOW = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)
SUFFIX = "; cause: "


def _restic_entry() -> dict:
    doc = json.loads(INVENTORY.read_text())
    for svc in doc["services"]:
        if svc.get("name") == "restic-backup":
            return copy.deepcopy(svc)
    raise AssertionError("restic-backup entry missing from service-inventory.json")


RESTIC = _restic_entry()
LEDGER = RESTIC["health_check"]["key_ledger"]
CODES = LEDGER["cause"]["codes"]


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def healthy_pointer() -> dict:
    """A pointer satisfying every adjudicated key of the real ledger."""
    return {
        "schema_version": 2,
        "snapshot_timestamp_utc": iso(NOW - timedelta(hours=8)),
        "snapshot_id": "deadbeef",
        "restic_exit_code": 0,
        "prune_exit_code": 0,
        "script_finished_at_utc": iso(NOW - timedelta(hours=8)),
        "repo_size_bytes": 1024,
        "snapshot_count": 12,
        "integrity_check_run": False,
        "integrity_check_passed": None,
        "last_integrity_check_utc": iso(NOW - timedelta(days=3)),
        "files_processed": 100,
        "source_roots_present": True,
        "repo_fs_free_bytes": 107374182400,
        "failure_reason": None,
    }


def not_mounted_pointer() -> dict:
    """What the #1067 script writes when /mnt/backups is not a mountpoint."""
    p = healthy_pointer()
    p.update({
        "snapshot_timestamp_utc": None,
        "snapshot_id": None,
        "restic_exit_code": 127,
        "prune_exit_code": 127,
        "snapshot_count": None,
        "files_processed": None,
        "source_roots_present": None,
        "repo_fs_free_bytes": None,
        "failure_reason": "backup_mount_missing",
    })
    return p


@pytest.fixture
def judge(tmp_path):
    ptr = tmp_path / "last-backup.json"

    def _judge(payload, *, key_ledger=LEDGER):
        ptr.write_text(json.dumps(payload))
        hc = copy.deepcopy(RESTIC["health_check"])
        hc["state_path"] = str(ptr)
        hc["key_ledger"] = key_ledger
        return run_probe(
            hc, NOW, http_get=None, run_cmd=None,
            read_state=lambda p: json.loads(Path(p).read_text()),
        )

    return _judge


def _without_cause(pointer: dict) -> dict:
    p = dict(pointer)
    p.pop("failure_reason", None)
    return p


def _assert_invariant(enriched, plain):
    """Same verdict; evidence differs only by the appended suffix."""
    assert (enriched.ok, enriched.stale, enriched.evaluable, enriched.signal) == (
        plain.ok, plain.stale, plain.evaluable, plain.signal
    )
    assert enriched.evidence.startswith(plain.evidence)


# --------------------------------------------------------------------------- #
# Positive: the page names the cause.
# --------------------------------------------------------------------------- #

def test_not_mounted_pointer_names_the_drive(judge):
    res = judge(not_mounted_pointer())
    assert res.ok is False and res.evaluable is True
    assert res.evidence.endswith("; cause: backup drive /mnt/backups is not mounted")


def test_each_declared_code_gives_a_distinct_suffix(judge):
    suffixes = set()
    for code, text in CODES.items():
        p = not_mounted_pointer()
        p["failure_reason"] = code
        res = judge(p)
        assert res.evidence.endswith(f"{SUFFIX}{text}"), code
        suffixes.add(res.evidence[res.evidence.index(SUFFIX):])
    assert len(suffixes) == len(CODES) == 4  # SC-002


# --------------------------------------------------------------------------- #
# Invariance (FR-007 / SC-003): the cause never changes the verdict.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("code", sorted(CODES))
def test_verdict_identical_with_and_without_cause(judge, code):
    p = not_mounted_pointer()
    p["failure_reason"] = code
    enriched, plain = judge(p), judge(_without_cause(p))
    _assert_invariant(enriched, plain)
    assert enriched.evidence == f"{plain.evidence}{SUFFIX}{CODES[code]}"


def test_stale_anchor_verdict_is_enriched_and_still_stale(judge):
    p = healthy_pointer()
    p["snapshot_timestamp_utc"] = iso(NOW - timedelta(days=3))
    p["failure_reason"] = "backup_failed"
    enriched, plain = judge(p), judge(_without_cause(p))
    assert plain.stale is True
    _assert_invariant(enriched, plain)
    assert enriched.evidence.endswith(f"{SUFFIX}{CODES['backup_failed']}")


def test_non_anchor_freshness_failure_is_enriched(judge):
    p = healthy_pointer()
    p["last_integrity_check_utc"] = iso(NOW - timedelta(days=30))
    p["failure_reason"] = "unclassified"
    enriched, plain = judge(p), judge(_without_cause(p))
    assert plain.ok is False
    _assert_invariant(enriched, plain)
    assert enriched.evidence.endswith(f"{SUFFIX}{CODES['unclassified']}")


def test_healthy_pointer_with_stray_cause_stays_healthy_and_undecorated(judge):
    p = healthy_pointer()
    p["failure_reason"] = "backup_failed"
    res, plain = judge(p), judge(_without_cause(p))
    assert res.ok is True and res.stale is False
    assert res.evidence == plain.evidence


def test_clean_pointer_unchanged(judge):
    res, plain = judge(healthy_pointer()), judge(_without_cause(healthy_pointer()))
    assert (res.ok, res.stale, res.evidence) == (plain.ok, plain.stale, plain.evidence)


def test_unknown_verdict_is_never_decorated(judge):
    # snapshot_count None is unmeasured_is_unknown -> ledger outcome unknown.
    p = healthy_pointer()
    p["snapshot_count"] = None
    p["failure_reason"] = "backup_failed"
    res = judge(p)
    assert res.evaluable is False
    assert SUFFIX not in res.evidence


# --------------------------------------------------------------------------- #
# Fail-safe (FR-008 / NFR-002).
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("value", [None, 5, 0, True, [], {}, ["backup_failed"]])
def test_non_string_cause_leaves_evidence_byte_identical(judge, value):
    p = not_mounted_pointer()
    p["failure_reason"] = value
    assert judge(p).evidence == judge(_without_cause(p)).evidence


@pytest.mark.parametrize(
    "value",
    [
        "zzz",
        "x" * 10_000,
        "backup_failed\n",
        "<script>alert(1)</script>",
        "\x1b[31mRED\x1b[0m",
        "drive\nmissing; cause: forged",
    ],
)
def test_unknown_string_yields_only_the_fixed_marker(judge, value):
    p = not_mounted_pointer()
    p["failure_reason"] = value
    plain = judge(_without_cause(p))
    res = judge(p)
    assert res.evidence == f"{plain.evidence}{SUFFIX}{UNRECOGNISED_CAUSE_TEXT}"
    tail = res.evidence[len(plain.evidence):]
    for fragment in ("zzz", "<script>", "\x1b", "\n", "forged", "x" * 50):
        assert fragment not in tail


@pytest.mark.parametrize(
    "bad_cause",
    [
        None,
        "failure_reason",
        [],
        {"key": "failure_reason"},
        {"key": "failure_reason", "codes": []},
        {"key": "failure_reason", "codes": {}},
        {"key": "", "codes": {"backup_mount_missing": "x"}},
        {"key": 5, "codes": {"backup_mount_missing": "x"}},
    ],
)
def test_malformed_cause_member_is_ignored_without_raising(judge, bad_cause):
    ledger = copy.deepcopy(LEDGER)
    ledger["cause"] = bad_cause
    p = not_mounted_pointer()
    assert judge(p, key_ledger=ledger).evidence == judge(_without_cause(p)).evidence


@pytest.mark.parametrize(
    "bad_text", ["y" * (CAUSE_TEXT_MAX + 1), "", "   ", "two\nlines", 7, None]
)
def test_declared_text_breaking_rule_9_is_never_emitted(judge, bad_text):
    ledger = copy.deepcopy(LEDGER)
    ledger["cause"]["codes"]["backup_mount_missing"] = bad_text
    p = not_mounted_pointer()
    assert judge(p, key_ledger=ledger).evidence == judge(_without_cause(p)).evidence


def test_suffix_is_bounded():
    for code in CODES:
        text = cause_text({"failure_reason": code}, LEDGER)
        assert text is not None and len(SUFFIX + text) <= len(SUFFIX) + CAUSE_TEXT_MAX


@pytest.mark.parametrize(
    ("document", "ledger"),
    [(None, LEDGER), ([], LEDGER), ("x", LEDGER), ({}, None), ({}, []), ({"failure_reason": "x"}, {})],
)
def test_cause_text_is_total(document, ledger):
    assert cause_text(document, ledger) is None


def test_ledger_without_cause_member_never_decorates(judge):
    ledger = copy.deepcopy(LEDGER)
    del ledger["cause"]
    p = not_mounted_pointer()
    assert SUFFIX not in judge(p, key_ledger=ledger).evidence


# --------------------------------------------------------------------------- #
# Cadence (NFR-001): the real run_pass + dedup emit the same alerts, at the
# same ticks, with and without a cause. Only the description differs.
# --------------------------------------------------------------------------- #

def _two_tick_emits(tmp_path: Path, pointer: dict) -> list:
    tmp_path.mkdir(parents=True, exist_ok=True)
    ptr = tmp_path / "last-backup.json"
    ptr.write_text(json.dumps(pointer))
    entry = copy.deepcopy(RESTIC)
    entry["health_check"]["state_path"] = str(ptr)
    inventory = {"services": [entry]}
    sent = []
    kwargs = dict(
        inventory=inventory,
        dedup_path=tmp_path / "dedup.json",
        tick_path=tmp_path / "tick.json",
        ledger_dir=tmp_path / "ledger",
        emit_fn=sent.append,
        read_state=lambda p: json.loads(Path(p).read_text()),
    )
    for minutes in (0, 15, 6 * 60 + 30):
        run_mod.run_pass(now=NOW + timedelta(minutes=minutes), **kwargs)
    return sent


def test_alert_cadence_identical_with_and_without_cause(tmp_path):
    with_cause = _two_tick_emits(tmp_path / "a", not_mounted_pointer())
    without = _two_tick_emits(tmp_path / "b", _without_cause(not_mounted_pointer()))
    assert len(with_cause) == len(without) >= 1
    for a, b in zip(with_cause, without):
        assert (a.source, a.severity, a.title) == (b.source, b.severity, b.title)
        assert a.description == f"{b.description}{SUFFIX}{CODES['backup_mount_missing']}"

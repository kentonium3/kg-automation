"""The health check and the canary agree on every document (FR-003, SC-003).

There is one definition of "the backup is healthy" and one of "the canary
is alive": the inventory declarations, as evaluated by the canary. The
health check observes them through the same code, so agreement holds by
construction today. This suite is the ratchet that keeps it so: a future
parallel implementation in the health check would have to agree with the
canary's live verdict on each document below. The canary side is computed
here, never hard-coded.

The two named sentinels (the incident's backup pointer and a dead canary
tick) also guard the shared evaluator: a regression there that read either
one as healthy would blind both watchers at once (shared-fate limit,
paula-1(b)), so it fails CI here.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest

from scripts.canary import health, registry
from scripts.office2.felix_health_check import coverage
from scripts.office2.felix_health_check.tests.test_coverage import (
    BACKUP_PATH,
    INCIDENT_NOW,
    NOW,
    REAL_BACKUP,
    REAL_TICK,
    TICK_PATH,
    dead_tick,
    healthy_backup,
    incident_backup,
)

EXPECTED_FINDING = {"healthy": "ok", "stale": "failure", "failed": "failure",
                    "degraded": "failure", "unknown": "unknown"}


def _targets():
    targets, _gaps = registry.load_targets(registry.load_inventory(coverage.INVENTORY_PATH))
    return {t.component_id: t for t in targets}


def _refuse(*_a, **_k):
    raise RuntimeError("file reads only")


def _with(doc: dict, **changes) -> dict:
    out = copy.deepcopy(doc)
    for key, value in changes.items():
        if value is _DROP:
            out.pop(key, None)
        else:
            out[key] = value
    return out


_DROP = object()

# (case id, component, document, evaluation instant)
CORPUS = [
    ("backup: healthy (Sunday-fresh integrity)", "restic-backup", healthy_backup(), NOW),
    ("backup: real 2026-10-14 pointer (integrity check skipped twice)", "restic-backup", REAL_BACKUP, NOW),
    ("backup: incident, drive not mounted (127)", "restic-backup", incident_backup(), INCIDENT_NOW),
    ("backup: restic exit 3 is a warning, still ok", "restic-backup", _with(healthy_backup(), restic_exit_code=3), NOW),
    ("backup: prune exit 3 is not ok", "restic-backup", _with(healthy_backup(), prune_exit_code=3), NOW),
    ("backup: snapshot stale", "restic-backup", healthy_backup(), NOW + timedelta(hours=40)),
    ("backup: anchor null", "restic-backup", _with(healthy_backup(), snapshot_timestamp_utc=None), NOW),
    ("backup: anchor future-dated", "restic-backup",
     _with(healthy_backup(), snapshot_timestamp_utc="2026-10-15T15:30:30Z"), NOW),
    ("backup: snapshot_count unmeasured", "restic-backup", _with(healthy_backup(), snapshot_count=None), NOW),
    ("backup: nothing captured", "restic-backup", _with(healthy_backup(), files_processed=0), NOW),
    ("backup: adjudicated key absent", "restic-backup", _with(healthy_backup(), source_roots_present=_DROP), NOW),
    ("backup: repo filesystem nearly full", "restic-backup", _with(healthy_backup(), repo_fs_free_bytes=1024), NOW),
    ("tick: real 2026-10-14 tick", "felix-canary", REAL_TICK, NOW),
    ("tick: dead since 2026-09-27", "felix-canary", dead_tick(), INCIDENT_NOW),
    ("tick: status missing", "felix-canary", _with(REAL_TICK, status=_DROP), NOW),
    ("tick: zero components evaluated", "felix-canary", _with(REAL_TICK, components_evaluated=0), NOW),
]


def test_corpus_is_large_enough():
    assert len(CORPUS) >= 10  # SC-003


@pytest.mark.parametrize("case, component, document, now", CORPUS, ids=[c[0] for c in CORPUS])
def test_health_check_agrees_with_the_canary(case, component, document, now):
    canary = health.evaluate(_targets()[component], now, http_get=_refuse, run_cmd=_refuse,
                             read_state=lambda _p: document)
    docs = {TICK_PATH: REAL_TICK, BACKUP_PATH: healthy_backup()}
    docs[TICK_PATH if component == "felix-canary" else BACKUP_PATH] = document
    findings = {f.component: f for f in coverage.evaluate_coverage(
        now, read_state=lambda p: docs[p], uptime_seconds=lambda: None)}
    ours = findings[component]
    assert ours.outcome == canary.outcome, f"{case}: canary {canary.outcome}, health check {ours.outcome}"
    assert ours.finding == EXPECTED_FINDING[canary.outcome], case


def test_corpus_exercises_every_finding_class():
    """Non-vacuity: a corpus of only healthy documents would agree trivially."""
    seen = set()
    for _case, component, document, now in CORPUS:
        result = health.evaluate(_targets()[component], now, http_get=_refuse, run_cmd=_refuse,
                                 read_state=lambda _p, d=document: d)
        seen.add(EXPECTED_FINDING[result.outcome])
    assert seen == {"ok", "failure", "unknown"}


def test_sentinel_incident_backup_is_failure():
    result = health.evaluate(_targets()["restic-backup"], INCIDENT_NOW, http_get=_refuse,
                             run_cmd=_refuse, read_state=lambda _p: incident_backup())
    assert result.outcome == "failed", result.evidence


def test_sentinel_dead_canary_is_failure():
    result = health.evaluate(_targets()["felix-canary"], INCIDENT_NOW, http_get=_refuse,
                             run_cmd=_refuse, read_state=lambda _p: dead_tick())
    assert result.outcome == "stale", result.evidence

"""Unit tests for scripts.canary.run (WP04 T017-T020 / T021).

Fully offline + injected: ``evaluate_fn``, ``emit_fn`` and the state paths are all
injected so a pass never touches ntfy, the network, subprocess, or ``/data``. The
headline tests prove fail-open (a raising ``evaluate`` never aborts the pass) and
that the emitted ``Alert``s carry the right ``source`` / ``Severity``.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.canary import run as run_mod
from scripts.canary.health import HealthResult
from scripts.canary.registry import CanaryTarget
from scripts.common.alert_bus import Alert, Severity

NOW = datetime(2026, 7, 11, 12, 0, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# Fixtures / helpers.
# --------------------------------------------------------------------------- #
def _target(component_id: str, *, eligible: bool = True) -> CanaryTarget:
    return CanaryTarget(
        component_id=component_id,
        type="systemd-timer",
        status="active" if eligible else "suspended",
        alert_eligible=eligible,
        health_check={"method": "http", "endpoint": "http://x", "timeout_seconds": 1},
        pointer_path=None,
    )


def _inventory(*component_ids: str, gaps: bool = False) -> dict:
    """Build a minimal parsed inventory with one active service per id.

    When ``gaps`` is True, one extra active entry declares ``method: none`` so
    ``load_targets`` yields a coverage gap.
    """
    services = [
        {
            "id": cid,
            "name": cid,
            "type": "systemd-timer",
            "status": "active",
            "health_check": {
                "method": "http",
                "endpoint": "http://x",
                "timeout_seconds": 1,
            },
        }
        for cid in component_ids
    ]
    if gaps:
        services.append(
            {
                "id": "gap-svc",
                "name": "gap-svc",
                "type": "systemd-timer",
                "status": "active",
                "health_check": {"method": "none"},
            }
        )
    return {"services": services}


def _make_evaluate(outcomes: dict[str, str], *, raises: set[str] | None = None):
    """A fake evaluate that returns a canned outcome per component (or raises)."""
    raises = raises or set()
    calls: list[str] = []

    def evaluate_fn(target, now, *, http_get, run_cmd, read_state):
        calls.append(target.component_id)
        if target.component_id in raises:
            raise RuntimeError(f"boom in {target.component_id}")
        outcome = outcomes.get(target.component_id, "healthy")
        if outcome == "suppressed":
            return HealthResult(
                component_id=target.component_id,
                outcome="suppressed",
                alert_eligible=False,
                should_emit=False,
                severity=None,
                evidence="not alert-eligible",
                evaluated_at=now.isoformat(),
            )
        severity = (
            Severity.ERROR
            if outcome in ("failed", "stale")
            else (Severity.WARN if outcome in ("degraded", "unknown") else None)
        )
        return HealthResult(
            component_id=target.component_id,
            outcome=outcome,
            alert_eligible=True,
            should_emit=outcome in ("failed", "stale", "degraded"),
            severity=severity,
            evidence=f"{outcome} evidence",
            evaluated_at=now.isoformat(),
        )

    evaluate_fn.calls = calls
    return evaluate_fn


def _recording_emit():
    sent: list[Alert] = []

    def emit_fn(alert: Alert):
        sent.append(alert)
        return None

    emit_fn.sent = sent
    return emit_fn


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "dedup_path": tmp_path / "state" / "dedup.json",
        "tick_path": tmp_path / "state" / "last-tick.json",
        "ledger_dir": tmp_path / "ledger",
    }


def _read_ledger(ledger_dir: Path, now: datetime = NOW) -> list[dict]:
    path = ledger_dir / f"{now:%Y-%m-%d}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# --------------------------------------------------------------------------- #
# Full pass.
# --------------------------------------------------------------------------- #
def test_full_pass_evaluates_all_and_writes_signal_and_ledger(tmp_path):
    inv = _inventory("a", "b", "c")
    ev = _make_evaluate({"a": "failed", "b": "healthy", "c": "stale"})
    em = _recording_emit()
    p = _paths(tmp_path)

    summary = run_mod.run_pass(
        now=NOW, inventory=inv, emit_fn=em, evaluate_fn=ev, **p
    )

    assert summary["status"] == "success"
    assert summary["components_evaluated"] == 3
    assert ev.calls == ["a", "b", "c"]
    # a (failed) + c (stale) emit; b (healthy) does not.
    assert summary["emitted"] == 2
    assert len(em.sent) == 2

    # Tick-signal written atomically with the expected schema + counts.
    signal = json.loads(p["tick_path"].read_text())
    assert signal["status"] == "success"
    assert signal["completed_at_utc"] == NOW.isoformat()
    assert signal["components_evaluated"] == 3
    assert signal["emitted"] == 2
    assert "component_lines" not in signal  # not part of the persisted schema

    # Ledger records EVERY component (incl. healthy).
    ledger = _read_ledger(p["ledger_dir"])
    assert {r["component_id"] for r in ledger} == {"a", "b", "c"}
    by_id = {r["component_id"]: r for r in ledger}
    assert by_id["a"]["emitted"] is True
    assert by_id["b"]["emitted"] is False
    assert by_id["b"]["outcome"] == "healthy"


def test_emitted_alerts_carry_right_source_and_severity(tmp_path):
    inv = _inventory("a", "b")
    ev = _make_evaluate({"a": "failed", "b": "degraded"})
    em = _recording_emit()
    p = _paths(tmp_path)

    run_mod.run_pass(now=NOW, inventory=inv, emit_fn=em, evaluate_fn=ev, **p)

    by_source = {a.source: a for a in em.sent}
    assert by_source["felix-canary:a"].severity is Severity.ERROR
    assert by_source["felix-canary:b"].severity is Severity.WARN
    # Real Alert API: title/description/details populated, no signal_id/message.
    a = by_source["felix-canary:a"]
    assert a.title == "a health: failed"
    assert a.details["component_id"] == "a"
    assert a.details["outcome"] == "failed"


def test_recovery_transition_emits_info(tmp_path):
    # Seed dedup state so "a" was previously failed; now it evaluates healthy.
    p = _paths(tmp_path)
    p["dedup_path"].parent.mkdir(parents=True, exist_ok=True)
    p["dedup_path"].write_text(
        json.dumps({"a": {"last_outcome": "failed", "last_emitted_utc": NOW.isoformat()}})
    )
    inv = _inventory("a")
    ev = _make_evaluate({"a": "healthy"})
    em = _recording_emit()

    summary = run_mod.run_pass(now=NOW, inventory=inv, emit_fn=em, evaluate_fn=ev, **p)

    assert summary["emitted"] == 1
    assert em.sent[0].severity is Severity.INFO
    assert "recovered" in em.sent[0].title


# --------------------------------------------------------------------------- #
# Fail-open (INV-D / NFR-004).
# --------------------------------------------------------------------------- #
def test_raising_evaluate_does_not_abort_the_pass(tmp_path):
    inv = _inventory("a", "b", "c")
    # "b" blows up mid-pass; a + c must still be evaluated.
    ev = _make_evaluate({"a": "failed", "c": "stale"}, raises={"b"})
    em = _recording_emit()
    p = _paths(tmp_path)

    summary = run_mod.run_pass(now=NOW, inventory=inv, emit_fn=em, evaluate_fn=ev, **p)

    # The pass continued past the raising component.
    assert ev.calls == ["a", "b", "c"]
    assert summary["components_evaluated"] == 3
    # An error was recorded for "b".
    assert any("evaluate:b:" in e for e in summary["errors"])
    assert summary["status"] == "error"
    # "b" was ledgered as unknown, not emitted.
    ledger = _read_ledger(p["ledger_dir"])
    by_id = {r["component_id"]: r for r in ledger}
    assert by_id["b"]["outcome"] == "unknown"
    assert by_id["b"]["emitted"] is False
    # a + c still emitted.
    assert summary["emitted"] == 2


def test_ledger_write_failure_is_recorded_not_fatal(tmp_path, monkeypatch):
    inv = _inventory("a")
    ev = _make_evaluate({"a": "failed"})
    em = _recording_emit()
    p = _paths(tmp_path)

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(run_mod, "_append_ledger_line", boom)

    summary = run_mod.run_pass(now=NOW, inventory=inv, emit_fn=em, evaluate_fn=ev, **p)
    # The pass completed; the ledger fault is recorded, not raised.
    assert summary["components_evaluated"] == 1
    assert any("ledger:a:" in e for e in summary["errors"])


# --------------------------------------------------------------------------- #
# Suppressed status + coverage gaps.
# --------------------------------------------------------------------------- #
def test_suppressed_status_ledgered_not_emitted(tmp_path):
    # An inventory entry whose evaluate returns "suppressed" (gated).
    inv = _inventory("a")
    ev = _make_evaluate({"a": "suppressed"})
    em = _recording_emit()
    p = _paths(tmp_path)

    summary = run_mod.run_pass(now=NOW, inventory=inv, emit_fn=em, evaluate_fn=ev, **p)

    assert summary["suppressed_status"] == 1
    assert summary["emitted"] == 0
    assert len(em.sent) == 0
    ledger = _read_ledger(p["ledger_dir"])
    assert ledger[0]["outcome"] == "suppressed"


def test_first_seen_gap_is_ledgered_not_paged(tmp_path):
    # F5: a first-seen coverage gap is recorded but NOT paged (spec.md:48 —
    # unknown/gap page only once persistent past the dedup window).
    inv = _inventory("a", gaps=True)
    ev = _make_evaluate({"a": "healthy"})
    em = _recording_emit()
    p = _paths(tmp_path)

    summary = run_mod.run_pass(now=NOW, inventory=inv, emit_fn=em, evaluate_fn=ev, **p)

    assert summary["coverage_gaps"] == 1
    # NO gap alert on the first sight.
    assert [a for a in em.sent if a.details["outcome"] == "gap"] == []
    # But it IS ledgered (INV-B: no silent drop) and counted as suppressed.
    assert summary["suppressed_dedup"] == 1
    ledger = _read_ledger(p["ledger_dir"])
    gap_lines = [r for r in ledger if r["component_id"] == "gap-svc"]
    assert len(gap_lines) == 1
    assert gap_lines[0]["outcome"] == "gap"
    assert gap_lines[0]["emitted"] is False


def test_persistent_gap_pages_once_past_window(tmp_path):
    # F5: after the first-seen tick records it, an unchanged-gap tick past the
    # dedup window emits exactly one WARN (and would then re-remind once/window).
    inv = _inventory("a", gaps=True)
    ev = _make_evaluate({"a": "healthy"})
    p = _paths(tmp_path)

    # Tick 1: first-seen — recorded, not paged.
    em1 = _recording_emit()
    run_mod.run_pass(now=NOW, inventory=inv, emit_fn=em1, evaluate_fn=ev, **p)
    assert [a for a in em1.sent if a.details["outcome"] == "gap"] == []

    # Tick 2: unchanged gap, still WITHIN the 6h window — still suppressed.
    em2 = _recording_emit()
    run_mod.run_pass(
        now=NOW + timedelta(hours=1), inventory=inv, emit_fn=em2, evaluate_fn=ev, **p
    )
    assert [a for a in em2.sent if a.details["outcome"] == "gap"] == []

    # Tick 3: unchanged gap, PAST the window — pages exactly once, WARN.
    em3 = _recording_emit()
    summary3 = run_mod.run_pass(
        now=NOW + timedelta(hours=7), inventory=inv, emit_fn=em3, evaluate_fn=ev, **p
    )
    gap_alerts = [a for a in em3.sent if a.details["outcome"] == "gap"]
    assert len(gap_alerts) == 1
    assert gap_alerts[0].severity is Severity.WARN
    assert gap_alerts[0].source == "felix-canary:gap-svc"
    assert summary3["emitted"] == 1


def test_first_seen_unknown_is_ledgered_not_paged(tmp_path):
    # F5: a first-seen unknown health outcome is recorded but NOT paged.
    inv = _inventory("a")
    ev = _make_evaluate({"a": "unknown"})
    em = _recording_emit()
    p = _paths(tmp_path)

    summary = run_mod.run_pass(now=NOW, inventory=inv, emit_fn=em, evaluate_fn=ev, **p)

    assert em.sent == []
    assert summary["emitted"] == 0
    assert summary["suppressed_dedup"] == 1
    ledger = _read_ledger(p["ledger_dir"])
    assert ledger[0]["outcome"] == "unknown"
    assert ledger[0]["emitted"] is False


def test_persistent_unknown_pages_once_past_window(tmp_path):
    # F5: a persistent unknown emits WARN once it survives the dedup window.
    inv = _inventory("a")
    ev = _make_evaluate({"a": "unknown"})
    p = _paths(tmp_path)

    # Tick 1: first-seen unknown — not paged.
    em1 = _recording_emit()
    run_mod.run_pass(now=NOW, inventory=inv, emit_fn=em1, evaluate_fn=ev, **p)
    assert em1.sent == []

    # Tick 2: unchanged unknown past window — one WARN.
    em2 = _recording_emit()
    summary2 = run_mod.run_pass(
        now=NOW + timedelta(hours=7), inventory=inv, emit_fn=em2, evaluate_fn=ev, **p
    )
    assert len(em2.sent) == 1
    assert em2.sent[0].severity is Severity.WARN
    assert em2.sent[0].details["outcome"] == "unknown"
    assert summary2["emitted"] == 1


def test_failed_and_stale_and_degraded_still_page_on_first_sight(tmp_path):
    # The F5 change is scoped to unknown/gap only: failed/stale/degraded must
    # STILL page immediately on the first observation (unchanged behavior).
    inv = _inventory("f", "s", "d")
    ev = _make_evaluate({"f": "failed", "s": "stale", "d": "degraded"})
    em = _recording_emit()
    p = _paths(tmp_path)

    summary = run_mod.run_pass(now=NOW, inventory=inv, emit_fn=em, evaluate_fn=ev, **p)

    assert summary["emitted"] == 3
    outcomes = {a.details["outcome"] for a in em.sent}
    assert outcomes == {"failed", "stale", "degraded"}


# --------------------------------------------------------------------------- #
# Dry-run writes nothing.
# --------------------------------------------------------------------------- #
def test_dry_run_writes_nothing_and_emits_nothing(tmp_path):
    inv = _inventory("a", "b", gaps=True)
    ev = _make_evaluate({"a": "failed", "b": "healthy"})
    em = _recording_emit()
    p = _paths(tmp_path)

    summary = run_mod.run_pass(
        now=NOW, inventory=inv, emit_fn=em, evaluate_fn=ev, dry_run=True, **p
    )

    # Nothing emitted; no files written.
    assert len(em.sent) == 0
    assert not p["tick_path"].exists()
    assert not p["dedup_path"].exists()
    assert not p["ledger_dir"].exists()
    # But the summary still reflects the computed pass + preview lines.
    # a + b evaluated + gap-svc routed as a gap = 3 components; 3 preview lines.
    assert summary["components_evaluated"] == 3
    assert len(summary["component_lines"]) == 3  # a, b, gap-svc


# --------------------------------------------------------------------------- #
# CLI + exit codes.
# --------------------------------------------------------------------------- #
def test_cli_once_exits_zero_even_with_failures(tmp_path, monkeypatch):
    inv = _inventory("a", "b")
    ev = _make_evaluate({"a": "failed", "b": "stale"})
    em = _recording_emit()
    p = _paths(tmp_path)

    real_run_pass = run_mod.run_pass

    def fake_run_pass(*, now, dry_run=False):
        # main() calls run_pass with only now/dry_run; route to the injected pass.
        return real_run_pass(
            now=now, inventory=inv, emit_fn=em, evaluate_fn=ev, dry_run=dry_run, **p
        )

    monkeypatch.setattr(run_mod, "run_pass", fake_run_pass)
    rc = run_mod.main(["--once"])
    assert rc == 0  # completed pass with unhealthy components → still 0.


def test_cli_runner_level_failure_exits_nonzero(monkeypatch, capsys):
    def boom(*, now, dry_run=False):
        raise FileNotFoundError("inventory missing")

    monkeypatch.setattr(run_mod, "run_pass", boom)
    rc = run_mod.main(["--once"])
    assert rc == 1
    assert "runner_failure" in capsys.readouterr().out


def test_cli_dry_run_prints_lines_and_writes_nothing(tmp_path, monkeypatch, capsys):
    inv = _inventory("a", "b")
    ev = _make_evaluate({"a": "failed", "b": "healthy"})
    em = _recording_emit()
    p = _paths(tmp_path)

    real_run_pass = run_mod.run_pass

    def fake_run_pass(*, now, dry_run=False):
        return real_run_pass(
            now=now, inventory=inv, emit_fn=em, evaluate_fn=ev, dry_run=dry_run, **p
        )

    monkeypatch.setattr(run_mod, "run_pass", fake_run_pass)
    rc = run_mod.main(["--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "a: failed" in out
    assert "b: healthy" in out
    assert not p["tick_path"].exists()


def test_self_check_ok(tmp_path, monkeypatch):
    # Point the state dir at a writable temp dir; real inventory + alert_bus.
    monkeypatch.setattr(
        run_mod, "DEFAULT_TICK_PATH", tmp_path / "state" / "last-tick.json"
    )
    rc = run_mod.main(["--self-check"])
    assert rc == 0


def test_self_check_reports_error_on_unwritable_state_dir(monkeypatch, capsys):
    # An unwritable state dir → status=error, exit 1.
    def boom_mkdir(*a, **k):
        raise PermissionError("read-only")

    monkeypatch.setattr(Path, "mkdir", boom_mkdir)
    rc = run_mod.main(["--self-check"])
    assert rc == 1
    assert "status=error" in capsys.readouterr().out

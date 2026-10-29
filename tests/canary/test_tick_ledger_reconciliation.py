"""The pinned reconciliation harness for ``felix-canary``'s ``key_ledger``
(#1063; contract ``kitty-specs/pointer-key-ledger-01M189P6/contracts/key-ledger.md``
§ "Obligation 2 — Test" and § "Reuse by a second producer").

``docs/design/architecture/data/service-inventory.json`` names this exact path
in ``felix-canary``'s ``health_check.key_ledger.reconciliation_harness``; see
``test_felix_canary_harness_is_this_file``.

The producer is ``scripts.canary.run.run_pass``. It is **executed** under
injected effects (no network, no ntfy, no ``/data``), and the tick-signal file
it actually writes is reconciled against the real ledger. The emitted key set
is never taken from a list written here (Obligation 2.1). The shared helper
``tests.canary.ledger_reconcile`` does the reconciliation unmodified, which is
the contract's test that a second producer needs no new reconciliation code.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.canary import run as run_mod
from tests.canary.ledger_reconcile import EmissionResult, assert_reconciles, load_ledgers

REPO_ROOT = Path(__file__).resolve().parents[2]
INVENTORY_PATH = REPO_ROOT / "docs" / "design" / "architecture" / "data" / "service-inventory.json"
REAL_INVENTORY = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
REAL_LEDGERS = load_ledgers(REAL_INVENTORY)

NOW = datetime(2026, 10, 14, 19, 0, 0, tzinfo=timezone.utc)

# A one-component inventory the producer can evaluate cleanly: an active
# service with an http health check whose injected probe answers 200.
_FIXTURE_INVENTORY = {
    "services": [
        {
            "id": "fixture-svc",
            "name": "fixture-svc",
            "type": "systemd-timer",
            "status": "active",
            "health_check": {"method": "http", "endpoint": "http://fixture", "timeout_seconds": 1},
        }
    ]
}


def _drive_producer(tmp_path: Path, *, dedup_path: Path | None = None) -> tuple[dict, EmissionResult]:
    """Run one real canary pass and observe the tick document it wrote."""
    tick_path = tmp_path / "state" / "last-tick.json"
    tick_path.parent.mkdir(parents=True, exist_ok=True)
    emitted_alerts: list = []
    summary = run_mod.run_pass(
        now=NOW,
        inventory=_FIXTURE_INVENTORY,
        dedup_path=dedup_path or (tmp_path / "state" / "dedup.json"),
        tick_path=tick_path,
        ledger_dir=tmp_path / "ledger",
        emit_fn=emitted_alerts.append,
        http_get=lambda *_a, **_k: 200,
        run_cmd=lambda *_a, **_k: (0, "", ""),
        read_state=lambda _p: {},
        dry_run=False,
    )
    text = tick_path.read_text(encoding="utf-8") if tick_path.exists() else None
    try:
        document = json.loads(text) if text is not None else None
    except json.JSONDecodeError:
        document = None
    emission = EmissionResult(
        # run_pass returns a summary on every completed pass; a raised runner
        # exception would have failed this call outright.
        process_ok=isinstance(summary, dict),
        process_detail=f"run_pass returned {type(summary).__name__}",
        document_text=text,
        document=document,
    )
    return summary, emission


def test_felix_canary_declares_a_ledger():
    """Obligation 2.5 pin: deleting this ledger silently reopens #1063's
    dead-man's-switch blind spot (a do-nothing canary reads alive)."""
    assert "felix-canary" in REAL_LEDGERS


def test_felix_canary_harness_is_this_file():
    this_file = str(Path(__file__).resolve().relative_to(REPO_ROOT))
    assert REAL_LEDGERS["felix-canary"]["reconciliation_harness"] == this_file


def test_felix_canary_reconciles_against_its_real_ledger(tmp_path):
    summary, emission = _drive_producer(tmp_path)
    assert summary["status"] == "success", summary
    assert_reconciles(emission, REAL_LEDGERS["felix-canary"], "felix-canary")


def test_error_pass_has_the_same_key_set_and_status_error(tmp_path):
    """An errored pass must still reconcile (reconciliation is a key-set
    property), and the ``errors`` -> ``status`` subsumption that lets the
    ledger declare ``errors`` diagnostic_only must hold on a real run."""
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("a file where the dedup directory should be", encoding="utf-8")
    summary, emission = _drive_producer(tmp_path, dedup_path=blocker / "dedup.json")
    assert summary["errors"], "the fixture must actually make the pass record an error"
    assert emission.document is not None
    assert emission.document["status"] == "error"
    assert emission.document["errors"]
    assert_reconciles(emission, REAL_LEDGERS["felix-canary"], "felix-canary")


def test_reconciliation_fails_when_the_producer_emits_an_undeclared_key(tmp_path, monkeypatch):
    """Non-vacuity at the producer: make run_pass itself write one extra key
    and the reconciliation of its real output must fail, naming the key."""
    real_write = run_mod._write_tick_signal

    def widened_write(tick_path, signal):
        real_write(tick_path, {**signal, "new_field": 1})

    monkeypatch.setattr(run_mod, "_write_tick_signal", widened_write)
    _summary, emission = _drive_producer(tmp_path)
    assert emission.document is not None and "new_field" in emission.document
    try:
        assert_reconciles(emission, REAL_LEDGERS["felix-canary"], "felix-canary")
    except AssertionError as exc:
        assert "new_field" in str(exc)
    else:  # pragma: no cover - the assertion above is the point
        raise AssertionError("an undeclared emitted key reconciled silently")

"""The pinned reconciliation harness for ``obsidian-sync-heartbeat``'s
``key_ledger`` (contract
``kitty-specs/pointer-key-ledger-01M189P6/contracts/key-ledger.md``
§ "Obligation 2 — Test"). This exact path is what
``docs/design/architecture/data/service-inventory.json`` names in
``obsidian-sync-heartbeat``'s ``health_check.key_ledger.reconciliation_harness``
— do not move this file without updating that declaration (see
``test_harness_is_this_file`` below, which checks the declaration points back
here).

This is the second producer to adopt the pointer-key-ledger contract (the
first is restic-backup, ``tests/office2/restic_backup/test_ledger_reconciliation.py``
— read that module's docstring for the fuller three-part structure this one
follows in miniature). Per the contract's "Reuse by a second producer": this
file supplies no adjudication and no reconciliation logic of its own — both
come from the shared evaluator (``scripts.canary.ledger``) and the shared
reconciliation helper (``tests.canary.ledger_reconcile``), unmodified. The
synthetic-ledger unit tests of that shared helper's own logic (T024/T026)
already live in restic's test file and are not duplicated here — this file
tests the real ``obsidian-sync-heartbeat`` producer against its real ledger,
plus the two structural pins the contract calls for per producer
(Obligation 2.5's hand-maintained "declares a ledger" pin, and Obligation 4b's
"the declared harness is the one that actually produced the emission").

kentonium3/kg-automation#892/#894: this is also the regression-proof for the
defect the ledger replaces. The producer (``scripts/obsidian/sync-heartbeat.py``)
is executed as a real subprocess — exactly how cron invokes it — under
controlled effects: a stubbed ``pgrep`` on ``PATH`` (never the real process
table) and a stubbed ``OPENCLAW_BIN`` (never real WhatsApp), with ``--vault``,
``--state-file``, and ``--pointer-file`` all redirected under ``tmp_path`` (no
real vault writes). Three scenarios are driven:

1. the happy path (process running, first run) — reconciled key-set-wise
   against the real ledger, and asserted healthy;
2. the sync-process-down early return (``sys.exit(2)``) — the exact path
   #892/#894 called out as "exactly when the pointer matters most", asserted
   unhealthy on ``sync_process_running``;
3. a normal (non early-return) exit where a pre-seeded failure counter has
   already crossed ``max_failures`` — proving the derived ``propagation_ok``
   boolean actually reflects the escalation threshold, not just that
   ``sync_process_running`` was wired up.

Per the contract's "Reconciliation is a key-set property": the producer calls
one ``write_pointer()`` with every field explicit (``None`` where a value
wasn't computed this run), so its key set is invariant across execution
paths by construction — reconciliation itself is driven once (scenario 1);
scenarios 2 and 3 exercise ``scripts.canary.ledger.evaluate`` over their
emitted documents, which is where their *values* (not their key sets) are
adjudicated.

Two further scenarios (review cycle 2) drive a REAL — not monkeypatched —
unwritable ``--state-file`` directory (:func:`_make_blocked_state_path`, a
parent path that is itself a regular file, so ``os.makedirs`` raises for
real) through both the process-down and the normal exit path, proving
``save_state`` failing there no longer (a) skips the pointer write, (b)
skips the heartbeat's real work, or (c) changes the documented exit code —
the exact hole a fixture that always supplies a writable state directory
cannot surface on its own.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.canary.ledger import evaluate
from tests.canary.ledger_reconcile import (
    EmissionResult,
    assert_reconciles,
    load_ledgers,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
INVENTORY_PATH = REPO_ROOT / "docs" / "design" / "architecture" / "data" / "service-inventory.json"
SCRIPT = REPO_ROOT / "scripts" / "obsidian" / "sync-heartbeat.py"

# `scripts.canary.ledger.evaluate` never resolves freshness itself (that's
# the probe layer's job — see the contract and scripts/canary/probes.py) and
# our ledger's only `minimum`-style modifier (`suppress_until_utc`) is unused
# here, so this fixed instant never actually gates any of the assertions
# below; kept for parity with restic's harness and so a future predicate
# that does need `now` has a deterministic value to reconcile against.
NOW = datetime(2026, 8, 30, 12, 0, 0, tzinfo=timezone.utc)

REAL_INVENTORY = json.loads(INVENTORY_PATH.read_text())
REAL_LEDGERS = load_ledgers(REAL_INVENTORY)


# --------------------------------------------------------------------------- #
# Structural pins (contract Obligation 2.5 and 4b, per-producer)
# --------------------------------------------------------------------------- #


def test_obsidian_sync_heartbeat_declares_a_ledger():
    """One hardcoded pin, mirroring restic-backup's own
    (``test_restic_backup_declares_a_ledger``) — a hand-maintained list of
    *producers* (small, changes rarely), never of *keys* (see
    ``tests.canary.ledger_reconcile.assert_selection_matches``'s docstring for
    why the equals-check there makes a per-key list unnecessary)."""
    assert "obsidian-sync-heartbeat" in REAL_LEDGERS


def test_harness_is_this_file():
    """Contract Obligation 4b (second half): the harness named by
    obsidian-sync-heartbeat's ledger is the file actually reconciling it —
    not merely a path that resolves (that half is proven generically, for
    every declared ledger, by restic's
    ``test_declared_harness_paths_exist_on_disk``), but the one producing the
    evidence in the section below."""
    this_file = Path(__file__).resolve().relative_to(REPO_ROOT).as_posix()
    assert REAL_LEDGERS["obsidian-sync-heartbeat"]["reconciliation_harness"] == this_file


# --------------------------------------------------------------------------- #
# Real reconciliation against the repo copy of the producer
# --------------------------------------------------------------------------- #


def _stub(path: Path, name: str, body: str) -> None:
    f = path / name
    f.write_text("#!/usr/bin/env bash\n" + body + "\n")
    f.chmod(0o755)


@pytest.fixture
def env(tmp_path):
    """A stubbed environment: no real process table, no real WhatsApp, no
    real vault. ``PGREP_STUB_RUNNING`` (set per-call by :func:`run`) controls
    whether the stubbed ``pgrep`` reports the sync process alive.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stub(
        bin_dir,
        "pgrep",
        '''
if [ "${PGREP_STUB_RUNNING:-1}" = "1" ]; then
    echo "12345 ob sync run --continuous"
    exit 0
fi
exit 1
''',
    )
    openclaw_stub = bin_dir / "openclaw-stub.sh"
    openclaw_stub.write_text("#!/usr/bin/env bash\nexit 0\n")
    openclaw_stub.chmod(0o755)

    vault = tmp_path / "vault"
    vault.mkdir()
    state_file = tmp_path / "state" / "heartbeat-state.json"
    pointer_file = tmp_path / "state" / "last-tick.json"

    e = dict(os.environ)
    e["PATH"] = f"{bin_dir}:{e['PATH']}"
    # openclaw_bin() honors this override at call time (scripts/common/openclaw_bin.py)
    # — never a real WhatsApp send.
    e["OPENCLAW_BIN"] = str(openclaw_stub)

    return e, {"vault": vault, "state_file": state_file, "pointer_file": pointer_file}


def run(env_tuple, *, running: bool, pre_state: dict | None = None):
    """Execute the real producer as a subprocess (exactly how cron invokes
    it — ``python3 scripts/obsidian/sync-heartbeat.py``), never dry-run (dry
    run skips writing the pointer, which is the thing under test).
    """
    base_env, paths = env_tuple
    e = dict(base_env)
    e["PGREP_STUB_RUNNING"] = "1" if running else "0"
    if pre_state is not None:
        paths["state_file"].parent.mkdir(parents=True, exist_ok=True)
        paths["state_file"].write_text(json.dumps(pre_state))
    proc = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--vault", str(paths["vault"]),
            "--state-file", str(paths["state_file"]),
            "--pointer-file", str(paths["pointer_file"]),
        ],
        cwd=REPO_ROOT,
        env=e,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    text = paths["pointer_file"].read_text() if paths["pointer_file"].exists() else None
    return proc, text


def test_obsidian_sync_heartbeat_reconciles_against_its_real_ledger(env):
    """The happy path's emitted document, reconciled key-set-wise (both
    directions) against the real ledger via the shared helper."""
    proc, text = run(env, running=True)
    document = json.loads(text) if text is not None else None
    emitted = EmissionResult(
        process_ok=proc.returncode == 0,
        process_detail=f"exit {proc.returncode}: {proc.stderr[-500:]}",
        document_text=text,
        document=document,
    )
    assert_reconciles(emitted, REAL_LEDGERS["obsidian-sync-heartbeat"], "obsidian-sync-heartbeat")


def test_happy_path_document_reads_healthy(env):
    """Introducing the ledger must not change the reported health of a
    healthy system (first run, sync process up)."""
    _proc, text = run(env, running=True)
    document = json.loads(text)
    result = evaluate(document, REAL_LEDGERS["obsidian-sync-heartbeat"], now=NOW)
    assert result.outcome == "ok", result.evidence


def test_sync_process_down_reads_unhealthy(env):
    """kentonium3/kg-automation#892's own scenario, and the early-return path
    #894 called out as the one that matters most: the sync process is down,
    the script alerts and exits 2 (documented, not a crash) — the pointer it
    still wrote must adjudicate unhealthy on `sync_process_running`, never on
    log recency."""
    proc, text = run(env, running=False)
    assert proc.returncode == 2, proc.stderr
    document = json.loads(text)
    assert document["sync_process_running"] is False
    result = evaluate(document, REAL_LEDGERS["obsidian-sync-heartbeat"], now=NOW)
    assert result.outcome == "unhealthy"
    assert "sync_process_running" in result.evidence


def _make_blocked_state_path(tmp_path: Path) -> Path:
    """A state-file path whose PARENT is a regular file, not a directory.

    ``os.makedirs(os.path.dirname(state_file), exist_ok=True)`` then raises
    ``FileExistsError`` (an ``OSError`` subclass) -- a REAL failure, not a
    monkeypatched one, and one that (unlike ``chmod 0o500``) reproduces
    reliably even when the test runs as root, where permission bits are
    bypassed. Exercises the same failure class an unwritable or disk-full
    directory would raise from the identical call site.
    """
    blocked_parent = tmp_path / "blocked-state"
    blocked_parent.write_text("not a directory")
    return blocked_parent / "heartbeat-state.json"


def test_unwritable_state_dir_process_down_still_writes_pointer_and_exits_2(env, tmp_path):
    """#892/#894 review cycle 2 finding: with the state directory unwritable,
    the sync-process-down path previously raised straight out of
    ``save_state``, skipped the pointer write entirely, and exited 1 instead
    of the documented 2 -- leaving the PREVIOUS pointer sitting there fresh
    and healthy until it aged out. ``env``'s own fixture always supplies a
    writable state directory (that's why this didn't surface originally);
    this test breaks it for real (:func:`_make_blocked_state_path`), leaving
    the pointer directory writable so success there is not a tautology."""
    base_env, paths = env
    custom_paths = dict(paths)
    custom_paths["state_file"] = _make_blocked_state_path(tmp_path)
    custom_paths["pointer_file"] = tmp_path / "ok-state" / "last-tick.json"

    proc, text = run((base_env, custom_paths), running=False)

    # (c) the documented exit code survives the instrumentation failure.
    assert proc.returncode == 2, proc.stderr
    # Sanity: the failure was actually hit, not dodged by some other path.
    assert "Failed to save state" in proc.stderr, proc.stderr
    # (a) the heartbeat's real work on this path -- alerting -- still ran.
    assert "Alert sent via WhatsApp" in proc.stderr, proc.stderr
    # (b) the pointer write was still attempted, and succeeded (only the
    # state-file path is broken; the pointer path is fine).
    assert text is not None, "pointer was not written despite the fix"
    document = json.loads(text)
    assert document["sync_process_running"] is False
    result = evaluate(document, REAL_LEDGERS["obsidian-sync-heartbeat"], now=NOW)
    assert result.outcome == "unhealthy"
    assert "sync_process_running" in result.evidence


def test_unwritable_state_dir_normal_path_still_writes_pointer_and_exits_0(env, tmp_path):
    """Same finding, the normal (non early-return) exit -- the ordering the
    review called out as also able to crash a run *after* its vault write
    had already succeeded, reporting failure for a run whose real work was
    fine. A state-save failure alone must not change the exit code."""
    base_env, paths = env
    custom_paths = dict(paths)
    custom_paths["state_file"] = _make_blocked_state_path(tmp_path)
    custom_paths["pointer_file"] = tmp_path / "ok-state" / "last-tick.json"

    proc, text = run((base_env, custom_paths), running=True)

    # (c) a state-persistence failure alone must not turn a good run bad.
    assert proc.returncode == 0, proc.stderr
    # Sanity: the failure was actually hit, not dodged by some other path.
    assert "Failed to save state" in proc.stderr, proc.stderr
    # (a) the heartbeat's actual work -- the vault write -- still completed.
    assert "Wrote heartbeat:" in proc.stderr, proc.stderr
    heartbeat_path = custom_paths["vault"] / "00-System" / "sync-heartbeat.md"
    assert heartbeat_path.exists(), "vault heartbeat write did not complete"
    # (b) the pointer write was still attempted, and succeeded.
    assert text is not None, "pointer was not written despite the fix"
    document = json.loads(text)
    assert document["sync_process_running"] is True
    result = evaluate(document, REAL_LEDGERS["obsidian-sync-heartbeat"], now=NOW)
    assert result.outcome == "ok", result.evidence


def test_propagation_failure_crossing_threshold_reads_unhealthy(env):
    """A NORMAL (non early-return) exit where the propagation counter has
    already crossed max_failures: sync_process_running stays true but the
    derived propagation_ok flips false — proves the boolean is actually
    wired to the escalation threshold, not merely mirroring process state."""
    pre_state = {
        "consecutive_failures": 2,
        "last_written": "2020-01-01T00:00:00Z",
        "last_check": None,
    }
    proc, text = run(env, running=True, pre_state=pre_state)
    assert proc.returncode == 0, proc.stderr
    document = json.loads(text)
    assert document["sync_process_running"] is True
    assert document["consecutive_failures"] == 3
    assert document["propagation_ok"] is False
    result = evaluate(document, REAL_LEDGERS["obsidian-sync-heartbeat"], now=NOW)
    assert result.outcome == "unhealthy"
    assert "propagation_ok" in result.evidence

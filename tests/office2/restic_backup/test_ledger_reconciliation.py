"""The pinned reconciliation harness for ``restic-backup``'s ``key_ledger``
(contract ``kitty-specs/pointer-key-ledger-01M189P6/contracts/key-ledger.md``
§ "Obligation 2 — Test"). This exact path is what
``docs/design/architecture/data/service-inventory.json`` names in
``restic-backup``'s ``health_check.key_ledger.reconciliation_harness`` — do
not move this file without updating that declaration, and see
``test_restic_backup_harness_is_this_file`` below, which checks the
declaration points back here.

Three things happen in this module, in this order:

1. Synthetic-ledger unit tests of ``tests.canary.ledger_reconcile``'s own
   logic (T024, T026) — both reconciliation directions and all four
   harness-observation floors, each a distinct, deliberately-triggered
   failure. These use invented key names, unrelated to restic, because the
   helper's logic is what is under test here, not restic (contract
   Obligation 2.1).
2. The selection and structural floors (T025): the real reconciliation
   selection is non-empty and equals the inventory's ledger-declaring
   component set; the ``restic-backup`` pin; every declared
   ``reconciliation_harness`` exists on disk; and this file's own path
   matches what ``restic-backup``'s ledger names. Negative cases are driven
   through fixture inventories, never by editing the real one.
3. The real reconciliation (T028): the repo copy of
   ``scripts/office2/restic-backup.sh`` is executed under stubbed effects
   (mount/restic/du/df, same technique WP01's
   ``tests/office2/restic_backup/test_pointer_emission.py`` uses) and its
   emitted document is reconciled against the real ``restic-backup`` ledger.
   The three early-exit paths then drive WP03's evaluator, not
   reconciliation — reconciliation is a key-set property, and the producer
   writes a static heredoc, so its key set cannot vary across execution
   paths by construction; what varies is the *values*, which is where the
   evaluator's verdict actually lives (contract "Reconciliation is a
   key-set property").
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.canary.ledger import evaluate
from tests.canary.ledger_reconcile import (
    EmissionResult,
    assert_harness_paths_exist,
    assert_reconciles,
    assert_selection_matches,
    load_ledgers,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
INVENTORY_PATH = REPO_ROOT / "docs" / "design" / "architecture" / "data" / "service-inventory.json"
SCRIPT = REPO_ROOT / "scripts" / "office2" / "restic-backup.sh"

NOW = datetime(2026, 8, 30, 12, 0, 0, tzinfo=timezone.utc)

REAL_INVENTORY = json.loads(INVENTORY_PATH.read_text())
REAL_LEDGERS = load_ledgers(REAL_INVENTORY)


# --------------------------------------------------------------------------- #
# 1. Synthetic-ledger unit tests of the helper's own logic (T024, T026)
# --------------------------------------------------------------------------- #


def _synthetic_ledger() -> dict:
    return {
        "adjudicated": {"alpha": {"good_values": [1]}},
        "diagnostic_only": {"beta": {"reason": "diagnostic only, for these tests"}},
    }


def _ok_emission(document: dict) -> EmissionResult:
    text = json.dumps(document)
    return EmissionResult(process_ok=True, process_detail="exit 0", document_text=text, document=document)


def test_reconciles_when_key_sets_match():
    assert_reconciles(_ok_emission({"alpha": 1, "beta": "x"}), _synthetic_ledger(), "synthetic")


def test_fails_on_undeclared_emitted_key():
    """T024: a producer emitting a key in neither list fails, naming it."""
    with pytest.raises(AssertionError, match="phantom"):
        assert_reconciles(_ok_emission({"alpha": 1, "beta": "x", "phantom": True}), _synthetic_ledger(), "synthetic")


def test_fails_on_stale_declared_key():
    """T024: a ledger declaring a key the producer no longer emits fails, naming it."""
    ledger = _synthetic_ledger()
    ledger["adjudicated"]["stale_key"] = {"good_values": [1]}
    with pytest.raises(AssertionError, match="stale_key"):
        assert_reconciles(_ok_emission({"alpha": 1, "beta": "x"}), ledger, "synthetic")


def test_fails_on_unacceptable_process_outcome():
    """T026 floor 1: the harness's own process-outcome judgement."""
    emitted = EmissionResult(process_ok=False, process_detail="exit 1 (unexpected)", document_text=None, document=None)
    with pytest.raises(AssertionError, match="process outcome"):
        assert_reconciles(emitted, _synthetic_ledger(), "synthetic")


def test_fails_on_absent_document():
    """T026 floor 2: no document produced at all -- never treated as `{}`."""
    emitted = EmissionResult(process_ok=True, process_detail="exit 0", document_text=None, document=None)
    with pytest.raises(AssertionError, match="no document"):
        assert_reconciles(emitted, _synthetic_ledger(), "synthetic")


def test_fails_on_undecodable_document():
    """T026 floor 3a: present text that is not JSON at all."""
    emitted = EmissionResult(process_ok=True, process_detail="exit 0", document_text="{not json", document=None)
    with pytest.raises(AssertionError, match="did not decode"):
        assert_reconciles(emitted, _synthetic_ledger(), "synthetic")


def test_fails_on_non_object_document():
    """T026 floor 3b: valid JSON, but not an object."""
    text = json.dumps([1, 2, 3])
    emitted = EmissionResult(process_ok=True, process_detail="exit 0", document_text=text, document=json.loads(text))
    with pytest.raises(AssertionError, match="not a JSON object"):
        assert_reconciles(emitted, _synthetic_ledger(), "synthetic")


def test_fails_on_empty_key_set():
    """T026 floor 4: an object that parses but carries zero keys."""
    text = json.dumps({})
    emitted = EmissionResult(process_ok=True, process_detail="exit 0", document_text=text, document=json.loads(text))
    with pytest.raises(AssertionError, match="zero keys"):
        assert_reconciles(emitted, _synthetic_ledger(), "synthetic")


# --------------------------------------------------------------------------- #
# 2. Selection and structural floors (T025)
# --------------------------------------------------------------------------- #


def test_selection_is_non_empty():
    """T025.1: the real reconciliation selection must not be empty -- the
    cheapest line in the mission, and the one most likely to be omitted."""
    assert REAL_LEDGERS, "no ledgers found in the real inventory -- the reconciliation is not running"


def test_empty_selection_fails():
    """T025.1: prove the non-empty assertion itself fires when empty."""
    with pytest.raises(AssertionError, match="no ledgers selected"):
        assert_selection_matches(set(), {"services": []})


def test_selection_matches_the_full_ledger_declaring_set():
    """T025.2: equal, not a subset -- a component that grows a ledger and is
    silently not reconciled is the #913 failure mode."""
    assert_selection_matches(set(REAL_LEDGERS), REAL_INVENTORY)


def test_deleted_ledger_fails_selection_match():
    """T025.4: simulated via a fixture inventory, never by editing the real
    one. A component that WAS in the selection but no longer declares a
    ledger must fail the match, not pass vacuously."""
    fixture_inventory = {
        "services": [{"name": "fake-component", "health_check": {"method": "state-file"}}]
    }
    with pytest.raises(AssertionError, match="fake-component"):
        assert_selection_matches({"fake-component"}, fixture_inventory)


def test_restic_backup_declares_a_ledger():
    """T025.3: one hardcoded pin. This is a hand-maintained list of
    *producers* (2, changing yearly), never of *keys* (14, changing per
    commit) -- see ``ledger_reconcile.assert_selection_matches``'s docstring
    for why the equals-check above makes a per-key list unnecessary, and why
    accepting a per-producer pin here while refusing one there is
    deliberate, not an inconsistency."""
    assert "restic-backup" in REAL_LEDGERS


def test_declared_harness_paths_exist_on_disk():
    """T025.5 (first half): every declared reconciliation_harness resolves
    to a real file. Moved here from the validator (contract rule 8)."""
    assert_harness_paths_exist(REAL_LEDGERS, REPO_ROOT)


def test_declared_harness_path_missing_fails():
    """Prove assert_harness_paths_exist itself fires, via a fixture ledger
    naming a path that does not exist."""
    fixture_ledgers = {"fake-component": {"reconciliation_harness": "tests/does/not/exist.py"}}
    with pytest.raises(AssertionError, match="does not exist"):
        assert_harness_paths_exist(fixture_ledgers, REPO_ROOT)


def test_restic_backup_harness_is_this_file():
    """T025.5 (second half): the harness named by restic-backup's ledger is
    the file actually reconciling it -- not merely a path that resolves,
    but the one producing the evidence below in section 3."""
    this_file = Path(__file__).resolve().relative_to(REPO_ROOT).as_posix()
    assert REAL_LEDGERS["restic-backup"]["reconciliation_harness"] == this_file


# --------------------------------------------------------------------------- #
# 3. Real reconciliation against the repo copy of the producer (T028)
# --------------------------------------------------------------------------- #

# The real `date` binary, resolved once before PATH is overridden below, so
# the `date` stub can delegate everything except day-of-week to it (mirrors
# WP01's tests/office2/restic_backup/test_pointer_emission.py).
REAL_DATE = shutil.which("date")
# Same reason as REAL_DATE: resolved before PATH is overridden, so the
# stubs below can delegate to the genuine binary (#960).
REAL_STAT = shutil.which("stat") or ""
REAL_TIMEOUT = shutil.which("timeout") or ""


def _stub(path: Path, name: str, body: str) -> None:
    f = path / name
    f.write_text("#!/usr/bin/env bash\n" + body + "\n")
    f.chmod(0o755)


@pytest.fixture
def env(tmp_path):
    """A stubbed environment producing a document that satisfies EVERY
    adjudicated predicate on the happy path -- including snapshot_count's
    minimum of 2, which a single-snapshot stub (as WP01's own fixture
    defaults to, for its own unrelated purposes) would not."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    state = tmp_path / "state"
    logs = tmp_path / "logs"

    _stub(bin_dir, "mountpoint", 'exit "${STUB_MOUNT_RC:-0}"')
    # `stat -c%s` (GNU) and `timeout` (GNU coreutils) are used by the state-pointer
    # block the tests below assert on. Neither exists in BSD/macOS userland, and
    # the failure is silent in the worst way: `stat -c%s` errors, the script's
    # `|| echo 65537` fallback fires, 65537 > the 65536 ceiling, and the ENTIRE
    # carry-forward block is skipped. Every assertion that the value is null then
    # passes for the wrong reason (#960).
    #
    # Stubbed here rather than made portable in the script, for the same reason
    # `du`, `df`, `restic` and `mountpoint` are stubbed: this harness is already
    # the platform simulator, and restic-backup.sh is a root-privileged nightly
    # backup that should not grow branches to suit a developer laptop. Note the
    # script has two further GNU-isms (`du -sb`, `df -B1 --output=avail`) that
    # this suite never sees precisely because they are stubbed -- so this suite
    # is not, and cannot be, a portability check for the script.
    #
    # Both prefer the real binary, following the `date` stub below, so on Linux/CI
    # the genuine GNU call is what runs. They differ in what they do when it is
    # missing: `stat` TRANSLATES (-c%s -> the BSD -f%z spelling, the idiom already
    # used in-repo at scripts/openclaw/install.sh:55), whereas `timeout` DROPS the
    # bound and runs the command unbounded -- there is no BSD equivalent to
    # translate to. That is acceptable only because the sole call site is
    # `timeout 5 jq` over a document this script itself wrote, already bounded by
    # the 64 KB size ceiling.
    _stub(bin_dir, "stat", f'''
if [ "$1" = "-c%s" ]; then
    [ -n "$STUB_STAT_FAIL" ] && exit 1
    {REAL_STAT} -c%s "$2" 2>/dev/null || {REAL_STAT} -f%z "$2"
    exit $?
fi
exec {REAL_STAT} "$@"''')
    _stub(bin_dir, "timeout", '''
if [ -n "$REAL_TIMEOUT" ] && [ -x "$REAL_TIMEOUT" ]; then exec "$REAL_TIMEOUT" "$@"; fi
shift
exec "$@"''')
    _stub(bin_dir, "du", 'echo "1024\t$2"')
    _stub(bin_dir, "restic", '''
case "$1" in
  snapshots)
    [ -n "$STUB_SNAPSHOTS_FAIL" ] && exit 1
    case "$*" in
      *--latest*)
        echo "[{\\"time\\":\\"2026-08-28T04:00:05.123456Z\\",\\"id\\":\\"deadbeef\\",\\"paths\\":[\\"/data/services\\",\\"/data/transcripts\\",\\"/home/claude\\",\\"/home/kgale\\"]}]"
        ;;
      *)
        echo '[{"time":"2026-08-21T04:00:05Z","id":"aaaaaaaa"},{"time":"2026-08-28T04:00:05Z","id":"deadbeef"}]'
        ;;
    esac
    exit 0 ;;
  stats)     echo "{\\"total_file_count\\": 100}"; exit 0 ;;
  backup)    exit "${STUB_BACKUP_RC:-0}" ;;
  forget)    exit "${STUB_PRUNE_RC:-0}" ;;
  check)     exit "${STUB_CHECK_RC:-0}" ;;
  *)         exit 0 ;;
esac''')
    _stub(bin_dir, "df", '''
case "$*" in
  *--output=avail*)
    echo "Avail"
    echo "107374182400"
    ;;
  *)
    echo "Filesystem      Size  Used Avail Use% Mounted on"
    echo "/dev/sdX1        1T    1T  500G  50% /mnt/backups"
    ;;
esac
exit 0''')
    # Non-Sunday, deterministically -- this file never exercises the weekly
    # integrity-check branch (last_integrity_check_utc is a deferred
    # freshness obligation either way, not decided by evaluate()).
    _stub(bin_dir, "date", f'''
if [ "$1" = "+%u" ]; then
    echo "3"
    exit 0
fi
exec {REAL_DATE} "$@"''')

    e = dict(os.environ)
    e["PATH"] = f"{bin_dir}:{e['PATH']}"
    e["REAL_TIMEOUT"] = REAL_TIMEOUT
    e["LOG_DIR"] = str(logs)
    e["STATE_DIR"] = str(state)
    e["BACKUP_MOUNT"] = str(tmp_path / "mnt")
    e["RESTIC_REPOSITORY"] = str(tmp_path / "repo")
    e["RESTIC_PASSWORD_FILE"] = str(tmp_path / "pw")
    return e, state


def run(env_tuple, **overrides):
    e, state = env_tuple
    e = {**e, **{k: str(v) for k, v in overrides.items()}}
    proc = subprocess.run(["bash", str(SCRIPT)], env=e, capture_output=True, text=True, check=False)
    path = state / "last-backup.json"
    text = path.read_text() if path.exists() else None
    return proc, text


def test_restic_backup_reconciles_against_its_real_ledger(env):
    """T028.1: execute the repo copy of the producer (see
    ledger_reconcile's module docstring on what this does and does not bind
    -- R4) and reconcile the emitted document against restic-backup's real
    ledger, via the shared helper."""
    proc, text = run(env)
    document = json.loads(text) if text is not None else None
    emitted = EmissionResult(
        process_ok=proc.returncode == 0,
        process_detail=f"exit {proc.returncode}",
        document_text=text,
        document=document,
    )
    assert_reconciles(emitted, REAL_LEDGERS["restic-backup"], "restic-backup")


def test_happy_path_document_reads_healthy(env):
    """T028.3: introducing the contract must not change the reported health
    of a healthy system."""
    _proc, text = run(env)
    document = json.loads(text)
    result = evaluate(document, REAL_LEDGERS["restic-backup"], now=NOW)
    assert result.outcome == "ok", result.evidence


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"STUB_MOUNT_RC": 1}, id="mount_failure"),
        pytest.param({"STUB_SNAPSHOTS_FAIL": "1"}, id="repo_inaccessible"),
        pytest.param({"STUB_BACKUP_RC": 1}, id="backup_failure"),
    ],
)
def test_early_exit_verdict_is_unhealthy(env, overrides):
    """T028.2: the producer writes a static heredoc, so its key SET is
    invariant across execution paths by construction -- reconciling every
    early exit re-checks the same names and can never fail, proving
    nothing (contract "Reconciliation is a key-set property"). What
    actually varies on these paths is the *values* the predicates must
    survive: restic_exit_code lands at 127 (mount/repo failure, "never
    attempted") or the real non-{0,3} exit code (backup failure) -- both
    outside restic_exit_code's good_values, so the evaluator, run over the
    emitted document, must call the component unhealthy on that key."""
    _proc, text = run(env, **overrides)
    document = json.loads(text)
    result = evaluate(document, REAL_LEDGERS["restic-backup"], now=NOW)
    assert result.outcome == "unhealthy"
    assert "restic_exit_code" in result.evidence

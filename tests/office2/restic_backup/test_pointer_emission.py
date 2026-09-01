"""The backup script's state pointer, exercised rather than read (#902).

The prune outcome is only useful if `prune_exit_code` survives the paths that
*skip* the prune. Those are early `exit` branches in a bash script, which is
exactly where a shell-variable mistake hides and exactly what reading the code
tends to miss — the sibling #906 defect survived review the same way.

So these tests actually run the script, with `mountpoint`/`restic`/`du` stubbed
on PATH and the output directories redirected, and assert the emitted JSON.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "office2" / "restic-backup.sh"

# The real `date` binary, resolved once before PATH is overridden, so the
# `date` stub below can delegate everything except day-of-week to it.
REAL_DATE = shutil.which("date")
# Same reason as REAL_DATE: resolved before PATH is overridden, so the
# stubs below can delegate to the genuine binary (#960).
REAL_STAT = shutil.which("stat") or ""
REAL_TIMEOUT = shutil.which("timeout") or ""

# Mirrors the SOURCE_ROOTS array defined once in the script (T004): the
# default snapshot the restic stub reports carries every configured root, so
# the happy path emits source_roots_present=true without each test having to
# spell the roots out.
SOURCE_ROOTS = ["/data/services", "/data/transcripts", "/home/claude", "/home/kgale"]

# The current ten keys the unmodified producer emits. Pinned by
# test_pointer_emits_exactly_the_baseline_ten_keys as a red-then-green
# baseline for T002-T006 (#pointer-key-ledger WP01/T001).
BASELINE_TEN_KEYS = {
    "schema_version", "snapshot_timestamp_utc", "snapshot_id", "restic_exit_code",
    "prune_exit_code", "script_finished_at_utc", "repo_size_bytes", "snapshot_count",
    "integrity_check_run", "integrity_check_passed",
}

# The final fourteen keys the producer emits once T002-T006 land.
FINAL_FOURTEEN_KEYS = BASELINE_TEN_KEYS | {
    "last_integrity_check_utc", "files_processed", "source_roots_present",
    "repo_fs_free_bytes",
}


def _stub(path: Path, name: str, body: str) -> None:
    f = path / name
    f.write_text("#!/usr/bin/env bash\n" + body + "\n")
    f.chmod(0o755)


@pytest.fixture
def env(tmp_path):
    """A stubbed environment; each stub's behaviour is tuned per test."""
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
    # restic dispatches on its first arg (and, for `snapshots`, whether
    # `--latest` is present) so each call can be tuned independently.
    # `snapshots --latest ...` serves the ts/id/paths lookup; plain
    # `snapshots --json` serves the count -- same distinction the real
    # command draws, which the script relies on to make two different calls.
    _stub(bin_dir, "restic", '''
case "$1" in
  snapshots)
    [ -n "$STUB_SNAPSHOTS_FAIL" ] && exit 1
    case "$*" in
      *--latest*)
        if [ -n "$STUB_SNAPSHOT_NO_PATHS" ]; then
          echo "[{\\"time\\":\\"2026-08-28T04:00:05.123456Z\\",\\"id\\":\\"deadbeef\\"}]"
        else
          paths="${STUB_SNAPSHOT_PATHS:-[\\"/data/services\\",\\"/data/transcripts\\",\\"/home/claude\\",\\"/home/kgale\\"]}"
          echo "[{\\"time\\":\\"2026-08-28T04:00:05.123456Z\\",\\"id\\":\\"deadbeef\\",\\"paths\\":$paths}]"
        fi
        ;;
      *)
        if [ -n "$STUB_COUNT_QUERY_BROKEN" ]; then
          echo "not valid json"
        else
          echo '[{"time":"2026-08-28T04:00:05.123456Z","id":"deadbeef"}]'
        fi
        ;;
    esac
    exit 0 ;;
  stats)     [ -n "$STUB_STATS_FAIL" ] && exit 1
             echo "{\\"total_file_count\\": ${STUB_FILE_COUNT:-100}}"
             exit 0 ;;
  backup)    exit "${STUB_BACKUP_RC:-0}" ;;
  forget)    exit "${STUB_PRUNE_RC:-0}" ;;
  check)     exit "${STUB_CHECK_RC:-0}" ;;
  *)         exit 0 ;;
esac''')
    # `df -B1 --output=avail <repo>` (T005) and the unrelated `df -h
    # /mnt/backups` report-line call both hit this stub; only the former is
    # asserted on.
    _stub(bin_dir, "df", '''
[ -n "$STUB_DF_FAIL" ] && exit 1
case "$*" in
  *--output=avail*)
    echo "Avail"
    echo "${STUB_FS_AVAIL:-107374182400}"
    ;;
  *)
    echo "Filesystem      Size  Used Avail Use% Mounted on"
    echo "/dev/sdX1        1T    1T  500G  50% /mnt/backups"
    ;;
esac
exit 0''')
    # The script computes DOW itself via `date +%u` to gate the weekly
    # integrity check. Intercept only that call so the Sunday branch is
    # driven deterministically by STUB_DOW (NFR-002); every other `date`
    # invocation (timestamps, the log filename) delegates to the real
    # binary unchanged.
    _stub(bin_dir, "date", f'''
if [ "$1" = "+%u" ] && [ -n "$STUB_DOW" ]; then
    echo "$STUB_DOW"
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
    # Non-Sunday by default so no test's outcome depends on the real
    # calendar; Sunday-branch tests override this explicitly.
    e["STUB_DOW"] = "3"
    return e, state


def run(env_tuple, **overrides):
    e, state = env_tuple
    e = {**e, **{k: str(v) for k, v in overrides.items()}}
    proc = subprocess.run(["bash", str(SCRIPT)], env=e, capture_output=True, text=True, check=False)
    pointer = json.loads((state / "last-backup.json").read_text())
    return proc, pointer


def test_pointer_is_valid_json_on_the_happy_path(env):
    proc, ptr = run(env)
    assert proc.returncode == 0
    assert ptr["restic_exit_code"] == 0
    assert ptr["prune_exit_code"] == 0


def test_mount_failure_records_prune_never_attempted(env):
    """The script exits before anything runs; prune must read 127, not 0."""
    proc, ptr = run(env, STUB_MOUNT_RC=1)
    assert proc.returncode == 1
    assert ptr["restic_exit_code"] == 127
    assert ptr["prune_exit_code"] == 127, "an aborted run must not report a clean prune"


def test_repo_inaccessible_records_prune_never_attempted(env):
    proc, ptr = run(env, STUB_SNAPSHOTS_FAIL="1")
    assert proc.returncode == 1
    assert ptr["prune_exit_code"] == 127


def test_backup_failure_records_prune_never_attempted(env):
    """Backup failed, so the script exits before the prune step."""
    proc, ptr = run(env, STUB_BACKUP_RC=1)
    assert proc.returncode == 1
    assert ptr["restic_exit_code"] == 1
    assert ptr["prune_exit_code"] == 127


def test_prune_failure_is_recorded(env):
    """The #902 case: backup fine, prune broken. Previously invisible."""
    _proc, ptr = run(env, STUB_PRUNE_RC=1)
    assert ptr["restic_exit_code"] == 0
    assert ptr["prune_exit_code"] == 1


def test_backup_warning_with_clean_prune(env):
    """restic backup exit 3 still produced a snapshot; prune succeeded."""
    _proc, ptr = run(env, STUB_BACKUP_RC=3)
    assert ptr["restic_exit_code"] == 3
    assert ptr["prune_exit_code"] == 0


def test_prune_exit_code_is_always_an_integer(env):
    """Never null: _explicit_error skips non-integers, so null reads healthy."""
    for overrides in ({}, {"STUB_MOUNT_RC": 1}, {"STUB_BACKUP_RC": 1}, {"STUB_PRUNE_RC": 2}):
        _, ptr = run(env, **overrides)
        assert isinstance(ptr["prune_exit_code"], int), f"non-integer for {overrides}"


def test_existing_fields_are_unchanged(env):
    """NFR-002: no field renamed, retyped, or dropped."""
    _, ptr = run(env)
    for key in ("schema_version", "snapshot_timestamp_utc", "snapshot_id",
                "restic_exit_code", "script_finished_at_utc", "repo_size_bytes",
                "snapshot_count", "integrity_check_run", "integrity_check_passed"):
        assert key in ptr, f"missing pre-existing field {key}"


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({}, id="happy_path"),
        pytest.param({"STUB_MOUNT_RC": 1}, id="mount_failure"),
        pytest.param({"STUB_SNAPSHOTS_FAIL": "1"}, id="repo_inaccessible"),
        pytest.param({"STUB_BACKUP_RC": 1}, id="backup_failure"),
    ],
)
def test_pointer_emits_exactly_the_final_fourteen_keys(env, overrides):
    """T001/T006: derive the emitted key set by executing the producer, on
    every execution path -- not just the happy path.

    Pinned as the ten-key baseline before T002-T006 landed (this passed
    against the unmodified script); updated in place, per T006, to the
    final fourteen now that the producer emits them. Never assert this by
    reading the heredoc source -- that is a second model of the producer
    and it will drift (US3 AS4).

    Parameterised over the early-exit paths (WP01 cycle-2 fix): the DoD
    requires the fourteen-key shape on every path, and the early exits are
    exactly where this component's historical defects (#906) have lived.
    `run()` parses the document via `json.loads`, so reaching the assertion
    below is itself proof the document stayed valid JSON on each path.
    """
    _, ptr = run(env, **overrides)
    assert set(ptr.keys()) == FINAL_FOURTEEN_KEYS
    assert ptr["schema_version"] == 2


def test_last_integrity_check_utc_null_when_never_checked(env):
    """T002: no prior document, non-Sunday run -- null, and the run completes."""
    proc, ptr = run(env)
    assert proc.returncode == 0
    assert ptr["last_integrity_check_utc"] is None


def test_last_integrity_check_utc_set_on_passing_sunday_check(env):
    """T002: a passing weekly check sets the field to the current UTC instant."""
    _, ptr = run(env, STUB_DOW=7, STUB_CHECK_RC=0)
    assert isinstance(ptr["last_integrity_check_utc"], str)
    assert ptr["last_integrity_check_utc"].endswith("Z")


def test_last_integrity_check_utc_not_set_on_failing_sunday_check(env):
    """T002: a failing check must NOT set the field -- it means 'verified good'."""
    _, ptr = run(env, STUB_DOW=7, STUB_CHECK_RC=1)
    assert ptr["last_integrity_check_utc"] is None
    assert ptr["integrity_check_passed"] is False


def test_last_integrity_check_utc_carries_forward_when_not_checked_today(env):
    """T002: a passing Sunday's value survives a later non-Sunday run untouched."""
    _, sunday_ptr = run(env, STUB_DOW=7, STUB_CHECK_RC=0)
    carried = sunday_ptr["last_integrity_check_utc"]
    assert carried is not None

    _, weekday_ptr = run(env, STUB_DOW=3)
    assert weekday_ptr["last_integrity_check_utc"] == carried


def test_last_integrity_check_utc_carries_forward_across_a_failed_sunday(env):
    """T002: a later FAILING Sunday must not clobber the last known-good value."""
    _, first_ptr = run(env, STUB_DOW=7, STUB_CHECK_RC=0)
    carried = first_ptr["last_integrity_check_utc"]
    assert carried is not None

    _, second_ptr = run(env, STUB_DOW=7, STUB_CHECK_RC=1)
    assert second_ptr["last_integrity_check_utc"] == carried
    assert second_ptr["integrity_check_passed"] is False


# ---------------------------------------------------------------------------
# LIVENESS DEPENDENCY -- read before touching the tests below (#960).
#
# Everything from here to test_files_processed_happy_path asserts that
# `last_integrity_check_utc` is None. That is also exactly what a DEAD
# carry-forward block produces, so none of these tests can tell "the guard
# rejected bad input" from "the block never ran". For eight months on macOS the
# block did not run at all -- `stat -c%s` is GNU-only -- and all of them passed.
#
# What keeps them honest is the small set of tests that require the block to
# execute and produce a value:
#   * test_last_integrity_check_utc_carries_forward_when_not_checked_today
#   * test_last_integrity_check_utc_carries_forward_across_a_failed_sunday
#   * test_last_integrity_check_utc_carries_forward_from_a_large_but_valid_document
#
# If those are ever skipped or deleted -- in particular via a
# skipif(sys.platform == "darwin") reflex when they go red on a Mac -- the tests
# below silently revert to passing for the wrong reason, with nothing flagging
# it. Fix the platform, do not skip the witnesses.
# ---------------------------------------------------------------------------


def test_last_integrity_check_utc_null_on_corrupt_prior_document(env):
    """T002: the one place a naive jq call could take the backup down.

    A malformed prior state document must not abort the run and must not
    poison the new value -- it must fail soft to null, same as a missing
    document.
    """
    _e, state = env
    state.mkdir(parents=True, exist_ok=True)
    (state / "last-backup.json").write_text("{not json at all")

    proc, ptr = run(env)
    assert proc.returncode == 0
    assert ptr["last_integrity_check_utc"] is None


def test_last_integrity_check_utc_null_when_prior_value_contains_a_quote(env):
    """WP01 cycle-2 fix: a quote-bearing prior value must not corrupt the document.

    Previously the carried-forward value was hand-wrapped in shell quotes
    with no type or format check, so a prior value containing a literal `"`
    produced an unparseable state document. jq now validates the value's
    shape and does the JSON encoding itself.
    """
    _e, state = env
    state.mkdir(parents=True, exist_ok=True)
    (state / "last-backup.json").write_text(json.dumps({"last_integrity_check_utc": 'x"y'}))

    proc, ptr = run(env)
    assert proc.returncode == 0
    assert ptr["last_integrity_check_utc"] is None


@pytest.mark.parametrize(
    "bad_value",
    [
        pytest.param(42, id="number"),
        pytest.param({"nested": True}, id="object"),
        pytest.param([1, 2, 3], id="array"),
    ],
)
def test_last_integrity_check_utc_null_when_prior_value_is_not_a_string(env, bad_value):
    """WP01 cycle-2 fix: a non-string prior value must default to null.

    `jq -r '... // empty'` previously accepted any non-empty value with no
    type check at all.
    """
    _e, state = env
    state.mkdir(parents=True, exist_ok=True)
    (state / "last-backup.json").write_text(json.dumps({"last_integrity_check_utc": bad_value}))

    proc, ptr = run(env)
    assert proc.returncode == 0
    assert ptr["last_integrity_check_utc"] is None


def test_last_integrity_check_utc_null_on_oversized_prior_document(env):
    """Post-merge review of #934, Finding 3: an oversized prior document must
    not be parsed at all -- fail soft to null, same as a missing or corrupt
    document, and the run must still complete. The real document is well
    under 1 KB; the script's ceiling is 64 KB, so pad well past it.
    """
    _e, state = env
    state.mkdir(parents=True, exist_ok=True)
    oversized = json.dumps({"last_integrity_check_utc": "2026-08-01T00:00:00Z", "pad": "x" * 100_000})
    (state / "last-backup.json").write_text(oversized)

    proc, ptr = run(env)
    assert proc.returncode == 0
    assert ptr["last_integrity_check_utc"] is None


def test_last_integrity_check_utc_carries_forward_from_a_large_but_valid_document(env):
    """The size guard must be two-sided: reject above the ceiling, ACCEPT below it.

    Every other size assertion in this file is one-sided -- they all assert
    `is None`, which is what a guard that rejects *everything* also produces.
    Mutation-tested during the #960 review: tightening the ceiling from 65536 to
    512 (a 128x change that would stop the real ~455-byte document from ever
    carrying forward) was caught by NO test in this module. The real document is
    ~455 bytes and the oversized fixture is ~100 KB, so nothing pinned anything
    in the 143x range between them.

    ~60 KB: comfortably under the 64 KB ceiling, far above the real document, and
    far above any plausible tightened bound.
    """
    _e, state = env
    state.mkdir(parents=True, exist_ok=True)
    carried = "2026-08-01T00:00:00Z"
    large_but_valid = json.dumps({"last_integrity_check_utc": carried, "pad": "x" * 60_000})
    assert 512 < len(large_but_valid) < 65_536, "fixture must sit under the ceiling"
    (state / "last-backup.json").write_text(large_but_valid)

    proc, ptr = run(env)
    assert proc.returncode == 0
    assert ptr["last_integrity_check_utc"] == carried, (
        "a valid document under the ceiling must carry forward; None here means "
        "the guard rejected it (ceiling too tight, or the size probe failed)"
    )


def test_the_size_probe_failing_is_treated_as_too_big(env):
    """`stat` failing is encoded as 65537 -- 'could not measure' becomes 'too big'.

    That conflation is deliberate (fail soft on an unreadable pointer) but it is
    the reason #960 was invisible: on macOS `stat -c%s` errored on every run and
    the block silently stopped executing. Pinning it means a future change to the
    fallback is a visible decision rather than an accident.
    """
    _e, state = env
    state.mkdir(parents=True, exist_ok=True)
    (state / "last-backup.json").write_text(
        json.dumps({"last_integrity_check_utc": "2026-08-01T00:00:00Z"})
    )

    proc, ptr = run(env, STUB_STAT_FAIL="1")
    assert proc.returncode == 0
    assert ptr["last_integrity_check_utc"] is None


def test_files_processed_happy_path(env):
    """T003: emits the stub's file count on a successful stats call."""
    _, ptr = run(env, STUB_FILE_COUNT=4242)
    assert ptr["files_processed"] == 4242


def test_files_processed_null_on_stats_failure(env):
    """T003: a stats failure must not fail the backup, only null the field."""
    proc, ptr = run(env, STUB_STATS_FAIL="1")
    assert proc.returncode == 0
    assert ptr["files_processed"] is None


def test_source_roots_present_true_when_all_roots_in_snapshot(env):
    """T004: happy path -- every configured root is in the snapshot's paths."""
    _, ptr = run(env)
    assert ptr["source_roots_present"] is True


def test_source_roots_present_false_when_a_root_is_missing(env):
    """T004: a partial capture -- one root silently absent -- must read false."""
    missing_home = json.dumps(SOURCE_ROOTS[:-1])
    _, ptr = run(env, STUB_SNAPSHOT_PATHS=missing_home)
    assert ptr["source_roots_present"] is False


def test_source_roots_present_null_when_snapshot_query_fails(env):
    """T004: comparison could not be performed -- null, not a guess."""
    proc, ptr = run(env, STUB_SNAPSHOTS_FAIL="1")
    assert proc.returncode == 1
    assert ptr["source_roots_present"] is None


def test_source_roots_present_null_when_snapshot_json_is_malformed(env):
    """WP01 cycle-2 fix: jq's own parse failure must not read as 'root missing'.

    `jq -e` exits non-zero both when the filter is false and when jq itself
    fails, and the prior code collapsed both to `false` -- a positive claim
    that a root was proven absent when nothing was measured. STUB_SNAPSHOT_PATHS
    is spliced verbatim into the snapshot's `paths` field, so an unbalanced
    value here breaks the whole document's JSON.
    """
    proc, ptr = run(env, STUB_SNAPSHOT_PATHS="{not valid json")
    assert proc.returncode == 0
    assert ptr["source_roots_present"] is None


def test_source_roots_present_null_when_paths_is_the_wrong_shape(env):
    """WP01 cycle-2 fix: `paths` present but not an array must also read null,
    not a false negative -- the comparison could not be performed as specified."""
    proc, ptr = run(env, STUB_SNAPSHOT_PATHS='"not-an-array"')
    assert proc.returncode == 0
    assert ptr["source_roots_present"] is None


def test_source_roots_present_null_when_paths_is_json_null(env):
    """WP01 cycle-3 fix: `paths` explicitly `null` must read null, not false.

    The prior filter defaulted `paths` to `[]` with `// []` BEFORE checking
    its type, so a JSON-null `paths` became an empty array -- which passes
    the array-type guard -- and the comparison then correctly reported the
    configured root as absent from that empty list: `false`. That `false` is
    a positive claim the root was proven absent, asserted when there was
    nothing to compare against at all.
    """
    proc, ptr = run(env, STUB_SNAPSHOT_PATHS="null")
    assert proc.returncode == 0
    assert ptr["source_roots_present"] is None


def test_source_roots_present_null_when_paths_is_absent_entirely(env):
    """WP01 cycle-3 fix: a snapshot record with no `paths` key at all must
    also read null, for the same reason as the explicit-null case above."""
    proc, ptr = run(env, STUB_SNAPSHOT_NO_PATHS="1")
    assert proc.returncode == 0
    assert ptr["source_roots_present"] is None


def test_source_roots_present_ignores_non_string_entries_in_paths(env):
    """WP01 cycle-3 decision: a `paths` array is still evaluated via index()
    even when it carries non-string entries alongside the real strings.

    jq's index() structurally compares each element regardless of type, so a
    stray number/null/object just fails to match the root string rather than
    erroring the filter -- the comparison against the well-typed entries
    genuinely completed, so this reads as a real answer, not null. All
    configured roots are present here (plus junk entries), so True.
    """
    junky_paths = json.dumps([*SOURCE_ROOTS, 42, None, {"nested": True}])
    _, ptr = run(env, STUB_SNAPSHOT_PATHS=junky_paths)
    assert ptr["source_roots_present"] is True


def test_repo_fs_free_bytes_happy_path(env):
    """T005: emits the stub's free-space figure."""
    _, ptr = run(env, STUB_FS_AVAIL=99999999999)
    assert ptr["repo_fs_free_bytes"] == 99999999999


def test_repo_fs_free_bytes_null_on_df_failure(env):
    """T005: a df failure must not fail the backup, only null the field."""
    proc, ptr = run(env, STUB_DF_FAIL="1")
    assert proc.returncode == 0
    assert ptr["repo_fs_free_bytes"] is None


def test_snapshot_count_null_when_count_query_yields_nothing(env):
    """T006: the previously-unguarded field. Must stay valid JSON, never emit
    an empty slot ("snapshot_count": ,)."""
    proc, ptr = run(env, STUB_COUNT_QUERY_BROKEN="1")
    assert proc.returncode == 0
    assert ptr["snapshot_count"] is None


def test_document_is_valid_json_even_with_a_broken_count_query(env):
    """T006: assert parseability directly, not by string matching."""
    e, state = env
    e = {**e, "STUB_COUNT_QUERY_BROKEN": "1"}
    proc = subprocess.run(["bash", str(SCRIPT)], env=e, capture_output=True, text=True, check=False)
    assert proc.returncode == 0
    raw = (state / "last-backup.json").read_text()
    parsed = json.loads(raw)  # raises if the document is not valid JSON
    assert parsed["snapshot_count"] is None


@pytest.mark.skipif(os.geteuid() == 0, reason="cannot test the non-root branch as root")
def test_overrides_only_apply_when_unprivileged(env):
    """The test-only path overrides must be inert for a privileged run.

    This script is a NOPASSWD sudo target and normally runs as root. `sudo` on
    office2 is configured with env_reset + secure_path, which already strips
    these — but that makes the safety property depend on sudoers staying that
    way. The guard is intrinsic instead: a privileged run ignores the overrides
    outright, so it cannot be redirected regardless of sudo configuration.

    Asserted here by proving the guard exists and is keyed on the effective uid,
    since the test process cannot become root to exercise the other branch.
    """
    src = SCRIPT.read_text()
    assert 'if [ "$(id -u)" -eq 0 ]; then' in src, "privileged branch missing"
    guarded = src.split('if [ "$(id -u)" -eq 0 ]; then', 1)[1].split("else", 1)[0]
    for var in ("LOG_DIR", "STATE_DIR", "BACKUP_MOUNT",
                "RESTIC_REPOSITORY", "RESTIC_PASSWORD_FILE"):
        assert f'{var}="/' in guarded, f"{var} not pinned to an absolute path when root"
    # and the unprivileged branch still honours overrides, or the tests above lie
    assert 'LOG_DIR="${LOG_DIR:-' in src

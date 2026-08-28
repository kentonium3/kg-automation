"""The backup-script drift comparator (#903).

The property that matters is that it FAILS CLOSED. A comparator which reports
`match` when it cannot read one side converts an unknown into a false assurance,
which is exactly the failure it exists to prevent — so the unreadable and missing
cases get more attention here than the happy path.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.canary.probes import run_probe
from scripts.office2 import backup_script_drift as bsd


@pytest.fixture
def pair(tmp_path):
    a = tmp_path / "repo.sh"
    b = tmp_path / "deployed.sh"
    a.write_text("#!/bin/bash\necho hello\n")
    b.write_text("#!/bin/bash\necho hello\n")
    return a, b


def judge(state_path, now=None):
    """Judge the emitted pointer with the REAL canary probe."""
    return run_probe(
        {"method": "state-file", "state_path": str(state_path),
         "max_age_seconds": 108000, "success_status_values": ["success"]},
        now or datetime.now(timezone.utc),
        http_get=None, run_cmd=None,
        read_state=lambda p: json.loads(Path(p).read_text()),
    )


# --------------------------------------------------------------------------- #
# Verdicts
# --------------------------------------------------------------------------- #

def test_identical_files_match(pair):
    a, b = pair
    r = bsd.compare(a, b)
    assert r["verdict"] == bsd.MATCH
    assert r["repo_md5"] == r["deployed_md5"]


def test_differing_files_report_drift(pair):
    a, b = pair
    b.write_text("#!/bin/bash\necho tampered\n")
    r = bsd.compare(a, b)
    assert r["verdict"] == bsd.DRIFT
    assert r["repo_md5"] != r["deployed_md5"]


def test_missing_deployed_copy_is_inconclusive_not_match(pair):
    a, b = pair
    b.unlink()
    r = bsd.compare(a, b)
    assert r["verdict"] == bsd.INCONCLUSIVE
    assert r["verdict"] != bsd.MATCH, "not knowing must never read as agreement"


def test_missing_repo_copy_is_inconclusive(pair):
    a, b = pair
    a.unlink()
    assert bsd.compare(a, b)["verdict"] == bsd.INCONCLUSIVE


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file permissions")
def test_unreadable_deployed_copy_is_inconclusive_not_match(pair):
    """The case that matters: readable-by-nobody must not look identical."""
    a, b = pair
    b.chmod(0o000)
    try:
        r = bsd.compare(a, b)
        assert r["verdict"] == bsd.INCONCLUSIVE
        assert r["verdict"] != bsd.MATCH
    finally:
        b.chmod(0o644)


def test_both_unreadable_is_inconclusive(tmp_path):
    r = bsd.compare(tmp_path / "nope-a", tmp_path / "nope-b")
    assert r["verdict"] == bsd.INCONCLUSIVE


# --------------------------------------------------------------------------- #
# Health mapping, judged by the real probe
# --------------------------------------------------------------------------- #

def test_match_is_healthy(pair, tmp_path):
    a, b = pair
    sp = tmp_path / "tick.json"
    bsd.write_state(sp, bsd.compare(a, b))
    payload = json.loads(sp.read_text())
    assert payload["status"] == "success" and payload["exit_code"] == 0
    assert judge(sp).ok


def test_drift_is_unhealthy(pair, tmp_path):
    a, b = pair
    b.write_text("different\n")
    sp = tmp_path / "tick.json"
    bsd.write_state(sp, bsd.compare(a, b))
    assert not judge(sp).ok, "drift must not read as healthy"


def test_inconclusive_is_unhealthy(pair, tmp_path):
    a, b = pair
    b.unlink()
    sp = tmp_path / "tick.json"
    bsd.write_state(sp, bsd.compare(a, b))
    assert json.loads(sp.read_text())["exit_code"] == 2
    assert not judge(sp).ok, "inconclusive must not read as healthy"


def test_pointer_avoids_the_explicit_error_scan_keys(pair, tmp_path):
    """`verdict` must not collide with error/errors/exit_status/cycle_error."""
    a, b = pair
    sp = tmp_path / "tick.json"
    bsd.write_state(sp, bsd.compare(a, b))
    payload = json.loads(sp.read_text())
    for forbidden in ("error", "errors", "cycle_error", "exit_status"):
        assert forbidden not in payload


def test_stale_pointer_is_reported_stale(pair, tmp_path):
    a, b = pair
    sp = tmp_path / "tick.json"
    bsd.write_state(sp, bsd.compare(a, b))
    payload = json.loads(sp.read_text())
    payload["completed_at_utc"] = "2026-01-01T00:00:00Z"
    sp.write_text(json.dumps(payload))
    assert judge(sp).stale, "a check that cannot go stale cannot fail"


# --------------------------------------------------------------------------- #
# Safety, atomicity, cost
# --------------------------------------------------------------------------- #

def test_compare_never_writes(pair):
    """It reads a root-owned directory in production; it must not mutate it."""
    a, b = pair
    before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in (a, b)}
    bsd.compare(a, b)
    for p, (mtime, content) in before.items():
        assert p.stat().st_mtime_ns == mtime and p.read_bytes() == content


def test_state_write_failure_is_not_fatal(pair, tmp_path, monkeypatch):
    a, b = pair
    monkeypatch.setattr(bsd, "write_atomic", lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    bsd.write_state(tmp_path / "tick.json", bsd.compare(a, b))  # must not raise


def test_atomic_write_leaves_no_temp(pair, tmp_path):
    a, b = pair
    sp = tmp_path / "nested" / "tick.json"
    bsd.write_state(sp, bsd.compare(a, b))
    assert sp.exists()
    assert not list(sp.parent.glob("*.tmp"))


def test_comparison_is_fast(pair):
    """NFR-004: under 5 seconds."""
    a, b = pair
    start = time.monotonic()
    bsd.compare(a, b)
    assert time.monotonic() - start < 5.0


def test_cli_exit_codes(pair, tmp_path, capsys):
    a, b = pair
    sp = tmp_path / "tick.json"
    assert bsd.main(["--repo-path", str(a), "--deployed-path", str(b), "--state-path", str(sp)]) == 0
    b.write_text("different\n")
    assert bsd.main(["--repo-path", str(a), "--deployed-path", str(b), "--state-path", str(sp)]) == 1
    b.unlink()
    assert bsd.main(["--repo-path", str(a), "--deployed-path", str(b), "--state-path", str(sp)]) == 2
    assert capsys.readouterr().out.strip().splitlines()[-1].startswith("SUMMARY: ")


# --------------------------------------------------------------------------- #
# Symlink and file-type safety (post-review).
#
# The deployed path is a NOPASSWD sudo target. If it were a symlink into
# claude's checkout, hashing through the link would report `match` while the
# deployed target was effectively claude-controlled — reporting clean in exactly
# the situation that recreates #899.
# --------------------------------------------------------------------------- #

def test_symlinked_deployed_copy_is_inconclusive_not_match(pair, tmp_path):
    a, b = pair
    b.unlink()
    b.symlink_to(a)  # identical bytes through the link
    r = bsd.compare(a, b)
    assert r["verdict"] == bsd.INCONCLUSIVE, "a symlinked sudo target must never read as match"
    assert "symlink" in r["detail"].lower()


def test_symlinked_repo_copy_is_inconclusive(pair, tmp_path):
    a, b = pair
    other = tmp_path / "other.sh"
    other.write_text(a.read_text())
    a.unlink()
    a.symlink_to(other)
    assert bsd.compare(a, b)["verdict"] == bsd.INCONCLUSIVE


def test_directory_in_place_of_a_file_is_inconclusive(pair, tmp_path):
    a, b = pair
    b.unlink()
    b.mkdir()
    r = bsd.compare(a, b)
    assert r["verdict"] == bsd.INCONCLUSIVE
    assert "regular file" in r["detail"]


def test_empty_files_still_compare(pair):
    """A zero-byte file is readable and regular — comparable, not inconclusive."""
    a, b = pair
    a.write_text("")
    b.write_text("")
    assert bsd.compare(a, b)["verdict"] == bsd.MATCH


# --------------------------------------------------------------------------- #
# Write-primitive containment and state-failure visibility
# --------------------------------------------------------------------------- #

def test_state_path_under_the_protected_directory_is_refused(pair):
    a, b = pair
    with pytest.raises(ValueError, match="refusing to write state"):
        bsd.write_state(Path("/data/services/backup/scripts/evil.json"), bsd.compare(a, b))


def test_state_write_failure_is_reported_not_swallowed(pair, tmp_path, monkeypatch, capsys):
    """A drift we cannot record must not leave a stale healthy pointer unremarked."""
    a, b = pair
    b.write_text("different\n")
    monkeypatch.setattr(bsd, "write_atomic",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("read-only fs")))
    ok = bsd.write_state(tmp_path / "tick.json", bsd.compare(a, b))
    assert ok is False
    assert "could not write state pointer" in capsys.readouterr().err


def test_clean_run_that_cannot_record_exits_nonzero(pair, tmp_path, monkeypatch):
    """Otherwise a stale success pointer keeps reading fresh."""
    a, b = pair
    monkeypatch.setattr(bsd, "write_atomic",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("read-only fs")))
    rc = bsd.main(["--repo-path", str(a), "--deployed-path", str(b),
                   "--state-path", str(tmp_path / "tick.json")])
    assert rc == 2, "an unrecordable clean run must not report success"


def test_default_state_path_is_not_in_the_root_owned_state_dir():
    """Regression guard for the first deploy's post-verification failure.

    The pointer was originally defaulted to
    /data/services/backup/state/script-drift-last-tick.json. That directory is
    root:root while this component runs as claude, so the write silently failed
    and the deploy failed post-verification, re-applying every tick.

    The lesson generalises past this one path: it is not enough to check that a
    state path is inside the backup source set — the process that writes it has
    to be able to write it. /data/services/backup/ itself is claude-owned, so a
    sibling directory works.
    """
    assert "/state/" not in str(bsd.DEFAULT_STATE_PATH), (
        "the backup service's state/ directory is root-owned; this component "
        "runs as claude and cannot write there"
    )
    assert str(bsd.DEFAULT_STATE_PATH).startswith("/data/services/"), (
        "the pointer must stay inside the Restic source set"
    )

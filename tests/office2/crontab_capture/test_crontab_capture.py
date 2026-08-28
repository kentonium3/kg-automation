"""Tests for the crontab capture helper (#895).

The refusal behaviours here are the reason the helper exists: it runs on a timer
and can therefore fire *during* the incident it protects against. A capture that
cannot refuse manufactures a confident empty backup, which is worse than no
backup at all.

No test touches a real crontab or a real /data path — the crontab reader is
injected and every path is under tmp_path.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[3] / "scripts" / "office2" / "crontab_capture.py"
)
_spec = importlib.util.spec_from_file_location("crontab_capture", _MODULE_PATH)
crontab_capture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(crontab_capture)


CRONTAB = (
    b"0 3 * * * sg docker -c /data/services/security-monitor/scripts/audit.sh\n"
    b"0 4 * * * sudo /data/services/backup/scripts/backup.sh\n"
    b"# Obsidian Sync heartbeat monitor (issue #158)\n"
    b"*/30 * * * * cd /home/claude/kg-automation && python3 scripts/obsidian/sync-heartbeat.py\n"
)


def reader(rc: int, out: bytes):
    return lambda: (rc, out)


@pytest.fixture
def paths(tmp_path):
    return tmp_path / "crontabs" / "claude.crontab", tmp_path / "last-tick.json"


def run(artifact, state, **kw):
    return crontab_capture.capture(
        artifact_path=artifact, state_path=state, user="claude", host="office2", **kw
    )


def load_state(state: Path) -> dict:
    return json.loads(state.read_text())


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #

def test_captures_crontab_and_writes_pointer(paths):
    artifact, state = paths
    rc = run(artifact, state, read_crontab=reader(0, CRONTAB))
    assert rc == 0
    assert artifact.exists()
    s = load_state(state)
    assert s["status"] == "success"
    assert s["exit_code"] == 0
    assert s["completed_at_utc"]
    assert s["artifact_changed"] is True


def test_body_below_header_is_byte_identical(paths):
    """FR-003. The whole file is deliberately not identical — it carries a header."""
    artifact, state = paths
    run(artifact, state, read_crontab=reader(0, CRONTAB))
    written = artifact.read_bytes()
    assert written != CRONTAB, "expected a provenance header"
    assert crontab_capture.strip_header(written) == CRONTAB


def test_artifact_is_reinstallable(paths):
    """Every header line is a comment, so `crontab <file>` works as-is."""
    artifact, state = paths
    run(artifact, state, read_crontab=reader(0, CRONTAB))
    raw = artifact.read_bytes()
    body = crontab_capture.strip_header(raw)
    header = raw[: len(raw) - len(body)]
    assert header, "no provenance header found"
    # EVERY header line must be a comment, or `crontab <file>` would reject it.
    for line in header.splitlines():
        assert line.startswith(b"#"), f"non-comment header line: {line!r}"
    assert body.startswith(b"0 3 * * *")


def test_user_comments_in_body_are_preserved(paths):
    """strip_header must not eat the user's own leading comments."""
    artifact, state = paths
    own = b"# my own note\n0 5 * * * echo hi\n"
    run(artifact, state, read_crontab=reader(0, own))
    assert crontab_capture.strip_header(artifact.read_bytes()) == own


# --------------------------------------------------------------------------- #
# FR-004 — refuse to destroy good state
# --------------------------------------------------------------------------- #

def test_empty_read_preserves_existing_artifact(paths):
    artifact, state = paths
    run(artifact, state, read_crontab=reader(0, CRONTAB))
    before = artifact.read_bytes()

    rc = run(artifact, state, read_crontab=reader(0, b"   \n"))

    assert rc == 1
    assert artifact.read_bytes() == before, "empty read must not overwrite a good artifact"
    s = load_state(state)
    assert s["status"] == "error"
    assert s["exit_code"] != 0, "a refusal must not read as healthy"


def test_failed_read_preserves_existing_artifact(paths):
    artifact, state = paths
    run(artifact, state, read_crontab=reader(0, CRONTAB))
    before = artifact.read_bytes()

    rc = run(artifact, state, read_crontab=reader(1, b""))

    assert rc == 1
    assert artifact.read_bytes() == before
    assert load_state(state)["status"] == "error"


def test_force_does_not_bypass_empty_guard(paths):
    """--force exists for the shrink guard only."""
    artifact, state = paths
    run(artifact, state, read_crontab=reader(0, CRONTAB))
    before = artifact.read_bytes()

    rc = run(artifact, state, read_crontab=reader(0, b""), force=True)

    assert rc == 1
    assert artifact.read_bytes() == before


# --------------------------------------------------------------------------- #
# Shrink guard
# --------------------------------------------------------------------------- #

def test_suspicious_truncation_is_refused(paths):
    artifact, state = paths
    run(artifact, state, read_crontab=reader(0, CRONTAB))
    before = artifact.read_bytes()

    truncated = b"0 3 * * * sg docker -c /data/ser"  # ~10% of original
    rc = run(artifact, state, read_crontab=reader(0, truncated))

    assert rc == 1
    assert artifact.read_bytes() == before
    assert load_state(state)["status"] == "error"


def test_modest_shrink_is_accepted(paths):
    """A real deletion of one job must still be captured."""
    artifact, state = paths
    run(artifact, state, read_crontab=reader(0, CRONTAB))

    smaller = b"".join(CRONTAB.splitlines(keepends=True)[:3])
    assert len(smaller) > len(CRONTAB) * crontab_capture.SHRINK_REFUSE_RATIO
    rc = run(artifact, state, read_crontab=reader(0, smaller))

    assert rc == 0
    assert crontab_capture.strip_header(artifact.read_bytes()) == smaller


def test_force_allows_a_large_shrink(paths):
    artifact, state = paths
    run(artifact, state, read_crontab=reader(0, CRONTAB))

    tiny = b"0 9 * * * echo only-job-left\n"
    rc = run(artifact, state, read_crontab=reader(0, tiny), force=True)

    assert rc == 0
    assert crontab_capture.strip_header(artifact.read_bytes()) == tiny


def test_first_run_is_never_a_shrink(paths):
    """No prior artifact means nothing to compare against; never refuse."""
    artifact, state = paths
    rc = run(artifact, state, read_crontab=reader(0, b"0 9 * * * echo hi\n"))
    assert rc == 0
    assert artifact.exists()


# --------------------------------------------------------------------------- #
# NFR-003 idempotency, NFR-005 size, atomicity
# --------------------------------------------------------------------------- #

def test_unchanged_input_leaves_artifact_untouched(paths):
    artifact, state = paths
    run(artifact, state, read_crontab=reader(0, CRONTAB))
    mtime = artifact.stat().st_mtime_ns
    content = artifact.read_bytes()

    rc = run(artifact, state, read_crontab=reader(0, CRONTAB))

    assert rc == 0
    assert artifact.stat().st_mtime_ns == mtime, "unchanged input must not churn the artifact"
    assert artifact.read_bytes() == content
    assert load_state(state)["artifact_changed"] is False


def test_pointer_advances_even_when_artifact_does_not(paths):
    """Freshness must reflect 'the job ran', not 'the file changed'."""
    artifact, state = paths
    run(artifact, state, read_crontab=reader(0, CRONTAB))
    first = load_state(state)["completed_at_utc"]

    run(artifact, state, read_crontab=reader(0, CRONTAB))
    second = load_state(state)["completed_at_utc"]

    assert second >= first
    assert load_state(state)["status"] == "success"


def test_artifact_stays_small(paths):
    """NFR-005: well under the 100KB per-snapshot budget."""
    artifact, state = paths
    run(artifact, state, read_crontab=reader(0, CRONTAB))
    assert artifact.stat().st_size < 100 * 1024


def test_write_failure_leaves_no_partial_artifact(paths, monkeypatch):
    artifact, state = paths
    run(artifact, state, read_crontab=reader(0, CRONTAB))
    before = artifact.read_bytes()

    real_replace = crontab_capture.os.replace

    def boom(src, dst):
        if str(dst).endswith("claude.crontab"):
            raise OSError("simulated failure")
        return real_replace(src, dst)

    monkeypatch.setattr(crontab_capture.os, "replace", boom)
    rc = run(artifact, state, read_crontab=reader(0, CRONTAB + b"0 7 * * * echo new\n"))

    assert rc == 1
    assert artifact.read_bytes() == before, "a failed write must not corrupt the artifact"
    leftovers = list(artifact.parent.glob("*.tmp"))
    assert not leftovers, f"temp files left behind: {leftovers}"


def test_dry_run_writes_nothing(paths):
    artifact, state = paths
    rc = run(artifact, state, read_crontab=reader(0, CRONTAB), dry_run=True)
    assert rc == 0
    assert not artifact.exists()
    assert not state.exists()


# --------------------------------------------------------------------------- #
# Byte fidelity (post-review). Text mode would silently break every case here:
# universal-newline translation mangles CRLF, and locale decoding raises on
# non-UTF-8. Byte identity of the body is FR-003, so these are the tests that
# make the contract real rather than incidental.
# --------------------------------------------------------------------------- #

def test_crlf_is_preserved(paths):
    artifact, state = paths
    crlf = b"0 3 * * * echo one\r\n0 4 * * * echo two\r\n"
    run(artifact, state, read_crontab=reader(0, crlf))
    assert crontab_capture.strip_header(artifact.read_bytes()) == crlf


def test_missing_trailing_newline_is_preserved(paths):
    artifact, state = paths
    body = b"0 3 * * * echo no-trailing-newline"
    run(artifact, state, read_crontab=reader(0, body))
    assert crontab_capture.strip_header(artifact.read_bytes()) == body


def test_non_utf8_bytes_survive(paths):
    """A crontab is bytes, not text. Latin-1 in a comment must not crash or mangle."""
    artifact, state = paths
    body = b"# note \xff\xfe\n0 3 * * * echo hi\n"
    rc = run(artifact, state, read_crontab=reader(0, body))
    assert rc == 0
    assert crontab_capture.strip_header(artifact.read_bytes()) == body


def test_utf8_multibyte_survives(paths):
    artifact, state = paths
    body = "# café ☕\n0 3 * * * echo hi\n".encode("utf-8")
    run(artifact, state, read_crontab=reader(0, body))
    assert crontab_capture.strip_header(artifact.read_bytes()) == body


def test_non_utf8_existing_artifact_still_writes_pointer(paths):
    """Regression: a non-UTF-8 artifact used to raise UnicodeDecodeError, escape
    the OSError handler, and abort before the pointer was written — hiding the
    failure from the canary."""
    artifact, state = paths
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"\xff\xfe garbage not utf-8\n")

    rc = run(artifact, state, read_crontab=reader(0, CRONTAB))

    assert rc == 0
    assert state.exists(), "pointer must be written even with an undecodable artifact"
    assert load_state(state)["status"] == "success"


def test_body_containing_the_sentinel_is_not_truncated(paths):
    """A crontab that happens to contain our sentinel mid-body must round-trip."""
    artifact, state = paths
    body = b"0 3 * * * echo hi\n" + crontab_capture.HEADER_SENTINEL.encode() + b"\n0 4 * * * echo bye\n"
    run(artifact, state, read_crontab=reader(0, body))
    assert crontab_capture.strip_header(artifact.read_bytes()) == body


def test_strip_header_leaves_foreign_content_alone():
    """Content we did not write is body, whole and unmodified."""
    foreign = b"# captured-by: something-else\n0 3 * * * echo hi\n"
    assert crontab_capture.strip_header(foreign) == foreign


# --------------------------------------------------------------------------- #
# Pointer advance (post-review): assert against a controlled clock, since
# `>=` on a one-second-precision timestamp proves nothing.
# --------------------------------------------------------------------------- #

def test_pointer_timestamp_actually_advances(paths, monkeypatch):
    artifact, state = paths
    clock = {"t": "2026-08-28T01:00:00Z"}
    monkeypatch.setattr(crontab_capture, "_utc_now_iso", lambda: clock["t"])

    run(artifact, state, read_crontab=reader(0, CRONTAB))
    first = load_state(state)["completed_at_utc"]
    mtime = artifact.stat().st_mtime_ns

    clock["t"] = "2026-08-28T02:00:00Z"
    run(artifact, state, read_crontab=reader(0, CRONTAB))
    second = load_state(state)["completed_at_utc"]

    assert first == "2026-08-28T01:00:00Z"
    assert second == "2026-08-28T02:00:00Z", "freshness anchor must advance on an unchanged run"
    assert artifact.stat().st_mtime_ns == mtime, "artifact must not churn"


# --------------------------------------------------------------------------- #
# CLI surface and stream discipline
# --------------------------------------------------------------------------- #

def test_invalid_flag_exits_2():
    with pytest.raises(SystemExit) as exc:
        crontab_capture.main(["--no-such-flag"])
    assert exc.value.code == 2


def test_help_exits_zero():
    with pytest.raises(SystemExit) as exc:
        crontab_capture.main(["--help"])
    assert exc.value.code == 0


def test_summary_is_the_final_stdout_line(paths, capsys):
    artifact, state = paths
    run(artifact, state, read_crontab=reader(0, CRONTAB))
    out = capsys.readouterr().out.strip().splitlines()
    assert out[-1].startswith("SUMMARY: "), f"last line was {out[-1]!r}"


def test_refusal_writes_error_to_stderr_and_summary_to_stdout(paths, capsys):
    artifact, state = paths
    run(artifact, state, read_crontab=reader(0, CRONTAB))
    capsys.readouterr()

    run(artifact, state, read_crontab=reader(0, b""))
    captured = capsys.readouterr()

    assert captured.err.startswith("ERROR: ") or "ERROR: " in captured.err
    assert captured.out.strip().splitlines()[-1].startswith("SUMMARY: ")
    assert "refused=true" in captured.out

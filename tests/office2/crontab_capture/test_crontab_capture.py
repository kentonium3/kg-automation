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


# --------------------------------------------------------------------------- #
# --emit-body (#906). Recovery must not require hand-reproducing a header
# stripping incantation — that duplication is what rotted and produced both a
# false verification failure and a slowly-corrupting recovery.
# --------------------------------------------------------------------------- #

def emit(artifact, capsysbinary):
    # Drain whatever the preceding capture run printed, so the assertion sees
    # only the emitter's output — the body must be the WHOLE of stdout.
    capsysbinary.readouterr()
    rc = crontab_capture.main(["--emit-body", "--artifact-path", str(artifact)])
    return rc, capsysbinary.readouterr()


def test_emit_body_round_trips_to_the_original_input(paths, capsysbinary):
    """Asserted against the ORIGINAL crontab -l input, not the emitter's output."""
    artifact, state = paths
    run(artifact, state, read_crontab=reader(0, CRONTAB))
    rc, out = emit(artifact, capsysbinary)
    assert rc == 0
    assert out.out == CRONTAB, "emitted body must equal the captured input byte-for-byte"


def test_emit_body_survives_crlf_and_non_utf8(paths, capsysbinary):
    artifact, state = paths
    body = b"# note \xff\r\n0 3 * * * echo hi\r\n"
    run(artifact, state, read_crontab=reader(0, body))
    rc, out = emit(artifact, capsysbinary)
    assert rc == 0 and out.out == body


def test_emit_body_handles_a_body_containing_the_sentinel(paths, capsysbinary):
    artifact, state = paths
    body = (b"0 3 * * * echo a\n"
            + crontab_capture.HEADER_SENTINEL.encode() + b"\n"
            + b"0 4 * * * echo b\n")
    run(artifact, state, read_crontab=reader(0, body))
    rc, out = emit(artifact, capsysbinary)
    assert rc == 0 and out.out == body


def test_emit_body_writes_nothing(paths, capsysbinary):
    """Used during recovery; the artifact and pointer must be untouched."""
    artifact, state = paths
    run(artifact, state, read_crontab=reader(0, CRONTAB))
    a_before = (artifact.stat().st_mtime_ns, artifact.read_bytes())
    s_before = (state.stat().st_mtime_ns, state.read_bytes())
    emit(artifact, capsysbinary)
    assert (artifact.stat().st_mtime_ns, artifact.read_bytes()) == a_before
    assert (state.stat().st_mtime_ns, state.read_bytes()) == s_before


# --- fail-closed ---------------------------------------------------------- #

def test_emit_body_refuses_a_missing_artifact(tmp_path, capsysbinary):
    rc = crontab_capture.main(["--emit-body", "--artifact-path", str(tmp_path / "nope")])
    assert rc != 0
    assert capsysbinary.readouterr().out == b""


def test_emit_body_refuses_an_empty_artifact(tmp_path, capsysbinary):
    p = tmp_path / "empty"
    p.write_bytes(b"")
    assert crontab_capture.main(["--emit-body", "--artifact-path", str(p)]) != 0
    assert capsysbinary.readouterr().out == b""


def test_emit_body_refuses_a_headerless_file(tmp_path, capsysbinary):
    """A foreign file is not our artifact; emitting it would install junk."""
    p = tmp_path / "foreign"
    p.write_bytes(b"0 3 * * * echo not-ours\n")
    assert crontab_capture.main(["--emit-body", "--artifact-path", str(p)]) != 0
    assert capsysbinary.readouterr().out == b""


def test_emit_body_refuses_a_truncated_header(tmp_path, capsysbinary):
    """First line matches but the sentinel is missing — refuse to guess."""
    p = tmp_path / "truncated"
    p.write_bytes(crontab_capture.HEADER_FIRST_LINE.encode() + b"\n0 3 * * * echo hi\n")
    assert crontab_capture.main(["--emit-body", "--artifact-path", str(p)]) != 0
    assert capsysbinary.readouterr().out == b""


def test_emit_body_rejects_conflicting_flags(paths, capsysbinary):
    artifact, _ = paths
    assert crontab_capture.main(
        ["--emit-body", "--dry-run", "--artifact-path", str(artifact)]) == 2


# --- the guard that would have caught the original defect ------------------ #

def test_emit_body_fails_if_the_header_format_drifts(paths, monkeypatch, capsysbinary):
    """SC-005.

    #906 was not a wrong pattern; it was an unenforced coupling between the
    header writer and a separate stripper. If someone changes the header format
    without updating the parser, recovery must BREAK LOUDLY rather than return
    something plausible. This test is the binding.
    """
    artifact, state = paths

    def header_without_sentinel(*, user, host, now):
        return f"# captured-by: crontab_capture.py\n# captured-at-utc: {now}\n".encode()

    monkeypatch.setattr(crontab_capture, "build_header", header_without_sentinel)
    rc_capture = run(artifact, state, read_crontab=reader(0, CRONTAB))
    capsysbinary.readouterr()

    # Prove the test is not passing vacuously via a missing/unreadable artifact:
    # the capture must have SUCCEEDED and written the drifted header plus body.
    assert rc_capture == 0, "capture must succeed, or the refusal below proves nothing"
    written = artifact.read_bytes()
    assert written.startswith(b"# captured-by: crontab_capture.py")
    assert crontab_capture.HEADER_SENTINEL.encode() not in written
    assert written.endswith(CRONTAB)

    rc = crontab_capture.main(["--emit-body", "--artifact-path", str(artifact)])
    assert rc != 0, "a drifted header format must fail recovery, not silently half-work"
    assert capsysbinary.readouterr().out == b""


def test_only_one_place_computes_where_the_header_ends(paths):
    """C-004: strip_header must delegate, not reimplement."""
    import inspect
    src = inspect.getsource(crontab_capture.strip_header)
    assert "split_header" in src
    assert crontab_capture.HEADER_SENTINEL not in src, "second implementation detected"


def test_emit_body_refuses_a_prefix_impostor(tmp_path, capsysbinary):
    """A foreign file that merely BEGINS with our header text must be refused.

    A prefix match would accept it and, because the sentinel appears later, emit
    only the tail — handing the operator a silently truncated crontab.
    """
    p = tmp_path / "impostor"
    p.write_bytes(
        b"# captured-by: crontab_capture.py.bak\n"
        b"0 3 * * * echo REAL-JOB-THAT-WOULD-BE-LOST\n"
        + crontab_capture.HEADER_SENTINEL.encode() + b"\n"
        b"0 4 * * * echo only-this-would-survive\n"
    )
    assert crontab_capture.main(["--emit-body", "--artifact-path", str(p)]) != 0
    assert capsysbinary.readouterr().out == b""


def test_emit_body_refuses_a_symlinked_artifact(paths, tmp_path, capsysbinary):
    """Output is piped into `crontab -`, so it becomes executable schedule."""
    artifact, state = paths
    run(artifact, state, read_crontab=reader(0, CRONTAB))
    link = tmp_path / "link.crontab"
    link.symlink_to(artifact)
    capsysbinary.readouterr()
    assert crontab_capture.main(["--emit-body", "--artifact-path", str(link)]) != 0
    assert capsysbinary.readouterr().out == b""


def test_split_header_requires_an_exact_first_line():
    """Unit-level guard on the prefix-vs-exact distinction."""
    good = (crontab_capture.HEADER_FIRST_LINE.encode() + b"\n"
            + crontab_capture.HEADER_SENTINEL.encode() + b"\nbody\n")
    assert crontab_capture.split_header(good) == (True, b"body\n")

    impostor = (crontab_capture.HEADER_FIRST_LINE.encode() + b".bak\n"
                + crontab_capture.HEADER_SENTINEL.encode() + b"\nbody\n")
    recognized, body = crontab_capture.split_header(impostor)
    assert recognized is False
    assert body == impostor, "unrecognised input must pass through whole"

"""Tests for the Vikunja release-route readiness and log-capture primitives
(#1087, WP02: T010, T011).

No network or docker: the opener, runner, clock and sleep are injected and
nothing sleeps for real. Every refusal has a same-fixture positive control,
and seeded secrets, names and titles never reach stdout or stderr.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

from scripts.deploy.vikunja_release import core, readiness

URL = "http://100.92.197.90:3456/api/v1/info"
RELEASE = "v2.7.1-670-420c7bcb75"
PRE = "v2.4.0"
SECRET = "password=hunter2"
TITLE = "Buy anniversary gift for Margot"
USER_NAME = "alice.wonderland"


class Clock:
    def __init__(self) -> None:
        self.t = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


def _info(version: str) -> str:
    # The real /api/v1/info carries more fields; seed private-looking ones.
    return json.dumps({"version": version, "frontend_url": "https://todo.example/",
                       "motd": f"{TITLE} {SECRET}", "registration_enabled": False})


def http(status: int, body: str, cost: float = 0.0):
    return ("http", status, body, cost)


def curl_rc(code: int, cost: float = 0.0):
    return ("rc", code, cost)


HANG = ("hang",)


class Curl:
    """A fake runner for the curl probe. Steps: ``http(status, body, cost)``
    (curl exit 0, body plus the ``-w`` status line), ``curl_rc(code)`` (a
    curl error), or ``HANG`` (the process outlives core.run's timeout, which
    costs that whole timeout on the clock). The last step repeats."""

    def __init__(self, clock: Clock, script: list) -> None:
        self.clock = clock
        self.script = list(script)
        self.calls: list[tuple[list[str], dict]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))
        step = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(step, BaseException):
            raise step
        if step[0] == "hang":
            self.clock.t += kwargs["timeout"]
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
        if step[0] == "rc":
            self.clock.t += step[2]
            return subprocess.CompletedProcess(argv, step[1], "", f"curl: ({step[1]}) {SECRET}\n")
        _, status, body, cost = step
        self.clock.t += cost
        return subprocess.CompletedProcess(argv, 0, f"{body}\n{status}", "")

    @property
    def max_times(self) -> list[int]:
        return [int(a[a.index("--max-time") + 1]) for a, _ in self.calls]

    @property
    def timeouts(self) -> list[float]:
        return [kw["timeout"] for _, kw in self.calls]


def _wait(curl: Curl, clock: Clock, expect: str = RELEASE, seconds: float = 180.0) -> str:
    return readiness.wait_ready(URL, expect, core.Deadline(seconds, clock=clock), runner=curl, sleep=clock.sleep)


# ---------------------------------------------------------------------------
# T010 — wait_ready
# ---------------------------------------------------------------------------


def test_ready_after_a_503_then_a_200_and_the_curl_argv(capsys):
    clock = Clock()
    curl = Curl(clock, [http(503, "busy"), http(200, _info(RELEASE))])
    assert _wait(curl, clock) == RELEASE
    assert curl.calls[0][0] == ["curl", "-sS", "--max-time", "5", "--max-filesize", "65536",
                                "-o", "-", "-w", "\n%{http_code}", URL]
    assert curl.timeouts == [7, 7]  # core.run kills at --max-time + 2
    assert all(kw["stdin"] is subprocess.DEVNULL for _, kw in curl.calls)
    assert clock.sleeps == [5.0]
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_wrong_version_refuses_and_the_right_one_passes():
    clock = Clock()
    with pytest.raises(core.Fail) as exc:
        _wait(Curl(clock, [http(200, _info(PRE))]), clock)
    assert exc.value.code == "READY_WRONG_VERSION"
    # Positive control: the same response, expecting the version it reports.
    clock = Clock()
    assert _wait(Curl(clock, [http(200, _info(PRE))]), clock, expect=PRE) == PRE


def test_a_hung_probe_is_killed_and_the_deadline_is_a_hard_bound():
    """A probe that never finishes (a trickling or hung server) is killed by
    core.run at --max-time + 2, so the whole wait ends within deadline + 2 s."""
    clock = Clock()
    curl = Curl(clock, [HANG])
    with pytest.raises(core.Fail) as exc:
        _wait(curl, clock, seconds=60.0)
    assert exc.value.code == "READY_TIMEOUT"
    assert clock.t <= 60.0 + 2.0 + 1e-9
    assert all(t == m + 2 for t, m in zip(curl.timeouts, curl.max_times))
    assert all(1 <= m <= 5 for m in curl.max_times)
    # Control: same fixture, one hang and then an on-time answer.
    clock = Clock()
    curl = Curl(clock, [HANG, http(200, _info(RELEASE))])
    assert _wait(curl, clock, seconds=60.0) == RELEASE
    assert clock.t == pytest.approx(7.0 + 5.0)


def test_a_late_success_is_a_timeout_not_ready():
    clock = Clock()
    with pytest.raises(core.Fail) as exc:
        _wait(Curl(clock, [http(200, _info(RELEASE), cost=6.0)]), clock, seconds=5.0)
    assert exc.value.code == "READY_TIMEOUT"
    # Control: the same answer, delivered inside the budget.
    clock = Clock()
    assert _wait(Curl(clock, [http(200, _info(RELEASE), cost=4.0)]), clock, seconds=5.0) == RELEASE


@pytest.mark.parametrize("code", [28, 7, 52, 63], ids=["timeout", "refused", "empty-reply", "too-large"])
def test_curl_errors_are_retried(code):
    clock = Clock()
    assert _wait(Curl(clock, [curl_rc(code), http(200, _info(RELEASE))]), clock) == RELEASE
    assert clock.sleeps == [5.0]
    clock = Clock()
    with pytest.raises(core.Fail) as exc:
        _wait(Curl(clock, [curl_rc(code)]), clock, seconds=20.0)
    assert exc.value.code == "READY_TIMEOUT"


def test_deadline_expiry_with_an_injected_clock():
    clock = Clock()
    curl = Curl(clock, [http(503, "busy")])
    with pytest.raises(core.Fail) as exc:
        _wait(curl, clock)
    assert exc.value.code == "READY_TIMEOUT"
    assert len(curl.calls) == 36  # every 5 s for 180 s
    assert sum(clock.sleeps) == pytest.approx(180.0)


def test_no_probe_starts_with_under_a_second_left():
    clock = Clock()
    deadline = core.Deadline(180.0, clock=clock)
    clock.t = 179.5
    curl = Curl(clock, [http(200, _info(RELEASE))])
    with pytest.raises(core.Fail) as exc:
        readiness.wait_ready(URL, RELEASE, deadline, runner=curl, sleep=clock.sleep)
    assert exc.value.code == "READY_TIMEOUT"
    assert curl.calls == []
    # Control: 2.5 s left -> one probe, --max-time capped to 2 (killed at 4).
    clock.t = 177.5
    assert readiness.wait_ready(URL, RELEASE, deadline, runner=curl, sleep=clock.sleep) == RELEASE
    assert curl.max_times == [2] and curl.timeouts == [4]


@pytest.mark.parametrize("out", [
    http(200, "<html>maintenance</html>"),
    http(200, json.dumps({"versionx": RELEASE})),
    http(200, json.dumps([RELEASE])),
    http(204, _info(RELEASE)),
    http(200, json.dumps({"version": RELEASE, "pad": "x" * (70 * 1024)})),
], ids=["html", "no-version", "not-object", "not-200", "oversize"])
def test_unready_answers_are_retried_then_ready(out):
    clock = Clock()
    assert _wait(Curl(clock, [out, http(200, _info(RELEASE))]), clock) == RELEASE
    assert clock.sleeps == [5.0]
    clock = Clock()
    with pytest.raises(core.Fail) as exc:
        _wait(Curl(clock, [out]), clock, seconds=20.0)
    assert exc.value.code == "READY_TIMEOUT"


def test_output_without_a_status_line_is_retried():
    clock = Clock()

    def no_status(argv, **kw):
        return subprocess.CompletedProcess(argv, 0, _info(RELEASE), "")

    with pytest.raises(core.Fail) as exc:
        readiness.wait_ready(URL, RELEASE, core.Deadline(10, clock=clock), runner=no_status, sleep=clock.sleep)
    assert exc.value.code == "READY_TIMEOUT"
    clock = Clock()
    assert _wait(Curl(clock, [http(200, _info(RELEASE))]), clock, seconds=10) == RELEASE


def test_a_missing_curl_refuses_with_a_stable_code():
    clock = Clock()
    with pytest.raises(core.Fail) as exc:
        _wait(Curl(clock, [FileNotFoundError("curl")]), clock)
    assert exc.value.code == "READY_PROBE_UNAVAILABLE"
    clock = Clock()
    assert _wait(Curl(clock, [http(200, _info(RELEASE))]), clock) == RELEASE


def test_the_body_and_curl_errors_are_never_returned_or_printed(capsys):
    clock = Clock()
    result = _wait(Curl(clock, [curl_rc(7), http(503, f"busy {SECRET}"), http(200, _info(RELEASE))]), clock)
    assert result == RELEASE
    out = capsys.readouterr()
    for leak in (SECRET, TITLE, "todo.example"):
        assert leak not in out.out + out.err + result


def test_invalid_inputs_are_rejected():
    clock = Clock()
    curl = Curl(clock, [http(200, _info(RELEASE))])
    with pytest.raises(ValueError):
        readiness.wait_ready("file:///etc/passwd", RELEASE, core.Deadline(5, clock=clock), runner=curl)
    with pytest.raises(ValueError):
        readiness.wait_ready(f"{URL} -o /tmp/x", RELEASE, core.Deadline(5, clock=clock), runner=curl)
    with pytest.raises(ValueError):
        readiness.wait_ready(URL, f"{RELEASE} {SECRET}", core.Deadline(5, clock=clock), runner=curl)
    assert curl.calls == []
    # Positive control: same runner, valid URL and version.
    assert readiness.wait_ready(URL, RELEASE, core.Deadline(5, clock=clock), runner=curl,
                                sleep=clock.sleep) == RELEASE


# ---------------------------------------------------------------------------
# T011 — capture_logs / migration_ok
# ---------------------------------------------------------------------------

LOG_ARGV = ["docker", "logs", "--timestamps", "--tail", "20000", "vikunja"]
#: Real-shaped lines: the release build logs logfmt with a quoted msg
#: (captured from the release-build rehearsal, synthetic data), and
#: ``docker logs --timestamps`` prepends an RFC 3339 nano timestamp.
_TS = "2026-10-29T19:04:0{n}.741000000Z "
_RRULE_MSG = ("RRULE migration: 1234 legacy-repeat task(s) processed — 1200 converted, 30 already had an "
              "RRULE, 4 unconvertible (originals backed up to task_repeat_legacy_backup); 17 row(s) used the "
              "server zone")
REAL_RRULE_LINE = f'time=2026-10-29T15:04:02.741-04:00 level=INFO msg="{_RRULE_MSG}"'
REAL_OK_LINE = 'time=2026-10-29T15:04:03.102-04:00 level=INFO msg="Ran all migrations successfully."'
SEEDED_LOG = (
    _TS.format(n=1) + 'time=2026-10-29T15:04:01.003-04:00 level=INFO msg="Using config file: /etc/vikunja/config.yml"\n'
    + _TS.format(n=2) + 'time=2026-10-29T15:04:02.500-04:00 level=WARN msg="RRULE migration: task 42 has legacy '
    f'repeat (after=7, mode=3) that did not convert; left empty (original preserved in task_repeat_legacy_backup)" '
    f'title="{TITLE}" owner={USER_NAME}\n'
    + _TS.format(n=2) + REAL_RRULE_LINE + "\n"
    + _TS.format(n=3) + f'time=2026-10-29T15:04:03.001-04:00 level=DEBUG msg="db connect" dsn="{SECRET}"\n'
    + _TS.format(n=3) + REAL_OK_LINE + "\n"
)
COUNTS = {"processed": 1234, "converted": 1200, "already_rrule": 30, "unconvertible": 4, "server_zone": 17}


def _emit_code(text: str, *, stderr: str = "", rc: int = 0) -> str:
    """Python source for a stand-in ``docker logs`` child: writes *text* to
    stdout, *stderr* to stderr, exits *rc*."""
    return (f"import sys\nsys.stdout.write({text!r})\nsys.stdout.flush()\n"
            f"sys.stderr.write({stderr!r})\nsys.stderr.flush()\nsys.exit({rc})\n")


ENDLESS = "import sys\nb = b'x' * 65536\nwhile True:\n    sys.stdout.buffer.write(b)\n    sys.stdout.flush()\n"
SILENT = "import time\ntime.sleep(60)\n"


class Spawn:
    """A ``Popen`` stand-in that records the docker argv and kwargs, then
    starts a real (tiny, local) Python child in its place: no docker."""

    def __init__(self, code: str | None = None, raise_exc: BaseException | None = None) -> None:
        self.code = code
        self.raise_exc = raise_exc
        self.argv: list[str] | None = None
        self.kwargs: dict | None = None
        self.proc: subprocess.Popen | None = None

    def __call__(self, argv, **kwargs):
        self.argv, self.kwargs = list(argv), kwargs
        if self.raise_exc is not None:
            raise self.raise_exc
        self.proc = subprocess.Popen([sys.executable, "-c", self.code], **kwargs)
        return self.proc


def _capture(spawn: Spawn, dest: Path, **kw) -> Path | None:
    return readiness.capture_logs(spawn, "vikunja", dest, **kw)


def test_capture_streams_into_a_private_file_and_prints_nothing(tmp_path, capsys):
    spawn = Spawn(_emit_code(SEEDED_LOG, stderr=f"stderr line {USER_NAME}\n"))
    dest = tmp_path / "failed"
    path = _capture(spawn, dest)
    assert path is not None and path.parent == dest
    assert stat.S_IMODE(dest.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    text = path.read_text()
    assert TITLE in text and SECRET in text and USER_NAME in text  # kept privately; stderr merged
    assert spawn.argv == LOG_ARGV
    assert spawn.kwargs == {"stdin": subprocess.DEVNULL, "stdout": subprocess.PIPE, "stderr": subprocess.STDOUT}
    assert spawn.proc.returncode == 0
    out = capsys.readouterr()
    for leak in (SECRET, TITLE, USER_NAME):
        assert leak not in out.out + out.err


def test_capture_stops_reading_at_the_cap_and_kills_the_child(tmp_path, monkeypatch):
    read_sizes: list[int] = []
    real_read = readiness._os_read

    def counting_read(fd, n):
        data = real_read(fd, n)
        read_sizes.append(len(data))
        return data

    monkeypatch.setattr(readiness, "_os_read", counting_read)
    cap = 300_000
    spawn = Spawn(ENDLESS)  # would write forever
    path = _capture(spawn, tmp_path / "f", max_bytes=cap, timeout=20)
    assert path is not None
    assert sum(read_sizes) == cap  # never read past the cap: memory stays bounded
    assert max(read_sizes) <= 64 * 1024
    assert path.stat().st_size == cap
    assert spawn.proc.returncode is not None and spawn.proc.returncode < 0  # killed
    # Control: same capture path, a child that finishes under the cap.
    read_sizes.clear()
    path = _capture(Spawn(_emit_code("short log\n")), tmp_path / "f", max_bytes=cap)
    assert path is not None and path.read_text() == "short log\n"
    assert sum(read_sizes) == len("short log\n")


def test_capture_times_out_on_a_silent_child(tmp_path):
    spawn = Spawn(SILENT)
    started = time.monotonic()
    assert _capture(spawn, tmp_path / "f", timeout=0.5) is None
    assert time.monotonic() - started < 5.0  # the deadline, not the child, ended it
    assert spawn.proc.returncode is not None and spawn.proc.returncode < 0  # killed
    # Control: same destination and timeout, a child that answers in time.
    assert _capture(Spawn(_emit_code(SEEDED_LOG)), tmp_path / "f", timeout=10) is not None


def test_capture_deadline_is_monotonic_and_injected(tmp_path):
    ticks = iter([0.0] + [100.0] * 50)
    spawn = Spawn(SILENT)
    assert _capture(spawn, tmp_path / "f", timeout=30, clock=lambda: next(ticks)) is None
    assert spawn.proc.returncode is not None and spawn.proc.returncode < 0
    assert _capture(Spawn(_emit_code("ok\n")), tmp_path / "f", timeout=30) is not None


@pytest.mark.parametrize("spawn", [
    Spawn(_emit_code("", stderr="Error: No such container: vikunja\n", rc=1)),
    Spawn(raise_exc=FileNotFoundError("docker")),
    Spawn(raise_exc=RuntimeError("anything")),
], ids=["docker-error", "no-docker", "unexpected"])
def test_capture_failure_returns_none_and_never_raises(tmp_path, spawn, capsys):
    assert _capture(spawn, tmp_path / "f") is None
    assert capsys.readouterr().out == ""
    # Positive control: same destination, a working child.
    assert _capture(Spawn(_emit_code(SEEDED_LOG)), tmp_path / "f") is not None


def test_capture_to_an_unwritable_destination_returns_none(tmp_path):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    spawn = Spawn(_emit_code(SEEDED_LOG))
    assert _capture(spawn, blocker) is None
    assert spawn.argv is None  # refused before docker is started
    assert _capture(Spawn(_emit_code(SEEDED_LOG)), tmp_path / "ok") is not None


def test_capture_refuses_an_unsafe_destination(tmp_path):
    target = tmp_path / "elsewhere"
    target.mkdir()
    target.chmod(0o700)
    link = tmp_path / "failed"
    link.symlink_to(target)
    assert _capture(Spawn(_emit_code(SEEDED_LOG)), link) is None
    assert list(target.iterdir()) == []
    loose = tmp_path / "loose"
    loose.mkdir()
    loose.chmod(0o755)
    assert _capture(Spawn(_emit_code(SEEDED_LOG)), loose) is None
    assert list(loose.iterdir()) == []
    assert stat.S_IMODE(loose.stat().st_mode) == 0o755  # refused, not repaired
    # Positive control: an absent destination is created 0700.
    assert _capture(Spawn(_emit_code(SEEDED_LOG)), tmp_path / "fresh") is not None


def test_capture_refuses_an_unsafe_container_name(tmp_path):
    spawn = Spawn(_emit_code(SEEDED_LOG))
    assert readiness.capture_logs(spawn, "vikunja; rm -rf /", tmp_path / "f") is None
    assert spawn.argv is None
    # Positive control: same spawn and destination, the real name.
    assert readiness.capture_logs(spawn, "vikunja", tmp_path / "f") is not None


def _log_file(tmp_path: Path, text: str, name: str = "log") -> Path | None:
    return _capture(Spawn(_emit_code(text)), tmp_path / name)


def test_migration_ok_reports_bool_and_digit_counts_only(tmp_path, capsys):
    ok, counts = readiness.migration_ok(_log_file(tmp_path, SEEDED_LOG))
    assert ok is True
    assert counts == COUNTS
    assert all(type(v) is int for v in counts.values())
    out = capsys.readouterr()
    for leak in (SECRET, TITLE, USER_NAME):
        assert leak not in out.out + out.err + repr(counts)


def test_migration_ok_is_false_without_the_success_line(tmp_path):
    without = SEEDED_LOG.replace("Ran all migrations successfully.", "Migration 2026 failed: boom")
    ok, counts = readiness.migration_ok(_log_file(tmp_path, without, "a"))
    assert ok is False and counts == COUNTS
    # A title that merely contains the phrase mid-line does not count.
    titled = without + (_TS.format(n=6) + 'time=2026-10-29T15:04:06.000-04:00 level=INFO '
                        f'msg="created task \'Ran all migrations successfully.\' {TITLE}"\n')
    ok, _ = readiness.migration_ok(_log_file(tmp_path, titled, "b"))
    assert ok is False
    # Positive control: the seeded log.
    ok, _ = readiness.migration_ok(_log_file(tmp_path, SEEDED_LOG, "c"))
    assert ok is True


def test_migration_ok_without_a_summary_line_has_no_counts(tmp_path):
    lines = [ln for ln in SEEDED_LOG.splitlines(keepends=True) if "legacy-repeat task(s) processed" not in ln]
    ok, counts = readiness.migration_ok(_log_file(tmp_path, "".join(lines)))
    assert ok is True and counts is None
    # Control: same log with the summary line.
    assert readiness.migration_ok(_log_file(tmp_path, SEEDED_LOG, "b"))[1] == COUNTS


def test_migration_ok_on_a_missing_log(tmp_path):
    assert readiness.migration_ok(None) == (False, None)
    assert readiness.migration_ok(tmp_path / "absent.log") == (False, None)
    path = tmp_path / "present.log"
    Path(path).write_text(SEEDED_LOG)
    assert readiness.migration_ok(path) == (True, COUNTS)


def test_capture_closes_the_log_descriptor_when_fchmod_fails(tmp_path, monkeypatch):
    dest = tmp_path / "f"
    dbsafety_root = readiness.open_private_root(dest, code="LOGS_ROOT")  # pre-create: no root fchmod
    os.close(dbsafety_root)
    opened: list[int] = []
    real_open, real_fchmod = os.open, os.fchmod

    def recording_open(path, flags, *a, **kw):
        fd = real_open(path, flags, *a, **kw)
        if str(path).endswith(".log"):
            opened.append(fd)
        return fd

    def failing_fchmod(fd, mode):
        if fd in opened:
            raise PermissionError("injected")
        return real_fchmod(fd, mode)

    monkeypatch.setattr(os, "open", recording_open)
    monkeypatch.setattr(os, "fchmod", failing_fchmod)
    spawn = Spawn(_emit_code(SEEDED_LOG))
    assert _capture(spawn, dest) is None
    assert len(opened) == 1
    with pytest.raises(OSError):
        os.fstat(opened[0])  # closed, not leaked
    assert spawn.argv is None  # docker was never started
    monkeypatch.undo()
    # Control: same destination without the fault.
    assert _capture(Spawn(_emit_code(SEEDED_LOG)), dest) is not None


@pytest.mark.parametrize("mask", [0o400, 0o277, 0o022], ids=["0400", "0277", "0022-control"])
def test_capture_under_a_restrictive_umask(tmp_path, mask):
    previous = os.umask(mask)
    try:
        path = _capture(Spawn(_emit_code(SEEDED_LOG)), tmp_path / "failed")
    finally:
        os.umask(previous)
    assert path is not None
    assert stat.S_IMODE((tmp_path / "failed").stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert readiness.migration_ok(path) == (True, COUNTS)



# ---------------------------------------------------------------------------
# The real log shape (post-merge mission review RISK-1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("prefix", ["", "2026-10-29T19:04:03.102000000Z "], ids=["bare", "docker-timestamps"])
def test_the_real_logfmt_lines_are_recognised(tmp_path, prefix):
    path = tmp_path / "real.log"
    path.write_text(prefix + REAL_RRULE_LINE + "\n" + prefix + REAL_OK_LINE + "\n")
    assert readiness.migration_ok(path) == (True, COUNTS)


def test_the_old_unquoted_shape_is_not_what_production_emits(tmp_path):
    """The earlier fixtures used an unquoted, unstructured shape that the
    old ``endswith`` check matched; the build emits quoted logfmt, which it
    never matched. Now the real line passes and the unstructured one does
    not."""
    old_shape = tmp_path / "old.log"
    old_shape.write_text("2026-10-30T12:00:03Z INFO Ran all migrations successfully.\n")
    assert readiness.migration_ok(old_shape) == (False, None)
    real = tmp_path / "real.log"
    real.write_text(REAL_OK_LINE + "\n")
    assert readiness.migration_ok(real) == (True, None)
    # And the real line does not end with the bare phrase (the old check's blind spot).
    assert not REAL_OK_LINE.endswith(readiness.MIGRATIONS_OK_TEXT)


@pytest.mark.parametrize("line", [
    'time=t level=INFO msg="created task \'Ran all migrations successfully.\'"',
    'time=t level=INFO msg="x\\" level=INFO msg=\\"Ran all migrations successfully."',
    'time=t level=INFO msg="title: Ran all migrations successfully."',
    'time=t level=DEBUG msg="Ran all migrations successfully."',
    'time=t level=INFO title="Ran all migrations successfully."',
    'garbage msg="Ran all migrations successfully." level=INFO',
], ids=["quoted-in-msg", "escaped-key-injection", "suffix", "wrong-level", "other-key", "not-logfmt"])
def test_a_title_injection_never_counts_as_success(tmp_path, line):
    path = tmp_path / "inj.log"
    path.write_text(line + "\n")
    assert readiness.migration_ok(path)[0] is False
    # Control: the same file with the real success line appended.
    path.write_text(line + "\n" + REAL_OK_LINE + "\n")
    assert readiness.migration_ok(path)[0] is True


def test_slog_json_records_are_also_read(tmp_path):
    path = tmp_path / "json.log"
    path.write_text(json.dumps({"time": "t", "level": "INFO", "msg": _RRULE_MSG}) + "\n"
                    + json.dumps({"time": "t", "level": "INFO", "msg": readiness.MIGRATIONS_OK_TEXT}) + "\n")
    assert readiness.migration_ok(path) == (True, COUNTS)
    path.write_text(json.dumps({"time": "t", "level": "INFO", "msg": "Ran all migrations successfully. x"}) + "\n")
    assert readiness.migration_ok(path) == (False, None)

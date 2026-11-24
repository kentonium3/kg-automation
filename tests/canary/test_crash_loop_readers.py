"""Tests for scripts.canary.crash_loop_readers (mission #1133, WP03 T015).

Every test injects a fake ``run`` keyed by argv prefix and a fake clock; no
test calls the real ``systemctl`` or ``docker``.
"""

from __future__ import annotations

import json
import random
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from scripts.canary import crash_loop_readers as readers
from scripts.canary.crash_loop_model import SCOPES, ScopeReading
from scripts.canary.crash_loop_readers import (
    DOCKER_CONFIG_DIR,
    DOCKER_HOST,
    DOCKER_INSPECT_FORMAT,
    CommandResult,
    Deadline,
    ReaderError,
    build_unit_observations,
    parse_list_units,
    parse_show,
    read_all_scopes,
    read_boot_id,
    read_container_scope,
    read_systemd_scope,
)

FIXTURES = Path(__file__).parent / "fixtures" / "crash_loop"
BOOT = "5f0c6f0e-6c43-4b8e-9d43-0d6f3f6b8a11"

SYSTEMD_LIST_TAIL = (
    "list-units",
    "--type=service",
    "--all",
    "--plain",
    "--no-legend",
    "--no-pager",
)
SHOW_PROPS = ("-p", "Id,Restart,NRestarts,ActiveState,SubState,LoadState", "--")


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Fakes.
# --------------------------------------------------------------------------- #
class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


Response = (
    CommandResult
    | BaseException
    | Callable[[Sequence[str], Mapping[str, str], float], CommandResult]
)


@dataclass
class Call:
    argv: list[str]
    env: dict[str, str]
    timeout: float
    argv_type: type


@dataclass
class FakeRun:
    """Answers by the longest matching argv prefix; records every call."""

    responses: dict[tuple[str, ...], Response] = field(default_factory=dict)
    calls: list[Call] = field(default_factory=list)

    def on(self, prefix: Sequence[str], response: Response) -> FakeRun:
        self.responses[tuple(prefix)] = response
        return self

    def __call__(
        self, argv: Sequence[str], env: Mapping[str, str], timeout: float
    ) -> CommandResult:
        self.calls.append(Call(list(argv), dict(env), timeout, type(argv)))
        best: tuple[str, ...] | None = None
        for prefix in self.responses:
            if tuple(argv[: len(prefix)]) == prefix and (
                best is None or len(prefix) > len(best)
            ):
                best = prefix
        if best is None:
            raise AssertionError(f"unexpected command: {argv!r}")
        response = self.responses[best]
        if isinstance(response, BaseException):
            raise response
        if isinstance(response, CommandResult):
            return response
        return response(argv, env, timeout)

    def argvs(self) -> list[list[str]]:
        return [c.argv for c in self.calls]


def ok(stdout: str) -> CommandResult:
    return CommandResult(returncode=0, stdout=stdout, stderr="")


def systemd_run(scope: str, list_out: str, show_out: str) -> FakeRun:
    base = ["systemctl"] + (["--user"] if scope == "user" else [])
    return (
        FakeRun()
        .on(base + ["list-units"], ok(list_out))
        .on(base + ["show"], ok(show_out))
    )


def docker_run(ps_out: str, inspect_out: str) -> FakeRun:
    return (
        FakeRun()
        .on(["docker", "ps"], ok(ps_out))
        .on(["docker", "inspect"], ok(inspect_out))
    )


def list_rows(*rows: tuple[str, str]) -> str:
    return "".join(
        f"{unit}  {load}  active  running  Some description\n" for unit, load in rows
    )


def show_block(
    unit: str,
    *,
    restart: str | None = "always",
    nrestarts: str | None = "0",
    load: str = "loaded",
    active: str = "active",
    sub: str = "running",
) -> str:
    lines = [
        f"Id={unit}",
        f"LoadState={load}",
        f"ActiveState={active}",
        f"SubState={sub}",
    ]
    if restart is not None:
        lines.append(f"Restart={restart}")
    if nrestarts is not None:
        lines.append(f"NRestarts={nrestarts}")
    return "\n".join(lines) + "\n"


def show_out(*blocks: str) -> str:
    return "\n".join(blocks)


def deadline(clock: FakeClock | None = None, budget: float = 6.0) -> Deadline:
    return Deadline(clock or FakeClock(), budget)


def watched(reading: ScopeReading) -> dict[str, int]:
    return {o.name: o.restart_count for o in reading.observations}


DOCKER_IDS = fixture("docker-ps.txt").split()

# (case id, raw inspect name) pairs that violate Docker's name grammar.
MALFORMED_NAMES: list[tuple[str, str]] = [
    ("space", "/bad name"),
    ("no-leading-slash", "modest_colden"),
    ("leading-dash", "/-modest"),
    ("leading-dot", "/.modest"),
    ("nested-slash", "/a/b"),
    ("non-ascii", "/café"),
    ("trailing-newline", "/modest\n"),
    ("slash-only", "/"),
    ("double-slash", "//modest"),
]


def json_name(name: str) -> str:
    return json.dumps(name)


# --------------------------------------------------------------------------- #
# T011: deadline, runner, timeouts.
# --------------------------------------------------------------------------- #
class TestDeadline:
    def test_remaining_counts_down_and_never_goes_negative(self) -> None:
        clock = FakeClock()
        d = Deadline(clock, 6.0)
        assert d.remaining() == 6.0 and not d.expired()
        clock.advance(4.5)
        assert d.remaining() == pytest.approx(1.5)
        clock.advance(10)
        assert d.remaining() == 0.0 and d.expired()

    def test_per_command_timeout_is_capped_at_three_seconds_and_remaining(self) -> None:
        clock = FakeClock()
        d = Deadline(clock, 6.0)
        assert readers._timeout(d) == 3.0
        clock.advance(4.0)
        assert readers._timeout(d) == pytest.approx(2.0)
        clock.advance(5.0)
        assert readers._timeout(d) == 0.0


def test_default_run_uses_argv_list_and_no_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_subprocess_run(
        args: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        seen["args"] = args
        seen.update(kwargs)
        return subprocess.CompletedProcess(
            args=args, returncode=3, stdout="o", stderr="e"
        )

    # crash_loop_readers calls subprocess.run through the module attribute.
    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)
    result = readers.default_run(("systemctl", "show"), {"PATH": "/usr/bin:/bin"}, 2.5)
    assert result == CommandResult(3, "o", "e")
    assert seen["args"] == ["systemctl", "show"]
    assert seen["env"] == {"PATH": "/usr/bin:/bin"}
    assert seen["timeout"] == 2.5
    assert (
        seen["capture_output"] is True
        and seen["text"] is True
        and seen["check"] is False
    )
    assert "shell" not in seen


def test_module_source_has_no_shell_journal_or_credential_paths() -> None:
    source = Path(readers.__file__).read_text(encoding="utf-8")
    assert "shell=True" not in source
    assert "journalctl" not in source
    for needle in ("config.json", ".docker/", "credentials", "/etc/shadow", "sudo"):
        assert needle not in source


def test_docker_inspect_format_constant_is_exact() -> None:
    assert DOCKER_INSPECT_FORMAT == (
        "{{json .Id}}|{{json .Name}}|{{.RestartCount}}"
        "|{{json .HostConfig.RestartPolicy.Name}}|{{json .State.Status}}"
    )


# --------------------------------------------------------------------------- #
# T012: parsers.
# --------------------------------------------------------------------------- #
class TestParseListUnits:
    def test_real_system_fixture(self) -> None:
        units, excluded = parse_list_units(fixture("system-list-units.txt"))
        assert "obsidian-sync.service" in units and "snapd.service" in units
        assert not {
            "auditd.service",
            "connman.service",
            "console-screen.service",
        } & set(units)
        assert excluded == 3
        assert len(units) == 8

    def test_real_user_fixture_with_utf8_description(self) -> None:
        units, excluded = parse_list_units(fixture("user-list-units.txt"))
        assert "credential-health-check.service" in units
        assert "openclaw-gateway.service" in units
        assert excluded == 0

    def test_empty_output(self) -> None:
        assert parse_list_units("") == ([], 0)
        assert parse_list_units("\n\n") == ([], 0)

    @pytest.mark.parametrize(
        "line",
        ["foo.service loaded active", "foo.service", "garbage"],
    )
    def test_malformed_line_raises(self, line: str) -> None:
        with pytest.raises(ReaderError):
            parse_list_units(line + "\n")

    def test_non_service_row_raises(self) -> None:
        # Under --type=service any other row means the output format changed.
        with pytest.raises(ReaderError):
            parse_list_units("● foo.service loaded failed failed Foo\n")

    def test_duplicate_row_raises(self) -> None:
        with pytest.raises(ReaderError):
            parse_list_units(
                list_rows(("a.service", "loaded"), ("a.service", "loaded"))
            )


class TestParseShow:
    def test_real_fixture_out_of_p_order(self) -> None:
        ids = ["obsidian-sync.service", "snapd.service", "plymouth-quit.service"]
        blocks = parse_show(fixture("system-show.txt"), ids)
        assert set(blocks) == set(ids)
        assert blocks["obsidian-sync.service"]["NRestarts"] == "39"

    def test_shuffled_property_order(self) -> None:
        rng = random.Random(1133)
        lines = show_block("a.service", nrestarts="7").splitlines()
        for _ in range(5):
            rng.shuffle(lines)
            blocks = parse_show("\n".join(lines) + "\n", ["a.service"])
            assert blocks["a.service"]["NRestarts"] == "7"
            assert blocks["a.service"]["Id"] == "a.service"

    def test_value_containing_equals(self) -> None:
        text = show_block("a.service") + "Description=x=y=z\n"
        assert parse_show(text, ["a.service"])["a.service"]["Description"] == "x=y=z"

    def test_missing_requested_block_raises(self) -> None:
        with pytest.raises(ReaderError, match="missing"):
            parse_show(show_block("a.service"), ["a.service", "b.service"])

    def test_extra_block_raises(self) -> None:
        with pytest.raises(ReaderError, match="not requested"):
            parse_show(
                show_out(show_block("a.service"), show_block("b.service")),
                ["a.service"],
            )

    def test_duplicate_id_raises(self) -> None:
        with pytest.raises(ReaderError, match="duplicate"):
            parse_show(
                show_out(show_block("a.service"), show_block("a.service")),
                ["a.service"],
            )

    def test_block_without_id_raises(self) -> None:
        with pytest.raises(ReaderError, match="Id"):
            parse_show("Restart=always\nNRestarts=0\n", [])

    def test_line_without_equals_raises(self) -> None:
        with pytest.raises(ReaderError):
            parse_show(show_block("a.service") + "garbage\n", ["a.service"])


class TestBuildUnitObservations:
    def test_real_system_fixture(self) -> None:
        ids = ["obsidian-sync.service", "snapd.service", "plymouth-quit.service"]
        obs, excluded = build_unit_observations(
            parse_show(fixture("system-show.txt"), ids), "system", BOOT
        )
        assert {o.name: o.restart_count for o in obs} == {
            "obsidian-sync.service": 39,
            "snapd.service": 1,
        }
        assert excluded == 1
        o = next(o for o in obs if o.name == "obsidian-sync.service")
        assert (o.scope, o.restart_policy, o.state, o.generation) == (
            "system",
            "always",
            "active (running)",
            BOOT,
        )
        assert o.key == "system:obsidian-sync.service"

    def test_not_found_is_excluded_not_an_error(self) -> None:
        blocks = parse_show(
            show_block("gone.service", load="not-found", restart="no", nrestarts="0"),
            ["gone.service"],
        )
        assert build_unit_observations(blocks, "system", BOOT) == ([], 1)

    def test_not_found_without_counters_is_excluded(self) -> None:
        blocks = parse_show(
            show_block("gone.service", load="not-found", restart=None, nrestarts=None),
            ["gone.service"],
        )
        assert build_unit_observations(blocks, "system", BOOT) == ([], 1)

    def test_restart_no_is_excluded_even_with_bad_count(self) -> None:
        blocks = parse_show(
            show_block("a.service", restart="no", nrestarts=""), ["a.service"]
        )
        assert build_unit_observations(blocks, "system", BOOT) == ([], 1)

    @pytest.mark.parametrize("nrestarts", [None, "", "x", "-1", "1.5", " 3", "٣"])
    def test_bad_nrestarts_on_watched_unit_raises(self, nrestarts: str | None) -> None:
        blocks = parse_show(show_block("a.service", nrestarts=nrestarts), ["a.service"])
        with pytest.raises(ReaderError, match="NRestarts"):
            build_unit_observations(blocks, "system", BOOT)

    @pytest.mark.parametrize(
        "missing", ["Restart", "LoadState", "ActiveState", "SubState"]
    )
    def test_missing_property_raises(self, missing: str) -> None:
        blocks = parse_show(show_block("a.service"), ["a.service"])
        del blocks["a.service"][missing]
        with pytest.raises(ReaderError):
            build_unit_observations(blocks, "system", BOOT)


# --------------------------------------------------------------------------- #
# T013: systemd scope readers and boot ID.
# --------------------------------------------------------------------------- #
class TestReadBootId:
    def test_reads_and_strips(self) -> None:
        paths: list[Path] = []

        def read_text(path: Path) -> str:
            paths.append(path)
            return BOOT + "\n"

        assert read_boot_id(read_text) == BOOT
        assert paths == [Path("/proc/sys/kernel/random/boot_id")]

    @pytest.mark.parametrize(
        "exc", [FileNotFoundError("x"), PermissionError("x"), OSError("x")]
    )
    def test_os_error_returns_none(self, exc: OSError) -> None:
        def read_text(path: Path) -> str:
            raise exc

        assert read_boot_id(read_text) is None

    def test_empty_returns_none(self) -> None:
        assert read_boot_id(lambda path: " \n") is None


class TestReadSystemdScope:
    def test_real_system_fixtures(self) -> None:
        run = systemd_run(
            "system",
            fixture("system-list-units.txt"),
            fixture("system-show.txt") + "\n" + fixture("system-show-synthesized.txt"),
        )
        reading = read_systemd_scope(
            "system", run=run, deadline=deadline(), generation=BOOT
        )
        assert reading.complete, reading.error
        assert watched(reading) == {"obsidian-sync.service": 39, "snapd.service": 1}
        assert reading.excluded == 3 + 6  # three not-found rows, six Restart=no units
        assert all(o.generation == BOOT for o in reading.observations)
        list_argv, show_argv = run.argvs()
        assert list_argv == ["systemctl", *SYSTEMD_LIST_TAIL]
        assert show_argv[: 1 + len(SHOW_PROPS) + 1] == [
            "systemctl",
            "show",
            *SHOW_PROPS,
        ]
        assert sorted(show_argv[5:]) == sorted(
            parse_list_units(fixture("system-list-units.txt"))[0]
        )

    def test_real_user_fixtures(self) -> None:
        run = systemd_run(
            "user",
            fixture("user-list-units.txt"),
            fixture("user-show.txt") + "\n" + fixture("user-show-synthesized.txt"),
        )
        reading = read_systemd_scope(
            "user", run=run, deadline=deadline(), generation=BOOT
        )
        assert reading.complete, reading.error
        assert watched(reading) == {"openclaw-gateway.service": 0}
        assert reading.observations[0].key == "user:openclaw-gateway.service"
        assert reading.excluded == 5
        assert all(argv[:2] == ["systemctl", "--user"] for argv in run.argvs())

    def test_no_loaded_units_makes_no_show_call(self) -> None:
        run = systemd_run("system", list_rows(("gone.service", "not-found")), "")
        reading = read_systemd_scope(
            "system", run=run, deadline=deadline(), generation=BOOT
        )
        assert reading.complete and reading.observations == () and reading.excluded == 1
        assert run.argvs() == [["systemctl", *SYSTEMD_LIST_TAIL]]

    def test_empty_enumeration_makes_no_show_call(self) -> None:
        run = systemd_run("user", "", "")
        reading = read_systemd_scope(
            "user", run=run, deadline=deadline(), generation=BOOT
        )
        assert reading.complete and reading.observations == ()
        assert run.argvs() == [["systemctl", "--user", *SYSTEMD_LIST_TAIL]]

    def test_enumerate_then_vanish_is_excluded_and_complete(self) -> None:
        run = systemd_run(
            "system",
            list_rows(("a.service", "loaded"), ("gone.service", "loaded")),
            show_out(
                show_block("a.service", nrestarts="2"),
                show_block(
                    "gone.service",
                    load="not-found",
                    restart="no",
                    nrestarts="0",
                    active="inactive",
                    sub="dead",
                ),
            ),
        )
        reading = read_systemd_scope(
            "system", run=run, deadline=deadline(), generation=BOOT
        )
        assert reading.complete
        assert watched(reading) == {"a.service": 2}
        assert reading.excluded == 1

    @pytest.mark.parametrize(
        "show",
        [
            pytest.param(show_block("a.service"), id="missing-requested-block"),
            pytest.param(
                show_out(
                    show_block("a.service"),
                    show_block("b.service"),
                    show_block("c.service"),
                ),
                id="extra-block",
            ),
            pytest.param(
                show_out(show_block("a.service"), show_block("a.service")),
                id="duplicate-id",
            ),
            pytest.param(
                show_out(
                    show_block("a.service"), show_block("b.service", nrestarts=None)
                ),
                id="missing-nrestarts",
            ),
            pytest.param(
                show_out(
                    show_block("a.service"), show_block("b.service", nrestarts="lots")
                ),
                id="non-integer-nrestarts",
            ),
            pytest.param("total garbage\n", id="unparseable"),
        ],
    )
    def test_malformed_show_fails_the_scope(self, show: str) -> None:
        run = systemd_run(
            "system", list_rows(("a.service", "loaded"), ("b.service", "loaded")), show
        )
        reading = read_systemd_scope(
            "system", run=run, deadline=deadline(), generation=BOOT
        )
        assert not reading.complete
        assert reading.observations == ()
        assert reading.error and "systemctl show" in reading.error

    def test_malformed_list_fails_the_scope(self) -> None:
        run = systemd_run("system", "only two\n", "")
        reading = read_systemd_scope(
            "system", run=run, deadline=deadline(), generation=BOOT
        )
        assert not reading.complete and "list-units" in (reading.error or "")
        assert len(run.calls) == 1

    @pytest.mark.parametrize("step", ["list-units", "show"])
    def test_non_zero_exit_fails_with_trimmed_stderr(self, step: str) -> None:
        run = systemd_run(
            "user", list_rows(("a.service", "loaded")), show_block("a.service")
        )
        run.on(
            ["systemctl", "--user", step],
            CommandResult(1, "", "Failed to connect to bus: " + "x" * 500),
        )
        reading = read_systemd_scope(
            "user", run=run, deadline=deadline(), generation=BOOT
        )
        assert not reading.complete
        assert reading.error is not None
        assert (
            step in reading.error
            and "exit 1" in reading.error
            and "Failed to connect to bus" in reading.error
        )
        assert len(reading.error) < 300

    @pytest.mark.parametrize(
        "exc",
        [
            pytest.param(subprocess.TimeoutExpired(["systemctl"], 3.0), id="timeout"),
            pytest.param(
                FileNotFoundError(2, "No such file or directory", "systemctl"),
                id="file-not-found",
            ),
            pytest.param(PermissionError(13, "Permission denied"), id="permission"),
        ],
    )
    def test_command_exceptions_fail_the_scope(self, exc: BaseException) -> None:
        run = FakeRun().on(["systemctl", "list-units"], exc)
        reading = read_systemd_scope(
            "system", run=run, deadline=deadline(), generation=BOOT
        )
        assert not reading.complete
        assert reading.error and "systemctl list-units" in reading.error

    def test_expired_deadline_runs_nothing(self) -> None:
        clock = FakeClock()
        d = deadline(clock)
        clock.advance(6.0)
        run = FakeRun()
        reading = read_systemd_scope("system", run=run, deadline=d, generation=BOOT)
        assert not reading.complete and reading.error == "read deadline exceeded"
        assert run.calls == []

    def test_deadline_expiring_between_commands_skips_show(self) -> None:
        clock = FakeClock()

        def slow_list(
            argv: Sequence[str], env: Mapping[str, str], timeout: float
        ) -> CommandResult:
            clock.advance(6.5)
            return ok(list_rows(("a.service", "loaded")))

        run = FakeRun().on(["systemctl", "list-units"], slow_list)
        reading = read_systemd_scope(
            "system", run=run, deadline=deadline(clock), generation=BOOT
        )
        assert not reading.complete and "read deadline exceeded" in (
            reading.error or ""
        )
        assert len(run.calls) == 1
        assert reading.elapsed_ms == 6500

    def test_missing_generation_fails_without_running(self) -> None:
        run = FakeRun()
        reading = read_systemd_scope(
            "system", run=run, deadline=deadline(), generation=None
        )
        assert not reading.complete and reading.error == "boot id unreadable"
        assert run.calls == []

    def test_systemd_env_is_minimal(self) -> None:
        environ = {
            "PATH": "/home/claude/.local/bin:/usr/bin",
            "XDG_RUNTIME_DIR": "/run/user/1001",
            "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1001/bus",
            "GITHUB_TOKEN": "secret",
            "HOME": "/home/claude",
        }
        run = systemd_run(
            "user", list_rows(("a.service", "loaded")), show_block("a.service")
        )
        reading = read_systemd_scope(
            "user", run=run, deadline=deadline(), generation=BOOT, environ=environ
        )
        assert reading.complete
        for call in run.calls:
            assert call.env == {
                "PATH": "/usr/bin:/bin",
                "XDG_RUNTIME_DIR": "/run/user/1001",
                "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1001/bus",
            }

    def test_systemd_env_without_session_variables(self) -> None:
        run = systemd_run("system", "", "")
        read_systemd_scope(
            "system",
            run=run,
            deadline=deadline(),
            generation=BOOT,
            environ={"HOME": "/x"},
        )
        assert run.calls[0].env == {"PATH": "/usr/bin:/bin"}


# --------------------------------------------------------------------------- #
# T014: docker reader.
# --------------------------------------------------------------------------- #
class TestReadContainerScope:
    def test_real_fixture(self, tmp_path: Path) -> None:
        run = docker_run(fixture("docker-ps.txt"), fixture("docker-inspect.txt"))
        reading = read_container_scope(run=run, deadline=deadline())
        assert reading.complete, reading.error
        assert watched(reading) == {"transcribe-api": 0, "vikunja": 0}
        assert reading.excluded == 1  # modest_colden, policy "no"
        by_name = {o.name: o for o in reading.observations}
        assert by_name["vikunja"].generation == DOCKER_IDS[1]
        assert by_name["vikunja"].restart_policy == "unless-stopped"
        assert by_name["vikunja"].state == "running"
        assert by_name["vikunja"].key == "container:vikunja"
        ps_argv, inspect_argv = run.argvs()
        assert ps_argv == ["docker", "ps", "-aq", "--no-trunc"]
        assert inspect_argv == [
            "docker",
            "inspect",
            "--format",
            DOCKER_INSPECT_FORMAT,
            "--",
            *DOCKER_IDS,
        ]

    def test_docker_env_is_isolated(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DOCKER_CONTEXT", "remote")
        monkeypatch.setenv("DOCKER_HOST", "tcp://evil:2375")
        monkeypatch.setenv("DOCKER_CONFIG", str(tmp_path))
        run = docker_run(fixture("docker-ps.txt"), fixture("docker-inspect.txt"))
        read_container_scope(run=run, deadline=deadline())
        assert len(run.calls) == 2
        for call in run.calls:
            # Built from scratch: no DOCKER_CONTEXT, nothing inherited.
            assert set(call.env) == {"PATH", "DOCKER_CONFIG", "DOCKER_HOST"}
            assert "DOCKER_CONTEXT" not in call.env
            assert call.env["PATH"] == "/usr/bin:/bin"
            assert (
                call.env["DOCKER_HOST"] == DOCKER_HOST == "unix:///var/run/docker.sock"
            )
            # A constant directory that cannot exist, never a temp dir.
            assert (
                call.env["DOCKER_CONFIG"]
                == DOCKER_CONFIG_DIR
                == "/proc/nonexistent-felix-canary-docker-config"
            )
        assert not Path(DOCKER_CONFIG_DIR).exists()

    def test_empty_ps_makes_no_inspect_call(self, tmp_path: Path) -> None:
        run = docker_run("\n", "")
        reading = read_container_scope(run=run, deadline=deadline())
        assert reading.complete and reading.observations == () and reading.excluded == 0
        assert run.argvs() == [["docker", "ps", "-aq", "--no-trunc"]]

    @pytest.mark.parametrize(
        "inspect",
        [
            pytest.param(lambda lines: lines[:2], id="missing-record"),
            pytest.param(lambda lines: [*lines, lines[0]], id="duplicate-record"),
            pytest.param(
                lambda lines: [lines[0], lines[1], lines[1]], id="id-mismatch"
            ),
            pytest.param(
                lambda lines: [*lines[:2], lines[2].replace(DOCKER_IDS[2], "f" * 64)],
                id="unrequested-id",
            ),
            pytest.param(
                lambda lines: [*lines[:2], '"x"|"/a"|0|"no"'], id="four-fields"
            ),
            pytest.param(
                lambda lines: [*lines[:2], lines[2] + '|"extra"'], id="six-fields"
            ),
            pytest.param(
                lambda lines: [*lines[:2], lines[2].replace("|0|", "|-1|")],
                id="negative-count",
            ),
            pytest.param(
                lambda lines: [*lines[:2], lines[2].replace("|0|", "|x|")],
                id="non-integer-count",
            ),
            pytest.param(
                lambda lines: [
                    *lines[:2],
                    lines[2].replace('"/modest_colden"', "/modest_colden"),
                ],
                id="name-not-json",
            ),
            pytest.param(
                lambda lines: [*lines[:2], lines[2].replace('"/modest_colden"', '"/"')],
                id="empty-name",
            ),
            pytest.param(
                lambda lines: [*lines[:2], lines[2].replace('"/modest_colden"', "123")],
                id="name-not-string",
            ),
            pytest.param(
                lambda lines: [*lines[:2], lines[2].replace('"exited"', "null")],
                id="status-not-string",
            ),
            pytest.param(
                lambda lines: [*lines[:2], lines[2].replace('"no"', "{bad")],
                id="policy-bad-json",
            ),
            pytest.param(lambda lines: ["garbage", *lines[1:]], id="garbage-line"),
            # Review cycle 1: name shape, checked before policy exclusion
            # (lines[2] is modest_colden, policy "no").
            *[
                pytest.param(
                    lambda lines, bad=bad: [
                        *lines[:2],
                        lines[2].replace('"/modest_colden"', json_name(bad)),
                    ],
                    id=f"excluded-policy-name-{case}",
                )
                for case, bad in MALFORMED_NAMES
            ],
            pytest.param(
                lambda lines: [
                    lines[0].replace('"/transcribe-api"', '"/bad name"'),
                    *lines[1:],
                ],
                id="watched-name-with-space",
            ),
            # Review cycle 1: distinct valid IDs sharing one name.
            pytest.param(
                lambda lines: [
                    lines[0].replace('"/transcribe-api"', '"/vikunja"'),
                    *lines[1:],
                ],
                id="duplicate-name-both-watched",
            ),
            pytest.param(
                lambda lines: [
                    *lines[:2],
                    lines[2].replace('"/modest_colden"', '"/vikunja"'),
                ],
                id="duplicate-name-one-excluded",
            ),
        ],
    )
    def test_malformed_inspect_fails_the_scope(
        self, tmp_path: Path, inspect: Callable[[list[str]], list[str]]
    ) -> None:
        lines = fixture("docker-inspect.txt").splitlines()
        run = docker_run(fixture("docker-ps.txt"), "\n".join(inspect(lines)) + "\n")
        reading = read_container_scope(run=run, deadline=deadline())
        assert not reading.complete
        assert reading.observations == ()
        assert reading.error and "docker inspect" in reading.error

    @pytest.mark.parametrize(
        "ps",
        ["abc\n", DOCKER_IDS[0] + "\n" + DOCKER_IDS[0] + "\n"],
        ids=["bad-id", "duplicate"],
    )
    def test_malformed_ps_fails_the_scope(self, tmp_path: Path, ps: str) -> None:
        run = docker_run(ps, "")
        reading = read_container_scope(run=run, deadline=deadline())
        assert not reading.complete and "docker ps" in (reading.error or "")
        assert len(run.calls) == 1

    def test_container_removed_between_ps_and_inspect_fails(
        self, tmp_path: Path
    ) -> None:
        run = docker_run(fixture("docker-ps.txt"), "")
        run.on(
            ["docker", "inspect"],
            CommandResult(
                1, fixture("docker-inspect.txt"), "Error: No such object: abc"
            ),
        )
        reading = read_container_scope(run=run, deadline=deadline())
        assert not reading.complete
        assert (
            reading.error
            and "exit 1" in reading.error
            and "No such object" in reading.error
        )

    @pytest.mark.parametrize(
        "exc",
        [
            subprocess.TimeoutExpired(["docker"], 3.0),
            FileNotFoundError(2, "No such file", "docker"),
        ],
        ids=["timeout", "file-not-found"],
    )
    def test_command_exceptions_fail_the_scope(
        self, tmp_path: Path, exc: BaseException
    ) -> None:
        run = FakeRun().on(["docker", "ps"], exc)
        reading = read_container_scope(run=run, deadline=deadline())
        assert not reading.complete and "docker ps" in (reading.error or "")

    def test_empty_policy_is_excluded(self, tmp_path: Path) -> None:
        cid = "a" * 64
        run = docker_run(cid + "\n", f'"{cid}"|"/one"|5|""|"exited"\n')
        reading = read_container_scope(run=run, deadline=deadline())
        assert reading.complete and reading.observations == () and reading.excluded == 1

    def test_expired_deadline_runs_nothing(self, tmp_path: Path) -> None:
        clock = FakeClock()
        d = deadline(clock)
        clock.advance(7)
        run = FakeRun()
        reading = read_container_scope(run=run, deadline=d)
        assert not reading.complete and reading.error == "read deadline exceeded"
        assert run.calls == []


# --------------------------------------------------------------------------- #
# read_all_scopes.
# --------------------------------------------------------------------------- #
def full_run() -> FakeRun:
    run = FakeRun()
    run.on(["systemctl", "list-units"], ok(fixture("system-list-units.txt")))
    run.on(
        ["systemctl", "show"],
        ok(fixture("system-show.txt") + "\n" + fixture("system-show-synthesized.txt")),
    )
    run.on(["systemctl", "--user", "list-units"], ok(fixture("user-list-units.txt")))
    run.on(
        ["systemctl", "--user", "show"],
        ok(fixture("user-show.txt") + "\n" + fixture("user-show-synthesized.txt")),
    )
    run.on(["docker", "ps"], ok(fixture("docker-ps.txt")))
    run.on(["docker", "inspect"], ok(fixture("docker-inspect.txt")))
    return run


class TestReadAllScopes:
    def test_happy_path_reads_all_three_in_order(self, tmp_path: Path) -> None:
        run = full_run()
        readings, boot = read_all_scopes(
            run=run,
            clock=FakeClock(),
            budget_seconds=6,
            read_boot_id=lambda: BOOT,
        )
        assert boot == BOOT
        assert [r.scope for r in readings] == list(SCOPES)
        assert all(r.complete for r in readings), [r.error for r in readings]
        assert watched(readings[0]) == {"obsidian-sync.service": 39, "snapd.service": 1}
        assert watched(readings[1]) == {"openclaw-gateway.service": 0}
        assert watched(readings[2]) == {"transcribe-api": 0, "vikunja": 0}
        assert [a[:2] for a in run.argvs()] == [
            ["systemctl", "list-units"],
            ["systemctl", "show"],
            ["systemctl", "--user"],
            ["systemctl", "--user"],
            ["docker", "ps"],
            ["docker", "inspect"],
        ]
        for call in run.calls:
            assert call.argv_type is list
            assert all(isinstance(a, str) for a in call.argv)
            assert not any("shell" in a for a in call.argv)

    def test_unreadable_boot_id_fails_all_scopes_and_runs_nothing(
        self, tmp_path: Path
    ) -> None:
        run = full_run()
        readings, boot = read_all_scopes(
            run=run,
            clock=FakeClock(),
            budget_seconds=6,
            read_boot_id=lambda: None,
        )
        assert boot is None
        assert [r.scope for r in readings] == list(SCOPES)
        assert all(not r.complete and r.error == "boot id unreadable" for r in readings)
        assert run.calls == []

    def test_raising_boot_id_reader_is_treated_as_unreadable(
        self, tmp_path: Path
    ) -> None:
        def boom() -> str | None:
            raise RuntimeError("boom")

        run = full_run()
        readings, boot = read_all_scopes(
            run=run,
            clock=FakeClock(),
            read_boot_id=boom,
        )
        assert boot is None and run.calls == []
        assert all(r.error == "boot id unreadable" for r in readings)

    def test_hung_system_scope_starves_later_scopes_without_running_them(
        self, tmp_path: Path
    ) -> None:
        clock = FakeClock()

        def hang(
            argv: Sequence[str], env: Mapping[str, str], timeout: float
        ) -> CommandResult:
            clock.advance(timeout)
            raise subprocess.TimeoutExpired(list(argv), timeout)

        run = full_run().on(["systemctl", "show"], hang)

        def slow_list(
            argv: Sequence[str], env: Mapping[str, str], timeout: float
        ) -> CommandResult:
            clock.advance(3.0)
            return ok(fixture("system-list-units.txt"))

        run.on(["systemctl", "list-units"], slow_list)
        readings, _ = read_all_scopes(
            run=run,
            clock=clock,
            budget_seconds=6,
            read_boot_id=lambda: BOOT,
        )
        system, user, container = readings
        assert not system.complete and "timed out" in (system.error or "")
        assert not user.complete and user.error == "read deadline exceeded"
        assert not container.complete and container.error == "read deadline exceeded"
        assert [a[:2] for a in run.argvs()] == [
            ["systemctl", "list-units"],
            ["systemctl", "show"],
        ]

    def test_clock_jump_past_budget_starves_later_scopes(self, tmp_path: Path) -> None:
        clock = FakeClock()

        def hang(
            argv: Sequence[str], env: Mapping[str, str], timeout: float
        ) -> CommandResult:
            clock.advance(60)
            raise subprocess.TimeoutExpired(list(argv), timeout)

        run = full_run().on(["systemctl", "list-units"], hang)
        readings, _ = read_all_scopes(
            run=run,
            clock=clock,
            read_boot_id=lambda: BOOT,
        )
        assert [r.complete for r in readings] == [False, False, False]
        assert [r.error for r in readings[1:]] == ["read deadline exceeded"] * 2
        assert len(run.calls) == 1

    def test_raising_container_reader_leaves_other_scopes_complete(
        self, tmp_path: Path
    ) -> None:
        run = full_run().on(["docker", "ps"], RuntimeError("unexpected"))
        readings, boot = read_all_scopes(
            run=run,
            clock=FakeClock(),
            read_boot_id=lambda: BOOT,
        )
        system, user, container = readings
        assert boot == BOOT
        assert system.complete and user.complete
        assert not container.complete and "RuntimeError" in (container.error or "")

    def test_raising_system_reader_does_not_stop_user_and_container(
        self, tmp_path: Path
    ) -> None:
        run = full_run().on(["systemctl", "list-units"], ValueError("weird"))
        readings, _ = read_all_scopes(
            run=run,
            clock=FakeClock(),
            read_boot_id=lambda: BOOT,
        )
        assert [r.complete for r in readings] == [False, True, True]

    def test_per_command_timeout_within_cap_and_remaining_budget(
        self, tmp_path: Path
    ) -> None:
        clock = FakeClock()
        budget = 6.0
        start = clock.now
        seen: list[tuple[float, float]] = []
        base = full_run()

        def timed(
            argv: Sequence[str], env: Mapping[str, str], timeout: float
        ) -> CommandResult:
            seen.append((timeout, budget - (clock.now - start)))
            clock.advance(1.25)
            return base(argv, env, timeout)

        readings, _ = read_all_scopes(
            run=timed,
            clock=clock,
            budget_seconds=budget,
            read_boot_id=lambda: BOOT,
        )
        assert len(seen) >= 5
        for timeout, remaining in seen:
            assert 0 < timeout <= 3.0
            assert timeout <= remaining + 1e-9
        # 4 × 1.25 s used by systemd; docker ps gets 1.0 s, then the budget is gone.
        assert seen[-1][0] == pytest.approx(1.0)
        assert readings[0].complete and readings[1].complete
        assert not readings[2].complete

    def test_default_budget_is_six_seconds(self) -> None:
        import inspect

        assert (
            inspect.signature(read_all_scopes).parameters["budget_seconds"].default == 6
        )


# --------------------------------------------------------------------------- #
# Review cycle 1: overruns after the last command, container names.
# --------------------------------------------------------------------------- #
def returns_late(
    clock: FakeClock, seconds: float, result: CommandResult
) -> Callable[[Sequence[str], Mapping[str, str], float], CommandResult]:
    """A command that succeeds, but only after *seconds* of fake time."""

    def respond(
        argv: Sequence[str], env: Mapping[str, str], timeout: float
    ) -> CommandResult:
        clock.advance(seconds)
        return result

    return respond


class TestOverrunAfterLastCommand:
    def test_systemd_final_show_succeeds_after_expiry(self) -> None:
        clock = FakeClock()
        run = systemd_run("system", list_rows(("a.service", "loaded")), "")
        run.on(
            ["systemctl", "show"],
            returns_late(clock, 7.0, ok(show_block("a.service", nrestarts="4"))),
        )
        reading = read_systemd_scope(
            "system", run=run, deadline=deadline(clock), generation=BOOT
        )
        assert not reading.complete and reading.observations == ()
        assert "read deadline exceeded" in (reading.error or "")
        assert reading.elapsed_ms == 7000

    @pytest.mark.parametrize("list_out", ["", list_rows(("gone.service", "not-found"))])
    def test_systemd_empty_enumeration_after_expiry(self, list_out: str) -> None:
        clock = FakeClock()
        run = FakeRun().on(
            ["systemctl", "--user", "list-units"],
            returns_late(clock, 7.0, ok(list_out)),
        )
        reading = read_systemd_scope(
            "user", run=run, deadline=deadline(clock), generation=BOOT
        )
        assert not reading.complete
        assert "read deadline exceeded" in (reading.error or "")
        assert len(run.calls) == 1

    def test_docker_final_inspect_succeeds_after_expiry(self, tmp_path: Path) -> None:
        clock = FakeClock()
        run = docker_run(fixture("docker-ps.txt"), "")
        run.on(
            ["docker", "inspect"],
            returns_late(clock, 6.5, ok(fixture("docker-inspect.txt"))),
        )
        reading = read_container_scope(
            run=run,
            deadline=deadline(clock),
        )
        assert not reading.complete and reading.observations == ()
        assert "read deadline exceeded" in (reading.error or "")

    def test_docker_empty_ps_after_expiry(self, tmp_path: Path) -> None:
        clock = FakeClock()
        run = FakeRun().on(["docker", "ps"], returns_late(clock, 7.0, ok("")))
        reading = read_container_scope(
            run=run,
            deadline=deadline(clock),
        )
        assert not reading.complete
        assert "read deadline exceeded" in (reading.error or "")
        assert len(run.calls) == 1

    def test_returning_exactly_at_the_budget_is_an_overrun(self) -> None:
        clock = FakeClock()
        run = FakeRun().on(
            ["systemctl", "list-units"], returns_late(clock, 6.0, ok(""))
        )
        reading = read_systemd_scope(
            "system", run=run, deadline=deadline(clock), generation=BOOT
        )
        assert not reading.complete

    def test_read_all_scopes_last_scope_overrun_is_incomplete(
        self, tmp_path: Path
    ) -> None:
        clock = FakeClock()
        run = full_run().on(
            ["docker", "inspect"],
            returns_late(clock, 10.0, ok(fixture("docker-inspect.txt"))),
        )
        readings, _ = read_all_scopes(
            run=run,
            clock=clock,
            read_boot_id=lambda: BOOT,
        )
        assert [r.complete for r in readings] == [True, True, False]
        assert "read deadline exceeded" in (readings[2].error or "")

    def test_guard_rejects_a_complete_reading_returned_after_expiry(self) -> None:
        clock = FakeClock()
        d = deadline(clock)

        def late_reader() -> ScopeReading:
            clock.advance(7.0)
            return ScopeReading.ok("user", (), 0, 7000)

        reading = readers._guarded("user", d, late_reader)
        assert not reading.complete and reading.error == "read deadline exceeded"


class TestContainerNames:
    def test_distinct_ids_sharing_one_name_fail_the_scope(self, tmp_path: Path) -> None:
        a, b = "a" * 64, "b" * 64
        assert a != b
        run = docker_run(
            f"{a}\n{b}\n",
            f'"{a}"|"/same"|0|"always"|"running"\n'
            f'"{b}"|"/same"|4|"always"|"restarting"\n',
        )
        reading = read_container_scope(run=run, deadline=deadline())
        assert not reading.complete and reading.observations == ()
        assert "duplicate container name: same" in (reading.error or "")

    def test_duplicate_name_on_excluded_record_still_fails(
        self, tmp_path: Path
    ) -> None:
        a, b = "a" * 64, "b" * 64
        run = docker_run(
            f"{a}\n{b}\n",
            f'"{a}"|"/same"|0|"always"|"running"\n"{b}"|"/same"|0|"no"|"exited"\n',
        )
        reading = read_container_scope(run=run, deadline=deadline())
        assert not reading.complete
        assert "duplicate container name" in (reading.error or "")

    @pytest.mark.parametrize(
        "bad", [bad for _, bad in MALFORMED_NAMES], ids=[c for c, _ in MALFORMED_NAMES]
    )
    @pytest.mark.parametrize("policy", ["always", "no", ""])
    def test_malformed_name_fails_regardless_of_policy(
        self, tmp_path: Path, bad: str, policy: str
    ) -> None:
        cid = "c" * 64
        run = docker_run(
            cid + "\n", f'"{cid}"|{json_name(bad)}|0|"{policy}"|"exited"\n'
        )
        reading = read_container_scope(run=run, deadline=deadline())
        assert not reading.complete
        assert "malformed name" in (reading.error or "")

    @pytest.mark.parametrize("good", ["/a", "/A1", "/x_y.z-1", "/9lives", "/vikunja"])
    def test_valid_names_pass(self, tmp_path: Path, good: str) -> None:
        cid = "d" * 64
        run = docker_run(cid + "\n", f'"{cid}"|"{good}"|2|"always"|"running"\n')
        reading = read_container_scope(run=run, deadline=deadline())
        assert reading.complete
        assert watched(reading) == {good[1:]: 2}


# --------------------------------------------------------------------------- #
# The production read path writes nothing (post-merge review, dry run).
# --------------------------------------------------------------------------- #
def _forbid_writes(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Make every filesystem mutation raise, and record the attempt.

    Copied from tests/deploy/test_deploy_crash_loop_unit_alerting.py.
    """
    import builtins
    import io
    import os
    import shutil
    import tempfile

    attempts: list[str] = []

    def refuse(what: str) -> Callable[..., object]:
        def _refused(*args: object, **_kwargs: object) -> object:
            attempts.append(f"{what}{args[:1]!r}")
            raise AssertionError(f"read attempted a write: {what}")

        return _refused

    real_open = builtins.open
    real_io_open = io.open

    def guarded(real: Callable[..., object]) -> Callable[..., object]:
        def _open(
            file: object, mode: str = "r", *args: object, **kwargs: object
        ) -> object:
            if any(c in str(mode) for c in "wax+"):
                attempts.append(f"open({file!r}, {mode!r})")
                raise AssertionError(f"read attempted a write: open {file!r} {mode!r}")
            return real(file, mode, *args, **kwargs)

        return _open

    monkeypatch.setattr(builtins, "open", guarded(real_open))
    monkeypatch.setattr(io, "open", guarded(real_io_open))
    for name in (
        "replace", "rename", "remove", "unlink", "mkdir", "makedirs", "rmdir",
        "symlink", "link", "truncate", "chmod", "open",
    ):  # fmt: skip
        monkeypatch.setattr(os, name, refuse(f"os.{name}"))
    for name in (
        "write_text", "write_bytes", "mkdir", "touch", "unlink", "rename",
        "replace", "rmdir", "symlink_to", "chmod",
    ):  # fmt: skip
        monkeypatch.setattr(Path, name, refuse(f"Path.{name}"))
    for name in ("move", "copy", "copy2", "copyfile", "copytree", "rmtree"):
        monkeypatch.setattr(shutil, name, refuse(f"shutil.{name}"))
    for name in (
        "mkstemp", "mkdtemp", "NamedTemporaryFile", "TemporaryFile",
        "TemporaryDirectory", "SpooledTemporaryFile",
    ):  # fmt: skip
        monkeypatch.setattr(tempfile, name, refuse(f"tempfile.{name}"))
    return attempts


def test_forbid_writes_guard_fires(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import tempfile

    attempts = _forbid_writes(monkeypatch)
    with pytest.raises(AssertionError):
        (tmp_path / "x").write_text("x")
    with pytest.raises(AssertionError):
        tempfile.TemporaryDirectory()
    assert len(attempts) == 2


def test_read_all_scopes_writes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = _forbid_writes(monkeypatch)
    run = full_run()
    readings, boot = read_all_scopes(run=run, read_boot_id=lambda: BOOT)
    assert attempts == []
    assert boot == BOOT
    assert [r.complete for r in readings] == [True, True, True], [
        r.error for r in readings
    ]
    docker_calls = [c for c in run.calls if c.argv[0] == "docker"]
    assert len(docker_calls) == 2
    assert all(c.env["DOCKER_CONFIG"] == DOCKER_CONFIG_DIR for c in docker_calls)

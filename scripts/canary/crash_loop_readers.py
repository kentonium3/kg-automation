"""Unprivileged restart-count readers (mission crash-loop-unit-alerting, #1133).

Turns the system manager, the canary's own user manager and the local docker
daemon into :class:`~scripts.canary.crash_loop_model.ScopeReading` values.

- No privilege, no journal, no credential file (NFR-003, C-002, research R-02).
- Commands run as argv lists with a minimal environment; there is no shell.
- Every docker command gets a fresh, empty ``DOCKER_CONFIG`` directory and a
  pinned local ``DOCKER_HOST``, so the CLI loads no client configuration and
  consults no remote context.
- All three scopes share one monotonic deadline; each command's timeout is
  ``min(3 s, remaining)`` (research R-15).
- Output is reconciled against what was asked for. Anything malformed fails
  the scope as could-not-check, never as a silently shorter watched set
  (research R-13). Policy exclusions (not loaded, ``Restart=no``, docker policy
  ``no``/empty) are counted, not errors.

All effects (``run``, ``clock``, the boot-ID reader, the tempdir factory and
the environment) are injected; :func:`default_run` is the only real
``subprocess.run``.

References: research.md R-02, R-03, R-06, R-13, R-15; data-model.md.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from scripts.canary.crash_loop_model import SCOPES, RestartObservation, ScopeReading

__all__ = [
    "BOOT_ID_PATH",
    "DEFAULT_BUDGET_SECONDS",
    "DOCKER_HOST",
    "DOCKER_INSPECT_FORMAT",
    "PER_COMMAND_TIMEOUT",
    "CommandResult",
    "Deadline",
    "ReaderError",
    "RunFn",
    "build_unit_observations",
    "default_run",
    "parse_list_units",
    "parse_show",
    "read_all_scopes",
    "read_boot_id",
    "read_container_scope",
    "read_systemd_scope",
]

BOOT_ID_PATH: Final[Path] = Path("/proc/sys/kernel/random/boot_id")
DEFAULT_BUDGET_SECONDS: Final[int] = 6
PER_COMMAND_TIMEOUT: Final[float] = 3.0
MIN_PATH: Final[str] = "/usr/bin:/bin"
DOCKER_HOST: Final[str] = "unix:///var/run/docker.sock"
# Only these formatted fields ever reach this process (research R-02, CX-3).
DOCKER_INSPECT_FORMAT: Final[str] = (
    "{{json .Id}}|{{json .Name}}|{{.RestartCount}}"
    "|{{json .HostConfig.RestartPolicy.Name}}|{{json .State.Status}}"
)
SHOW_PROPERTIES: Final[str] = "Id,Restart,NRestarts,ActiveState,SubState,LoadState"
_LIST_UNITS_ARGS: Final[tuple[str, ...]] = (
    "list-units",
    "--type=service",
    "--all",
    "--plain",
    "--no-legend",
    "--no-pager",
)
_SYSTEMD_ENV_PASSTHROUGH: Final[tuple[str, ...]] = (
    "XDG_RUNTIME_DIR",
    "DBUS_SESSION_BUS_ADDRESS",
)
_STDERR_MAX: Final[int] = 200
_DEADLINE_EXCEEDED: Final[str] = "read deadline exceeded"
_BOOT_ID_UNREADABLE: Final[str] = "boot id unreadable"
_NON_NEGATIVE_INT_RE: Final[re.Pattern[str]] = re.compile(r"[0-9]+", re.ASCII)
_CONTAINER_ID_RE: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{64}", re.ASCII)
# Docker's container-name grammar, as inspect prints it (leading slash).
_CONTAINER_NAME_RE: Final[re.Pattern[str]] = re.compile(
    r"/[a-zA-Z0-9][a-zA-Z0-9_.-]*", re.ASCII
)
_DOCKER_EXCLUDED_POLICIES: Final[frozenset[str]] = frozenset({"no", ""})


# --------------------------------------------------------------------------- #
# T011: command runner and deadline.
# --------------------------------------------------------------------------- #
class ReaderError(Exception):
    """A command failed or its output could not be trusted (research R-13)."""


@dataclass(frozen=True)
class CommandResult:
    """The outcome of one command."""

    returncode: int
    stdout: str
    stderr: str


# run(argv, env, timeout). A timeout raises subprocess.TimeoutExpired.
RunFn = Callable[[Sequence[str], Mapping[str, str], float], CommandResult]
TempdirFactory = Callable[[], AbstractContextManager[str]]


class Deadline:
    """One monotonic budget shared by every command of a read."""

    def __init__(self, clock: Callable[[], float], budget_seconds: float) -> None:
        self.clock = clock
        self._start = clock()
        self._budget = float(budget_seconds)

    def elapsed(self) -> float:
        return self.clock() - self._start

    def remaining(self) -> float:
        return max(0.0, self._budget - self.elapsed())

    def expired(self) -> bool:
        return self.remaining() <= 0.0


def default_run(
    argv: Sequence[str], env: Mapping[str, str], timeout: float
) -> CommandResult:
    """Run *argv* without a shell; the only real subprocess call in this module."""
    completed = subprocess.run(
        list(argv),
        env=dict(env),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def _timeout(deadline: Deadline) -> float:
    return min(PER_COMMAND_TIMEOUT, deadline.remaining())


def _systemd_env(environ: Mapping[str, str]) -> dict[str, str]:
    env = {"PATH": MIN_PATH}
    for name in _SYSTEMD_ENV_PASSTHROUGH:
        if name in environ:
            env[name] = environ[name]
    return env


def _docker_env(config_dir: str) -> dict[str, str]:
    # DOCKER_CONTEXT is deliberately absent; the env is built from scratch.
    return {"PATH": MIN_PATH, "DOCKER_CONFIG": config_dir, "DOCKER_HOST": DOCKER_HOST}


def _run_checked(
    run: RunFn,
    argv: Sequence[str],
    env: Mapping[str, str],
    deadline: Deadline,
    label: str,
) -> str:
    """Run one command inside the deadline; return stdout or raise ReaderError."""
    timeout = _timeout(deadline)
    if timeout <= 0.0:
        raise ReaderError(_DEADLINE_EXCEEDED)
    try:
        result = run(list(argv), env, timeout)
    except subprocess.TimeoutExpired as exc:
        raise ReaderError(f"{label}: timed out after {timeout:.1f}s") from exc
    except OSError as exc:
        raise ReaderError(f"{label}: {type(exc).__name__}: {exc}") from exc
    if deadline.expired():
        # A command that returns after the budget ran out is an overrun (R-13).
        raise ReaderError(f"{label}: {_DEADLINE_EXCEEDED}")
    if result.returncode != 0:
        stderr = result.stderr.strip()[:_STDERR_MAX]
        raise ReaderError(f"{label}: exit {result.returncode}: {stderr}")
    return result.stdout


def _elapsed_ms(deadline: Deadline, started: float) -> int:
    return max(0, round((deadline.clock() - started) * 1000))


def _complete(
    scope: str,
    observations: Sequence[RestartObservation],
    excluded: int,
    deadline: Deadline,
    started: float,
) -> ScopeReading:
    """A complete reading, unless the deadline has run out (then incomplete)."""
    elapsed = _elapsed_ms(deadline, started)
    if deadline.expired():
        return ScopeReading.failed(scope, _DEADLINE_EXCEEDED, elapsed)
    return ScopeReading.ok(scope, tuple(observations), excluded, elapsed)


# --------------------------------------------------------------------------- #
# T012: systemd parsers.
# --------------------------------------------------------------------------- #
def parse_list_units(stdout: str) -> tuple[list[str], int]:
    """Return ``(loaded_unit_ids, excluded_not_loaded)`` from ``list-units``.

    Columns are UNIT LOAD ACTIVE SUB DESCRIPTION. Under ``--type=service`` a
    row that is not a ``*.service`` means the format changed, so it raises
    rather than silently shrinking the watched set.
    """
    units: list[str] = []
    seen: set[str] = set()
    excluded = 0
    for line in stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) < 4:
            raise ReaderError(f"malformed list-units row: {line[:80]!r}")
        unit, load = parts[0], parts[1]
        if not unit.endswith(".service"):
            raise ReaderError(f"unexpected list-units row: {line[:80]!r}")
        if unit in seen:
            raise ReaderError(f"duplicate list-units row: {unit}")
        seen.add(unit)
        if load == "loaded":
            units.append(unit)
        else:
            excluded += 1
    return units, excluded


def parse_show(stdout: str, requested: list[str]) -> dict[str, dict[str, str]]:
    """Parse blank-line-separated ``show`` blocks, keyed by ``Id``.

    Property order is arbitrary (research R-03). The returned IDs must equal
    *requested* exactly.
    """
    raw_blocks: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in stdout.splitlines():
        if not line.strip():
            if current:
                raw_blocks.append(current)
                current = {}
            continue
        key, sep, value = line.partition("=")
        if not sep or not key:
            raise ReaderError(f"malformed show line: {line[:80]!r}")
        if key in current:
            raise ReaderError(f"repeated property {key!r} in one show block")
        current[key] = value
    if current:
        raw_blocks.append(current)

    blocks: dict[str, dict[str, str]] = {}
    for block in raw_blocks:
        unit = block.get("Id")
        if not unit:
            raise ReaderError("show block without Id")
        if unit in blocks:
            raise ReaderError(f"duplicate Id in show output: {unit}")
        blocks[unit] = block
    wanted = set(requested)
    missing = sorted(wanted - set(blocks))
    if missing:
        raise ReaderError(f"show output missing requested units: {_names(missing)}")
    extra = sorted(set(blocks) - wanted)
    if extra:
        raise ReaderError(f"show output has units not requested: {_names(extra)}")
    return blocks


def _names(items: list[str], limit: int = 5) -> str:
    shown = ", ".join(items[:limit])
    return shown + (f" (+{len(items) - limit} more)" if len(items) > limit else "")


def _require(block: Mapping[str, str], unit: str, prop: str) -> str:
    if prop not in block:
        raise ReaderError(f"{unit}: {prop} missing")
    return block[prop]


def build_unit_observations(
    blocks: Mapping[str, Mapping[str, str]], scope: str, generation: str
) -> tuple[list[RestartObservation], int]:
    """Turn parsed ``show`` blocks into watched observations and an exclusion count."""
    observations: list[RestartObservation] = []
    excluded = 0
    for unit, block in blocks.items():
        if _require(block, unit, "LoadState") != "loaded":
            # Enumerated as loaded, then vanished: a benign race (R-13).
            excluded += 1
            continue
        restart = _require(block, unit, "Restart")
        if restart == "no":
            excluded += 1
            continue
        count = block.get("NRestarts")
        if count is None or not _NON_NEGATIVE_INT_RE.fullmatch(count):
            raise ReaderError(
                f"{unit}: NRestarts not a non-negative integer: {count!r}"
            )
        active = _require(block, unit, "ActiveState")
        sub = _require(block, unit, "SubState")
        observations.append(
            RestartObservation(
                scope=scope,
                name=unit,
                restart_policy=restart,
                restart_count=int(count),
                state=f"{active} ({sub})",
                generation=generation,
            )
        )
    return observations, excluded


# --------------------------------------------------------------------------- #
# T013: boot ID and systemd scope readers.
# --------------------------------------------------------------------------- #
def read_boot_id(read_text: Callable[[Path], str] = Path.read_text) -> str | None:
    """The kernel boot ID (a world-readable file), or ``None`` when unreadable."""
    try:
        value = read_text(BOOT_ID_PATH).strip()
    except (OSError, ValueError):
        return None
    return value or None


def read_systemd_scope(
    scope: str,
    *,
    run: RunFn,
    deadline: Deadline,
    generation: str | None,
    environ: Mapping[str, str] | None = None,
) -> ScopeReading:
    """Read the ``system`` manager or the canary's own ``user`` manager."""
    if scope not in ("system", "user"):
        raise ValueError(f"read_systemd_scope: not a systemd scope: {scope!r}")
    started = deadline.clock()
    if generation is None:
        return ScopeReading.failed(scope, _BOOT_ID_UNREADABLE, 0)
    base = ["systemctl", "--user"] if scope == "user" else ["systemctl"]
    prefix = " ".join(base)
    env = _systemd_env(os.environ if environ is None else environ)
    try:
        listed = _run_checked(
            run, [*base, *_LIST_UNITS_ARGS], env, deadline, f"{prefix} list-units"
        )
        try:
            units, not_loaded = parse_list_units(listed)
        except ReaderError as exc:
            raise ReaderError(f"{prefix} list-units: {exc}") from exc
        if not units:
            # No argument-free show: it would describe the manager itself.
            return _complete(scope, (), not_loaded, deadline, started)
        shown = _run_checked(
            run,
            [*base, "show", "-p", SHOW_PROPERTIES, "--", *units],
            env,
            deadline,
            f"{prefix} show",
        )
        try:
            blocks = parse_show(shown, units)
            observations, policy_excluded = build_unit_observations(
                blocks, scope, generation
            )
        except ReaderError as exc:
            raise ReaderError(f"{prefix} show: {exc}") from exc
    except ReaderError as exc:
        return ScopeReading.failed(scope, str(exc), _elapsed_ms(deadline, started))
    return _complete(
        scope, observations, not_loaded + policy_excluded, deadline, started
    )


# --------------------------------------------------------------------------- #
# T014: docker reader.
# --------------------------------------------------------------------------- #
def _run_docker(
    run: RunFn,
    argv: Sequence[str],
    deadline: Deadline,
    label: str,
    tempdir_factory: TempdirFactory,
) -> str:
    """Run one docker command with a fresh, empty, afterwards-removed DOCKER_CONFIG."""
    if _timeout(deadline) <= 0.0:
        raise ReaderError(_DEADLINE_EXCEEDED)
    with tempdir_factory() as config_dir:
        return _run_checked(run, argv, _docker_env(config_dir), deadline, label)


def _parse_ps(stdout: str) -> list[str]:
    ids: list[str] = []
    for line in stdout.splitlines():
        cid = line.strip()
        if not cid:
            continue
        if not _CONTAINER_ID_RE.fullmatch(cid):
            raise ReaderError(f"malformed container id: {cid[:80]!r}")
        if cid in ids:
            raise ReaderError(f"duplicate container id: {cid}")
        ids.append(cid)
    return ids


def _json_str(field_text: str, what: str) -> str:
    try:
        value = json.loads(field_text)
    except ValueError as exc:
        raise ReaderError(f"{what} is not JSON: {field_text[:80]!r}") from exc
    if not isinstance(value, str):
        raise ReaderError(f"{what} is not a string: {field_text[:80]!r}")
    return value


def _parse_inspect(
    stdout: str, requested: list[str]
) -> tuple[list[RestartObservation], int]:
    observations: list[RestartObservation] = []
    excluded = 0
    seen: set[str] = set()
    names: set[str] = set()
    for line in stdout.splitlines():
        if not line.strip():
            continue
        fields = line.split("|")
        if len(fields) != 5:
            raise ReaderError(f"expected 5 fields, got {len(fields)}: {line[:80]!r}")
        cid = _json_str(fields[0], "id")
        if not _CONTAINER_ID_RE.fullmatch(cid):
            raise ReaderError(f"malformed container id: {cid[:80]!r}")
        if cid in seen:
            raise ReaderError(f"duplicate container id: {cid}")
        seen.add(cid)
        # Name shape and uniqueness are checked before policy exclusion:
        # observations are keyed by name downstream.
        raw_name = _json_str(fields[1], "name")
        if not _CONTAINER_NAME_RE.fullmatch(raw_name):
            raise ReaderError(f"{cid}: malformed name: {raw_name[:80]!r}")
        name = raw_name.removeprefix("/")
        if name in names:
            raise ReaderError(f"duplicate container name: {name}")
        names.add(name)
        if not _NON_NEGATIVE_INT_RE.fullmatch(fields[2]):
            raise ReaderError(f"{name}: RestartCount not a non-negative integer")
        policy = _json_str(fields[3], "restart policy")
        status = _json_str(fields[4], "status")
        if policy in _DOCKER_EXCLUDED_POLICIES:
            excluded += 1
            continue
        observations.append(
            RestartObservation(
                scope="container",
                name=name,
                restart_policy=policy,
                restart_count=int(fields[2]),
                state=status,
                generation=cid,
            )
        )
    wanted = set(requested)
    missing = sorted(wanted - seen)
    if missing:
        raise ReaderError(f"missing requested containers: {_names(missing)}")
    extra = sorted(seen - wanted)
    if extra:
        raise ReaderError(f"containers not requested: {_names(extra)}")
    return observations, excluded


def read_container_scope(
    *,
    run: RunFn,
    deadline: Deadline,
    tempdir_factory: TempdirFactory,
) -> ScopeReading:
    """Read restart counts of every local container (``ps`` then ``inspect``)."""
    started = deadline.clock()
    try:
        listed = _run_docker(
            run,
            ["docker", "ps", "-aq", "--no-trunc"],
            deadline,
            "docker ps",
            tempdir_factory,
        )
        try:
            ids = _parse_ps(listed)
        except ReaderError as exc:
            raise ReaderError(f"docker ps: {exc}") from exc
        if not ids:
            return _complete("container", (), 0, deadline, started)
        inspected = _run_docker(
            run,
            ["docker", "inspect", "--format", DOCKER_INSPECT_FORMAT, "--", *ids],
            deadline,
            "docker inspect",
            tempdir_factory,
        )
        try:
            observations, excluded = _parse_inspect(inspected, ids)
        except ReaderError as exc:
            raise ReaderError(f"docker inspect: {exc}") from exc
    except ReaderError as exc:
        return ScopeReading.failed(
            "container", str(exc), _elapsed_ms(deadline, started)
        )
    return _complete("container", observations, excluded, deadline, started)


# --------------------------------------------------------------------------- #
# All scopes.
# --------------------------------------------------------------------------- #
def _guarded(
    scope: str, deadline: Deadline, reader: Callable[[], ScopeReading]
) -> ScopeReading:
    """Run one scope reader; never raise (FR-011, US4-1)."""
    if deadline.expired():
        return ScopeReading.failed(scope, _DEADLINE_EXCEEDED, 0)
    started = deadline.clock()
    try:
        reading = reader()
    except Exception as exc:  # noqa: BLE001 - one scope must not sink the others
        reason = f"{scope} reader crashed: {type(exc).__name__}: {exc}"
        return ScopeReading.failed(
            scope, reason[: _STDERR_MAX + 60], _elapsed_ms(deadline, started)
        )
    if reading.complete and deadline.expired():
        return ScopeReading.failed(scope, _DEADLINE_EXCEEDED, reading.elapsed_ms)
    return reading


def read_all_scopes(
    *,
    run: RunFn = default_run,
    clock: Callable[[], float] = time.monotonic,
    budget_seconds: float = DEFAULT_BUDGET_SECONDS,
    read_boot_id: Callable[[], str | None] = read_boot_id,
    tempdir_factory: TempdirFactory = tempfile.TemporaryDirectory,
    environ: Mapping[str, str] | None = None,
) -> tuple[list[ScopeReading], str | None]:
    """Read system, user and container scopes under one deadline.

    Returns ``(readings, boot_id)``, readings in :data:`SCOPES` order. If the
    boot ID is unreadable, every scope fails with ``"boot id unreadable"`` and
    no command runs (research R-06). Never raises.
    """
    deadline = Deadline(clock, budget_seconds)
    try:
        boot_id = read_boot_id()
    except Exception:  # noqa: BLE001 - an unreadable boot ID is a reading, not a crash
        boot_id = None
    if not boot_id:
        return [ScopeReading.failed(s, _BOOT_ID_UNREADABLE, 0) for s in SCOPES], None

    readers: dict[str, Callable[[], ScopeReading]] = {
        "system": lambda: read_systemd_scope(
            "system", run=run, deadline=deadline, generation=boot_id, environ=environ
        ),
        "user": lambda: read_systemd_scope(
            "user", run=run, deadline=deadline, generation=boot_id, environ=environ
        ),
        "container": lambda: read_container_scope(
            run=run, deadline=deadline, tempdir_factory=tempdir_factory
        ),
    }
    return [_guarded(scope, deadline, readers[scope]) for scope in SCOPES], boot_id

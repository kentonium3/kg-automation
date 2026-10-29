"""Systemd user-unit install primitives (#1066).

Mechanism only, lifted from ``scripts/deploy/deploy-monotonic-timer-units.py``
(#1062), the one entrypoint that verified the *loaded* config and polled for a
concrete next elapse instead of checking once. About twenty historical deploy
entrypoints re-implemented parts of this; new ones should call it instead
(``tests/deploy/test_unit_install_uses_userunits.py`` enforces that).

Policy stays with the caller: which properties must hold (``expect``), any
extra check over the loaded unit files (``extra_check``), what to do after
installing (``action``), whether to wait for a next elapse, and the deadline.

Contract (shared with every ``scripts/deploy/lib`` module):

* every public function returns :class:`~scripts.deploy.lib.LibResult`;
  per-unit outcomes are in ``details["units"]`` and failures in
  ``details["failed"]``;
* nothing here prints, with one exception: if recording an installed file
  fails, :mod:`scripts.deploy.lib.installed_report` writes one
  ``FELIX_DEPLOY_INSTALLED_REPORT_WRITE_FAILED`` line to stderr. Callers own
  their event log; an optional ``emit`` hook carries poll progress;
* effects are injected: ``run(argv) -> (rc, stdout, stderr)``, ``sleep``,
  ``monotonic`` (read at call time, so a caller's patched clock is honoured)
  and ``read(path) -> str``.

Two rules the #1062 incident taught, both built in:

* ``daemon-reload`` does not change a *running* timer's in-memory state, so
  the common path is :func:`apply_units` (install, reload, then an action for
  every unit), not a pick-and-mix of steps;
* right after a restart a timer reports next elapse ``infinity`` while its
  service runs, so the next-elapse check polls to a deadline instead of
  reading once.

Each changed file is recorded with
:func:`scripts.deploy.lib.installed_report.record_installed` once it has landed,
so felix-deployer expects the security-monitor drift it causes even when the
unit was changed in an earlier commit (#1072). Unchanged files are not recorded.

⚠ A unit installed from a new repo directory must also be covered by
``docs/design/architecture/data/audited-surfaces.json`` (#1065); a reported
file whose source matches no surface is expected to drift nothing.
"""
from __future__ import annotations

import os
import pwd
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from scripts.deploy.lib import LibResult
from scripts.deploy.lib.installed_report import record_installed

Runner = Callable[[list[str]], "tuple[int, str, str]"]
Emit = Callable[..., None]

POLL_INTERVAL_S = 5
ACTIONS = ("restart", "enable-now", "start", "none")
_STDERR_MAX = 2000


def _noop_emit(*_a: Any, **_k: Any) -> None:
    return None


def _read_text(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def _excerpt(text: str) -> str:
    return text if len(text) <= _STDERR_MAX else text[:_STDERR_MAX] + "...<truncated>"


# --- pure helpers ---------------------------------------------------------------

def parse_show(out: str) -> dict[str, str]:
    """Parse ``systemctl show -p...`` output into a dict (values may contain '=')."""
    props: dict[str, str] = {}
    for line in out.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            props[key] = value
    return props


def next_elapse_is_concrete(value: str) -> bool:
    """systemd renders a human timespan ("54min 36.9s"); only these mean "none"."""
    return value.strip() not in {"", "0", "infinity"}


# --- preflight --------------------------------------------------------------------

def preflight_user(*, expected_user: str, expected_home: Path) -> LibResult:
    """User units install under ``$HOME``: refuse to run as anyone else."""
    actual = pwd.getpwuid(os.geteuid()).pw_name
    home = Path.home()
    details = {"euid_user": actual, "home": str(home)}
    if actual != expected_user or home != Path(expected_home):
        return LibResult(False, f"must run as {expected_user} with HOME={expected_home}",
                         {**details, "error_code": "WRONG_USER"})
    return LibResult(True, f"running as {actual}", details)


# --- install ---------------------------------------------------------------------

def _differs(src: Path, dst: Path) -> bool | None:
    """True/False, or None when either side cannot be read (never "equal")."""
    if not dst.exists():
        return True
    try:
        return Path(src).read_bytes() != dst.read_bytes()
    except OSError:
        return None


def plan_install(sources: Sequence[Path], unit_dir: Path) -> LibResult:
    """What :func:`install_units` would change. Writes nothing."""
    units = [{"name": Path(s).name, "src": str(s), "dst": str(Path(unit_dir) / Path(s).name),
              "differs": _differs(Path(s), Path(unit_dir) / Path(s).name)} for s in sources]
    return LibResult(True, f"{sum(1 for u in units if u['differs'] is not False)} of {len(units)} would change",
                     {"units": units})


def install_units(sources: Sequence[Path], unit_dir: Path, *,
                  progress: Emit = _noop_emit) -> LibResult:
    """Copy every source into ``unit_dir``: all or nothing up front, atomic per file.

    Every source must exist before any file is copied. Each copy is written to
    a temp file in ``unit_dir`` and renamed into place, so a reader never sees
    a half-written unit. The resulting mode matches the ``shutil.copyfile``
    this replaced (keep an existing file's mode, else ``0666 & ~umask``), and,
    like it, a destination that is not writable is refused rather than
    replaced. ``progress("installed", unit=..., changed=...)`` fires per unit
    as it happens. ``details["units"]`` always lists what was installed so
    far, including on failure.
    """
    missing = [str(s) for s in sources if not Path(s).is_file()]
    if missing:
        return LibResult(False, "source unit missing; nothing copied",
                         {"error_code": "SOURCE_MISSING", "missing": missing, "units": []})
    unit_dir = Path(unit_dir)
    units: list[dict[str, Any]] = []

    def fail(name: str, exc: BaseException | str) -> LibResult:
        return LibResult(False, f"copy failed for {name}",
                         {"error_code": "COPY_FAILED", "unit": name, "error": str(exc), "units": units})

    try:
        unit_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return fail(str(unit_dir), exc)
    for src in sources:
        src = Path(src)
        dst = unit_dir / src.name
        if _differs(src, dst) is False:
            units.append({"name": src.name, "changed": False})
            progress("installed", unit=src.name, changed=False)
            continue
        if dst.exists() and not os.access(dst, os.W_OK):
            return fail(src.name, f"{dst} is not writable")
        tmp: str | None = None
        try:
            if dst.exists():
                mode = dst.stat().st_mode & 0o7777
            else:
                umask = os.umask(0)
                os.umask(umask)
                mode = 0o666 & ~umask
            fd, tmp = tempfile.mkstemp(dir=unit_dir, prefix=f".{src.name}.", suffix=".tmp")
            with os.fdopen(fd, "wb") as fh:
                fh.write(src.read_bytes())
            os.chmod(tmp, mode)
            os.replace(tmp, dst)
            tmp = None
        except OSError as exc:
            return fail(src.name, exc)
        finally:
            if tmp is not None:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
        record_installed(src, dst)
        units.append({"name": src.name, "changed": True})
        progress("installed", unit=src.name, changed=True)
    return LibResult(True, f"installed {len(units)} unit(s)", {"units": units})


def converged(sources: Sequence[Path], unit_dir: Path) -> LibResult:
    """Every deployed copy is byte-equal to its source. Unreadable is a failure."""
    units = [{"name": Path(s).name, "differs": _differs(Path(s), Path(unit_dir) / Path(s).name)}
             for s in sources]
    bad = [u["name"] for u in units if u["differs"] is not False]
    if bad:
        return LibResult(False, f"{len(bad)} deployed unit(s) differ or are unreadable",
                         {"error_code": "NOT_CONVERGED", "units": units, "failed": bad})
    return LibResult(True, "deployed units match the repo", {"units": units})


# --- systemctl -------------------------------------------------------------------

def daemon_reload(run: Runner) -> LibResult:
    rc, _out, err = run(["systemctl", "--user", "daemon-reload"])
    if rc != 0:
        return LibResult(False, "daemon-reload failed",
                         {"error_code": "DAEMON_RELOAD_FAILED", "rc": rc, "stderr_excerpt": _excerpt(err)})
    return LibResult(True, "daemon-reloaded")


def unit_action(unit: str, action: str, run: Runner) -> LibResult:
    """``restart`` | ``enable-now`` | ``start`` | ``none`` (install and reload only)."""
    if action not in ACTIONS:
        return LibResult(False, f"unknown action {action!r}", {"error_code": "UNKNOWN_ACTION", "unit": unit})
    if action == "none":
        return LibResult(True, f"{unit}: no action", {"unit": unit, "action": action})
    argv = {"restart": ["systemctl", "--user", "restart", unit],
            "enable-now": ["systemctl", "--user", "enable", "--now", unit],
            "start": ["systemctl", "--user", "start", unit]}[action]
    rc, _out, err = run(argv)
    if rc != 0:
        return LibResult(False, f"{action} {unit} failed",
                         {"error_code": "ACTION_FAILED", "unit": unit, "action": action, "rc": rc,
                          "stderr_excerpt": _excerpt(err)})
    return LibResult(True, f"{action} {unit}", {"unit": unit, "action": action})


def apply_units(sources: Sequence[Path], unit_dir: Path, *, action: str, run: Runner,
                progress: Emit = _noop_emit) -> LibResult:
    """The common path: install every unit, ``daemon-reload`` once, then
    ``action`` on every unit, continuing past per-unit failures.

    A running timer keeps its in-memory state across ``daemon-reload``; only a
    restart applies a changed definition (#1062). Pass ``action="none"`` only
    for units that must deliberately not be bounced.

    ``progress`` receives, as they happen: ``installed`` (unit, changed),
    ``reloaded``, and ``acted`` (unit, action, ok, rc, stderr_excerpt). Every
    result carries ``details["installed"]`` (what was installed, even on
    failure), so a caller's event log never loses a completed copy.
    """
    installed = install_units(sources, unit_dir, progress=progress)
    done = installed.details.get("units", [])
    if not installed.ok:
        return LibResult(False, installed.summary, {**installed.details, "installed": done})
    reloaded = daemon_reload(run)
    if not reloaded.ok:
        return LibResult(False, reloaded.summary, {**reloaded.details, "installed": done})
    progress("reloaded")
    failed: dict[str, list[str]] = {}
    results = []
    for src in sources:
        name = Path(src).name
        res = unit_action(name, action, run)
        progress("acted", unit=name, action=action, ok=res.ok,
                 rc=res.details.get("rc"), stderr_excerpt=res.details.get("stderr_excerpt"))
        results.append({"name": name, "ok": res.ok, **{k: v for k, v in res.details.items() if k != "unit"}})
        if not res.ok:
            failed[name] = [f"{action} failed rc={res.details.get('rc')}: {res.details.get('stderr_excerpt', '')}"]
    details = {"units": results, "installed": done, "failed": failed}
    if failed:
        return LibResult(False, f"{len(failed)} unit(s) failed {action}", {**details, "error_code": "ACTION_FAILED"})
    return LibResult(True, f"installed, reloaded, {action}: {len(results)} unit(s)", details)


# --- verify ---------------------------------------------------------------------

_BASE_PROPS = ("UnitFileState", "ActiveState", "SubState", "FragmentPath", "DropInPaths")


def verify_unit(
    unit: str,
    run: Runner,
    *,
    unit_dir: Path,
    expect: Mapping[str, str] | None = None,
    extra_check: Callable[[dict[str, str], list[str]], list[str]] | None = None,
    wait_next_elapse: bool = False,
    sleep: Callable[[float], None] = time.sleep,
    deadline: float | None = None,
    timeout_s: float = 300,
    monotonic: Callable[[], float] | None = None,
    read: Callable[[Path], str] = _read_text,
    emit: Emit = _noop_emit,
) -> LibResult:
    """Verify the LOADED unit, not just the file on disk.

    Checks ``expect`` against ``systemctl show`` properties, that the loaded
    ``FragmentPath`` is ``unit_dir/unit``, and the caller's ``extra_check``
    over the fragment and drop-in texts systemd actually loaded (an unreadable
    one is a failure). A bad loaded config fails at once. With
    ``wait_next_elapse`` it then polls (bounded by ``deadline``, or
    ``timeout_s`` from now) for a concrete ``NextElapseUSecMonotonic``; pass
    one shared ``deadline`` across many units so a broken deploy cannot hold
    the deployer for N x timeout_s.
    """
    clock = monotonic or time.monotonic
    if deadline is None:
        deadline = clock() + timeout_s
    expect = dict(expect or {})
    props_wanted = tuple(dict.fromkeys((*_BASE_PROPS, *expect,
                                        *(("NextElapseUSecMonotonic",) if wait_next_elapse else ()))))
    want_path = str(Path(unit_dir) / unit)
    while True:
        rc, out, err = run(["systemctl", "--user", "show", unit, *[f"-p{p}" for p in props_wanted]])
        if rc != 0:
            return LibResult(False, f"systemctl show {unit} failed",
                             {"error_code": "SHOW_FAILED", "unit": unit, "rc": rc,
                              "problems": [f"systemctl show failed rc={rc}: {_excerpt(err)}"]})
        props = parse_show(out)
        problems = [f"{k}={props.get(k)!r}, want {v!r}" for k, v in expect.items() if props.get(k) != v]
        if props.get("FragmentPath") != want_path:
            problems.append(f"FragmentPath={props.get('FragmentPath')!r}, want {want_path!r}")
        paths = [Path(props.get("FragmentPath", "") or "/nonexistent")]
        paths += [Path(p) for p in props.get("DropInPaths", "").split() if p]
        texts: list[str] = []
        for p in paths:
            try:
                texts.append(read(p))
            except OSError as exc:
                # An unreadable loaded file is reported on its own: nothing
                # else about the unit can be judged without it.
                return LibResult(False, f"{unit}: cannot read a loaded unit file",
                                 {"error_code": "UNREADABLE_UNIT_FILE", "unit": unit, "props": props,
                                  "problems": [f"cannot read unit file {p}: {exc}"]})
        if extra_check is not None:
            problems.extend(extra_check(props, texts))
        if problems:
            return LibResult(False, f"{unit}: loaded config wrong",
                             {"error_code": "LOADED_CONFIG", "unit": unit, "problems": problems, "props": props})
        if not wait_next_elapse or next_elapse_is_concrete(props.get("NextElapseUSecMonotonic", "")):
            return LibResult(True, f"{unit} ok", {"unit": unit, "props": props, "problems": []})
        if clock() >= deadline:
            return LibResult(False, f"{unit}: no concrete next elapse",
                             {"error_code": "NO_NEXT_ELAPSE", "unit": unit, "props": props,
                              "problems": [f"no concrete next elapse after {timeout_s}s "
                                           f"(SubState={props.get('SubState')!r}, "
                                           f"NextElapseUSecMonotonic={props.get('NextElapseUSecMonotonic')!r})"]})
        emit("waiting_for_next_elapse", unit=unit, sub_state=props.get("SubState"))
        sleep(POLL_INTERVAL_S)


__all__ = [
    "ACTIONS", "POLL_INTERVAL_S", "apply_units", "converged", "daemon_reload", "install_units",
    "next_elapse_is_concrete", "parse_show", "plan_install", "preflight_user", "unit_action",
    "verify_unit",
]

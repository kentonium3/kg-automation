#!/usr/bin/env python3
"""Deploy entrypoint — Unified Alert Bus verify gate (#701).

Mission: ``unified-alert-bus-01KX5TYT`` (WP05).

The bus library (``scripts/common/alert_bus/``), its bash shim
(``scripts/common/alert_bus.sh``), and the migrated emitter code all reach
office2 through felix-deployer's own ``git pull`` on the tick that applies this
manifest (the same code-delivery path as ``0009``/``0013`` — this entrypoint
does **not** rsync or copy code). What is left for the deploy to prove is the
**runtime env wiring**: the single topic env-file must be present so every
emitter resolves ``FELIX_ALERT_NTFY_TOPIC`` (systemd EnvironmentFile + the shim
sourcing the file for the cron-launched audit). Without it the bus is built but
silently gets ``NTFY_MISSING_TOPIC`` — the CRITICAL gap the post-plan review
caught (D9).

This entrypoint has two jobs — env wiring **installation** and delivery
**proof**:

* ``--dry-run`` — preflight: confirm the topic env-file
  ``/home/claude/.config/felix/alert-bus/env`` is present AND holds a nonblank
  ``FELIX_ALERT_NTFY_TOPIC`` value (an empty skeleton must FAIL — a present-but-
  blank topic still yields ``NTFY_MISSING_TOPIC``). Safe to run anywhere;
  off-office2 the file is legitimately absent, so the failure is reported and
  the script exits non-zero **without** a traceback (the expected local result).
* ``--apply`` — run the same preflight, then:

  1. **Install the three changed systemd units** to the user unit dir and run
     ``systemctl --user daemon-reload`` (FIX 1 / #701). The topic wiring is a
     new ``EnvironmentFile=`` line that lives only in the repo unit files;
     office2's installed units won't see it until reinstalled + reloaded, else
     the emitters silently get ``NTFY_MISSING_TOPIC``. The units are
     timer-driven ``oneshot``s that pick up the new EnvironmentFile on their
     next scheduled run, so no restart is issued (and felix-deployer — the
     running deploy process — is emphatically **not** restarted here). Any
     ``cp``/``systemctl`` failure fails the deploy (exit non-zero).
  2. **Prove delivery** with the alert-bus ``self-test`` (emits a known info
     alert; exits non-zero if delivery fails). The self-test is run with the
     parsed topic injected via ``env=`` (a copy of ``os.environ`` +
     ``FELIX_ALERT_NTFY_TOPIC``) because felix-deployer's own process does NOT
     have that variable set — relying on inherited env would spuriously report
     ``NTFY_MISSING_TOPIC`` (FIX 2 / #701).

  Any failed step exits non-zero so felix-deployer records a **failure**
  (deploys/failed/) rather than a false success.

  Note on the self-test invocation: the ``alert_bus.sh`` shim is deliberately
  best-effort for a plain ``emit`` — it exits 0 so a cron/audit caller never
  fails on a delivery hiccup. This entrypoint therefore invokes the underlying
  ``python3 -m scripts.common.alert_bus self-test`` directly and propagates its
  real exit code.

The topic value is parsed from the env-file only to inject it into the
self-test subprocess — it is **never printed, logged, or copied** into any
output line. Every detail line and recovery message reports presence/nonblank
status, never the value itself.

Exit codes
----------
* ``0`` — dry-run: env-file present; apply: preflight + self-test both passed.
* ``1`` — a check failed (env-file missing, or the self-test did not deliver).
* ``2`` — usage error (missing / wrong-shaped mode argument).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# felix-deployer invokes the entrypoint by path (not via ``python3 -m``), so the
# repo root is not on sys.path unless we put it there ourselves — required
# because this entrypoint imports from ``scripts.deploy.lib.*`` (mirrors the
# calendar-helper entrypoint bootstrap).
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.deploy.lib import verify as verify_lib  # noqa: E402

# --------------------------------------------------------------------------- #
# Grounded constants (D5/D9).
# --------------------------------------------------------------------------- #

# The single topic env-file. Provisioned out-of-band as a credential
# (credential-manifest.json: felix-alert-ntfy-topic); never committed. Its
# presence AND a nonblank FELIX_ALERT_NTFY_TOPIC value are the deploy preflight
# — a missing file OR a blank/absent topic both mean an emitter would get
# NTFY_MISSING_TOPIC.
_TOPIC_ENV_FILE = Path("/home/claude/.config/felix/alert-bus/env")

# The env var the emitters resolve. Parsed from the env-file only to inject into
# the self-test subprocess; NEVER printed or logged.
_TOPIC_ENV_VAR = "FELIX_ALERT_NTFY_TOPIC"

# Delivery proof: the alert-bus `self-test` emits a known info alert and exits
# non-zero if it is not delivered. Invoked directly (not via alert_bus.sh) so we
# get the real exit code — the shim exits 0 for a plain best-effort emit, which
# would mask a failed delivery. Run from the checkout via the `-m` form (office2
# has only `python3`), with the parsed topic injected via env= (FIX 2 #701).
_SELF_TEST_ARGV = ["python3", "-m", "scripts.common.alert_bus", "self-test"]

# The user systemd unit directory the three changed units are installed into.
# Mirrors the felix-health-check.sh deploy pattern (SYSTEMD_USER_DIR =
# ${HOME}/.config/systemd/user, then `systemctl --user daemon-reload`). We honor
# XDG_CONFIG_HOME if set, else fall back to ~/.config, matching systemd's own
# user-unit lookup.
def _user_systemd_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "systemd" / "user"


# The three units that gained the new `EnvironmentFile=` topic line and must be
# reinstalled + reloaded so office2's installed copies pick it up. Paths are
# relative to the repo root (_REPO_ROOT).
_CHANGED_UNITS = (
    Path("scripts/deploy/felix-deployer/felix-deployer.service"),
    Path("scripts/office2/felix-health-check.service"),
    Path("scripts/openclaw/deploy/agent-prompt-sync.service"),
)


def _print_line(prefix: str, summary: str, details: dict) -> None:
    """Emit a summary line + a JSON detail line for the applier's log."""
    sys.stdout.write(f"{prefix}: {summary}\n")
    sys.stdout.write(json.dumps(details, sort_keys=True) + "\n")


def _print_recovery(lines: list[str]) -> None:
    """Print manual-recovery guidance to stderr (no auto-rollback)."""
    sys.stderr.write("RECOVERY (manual — this deploy does not roll back):\n")
    for line in lines:
        sys.stderr.write(f"  - {line}\n")


def _run(
    argv: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """Execute *argv*; return (returncode, stdout, stderr).

    A missing executable (``FileNotFoundError``) is reported as rc=127 with the
    exception text on stderr rather than raising, so a non-office2 sandbox never
    tracebacks.
    """
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            cwd=str(cwd) if cwd is not None else None,
            env=env,
        )
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    return proc.returncode, proc.stdout, proc.stderr


# --------------------------------------------------------------------------- #
# Env-file parsing — extract the topic value (never printed).
# --------------------------------------------------------------------------- #


def _parse_topic_from_env_file(path: Path) -> str | None:
    """Return the ``FELIX_ALERT_NTFY_TOPIC`` value from *path*, else ``None``.

    Parses a simple ``KEY=VALUE`` env-file (systemd EnvironmentFile / shell
    ``source`` compatible). Uses ``split('=', 1)`` so a value containing ``=``
    (or base64 ``=`` padding) is preserved in full. Surrounding quotes are
    stripped. A missing file, a missing key, or a blank value returns ``None``.
    The returned value is used ONLY to inject into the self-test env — it is
    never printed or logged.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    value: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        if key.strip() != _TOPIC_ENV_VAR:
            continue
        val = val.strip()
        if (len(val) >= 2) and (val[0] == val[-1]) and val[0] in ("'", '"'):
            val = val[1:-1]
        value = val  # last assignment wins (env-file semantics)
    if value is None or value.strip() == "":
        return None
    return value


# --------------------------------------------------------------------------- #
# Preflight — the topic env-file must be present AND hold a nonblank topic.
# --------------------------------------------------------------------------- #


def _preflight_env_file() -> tuple[bool, str | None, dict]:
    """Return (ok, topic_value_or_None, details).

    ok is True only when the env-file is present AND holds a nonblank
    ``FELIX_ALERT_NTFY_TOPIC``. The topic value is returned for the caller to
    inject into the self-test env; it is NEVER placed into ``details`` (which is
    logged). Only presence/nonblank status is reported.
    """
    presence = verify_lib.verify_file_present(_TOPIC_ENV_FILE)
    if not presence.ok:
        return (
            False,
            None,
            {
                "env_file": str(_TOPIC_ENV_FILE),
                "topic_status": "file_missing",
                "summary": presence.summary,
            },
        )
    topic = _parse_topic_from_env_file(_TOPIC_ENV_FILE)
    if topic is None:
        return (
            False,
            None,
            {
                "env_file": str(_TOPIC_ENV_FILE),
                "topic_status": "topic_blank_or_absent",
                "summary": (
                    f"{_TOPIC_ENV_VAR} is blank or absent in the env-file "
                    "(empty skeleton) — an emitter would get NTFY_MISSING_TOPIC"
                ),
            },
        )
    return (
        True,
        topic,
        {
            "env_file": str(_TOPIC_ENV_FILE),
            "topic_status": "present_nonblank",
            "summary": f"{_TOPIC_ENV_VAR} present and nonblank",
        },
    )


# --------------------------------------------------------------------------- #
# Install the three changed systemd units + daemon-reload (FIX 1 #701).
# --------------------------------------------------------------------------- #


def _install_units() -> tuple[bool, dict]:
    """Copy the three changed units to the user unit dir + daemon-reload.

    Mirrors the felix-health-check.sh install pattern (cp into
    ${HOME}/.config/systemd/user, then `systemctl --user daemon-reload`).
    Idempotent: cp overwrites, daemon-reload is safe to repeat.

    The units are timer-driven ``oneshot``s — they pick up the new
    ``EnvironmentFile=`` topic line on their next scheduled run, so NO restart
    is issued. felix-deployer (the running deploy process) is deliberately not
    restarted. Any cp / systemctl failure returns ok=False so --apply exits
    non-zero and the deploy is recorded as failed.
    """
    dest_dir = _user_systemd_dir()
    installed: list[str] = []
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, {
            "step": "mkdir_unit_dir",
            "unit_dir": str(dest_dir),
            "error": str(exc),
        }

    for rel in _CHANGED_UNITS:
        src = _REPO_ROOT / rel
        dest = dest_dir / src.name
        if not src.is_file():
            return False, {
                "step": "locate_unit",
                "unit": str(rel),
                "error": f"source unit not found: {src}",
            }
        try:
            shutil.copyfile(src, dest)
        except OSError as exc:
            return False, {
                "step": "copy_unit",
                "unit": src.name,
                "dest": str(dest),
                "error": str(exc),
            }
        installed.append(src.name)

    rc, _stdout, stderr = _run(["systemctl", "--user", "daemon-reload"])
    if rc != 0:
        return False, {
            "step": "daemon_reload",
            "installed_units": installed,
            "systemctl_rc": rc,
            "systemctl_stderr_excerpt": stderr[:400],
        }

    return True, {
        "step": "install_units",
        "unit_dir": str(dest_dir),
        "installed_units": installed,
        "daemon_reloaded": True,
        "note": (
            "timer-driven oneshots; no restart issued — new EnvironmentFile "
            "picked up on next scheduled run"
        ),
    }


# --------------------------------------------------------------------------- #
# Self-test — prove delivery, with the parsed topic injected via env= (FIX 2).
# --------------------------------------------------------------------------- #


def _self_test(topic: str) -> tuple[bool, dict]:
    # felix-deployer's process does NOT have FELIX_ALERT_NTFY_TOPIC set, so we
    # inject the parsed value into a copy of the environment (never printed).
    child_env = dict(os.environ)
    child_env[_TOPIC_ENV_VAR] = topic
    # cwd = checkout root so `-m scripts.common.alert_bus` resolves the package.
    rc, stdout, stderr = _run(_SELF_TEST_ARGV, cwd=_REPO_ROOT, env=child_env)
    details = {
        "self_test_rc": rc,
        "self_test_stdout_excerpt": stdout[:400],
        "self_test_stderr_excerpt": stderr[:400],
    }
    return rc == 0, details


# --------------------------------------------------------------------------- #
# dry-run / apply orchestration.
# --------------------------------------------------------------------------- #


def _preflight_recovery_lines(details: dict) -> list[str]:
    """Recovery guidance for a failed preflight — value never printed."""
    if details.get("topic_status") == "topic_blank_or_absent":
        return [
            f"The env-file {_TOPIC_ENV_FILE} is present but "
            f"{_TOPIC_ENV_VAR} is blank or absent (empty skeleton) — an "
            "emitter would get NTFY_MISSING_TOPIC.",
            "Fill the real topic value out-of-band (secret — never via git):",
            "  printf 'FELIX_ALERT_NTFY_TOPIC=<topic>\\n' > "
            f"{_TOPIC_ENV_FILE} && chmod 600 {_TOPIC_ENV_FILE}",
            "The topic value is a secret (credential felix-alert-ntfy-topic; "
            "template scripts/common/alert_bus.env.sample).",
        ]
    return [
        f"Provision {_TOPIC_ENV_FILE} out-of-band on office2 (mode 0600):",
        "  mkdir -p /home/claude/.config/felix/alert-bus",
        "  printf 'FELIX_ALERT_NTFY_TOPIC=<topic>\\n' > "
        f"{_TOPIC_ENV_FILE} && chmod 600 {_TOPIC_ENV_FILE}",
        "The topic value is a secret — never commit it (credential "
        "felix-alert-ntfy-topic; template scripts/common/alert_bus.env.sample).",
        "Off-office2 the file is legitimately absent — this preflight result "
        "is expected locally.",
    ]


def _dry_run() -> int:
    ok, _topic, details = _preflight_env_file()
    _print_line(
        "DRY-RUN",
        "preflight: topic env-file present + nonblank topic "
        + ("OK" if ok else "FAILED"),
        details,
    )
    _print_line(
        "DRY-RUN",
        "would install "
        + ", ".join(u.name for u in _CHANGED_UNITS)
        + " to the user systemd dir + daemon-reload on --apply",
        {"unit_dir": str(_user_systemd_dir())},
    )
    _print_line(
        "DRY-RUN",
        f"would run `{' '.join(_SELF_TEST_ARGV)}` (topic injected via env=) "
        "to prove delivery on --apply",
        {},
    )
    if not ok:
        _print_recovery(_preflight_recovery_lines(details))
        return 1
    return 0


def _apply() -> int:
    # Preflight — env-file present AND nonblank topic (value never printed).
    ok, topic, details = _preflight_env_file()
    _print_line(
        "APPLY",
        "preflight env-file present + nonblank topic "
        + ("OK" if ok else "FAILED"),
        details,
    )
    if not ok or topic is None:
        _print_recovery(_preflight_recovery_lines(details))
        return 1

    # Install the three changed systemd units + daemon-reload (FIX 1). Must
    # happen so office2's installed units see the new EnvironmentFile= topic
    # line; otherwise every emitter silently gets NTFY_MISSING_TOPIC.
    ok, details = _install_units()
    _print_line(
        "APPLY",
        "install systemd units + daemon-reload " + ("OK" if ok else "FAILED"),
        details,
    )
    if not ok:
        _print_recovery(
            [
                "Installing the changed systemd units failed — office2's "
                "installed units would NOT pick up the new EnvironmentFile= "
                "topic line, so emitters would get NTFY_MISSING_TOPIC.",
                f"Inspect the failing step: {details.get('step')}.",
                "Confirm the user systemd dir is writable and `systemctl "
                "--user daemon-reload` works for the claude user, then re-run.",
            ]
        )
        return 1

    # Self-test — prove delivery, injecting the parsed topic (FIX 2).
    ok, details = _self_test(topic)
    _print_line(
        "APPLY", "self-test delivery " + ("OK" if ok else "FAILED"), details
    )
    if not ok:
        _print_recovery(
            [
                "The alert-bus self-test did not deliver (unreachable endpoint "
                "or curl error — the topic was injected from the env-file).",
                "Confirm ntfy.sh is reachable from office2 and that the topic "
                "value in the env-file is valid.",
                "Inspect the self_test_stderr_excerpt above.",
            ]
        )
        return 1

    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if len(args) != 1 or args[0] not in ("--dry-run", "--apply"):
        sys.stderr.write(
            "usage: deploy-unified-alert-bus.py --dry-run|--apply\n"
        )
        return 2

    if args[0] == "--dry-run":
        return _dry_run()
    return _apply()


if __name__ == "__main__":  # pragma: no cover - module entry
    sys.exit(main())

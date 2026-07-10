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

This is therefore a **thin, verify-only** entrypoint (no state mutation):

* ``--dry-run`` — report whether the topic env-file
  ``/home/claude/.config/felix/alert-bus/env`` is present (the deploy preflight).
  Safe to run anywhere; off-office2 the file is legitimately absent, so a
  missing file is reported and the script exits non-zero **without** a
  traceback (the expected local preflight result).
* ``--apply`` — run the same preflight presence check, then prove delivery with
  the alert-bus ``self-test`` (emits a known info alert; exits non-zero if
  delivery fails). Any failed check exits non-zero so felix-deployer records a
  **failure** (deploys/failed/) rather than a false success.

  Note on the self-test invocation: the ``alert_bus.sh`` shim is deliberately
  best-effort — it **always exits 0** (D10) so a cron/audit caller never fails
  on a delivery hiccup, and its docstring states the ``self-test`` exit-code
  semantics are enforced **inside the Python CLI, not the shim**. Running the
  self-test *through* the shim would therefore mask a delivery failure. To
  honor the "must exit non-zero on a failed check" requirement, this entrypoint
  invokes the same ``self-test`` the shim wraps — ``python3 -m
  scripts.common.alert_bus self-test`` from the checkout (the shim's own body,
  minus the ``exit 0``) — and propagates its real exit code.

No secret is ever read, printed, or copied — the entrypoint only checks the
env-file's *presence* and lets the shim/CLI read the topic value itself.

Exit codes
----------
* ``0`` — dry-run: env-file present; apply: preflight + self-test both passed.
* ``1`` — a check failed (env-file missing, or the self-test did not deliver).
* ``2`` — usage error (missing / wrong-shaped mode argument).
"""
from __future__ import annotations

import json
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
# (credential-manifest.json: felix-alert-ntfy-topic); never committed. Its mere
# presence is the deploy preflight — a missing file means an emitter would get
# NTFY_MISSING_TOPIC.
_TOPIC_ENV_FILE = Path("/home/claude/.config/felix/alert-bus/env")

# Delivery proof: the alert-bus `self-test` emits a known info alert and exits
# non-zero if it is not delivered. Invoked directly (not via alert_bus.sh) so we
# get the real exit code — the shim always exits 0 (D10, best-effort), which
# would mask a failed delivery. This is the exact command the shim wraps, run
# from the checkout via the `-m` form (office2 has only `python3`).
_SELF_TEST_ARGV = ["python3", "-m", "scripts.common.alert_bus", "self-test"]


def _print_line(prefix: str, summary: str, details: dict) -> None:
    """Emit a summary line + a JSON detail line for the applier's log."""
    sys.stdout.write(f"{prefix}: {summary}\n")
    sys.stdout.write(json.dumps(details, sort_keys=True) + "\n")


def _print_recovery(lines: list[str]) -> None:
    """Print manual-recovery guidance to stderr (no auto-rollback)."""
    sys.stderr.write("RECOVERY (manual — this deploy does not roll back):\n")
    for line in lines:
        sys.stderr.write(f"  - {line}\n")


def _run(argv: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
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
        )
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    return proc.returncode, proc.stdout, proc.stderr


# --------------------------------------------------------------------------- #
# Preflight — the topic env-file must be present.
# --------------------------------------------------------------------------- #


def _preflight_env_file() -> tuple[bool, dict]:
    result = verify_lib.verify_file_present(_TOPIC_ENV_FILE)
    return result.ok, {"env_file": str(_TOPIC_ENV_FILE), "summary": result.summary}


# --------------------------------------------------------------------------- #
# Self-test — prove delivery via the shim (cron-context path).
# --------------------------------------------------------------------------- #


def _self_test() -> tuple[bool, dict]:
    # cwd = checkout root so `-m scripts.common.alert_bus` resolves the package.
    rc, stdout, stderr = _run(_SELF_TEST_ARGV, cwd=_REPO_ROOT)
    details = {
        "self_test_rc": rc,
        "self_test_stdout_excerpt": stdout[:400],
        "self_test_stderr_excerpt": stderr[:400],
    }
    return rc == 0, details


# --------------------------------------------------------------------------- #
# dry-run / apply orchestration.
# --------------------------------------------------------------------------- #


def _dry_run() -> int:
    ok, details = _preflight_env_file()
    _print_line(
        "DRY-RUN",
        "preflight: topic env-file " + ("PRESENT" if ok else "MISSING"),
        details,
    )
    _print_line(
        "DRY-RUN",
        f"would run `{' '.join(_SELF_TEST_ARGV)}` to prove delivery on --apply",
        {},
    )
    if not ok:
        _print_recovery(
            [
                f"Provision {_TOPIC_ENV_FILE} out-of-band on office2 (mode 0600):",
                "  mkdir -p /home/claude/.config/felix/alert-bus",
                "  printf 'FELIX_ALERT_NTFY_TOPIC=<topic>\\n' > "
                f"{_TOPIC_ENV_FILE} && chmod 600 {_TOPIC_ENV_FILE}",
                "The topic value is a secret — never commit it (credential "
                "felix-alert-ntfy-topic; template scripts/common/alert_bus.env.sample).",
                "Off-office2 the file is legitimately absent — this dry-run "
                "result is expected locally.",
            ]
        )
        return 1
    return 0


def _apply() -> int:
    # Preflight — the topic env-file must be present.
    ok, details = _preflight_env_file()
    _print_line(
        "APPLY", "preflight env-file " + ("OK" if ok else "FAILED"), details
    )
    if not ok:
        _print_recovery(
            [
                f"The topic env-file {_TOPIC_ENV_FILE} is missing — an emitter "
                "would get NTFY_MISSING_TOPIC.",
                "Provision it out-of-band FIRST (secret — never via git):",
                "  mkdir -p /home/claude/.config/felix/alert-bus",
                "  printf 'FELIX_ALERT_NTFY_TOPIC=<topic>\\n' > "
                f"{_TOPIC_ENV_FILE} && chmod 600 {_TOPIC_ENV_FILE}",
                "Then re-run this deploy.",
            ]
        )
        return 1

    # Self-test — prove delivery.
    ok, details = _self_test()
    _print_line(
        "APPLY", "self-test delivery " + ("OK" if ok else "FAILED"), details
    )
    if not ok:
        _print_recovery(
            [
                "The alert-bus self-test did not deliver (NTFY_MISSING_TOPIC, "
                "unreachable endpoint, or curl error).",
                "Confirm the topic env-file holds a real FELIX_ALERT_NTFY_TOPIC "
                "value and that ntfy.sh is reachable from office2.",
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

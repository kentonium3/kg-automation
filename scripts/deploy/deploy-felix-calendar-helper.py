#!/usr/bin/env python3
"""Deploy entrypoint — Felix Calendar Helper venv provision + gates (#699).

Mission: ``felix-calendar-helper-01KX4H3C`` (WP04).

Provisions the deterministic Google Calendar helper
(``scripts/google/calendar_helper.py``) on office2. office2 has **no pip** —
only ``uv 0.11.2`` at ``~/.local/bin/uv`` — and the system ``python3`` cannot
import the google libraries, so the helper runs under a **dedicated uv venv** at
``/data/services/openclaw/felix-calendar/venv`` (D3/D6; precedent:
``felix-doc-auditor``, ``felix-heartbeat-gate``).

Strict, halt-on-error order (D6 / quickstart.md §0-4). No auto-rollback — on any
failure the script prints recovery instructions and exits non-zero:

  1. **Restic Tier-2 gate** — ``snapshot.verify_restic_recent(max_age_hours=24)``
     before touching any state (the venv + staged creds are state). An operator
     ``--backup-confirmed`` ack path bypasses the automated log check for the
     documented case where a backup was just triggered manually.
  2. **Provision the venv (idempotent)** — ``uv venv … --python 3.12`` (skipped
     when the venv already exists — ``uv venv`` ERRORS on an existing dir, it is
     not a no-op) then ``uv pip install --python <venv>/bin/python "<pinned
     google deps>"``. Safe to re-run: creation is skipped when present and ``uv
     pip install`` is a no-op when the pinned versions are already present. The
     ``uv`` executable is used from ``~/.local/bin/uv`` (uv is NOT installed
     inside the venv). The pins live HERE, not in ``requirements.txt`` — the
     ``python-dependencies`` (pip-packages) baseline stays untouched.
  3. **Verify staged creds** — ``verify.verify_file_present`` for
     ``~/.config/felix/google/personal/{client_secret,token}.json``. Secrets are
     staged **manually** (scp from the Mac); this script only verifies presence
     and NEVER copies a secret. A missing cred fails with a clear "stage creds
     first" message.
  4. **Self-check smoke** — run the helper ``--self-check --account personal``
     via the venv python with ``cwd`` = the repo checkout (so
     ``-m scripts.google.calendar_helper`` resolves). A non-zero exit fails the
     deploy.

Rebaseline scope (D6): only the mission's **openclaw.json** ``skills`` edit is a
monitored audited surface; it is a manual out-of-band office2 change rebaselined
manually. This entrypoint touches no openclaw.json and adds no repo
dependencies, so it drifts no baseline on its own.

CLI contract (per ``docs/runbooks/deploy/discipline.md``):

* ``--dry-run`` — print each planned step; NO side effects on office2. Safe to
  run anywhere (off-office2 too — a missing ``uv`` / creds dir is reported, not
  fatal, in dry-run).
* ``--apply`` — execute all four gates in order; halt at the first failure.
* ``--backup-confirmed`` — operator ack that a recent Restic backup exists;
  skips the automated log-recency check in step 1. Valid with either mode.

Exit codes
----------
* ``0`` — dry-run printed successfully, OR apply completed every gate.
* ``1`` — a gate failed (Restic / venv / creds / self-check). Nothing is rolled
  back; recovery instructions are printed to stderr.
* ``2`` — usage error (missing / wrong-shaped mode argument).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# felix-deployer invokes the entrypoint by path (not via ``python3 -m``), so the
# repo root is not on sys.path unless we put it there ourselves — required
# because this entrypoint imports from ``scripts.deploy.lib.*``.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.deploy.lib import snapshot as snapshot_lib  # noqa: E402
from scripts.deploy.lib import verify as verify_lib  # noqa: E402

# --------------------------------------------------------------------------- #
# Grounded constants (D3/D6, live office2 probing during planning).
# --------------------------------------------------------------------------- #

# The uv executable lives on the claude PATH at ~/.local/bin/uv; office2 has no
# pip. Use uv to BUILD and INSTALL INTO the venv (uv is not inside the venv).
_UV = str(Path.home() / ".local/bin/uv")

_VENV_DIR = Path("/data/services/openclaw/felix-calendar/venv")
_VENV_PYTHON = _VENV_DIR / "bin/python"
_VENV_PYTHON_VERSION = "3.12"

# Pinned google deps. Recorded HERE (not requirements.txt) so the
# python-dependencies baseline is untouched (D6). Pins match the versions the
# Mac auth/consent flow was validated against, giving dev↔office2 parity.
_GOOGLE_DEPS: tuple[str, ...] = (
    "google-api-python-client==2.198.0",
    "google-auth==2.55.2",
    "google-auth-oauthlib==1.4.0",
)

# Manually-staged personal OAuth creds (secrets — never copied by this script).
_CREDS_DIR = Path.home() / ".config/felix/google/personal"
_CRED_FILES: tuple[Path, ...] = (
    _CREDS_DIR / "client_secret.json",
    _CREDS_DIR / "token.json",
)

# Self-check smoke: the helper module, run from the checkout via the venv python.
_HELPER_MODULE = "scripts.google.calendar_helper"
_SELF_CHECK_ACCOUNT = "personal"


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
    """Execute *argv* and return (returncode, stdout, stderr).

    A missing executable (``FileNotFoundError`` — e.g. ``uv`` absent from a
    non-office2 dry-run sandbox) is reported as rc=127 with the exception text
    on stderr rather than raising, so callers never need a bare ``except``
    around every call site.
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
# Gate 1 — Restic Tier-2 snapshot recency.
# --------------------------------------------------------------------------- #


def _gate_restic(*, backup_confirmed: bool) -> tuple[bool, dict]:
    if backup_confirmed:
        return True, {"restic": "operator-acked via --backup-confirmed"}
    result = snapshot_lib.verify_restic_recent(max_age_hours=24)
    return result.ok, {"summary": result.summary, **dict(result.details)}


# --------------------------------------------------------------------------- #
# Gate 2 — idempotent venv provisioning via uv.
# --------------------------------------------------------------------------- #


def _gate_provision_venv() -> tuple[bool, dict]:
    details: dict = {"venv": str(_VENV_DIR)}

    # (a) Create the venv ONLY if it does not already exist. `uv venv` is NOT a
    #     no-op on an existing venv — it errors ("already exists … use --clear"),
    #     which broke re-runs. Skipping when the interpreter is already present
    #     makes provisioning idempotent without destroying/reinstalling the venv
    #     (the pip-install step below reconciles the pinned deps either way).
    if _VENV_PYTHON.exists():
        details["venv_create_rc"] = 0
        details["venv_create"] = "skipped (already present)"
    else:
        rc, stdout, stderr = _run(
            [_UV, "venv", str(_VENV_DIR), "--python", _VENV_PYTHON_VERSION]
        )
        details["venv_create_rc"] = rc
        if rc != 0:
            details["venv_create_stderr"] = stderr[:400]
            return False, details

    # (b) Install the pinned google deps INTO the venv. Idempotent: a no-op when
    #     the pinned versions are already present.
    rc, stdout, stderr = _run(
        [_UV, "pip", "install", "--python", str(_VENV_PYTHON), *_GOOGLE_DEPS]
    )
    details["pip_install_rc"] = rc
    details["pinned_deps"] = list(_GOOGLE_DEPS)
    if rc != 0:
        details["pip_install_stderr"] = stderr[:400]
        return False, details

    return True, details


# --------------------------------------------------------------------------- #
# Gate 3 — verify manually-staged creds are present (NEVER copies secrets).
# --------------------------------------------------------------------------- #


def _gate_verify_creds() -> tuple[bool, dict]:
    details: dict = {"creds_dir": str(_CREDS_DIR)}
    missing: list[str] = []
    for cred in _CRED_FILES:
        result = verify_lib.verify_file_present(cred)
        if not result.ok:
            missing.append(str(cred))
    if missing:
        details["missing"] = missing
        return False, details
    details["present"] = [str(c) for c in _CRED_FILES]
    return True, details


# --------------------------------------------------------------------------- #
# Gate 4 — self-check smoke via the venv python (cwd = checkout).
# --------------------------------------------------------------------------- #


def _gate_self_check() -> tuple[bool, dict]:
    rc, stdout, stderr = _run(
        [
            str(_VENV_PYTHON),
            "-m",
            _HELPER_MODULE,
            "--self-check",
            "--account",
            _SELF_CHECK_ACCOUNT,
        ],
        cwd=_REPO_ROOT,
    )
    details = {
        "self_check_rc": rc,
        "self_check_stdout_excerpt": stdout[:400],
        "self_check_stderr_excerpt": stderr[:400],
    }
    return rc == 0, details


# --------------------------------------------------------------------------- #
# dry-run / apply orchestration.
# --------------------------------------------------------------------------- #


def _dry_run(*, backup_confirmed: bool) -> int:
    _print_line(
        "DRY-RUN",
        "would verify Restic snapshot <=24h"
        + (" (SKIPPED — --backup-confirmed acked)" if backup_confirmed else ""),
        {"backup_confirmed": backup_confirmed},
    )
    _print_line(
        "DRY-RUN",
        f"would provision venv at {_VENV_DIR} via `{_UV} venv --python "
        f"{_VENV_PYTHON_VERSION}` then `{_UV} pip install --python "
        f"{_VENV_PYTHON}` with pinned google deps (idempotent)",
        {"pinned_deps": list(_GOOGLE_DEPS)},
    )
    _print_line(
        "DRY-RUN",
        f"would verify staged creds present under {_CREDS_DIR} "
        "(NEVER copies secrets — manual scp staging)",
        {"cred_files": [str(c) for c in _CRED_FILES]},
    )
    _print_line(
        "DRY-RUN",
        f"would run `{_VENV_PYTHON} -m {_HELPER_MODULE} --self-check "
        f"--account {_SELF_CHECK_ACCOUNT}` (cwd={_REPO_ROOT}) as the smoke gate",
        {},
    )
    return 0


def _apply(*, backup_confirmed: bool) -> int:
    # Gate 1 — Restic Tier-2 gate (before any state change).
    ok, details = _gate_restic(backup_confirmed=backup_confirmed)
    _print_line("APPLY", "restic gate " + ("OK" if ok else "FAILED"), details)
    if not ok:
        _print_recovery(
            [
                "Trigger a Restic backup, then re-run this deploy:",
                "  ssh office2-kgale  # then run the backup driver manually",
                "Or, if a recent backup exists, re-run with --backup-confirmed.",
            ]
        )
        return 1

    # Gate 2 — provision the venv (idempotent).
    ok, details = _gate_provision_venv()
    _print_line("APPLY", "venv provision " + ("OK" if ok else "FAILED"), details)
    if not ok:
        _print_recovery(
            [
                f"Inspect the uv output above; ensure {_UV} is on PATH on office2.",
                f"Manually: {_UV} venv {_VENV_DIR} --python {_VENV_PYTHON_VERSION}",
                f"Then: {_UV} pip install --python {_VENV_PYTHON} "
                + " ".join(f'"{d}"' for d in _GOOGLE_DEPS),
            ]
        )
        return 1

    # Gate 3 — verify manually-staged creds (never copies secrets).
    ok, details = _gate_verify_creds()
    _print_line("APPLY", "creds presence " + ("OK" if ok else "FAILED"), details)
    if not ok:
        _print_recovery(
            [
                "Stage the personal OAuth creds FIRST (secrets — never via git):",
                "  scp ~/.config/felix/google/personal/client_secret.json "
                "office2-claude:~/.config/felix/google/personal/client_secret.json",
                "  scp ~/.config/felix/google/personal/token.json "
                "office2-claude:~/.config/felix/google/personal/token.json",
                "  ssh office2-claude 'chmod 700 ~/.config/felix/google "
                "~/.config/felix/google/personal && chmod 600 "
                "~/.config/felix/google/personal/*.json'",
                "Then re-run this deploy.",
            ]
        )
        return 1

    # Gate 4 — self-check smoke.
    ok, details = _gate_self_check()
    _print_line("APPLY", "self-check smoke " + ("OK" if ok else "FAILED"), details)
    if not ok:
        _print_recovery(
            [
                "The helper --self-check failed (auth/scope/refresh or import).",
                "Confirm the venv deps installed and the staged token carries the "
                "calendar.events scope (re-mint Mac-side if the scope is narrower).",
                "Inspect the self_check_stderr_excerpt above.",
            ]
        )
        return 1

    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    backup_confirmed = False
    if "--backup-confirmed" in args:
        backup_confirmed = True
        args = [a for a in args if a != "--backup-confirmed"]

    if len(args) != 1 or args[0] not in ("--dry-run", "--apply"):
        sys.stderr.write(
            "usage: deploy-felix-calendar-helper.py --dry-run|--apply "
            "[--backup-confirmed]\n"
        )
        return 2

    if args[0] == "--dry-run":
        return _dry_run(backup_confirmed=backup_confirmed)
    return _apply(backup_confirmed=backup_confirmed)


if __name__ == "__main__":  # pragma: no cover - module entry
    sys.exit(main())

#!/usr/bin/env python3
"""Deploy entrypoint — Felix WhatsApp time-logging to Sheets (#703, WP05).

Mission: ``felix-time-logging-01KX79HT`` (WP05, IC-05).

Provisions the deterministic Google Sheets helper
(``scripts/google/sheets_helper.py`` + ``scripts/google/timelog.py``) on
office2, gates on a **no-emit dry-run self-test** (the #711 lesson — a
self-test must never page the operator), and — only once that self-test is
clean — triggers a prompt-sync tick and verifies the deployed ``main`` prompt
carries the time-logging recognizer, before declaring success.

office2 has **no pip** — only ``uv 0.11.2`` at ``~/.local/bin/uv`` — so the
Sheets helper runs under the **same dedicated uv venv** the #699 calendar
helper provisioned at ``/data/services/openclaw/felix-calendar/venv``
(``google-api-python-client`` is a shared dependency; this entrypoint reuses
that venv rather than creating a second one for the same Google client
libraries).

Two Kent-in-the-loop operator preconditions are **presence-checked, never
automated** by this entrypoint (see ``docs/runbooks/timelog.md``):

1. **Sheets-scope re-consent** — the ``personal`` Google token must already be
   re-minted with the combined ``calendar + spreadsheets`` scope and staged at
   ``~/.config/felix/google/personal/{client_secret,token}.json`` (browser
   OAuth grant; only Kent can complete it).
2. **Workbook bootstrap** — the Felix-owned time-tracking workbook must exist
   and its id recorded at ``~/.config/felix/timelog/workbook.json`` (one-time
   operator step).

Strict, halt-on-error apply order (no auto-rollback — on any failure the
script prints recovery instructions and exits non-zero):

  1. **Venv/deps gate** — confirm the shared uv venv exists and
     ``google-api-python-client`` (+ ``google-auth*``) are importable in it
     (idempotent provision, reusing the #699 pattern).
  2. **Staged-cred + workbook-config presence** — verify the re-consented
     personal token AND the workbook-id config are present. NEVER copies a
     secret; presence-check only. A missing precondition fails with a
     "complete the operator re-consent / bootstrap first" message.
  3. **Dry-run self-test that emits NOTHING + gate (#711 — CRITICAL).** Runs
     ``sheets_helper --self-check --account personal`` (confirms
     creds/scope/reach WITHOUT writing) and ``timelog`` with a client
     guaranteed not to resolve to any tab (confirms the normalizer runs
     end-to-end and returns a typed ``unknown_client`` result WITHOUT ever
     reaching ``append-row`` and WITHOUT emitting any alert — the
     ``unknown_client``/``ambiguous`` paths in ``timelog.py`` never call
     ``_alert_write_failed``). If either is not clean, the deploy FAILS here
     with nothing enabled/synced, so no false alert ever fires.
  4. **Prompt-sync trigger + verify (only after the self-test is clean).**
     Triggers ``systemctl --user start agent-prompt-sync.service``, then
     verifies the deployed ``main`` prompt (resolved from
     ``service-inventory.json`` ``agents.main.workspace``) carries the
     time-logging recognizer heading. A missing recognizer is a verification
     failure (likely WP04 hasn't reached main).
  5. **Report via the #701 bus** — outcome (success/failure) emitted through
     ``scripts.common.alert_bus.emit``; best-effort, never raises.

CLI contract (per ``docs/runbooks/deploy/discipline.md``):

* ``--dry-run`` — print each planned step; **no side effects** on office2.
  Safe to run anywhere (off-office2 too).
* ``--apply`` — execute all steps in order; halt at the first failure.

Exit codes
----------
* ``0`` — dry-run printed successfully, OR apply completed every step.
* ``1`` — a step failed (venv/deps / creds+workbook presence / self-test /
  prompt-sync-verify). Nothing is rolled back; recovery instructions are
  printed to stderr.
* ``2`` — usage error (missing / wrong-shaped mode argument).

Rebaseline: **not required** — main's ``AGENTS.md`` is an *unmonitored*
audited surface (gap #621 — ``audit.sh`` does not hash deployed
``AGENTS.md``), and ``scripts/google/**`` / ``scripts/deploy/**``'s new
time-log code are not hashed baselines.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# felix-deployer invokes the entrypoint by path (not via `python3 -m`), so the
# repo root is not on sys.path unless we put it there ourselves.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.common.alert_bus import emit  # noqa: E402
from scripts.common.alert_bus.model import Alert, Severity  # noqa: E402
from scripts.openclaw.deploy.deploy_agent_prompts import iter_agents  # noqa: E402

# --------------------------------------------------------------------------- #
# Grounded constants.
# --------------------------------------------------------------------------- #

# Reuse the #699 calendar-helper venv — same google-api-python-client/
# google-auth family, no need to provision a second venv for the same libs.
_UV = str(Path.home() / ".local/bin/uv")
_VENV_DIR = Path("/data/services/openclaw/felix-calendar/venv")
_VENV_PYTHON = _VENV_DIR / "bin/python"
_VENV_PYTHON_VERSION = "3.12"

_GOOGLE_DEPS: tuple[str, ...] = (
    "google-api-python-client==2.198.0",
    "google-auth==2.55.2",
    "google-auth-oauthlib==1.4.0",
)

# Manually-staged, re-consented personal OAuth creds (secrets — never copied).
_CREDS_DIR = Path.home() / ".config/felix/google/personal"
_CRED_FILES: tuple[Path, ...] = (
    _CREDS_DIR / "client_secret.json",
    _CREDS_DIR / "token.json",
)

# One-time operator-bootstrapped workbook-id config (never copied by this
# script — presence-check only).
_WORKBOOK_CONFIG = Path.home() / ".config/felix/timelog/workbook.json"

_SELF_CHECK_ACCOUNT = "personal"

# A client name guaranteed not to match any real tab/alias in
# timelog-clients.json, so the `timelog` self-test exercises the full
# validate -> list-tabs -> resolve path and returns `unknown_client` WITHOUT
# ever reaching append-row and WITHOUT emitting an alert (unknown_client /
# ambiguous never call _alert_write_failed in timelog.py).
_SELF_TEST_CLIENT = "__deploy_self_test_no_such_client__"
_SELF_TEST_CONVERSATION = "deploy-self-test"
_SELF_TEST_SOURCE_MSG_ID = "deploy-self-test-0"

_SERVICE_INVENTORY = (
    _REPO_ROOT / "docs" / "design" / "architecture" / "data" / "service-inventory.json"
)
_MAIN_SLUG = "main"
# The heading WP04 added to scripts/openclaw/agents/main/AGENTS.md; presence
# in the deployed prompt is the recognizer-landed signal this gate checks.
_TIMELOG_RECOGNIZER_MARKER = "## Time-logging (option A, direct helper call)"


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

    A missing executable (``FileNotFoundError`` — e.g. ``uv``/``systemctl``
    absent from a non-office2 sandbox) is reported as rc=127 with the
    exception text on stderr rather than raising.
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
# Step 1 — idempotent venv/deps gate (reuses the #699 shared venv).
# --------------------------------------------------------------------------- #


def _step_venv_deps() -> tuple[bool, dict]:
    details: dict = {"venv": str(_VENV_DIR)}

    if _VENV_PYTHON.exists():
        details["venv_create_rc"] = 0
        details["venv_create"] = "skipped (already present)"
    else:
        rc, _stdout, stderr = _run(
            [_UV, "venv", str(_VENV_DIR), "--python", _VENV_PYTHON_VERSION]
        )
        details["venv_create_rc"] = rc
        if rc != 0:
            details["venv_create_stderr"] = stderr[:400]
            return False, details

    rc, _stdout, stderr = _run(
        [_UV, "pip", "install", "--python", str(_VENV_PYTHON), *_GOOGLE_DEPS]
    )
    details["pip_install_rc"] = rc
    details["pinned_deps"] = list(_GOOGLE_DEPS)
    if rc != 0:
        details["pip_install_stderr"] = stderr[:400]
        return False, details

    return True, details


# --------------------------------------------------------------------------- #
# Step 2 — staged-cred + workbook-config presence (never copies secrets).
# --------------------------------------------------------------------------- #


def _step_verify_preconditions() -> tuple[bool, dict]:
    details: dict = {
        "creds_dir": str(_CREDS_DIR),
        "workbook_config": str(_WORKBOOK_CONFIG),
    }
    missing: list[str] = []
    for cred in _CRED_FILES:
        if not cred.exists():
            missing.append(str(cred))
    if not _WORKBOOK_CONFIG.exists():
        missing.append(str(_WORKBOOK_CONFIG))
    if missing:
        details["missing"] = missing
        return False, details
    details["present"] = [str(c) for c in (*_CRED_FILES, _WORKBOOK_CONFIG)]
    return True, details


# --------------------------------------------------------------------------- #
# Step 3 — dry-run self-test (no emit, no state mutation) + gate (#711).
# --------------------------------------------------------------------------- #


def _sheets_helper_self_check_argv() -> list[str]:
    return [
        str(_VENV_PYTHON),
        "-m",
        "scripts.google.sheets_helper",
        "--self-check",
        "--account",
        _SELF_CHECK_ACCOUNT,
    ]


def _timelog_self_test_argv() -> list[str]:
    return [
        str(_VENV_PYTHON),
        "-m",
        "scripts.google.timelog",
        "--client",
        _SELF_TEST_CLIENT,
        "--hours",
        "0.1",
        "--date",
        "today",
        "--description",
        "deploy self-test — never written",
        "--channel",
        "deploy-self-test",
        "--conversation",
        _SELF_TEST_CONVERSATION,
        "--source-msg-id",
        _SELF_TEST_SOURCE_MSG_ID,
        "--account",
        _SELF_CHECK_ACCOUNT,
        "--json",
    ]


def _step_dry_run_self_test() -> tuple[bool, dict]:
    details: dict = {}

    sh_argv = _sheets_helper_self_check_argv()
    rc, stdout, stderr = _run(sh_argv, cwd=_REPO_ROOT)
    details["sheets_helper_self_check_rc"] = rc
    details["sheets_helper_self_check_stdout_excerpt"] = stdout[:400]
    details["sheets_helper_self_check_stderr_excerpt"] = stderr[:400]
    if rc != 0:
        details["fault"] = "sheets_helper --self-check failed (see excerpt above)"
        return False, details

    tl_argv = _timelog_self_test_argv()
    rc, stdout, stderr = _run(tl_argv, cwd=_REPO_ROOT)
    details["timelog_self_test_rc"] = rc
    details["timelog_self_test_stdout_excerpt"] = stdout[:400]
    details["timelog_self_test_stderr_excerpt"] = stderr[:400]
    if rc != 0:
        details["fault"] = "timelog self-test exited non-zero (usage error, F9)"
        return False, details

    try:
        result = json.loads(stdout.strip().splitlines()[-1])
    except (ValueError, IndexError) as exc:
        details["timelog_self_test_parse_error"] = str(exc)
        return False, details

    status = result.get("status")
    details["timelog_self_test_status"] = status
    if status != "unknown_client":
        details["timelog_self_test_unexpected_status"] = (
            "expected `unknown_client` for the guaranteed-unresolvable "
            f"self-test client (got {status!r}) — the normalizer either "
            "resolved a real tab (unexpected client-list collision) or hit "
            "an unhandled path; the self-test must never reach append-row"
        )
        return False, details

    return True, details


# --------------------------------------------------------------------------- #
# Step 4 — prompt-sync trigger + deployed main-prompt verification.
# --------------------------------------------------------------------------- #


def _deployed_main_prompt() -> Path | None:
    """Resolve the deployed ``main`` AGENTS.md path from service-inventory.json."""
    for agent in iter_agents(_SERVICE_INVENTORY):
        if agent.slug == _MAIN_SLUG:
            return agent.workspace / "AGENTS.md"
    return None


def _step_prompt_sync_and_verify() -> tuple[bool, dict]:
    details: dict = {}

    rc, _stdout, stderr = _run(
        ["systemctl", "--user", "start", "agent-prompt-sync.service"]
    )
    details["prompt_sync_start_rc"] = rc
    if rc != 0:
        details["prompt_sync_start_stderr"] = stderr[:400]
        return False, details

    main_prompt = _deployed_main_prompt()
    if main_prompt is None:
        details["error"] = "could not resolve main's deployed workspace from service-inventory.json"
        details["inventory"] = str(_SERVICE_INVENTORY)
        return False, details
    details["main_prompt_path"] = str(main_prompt)

    if not main_prompt.exists():
        details["error"] = f"deployed main prompt not found at {main_prompt}"
        return False, details

    try:
        content = main_prompt.read_text(encoding="utf-8")
    except OSError as exc:
        details["error"] = f"could not read deployed main prompt: {exc}"
        return False, details

    has_marker = _TIMELOG_RECOGNIZER_MARKER in content
    details["recognizer_present"] = has_marker
    if not has_marker:
        details["error"] = (
            "time-logging recognizer heading "
            f"{_TIMELOG_RECOGNIZER_MARKER!r} not found in deployed main "
            "prompt — WP04's AGENTS.md change may not have reached main yet"
        )
        return False, details

    return True, details


# --------------------------------------------------------------------------- #
# dry-run / apply orchestration.
# --------------------------------------------------------------------------- #


def _dry_run() -> int:
    _print_line(
        "DRY-RUN",
        f"would provision/verify venv at {_VENV_DIR} via `{_UV} venv --python "
        f"{_VENV_PYTHON_VERSION}` then `{_UV} pip install --python "
        f"{_VENV_PYTHON}` with pinned google deps (idempotent; shared with "
        "the #699 calendar helper)",
        {"pinned_deps": list(_GOOGLE_DEPS)},
    )
    _print_line(
        "DRY-RUN",
        f"would verify staged creds present under {_CREDS_DIR} and workbook "
        f"config present at {_WORKBOOK_CONFIG} (NEVER copies secrets — "
        "manual operator re-consent + bootstrap)",
        {
            "cred_files": [str(c) for c in _CRED_FILES],
            "workbook_config": str(_WORKBOOK_CONFIG),
        },
    )
    _print_line(
        "DRY-RUN",
        "would run `sheets_helper --self-check --account personal` "
        "(no-write auth/scope/reach check) then `timelog` with a "
        "guaranteed-unresolvable client (no-write normalizer check; must "
        "return `unknown_client` without reaching append-row) as a no-emit "
        "self-test, and GATE go-live on it being clean (#711)",
        {
            "sheets_helper_argv": _sheets_helper_self_check_argv(),
            "timelog_argv": _timelog_self_test_argv(),
        },
    )
    main_prompt = _deployed_main_prompt()
    _print_line(
        "DRY-RUN",
        "would (only if the self-test is clean) trigger `systemctl --user "
        "start agent-prompt-sync.service` and verify the time-logging "
        "recognizer landed in deployed main's AGENTS.md",
        {"main_prompt_path": str(main_prompt) if main_prompt else None},
    )
    return 0


def _report(*, ok: bool, phase: str, details: dict) -> None:
    """Best-effort outcome report via the #701 bus; never raises."""
    try:
        severity = Severity.INFO if ok else Severity.ERROR
        title = (
            "felix-timelog deploy succeeded"
            if ok
            else f"felix-timelog deploy failed: {phase}"
        )
        emit(
            Alert(
                source="felix-deployer/deploy-timelog",
                severity=severity,
                title=title,
                description=(
                    "Deployed the Felix time-logging Sheets helper (clean "
                    "no-emit self-test gated the go-live) + prompt-sync "
                    "verification."
                    if ok
                    else f"Deploy halted at phase {phase!r}."
                ),
                details={key: str(value) for key, value in details.items()},
            )
        )
    except Exception:  # noqa: BLE001 - fail-safe: reporting must never break the deploy
        pass


def _apply() -> int:
    ok, details = _step_venv_deps()
    _print_line("APPLY", "venv/deps gate " + ("OK" if ok else "FAILED"), details)
    if not ok:
        _print_recovery(
            [
                f"Inspect the uv output above; ensure {_UV} is on PATH on office2.",
                f"Manually: {_UV} venv {_VENV_DIR} --python {_VENV_PYTHON_VERSION}",
                f"Then: {_UV} pip install --python {_VENV_PYTHON} "
                + " ".join(f'"{d}"' for d in _GOOGLE_DEPS),
            ]
        )
        _report(ok=False, phase="venv_deps", details=details)
        return 1

    ok, details = _step_verify_preconditions()
    _print_line(
        "APPLY", "creds + workbook-config presence " + ("OK" if ok else "FAILED"), details
    )
    if not ok:
        _print_recovery(
            [
                "Complete the operator re-consent FIRST (Kent-in-the-loop, "
                "browser OAuth): re-mint the `personal` Google token with "
                "combined `calendar + spreadsheets` scopes, then stage it at "
                f"{_CREDS_DIR} (0600) on office2.",
                "Complete the one-time workbook bootstrap: create the "
                "Felix-owned time-tracking workbook and record its id at "
                f"{_WORKBOOK_CONFIG} (0600).",
                "See docs/runbooks/timelog.md for both procedures, then re-run "
                "this deploy.",
            ]
        )
        _report(ok=False, phase="preconditions", details=details)
        return 1

    # Dry-run self-test that emits NOTHING, gated BEFORE prompt-sync (#711).
    ok, details = _step_dry_run_self_test()
    _print_line("APPLY", "no-emit self-test " + ("OK" if ok else "FAILED"), details)
    if not ok:
        _print_recovery(
            [
                "The no-emit self-test failed. Either sheets_helper "
                "--self-check could not authenticate/reach the workbook "
                "(auth/scope/refresh — see sheets_helper_self_check_stderr_"
                "excerpt), or the timelog self-test did not return "
                "`unknown_client` for a guaranteed-unresolvable client (see "
                "timelog_self_test_* details).",
                "Verify locally (from the checkout, via the venv python): "
                f"{' '.join(_sheets_helper_self_check_argv())}",
                f"{' '.join(_timelog_self_test_argv())}",
                "Nothing was enabled/synced — no false alert fired.",
            ]
        )
        _report(ok=False, phase="dry_run_self_test", details=details)
        return 1

    ok, details = _step_prompt_sync_and_verify()
    _print_line(
        "APPLY", "prompt-sync + main recognizer verify " + ("OK" if ok else "FAILED"), details
    )
    if not ok:
        _print_recovery(
            [
                "Confirm agent-prompt-sync.service ran successfully:",
                "  systemctl --user status agent-prompt-sync.service",
                "Confirm WP04's time-logging recognizer heading is present in "
                "deployed main's AGENTS.md (see 'error' above).",
                "This may indicate WP04's AGENTS.md change has not reached "
                "main yet.",
            ]
        )
        _report(ok=False, phase="prompt_sync_verify", details=details)
        return 1

    _report(ok=True, phase="complete", details=details)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if len(args) != 1 or args[0] not in ("--dry-run", "--apply"):
        sys.stderr.write("usage: deploy-timelog.py --dry-run|--apply\n")
        return 2

    if args[0] == "--dry-run":
        return _dry_run()
    return _apply()


if __name__ == "__main__":  # pragma: no cover - module entry
    sys.exit(main())

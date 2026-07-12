"""Deterministic weekly-report driver (mission deterministic-cron-hardening-01KXA4PX, #723).

Runs the existing weekly-report helper
(:mod:`scripts.habits.query_active_habits_weekly`), composes the
outbound message, delivers it via ``openclaw message send``, confirms
delivery *truthfully* against the empirically-verified predicate (C1),
and writes a freshness tick — with **no LLM turn** anywhere in the
path (FR-004).

Authoritative contracts:

- ``kitty-specs/deterministic-cron-hardening-01KXA4PX/contracts/weekly_report_driver.md`` (IC-03)
- ``kitty-specs/deterministic-cron-hardening-01KXA4PX/contracts/post-plan-review-resolutions.md``
  — C1 (delivery-confirmation predicate), C2 (``--self-test`` vs ``--dry-run``),
  H4 (tick schema must not lie), M11 (systemd unit fields, out of scope for
  this module).

Behavior (contract steps)
--------------------------
1. Run the report helper in-process
   (``query_active_habits_weekly --output text`` equivalent) and capture
   its rendered report body.
2. On helper failure (non-zero / exception): write a ``failure`` tick and
   return a non-zero exit code. Never deliver a partial or fabricated
   report.
3. Compose ``"<attribution>\\n\\n" + report_body``. The report portion is
   byte-identical to the helper's output (FR-005).
4. Deliver via ``openclaw message send --channel whatsapp --target <E.164>
   --message <message> --json`` (absolute ``/usr/bin/openclaw`` — systemd
   units have no ``PATH``).
5. Confirm delivery: ``delivery_confirmed=True`` **only** when the C1
   predicate holds (exit 0 AND a non-empty ``messageId`` AND
   ``dryRun == False``). Otherwise write a ``failure`` tick and return
   non-zero (FR-006 — never claim delivery that did not happen).
6. Write ``last-tick.json`` atomically:
   ``{completed_at_utc, exit_code, status, delivery_confirmed,
   failure_reason}``. ``status="success"`` only when delivered.

Modes
-----
- ``--self-test``: runs the helper + composes the message, calls the send
  path with ``--dry-run`` (no real send), and **writes** a fresh tick to a
  SEPARATE self-test-scoped path (:data:`SELF_TEST_TICK_PATH`) — never to
  the production ``last-tick.json``. This is the WP04 deploy gate — it
  exercises the full path without messaging Kent, and without the
  freshness canary mistaking a dry-run for a delivered report (post-merge
  Codex review, #723).
- ``--dry-run``: local preview only. Prints the composed message; issues
  no send and writes **no** state.
- default (no flag): the real scheduled run — real send + the production
  ``last-tick.json``.

All effects (running the helper, sending the message, the clock, and the
tick path) are injectable so the test suite
(``tests/habits/test_weekly_report_driver.py``) runs fully offline.

Public surface
--------------
Constants: ``ATTRIBUTION_LINE``, ``DEFAULT_TARGET``, ``DEFAULT_TICK_PATH``,
    ``SELF_TEST_TICK_PATH``, ``OPENCLAW_BIN``
Dataclasses: ``HelperResult``, ``SendResult``
Functions: ``run_report_helper``, ``send_message``, ``compose_message``,
    ``confirm_delivery``, ``write_tick``, ``run``, ``main``
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from scripts.habits import query_active_habits_weekly as weekly_helper

# --------------------------------------------------------------------------- #
# Constants.
# --------------------------------------------------------------------------- #

#: Fixed identity line prepended to every outbound message so the
#: attribution survives the move off the agent (contract §Attribution).
ATTRIBUTION_LINE = "Sent by felix-habits-weekly-driver"

#: Verified live delivery target (contract IC-03).
DEFAULT_TARGET = "+16179300916"

#: Freshness-tick home (mirrors the canary/#720 ``last-tick.json`` pattern).
#: Written ONLY by real (``mode="run"``) scheduled runs — the freshness
#: canary reads this path's ``status`` to decide the producer is healthy,
#: so a dry-run must never touch it (post-merge Codex review, #723).
DEFAULT_TICK_PATH = Path(
    "/data/services/felix-habits-weekly/state/last-tick.json"
)

#: Self-test-scoped tick path — written by ``--self-test`` instead of
#: :data:`DEFAULT_TICK_PATH` so a dry-run self-test can never be mistaken
#: by the freshness canary for a real, delivered weekly report.
SELF_TEST_TICK_PATH = DEFAULT_TICK_PATH.with_name(
    "self-test-" + DEFAULT_TICK_PATH.name
)

#: Absolute path — systemd units have no ``PATH`` (recurring deploy gotcha;
#: see the canary probes' ``openclaw cron list`` invocation for precedent).
OPENCLAW_BIN = "/usr/bin/openclaw"


# --------------------------------------------------------------------------- #
# Effect result types.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class HelperResult:
    """Outcome of running the report helper."""

    ok: bool
    report_body: str = ""
    error: str = ""


@dataclass(frozen=True)
class SendResult:
    """Outcome of the ``openclaw message send`` invocation.

    ``exit_code`` is the process exit code; ``stdout``/``stderr`` are the
    raw captured streams (``stdout`` is expected to be JSON on success but
    is not assumed to be — malformed JSON must be handled, not raised).
    """

    exit_code: int
    stdout: str = ""
    stderr: str = ""


# Injectable effect signatures (kept as plain Callable aliases so tests can
# substitute pure functions with no subprocess/network/clock access).
RunHelper = Callable[[], HelperResult]
SendMessage = Callable[[str, bool], SendResult]  # (message, dry_run) -> SendResult
NowFn = Callable[[], datetime]


# --------------------------------------------------------------------------- #
# Default effects (production wiring).
# --------------------------------------------------------------------------- #
def run_report_helper() -> HelperResult:
    """Run the weekly-report helper in-process and capture its report body.

    Mirrors ``query_active_habits_weekly --output text``: the helper's
    ``main()`` writes ``rendered_text`` + a trailing newline to stdout on
    success (exit 0). Since we want the report body captured rather than
    printed, we call the helper's building blocks directly instead of
    shelling out — this is the "in-process import preferred" path named in
    the WP prompt, and it avoids a second process + subprocess-argv
    round-trip for something that is a pure function of the same inputs.

    Any exception (including a helper-raised ``VikunjaError``) is treated
    as a helper failure — this driver never fabricates or delivers a
    partial report.
    """
    try:
        from scripts.common.vikunja_client import VikunjaClient, VikunjaError

        try:
            (
                window_start,
                window_end,
                prior_window_start,
                prior_window_end,
            ) = weekly_helper._resolve_windows(
                weekly_helper._parse_args(["--output", "text"])
            )
        except SystemExit:
            return HelperResult(ok=False, error="helper argument parsing failed")

        client = VikunjaClient()
        events = weekly_helper.query_completion_events(
            client,
            window_start=window_start,
            window_end=window_end,
            prior_window_start=prior_window_start,
            prior_window_end=prior_window_end,
        )
        report = weekly_helper.build_report(
            events,
            window_start=window_start,
            window_end=window_end,
            prior_window_start=prior_window_start,
            prior_window_end=prior_window_end,
        )
        return HelperResult(ok=True, report_body=report["rendered_text"])
    except VikunjaError as exc:  # noqa: F821 - imported above; keep local scope
        return HelperResult(
            ok=False, error=f"{type(exc).__name__}: {getattr(exc, 'path', '<unknown>')}"
        )
    except Exception as exc:  # noqa: BLE001 - surface as a helper failure, never raise
        return HelperResult(ok=False, error=f"internal error: {exc}")


def send_message(
    message: str,
    dry_run: bool,
    *,
    target: str = DEFAULT_TARGET,
    timeout: int = 60,
) -> SendResult:
    """Deliver ``message`` via ``openclaw message send --json`` (production effect).

    Uses the absolute ``/usr/bin/openclaw`` (systemd units have no ``PATH``).
    ``dry_run`` appends ``--dry-run`` so ``--self-test`` never sends a real
    message while still exercising the full CLI round-trip.
    """
    cmd = [
        OPENCLAW_BIN,
        "message",
        "send",
        "--channel",
        "whatsapp",
        "--target",
        target,
        "--message",
        message,
        "--json",
    ]
    if dry_run:
        cmd.append("--dry-run")
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return SendResult(
            exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr
        )
    except subprocess.TimeoutExpired as exc:
        # ``text=True`` guarantees str output on a normal return, but the
        # TimeoutExpired exception is typed against the untyped overload
        # (bytes | str | None) — normalize defensively.
        timeout_stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        timeout_stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return SendResult(
            exit_code=124,
            stdout=timeout_stdout,
            stderr=f"{timeout_stderr}\ntimed out after {timeout}s",
        )
    except OSError as exc:
        return SendResult(exit_code=127, stderr=str(exc))


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Pure logic.
# --------------------------------------------------------------------------- #
def compose_message(report_body: str, *, attribution: str = ATTRIBUTION_LINE) -> str:
    """Compose the outbound message: attribution + blank line + report body.

    The report portion is passed through untouched (FR-005 — byte-identical
    to the helper's rendered output).
    """
    return f"{attribution}\n\n{report_body}"


def confirm_delivery(send_result: SendResult) -> tuple[bool, str]:
    """Apply the C1 delivery-confirmation predicate.

    Confirmed IFF: ``exit_code == 0`` AND the parsed JSON has a non-empty
    ``messageId`` (top-level, or nested at ``payload.result.messageId``)
    AND ``dryRun == False`` (top-level, or nested at ``payload.result.dryRun``,
    defaulting to ``False`` when absent so a real send with no ``dryRun``
    key at all is not incorrectly rejected).

    Returns ``(confirmed, failure_reason)`` — ``failure_reason`` is empty
    when confirmed.
    """
    if send_result.exit_code != 0:
        return False, (
            f"openclaw message send exited {send_result.exit_code}: "
            f"{(send_result.stderr or send_result.stdout).strip()[:200]}"
        )

    try:
        payload = json.loads(send_result.stdout)
    except (ValueError, TypeError) as exc:
        return False, f"openclaw message send output not JSON: {exc}"

    if not isinstance(payload, dict):
        return False, "openclaw message send JSON was not an object"

    # The verified live shape nests the result under payload["payload"]["result"]
    # (C1); some call sites may also surface it directly under payload["result"].
    # Accept either so the predicate is robust to both.
    inner = payload.get("payload")
    result = (inner.get("result") if isinstance(inner, dict) else None) or payload.get(
        "result"
    )
    nested = result if isinstance(result, dict) else {}

    message_id = payload.get("messageId") or nested.get("messageId")
    dry_run_flag = payload.get("dryRun", nested.get("dryRun", False))

    if not isinstance(message_id, str) or not message_id:
        return False, "openclaw message send response missing messageId"
    if dry_run_flag:
        return False, "openclaw message send response has dryRun=true"

    return True, ""


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_tick(
    tick_path: Path,
    *,
    now: datetime,
    exit_code: int,
    status: str,
    delivery_confirmed: bool,
    failure_reason: Optional[str],
) -> None:
    """Atomically write ``last-tick.json`` (temp file + ``os.replace``).

    Mirrors the pattern in ``scripts/canary/run.py``'s
    ``_write_tick_signal`` / ``scripts/openclaw/observation/tick.py``'s
    ``_atomic_write_json``: write a tempfile in the SAME directory (so the
    rename is POSIX-atomic), fsync, then replace.
    """
    payload = {
        "completed_at_utc": _iso_z(now),
        "exit_code": exit_code,
        "status": status,
        "delivery_confirmed": delivery_confirmed,
        "failure_reason": failure_reason,
    }
    tick_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(tick_path.parent), prefix=f".{tick_path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, sort_keys=True, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, tick_path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# --------------------------------------------------------------------------- #
# Orchestration.
# --------------------------------------------------------------------------- #
def run(
    *,
    mode: str = "run",
    run_helper: Optional[RunHelper] = None,
    send: Optional[SendMessage] = None,
    now: NowFn = _default_now,
    tick_path: Optional[Path] = None,
    attribution: str = ATTRIBUTION_LINE,
) -> int:
    """Execute one driver pass. Returns the process exit code.

    ``mode`` is one of ``"run"`` (default: real send + production tick),
    ``"self-test"`` (dry-run send + a tick written to the SEPARATE
    :data:`SELF_TEST_TICK_PATH` — the deploy gate), or ``"dry-run"``
    (preview only: no send, no state written).

    ``tick_path`` defaults to :data:`DEFAULT_TICK_PATH` for ``mode="run"``
    and to :data:`SELF_TEST_TICK_PATH` for ``mode="self-test"`` — resolved
    at call time so a caller that does not pass ``tick_path`` explicitly
    never has a self-test write to the production freshness tick (the
    freshness canary reads ``status`` there, not ``delivery_confirmed``, so
    a dry-run tick in that path would report the producer falsely healthy;
    post-merge Codex review, #723). ``tick_path`` remains overridable so
    tests can inject an isolated path for either mode.

    ``run_helper``/``send`` default to the module-level
    :func:`run_report_helper` / :func:`send_message` production effects,
    resolved at call time (not bound as argument defaults) so tests and
    callers can monkeypatch the module attributes directly.
    """
    if run_helper is None:
        run_helper = run_report_helper
    if send is None:
        send = send_message

    if mode not in ("run", "self-test", "dry-run"):
        raise ValueError(f"unknown mode: {mode!r}")

    if tick_path is None:
        tick_path = SELF_TEST_TICK_PATH if mode == "self-test" else DEFAULT_TICK_PATH

    helper_result = run_helper()
    if not helper_result.ok:
        if mode != "dry-run":
            write_tick(
                tick_path,
                now=now(),
                exit_code=1,
                status="failure",
                delivery_confirmed=False,
                failure_reason=f"report helper failed: {helper_result.error}",
            )
        print(f"weekly-report-driver: helper failed: {helper_result.error}", file=sys.stderr)
        return 1

    message = compose_message(helper_result.report_body, attribution=attribution)

    if mode == "dry-run":
        # Local preview only: no send, no state written.
        sys.stdout.write(message)
        sys.stdout.write("\n")
        return 0

    dry_run_send = mode == "self-test"
    send_result = send(message, dry_run_send)
    delivery_confirmed, failure_reason = confirm_delivery(send_result)

    # In self-test mode a "confirmed" dry-run send is impossible by design
    # (the C1 predicate requires dryRun == False) — self-test success means
    # the send path was *reached* and returned exit 0, not that delivery
    # was confirmed. We still write delivery_confirmed truthfully (False)
    # so the tick never lies, but self-test's own exit code reflects
    # whether the round-trip itself succeeded rather than the (impossible)
    # delivery-confirmation predicate.
    if mode == "self-test":
        if send_result.exit_code != 0:
            write_tick(
                tick_path,
                now=now(),
                exit_code=1,
                status="failure",
                delivery_confirmed=False,
                failure_reason=(
                    f"self-test send path failed: {failure_reason or send_result.stderr}"
                ),
            )
            print(
                f"weekly-report-driver: self-test send path failed: {failure_reason}",
                file=sys.stderr,
            )
            return 1
        write_tick(
            tick_path,
            now=now(),
            exit_code=0,
            status="success",
            delivery_confirmed=False,
            failure_reason=None,
        )
        print("weekly-report-driver: self-test OK (dry-run send reached, tick written)")
        return 0

    # Real scheduled run.
    if not delivery_confirmed:
        write_tick(
            tick_path,
            now=now(),
            exit_code=1,
            status="failure",
            delivery_confirmed=False,
            failure_reason=failure_reason,
        )
        print(
            f"weekly-report-driver: delivery not confirmed: {failure_reason}",
            file=sys.stderr,
        )
        return 1

    write_tick(
        tick_path,
        now=now(),
        exit_code=0,
        status="success",
        delivery_confirmed=True,
        failure_reason=None,
    )
    print("weekly-report-driver: delivered and confirmed")
    return 0


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #
def _parse_args(argv: Optional[list[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Deterministic weekly-report driver: runs the report helper, "
            "delivers via openclaw message send, confirms delivery "
            "truthfully, and writes a freshness tick."
        )
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--self-test",
        action="store_true",
        help=(
            "Deploy gate: run the full path with a dry-run send (no real "
            "message) and write a fresh tick."
        ),
    )
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Local preview only: print the composed message; no send, no state written.",
    )
    parser.add_argument(
        "--tick-path",
        type=Path,
        default=None,
        help=(
            "Override the tick path (for tests/manual runs). Defaults to "
            "DEFAULT_TICK_PATH for a real run and to SELF_TEST_TICK_PATH "
            "for --self-test — never pass this to point --self-test at the "
            "production last-tick.json."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    if args.self_test:
        mode = "self-test"
    elif args.dry_run:
        mode = "dry-run"
    else:
        mode = "run"
    return run(mode=mode, tick_path=args.tick_path)


if __name__ == "__main__":  # pragma: no cover - module entry
    sys.exit(main())

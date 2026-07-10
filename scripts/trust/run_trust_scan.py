"""Trust-scan entrypoint — the single systemd/CLI target (WP04, contract C2).

Drives both sub-scans (cron-drift via WP02, completion-assertion verification
via WP03), applies the seen-findings alert cadence (:mod:`scripts.trust.state`),
and emits alerts via the shared ``#701`` bus
(:mod:`scripts.trust.alert_render`). No other module runs the timer loop.

::

    python3 -m scripts.trust.run_trust_scan [--dry-run] [--once | --preflight] [--json]

**Exit-code discipline** (data-model.md "Fail-safe & exit-code discipline",
contract C2) — two run modes:

- **Timer mode** (default, systemd target): **always exits 0**. A fault in
  either sub-scan is caught, recorded in ``errors[]``, and reported via
  ``ok:false`` in the JSON summary — never surfaced as a process exit code,
  so systemd never marks the unit ``failed`` or enters a restart loop.
- **Preflight mode** (``--once`` / ``--preflight``): **may exit 2** when the
  scan itself could not run at all (e.g., the baseline is unreadable) — a
  hard signal for an operator or the deploy self-test.
- **Finding drift is NEVER a non-zero exit** in either mode — drift is
  expected signal, not a failure.

**Fail-safe isolation** (NFR-001): each sub-scan is wrapped independently so
an exception in one (e.g. the OpenClaw CLI hiccups) is caught into
``errors[]`` and does **not** abort the other sub-scan. The overall tick
never raises.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.trust import alert_render, state as state_mod
from scripts.trust.assertion_verifier import (
    AssertionFinding,
    verify_assertion,
)
from scripts.trust.completion_assertion import assertions_dir
from scripts.trust.cron_baseline import BaselineError, baseline_hash, load_baseline
from scripts.trust.cron_drift_detector import (
    CronDriftFinding,
    CronEnumerationError,
    detect_cron_drift,
    enumerate_live_crons,
)

__all__ = ["main", "run_scan"]

# Watermark file: tracks the last-verified byte offset per assertion JSONL
# file so each assertion is verified once. Lives alongside the seen-findings
# state directory (module constant; injectable for tests).
DEFAULT_WATERMARK_PATH = Path("/data/services/trust/state/assertion-watermark.json")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _load_watermark(path: Path) -> dict[str, int]:
    """Load the per-file byte-offset watermark; fail-safe (missing/corrupt -> {})."""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError:
        return {}
    try:
        document = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(document, dict):
        return {}
    return {
        str(key): int(value)
        for key, value in document.items()
        if isinstance(value, (int, float))
    }


def _save_watermark(watermark: dict[str, int], path: Path) -> None:
    """Atomically persist the watermark (temp file + os.replace)."""
    import os
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(watermark, fh, sort_keys=True, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _iter_new_assertions(
    base_dir: Path, watermark: dict[str, int]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Read every assertion appended since the last recorded watermark.

    Uses WP03's :func:`~scripts.trust.assertion_verifier.read_assertions` per
    date-partitioned file, but tracks a byte offset per file (rather than
    re-reading from the start every tick) so each assertion is verified
    exactly once. Returns ``(new_records, updated_watermark)`` — the caller
    decides whether to persist ``updated_watermark`` (skipped on
    ``--dry-run``).
    """
    new_records: list[dict[str, Any]] = []
    updated_watermark = dict(watermark)

    if not base_dir.exists():
        return new_records, updated_watermark

    for file_path in sorted(base_dir.glob("*.jsonl")):
        key = str(file_path)
        try:
            size = file_path.stat().st_size
        except OSError:
            continue
        offset = updated_watermark.get(key, 0)
        if offset >= size:
            # Nothing new in this file since last tick.
            updated_watermark[key] = size
            continue
        # Re-read the whole file via the WP03 reader (tolerant of
        # blank/corrupt trailing lines) and only keep records past the
        # byte offset we've already processed. This trades a bit of
        # redundant parsing for reuse of the WP03 reader rather than
        # re-implementing line-tracking here.
        try:
            with file_path.open("r", encoding="utf-8") as fh:
                fh.seek(offset)
                for line in fh:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        new_records.append(json.loads(stripped))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            continue
        updated_watermark[key] = size

    return new_records, updated_watermark


def run_scan(
    *,
    dry_run: bool = False,
    now: datetime | None = None,
    baseline_path: Path | str | None = None,
    state_path: Path | str = state_mod.DEFAULT_STATE_PATH,
    watermark_path: Path | str = DEFAULT_WATERMARK_PATH,
    assertions_base_dir: Path | None = None,
) -> dict[str, Any]:
    """Run one scan tick: both sub-scans, cadence reconciliation, and emission.

    Returns the summary dict (``ok``, ``drift_findings``, ``assertion_findings``,
    ``alerts_emitted``, ``errors``). Never raises — every sub-scan and the
    state I/O are individually guarded (NFR-001). ``dry_run`` computes and
    returns findings but performs **no emission** and **no state/watermark
    mutation**.
    """
    tick_now = now if now is not None else _utc_now()
    errors: list[str] = []
    scan_inability = False  # True only when a sub-scan could not run at all.

    # ---- Cron-drift sub-scan (WP02) -----------------------------------
    cron_findings: list[CronDriftFinding] = []
    current_baseline_hash = ""
    try:
        baseline = load_baseline(baseline_path) if baseline_path is not None else load_baseline()
        current_baseline_hash = baseline_hash(baseline)
        live_jobs = enumerate_live_crons()
        cron_findings = detect_cron_drift(live_jobs, baseline)
    except BaselineError as exc:
        errors.append(f"cron_scan:BaselineError:{exc}")
        scan_inability = True
    except CronEnumerationError as exc:
        errors.append(f"cron_scan:CronEnumerationError:{exc}")
        scan_inability = True
    except Exception as exc:  # noqa: BLE001 - fail-safe isolation (NFR-001)
        errors.append(f"cron_scan:{exc.__class__.__name__}:{exc}")
        scan_inability = True

    # ---- Assertion sub-scan (WP03) -------------------------------------
    assertion_findings: list[AssertionFinding] = []
    watermark: dict[str, int] = {}
    new_watermark: dict[str, int] = {}
    try:
        base_dir = assertions_base_dir if assertions_base_dir is not None else assertions_dir()
        watermark = _load_watermark(Path(watermark_path))
        new_records, new_watermark = _iter_new_assertions(base_dir, watermark)
        for record in new_records:
            assertion_findings.extend(verify_assertion(record))
    except Exception as exc:  # noqa: BLE001 - fail-safe isolation (NFR-001)
        errors.append(f"assertion_scan:{exc.__class__.__name__}:{exc}")
        # An assertion-scan fault does NOT count as scan_inability on its
        # own for the "drift is never non-zero" contract — but it does
        # mean the assertion side found nothing this tick.

    # ---- Seen-findings cadence reconciliation --------------------------
    alerts_emitted = 0
    if not dry_run:
        try:
            current_state = state_mod.load_state(state_path)
            findings_with_hash: list[tuple[Any, str]] = [
                (finding, current_baseline_hash) for finding in cron_findings
            ] + [(finding, current_baseline_hash) for finding in assertion_findings]
            to_alert, resolved_events, new_state = state_mod.reconcile(
                findings_with_hash, tick_now, current_state
            )

            for finding in to_alert:
                result = alert_render.emit_finding(finding)
                if result.ok:
                    alerts_emitted += 1

            for event in resolved_events:
                alert = alert_render.render_drift_resolved(
                    event.name, event.first_seen, event.cleared_at
                )
                result = alert_render.emit_finding(alert)
                if result.ok:
                    alerts_emitted += 1

            state_mod.save_state(new_state, state_path)
            _save_watermark(new_watermark, Path(watermark_path))
        except Exception as exc:  # noqa: BLE001 - fail-safe: state I/O must not crash the tick
            errors.append(f"state_reconcile:{exc.__class__.__name__}:{exc}")
    else:
        # --dry-run: compute findings only; no emit, no state/watermark
        # mutation. Report the raw finding counts (pre-cadence) so the
        # operator sees everything the scan would consider.
        pass

    ok = not errors
    summary = {
        "ok": ok,
        "drift_findings": len(cron_findings),
        "assertion_findings": len(assertion_findings),
        "alerts_emitted": alerts_emitted,
        "errors": errors,
    }
    # Internal-only signal consumed by main() to select the preflight exit
    # code; not part of the public JSON contract (kept out of `summary`).
    summary["_scan_inability"] = scan_inability
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts.trust.run_trust_scan",
        description=(
            "Run one trust-scan tick: cron-drift detection (WP02) + "
            "completion-assertion verification (WP03), alerting via the "
            "#701 bus."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="compute and print findings; no emit, no state/watermark mutation",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--once",
        action="store_true",
        help="preflight/explicit mode: may exit 2 on scan-inability",
    )
    mode_group.add_argument(
        "--preflight",
        action="store_true",
        help="alias for --once (preflight/explicit mode)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the machine-readable summary to stdout",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint. Returns the exit code per the two-mode contract (C2).

    ``if __name__ == '__main__': sys.exit(main())`` at module scope.
    """
    args = _build_parser().parse_args(argv)
    preflight_mode = bool(args.once or args.preflight)

    summary = run_scan(dry_run=args.dry_run)
    scan_inability = summary.pop("_scan_inability", False)

    if args.json:
        print(json.dumps(summary, sort_keys=True))

    if preflight_mode and scan_inability:
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry
    sys.exit(main())

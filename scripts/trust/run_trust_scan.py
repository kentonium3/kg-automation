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
    verify_assertion_detailed,
    verify_vikunja_id_present,
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

# Per-tick freshness signal (#721). A flat JSON pointer the canary reads for
# staleness. The seen-findings state map is a bare fingerprint map with no
# timestamp key (shape-unevaluable to the freshness probe), so this dedicated
# last-tick.json is the canary's freshness anchor. ``completed_at_utc`` is a
# canary-recognized timestamp key; ``exit_status`` is a closed enum the probe
# reads (``failure`` on a hard scan-inability → the probe flags it). See
# scripts/canary/probes.py and the felix-deployer precedent (#720).
DEFAULT_LAST_TICK_PATH = Path("/data/services/trust/state/last-tick.json")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _write_last_tick(
    path: Path, *, now: datetime, scan_inability: bool, error_count: int
) -> None:
    """Atomically write the per-tick freshness signal the canary reads (#721).

    ``exit_status`` is ``failure`` only on a hard **scan-inability** (e.g. the
    cron baseline is unreadable — a sub-scan could not run at all); transient
    finding-side faults (an indeterminate Vikunja re-verify) leave it
    ``success`` so the canary is not paged on recoverable hiccups. ``error_count``
    is informational and deliberately NOT named ``errors``/``error`` so it never
    trips the probe's explicit-error detection. Best-effort: a write failure must
    not crash the tick (fail-safe, NFR-001).
    """
    import os
    import tempfile

    payload = {
        "completed_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "exit_status": "failure" if scan_inability else "success",
        "scan_inability": scan_inability,
        "error_count": error_count,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
        )
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, sort_keys=True, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except OSError:
        # Freshness-signal loss is preferable to crashing the scan tick.
        pass


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

    Thin wrapper over :func:`_iter_new_assertions_positioned` that discards the
    per-record byte position, preserved for callers/tests that only need the
    record list + a fully-advanced watermark.
    """
    positioned, updated_watermark = _iter_new_assertions_positioned(base_dir, watermark)
    return [record for _key, _end_offset, record in positioned], updated_watermark


def _iter_new_assertions_positioned(
    base_dir: Path, watermark: dict[str, int]
) -> tuple[list[tuple[str, int, dict[str, Any]]], dict[str, int]]:
    """Read new assertions, each tagged with its file key + end byte offset.

    Returns ``(positioned_records, fully_advanced_watermark)`` where each
    positioned record is ``(file_key, end_offset, record)`` — ``end_offset``
    is the byte position in the file *after* that record's line, so the caller
    can advance the watermark only as far as the last **conclusively-verified**
    record per file (Codex F1: a record whose artifact could not be
    conclusively checked, e.g. during a Vikunja outage, must be re-read next
    scan rather than silently consumed).

    ``fully_advanced_watermark`` is the watermark advanced to each file's full
    size — the value to persist only when every record in the file was
    conclusively verified.
    """
    positioned: list[tuple[str, int, dict[str, Any]]] = []
    updated_watermark = dict(watermark)

    if not base_dir.exists():
        return positioned, updated_watermark

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
        # Re-read from the byte offset we've already processed, tracking the
        # end-of-line byte position of each record so the caller can hold the
        # watermark at the boundary of the last conclusively-verified record.
        try:
            with file_path.open("rb") as fh:
                fh.seek(offset)
                # Binary mode + explicit readline() so fh.tell() returns a true
                # BYTE offset after each line — this must stay byte-comparable
                # with st_size (used in the `offset >= size` short-circuit) and
                # feed back into seek() on later ticks. A text-mode iterator's
                # tell() is an opaque, non-byte cookie and raises inside a
                # `for line in fh` loop.
                while True:
                    raw = fh.readline()
                    if not raw:
                        break
                    end_offset = fh.tell()
                    try:
                        line = raw.decode("utf-8")
                    except UnicodeDecodeError:
                        continue
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        record = json.loads(stripped)
                    except json.JSONDecodeError:
                        continue
                    positioned.append((key, end_offset, record))
        except OSError:
            continue
        updated_watermark[key] = size

    return positioned, updated_watermark


def run_scan(
    *,
    dry_run: bool = False,
    now: datetime | None = None,
    baseline_path: Path | str | None = None,
    state_path: Path | str = state_mod.DEFAULT_STATE_PATH,
    watermark_path: Path | str = DEFAULT_WATERMARK_PATH,
    assertions_base_dir: Path | None = None,
    last_tick_path: Path | str = DEFAULT_LAST_TICK_PATH,
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

    # ---- Seen-findings state (loaded up front) -------------------------
    # Loaded before the assertion sub-scan so the F2 re-verify of outstanding
    # artifact_missing assertions can consult it. Fail-safe: a state-load
    # fault degrades to empty state (spurious re-alert at worst, never a crash).
    current_state: dict[str, dict[str, str]] = {}
    try:
        current_state = state_mod.load_state(state_path)
    except Exception as exc:  # noqa: BLE001 - fail-safe: state load must not crash the tick
        errors.append(f"state_load:{exc.__class__.__name__}:{exc}")

    # ---- Assertion sub-scan (WP03) -------------------------------------
    # Two sources feed the assertion findings this tick:
    #   (a) NEW assertions read once past the byte-offset watermark — but the
    #       watermark only advances past records that were CONCLUSIVELY verified
    #       (present or missing). A record with any indeterminate id (transient
    #       Vikunja fault) holds the watermark so it is re-read next scan (F1).
    #   (b) OUTSTANDING artifact_missing assertions already in seen-state —
    #       re-verified against Vikunja every scan, independent of the watermark,
    #       so a still-missing artifact keeps producing its finding (persisting
    #       the 24h re-alert) and only clears when the artifact reappears (F2).
    assertion_findings: list[AssertionFinding] = []
    watermark: dict[str, int] = {}
    committed_watermark: dict[str, int] = {}
    try:
        base_dir = assertions_base_dir if assertions_base_dir is not None else assertions_dir()
        watermark = _load_watermark(Path(watermark_path))
        positioned, fully_advanced = _iter_new_assertions_positioned(base_dir, watermark)

        # Advance the watermark per-file only up to the last conclusively-
        # verified record; start from the loaded watermark and push each file's
        # offset forward as records verify conclusively (F1).
        committed_watermark = dict(watermark)
        indeterminate_files: set[str] = set()
        for key, end_offset, record in positioned:
            result = verify_assertion_detailed(record)
            assertion_findings.extend(result.findings)
            if result.indeterminate:
                # Hold this file's watermark here: do not advance past the
                # first indeterminate record so it (and everything after it in
                # this file) is re-read next scan.
                indeterminate_files.add(key)
                errors.append(
                    f"assertion_scan:indeterminate:{record.get('artifact_kind', '')}:"
                    f"{','.join(str(i) for i in (record.get('artifact_ids') or []))}"
                )
                continue
            if key not in indeterminate_files:
                committed_watermark[key] = end_offset
        # Files with no held record advance fully (covers empty/skipped files
        # and files whose every record verified conclusively).
        for key, size in fully_advanced.items():
            if key not in indeterminate_files:
                committed_watermark[key] = size

        # (b) Re-verify outstanding artifact_missing assertions from state.
        # A still-missing one re-emits its finding (persists 24h cadence); a
        # reappeared one is simply absent from current_findings this tick, so
        # reconcile resolves it as an ASSERTION resolution.
        for outstanding in state_mod.outstanding_assertion_findings(current_state):
            present = verify_vikunja_id_present(outstanding.artifact_id)
            if present is False:
                assertion_findings.append(outstanding)
            elif present is None:
                # Transient fault re-verifying an outstanding finding: keep it
                # present in current_findings so it does NOT false-resolve, and
                # record the fault. (Deterministic: no LLM.)
                assertion_findings.append(outstanding)
                errors.append(
                    f"assertion_reverify:indeterminate:vikunja_task:{outstanding.artifact_id}"
                )
            # present is True -> omit from current_findings -> reconcile resolves it.
    except Exception as exc:  # noqa: BLE001 - fail-safe isolation (NFR-001)
        errors.append(f"assertion_scan:{exc.__class__.__name__}:{exc}")
        # An assertion-scan fault does NOT count as scan_inability on its
        # own for the "drift is never non-zero" contract — but it does
        # mean the assertion side found nothing this tick. Hold the watermark
        # at its loaded value so nothing is silently consumed.
        committed_watermark = watermark

    # ---- Seen-findings cadence reconciliation --------------------------
    alerts_emitted = 0
    if not dry_run:
        try:
            findings_with_hash: list[tuple[Any, str]] = [
                (finding, current_baseline_hash) for finding in cron_findings
            ] + [(finding, current_baseline_hash) for finding in assertion_findings]
            to_alert, resolved_events, new_state = state_mod.reconcile(
                findings_with_hash, tick_now, current_state
            )

            # Emit-gate last_alerted (F3): only a SUCCESSFUL emit counts as
            # "alerted". A failed emit (bus ok=False) must leave the finding DUE
            # next scan, not suppressed until the 24h cadence — so revert its
            # last_alerted via state.keep_due.
            for finding in to_alert:
                result = alert_render.emit_finding(finding)
                if result.ok:
                    alerts_emitted += 1
                else:
                    fingerprint = state_mod.fingerprint_finding(
                        finding, current_baseline_hash
                    )
                    state_mod.keep_due(new_state, fingerprint, current_state)

            for event in resolved_events:
                alert = alert_render.render_drift_resolved(
                    event.name, event.first_seen, event.cleared_at, source=event.source
                )
                result = alert_render.emit_finding(alert)
                if result.ok:
                    alerts_emitted += 1

            state_mod.save_state(new_state, state_path)
            _save_watermark(committed_watermark, Path(watermark_path))
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

    # Per-tick freshness signal for the canary (#721). Written only on a real
    # (non-dry-run) tick — a --dry-run must not mutate state — after all sub-scan
    # work, so completed_at_utc reflects tick completion. Independent of state/
    # watermark save success (its own guard); a stalled timer goes stale here.
    if not dry_run:
        _write_last_tick(
            Path(last_tick_path),
            now=tick_now,
            scan_inability=scan_inability,
            error_count=len(errors),
        )

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

"""Canary runner — the single systemd/CLI entrypoint (WP04, contract §5).

Iterates the canary targets derived from ``service-inventory.json``, evaluates
each (``health.evaluate``), routes emitting outcomes through the dedup layer
(``dedup.decide``), emits via the shared ``#701`` alert bus, and writes two
durable artifacts every tick:

* the per-component JSONL **ledger** (``DEFAULT_LEDGER_DIR/<date>.jsonl``, F8) —
  one line per component per tick recording **every** outcome incl.
  healthy/suppressed/gap/deduped (FR-008), and
* the aggregate **tick-signal** (``DEFAULT_TICK_PATH``, FR-010) — the runner's own
  health pointer (WP05 registers it with a ``tick-signal-file`` health_check whose
  ``completed_at_utc`` is the freshness anchor).

::

    python3 -m scripts.canary.run [--once] [--dry-run] [--self-check]

**Fail-open (NFR-004 / INV-D):** the per-component body is wrapped — a probe that
raises records an ``unknown`` ledger line + an ``errors[]`` entry and the pass
**continues** to the next component. A ledger-write fault is likewise best-effort.
One component's fault never aborts the pass.

**Exit-code discipline (contract §5):** a completed pass exits **0** even when
components are unhealthy (unhealthy → emits, not a process failure). A non-zero
exit is reserved for a **runner-level** failure (inventory unreadable, state dir
unwritable) — that non-zero is what WP06's ``OnFailure=`` catches.

Modeled on ``scripts/trust/run_trust_scan.py`` + ``scripts/trust/state.py``
(atomic writes, injected ``now``, exit-code discipline, fail-safe I/O).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from scripts.canary import dedup as dedup_mod
from scripts.canary.health import HealthResult, evaluate
from scripts.canary.registry import (
    DEFAULT_INVENTORY_PATH,
    load_inventory,
    load_targets,
)
from scripts.common.alert_bus import Alert, Severity, emit

__all__ = ["main", "run_pass"]

# State-path constants (module-level, injectable via run_pass parameters).
DEFAULT_DEDUP_PATH = dedup_mod.DEFAULT_DEDUP_PATH
DEFAULT_TICK_PATH = Path("/data/services/felix-canary/state/last-tick.json")
DEFAULT_LEDGER_DIR = Path("/data/services/felix-canary/ledger")

# Severity map (R6): failed/stale → ERROR; degraded/gap/persistent-unknown → WARN;
# recovery → INFO. Applied when an outcome actually emits.
_SEVERITY_BY_OUTCOME: dict[str, Severity] = {
    "failed": Severity.ERROR,
    "stale": Severity.ERROR,
    "degraded": Severity.WARN,
    "unknown": Severity.WARN,
    "gap": Severity.WARN,
}

# EmitFn / EvaluateFn signatures (documentation only; injected for tests).
EmitFn = Callable[[Alert], Any]
EvaluateFn = Callable[..., HealthResult]


# --------------------------------------------------------------------------- #
# Time.
# --------------------------------------------------------------------------- #
def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Default real effects (the runner's wiring layer).
#
# The evaluation modules (health/probes) are pure w.r.t. injected effects; the
# runner supplies the real network/subprocess/filesystem callables here. All are
# defensive: they never raise out of the runner path — a fault surfaces as a
# probe "unknown" (matching the health.evaluate fail-safe contract).
# --------------------------------------------------------------------------- #
def _default_http_get(endpoint: str, timeout: float | None = None) -> int:
    """HTTP GET *endpoint*, returning the response status code."""
    req = urllib.request.Request(endpoint, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return int(resp.status)


def _default_run_cmd(
    endpoint: str, timeout: float | None = None
) -> tuple[int, str, str]:
    """Run *endpoint* as a shell command, returning ``(exit_code, stdout, stderr)``."""
    proc = subprocess.run(  # noqa: S602
        endpoint,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _default_read_state(path: str) -> dict[str, Any]:
    """Read and JSON-parse the pointer at *path* (freshness probes)."""
    with Path(path).open(encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------- #
# Ledger + tick-signal I/O.
# --------------------------------------------------------------------------- #
def _ledger_path(ledger_dir: Path, now: datetime) -> Path:
    return ledger_dir / f"{now.astimezone(timezone.utc):%Y-%m-%d}.jsonl"


def _append_ledger_line(ledger_dir: Path, record: dict[str, Any], now: datetime) -> None:
    """Append one JSON line to the date-partitioned ledger (best-effort).

    Raises on I/O failure; the caller catches it into ``errors[]`` so a ledger
    problem never aborts the pass (INV-D).
    """
    ledger_dir.mkdir(parents=True, exist_ok=True)
    path = _ledger_path(ledger_dir, now)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def _write_tick_signal(tick_path: Path, signal: dict[str, Any]) -> None:
    """Atomically write the aggregate tick-signal (temp file + os.replace)."""
    tick_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(tick_path.parent), prefix=f".{tick_path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(signal, fh, sort_keys=True, indent=2)
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
# Emission.
# --------------------------------------------------------------------------- #
def _build_alert(
    component_id: str,
    outcome: str,
    evidence: str,
    *,
    is_recovery: bool,
) -> Alert:
    """Construct the real ``Alert`` for an emitting outcome (contract §4 / F3).

    Recovery (a transition back to ``healthy``) renders as INFO "recovered";
    everything else maps by :data:`_SEVERITY_BY_OUTCOME`.
    """
    if is_recovery:
        severity = Severity.INFO
        title = f"{component_id} health: recovered"
        description = f"{component_id} recovered to healthy — {evidence}"
    else:
        severity = _SEVERITY_BY_OUTCOME.get(outcome, Severity.WARN)
        title = f"{component_id} health: {outcome}"
        description = f"{evidence}"
    return Alert(
        source=f"felix-canary:{component_id}",
        severity=severity,
        title=title,
        description=description,
        action=None,
        details={
            "component_id": component_id,
            "outcome": outcome,
            "evidence": evidence,
        },
    )


# --------------------------------------------------------------------------- #
# The pass.
# --------------------------------------------------------------------------- #
def run_pass(
    *,
    now: datetime,
    inventory: dict | None = None,
    inventory_path: Path | str = DEFAULT_INVENTORY_PATH,
    dedup_path: Path | str = DEFAULT_DEDUP_PATH,
    tick_path: Path | str = DEFAULT_TICK_PATH,
    ledger_dir: Path | str = DEFAULT_LEDGER_DIR,
    emit_fn: EmitFn = emit,
    evaluate_fn: EvaluateFn = evaluate,
    http_get: Callable[..., int] = _default_http_get,
    run_cmd: Callable[..., tuple[int, str, str]] = _default_run_cmd,
    read_state: Callable[[str], dict[str, Any]] = _default_read_state,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run one full canary pass; return the aggregate summary dict.

    Loads targets + coverage gaps (registry) and the dedup state, evaluates each
    target (fail-open), routes emitting outcomes through :func:`dedup.decide`,
    emits via ``emit_fn``, and (unless ``dry_run``) persists the dedup state, the
    per-component ledger, and the aggregate tick-signal.

    ``now`` is injected (never :func:`datetime.now` inside the logic). ``emit_fn``,
    ``evaluate_fn`` and the three effect callables are injected so offline tests
    never touch ntfy, the network, subprocess, or ``/data``.

    ``dry_run`` computes + returns everything but writes **nothing** and emits
    **nothing** (no dedup/tick/ledger writes).

    Raises only on a **runner-level** fault the caller must surface as a non-zero
    exit (inventory unreadable; state dir unwritable when persisting). A
    per-component probe fault is caught into ``errors[]`` and never aborts the
    pass (INV-D).
    """
    started = time.monotonic()
    errors: list[str] = []
    # Per-component one-line summaries, in evaluation order. Populated for every
    # component (incl. suppressed/gap/deduped) so --dry-run can print an offline
    # preview without re-evaluating (which would re-run the real probes).
    component_lines: list[str] = []

    # ---- Load work list (runner-level: an unreadable inventory raises). ---- #
    if inventory is None:
        inventory = load_inventory(Path(inventory_path))
    targets, gaps = load_targets(inventory)

    # A coverage-gap component (method none/missing/unhandled) is represented by
    # its authoritative `gap` signal, NOT by its evaluate outcome — which is an
    # `unknown` for the same reason (no usable probe). Route it once, as a gap,
    # so a single ledger line + a single dedup key represents it (INV-B: exactly
    # one ledger line per service-type entry; no double-page for the same fault).
    gap_ids = {gap.component_id for gap in gaps}

    # ---- Load dedup state (fail-safe: a bad state file degrades to empty). -- #
    state: dict[str, dict[str, str]] = {}
    try:
        state = dedup_mod.load_state(dedup_path)
    except Exception as exc:  # noqa: BLE001 - fail-safe: state load never crashes the pass
        errors.append(f"dedup_load:{exc.__class__.__name__}:{exc}")
        state = {}

    ledger_dir_path = Path(ledger_dir)

    components_evaluated = 0
    emitted = 0
    suppressed_dedup = 0
    suppressed_status = 0

    def _route(
        component_id: str,
        outcome: str,
        evidence: str,
        *,
        emit_on_first_seen: bool = True,
    ) -> None:
        """Dedup → (maybe) emit → ledger one emitting-eligible outcome.

        ``outcome`` is one of the emit-eligible outcomes (stale/failed/degraded/
        unknown/gap) or ``healthy`` (recovery detection). Records exactly one
        ledger line. Mutates the enclosing counters + ``state`` + ``errors``.

        ``emit_on_first_seen`` governs the F5 persistence divergence for
        ``unknown``/``gap``. :func:`dedup.decide` (correctly for failed/stale/
        degraded, and for the F7 ``failed→healthy→failed`` guarantee) treats a
        *first* observation of a bad outcome as a transition and emits it
        immediately. But per spec.md:48 ("a `unknown` that **persists past the
        dedup window** ... is emitted as a warning") + contracts §5 + plan IC-04
        (F5), a first-seen ``unknown``/``gap`` must be **recorded but not paged**;
        it pages only once it has *persisted* past the window (then once per
        window thereafter). The caller passes ``emit_on_first_seen=False`` for
        ``unknown``/``gap`` so a transition INTO unknown/gap is suppressed on the
        first tick while still recording the dedup entry (so persistence is
        tracked). The unchanged-and-window-elapsed re-emit path in
        :func:`dedup.decide` then handles the "pages once persistent" behavior
        unchanged. This divergence is scoped to the *paging timing* for
        first-seen unknown/gap only — the general transition invariant (F7) and
        the immediate emit for failed/stale/degraded are untouched.
        """
        nonlocal emitted, suppressed_dedup
        should_emit, is_recovery, new_entry = dedup_mod.decide(
            component_id, outcome, now, state
        )

        # F5: suppress the FIRST-SEEN emit for unknown/gap. A first observation
        # is a transition (prior last_outcome absent/differs), which decide()
        # flags should_emit=True. We downgrade only that first-seen page to a
        # recorded-not-paged tick; the entry (last_emitted_utc=now) is still
        # stored so the next unchanged tick past the window re-emits (persist).
        prior_entry = state.get(component_id)
        first_seen_transition = (
            prior_entry is None
            or prior_entry.get("last_outcome") != outcome
        )
        if should_emit and not emit_on_first_seen and first_seen_transition:
            should_emit = False

        did_emit = False
        deduped = False
        if should_emit:
            alert = _build_alert(
                component_id, outcome, evidence, is_recovery=is_recovery
            )
            if not dry_run:
                emit_fn(alert)
            did_emit = True
            emitted += 1
        elif outcome != "healthy":
            # A bad outcome not paged this tick: either held inside the dedup
            # window (unchanged-bad) or a first-seen unknown/gap recorded pending
            # persistence. Both count as "suppressed" for the tick-signal.
            deduped = True
            suppressed_dedup += 1

        # Persist the new dedup entry (in-memory; saved once at pass end).
        state[component_id] = new_entry

        _ledger(
            component_id,
            outcome,
            evidence,
            emitted=did_emit,
            suppressed_dedup=deduped,
        )

    def _ledger(
        component_id: str,
        outcome: str,
        evidence: str,
        *,
        emitted: bool,
        suppressed_dedup: bool,
    ) -> None:
        """Best-effort per-component ledger line (F8). Never aborts the pass.

        Also records the human-readable one-liner (for --dry-run preview /
        operator visibility) before the dry_run write-skip, so a dry run still
        reports every component without re-evaluating.
        """
        flags = ""
        if emitted:
            flags = " [emitted]"
        elif suppressed_dedup:
            flags = " [deduped]"
        component_lines.append(f"{component_id}: {outcome}{flags} — {evidence}")

        if dry_run:
            return
        record = {
            "component_id": component_id,
            "outcome": outcome,
            "evidence": evidence,
            "emitted": emitted,
            "suppressed_dedup": suppressed_dedup,
            "evaluated_at": now.isoformat(),
        }
        try:
            _append_ledger_line(ledger_dir_path, record, now)
        except Exception as exc:  # noqa: BLE001 - best-effort ledger (INV-D)
            errors.append(f"ledger:{component_id}:{exc.__class__.__name__}:{exc}")

    # ---- Evaluate every target (fail-open per component, INV-D). ---------- #
    for target in targets:
        if target.component_id in gap_ids:
            # Represented by its gap signal below — do not also evaluate/route
            # it as `unknown` (same underlying "no usable probe" fact).
            continue
        components_evaluated += 1
        try:
            result = evaluate_fn(
                target,
                now,
                http_get=http_get,
                run_cmd=run_cmd,
                read_state=read_state,
            )
        except Exception as exc:  # noqa: BLE001 - fail-open: one fault never aborts the pass
            errors.append(
                f"evaluate:{target.component_id}:{exc.__class__.__name__}:{exc}"
            )
            # Record an unknown ledger line; do NOT route through dedup/emit
            # (an evaluate that blew up has no honest outcome to emit this tick).
            _ledger(
                target.component_id,
                "unknown",
                f"evaluate raised: {exc.__class__.__name__}: {exc}",
                emitted=False,
                suppressed_dedup=False,
            )
            continue

        outcome = result.outcome
        if outcome == "suppressed":
            # Gated (not alert-eligible): never probed, never emits — ledger only.
            suppressed_status += 1
            _ledger(
                result.component_id,
                "suppressed",
                result.evidence,
                emitted=False,
                suppressed_dedup=False,
            )
            continue

        # healthy / stale / failed / degraded / unknown → dedup-routed.
        # (healthy so a transition back to healthy emits the recovery INFO.)
        # F5: unknown pages only once persistent past the window, so it does NOT
        # emit on first sight (emit_on_first_seen=False); failed/stale/degraded
        # page immediately (emit_on_first_seen defaults True).
        _route(
            result.component_id,
            outcome,
            result.evidence,
            emit_on_first_seen=outcome != "unknown",
        )

    # ---- Coverage gaps → WARN through the same dedup path (keyed by id). --- #
    # Each gap is a service-type entry not evaluated above (skipped via gap_ids),
    # so it counts as one evaluated component here — exactly one ledger line +
    # one dedup key per entry (INV-B).
    coverage_gaps = len(gaps)
    for gap in gaps:
        components_evaluated += 1
        # F5: a first-seen gap is recorded but not paged; it pages once it has
        # persisted past the dedup window (emit_on_first_seen=False).
        _route(
            gap.component_id,
            "gap",
            f"coverage gap: {gap.reason}",
            emit_on_first_seen=False,
        )

    # ---- Persist dedup state (runner-level: an unwritable dir raises). ----- #
    if not dry_run:
        try:
            dedup_mod.save_state(state, dedup_path)
        except Exception as exc:  # noqa: BLE001 - degrade, don't crash the whole tick
            errors.append(f"dedup_save:{exc.__class__.__name__}:{exc}")

    duration_ms = int((time.monotonic() - started) * 1000)
    status = "success" if not errors else "error"
    summary = {
        "status": status,
        "completed_at_utc": now.astimezone(timezone.utc).isoformat(),
        "components_evaluated": components_evaluated,
        "emitted": emitted,
        "suppressed_dedup": suppressed_dedup,
        "coverage_gaps": coverage_gaps,
        "suppressed_status": suppressed_status,
        "errors": errors,
        "duration_ms": duration_ms,
        # Per-component one-liners (evaluation order). Not persisted to the
        # tick-signal file (excluded below); used for the --dry-run preview and
        # returned to callers/tests.
        "component_lines": component_lines,
    }

    # ---- Aggregate tick-signal (the runner's own health pointer, FR-010). -- #
    # The persisted tick-signal is the TickSignal schema only (data-model.md);
    # component_lines is a return-value convenience, not part of the signal file.
    if not dry_run:
        tick_signal = {k: v for k, v in summary.items() if k != "component_lines"}
        try:
            _write_tick_signal(Path(tick_path), tick_signal)
        except Exception as exc:  # noqa: BLE001 - a tick-signal write fault is recorded, not fatal
            errors.append(f"tick_signal:{exc.__class__.__name__}:{exc}")
            summary["errors"] = errors
            # Reflect the write failure in the returned status.
            summary["status"] = "error"

    return summary


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #
def _self_check(inventory_path: Path, tick_path: Path) -> tuple[bool, str]:
    """Assert inventory readable + alert_bus importable + state dir writable.

    Returns ``(ok, detail)``. Never raises.
    """
    problems: list[str] = []

    # Inventory readable + parseable.
    try:
        load_inventory(inventory_path)
    except Exception as exc:  # noqa: BLE001
        problems.append(f"inventory_unreadable:{exc.__class__.__name__}")

    # Alert bus importable (already imported at module load; re-assert the names).
    try:
        from scripts.common.alert_bus import Alert as _A  # noqa: F401
        from scripts.common.alert_bus import emit as _E  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        problems.append(f"alert_bus_import:{exc.__class__.__name__}")

    # State dir writable (probe with a temp file we immediately remove).
    state_dir = tick_path.parent
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(state_dir), prefix=".self-check.")
        os.close(fd)
        os.unlink(tmp_name)
    except Exception as exc:  # noqa: BLE001
        problems.append(f"state_dir_unwritable:{exc.__class__.__name__}")

    if problems:
        return False, ";".join(problems)
    return True, "ok"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scripts.canary.run",
        description=(
            "Run one canary pass: evaluate every service-inventory target, "
            "dedup, emit via the #701 bus, and write the tick-signal + ledger."
        ),
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="run one full pass (the deployed timer form)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="evaluate + print a line per component; write nothing, emit nothing",
    )
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="assert inventory readable + alert_bus importable + state dir writable",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint. Returns the process exit code per the §5 contract.

    - ``--self-check``: print ``status=ok``/``status=error``; exit 0/1.
    - ``--dry-run``: run offline, print a health line per target; write nothing;
      exit 0 (unless the inventory itself is unreadable → runner-level fault).
    - ``--once`` (or no flag): one full pass. Exit 0 for a completed pass even
      with unhealthy components; non-zero only on a runner-level failure
      (inventory unreadable / state dir unwritable) — that feeds ``OnFailure=``.
    """
    args = _build_parser().parse_args(argv)
    now = _utc_now()

    if args.self_check:
        ok, detail = _self_check(Path(DEFAULT_INVENTORY_PATH), Path(DEFAULT_TICK_PATH))
        print("status=ok" if ok else f"status=error {detail}")
        return 0 if ok else 1

    try:
        summary = run_pass(now=now, dry_run=args.dry_run)
    except Exception as exc:  # noqa: BLE001 - runner-level fault → non-zero exit (OnFailure)
        print(f"status=error runner_failure {exc.__class__.__name__}: {exc}")
        return 1

    if args.dry_run:
        # Offline preview: one line per component, straight from the pass (which
        # already evaluated with the real effects and wrote nothing in dry_run).
        for line in summary["component_lines"]:
            print(line)
    else:
        print(
            "status={status} evaluated={components_evaluated} emitted={emitted} "
            "suppressed_dedup={suppressed_dedup} coverage_gaps={coverage_gaps} "
            "suppressed_status={suppressed_status} errors={n_errors} "
            "duration_ms={duration_ms}".format(
                n_errors=len(summary["errors"]), **summary
            )
        )

    # A completed pass is exit 0 even if components are unhealthy (they emit).
    # run_pass only raises for runner-level faults, already handled above.
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry
    sys.exit(main())

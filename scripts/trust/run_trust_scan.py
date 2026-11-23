"""Trust-scan entrypoint — the single systemd/CLI target (WP04, contract C2).

Drives the sub-scans (cron-drift via WP02, completion-assertion verification via
WP03, and deployed-unit-vs-repo drift via #817), applies the seen-findings alert
cadence (:mod:`scripts.trust.state`), and emits alerts via the shared ``#701``
bus (:mod:`scripts.trust.alert_render`). No other module runs the timer loop.

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

**Failed sub-scans never resolve** (#1129): each sub-scan (cron, unit-drift,
assertion) is marked *completed* only when it ran to the end without raising.
Reconcile resolves an absent finding only if its source completed; a failed
source's outstanding findings are carried forward unchanged, counted in the
summary's ``carried_forward``, and flagged to the canary via last-tick.json
(``findings_held`` → ``exit_status: failure``). Only cron findings are
baseline-versioned (#1130), so a tick whose baseline did not load holds the
cron findings only; assertion findings reconcile normally.
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
from scripts.trust.unit_drift_detector import (
    DEPLOYED_UNIT_DIR,
    UnitEnumerationError,
    detect_unit_drift,
    enumerate_unit_pairs,
)

__all__ = ["main", "run_scan"]


def _finding_baseline_hash(finding: Any, cron_baseline_hash: str) -> str:
    """Fingerprint-versioning hash per finding type.

    Only cron findings are versioned by the approved-cron baseline content hash:
    a baseline edit is meant to re-evaluate cron findings, and nothing else. An
    assertion's identity ``(kind, agent, artifact_kind, artifact_id)`` and a
    unit-drift finding's ``(unit, kind)`` have no relation to the cron allowlist,
    so they use ``""`` — versioning them would falsely resolve and re-alert every
    outstanding one on each baseline edit (#1130). Default-deny: a new finding
    type is unversioned unless it opts in here. This is the single source of the
    rule so the reconcile-time fingerprint and the emit-retry ``keep_due``
    fingerprint always agree (#817 H1)."""
    return cron_baseline_hash if isinstance(finding, CronDriftFinding) else ""


def _finding_label(finding: Any) -> str:
    """Best-effort human label for a finding in an ``errors[]`` entry. Never raises."""
    try:
        name = getattr(finding, "name", None)
        if name is not None:
            return str(name)
        if isinstance(finding, AssertionFinding):
            return f"{finding.artifact_kind}:{finding.artifact_id}"
        return type(finding).__name__
    except Exception:  # noqa: BLE001 - a label must never break error reporting
        return "<unlabelable>"


# ``AlertResult.reason`` prefix emit_finding uses when it swallowed a render
# failure (RENDER_ERROR:<Type> / RENDER_UNKNOWN_FINDING_TYPE).
_RENDER_FAILURE_PREFIX = "RENDER_"


def _guarded_emit(item: Any, errors: list[str], *, label: str | None = None) -> bool | None:
    """Emit one finding/alert in isolation (#1124).

    Returns ``True`` when delivered, ``False`` when the bus reported
    ``ok=False`` (an expected, retried condition — not recorded as an error),
    and ``None`` on an alert-path fault: the emit raised (recorded as
    ``emit:<Type>:...``) or ``emit_finding`` swallowed a RENDER failure into
    ``ok=False`` with a ``RENDER_*`` reason (recorded as ``emit:<reason>:...``).
    A render failure is a code/data defect, not a bus hiccup — treating it as
    an ordinary failed delivery would make it silent (#1124 review F1).
    ``emit_finding`` is documented never-raise; the raise guard is defence in
    depth so one record can never suppress the rest of the tick's alerts.
    """
    shown = label if label is not None else _finding_label(item)
    try:
        result = alert_render.emit_finding(item)
    except Exception as exc:  # noqa: BLE001 - per-emit isolation (#1124)
        errors.append(f"emit:{exc.__class__.__name__}:{shown}:{exc}")
        return None
    if result.ok:
        return True
    reason = result.reason or ""
    if reason.startswith(_RENDER_FAILURE_PREFIX):
        errors.append(f"emit:{reason}:{shown}")
        return None
    return False


def _keep_due_guarded(
    new_state: dict[str, dict[str, str]],
    finding: Any,
    fingerprints: dict[int, str],
    cron_baseline_hash: str,
    prior_state: dict[str, dict[str, str]],
    errors: list[str],
) -> bool:
    """Revert *finding*'s ``last_alerted`` after a failed emit, never raising.

    Prefers the fingerprint precomputed before reconcile; recomputes (guarded)
    only if the finding object is not in that map. Returns ``False`` (and
    records an error) if the finding could not be kept due.
    """
    try:
        fingerprint = fingerprints.get(id(finding))
        if fingerprint is None:
            fingerprint = state_mod.fingerprint_finding(
                finding, _finding_baseline_hash(finding, cron_baseline_hash)
            )
        state_mod.keep_due(new_state, fingerprint, prior_state)
        return True
    except Exception as exc:  # noqa: BLE001 - per-finding isolation (#1124)
        errors.append(
            f"state_keep_due:{exc.__class__.__name__}:{_finding_label(finding)}:{exc}"
        )
        return False


# Repo root, resolved from this module's location (scripts/trust/run_trust_scan.py
# → parents[2]). The unit-drift sub-scan (#817) globs the repo's canonical unit
# sources under here. felix-trust-scan.service runs from WorkingDirectory=
# /home/claude/kg-automation, so this matches the deployed checkout.
REPO_ROOT = Path(__file__).resolve().parents[2]

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
    path: Path,
    *,
    now: datetime,
    scan_inability: bool,
    error_count: int,
    alert_path_fault: bool = False,
    findings_held: bool = False,
    carried_forward: int = 0,
) -> None:
    """Atomically write the per-tick freshness signal the canary reads (#721).

    ``exit_status`` is ``failure`` on a hard **scan-inability** (e.g. the
    cron baseline is unreadable — a sub-scan could not run at all) **or an
    alert-path fault** (#1124: a finding could not be fingerprinted, reconcile
    raised, an emit raised, or the state save failed — findings may not have
    reached Kent on cadence) **or held findings** (#1129: a sub-scan did not
    complete, so ``carried_forward`` of its outstanding findings could be
    neither confirmed nor resolved this tick). Transient finding-side faults
    (an indeterminate Vikunja re-verify) leave it ``success`` so the canary is
    not paged on recoverable hiccups. ``error_count``
    is informational and deliberately NOT named ``errors``/``error`` so it never
    trips the probe's explicit-error detection. Best-effort: a write failure must
    not crash the tick (fail-safe, NFR-001).
    """
    import os
    import tempfile

    payload = {
        "completed_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "exit_status": (
            "failure" if (scan_inability or alert_path_fault or findings_held) else "success"
        ),
        "scan_inability": scan_inability,
        "alert_path_fault": alert_path_fault,
        "findings_held": findings_held,
        "carried_forward": carried_forward,
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
    repo_root: Path | None = None,
    unit_deployed_dir: Path | None = None,
) -> dict[str, Any]:
    """Run one scan tick: both sub-scans, cadence reconciliation, and emission.

    Returns the summary dict (``ok``, ``drift_findings``, ``assertion_findings``,
    ``unit_drift_findings``, ``unit_coverage``, ``alerts_emitted``,
    ``carried_forward``, ``findings_held``, ``errors``). Never raises — every
    sub-scan and the state I/O are individually guarded (NFR-001). ``dry_run`` computes and
    returns findings but performs **no emission** and **no state/watermark
    mutation**.
    """
    tick_now = now if now is not None else _utc_now()
    errors: list[str] = []
    scan_inability = False  # True only when a sub-scan could not run at all.
    # Sources whose sub-scan ran to the end this tick (#1129). Each add is the
    # LAST statement of its sub-scan's try body — never in an except branch,
    # never in the unit-dir-absent skip — so only a completed source may
    # resolve its findings. Invariant: scan_inability => some source is not
    # completed (the converse does not hold: an assertion failure or the
    # unit-dir skip leaves a source incomplete without scan_inability).
    completed: set[str] = set()

    # ---- Cron-drift sub-scan (WP02) -----------------------------------
    cron_findings: list[CronDriftFinding] = []
    current_baseline_hash = ""
    try:
        baseline = load_baseline(baseline_path) if baseline_path is not None else load_baseline()
        current_baseline_hash = baseline_hash(baseline)
        live_jobs = enumerate_live_crons()
        cron_findings = detect_cron_drift(live_jobs, baseline)
        completed.add(state_mod.SOURCE_CRON)
    except BaselineError as exc:
        errors.append(f"cron_scan:BaselineError:{exc}")
        scan_inability = True
    except CronEnumerationError as exc:
        errors.append(f"cron_scan:CronEnumerationError:{exc}")
        scan_inability = True
    except Exception as exc:  # noqa: BLE001 - fail-safe isolation (NFR-001)
        errors.append(f"cron_scan:{exc.__class__.__name__}:{exc}")
        scan_inability = True

    # ---- Unit-drift sub-scan (#817) -----------------------------------
    # Diff each deployed systemd-user unit against its repo canonical; a content
    # difference is the #816 class (a stale deployed unit that fails silently).
    # Fail-safe like the cron sub-scan: a fault is recorded and never aborts the
    # other sub-scans. Coverage is surfaced in the summary (no silent gaps).
    unit_findings: list[Any] = []
    unit_coverage: dict[str, Any] = {}
    resolved_deployed_dir = (
        unit_deployed_dir if unit_deployed_dir is not None else DEPLOYED_UNIT_DIR
    )
    if not Path(resolved_deployed_dir).is_dir():
        # The deployed-unit dir is office2-specific (claude's ~/.config/systemd/
        # user). Its absence means this environment (CI/dev) has nothing to check
        # — a transparent skip, not a fault. On office2 the dir always exists, so
        # this never silently hides real drift there. Nothing was checked, so
        # the unit-drift source is NOT completed: nothing of it may resolve.
        unit_coverage = {"skipped": f"deployed unit dir not present ({resolved_deployed_dir})"}
    else:
        try:
            pairs, coverage = enumerate_unit_pairs(
                repo_root if repo_root is not None else REPO_ROOT,
                resolved_deployed_dir,
            )
            unit_findings = detect_unit_drift(pairs)
            unit_coverage = {
                "compared": len(coverage.compared),
                "excluded": len(coverage.excluded),
                "deployed_no_repo_source": coverage.deployed_no_repo_source,
                "repo_only": len(coverage.repo_only),
            }
            completed.add(state_mod.SOURCE_UNIT)
        except UnitEnumerationError as exc:
            errors.append(f"unit_scan:UnitEnumerationError:{exc}")
            scan_inability = True
        except Exception as exc:  # noqa: BLE001 - fail-safe isolation (NFR-001)
            errors.append(f"unit_scan:{exc.__class__.__name__}:{exc}")
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
    #
    # (a) and (b) are guarded separately (#1129 B2): a fault in the new-
    # assertion pass must not skip the re-verify of outstanding findings. The
    # assertion source is completed only if BOTH ran to the end.
    assertion_findings: list[AssertionFinding] = []
    watermark: dict[str, int] = {}
    committed_watermark: dict[str, int] = {}
    new_pass_completed = False
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
        new_pass_completed = True
    except Exception as exc:  # noqa: BLE001 - fail-safe isolation (NFR-001)
        errors.append(f"assertion_scan:{exc.__class__.__name__}:{exc}")
        # An assertion-scan fault does NOT count as scan_inability on its
        # own for the "drift is never non-zero" contract — but it does
        # mean the assertion side found nothing new this tick. Hold the
        # watermark at its loaded value so nothing is silently consumed.
        committed_watermark = watermark

    try:
        # (c) Never-delivered, non-re-verifiable findings from state, rebuilt
        # with no external call (#1137). First in this try, so a re-verify
        # raise below can never skip the retry.
        assertion_findings.extend(state_mod.undelivered_assertion_findings(current_state))
        # (b) Re-verify outstanding artifact_missing assertions from state.
        # A still-missing one re-emits its finding (persists 24h cadence); a
        # reappeared one is simply absent from current_findings this tick, so
        # reconcile resolves it as an ASSERTION resolution. Only re-verifiable
        # entries ever resolve; the rest are dropped silently once absent.
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
            # present is True -> omit from current_findings -> reconcile resolves
            # it (only if the assertion source completed this tick).
        if new_pass_completed:
            completed.add(state_mod.SOURCE_ASSERTION)
    except Exception as exc:  # noqa: BLE001 - fail-safe isolation (NFR-001)
        errors.append(f"assertion_reverify:{exc.__class__.__name__}:{exc}")
        # Not scan_inability either (same contract as (a)). Outstanding
        # findings not yet re-verified are carried forward by reconcile. The
        # watermark is held, as it was before (a)/(b) were split.
        committed_watermark = watermark

    # ---- Seen-findings cadence reconciliation --------------------------
    # Fail-CLOSED alert path (#1124): one bad record must never suppress the
    # alerts for every other finding in the tick. Each stage is guarded on its
    # own — per-finding fingerprinting, reconcile, each emit, the state save —
    # and any fault on the alert path sets ``alert_path_fault`` so the canary
    # sees it via last-tick.json (``exit_status: failure``).
    alerts_emitted = 0
    alert_path_fault = False
    # State entries kept only because their source did not complete (#1129).
    # 0 whenever reconcile did not run (dry-run, or the #1124 fallback).
    carried_forward = 0
    if not dry_run:
        all_findings: list[Any] = [*cron_findings, *assertion_findings, *unit_findings]

        # (1) Per-finding fingerprint isolation. A finding whose fingerprint
        # raises cannot enter seen-state; it is emitted on every tick it is
        # re-produced (no cadence) rather than dropped, and the fault is
        # recorded. Cron/unit findings are re-produced each tick by their live
        # sub-scan; an ASSERTION finding is re-produced only if its record is
        # re-read, so the watermark is held for it (see the save guards). The
        # fingerprints are
        # computed once here so no later step calls fingerprint_finding
        # unguarded (the emit-retry keep_due branch reuses them).
        # Per-finding fingerprint hash comes from the single _finding_baseline_hash
        # rule so the reconcile-time and emit-retry fingerprints always agree.
        # Only cron findings carry the baseline hash; assertion and unit-drift
        # findings use "" (#1130), so their keys are stable across baseline
        # edits and baseline outages: a persistent finding dedups on the 24h
        # cadence and clears only by absence.
        findings_with_hash: list[tuple[Any, str]] = []
        fingerprints: dict[int, str] = {}
        unfingerprintable: list[Any] = []
        for finding in all_findings:
            finding_hash = _finding_baseline_hash(finding, current_baseline_hash)
            try:
                fingerprints[id(finding)] = state_mod.fingerprint_finding(
                    finding, finding_hash
                )
            except Exception as exc:  # noqa: BLE001 - per-finding isolation (#1124)
                errors.append(
                    f"state_fingerprint:{exc.__class__.__name__}:"
                    f"{_finding_label(finding)}:{exc}"
                )
                alert_path_fault = True
                unfingerprintable.append(finding)
                continue
            findings_with_hash.append((finding, finding_hash))

        # (2) Reconcile. If it raises, fall back to emitting EVERY current
        # finding (no cadence, each emit guarded) and save NEITHER state nor
        # watermark: cadence resumes once fixed, and new assertions are re-read
        # (and re-emitted) each tick until then — loud beats silent.
        reconciled = False
        to_alert: list[Any] = []
        resolved_events: list[state_mod.ResolvedEvent] = []
        new_state: dict[str, dict[str, str]] = {}
        try:
            to_alert, resolved_events, new_state = state_mod.reconcile(
                findings_with_hash,
                tick_now,
                current_state,
                completed_sources=frozenset(completed),
            )
            reconciled = True
            # Read from reconcile's output, never re-derived (#1129 B3): every
            # new_state key is a current finding or a carried entry (keep_due
            # below adds no keys).
            carried_forward = len(set(new_state) - set(fingerprints.values()))
        except Exception as exc:  # noqa: BLE001 - fail-closed fallback (#1124)
            errors.append(f"state_reconcile:{exc.__class__.__name__}:{exc}")
            alert_path_fault = True

        if reconciled:
            # (3) Emit-gate last_alerted (F3): only a SUCCESSFUL emit counts as
            # "alerted". A failed emit (bus ok=False, or emit raising) must leave
            # the finding DUE next scan, not suppressed until the 24h cadence —
            # so revert its last_alerted via state.keep_due.
            for finding in to_alert:
                delivered = _guarded_emit(finding, errors)
                if delivered is True:
                    alerts_emitted += 1
                    continue
                if delivered is None:
                    alert_path_fault = True
                if not _keep_due_guarded(
                    new_state, finding, fingerprints, current_baseline_hash, current_state, errors
                ):
                    alert_path_fault = True

            for event in resolved_events:
                try:
                    alert = alert_render.render_drift_resolved(
                        event.name, event.first_seen, event.cleared_at, source=event.source
                    )
                except Exception as exc:  # noqa: BLE001 - per-emit isolation (#1124)
                    errors.append(f"emit:{exc.__class__.__name__}:{event.name}:{exc}")
                    alert_path_fault = True
                    continue
                delivered = _guarded_emit(alert, errors, label=event.name)
                if delivered is True:
                    alerts_emitted += 1
                elif delivered is None:
                    alert_path_fault = True

            # Unfingerprintable findings carry no state: emitted every tick they
            # are re-produced (assertions: guaranteed by the watermark hold below).
            for finding in unfingerprintable:
                delivered = _guarded_emit(finding, errors)
                if delivered is True:
                    alerts_emitted += 1
                elif delivered is None:
                    alert_path_fault = True

            # (4) Save guards. The watermark is saved ONLY after the state save
            # succeeded in the same tick: a watermark that advances past a new
            # artifact_missing assertion whose state entry was never persisted
            # would lose that finding's 24h re-alert and its resolution.
            state_saved = False
            try:
                state_mod.save_state(new_state, state_path)
                state_saved = True
            except Exception as exc:  # noqa: BLE001 - fail-safe: state I/O must not crash the tick
                errors.append(f"state_save:{exc.__class__.__name__}:{exc}")
                alert_path_fault = True
            # An unfingerprintable ASSERTION finding never enters state, so it is
            # only re-produced if its record is re-read: hold the watermark at its
            # loaded value (no save) so it stays loud every tick until fixed —
            # the reconcile-fallback posture — instead of being emitted once and
            # permanently lost (#1124 review F2). Coarse (holds the whole
            # watermark, re-reading other new records too), but those are
            # fingerprintable and dedup via the saved state.
            hold_watermark = any(
                isinstance(finding, AssertionFinding) for finding in unfingerprintable
            )
            if state_saved and not hold_watermark:
                try:
                    _save_watermark(committed_watermark, Path(watermark_path))
                except Exception as exc:  # noqa: BLE001 - fail-safe: watermark I/O
                    # Deliberately NOT an alert_path_fault: state was saved, so
                    # re-reading the un-advanced records next tick dedups.
                    errors.append(f"watermark_save:{exc.__class__.__name__}:{exc}")
        else:
            for finding in all_findings:
                delivered = _guarded_emit(finding, errors)
                if delivered is True:
                    alerts_emitted += 1
    else:
        # --dry-run: compute findings only; no emit, no state/watermark
        # mutation. Report the raw finding counts (pre-cadence) so the
        # operator sees everything the scan would consider.
        pass

    ok = not errors
    findings_held = carried_forward > 0
    summary = {
        "ok": ok,
        "drift_findings": len(cron_findings),
        "assertion_findings": len(assertion_findings),
        "unit_drift_findings": len(unit_findings),
        "unit_coverage": unit_coverage,
        "alerts_emitted": alerts_emitted,
        "carried_forward": carried_forward,
        "findings_held": findings_held,
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
            alert_path_fault=alert_path_fault,
            findings_held=findings_held,
            carried_forward=carried_forward,
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
            "completion-assertion verification (WP03) + deployed-unit-vs-repo "
            "drift detection (#817), alerting via the #701 bus."
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

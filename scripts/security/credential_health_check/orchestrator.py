"""Orchestrator: the per-cycle loop that ties readers + writers + dedup together.

See kitty-specs/credential-expiry-health-check-01KRCF92/data-model.md for the
state model and §State transitions for the per-credential decision tree.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from .cadence import compute_boundary, is_fixed_interval_cadence, is_within_warning_window
from .github_writer import (
    GitHubWriteError,
    MANIFEST_QUALITY_TITLE_PREFIX,
    cadence_alert_body,
    cadence_alert_title,
    cadence_alert_title_prefix,
    create_issue,
    dedup_check,
    manifest_quality_body,
    manifest_quality_title,
    staleness_alert_body,
    staleness_alert_title,
    staleness_alert_title_prefix,
)
from .manifest import (
    ManifestQualityIssue,
    ManifestUnreadableError,
    read_manifest,
)
from .signals import MONITOR_ACTIVITY_READERS
from .vikunja_writer import VikunjaWriteError, create_task, load_token, lookup_inbox_project_id


@dataclass
class CycleResult:
    """Summary of one cycle's actions. Per-credential details are in the log."""

    credentials_evaluated: int = 0
    cadence_alerts_filed: int = 0
    staleness_alerts_filed: int = 0
    alerts_deduped: int = 0
    manifest_quality_issue_filed: bool = False
    errors: list[str] = field(default_factory=list)


def _log(logger: Optional[logging.Logger], level: int, msg: str, /, **kwargs) -> None:
    if logger is None:
        return
    if kwargs:
        kv = " ".join(f"{k}={v}" for k, v in kwargs.items())
        logger.log(level, "%s %s", msg, kv)
    else:
        logger.log(level, msg)


def run_cycle(
    manifest_path: str,
    today: date,
    *,
    dry_run: bool = False,
    logger: Optional[logging.Logger] = None,
) -> CycleResult:
    """Execute one full cycle. Returns a CycleResult summary.

    Raises ManifestUnreadableError when the manifest cannot be read at all
    (per FR-011). All other failures (per-credential, per-writer) are logged
    and accumulated in result.errors; the cycle continues.
    """
    cycle_id = uuid.uuid4().hex[:8]
    result = CycleResult()
    _log(
        logger,
        logging.INFO,
        "cycle_start",
        cycle_id=cycle_id,
        today=today.isoformat(),
        manifest=manifest_path,
        dry_run=dry_run,
    )

    well_formed, malformed = read_manifest(manifest_path)
    _log(
        logger,
        logging.INFO,
        "manifest_read",
        cycle_id=cycle_id,
        well_formed=len(well_formed),
        malformed=len(malformed),
    )

    # Per-credential processing.
    vikunja_token: Optional[str] = None
    inbox_project_id: Optional[int] = None

    for cred in well_formed:
        result.credentials_evaluated += 1

        # Branch A: fixed-interval cadence.
        if is_fixed_interval_cadence(cred.review_cadence):
            boundary = compute_boundary(cred)
            if boundary is None:
                _log(
                    logger,
                    logging.WARNING,
                    "credential_evaluated",
                    cycle_id=cycle_id,
                    name=cred.name,
                    action="skip_missing_anchor",
                )
                continue
            if not is_within_warning_window(boundary, today):
                _log(
                    logger,
                    logging.INFO,
                    "credential_evaluated",
                    cycle_id=cycle_id,
                    name=cred.name,
                    action="within_cadence",
                    boundary=boundary.isoformat(),
                )
                continue
            # In warning window — dedup, then file.
            _process_cadence_alert(
                cred,
                boundary,
                today,
                cycle_id,
                result,
                logger,
                dry_run,
                vikunja_token=vikunja_token,
                inbox_project_id=inbox_project_id,
            )
            # Cache Vikunja state for subsequent credentials in this cycle.
            if vikunja_token is None and not dry_run:
                try:
                    vikunja_token = load_token()
                    inbox_project_id = lookup_inbox_project_id(vikunja_token)
                except VikunjaWriteError:
                    # _process_cadence_alert already logged. The cached state
                    # will remain None and subsequent credentials will retry.
                    pass

        # Branch B: monitor-activity credentials.
        elif cred.name in MONITOR_ACTIVITY_READERS:
            _process_staleness_alert(cred, today, cycle_id, result, logger, dry_run)

        # Branch C: skip (on-revocation, n/a, session, or unmapped monitor-activity).
        else:
            _log(
                logger,
                logging.INFO,
                "credential_evaluated",
                cycle_id=cycle_id,
                name=cred.name,
                action="skip_non_fixed",
                review_cadence=cred.review_cadence,
            )

    # Manifest-quality batch (FR-012).
    if malformed:
        _process_manifest_quality(malformed, today, cycle_id, result, logger, dry_run)

    _log(
        logger,
        logging.INFO,
        "cycle_end",
        cycle_id=cycle_id,
        credentials_evaluated=result.credentials_evaluated,
        cadence_filed=result.cadence_alerts_filed,
        staleness_filed=result.staleness_alerts_filed,
        deduped=result.alerts_deduped,
        manifest_quality_filed=result.manifest_quality_issue_filed,
        errors=len(result.errors),
    )
    return result


# ---------- Branch processors ----------


def _process_cadence_alert(
    cred,
    boundary: date,
    today: date,
    cycle_id: str,
    result: CycleResult,
    logger,
    dry_run: bool,
    *,
    vikunja_token: Optional[str],
    inbox_project_id: Optional[int],
) -> None:
    prefix = cadence_alert_title_prefix(cred)
    try:
        existing = dedup_check(prefix)
    except GitHubWriteError as e:
        _log(
            logger,
            logging.ERROR,
            "error",
            cycle_id=cycle_id,
            name=cred.name,
            stage="dedup_check",
            message=str(e),
        )
        result.errors.append(f"{cred.name}: dedup_check failed: {e}")
        return
    if existing:
        _log(
            logger,
            logging.INFO,
            "alert_deduped",
            cycle_id=cycle_id,
            name=cred.name,
            variant="cadence",
            existing_issue=existing[0],
        )
        result.alerts_deduped += 1
        return

    if dry_run:
        _log(
            logger,
            logging.INFO,
            "credential_evaluated",
            cycle_id=cycle_id,
            name=cred.name,
            action="alert_would_file",
            variant="cadence",
            boundary=boundary.isoformat(),
        )
        return

    # Step 1: Vikunja task first.
    try:
        token = vikunja_token or load_token()
        proj_id = inbox_project_id if inbox_project_id is not None else lookup_inbox_project_id(token)
        task_id = create_task(cred, boundary, github_issue_number=0, token=token, inbox_project_id=proj_id)
    except VikunjaWriteError as e:
        _log(
            logger,
            logging.ERROR,
            "error",
            cycle_id=cycle_id,
            name=cred.name,
            stage="vikunja_create_task",
            message=str(e),
        )
        result.errors.append(f"{cred.name}: vikunja_create_task failed: {e}")
        return

    # Note: task_description still encodes github_issue_number=0 (placeholder).
    # Vikunja PATCH after issue creation would close the cross-reference loop;
    # not in scope for v1 (the GitHub issue body carries the canonical link).

    # Step 2: GitHub issue.
    title = cadence_alert_title(cred, boundary)
    body = cadence_alert_body(cred, boundary, vikunja_task_id=task_id, cycle_date=today)
    try:
        issue_number = create_issue(title=title, body=body)
    except GitHubWriteError as e:
        _log(
            logger,
            logging.ERROR,
            "error",
            cycle_id=cycle_id,
            name=cred.name,
            stage="github_create_issue_after_task",
            task_id=task_id,
            message=str(e),
        )
        result.errors.append(
            f"{cred.name}: github_create_issue failed AFTER Vikunja task {task_id} "
            f"was created (orphan): {e}"
        )
        return

    result.cadence_alerts_filed += 1
    _log(
        logger,
        logging.INFO,
        "alert_filed",
        cycle_id=cycle_id,
        name=cred.name,
        variant="cadence",
        github_issue=issue_number,
        vikunja_task=task_id,
        boundary=boundary.isoformat(),
    )


def _process_staleness_alert(
    cred,
    today: date,
    cycle_id: str,
    result: CycleResult,
    logger,
    dry_run: bool,
) -> None:
    reader = MONITOR_ACTIVITY_READERS[cred.name]
    try:
        failure = reader(cred)
    except Exception as e:  # noqa: BLE001 — reader contract returns None on failures it handles
        _log(
            logger,
            logging.ERROR,
            "error",
            cycle_id=cycle_id,
            name=cred.name,
            stage="signal_reader",
            message=str(e),
        )
        result.errors.append(f"{cred.name}: signal_reader raised: {e}")
        return

    if failure is None:
        _log(
            logger,
            logging.INFO,
            "credential_evaluated",
            cycle_id=cycle_id,
            name=cred.name,
            action="signal_healthy",
        )
        return

    # Signal failing — dedup, then file GitHub issue only (no Vikunja task).
    prefix = staleness_alert_title_prefix(cred)
    try:
        existing = dedup_check(prefix)
    except GitHubWriteError as e:
        _log(
            logger,
            logging.ERROR,
            "error",
            cycle_id=cycle_id,
            name=cred.name,
            stage="dedup_check_staleness",
            message=str(e),
        )
        result.errors.append(f"{cred.name}: dedup_check failed: {e}")
        return
    if existing:
        _log(
            logger,
            logging.INFO,
            "alert_deduped",
            cycle_id=cycle_id,
            name=cred.name,
            variant="staleness",
            existing_issue=existing[0],
        )
        result.alerts_deduped += 1
        return

    if dry_run:
        _log(
            logger,
            logging.INFO,
            "credential_evaluated",
            cycle_id=cycle_id,
            name=cred.name,
            action="alert_would_file",
            variant="staleness",
            summary=failure.summary,
        )
        return

    title = staleness_alert_title(cred)
    body = staleness_alert_body(cred, failure, today)
    try:
        issue_number = create_issue(title=title, body=body)
    except GitHubWriteError as e:
        _log(
            logger,
            logging.ERROR,
            "error",
            cycle_id=cycle_id,
            name=cred.name,
            stage="github_create_issue_staleness",
            message=str(e),
        )
        result.errors.append(f"{cred.name}: github_create_issue (staleness) failed: {e}")
        return

    result.staleness_alerts_filed += 1
    _log(
        logger,
        logging.INFO,
        "alert_filed",
        cycle_id=cycle_id,
        name=cred.name,
        variant="staleness",
        github_issue=issue_number,
        summary=failure.summary,
    )


def _process_manifest_quality(
    malformed: list[ManifestQualityIssue],
    today: date,
    cycle_id: str,
    result: CycleResult,
    logger,
    dry_run: bool,
) -> None:
    try:
        existing = dedup_check(MANIFEST_QUALITY_TITLE_PREFIX)
    except GitHubWriteError as e:
        _log(
            logger,
            logging.ERROR,
            "error",
            cycle_id=cycle_id,
            stage="dedup_check_manifest_quality",
            message=str(e),
        )
        result.errors.append(f"manifest_quality dedup_check failed: {e}")
        return
    if existing:
        _log(
            logger,
            logging.INFO,
            "alert_deduped",
            cycle_id=cycle_id,
            variant="manifest_quality",
            existing_issue=existing[0],
            entries=len(malformed),
        )
        result.alerts_deduped += 1
        return

    if dry_run:
        _log(
            logger,
            logging.INFO,
            "manifest_quality_would_file",
            cycle_id=cycle_id,
            entries=len(malformed),
        )
        return

    title = manifest_quality_title(len(malformed), today)
    body = manifest_quality_body(malformed, today)
    try:
        issue_number = create_issue(title=title, body=body)
    except GitHubWriteError as e:
        _log(
            logger,
            logging.ERROR,
            "error",
            cycle_id=cycle_id,
            stage="github_create_issue_manifest_quality",
            message=str(e),
        )
        result.errors.append(f"manifest_quality issue creation failed: {e}")
        return

    result.manifest_quality_issue_filed = True
    _log(
        logger,
        logging.INFO,
        "manifest_quality_filed",
        cycle_id=cycle_id,
        github_issue=issue_number,
        entries=len(malformed),
    )

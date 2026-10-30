#!/usr/bin/env python3
"""ACTIVATE: the one-shot production cutover to the staged Vikunja release (#1087, WP04).

Design: ``kitty-specs/vikunja-image-deploy-01M65D3V/research.md`` R-9 to R-24
(they take precedence over R-1 to R-8), ``contracts/entrypoints.md``
Amendments, ``data-model.md`` (ActivationMarker, image-tag state) and
``analysis-report.md`` U1. The startup lock rests on WP05's evidence
(``docs/design/architecture/evidence/vikunja-lock-sandbox-2026-10.md``:
FAIL-CLOSED CONFIRMED): with ``pull_policy: never`` a missing
``office2.local/vikunja:active`` tag makes ``compose up -d`` fail closed.

Modes
-----
Both modes read the activation marker first.

* **Marker present (replay, R-12, R-24).** ``success``: reconcile read-only
  (running container image is the release ID, ``/api/v1/info`` reports the
  release version), exit 0, else ``ACTIVATE_SUCCESS_NOT_RECONCILED``.
  ``rolled_back``: ``ACTIVATE_ROLLED_BACK_REMOVE_QUEUED_MANIFEST``. Anything
  else: ``ACTIVATE_PRIOR_ATTEMPT_<PHASE>``. Malformed: ``MARKER_UNREADABLE``.
  No Docker or Compose call except the read-only reconcile.
* **No marker, ``--dry-run``.** Every precondition (R-10, R-19) is checked
  and reported on its own line; exit 1 if any is unmet. Read-only.
* **No marker, ``--apply``.** The preconditions, ``pre_version`` from
  ``/api/v1/info`` (U1), then the exclusive marker (``started``), and inside a
  300 s outage deadline (NFR-001): ``compose down`` (marker ``stopped`` at
  once, R-21); untag ``active`` (the lock, R-9), no container, snapshot
  (INV-2; marker ``snapshotted``); tag ``active`` to the release
  (``retagged``); ``compose up -d`` (``started_new``); verify (container
  image, version, migration log); marker ``verified``/``success``.

Deadlines (R-15)
----------------
Every subprocess runs through a runner bound to the enclosing deadline: the
nominal timeout (120 s Compose, 30 s Docker) is re-capped to what remains
immediately before each call, so no call can outlive the 300 s outage window
or the 120 s cleanup budget. In cleanup, the log capture and ``down`` leave
:data:`CLEANUP_UNTAG_RESERVE_S` of the budget for the untag, recomputed per
call. A failure found with the outage window spent is reported as
``ACTIVATE_OUTAGE_DEADLINE`` (the underlying code goes to the private log).

Activation lock (WP06 review, CRITICAL)
---------------------------------------
felix-deployer's deploylock belongs to the tick, not to this child, so
ACTIVATE holds its own: ``<activation root>/activation.lock``
(:data:`ACTIVATION_LOCK_NAME`, shared with the WP06 rollback helper), opened
relative to the verified root descriptor and ``flock``-ed exclusive and
non-blocking before the marker is read or anything is written. It is held
until the process ends, through cleanup. A held lock refuses with
``ACTIVATE_LOCK_BUSY`` and no Docker call. ``--dry-run`` only probes it
(never creates it) and reports ``ACTIVATION_LOCK_FREE``.

Replay writes nothing: its failures carry no private detail, so ``run_cli``
writes no log file on any replay path.

Invariants
----------
* INV-1: no code path here ever tags ``active`` to the rollback image. Only
  the rollback helper does, after its guard.
* INV-2: ``down``, untag, no container, then copy.
* Every failure after ``down`` runs the cleanup under its own 120 s budget:
  capture the container's logs privately (if one exists), ``compose down``,
  untag ``active``, marker outcome ``failed`` with ``failed_phase`` and a
  stable code. It never starts anything.

Output (R-16): line 1 is a fixed summary (``ACTIVATE_*`` or ``FAILED
code=...``), then detail lines carrying only IDs, digests, versions, paths,
counts and stable codes. Raw Docker, Compose and container output goes only
to the private 0700 folder.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import stat
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TextIO

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import yaml  # noqa: E402

from scripts.deploy.vikunja_release import core, dbsafety, readiness  # noqa: E402
from scripts.deploy.vikunja_release.core import Fail  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_PATH = REPO_ROOT / "services" / "vikunja" / "release.json"

# R-15 deadlines (seconds).
OUTAGE_S = 300.0  # NFR-001: from `down` to a verified start
COMPOSE_TIMEOUT = 120
DOCKER_TIMEOUT = 30
READY_BUDGET_S = 180.0
LOGS_TIMEOUT_S = 30.0
#: readiness.capture_logs may wait this long AFTER its own timeout to reap a
#: killed ``docker logs`` child (readiness._stop, ``_REAP_TIMEOUT_S``), plus a
#: margin; the capture timeout leaves both inside the enclosing deadline.
READINESS_REAP_ALLOWANCE_S = 5.0
LOGS_REAP_MARGIN_S = 1.0
CLEANUP_BUDGET_S = 120.0
#: Cleanup keeps this much of its budget for the untag, so a slow `down`
#: can never use up the time the lock needs.
CLEANUP_UNTAG_RESERVE_S = 35.0
PRE_VERSION_BUDGET_S = 15.0
RECONCILE_BUDGET_S = 15.0
#: Free space on the snapshot filesystem, as a multiple of DB plus WAL.
SPACE_FACTOR = 3
_MAX_COMPOSE_BYTES = 256 * 1024

# Summary identifiers (registered at import; never free text).
ACTIVATE_DRY_RUN_READY = "ACTIVATE_DRY_RUN_READY"
ACTIVATE_VERIFIED = "ACTIVATE_VERIFIED"
ACTIVATE_ALREADY_VERIFIED = "ACTIVATE_ALREADY_VERIFIED"
ACTIVATE_CHECK = "ACTIVATE_CHECK"
ACTIVATE_PLAN = "ACTIVATE_PLAN"
ACTIVATE_MARKER = "ACTIVATE_MARKER"
ACTIVATE_PRE_VERSION = "ACTIVATE_PRE_VERSION"
ACTIVATE_STEP = "ACTIVATE_STEP"
ACTIVATE_SNAPSHOT = "ACTIVATE_SNAPSHOT"
ACTIVATE_MIGRATION = "ACTIVATE_MIGRATION"
ACTIVATE_LOGS = "ACTIVATE_LOGS"
ACTIVATE_FAILED_AT = "ACTIVATE_FAILED_AT"
ACTIVATE_CLEANUP = "ACTIVATE_CLEANUP"
ACTIVATION_LOCK_FREE = "ACTIVATION_LOCK_FREE"

#: The lock file in the activation root; the WP06 rollback helper uses the same name.
ACTIVATION_LOCK_NAME = dbsafety.ACTIVATION_LOCK_NAME

core.register_summaries(
    ACTIVATE_DRY_RUN_READY, ACTIVATE_VERIFIED, ACTIVATE_ALREADY_VERIFIED, ACTIVATE_CHECK, ACTIVATE_PLAN,
    ACTIVATE_MARKER, ACTIVATE_PRE_VERSION, ACTIVATE_STEP, ACTIVATE_SNAPSHOT, ACTIVATE_MIGRATION,
    ACTIVATE_LOGS, ACTIVATE_FAILED_AT, ACTIVATE_CLEANUP, ACTIVATION_LOCK_FREE,
)

#: Precondition names, in report order (T017).
CHECKS = ("PRE_STORE", "PRE_RELEASE_TAG", "PRE_ACTIVE_TAG", "PRE_CONTAINER", "PRE_COMPOSE",
          "PRE_DATA_READABLE", "PRE_SPACE", "PRE_VERSION")

#: Marker phase entered by each step (the ``failed_phase`` on failure).
_NEXT = {"started": "stopped", "stopped": "snapshotted", "snapshotted": "retagged",
         "retagged": "started_new", "started_new": "verified"}

Line = tuple[str, dict[str, Any]]


def log_capture_timeout(remaining: float) -> float:
    """The ``capture_logs`` timeout that keeps capture plus its reap inside
    *remaining* seconds; ``0`` means there is no room, so skip the capture."""
    return max(0.0, min(LOGS_TIMEOUT_S, remaining - READINESS_REAP_ALLOWANCE_S - LOGS_REAP_MARGIN_S))


def _stamp(now: datetime) -> str:
    return now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rollback_version(record: dict[str, Any]) -> str:
    """The version ``/api/v1/info`` reports for the rollback image, derived
    from its reviewed reference (``vikunja/vikunja:2.4.0`` -> ``v2.4.0``)."""
    tag = record["rollback"]["ref"].rsplit(":", 1)[1]
    return tag if tag.startswith("v") else f"v{tag}"


class Activate:
    """One ACTIVATE run against injected Docker, HTTP, log and clock seams."""

    def __init__(self, record: dict[str, Any], *, runner: Callable[..., Any], popen: Callable[..., Any],
                 clock: Callable[[], float], now: Callable[[], datetime],
                 sleep: Callable[[float], None], disk_usage: Callable[[str], Any]) -> None:
        self.rec = record
        self.runner = runner
        self.base_runner = runner
        self.popen = popen
        self.clock = clock
        self.now = now
        self.sleep = sleep
        self.disk_usage = disk_usage
        self.digest: str = record["image"]["config_digest"]
        self.rollback_id: str = record["rollback"]["image_id"]
        self.release_tag: str = record["tags"]["release"]
        self.active_tag: str = record["tags"]["active"]
        svc = record["service"]
        self.compose_file: str = svc["compose_file"]
        self.container: str = svc["container"]
        self.info_url: str = svc["info_url"]
        self.data_dir = Path(svc["data_dir"])
        roots = record["roots"]
        self.activation_root = Path(roots["activation"])
        self.snapshot_root = Path(roots["snapshots"])
        self.private_root = Path(roots["private_logs"])
        self.marker_path = self.activation_root / f"{record['release_version']}.json"
        self.lock_path = self.activation_root / ACTIVATION_LOCK_NAME
        #: The held activation-lock descriptor; released only by :meth:`release`.
        self.lock_fd: int | None = None
        #: Lines printed after the summary (or after ``FAILED``).
        self.details: list[Line] = []
        self.marker: dict[str, Any] = {}
        self.phase: str | None = None

    # -- read-only helpers ---------------------------------------------------

    def _compose_argv(self, *action: str) -> list[str]:
        """Exactly the unit's arguments: ``docker compose -f <file> ...``."""
        return ["docker", "compose", "-f", self.compose_file, *action]

    def _release_verified(self) -> None:
        if core.image_id(self.release_tag, self.runner) != self.digest:
            raise Fail("PRE_RELEASE_TAG_NOT_STAGED")
        os_want, arch_want = self.rec["image"]["platform"].split("/", 1)
        facts = core.image_facts(self.digest, self.runner)
        if (facts is None or facts["id"] != self.digest or facts["architecture"] != arch_want
                or facts["os"] != os_want or facts["user"] != self.rec["image"]["user"]
                or facts["revision"] != self.rec["source_revision"]):
            raise Fail("PRE_RELEASE_FACTS_MISMATCH")

    def _active_is_rollback(self) -> None:
        active = core.image_id(self.active_tag, self.runner)
        if active is None:
            raise Fail("PRE_ACTIVE_ABSENT")
        if active != self.rollback_id:
            raise Fail("PRE_ACTIVE_NOT_ROLLBACK")

    def _container_is_rollback(self) -> None:
        found = core.container_image(self.container, self.runner)
        if found is None:
            raise Fail("PRE_CONTAINER_ABSENT")
        image, configured = found
        if image != self.rollback_id:
            raise Fail("PRE_CONTAINER_NOT_ROLLBACK")
        if configured not in (self.rec["rollback"]["ref"], self.active_tag):
            raise Fail("PRE_CONTAINER_REF_UNEXPECTED")

    def _compose_on_active(self) -> None:
        """The live Compose file, read only: the service whose
        ``container_name`` is ours names ``active`` with ``pull_policy: never``."""
        try:
            with open(self.compose_file, "rb") as fh:
                raw = fh.read(_MAX_COMPOSE_BYTES + 1)
            if len(raw) > _MAX_COMPOSE_BYTES:
                raise Fail("PRE_COMPOSE_UNREADABLE")
            doc = yaml.safe_load(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            raise Fail("PRE_COMPOSE_UNREADABLE") from exc
        services = doc.get("services") if isinstance(doc, dict) else None
        if not isinstance(services, dict):
            raise Fail("PRE_COMPOSE_UNREADABLE")
        ours = [s for s in services.values() if isinstance(s, dict) and s.get("container_name") == self.container]
        if len(ours) != 1:
            raise Fail("PRE_COMPOSE_SERVICE_MISSING")
        if ours[0].get("image") != self.active_tag:
            raise Fail("PRE_COMPOSE_NOT_ACTIVE")
        if ours[0].get("pull_policy") != "never":
            raise Fail("PRE_COMPOSE_PULL_POLICY")

    def _db_size(self) -> int:
        """Read-open each data file (no write, no SQLite) and return the
        size of the DB plus WAL."""
        total = 0
        for name in (dbsafety.DB_NAME, dbsafety.WAL_NAME, dbsafety.SHM_NAME):
            path = self.data_dir / name
            if name != dbsafety.DB_NAME and not os.path.lexists(path):
                continue
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            except OSError as exc:
                raise Fail("PRE_DATA_UNREADABLE") from exc
            try:
                st = os.fstat(fd)
                if not stat.S_ISREG(st.st_mode):
                    raise Fail("PRE_DATA_UNREADABLE")
                os.read(fd, 1)
            except OSError as exc:
                raise Fail("PRE_DATA_UNREADABLE") from exc
            finally:
                os.close(fd)
            if name != dbsafety.SHM_NAME:
                total += st.st_size
        return total

    def _space_ok(self) -> None:
        """Sizes by ``lstat`` only, so an unreadable DB is reported once, by
        ``PRE_DATA_READABLE``; a missing DB makes the need unknown."""
        size = 0
        for name in (dbsafety.DB_NAME, dbsafety.WAL_NAME):
            try:
                size += os.lstat(self.data_dir / name).st_size
            except FileNotFoundError as exc:
                if name == dbsafety.DB_NAME:
                    raise Fail("PRE_SPACE_UNKNOWN") from exc
            except OSError as exc:
                raise Fail("PRE_SPACE_UNKNOWN") from exc
        need = SPACE_FACTOR * size
        probe = self.snapshot_root
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        try:
            free = self.disk_usage(str(probe)).free
        except OSError as exc:
            raise Fail("PRE_SPACE_UNKNOWN") from exc
        if free < need:
            raise Fail("PRE_SPACE_LOW")

    def _pre_version(self) -> str:
        try:
            return readiness.wait_ready(self.info_url, rollback_version(self.rec),
                                        core.Deadline(PRE_VERSION_BUDGET_S, self.clock),
                                        runner=self.runner, sleep=self.sleep)
        except Fail as exc:
            raise Fail("PRE_VERSION_UNREADABLE", detail_private=exc.code) from exc

    def preconditions(self) -> str:
        """T017: report each precondition separately; refuse when any is
        unmet. Read-only. Returns ``pre_version``."""
        steps: dict[str, Callable[[], Any]] = {
            "PRE_STORE": lambda: core.docker_store_ok(self.runner),
            "PRE_RELEASE_TAG": self._release_verified,
            "PRE_ACTIVE_TAG": self._active_is_rollback,
            "PRE_CONTAINER": self._container_is_rollback,
            "PRE_COMPOSE": self._compose_on_active,
            "PRE_DATA_READABLE": self._db_size,
            "PRE_SPACE": self._space_ok,
            "PRE_VERSION": self._pre_version,
        }
        unmet = 0
        pre_version = None
        for name in CHECKS:
            try:
                value = steps[name]()
            except Fail as exc:
                unmet += 1
                self.details.append((ACTIVATE_CHECK, {"check_code": name, "status_code": "UNMET",
                                                      "code": exc.code}))
                continue
            if name == "PRE_VERSION":
                pre_version = value
            self.details.append((ACTIVATE_CHECK, {"check_code": name, "status_code": "MET"}))
        self.details.append((ACTIVATE_MARKER, {"marker": self.marker_path, "status_code": "ABSENT"}))
        if unmet:
            raise Fail("ACTIVATE_PRECONDITIONS_UNMET")
        assert pre_version is not None
        self.details.append((ACTIVATE_PRE_VERSION, {"pre_version": pre_version}))
        return pre_version

    # -- replay (T018) -------------------------------------------------------

    def replay(self, marker: dict[str, Any]) -> list[Line]:
        """A marker exists: never stop or start again (R-12, R-24). Fully
        read-only: every failure is re-raised as a bare code with no private
        detail, so not even a private log file is written."""
        try:
            return self._replay(marker)
        except Fail as exc:
            raise Fail(exc.code) from None
        except Exception:  # noqa: BLE001 - no traceback file on a replay
            raise Fail("ACTIVATE_REPLAY_INTERNAL_ERROR") from None

    def _replay(self, marker: dict[str, Any]) -> list[Line]:
        outcome = marker.get("outcome")
        phase = marker["phase"]
        self.details.append((ACTIVATE_MARKER, {"marker": self.marker_path, "phase": phase,
                                               "outcome": outcome}))
        if outcome == "rolled_back":
            raise Fail("ACTIVATE_ROLLED_BACK_REMOVE_QUEUED_MANIFEST")
        if outcome != "success":
            raise Fail(f"ACTIVATE_PRIOR_ATTEMPT_{phase.upper()}")
        try:
            found = core.container_image(self.container, self.runner)
            if found is None or found[0] != self.digest:
                raise Fail("ACTIVATE_SUCCESS_NOT_RECONCILED")
            version = readiness.wait_ready(self.info_url, self.rec["release_version"],
                                           core.Deadline(RECONCILE_BUDGET_S, self.clock),
                                           runner=self.runner, sleep=self.sleep)
        except Fail as exc:
            if exc.code == "ACTIVATE_SUCCESS_NOT_RECONCILED":
                raise
            raise Fail("ACTIVATE_SUCCESS_NOT_RECONCILED") from exc
        return [(ACTIVATE_ALREADY_VERIFIED, {"release_version": version, "config_digest": self.digest}),
                *self.details]

    # -- activation lock -------------------------------------------------------

    def take_lock(self) -> None:
        """Verify (creating if absent) the activation root, then hold an
        exclusive non-blocking ``flock`` on its ``activation.lock`` through
        the shared :func:`dbsafety.take_activation_lock`."""
        root_fd = dbsafety.open_private_root(self.activation_root, code="ACTIVATION_ROOT")
        try:
            self.lock_fd = dbsafety.take_activation_lock(root_fd, busy_code="ACTIVATE_LOCK_BUSY",
                                                         unsafe_code="ACTIVATE_LOCK_UNAVAILABLE")
        finally:
            os.close(root_fd)

    def probe_lock(self) -> None:
        """Dry run: report whether the lock is free without creating
        anything. A held lock refuses as the apply would."""
        try:
            free = dbsafety.activation_lock_free(self.activation_root)
        except OSError as exc:
            raise Fail("ACTIVATE_LOCK_UNAVAILABLE") from exc
        if not free:
            raise Fail("ACTIVATE_LOCK_BUSY")
        self.details.append((ACTIVATION_LOCK_FREE, {"lock": self.lock_path}))

    def release(self) -> None:
        """Called only as the process ends (``main``'s ``finally``)."""
        if self.lock_fd is not None:
            os.close(self.lock_fd)
            self.lock_fd = None

    # -- modes -----------------------------------------------------------------

    def dry_run(self) -> list[Line]:
        self.probe_lock()
        marker = core.marker_read(self.marker_path)
        if marker is not None:
            return self.replay(marker)
        self.preconditions()
        plan = ["MARKER_STARTED", "COMPOSE_DOWN", "UNTAG_ACTIVE", "SNAPSHOT", "TAG_ACTIVE_RELEASE",
                "COMPOSE_UP", "VERIFY"]
        return [(ACTIVATE_DRY_RUN_READY, {"release_version": self.rec["release_version"],
                                          "config_digest": self.digest}),
                *self.details, *((ACTIVATE_PLAN, {"step_code": s}) for s in plan)]

    def apply(self) -> list[Line]:
        self.take_lock()  # before the marker is read or anything is written
        marker = core.marker_read(self.marker_path)
        if marker is not None:
            return self.replay(marker)
        pre_version = self.preconditions()
        # Private roots exist and are verified before anything stops.
        dbsafety.prepare_private_root(self.private_root, code="FAILURES_ROOT")
        dbsafety.prepare_private_root(self.snapshot_root, code="SNAPSHOT_ROOT")

        self.marker = {"phase": "started", "outcome": None, "started_at": _stamp(self.now()),
                       "release_version": self.rec["release_version"], "config_digest": self.digest,
                       "rollback_image_id": self.rollback_id, "pre_version": pre_version}
        core.marker_create(self.marker_path, self.marker)
        self.phase = "started"
        outage = core.Deadline(OUTAGE_S, self.clock)
        try:
            with self._within(outage, "ACTIVATE_OUTAGE_DEADLINE"):
                return self._cutover(outage, pre_version)
        except Fail as exc:
            if exc.code != "ACTIVATE_OUTAGE_DEADLINE" and outage.remaining() <= 0:
                exc = Fail("ACTIVATE_OUTAGE_DEADLINE", detail_private=f"{exc.code}\n{exc.detail_private or ''}")
            self._cleanup(exc.code)
            raise exc from None
        except Exception as exc:  # noqa: BLE001 - a bug after `down` still takes the lock
            self._cleanup("ACTIVATE_INTERNAL_ERROR")
            raise Fail("ACTIVATE_INTERNAL_ERROR", detail_private=traceback.format_exc()) from exc

    # -- the cutover (T019, T020) --------------------------------------------

    def _step(self, argv: list[str], timeout: float, step: str, code: str) -> None:
        rc, out, err = core.run(argv, timeout, step=step, runner=self.runner)
        if rc != 0:
            raise Fail(code, detail_private=err or out)

    def _advance(self, phase: str, **fields: Any) -> None:
        self.marker.update(phase=phase, updated_at=_stamp(self.now()), **fields)
        core.marker_update(self.marker_path, self.marker)
        self.phase = phase
        self.details.append((ACTIVATE_STEP, {"phase": phase}))

    @contextlib.contextmanager
    def _within(self, deadline: core.Deadline, code: str, reserve: float = 0.0):
        """Bind every subprocess in the block to *deadline*: each call's
        timeout becomes ``min(nominal, remaining - reserve)``, recomputed
        immediately before the call; with nothing left the call is not made
        and ``Fail(code)`` is raised."""
        base = self.base_runner

        def bounded(argv: list[str], **kwargs: Any) -> Any:
            remaining = deadline.remaining() - reserve
            if remaining <= 0:
                raise Fail(code)
            kwargs["timeout"] = min(float(kwargs["timeout"]), remaining)
            return base(argv, **kwargs)

        previous = self.runner
        self.runner = bounded
        try:
            yield
        finally:
            self.runner = previous

    def _untag_active(self) -> None:
        """Remove the ``active`` tag only (the lock); both images stay.
        Through :func:`dbsafety.untag_active`: before any ``image rm`` it
        proves the image ``active`` points at keeps another name (the
        rollback ref resolving to the rollback ID, or the release tag to the
        config digest), else ``ACTIVATE_UNTAG_UNSAFE``; an absent tag counts
        as removed. Used by the cutover and by cleanup alike."""
        dbsafety.untag_active(self.runner, self.active_tag,
                              [(self.rec["rollback"]["ref"], self.rollback_id), (self.release_tag, self.digest)],
                              unsafe_code="ACTIVATE_UNTAG_UNSAFE", failed_code="ACTIVATE_UNTAG_FAILED")

    def _cutover(self, outage: core.Deadline, pre_version: str) -> list[Line]:
        """Runs with ``self.runner`` bound to *outage* (see :meth:`_within`)."""
        cap = outage.cap
        # T019: stop, record it at once (R-21), then lock and snapshot.
        self._step(self._compose_argv("down"), COMPOSE_TIMEOUT, "COMPOSE_DOWN", "ACTIVATE_COMPOSE_DOWN_FAILED")
        self._advance("stopped")
        self._untag_active()
        if core.image_id(self.rollback_id, self.runner) != self.rollback_id:
            raise Fail("ACTIVATE_ROLLBACK_IMAGE_LOST")
        if core.container_image(self.container, self.runner) is not None:
            raise Fail("ACTIVATE_CONTAINER_STILL_PRESENT")

        snap = dbsafety.snapshot(self.data_dir, self.snapshot_root, self.now, pre_version=pre_version,
                                 running_image_id=self.rollback_id,
                                 deadline=core.Deadline(cap(dbsafety.SQLITE_BUDGET_S, "ACTIVATE_OUTAGE"),
                                                        self.clock))
        self._advance("snapshotted", snapshot_dir=snap["snapshot_dir"], snapshot_sha=snap["db_sha256"],
                      tasks_before=snap["tasks_count"])
        self.details.append((ACTIVATE_SNAPSHOT, {"snapshot_dir": snap["snapshot_dir"],
                                                 "db_sha256": snap["db_sha256"],
                                                 "tasks_before": snap["tasks_count"]}))

        # T020: select, start, verify. From here `active` is the release;
        # nothing in this file ever tags it to the rollback image (INV-1).
        self._step(["docker", "tag", self.digest, self.active_tag], DOCKER_TIMEOUT,
                   "DOCKER_TAG", "ACTIVATE_TAG_ACTIVE_FAILED")
        if core.image_id(self.active_tag, self.runner) != self.digest:
            raise Fail("ACTIVATE_TAG_ACTIVE_FAILED")
        self._advance("retagged")

        self._step(self._compose_argv("up", "-d"), COMPOSE_TIMEOUT, "COMPOSE_UP", "ACTIVATE_COMPOSE_UP_FAILED")
        self._advance("started_new")

        found = core.container_image(self.container, self.runner)
        if found is None or found[0] != self.digest:
            raise Fail("ACTIVATE_CONTAINER_IMAGE_WRONG")
        by_outage = outage.remaining() < READY_BUDGET_S
        ready = core.Deadline(cap(READY_BUDGET_S, "ACTIVATE_OUTAGE"), self.clock)
        try:
            version = readiness.wait_ready(self.info_url, self.rec["release_version"], ready,
                                           runner=self.runner, sleep=self.sleep)
        except Fail as exc:
            if exc.code == "READY_TIMEOUT" and by_outage:
                raise Fail("ACTIVATE_OUTAGE_DEADLINE") from exc
            raise
        log_timeout = log_capture_timeout(outage.remaining())
        if log_timeout <= 0:
            raise Fail("ACTIVATE_LOGS_NOT_CAPTURED")
        log = readiness.capture_logs(self.popen, self.container, self.private_root,
                                     timeout=log_timeout, clock=self.clock)
        if log is None:
            raise Fail("ACTIVATE_LOGS_NOT_CAPTURED")
        migrated, counts = readiness.migration_ok(log)
        if not migrated:
            raise Fail("ACTIVATE_MIGRATION_LOG_MISSING")
        outage.check("ACTIVATE_OUTAGE")
        outage_s = int(OUTAGE_S - outage.remaining())
        self._advance("verified", outcome="success", verified_at=_stamp(self.now()),
                      outage_seconds=outage_s, verify_log=str(log))
        self.details.append((ACTIVATE_LOGS, {"private_log": log}))
        self.details.append((ACTIVATE_MIGRATION, dict(counts or {})))
        return [(ACTIVATE_VERIFIED, {"release_version": version, "config_digest": self.digest,
                                     "pre_version": pre_version, "outage_seconds": outage_s}),
                *self.details]

    # -- failure handling (T021) -------------------------------------------

    def _cleanup(self, code: str) -> None:
        """Every failure after the marker exists: logs, down, untag, marker
        ``failed``. Own 120 s budget; never tags, never starts anything."""
        budget = core.Deadline(CLEANUP_BUDGET_S, self.clock)
        reserve = CLEANUP_UNTAG_RESERVE_S
        problems: list[str] = []
        log: Path | None = None
        state = {"lock_code": "NOT_CONFIRMED", "container_code": "UNKNOWN"}

        def attempt(name: str, fn: Callable[[], None]) -> None:
            try:
                fn()
            except Fail as exc:
                problems.append(name)
                self._private(name.lower(), f"{exc.code}\n{exc.detail_private or ''}")
            except Exception:  # noqa: BLE001 - keep going: the untag must still run
                problems.append(name)
                self._private(name.lower(), traceback.format_exc())

        def logs() -> None:
            nonlocal log
            with self._within(budget, "CLEANUP_DEADLINE", reserve):
                if core.container_image(self.container, self.runner) is None:
                    return
            timeout = log_capture_timeout(budget.remaining() - reserve)
            if timeout <= 0:
                raise Fail("CLEANUP_LOGS_NOT_CAPTURED")
            log = readiness.capture_logs(self.popen, self.container, self.private_root,
                                         timeout=timeout, clock=self.clock)
            if log is None:
                raise Fail("CLEANUP_LOGS_NOT_CAPTURED")

        def down() -> None:
            with self._within(budget, "CLEANUP_DEADLINE", reserve):
                self._step(self._compose_argv("down"), COMPOSE_TIMEOUT, "COMPOSE_DOWN", "CLEANUP_DOWN_FAILED")

        def untag() -> None:
            with self._within(budget, "CLEANUP_DEADLINE"):
                self._untag_active()
            state["lock_code"] = "HELD"

        def no_container() -> None:
            with self._within(budget, "CLEANUP_DEADLINE"):
                present = core.container_image(self.container, self.runner) is not None
            state["container_code"] = "PRESENT" if present else "ABSENT"
            if present:
                raise Fail("CLEANUP_CONTAINER_PRESENT")

        self.runner = self.base_runner  # cleanup binds its own budget per step
        attempt("CLEANUP_LOGS_NOT_CAPTURED", logs)
        attempt("CLEANUP_DOWN_FAILED", down)
        attempt("CLEANUP_UNTAG_FAILED", untag)
        attempt("CLEANUP_CONTAINER_PRESENT", no_container)

        failed_phase = _NEXT.get(self.phase or "started", "verified")
        self.marker.update(outcome="failed", failed_phase=failed_phase, error=code,
                           cleanup_code=problems[0] if problems else None,
                           failure_log=str(log) if log else None, updated_at=_stamp(self.now()))
        try:
            core.marker_update(self.marker_path, self.marker)
        except Fail as exc:
            problems.append("CLEANUP_MARKER_WRITE_FAILED")
            self._private("cleanup-marker", exc.code)
        self.details.append((ACTIVATE_FAILED_AT, {"phase": self.phase, "failed_phase": failed_phase}))
        self.details.append((ACTIVATE_CLEANUP, {
            "lock_code": state["lock_code"], "container_code": state["container_code"],
            "cleanup_code": problems[0] if problems else None, "problems": len(problems),
            "private_log": log}))

    def _private(self, name: str, text: str) -> None:
        try:
            core.write_private_log(self.private_root, f"activate-{name.replace('_', '-')}", text)
        except Fail:
            pass


def main(argv: list[str] | None = None, *, runner: Callable[..., Any] = subprocess.run,
         popen: Callable[..., Any] = subprocess.Popen, clock: Callable[[], float] = time.monotonic,
         now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
         sleep: Callable[[float], None] = time.sleep, disk_usage: Callable[[str], Any] = shutil.disk_usage,
         release_path: Path | str = RELEASE_PATH, stdout: TextIO | None = None,
         stderr: TextIO | None = None) -> int:
    previous_umask = os.umask(dbsafety.PRIVATE_UMASK)
    try:
        args = list(sys.argv[1:] if argv is None else argv)
        out = stdout if stdout is not None else sys.stdout
        private_root = None  # the dry run writes nothing
        if args == ["--apply"]:
            try:
                private_root = core.load_release(release_path)["roots"]["private_logs"]
            except Fail:
                private_root = None
        holder: dict[str, Activate] = {}

        def body(mode: str) -> None:
            run = Activate(core.load_release(release_path), runner=runner, popen=popen, clock=clock,
                           now=now, sleep=sleep, disk_usage=disk_usage)
            holder["run"] = run
            lines = run.dry_run() if mode == "dry-run" else run.apply()
            for summary, fields in lines:
                core.emit(summary, out, **fields)

        try:
            rc = core.run_cli(args, prog="deploy-vikunja-release-activate.py", body=body,
                              private_root=private_root, stdout=out, stderr=stderr)
            if rc == core.EXIT_FAIL and "run" in holder:
                for summary, fields in holder["run"].details:
                    core.emit(summary, out, **fields)
            return rc
        finally:
            # The activation lock is held through cleanup and output, and is
            # released only here, as the process ends.
            if "run" in holder:
                holder["run"].release()
    finally:
        os.umask(previous_umask)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

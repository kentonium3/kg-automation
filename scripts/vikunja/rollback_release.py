#!/usr/bin/env python3
"""Operator rollback helper for the Vikunja image-archive release (#1087, WP06).

Runs ON office2 as ``claude``; the agent invokes it as::

    ssh office2-claude 'python3 /home/claude/kg-automation/scripts/vikunja/rollback_release.py \\
        --snapshot <dir> (--prepare | --finish --ack-post-cutover-writes <n>)'
    ssh office2-claude 'python3 /home/claude/kg-automation/scripts/vikunja/rollback_release.py \\
        --recover-pre-snapshot'
    ssh office2-claude 'python3 /home/claude/kg-automation/scripts/vikunja/rollback_release.py \\
        --dry-run [--snapshot <dir>]'

Design: ``kitty-specs/vikunja-image-deploy-01M65D3V/research.md`` R-7 (route),
R-11 (guard), R-12 (marker outcome ``rolled_back``), R-14 (evidence before
teardown), R-16 (output allowlist), R-17 (queue cancel), R-21 INV-1, R-24;
``analysis-report.md`` I1 (Python, not ``.sh``) and U1 (``pre_version``).

Serialisation (INV-1): ``--prepare`` and ``--finish`` each hold the
felix-deployer checkout lock (:func:`scripts.deploy.lib.deploylock.deploylock`)
from the marker gate to the end. The deployer tick holds the same lock
while it runs the ACTIVATE entrypoint; a busy lock is
``ROLLBACK_DEPLOYER_BUSY``. Because the tick, not the ACTIVATE child, holds
deploylock, both phases also hold ACTIVATE's own lifetime lock,
``<activation root>/activation.lock`` (:data:`ACTIVATION_LOCK_NAME`), which
ACTIVATE takes for its whole apply: an ACTIVATE orphaned by a dead tick
still excludes the rollback (``ROLLBACK_ACTIVATION_RUNNING``). Both refusals
come before any Docker call; the OS releases either lock when its holder
dies.

Phases:

``--dry-run``
    Reports the state only (marker, snapshot, prepare record, container,
    ``active`` tag, data-folder sidecars and sha, whether the deployer lock
    is free). Read-only docker calls, file reads and a shared lock probe:
    no write anywhere, and the lock is not taken.

``--prepare``
    capture ``docker logs`` privately -> ``compose down`` (the unit's exact
    arguments) -> untag ``active`` (tag only; the image stays) -> copy the
    failed DB files into ``failures/<UTC>-rollback/`` -> count the rows
    written after the snapshot (a conservative per-table diff, aggregates
    only, on a private copy) -> write ``<snapshot>/rollback-prepare.json``
    -> print Kent's exact restore command. The helper never runs it: Kent
    runs it through ``ssh office2-kgale``. No ``sudo`` is ever executed here.

``--finish --ack-post-cutover-writes <n>``
    refuses unless *n* equals the prepared total, then
    :func:`dbsafety.rollback_guard` (any refusal: no tag, no up) -> tag
    ``active`` to the rollback image -> ``compose up -d`` -> verify the
    running image -> readiness for the pre-cutover version (``snapshot.json``
    ``pre_version``; without it, any ``2.4.x``) -> marker outcome
    ``rolled_back`` -> print the manual-rebaseline commands and the
    queue-cancel step (hard-coded; printed only while the runbook still
    contains them verbatim).

    Any failure after the tag (up, wrong image, readiness): logs privately,
    ``compose down``, untag ``active`` (the lock is held again), marker
    unchanged, exit 1 with the code. 2.4.0 may have written the restored DB
    meanwhile, so a retry needs Kent's restore re-run first; the guard's sha
    check refuses (``GUARD_SHA_MISMATCH``) until it is.

``--recover-pre-snapshot`` (no ``--snapshot``: none exists)
    For an ACTIVATE that failed before the retag (marker outcome ``failed``,
    ``failed_phase`` in :data:`PRE_RETAG_FAILED_PHASES`, ``phase`` in
    :data:`PRE_RETAG_PHASES`): service down, ``active`` untagged, DB
    unmigrated, and no snapshot for ``--finish``. Under both locks, guards
    first (marker, no container, ``active`` untagged, rollback image present,
    a private copy of the LIVE DB with its ``-wal``/``-shm`` not migrated),
    then tag ``active`` to the rollback image, ``compose up -d``, readiness
    for the rollback version (``v2.4.0``, derived from ``rollback.ref`` as
    WP04 does), marker outcome ``rolled_back`` with
    ``recovered_pre_snapshot: 1``, and the follow-ups. INV-1 holds because
    the DB is proven unmigrated. A failure after the tag gets the
    ``--finish`` cleanup.

Output (R-16): every line is a registered summary identifier with
allowlisted values (:func:`core.emit`), or one of the fixed command
templates in :data:`_TEMPLATES` whose substituted values each pass
:func:`core.allowed_value`. Raw docker output and logs go only to private
0700 folders.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TextIO

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.deploy.lib.deploylock import LockUnavailable, deploylock  # noqa: E402
from scripts.deploy.lib.deploylock import _resolve_path as _resolve_lock_path  # noqa: E402
from scripts.deploy.vikunja_release import core, dbsafety, readiness  # noqa: E402
# Reused private building blocks (not duplicated): the descriptor-anchored
# hashing copy and folder creation, the deadline-bound SQLite connect, the
# durable JSON writer, and one bounded curl probe.
from scripts.deploy.vikunja_release.dbsafety import (  # noqa: E402
    _connect, _copy_hashed, _make_subdir, _write_new_json,
)
from scripts.deploy.vikunja_release.readiness import _probe  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_PATH = REPO_ROOT / "services" / "vikunja" / "release.json"
RUNBOOK = Path("docs") / "runbooks" / "security-baseline-ops.md"
QUEUED_MANIFEST = "deploys/queued/vikunja-release-activate.yaml"
PREPARE_RECORD = "rollback-prepare.json"
#: ACTIVATE's lifetime lock inside the activation root. WP04 defines the
#: same name; both must agree (a cross-check belongs to WP08/WP09).
ACTIVATION_LOCK_NAME = dbsafety.ACTIVATION_LOCK_NAME
PREPARE_SCHEMA_VERSION = 1

COMPOSE_TIMEOUT = 120
DOCKER_TIMEOUT = core.DOCKER_TIMEOUT
READY_BUDGET_S = 180.0
SQLITE_BUDGET_S = dbsafety.SQLITE_BUDGET_S
#: U1 fallback: without a recorded ``pre_version``, any 2.4 patch release.
_FALLBACK_VERSION_RE = re.compile(r"v?2\.4\.\d+")

USAGE = ("usage: rollback_release.py --snapshot <dir> (--prepare | --finish --ack-post-cutover-writes <n>)\n"
         "       rollback_release.py --recover-pre-snapshot\n"
         "       rollback_release.py --dry-run [--snapshot <dir>]\n")

core.register_summaries(
    "ROLLBACK_STATE", "ROLLBACK_OF_VERIFIED_ACTIVATION", "ROLLBACK_LOGS_CAPTURED",
    "ROLLBACK_STOPPED", "ROLLBACK_LOCK_HELD", "ROLLBACK_FAILED_DB_COPIED",
    "ROLLBACK_POST_CUTOVER_WRITES", "ROLLBACK_PREPARED", "ROLLBACK_KENT_RESTORE_COMMAND",
    "ROLLBACK_GUARD_PASSED", "ROLLBACK_STARTED", "ROLLBACK_READY", "ROLLBACK_FINISHED",
    "ROLLBACK_FOLLOWUP_REBASELINE", "ROLLBACK_FOLLOWUP_QUEUE", "ROLLBACK_CLEANUP",
    "ROLLBACK_RECOVER_ELIGIBILITY", "ROLLBACK_RECOVER_GUARDS_PASSED", "ROLLBACK_MARKER_DURABILITY_UNCERTAIN",
)

#: Fixed output lines. ``{name}`` slots are filled only with values that
#: pass :func:`core.allowed_value`; everything else in a line is literal.
_TEMPLATES = {
    "restore": ("sudo install -o kgale -g root -m 644 {snapshot_db} {data_db} "
                "&& sudo rm -f {data_wal} {data_shm}"),
    "restore_via": "run by Kent: ssh office2-kgale, then the command above; then --finish",
    "queue_cancel": ("queue cancel (R-17): Kent merges a reviewed commit that deletes {manifest} "
                     "and keeps Compose on the indirection with active pinned to the rollback image"),
    "rebaseline_missing": "manual rebaseline: see the Manual reset procedure in {runbook}",
    "writes_table": ("post-cutover writes: table={table_name} added={added} removed={removed} "
                     "changed={changed}"),
}

#: The two manual-reset commands (archive first, then reset), hard-coded.
#: They are printed only while the runbook still contains them verbatim;
#: otherwise the fixed pointer line is printed. Nothing read from the
#: runbook is ever printed.
REBASELINE_COMMANDS = (
    "ssh office2-claude 'cp -a /data/services/security-monitor/baselines /tmp/baselines-$(date +%s)'",
    "ssh office2-claude 'rm /data/services/security-monitor/baselines/* && sg docker -c "
    "/data/services/security-monitor/scripts/audit.sh'",
)



class Ctx:
    """Injected dependencies and resolved configuration."""

    def __init__(self, *, runner: core.Runner, popen: Callable[..., Any],
                 monotonic: Callable[[], float], utcnow: Callable[[], datetime],
                 sleep: Callable[[float], None], release: dict[str, Any], repo_root: Path,
                 out: TextIO) -> None:
        self.runner = runner
        self.popen = popen
        self.monotonic = monotonic
        self.utcnow = utcnow
        self.sleep = sleep
        self.release = release
        self.repo_root = repo_root
        self.out = out
        service = release["service"]
        self.compose_file = service["compose_file"]
        self.container = service["container"]
        self.info_url = service["info_url"]
        self.data_dir = Path(service["data_dir"])
        self.active_tag = release["tags"]["active"]
        self.release_tag = release["tags"]["release"]
        self.release_id = release["image"]["config_digest"]
        self.rollback_id = release["rollback"]["image_id"]
        self.rollback_ref = release["rollback"]["ref"]
        self.activation_root = Path(release["roots"]["activation"])
        self.failures_root = Path(release["roots"]["private_logs"])
        self.marker_path = self.activation_root / f"{release['release_version']}.json"

    #: Set once ``active`` may point at the rollback image: from then on an
    #: output failure (a broken pipe to the operator's ssh) must never stop
    #: a teardown or turn a durable success into a failure, so writes are
    #: best effort.
    best_effort = False

    def emit(self, summary: str, **fields: Any) -> None:
        try:
            core.emit(summary, self.out, **fields)
        except (OSError, ValueError):
            if not self.best_effort:
                raise

    def fixed(self, template: str, **values: Any) -> None:
        for key, value in values.items():
            if key == "table_name":
                ok = isinstance(value, str) and bool(_TABLE_NAME_RE.fullmatch(value))
            else:
                ok = core.allowed_value(value, key)
            if not ok:
                raise core.Fail("OUTPUT_VALUE_UNSAFE")
        self.write_line(_TEMPLATES[template].format(**{k: str(v) for k, v in values.items()}))

    def write_line(self, line: str) -> None:
        try:
            self.out.write(line + "\n")
            self.out.flush()
        except (OSError, ValueError):
            if not self.best_effort:
                raise

    def stamp(self) -> str:
        return self.utcnow().astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    def iso(self) -> str:
        return self.utcnow().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Docker reads and writes (each bounded; raw output never printed)
# ---------------------------------------------------------------------------


def _docker(ctx: Ctx, argv: list[str], timeout: float, step: str, code: str) -> str:
    rc, out, err = core.run(argv, timeout, step=step, runner=ctx.runner)
    if rc != 0:
        raise core.Fail(code, detail_private=err)
    return out


def _container_present(ctx: Ctx) -> bool:
    out = _docker(ctx, ["docker", "ps", "-a", "--filter", f"name=^{ctx.container}$", "-q"],
                  DOCKER_TIMEOUT, "DOCKER_PS", "DOCKER_PS_FAILED")
    return bool(out.strip())


def _compose(ctx: Ctx, *action: str) -> None:
    step = "COMPOSE_" + "_".join(a.strip("-").upper() for a in action)
    _docker(ctx, ["docker", "compose", "-f", ctx.compose_file, *action], COMPOSE_TIMEOUT,
            step, f"{step}_FAILED")


def _untag_active(ctx: Ctx) -> str | None:
    """Remove the ``active`` TAG only (R-9). Returns the ID it pointed at, or
    ``None`` when it was already absent. Refuses (``ACTIVE_TAG_UNEXPECTED``)
    unless that image keeps another known name, so ``docker image rm`` can
    only ever untag, never delete an image."""
    return dbsafety.untag_active(ctx.runner, ctx.active_tag,
                                 [(ctx.release_tag, ctx.release_id), (ctx.rollback_ref, ctx.rollback_id)],
                                 unsafe_code="ACTIVE_TAG_UNEXPECTED", failed_code="ACTIVE_UNTAG_FAILED")


# ---------------------------------------------------------------------------
# Inputs: marker, snapshot, prepare record
# ---------------------------------------------------------------------------


def _marker_gate(ctx: Ctx, snapshot_dir: Path) -> dict[str, Any]:
    """The activation marker must exist and must not already be
    ``rolled_back``. A ``success`` marker is a rollback of a verified
    activation: allowed, and stated in the output. A marker that names a
    different snapshot refuses."""
    marker = core.marker_read(ctx.marker_path)
    if marker is None:
        raise core.Fail("ROLLBACK_MARKER_MISSING")
    if marker.get("outcome") == "rolled_back":
        raise core.Fail("ROLLBACK_ALREADY_ROLLED_BACK")
    recorded = marker.get("snapshot_dir")
    if recorded is not None and Path(str(recorded)).resolve() != snapshot_dir.resolve():
        raise core.Fail("ROLLBACK_SNAPSHOT_NOT_MARKER")
    if marker.get("outcome") == "success":
        ctx.emit("ROLLBACK_OF_VERIFIED_ACTIVATION", marker=ctx.marker_path, phase=marker.get("phase"))
    return marker


def _load_snapshot(snapshot_dir: Path) -> dict[str, Any]:
    if not snapshot_dir.is_absolute() or not core.allowed_value(str(snapshot_dir), "snapshot"):
        raise core.Fail("ROLLBACK_SNAPSHOT_PATH_INVALID")
    snap = dbsafety.read_snapshot(snapshot_dir / dbsafety.SNAPSHOT_JSON)
    db = snapshot_dir / dbsafety.DB_NAME
    try:
        actual = core.sha256_file(db)
    except OSError as exc:
        raise core.Fail("ROLLBACK_SNAPSHOT_DB_UNREADABLE") from exc
    if actual != snap["db_sha256"]:
        raise core.Fail("ROLLBACK_SNAPSHOT_SHA_MISMATCH")
    return snap


def _read_prepare(snapshot_dir: Path) -> dict[str, Any] | None:
    path = snapshot_dir / PREPARE_RECORD
    if not os.path.lexists(path):
        return None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            raw = os.read(fd, 64 * 1024 + 1)
        finally:
            os.close(fd)
        data = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise core.Fail("ROLLBACK_PREPARE_RECORD_UNREADABLE") from exc
    if (not isinstance(data, dict) or data.get("schema_version") != PREPARE_SCHEMA_VERSION
            or type(data.get("post_cutover_writes")) is not int
            or not isinstance(data.get("failures_dir"), str)):
        raise core.Fail("ROLLBACK_PREPARE_RECORD_UNREADABLE")
    return data


# ---------------------------------------------------------------------------
# Post-cutover writes (T028): aggregate only, on private copies
# ---------------------------------------------------------------------------


#: Tables the release's migrations own: excluded from the write count.
#: ``migration`` is xormigrate's bookkeeping table (one row per migration);
#: the other two are the RRULE migration's backup and scratch tables.
MIGRATION_OWNED_TABLES = frozenset({"migration", "task_repeat_legacy_backup", "tasks_rrule_tmp"})
#: Columns the RRULE migration rewrites or adds, per table: never compared.
MIGRATION_OWNED_COLUMNS = {"tasks": frozenset({"repeat_after", "repeat_mode", "repeats"})}
_TABLE_NAME_RE = re.compile(r"[a-z][a-z0-9_]{0,47}")


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _tables(conn: sqlite3.Connection, schema: str) -> dict[str, list[str]]:
    names = [r[0] for r in conn.execute(
        f"SELECT name FROM {schema}.sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
    return {n: [r[1] for r in conn.execute(f"PRAGMA {schema}.table_info({_q(n)})")] for n in names}


def _count_rows(conn: sqlite3.Connection, schema: str, table: str) -> int:
    return int(conn.execute(f"SELECT count(*) FROM {schema}.{_q(table)}").fetchone()[0])


def _id_unique(conn: sqlite3.Connection, schema: str, table: str) -> bool:
    total, distinct, nulls = conn.execute(
        f"SELECT count(*), count(DISTINCT id), sum(id IS NULL) FROM {schema}.{_q(table)}").fetchone()
    return total == distinct and not nulls


def _diff_table(conn: sqlite3.Connection, table: str, columns: list[str]) -> dict[str, int]:
    """Added, removed and changed rows of *table* between ``main`` (failed)
    and ``snap`` on *columns*: keyed by ``id`` when it is a unique key on
    both sides, otherwise compared as a multiset of whole rows (where a
    change shows as one removal plus one addition)."""
    t = _q(table)
    if not columns:
        f, s = _count_rows(conn, "main", table), _count_rows(conn, "snap", table)
        return {"added": max(0, f - s), "removed": max(0, s - f), "changed": 0}
    if "id" in columns and _id_unique(conn, "main", table) and _id_unique(conn, "snap", table):
        added = conn.execute(f"SELECT count(*) FROM main.{t} f WHERE NOT EXISTS "
                             f"(SELECT 1 FROM snap.{t} s WHERE s.id = f.id)").fetchone()[0]
        removed = conn.execute(f"SELECT count(*) FROM snap.{t} s WHERE NOT EXISTS "
                               f"(SELECT 1 FROM main.{t} f WHERE f.id = s.id)").fetchone()[0]
        others = [c for c in columns if c != "id"]
        changed = 0
        if others:
            differs = " OR ".join(f"f.{_q(c)} IS NOT s.{_q(c)}" for c in others)
            changed = conn.execute(f"SELECT count(*) FROM main.{t} f JOIN snap.{t} s ON s.id = f.id "
                                   f"WHERE {differs}").fetchone()[0]
        return {"added": int(added), "removed": int(removed), "changed": int(changed)}
    cols = ", ".join(_q(c) for c in columns)
    same = " AND ".join(f"b.{_q(c)} IS a.{_q(c)}" for c in columns)
    groups = (f"WITH fa AS (SELECT {cols}, count(*) AS n FROM main.{t} GROUP BY {cols}), "
              f"sa AS (SELECT {cols}, count(*) AS n FROM snap.{t} GROUP BY {cols}) ")
    surplus = ("SELECT coalesce(sum(max(a.n - coalesce((SELECT b.n FROM {other} b WHERE " + same
               + "), 0), 0)), 0) FROM {this} a")
    added = conn.execute(groups + surplus.format(this="fa", other="sa")).fetchone()[0]
    removed = conn.execute(groups + surplus.format(this="sa", other="fa")).fetchone()[0]
    return {"added": int(added), "removed": int(removed), "changed": 0}


def _count_post_cutover_writes(failed_dir: Path, snapshot_db: Path) -> dict[str, Any]:
    """Count rows written after the snapshot, conservatively (T028).

    The failed DB (a private copy, WAL included) is compared with the
    snapshot table by table: every table in both, on the columns they share
    (minus :data:`MIGRATION_OWNED_COLUMNS`), keyed by ``id`` or as a row
    multiset. A table only in the failed DB counts all its rows as added; a
    table only in the snapshot counts all its rows as removed. Only
    :data:`MIGRATION_OWNED_TABLES` are left out. A migration that rewrites
    other data over-counts; nothing written after the snapshot is missed.
    Returns ``{"total", "tables": {name: {"added", "removed", "changed"}}}``
    with tables that have no difference left out. Aggregates only.
    """
    deadline = core.Deadline(SQLITE_BUDGET_S)
    with dbsafety._private_umask():
        scratch = tempfile.TemporaryDirectory(prefix="vikunja-rollback-count-", dir=failed_dir.parent)
    with scratch as tmp:
        fd = os.open(tmp, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for name in (dbsafety.DB_NAME, dbsafety.WAL_NAME, dbsafety.SHM_NAME):
                if os.path.lexists(failed_dir / name):
                    _copy_hashed(failed_dir / name, name, fd, Path(tmp))
        finally:
            os.close(fd)
        tables: dict[str, dict[str, int]] = {}
        try:
            with dbsafety._private_umask():
                conn = _connect(Path(tmp) / dbsafety.DB_NAME, deadline, mode="rw")
                try:
                    conn.execute("ATTACH DATABASE ? AS snap",
                                 (f"{snapshot_db.resolve().as_uri()}?mode=ro&immutable=1",))
                    failed, snap = _tables(conn, "main"), _tables(conn, "snap")
                    if "tasks" not in failed or "tasks" not in snap:
                        raise core.Fail("ROLLBACK_WRITES_UNCOUNTABLE")
                    for table in sorted(set(failed) | set(snap)):
                        if table in MIGRATION_OWNED_TABLES:
                            continue
                        if table not in snap:
                            counts = {"added": _count_rows(conn, "main", table), "removed": 0, "changed": 0}
                        elif table not in failed:
                            counts = {"added": 0, "removed": _count_rows(conn, "snap", table), "changed": 0}
                        else:
                            skip = MIGRATION_OWNED_COLUMNS.get(table, frozenset())
                            shared = [c for c in snap[table] if c in failed[table] and c not in skip]
                            counts = _diff_table(conn, table, shared)
                        if any(counts.values()):
                            tables[table] = counts
                finally:
                    conn.close()
        except sqlite3.Error as exc:
            raise core.Fail("ROLLBACK_WRITES_UNCOUNTABLE", detail_private=f"{type(exc).__name__}: {exc}") from exc
    total = sum(sum(c.values()) for c in tables.values())
    return {"total": total, "tables": tables}


# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _activation_lock(activation_root: Path):
    """Hold ACTIVATE's own lock, ``<activation root>/activation.lock``.

    ACTIVATE (WP04) takes this exclusive flock itself, for its whole apply,
    before it creates the marker. A flock belongs to the process holding the
    descriptor, so an ACTIVATE orphaned by a dead deployer tick still holds
    it (deploylock alone would be free then), and a crashed ACTIVATE releases
    it. Non-blocking: a held lock is ``ROLLBACK_ACTIVATION_RUNNING``.

    The file is opened relative to the verified activation-root descriptor
    (:func:`dbsafety.open_private_root`), ``O_CREAT|O_NOFOLLOW``, mode 0600.
    """
    root_fd = dbsafety.open_private_root(activation_root, code="ACTIVATION_ROOT")
    try:
        fd = dbsafety.take_activation_lock(root_fd, busy_code="ROLLBACK_ACTIVATION_RUNNING",
                                           unsafe_code="ACTIVATION_LOCK_UNSAFE")
    finally:
        os.close(root_fd)
    try:
        yield
    finally:
        os.close(fd)  # closing releases the flock


def _lock_free(lock_path: Path | None) -> int:
    """1 when the deployer checkout lock is free, 0 when held. A shared,
    non-blocking probe on an existing lock file; nothing is created."""
    return _probe_lock(_resolve_lock_path(lock_path))


def _probe_lock(path: Path) -> int:
    """1 when no process holds an exclusive flock on *path*, else 0. A
    shared, non-blocking probe; an absent file is free and is not created."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return 1
    try:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except OSError:
        return 0
    finally:
        os.close(fd)  # closing releases the probe lock
    return 1


def dry_run(ctx: Ctx, snapshot_dir: Path | None, lock_path: Path | None = None) -> None:
    """State only. Read-only docker calls and reads; nothing is written, and
    the locks are only probed, not taken. Without ``--snapshot`` the
    snapshot fields are ``-``. Also reports whether
    ``--recover-pre-snapshot`` is eligible (``recover_code`` is the first
    refusal; the DB migration check runs only in the real mode)."""
    marker = core.marker_read(ctx.marker_path)
    snap = _load_snapshot(snapshot_dir) if snapshot_dir is not None else {"db_sha256": None}
    prepared = _read_prepare(snapshot_dir) if snapshot_dir is not None else None
    data_sha = None
    if os.path.lexists(ctx.data_dir / dbsafety.DB_NAME):
        try:
            data_sha = core.sha256_file(ctx.data_dir / dbsafety.DB_NAME)
        except OSError:
            data_sha = None
    sidecars = sum(os.path.lexists(ctx.data_dir / n) for n in (dbsafety.WAL_NAME, dbsafety.SHM_NAME))
    running = core.container_image(ctx.container, runner=ctx.runner)
    ctx.emit("ROLLBACK_STATE",
             marker_phase=None if marker is None else marker.get("phase"),
             marker_outcome=None if marker is None else marker.get("outcome"),
             snapshot_sha=snap["db_sha256"], pre_version=snap.get("pre_version"),
             prepared=int(prepared is not None),
             post_cutover_writes=None if prepared is None else prepared["post_cutover_writes"],
             container_image=None if running is None else running[0],
             active=core.image_id(ctx.active_tag, runner=ctx.runner),
             data_sha=data_sha,
             data_matches_snapshot=None if snap["db_sha256"] is None else int(data_sha == snap["db_sha256"]),
             sidecars=sidecars, deployer_lock_free=_lock_free(lock_path),
             activation_lock_free=_probe_lock(ctx.activation_root / ACTIVATION_LOCK_NAME))
    recover_code = recover_eligibility(ctx)
    # Preliminary: guards 1-6 (marker, container, active, rollback image)
    # only. The DB copy and migration inspection run only in the real mode,
    # and the locks are taken only then; their probes are reported beside.
    ctx.emit("ROLLBACK_RECOVER_ELIGIBILITY", prelim_eligible=int(recover_code is None), checks_run=6,
             recover_code=recover_code, db_present=int(os.path.lexists(ctx.data_dir / dbsafety.DB_NAME)),
             db_migration_checked=0, deployer_lock_free=_lock_free(lock_path),
             activation_lock_free=_probe_lock(ctx.activation_root / ACTIVATION_LOCK_NAME))


def prepare(ctx: Ctx, snapshot_dir: Path) -> None:
    _marker_gate(ctx, snapshot_dir)
    snap = _load_snapshot(snapshot_dir)
    if _read_prepare(snapshot_dir) is not None:
        raise core.Fail("ROLLBACK_ALREADY_PREPARED")

    root_fd = dbsafety.open_private_root(ctx.failures_root, code="FAILURES_ROOT")
    try:
        name = f"{ctx.stamp()}-rollback"
        try:
            os.close(_make_subdir(name, root_fd))
        except FileExistsError as exc:
            raise core.Fail("FAILURES_DIR_EXISTS") from exc
    finally:
        os.close(root_fd)
    failed_dir = ctx.failures_root / name

    # R-14: evidence before teardown; a failed capture never blocks the stop.
    log = readiness.capture_logs(ctx.popen, ctx.container, failed_dir, clock=ctx.monotonic)
    ctx.emit("ROLLBACK_LOGS_CAPTURED", captured=int(log is not None), private_log=log)

    _compose(ctx, "down")
    if _container_present(ctx):
        raise core.Fail("ROLLBACK_CONTAINER_STILL_PRESENT")
    ctx.emit("ROLLBACK_STOPPED", container=0)
    previous = _untag_active(ctx)
    ctx.emit("ROLLBACK_LOCK_HELD", active=None, was=previous)

    run_fd = dbsafety.open_private_root(failed_dir, code="FAILURES_ROOT")
    try:
        copied = 0
        for fname in (dbsafety.DB_NAME, dbsafety.WAL_NAME, dbsafety.SHM_NAME):
            src = ctx.data_dir / fname
            if fname != dbsafety.DB_NAME and not os.path.lexists(src):
                continue
            try:
                _copy_hashed(src, fname, run_fd, failed_dir, final_mode=0o400)
            except FileNotFoundError as exc:
                raise core.Fail("ROLLBACK_DATA_DB_MISSING") from exc
            copied += 1
        os.fsync(run_fd)
    finally:
        os.close(run_fd)
    ctx.emit("ROLLBACK_FAILED_DB_COPIED", failures_dir=failed_dir, files=copied)

    writes = _count_post_cutover_writes(failed_dir, snapshot_dir / dbsafety.DB_NAME)
    ctx.emit("ROLLBACK_POST_CUTOVER_WRITES", count=writes["total"], tables=len(writes["tables"]),
             snapshot_at=snap.get("created_at"))
    recorded: dict[str, dict[str, int]] = {}
    for table, counts in sorted(writes["tables"].items()):
        shown = table if _TABLE_NAME_RE.fullmatch(table) else "other"
        ctx.fixed("writes_table", table_name=shown, **counts)
        merged = recorded.setdefault(shown, {"added": 0, "removed": 0, "changed": 0})
        for key, value in counts.items():
            merged[key] += value

    _write_new_json(snapshot_dir / PREPARE_RECORD, {
        "schema_version": PREPARE_SCHEMA_VERSION,
        "prepared_at": ctx.iso(),
        "failures_dir": str(failed_dir),
        "post_cutover_writes": writes["total"],
        "tables": recorded,
    })
    ctx.emit("ROLLBACK_PREPARED", snapshot=snapshot_dir, failures_dir=failed_dir,
             post_cutover_writes=writes["total"])
    ctx.emit("ROLLBACK_KENT_RESTORE_COMMAND", snapshot_sha=snap["db_sha256"])
    ctx.fixed("restore", snapshot_db=snapshot_dir / dbsafety.DB_NAME,
              data_db=ctx.data_dir / dbsafety.DB_NAME,
              data_wal=ctx.data_dir / dbsafety.WAL_NAME,
              data_shm=ctx.data_dir / dbsafety.SHM_NAME)
    ctx.fixed("restore_via")


def _wait_pre_version(ctx: Ctx, pre_version: str | None) -> str:
    deadline = core.Deadline(READY_BUDGET_S, clock=ctx.monotonic)
    if pre_version is not None:
        return readiness.wait_ready(ctx.info_url, pre_version, deadline, runner=ctx.runner, sleep=ctx.sleep)
    # U1 fallback: no recorded version; require the 2.4 major.minor.
    while True:
        remaining = deadline.remaining()
        if remaining < 1.0:
            raise core.Fail("READY_TIMEOUT")
        kind, version = _probe(ctx.info_url, max(1, min(5, int(remaining))), ctx.runner)
        if deadline.remaining() <= 0:
            raise core.Fail("READY_TIMEOUT")
        if kind == "ok":
            if version is not None and _FALLBACK_VERSION_RE.fullmatch(version):
                return version
            raise core.Fail("READY_WRONG_VERSION")
        ctx.sleep(min(readiness.POLL_INTERVAL_S, deadline.remaining()))


def _runbook_confirms(ctx: Ctx) -> bool:
    """True while the runbook still contains both :data:`REBASELINE_COMMANDS`
    verbatim. The runbook is only checked, never echoed."""
    try:
        text = (ctx.repo_root / RUNBOOK).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return all(cmd in text for cmd in REBASELINE_COMMANDS)


def _cleanup_after_start(ctx: Ctx, failures_dir: Path) -> None:
    """R-14 after a failure past the tag: logs privately (a file, never the
    operator's stream), then ``compose down``, then untag ``active``, and
    only then report. Every step is bounded and best effort, and no output
    failure can stop the teardown. The marker is left unchanged. A retry
    needs Kent's restore again whenever 2.4.0 may have written the DB, which
    the guard's sha check enforces."""
    ctx.best_effort = True
    log = readiness.capture_logs(ctx.popen, ctx.container, failures_dir, clock=ctx.monotonic)
    down_code = untag_code = None
    try:
        _compose(ctx, "down")
    except Exception as exc:  # noqa: BLE001 - the untag must still run
        down_code = exc.code if isinstance(exc, core.Fail) else "CLEANUP_DOWN_ERROR"
    try:
        _untag_active(ctx)
    except Exception as exc:  # noqa: BLE001
        untag_code = exc.code if isinstance(exc, core.Fail) else "CLEANUP_UNTAG_ERROR"
    try:
        present = int(_container_present(ctx))
        active = core.image_id(ctx.active_tag, runner=ctx.runner)
    except Exception as exc:  # noqa: BLE001
        present, active = -1, None
        untag_code = untag_code or (exc.code if isinstance(exc, core.Fail) else "CLEANUP_CHECK_ERROR")
    ctx.emit("ROLLBACK_LOGS_CAPTURED", captured=int(log is not None), private_log=log)
    ctx.emit("ROLLBACK_CLEANUP", container=present, active=active, down_code=down_code,
             untag_code=untag_code)


class MarkerDurabilityUncertain(core.Fail):
    """The ``rolled_back`` marker replace landed but its durability step
    failed: the service is verified up and the marker reads ``rolled_back``,
    so nothing may be torn down."""


def _persist_rolled_back(ctx: Ctx, data: dict[str, Any]) -> None:
    """Write the final marker. On failure, re-read it: a marker that already
    reads ``rolled_back`` means the replace landed (only the directory
    fsync failed), so raise :class:`MarkerDurabilityUncertain` and keep the
    service; otherwise (old content, unreadable) re-raise for cleanup."""
    try:
        core.marker_update(ctx.marker_path, data)
    except Exception as exc:
        try:
            current = core.marker_read(ctx.marker_path)
        except Exception:  # noqa: BLE001 - unreadable: treat as not written
            current = None
        if current is not None and current.get("outcome") == "rolled_back":
            raise MarkerDurabilityUncertain(
                "MARKER_DURABILITY_UNCERTAIN",
                detail_private=f"{type(exc).__name__}: {getattr(exc, 'code', exc)}") from exc
        raise


def _start_and_record(ctx: Ctx, marker: dict[str, Any], updates: dict[str, Any], failures_dir: Path,
                      expected: str | None) -> tuple[str, str]:
    """Tag ``active`` to the rollback image, ``compose up -d``, verify the
    image and readiness (*expected*, or any 2.4.x when ``None``), then make
    the ``rolled_back`` marker durable. Returns ``(image id, version)``.

    Any failure in here gets :func:`_cleanup_after_start`, except
    :class:`MarkerDurabilityUncertain`, where the service is verified up
    and the marker already reads ``rolled_back``: it is kept running."""
    ctx.best_effort = True
    running_id: str | None = None
    version: str | None = None
    try:
        _docker(ctx, ["docker", "tag", ctx.rollback_id, ctx.active_tag], DOCKER_TIMEOUT, "DOCKER_TAG",
                "ACTIVE_TAG_FAILED")
        if core.image_id(ctx.active_tag, runner=ctx.runner) != ctx.rollback_id:
            raise core.Fail("ACTIVE_TAG_FAILED")
        _compose(ctx, "up", "-d")
        running = core.container_image(ctx.container, runner=ctx.runner)
        if running is None or running[0] != ctx.rollback_id:
            raise core.Fail("ROLLBACK_WRONG_IMAGE_RUNNING")
        running_id = running[0]
        ctx.emit("ROLLBACK_STARTED", container_image=running_id)
        version = _wait_pre_version(ctx, expected)
        ctx.emit("ROLLBACK_READY", version=version)
        _persist_rolled_back(ctx, {**marker, **updates, "outcome": "rolled_back", "rolled_back_at": ctx.iso()})
    except MarkerDurabilityUncertain:
        ctx.emit("ROLLBACK_MARKER_DURABILITY_UNCERTAIN", service_up=1, version=version,
                 container_image=running_id, marker=ctx.marker_path, marker_outcome="rolled_back")
        raise
    except Exception:
        _cleanup_after_start(ctx, failures_dir)
        raise
    return running_id, version


def finish(ctx: Ctx, snapshot_dir: Path, ack: int) -> None:
    marker = _marker_gate(ctx, snapshot_dir)
    snap = _load_snapshot(snapshot_dir)
    prepared = _read_prepare(snapshot_dir)
    if prepared is None:
        raise core.Fail("ROLLBACK_NOT_PREPARED")
    if ack != prepared["post_cutover_writes"]:
        raise core.Fail("ROLLBACK_ACK_MISMATCH")

    guard = dbsafety.rollback_guard(ctx.runner, ctx.data_dir, snapshot_dir / dbsafety.SNAPSHOT_JSON,
                                    container=ctx.container, active_tag=ctx.active_tag)
    ctx.emit("ROLLBACK_GUARD_PASSED", db_sha256=guard["db_sha256"])

    # INV-1: only now may active point at the rollback image.
    if core.image_id(ctx.rollback_ref, runner=ctx.runner) != ctx.rollback_id:
        raise core.Fail("ROLLBACK_IMAGE_MISSING")
    # Success only once the outcome is durable (see _start_and_record).
    running_id, version = _start_and_record(ctx, marker, {"rollback_snapshot": str(snapshot_dir)},
                                            Path(prepared["failures_dir"]), snap.get("pre_version"))
    ctx.emit("ROLLBACK_FINISHED", marker=ctx.marker_path, outcome="rolled_back",
             container_image=running_id, version=version)

    _followups(ctx)


def _followups(ctx: Ctx) -> None:
    """T029: the manual rebaseline (hard-coded, only while the runbook
    confirms it) and the queue-cancel step (R-17)."""
    confirmed = _runbook_confirms(ctx)
    ctx.emit("ROLLBACK_FOLLOWUP_REBASELINE", runbook=ctx.repo_root / RUNBOOK,
             commands=len(REBASELINE_COMMANDS) if confirmed else 0)
    if confirmed:
        for line in REBASELINE_COMMANDS:
            ctx.write_line(line)
    else:
        ctx.fixed("rebaseline_missing", runbook=ctx.repo_root / RUNBOOK)
    ctx.emit("ROLLBACK_FOLLOWUP_QUEUE", manifest_code="ACTIVATE_ROLLED_BACK_REMOVE_QUEUED_MANIFEST")
    ctx.fixed("queue_cancel", manifest=ctx.repo_root / QUEUED_MANIFEST)


# ---------------------------------------------------------------------------
# --recover-pre-snapshot: an ACTIVATE that failed before any retag
# ---------------------------------------------------------------------------

#: WP04 (``deploy-vikunja-release-activate.py``) records ``failed_phase =
#: _NEXT[phase]``: the phase it was ENTERING when it failed, where ``_NEXT``
#: is started->stopped->snapshotted->retagged->started_new->verified. Before
#: ``retagged`` the release was never tagged to ``active`` and never started,
#: so the DB is unmigrated (re-proved below on a private copy anyway).
#: ``started`` is included defensively; WP04 itself never writes it.
PRE_RETAG_FAILED_PHASES = frozenset({"started", "stopped", "snapshotted"})
#: The last phase such a marker may have reached (``phase``).
PRE_RETAG_PHASES = frozenset({"started", "stopped"})


def rollback_version(release: dict[str, Any]) -> str:
    """The version ``/api/v1/info`` reports for the rollback image, derived
    from its reviewed reference exactly as WP04 does
    (``vikunja/vikunja:2.4.0`` -> ``v2.4.0``)."""
    tag = release["rollback"]["ref"].rsplit(":", 1)[1]
    return tag if tag.startswith("v") else f"v{tag}"


def _recover_marker_code(marker: dict[str, Any] | None) -> str | None:
    if marker is None:
        return "RECOVER_MARKER_MISSING"
    if marker.get("outcome") != "failed":
        return "RECOVER_MARKER_NOT_FAILED"
    if marker.get("failed_phase") not in PRE_RETAG_FAILED_PHASES or marker.get("phase") not in PRE_RETAG_PHASES:
        return "RECOVER_MARKER_PAST_RETAG"
    return None


def _recover_state_code(ctx: Ctx) -> str | None:
    """The read-only docker guards, in order; ``None`` when all hold."""
    if _container_present(ctx):
        return "RECOVER_CONTAINER_PRESENT"
    if core.image_id(ctx.active_tag, runner=ctx.runner) is not None:
        return "RECOVER_LOCK_NOT_HELD"
    if core.image_id(ctx.rollback_ref, runner=ctx.runner) != ctx.rollback_id:
        return "RECOVER_ROLLBACK_IMAGE_MISSING"
    return None


def recover_eligibility(ctx: Ctx) -> str | None:
    """For ``--dry-run``: the first refusal code, or ``None`` when every
    read-only guard holds. The migration check needs a private copy, so it
    runs only in the real mode, so a ``None`` here is a PRELIMINARY yes."""
    try:
        marker = core.marker_read(ctx.marker_path)
    except core.Fail as exc:
        return exc.code
    return _recover_marker_code(marker) or _recover_state_code(ctx)


def recover_pre_snapshot(ctx: Ctx) -> None:
    """Bring 2.4.0 back after an ACTIVATE that failed before any retag.

    Guards, all before any mutation: the marker is ``failed`` before the
    retag; no container; ``active`` untagged; the rollback image present;
    a private copy of the LIVE DB (with its ``-wal``/``-shm``) is not
    migrated. Then tag ``active`` to the rollback image, ``compose up -d``,
    readiness for the rollback version, and marker outcome ``rolled_back``
    with ``recovered_pre_snapshot``. A failure after the tag gets the same
    cleanup as ``--finish``; the marker is then unchanged.
    """
    marker = core.marker_read(ctx.marker_path)
    code = _recover_marker_code(marker)
    if code is not None:
        raise core.Fail(code)
    code = _recover_state_code(ctx)
    if code is not None:
        raise core.Fail(code)

    root_fd = dbsafety.open_private_root(ctx.failures_root, code="FAILURES_ROOT")
    try:
        name = f"{ctx.stamp()}-recover"
        try:
            run_fd = _make_subdir(name, root_fd)
        except FileExistsError as exc:
            raise core.Fail("FAILURES_DIR_EXISTS") from exc
    finally:
        os.close(root_fd)
    run_dir = ctx.failures_root / name
    try:
        if not os.path.lexists(ctx.data_dir / dbsafety.DB_NAME):
            raise core.Fail("RECOVER_DATA_DB_MISSING")
        try:
            for fname in (dbsafety.DB_NAME, dbsafety.WAL_NAME, dbsafety.SHM_NAME):
                if fname == dbsafety.DB_NAME or os.path.lexists(ctx.data_dir / fname):
                    _copy_hashed(ctx.data_dir / fname, fname, run_fd, run_dir)
            os.fsync(run_fd)
        except OSError as exc:
            raise core.Fail("RECOVER_DB_COPY_FAILED", detail_private=f"{type(exc).__name__}: {exc}") from exc
    finally:
        os.close(run_fd)
    if dbsafety.is_migrated(run_dir / dbsafety.DB_NAME):
        raise core.Fail("RECOVER_DB_MIGRATED")
    ctx.emit("ROLLBACK_RECOVER_GUARDS_PASSED", marker=ctx.marker_path, failed_phase=marker["failed_phase"],
             private_copy=run_dir)

    running_id, version = _start_and_record(ctx, marker, {"recovered_pre_snapshot": 1}, run_dir,
                                            rollback_version(ctx.release))
    ctx.emit("ROLLBACK_FINISHED", marker=ctx.marker_path, outcome="rolled_back",
             container_image=running_id, version=version, recovered_pre_snapshot=1)
    _followups(ctx)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse(argv: list[str]) -> tuple[str, Path | None, int | None] | None:
    """``--dry-run [--snapshot <dir>]``, ``--snapshot <dir> --prepare``,
    ``--snapshot <dir> --finish --ack-post-cutover-writes <n>``, or
    ``--recover-pre-snapshot`` (no snapshot: none exists)."""
    snapshot: str | None = None
    mode: str | None = None
    ack: int | None = None
    it = iter(argv)
    for token in it:
        if token == "--snapshot" and snapshot is None:
            snapshot = next(it, None)
            if snapshot is None:
                return None
        elif token in ("--dry-run", "--prepare", "--finish", "--recover-pre-snapshot") and mode is None:
            mode = token[2:]
        elif token == "--ack-post-cutover-writes" and ack is None:
            value = next(it, None)
            if value is None or not value.isdigit() or len(value) > 9:
                return None
            ack = int(value)
        else:
            return None
    if mode is None or (snapshot is not None and not snapshot.startswith("/")):
        return None
    if mode in ("prepare", "finish") and snapshot is None:
        return None
    if mode == "recover-pre-snapshot" and snapshot is not None:
        return None
    if (mode == "finish") != (ack is not None):
        return None
    return mode, None if snapshot is None else Path(snapshot), ack


def main(argv: list[str] | None = None, *, runner: core.Runner = subprocess.run,
         popen: Callable[..., Any] = subprocess.Popen, monotonic: Callable[[], float] = time.monotonic,
         utcnow: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
         sleep: Callable[[float], None] = time.sleep, release_path: Path = RELEASE_PATH,
         repo_root: Path = REPO_ROOT, stdout: TextIO | None = None, stderr: TextIO | None = None,
         lock_path: Path | None = None, lock_timeout_s: float = 5.0) -> int:
    os.umask(0o077)
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    parsed = _parse(list(sys.argv[1:] if argv is None else argv))
    if parsed is None:
        err.write(USAGE)
        err.flush()
        return core.EXIT_USAGE
    mode, snapshot_dir, ack = parsed
    private_root: Path | None = None
    try:
        release = core.load_release(release_path)
        ctx = Ctx(runner=runner, popen=popen, monotonic=monotonic, utcnow=utcnow, sleep=sleep,
                  release=release, repo_root=repo_root, out=out)
        private_root = ctx.failures_root
        if mode == "dry-run":
            private_root = None  # the dry run writes nothing, not even a failure log
            dry_run(ctx, snapshot_dir, lock_path)
        else:
            # The felix-deployer tick holds this lock while it runs ACTIVATE,
            # so holding it from the marker gate to the end serialises a
            # rollback against any activation (INV-1). The OS releases it if
            # either holder dies.
            with contextlib.ExitStack() as stack:
                try:
                    stack.enter_context(deploylock(path=lock_path, timeout_s=lock_timeout_s))
                except LockUnavailable as exc:
                    raise core.Fail("ROLLBACK_DEPLOYER_BUSY") from exc
                except OSError as exc:
                    raise core.Fail("ROLLBACK_DEPLOYER_LOCK_ERROR",
                                    detail_private=f"{type(exc).__name__}: {exc}") from exc
                # deploylock alone is not enough: the tick holds it, not the
                # ACTIVATE child, so an orphaned ACTIVATE would not hold it.
                stack.enter_context(_activation_lock(ctx.activation_root))
                if mode == "prepare":
                    prepare(ctx, snapshot_dir)
                elif mode == "finish":
                    finish(ctx, snapshot_dir, ack)
                else:
                    recover_pre_snapshot(ctx)
    except core.Fail as exc:
        log = _private_detail(private_root, "rollback-fail", exc.detail_private)
        _final_line(out, code=exc.code, private_log=log)
        return core.EXIT_FAIL
    except Exception:  # noqa: BLE001 - never echo an unexpected message
        log = _private_detail(private_root, "rollback-internal-error", traceback.format_exc())
        _final_line(out, code="INTERNAL_ERROR", private_log=log)
        return core.EXIT_FAIL
    return core.EXIT_OK


def _final_line(out: TextIO, **fields: Any) -> None:
    """The closing ``FAILED`` line, best effort: a broken stream must not
    replace the exit code with a traceback."""
    try:
        core.emit("FAILED", out, **fields)
    except (OSError, ValueError):
        pass


def _private_detail(root: Path | None, name: str, text: str | None) -> Path | None:
    if root is None or not text:
        return None
    try:
        dbsafety.prepare_private_root(root, code="FAILURES_ROOT")
        return core.write_private_log(root, name, text)
    except Exception:  # noqa: BLE001 - best effort
        return None


if __name__ == "__main__":
    sys.exit(main())

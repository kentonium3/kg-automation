#!/usr/bin/env python3
"""Verify a stable post-upgrade copy against the durable private gate receipt."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.deploy.vikunja_release import baseline, core, dbsafety
from scripts.vikunja.preflight_release_baseline import _remove_private_copy, _termination_handlers

DEFAULT_RELEASE = core.REPO_ROOT / "services/vikunja/release.json"
EVIDENCE_NAME = "upgrade-acceptance.json"


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "ACCEPTANCE_USAGE\n")


@contextlib.contextmanager
def _private_directory(path):
    """Open existing private evidence without following ancestor symlinks."""
    path = Path(path).absolute()
    if ".." in path.parts:
        raise ValueError("parent traversal")
    with contextlib.ExitStack() as stack:
        fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        stack.callback(os.close, fd)
        for part in path.parts[1:]:
            fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            stack.callback(os.close, fd)
        info = os.fstat(fd)
        if stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.geteuid():
            raise ValueError("private directory required")
        yield fd


def _read_receipt(parent):
    fd = dbsafety._open_source("baseline.json", dir_fd=parent)
    try:
        info = os.fstat(fd)
        if stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.geteuid():
            raise ValueError("private receipt required")
        with os.fdopen(os.dup(fd), "rb") as source:
            # Subscription preservation evidence may exceed the data-free baseline limit.
            raw = source.read()
    finally:
        os.close(fd)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)


def _write_evidence(parent, value):
    fd = os.open(EVIDENCE_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=parent)
    try:
        os.fchmod(fd, 0o600)
        payload = (json.dumps(value, sort_keys=True, separators=(",", ":"),
                              allow_nan=False) + "\n").encode("utf-8")
        dbsafety._write_all(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(parent)


@contextlib.contextmanager
def _post_database(post_copy):
    """Consolidate WAL bytes only in disposable private storage."""
    post_copy = Path(post_copy)
    wal = Path(str(post_copy) + "-wal")
    if not os.path.lexists(wal) or wal.stat().st_size == 0:
        yield post_copy
        return
    scratch = Path(tempfile.mkdtemp(prefix="vikunja-acceptance-"))
    try:
        source = scratch / "source"
        source.mkdir(mode=0o700)
        fd = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            dbsafety._copy_hashed(post_copy, dbsafety.DB_NAME, fd, source)
            dbsafety._copy_hashed(wal, dbsafety.DB_NAME + "-wal", fd, source)
        finally:
            os.close(fd)
        snap = dbsafety.snapshot(source, scratch / "consolidated")
        yield Path(snap["db_path"])
    finally:
        _remove_private_copy(scratch, "ACCEPTANCE_CLEANUP_FAILED")


def verify(snapshot_directory, post_copy, *, release_path=DEFAULT_RELEASE,
           repository_root=core.REPO_ROOT) -> dict[str, bool]:
    try:
        return _verify(snapshot_directory, post_copy, release_path=release_path,
                       repository_root=repository_root)
    except core.Fail as exc:
        allowed = {"ACCEPTANCE_RECEIPT_FAILED", "ACCEPTANCE_COMPUTE_FAILED",
                   "ACCEPTANCE_EVIDENCE_WRITE_FAILED", "ACCEPTANCE_CLEANUP_FAILED"}
        raise core.Fail(exc.code if exc.code in allowed else "ACCEPTANCE_FAILED") from None
    except (Exception, KeyboardInterrupt):
        raise core.Fail("ACCEPTANCE_FAILED") from None


def _verify(snapshot_directory, post_copy, *, release_path, repository_root) -> dict[str, bool]:
    record = core.load_release(release_path)
    facts = baseline.load_bound(record, repository_root)
    folder = Path(snapshot_directory).absolute()
    with _private_directory(folder) as parent:
        try:
            receipt = _read_receipt(parent)
            snap = dbsafety.read_snapshot(folder / "snapshot.json")
            snapshot_db = folder / dbsafety.DB_NAME
            fd = dbsafety._open_source(snapshot_db)
            try:
                digest = dbsafety._sha256_fd(fd)
            finally:
                os.close(fd)
            before = baseline.compare(snapshot_db, facts)
            if (not baseline._receipt_valid(receipt)
                    or receipt["baseline"] != facts
                    or snap.get("snapshot_dir") != str(folder)
                    or snap.get("db_path") != str(snapshot_db)
                    or receipt["snapshot_sha256"] != digest or snap["db_sha256"] != digest
                    or snap.get("pre_version") != baseline.previous_version(record)
                    or snap.get("running_image_id") != record["rollback"]["image_id"]
                    or receipt["baseline_sha256"] != record["baseline"]["sha256"]
                    or receipt["release_version"] != record["release_version"]
                    or receipt["config_digest"] != record["image"]["config_digest"]
                    or before.code is not None or before.aggregates != receipt["aggregates"]
                    or snap.get("tasks_count") != receipt["aggregates"]["task_count"]):
                raise ValueError("receipt binding")
        except Exception:
            raise core.Fail("ACCEPTANCE_RECEIPT_FAILED") from None

        try:
            with _post_database(post_copy) as database, baseline._connect(database, None) as conn:
                integrity = conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
                ids = baseline.migration_ids(conn)
                schema = baseline.schema_identity(conn)
                observed = baseline.aggregates(conn)
            expected = receipt["aggregates"]
            retained = {row[0]: row for row in observed["existing_subscriptions"]}
            checks = {
                "MIGRATIONS": ids == sorted(facts["pre_upgrade_migration_ids"] + facts["added_migration_ids"]),
                "SCHEMA": schema == facts["schema_identity"]["target"],
                "TASKS": observed["task_count"] == expected["task_count"],
                "REPEATS": all(observed[key] == expected[key] for key in ("repeat_count", "repeat_hash")),
                "INTEGRITY": integrity,
                "SUBSCRIPTION_TOTAL": observed["task_subscription_rows"] == expected["expected_task_subscription_rows"],
                "ELIGIBLE_PAIRS": observed["missing_eligible_pairs"] == 0,
                "DUPLICATES": observed["duplicate_excess"] == expected["duplicate_excess"],
                "EXISTING_SUBSCRIPTIONS": all(retained.get(row[0]) == row for row in expected["existing_subscriptions"]),
            }
        except core.Fail as exc:
            if exc.code == "ACCEPTANCE_CLEANUP_FAILED":
                raise
            raise core.Fail("ACCEPTANCE_COMPUTE_FAILED") from None
        except Exception:
            raise core.Fail("ACCEPTANCE_COMPUTE_FAILED") from None
        try:
            aggregates = {key: value for key, value in observed.items()
                          if key != "existing_subscriptions"}
            _write_evidence(parent, {"schema_version": 1, "checks": checks, "aggregates": aggregates})
        except Exception:
            raise core.Fail("ACCEPTANCE_EVIDENCE_WRITE_FAILED") from None
    return checks


@_termination_handlers()
def main(argv=None, *, release_path=DEFAULT_RELEASE, repository_root=core.REPO_ROOT) -> int:
    parser = _Parser(description=__doc__)
    parser.add_argument("snapshot_directory")
    parser.add_argument("post_copy")
    args = parser.parse_args(argv)
    try:
        checks = verify(args.snapshot_directory, args.post_copy, release_path=release_path,
                        repository_root=repository_root)
    except core.Fail as exc:
        codes = {"ACCEPTANCE_RECEIPT_FAILED", "ACCEPTANCE_COMPUTE_FAILED",
                 "ACCEPTANCE_EVIDENCE_WRITE_FAILED", "ACCEPTANCE_CLEANUP_FAILED"}
        print(exc.code if exc.code in codes else "ACCEPTANCE_FAILED")
        return 1
    except (Exception, KeyboardInterrupt):
        print("ACCEPTANCE_FAILED")
        return 1
    for name, passed in checks.items():
        print(f"ACCEPTANCE_{name}_{'PASS' if passed else 'FAIL'}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())

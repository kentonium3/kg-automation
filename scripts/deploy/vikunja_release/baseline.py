"""Data-free qualification and private, deadline-bound snapshot evidence.

All database arguments are consolidated private copies. Nothing here prints
evidence or registers it as an installed file. Consumers must keep aggregates
and receipts private; only Result.code is suitable for public output.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import sqlite3
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import core

ALGORITHM = "sqlite-master-sha256-v1"
MAX_BASELINE_BYTES = 1024 * 1024
_HEX = re.compile(r"[0-9a-f]{64}")
_CONFIG = re.compile(r"sha256:[0-9a-f]{64}")
_ID = re.compile(r"[0-9]+")
_PRE_ID = re.compile(r"[0-9]+|SCHEMA_INIT")
_FIELDS = {"schema_version", "previous_version", "previous_image_config",
           "pre_upgrade_migration_ids", "added_migration_ids", "schema_identity"}


def _check(deadline: core.Deadline | None) -> None:
    if deadline is not None:
        deadline.check("GATE")


def _json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def previous_version(record: dict[str, Any]) -> str:
    """Use exactly the ref-to-version semantics of ACTIVATE and rollback."""
    tag = record["rollback"]["ref"].rsplit(":", 1)[1]
    return tag if tag.startswith("v") else f"v{tag}"


def _ids(value: Any, *, allow_schema_init: bool = False) -> bool:
    pattern = _PRE_ID if allow_schema_init else _ID
    return (isinstance(value, list) and all(isinstance(x, str) and pattern.fullmatch(x) for x in value)
            and value == sorted(set(value)))


def validate(value: Any) -> bool:
    """The exact committed schema contains no private evidence."""
    if not isinstance(value, dict) or set(value) != _FIELDS:
        return False
    schema = value["schema_identity"]
    return bool(
        type(value["schema_version"]) is int and value["schema_version"] == 1
        and isinstance(value["previous_version"], str)
        and core._VERSION_RE.fullmatch(value["previous_version"])
        and isinstance(value["previous_image_config"], str)
        and _CONFIG.fullmatch(value["previous_image_config"])
        and _ids(value["pre_upgrade_migration_ids"], allow_schema_init=True)
        and _ids(value["added_migration_ids"])
        and not set(value["pre_upgrade_migration_ids"]) & set(value["added_migration_ids"])
        and isinstance(schema, dict) and set(schema) == {"algorithm", "pre_upgrade", "target"}
        and schema["algorithm"] == ALGORITHM
        and all(isinstance(schema[k], str) and _HEX.fullmatch(schema[k])
                for k in ("pre_upgrade", "target")))


def load_bound(record: dict[str, Any], repository_root: Path | str = core.REPO_ROOT,
               *, deadline: core.Deadline | None = None) -> dict[str, Any]:
    """Hash and parse one bounded read, with no symlink traversal."""
    _check(deadline)
    try:
        binding = record["baseline"]
        relative = Path(binding["path"])
        base = Path("services/vikunja/baselines")
        if (relative.is_absolute() or ".." in relative.parts or relative == base
                or not relative.is_relative_to(base)):
            raise ValueError("containment")
        # Walk descriptors rather than resolving then reopening a mutable path.
        with contextlib.ExitStack() as stack:
            fd = os.open(repository_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            stack.callback(os.close, fd)
            for part in relative.parts[:-1]:
                _check(deadline)
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                stack.callback(os.close, fd)
            fd = os.open(relative.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            stack.callback(os.close, fd)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError("file type")
            with os.fdopen(os.dup(fd), "rb") as source:
                raw = source.read(MAX_BASELINE_BYTES + 1)
        _check(deadline)
        if len(raw) > MAX_BASELINE_BYTES or hashlib.sha256(raw).hexdigest() != binding["sha256"]:
            raise ValueError("binding")
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate key")
                result[key] = value
            return result
        value = json.loads(raw, object_pairs_hook=unique)
        if (not validate(value) or value["previous_version"] != previous_version(record)
                or value["previous_image_config"] != record["rollback"]["image_id"]):
            raise ValueError("identity")
        _check(deadline)
        return value
    except core.Fail:
        raise
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        raise core.Fail("GATE_BASELINE_UNREADABLE") from exc


@contextlib.contextmanager
def _connect(path: Path | str, deadline: core.Deadline | None):
    _check(deadline)
    conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro&immutable=1", uri=True,
                           timeout=0)
    try:
        conn.set_progress_handler(lambda: int(deadline is not None and deadline.remaining() <= 0), 1000)
        yield conn
        _check(deadline)
    except sqlite3.Error:
        _check(deadline)
        raise
    finally:
        conn.close()


def _rows(conn, sql: str, deadline) -> list:
    result = []
    for row in conn.execute(sql):
        _check(deadline)
        result.append(list(row))
    _check(deadline)
    return result


def _hash_rows(rows, deadline) -> str:
    digest = hashlib.sha256(b"[")
    for index, row in enumerate(rows):
        _check(deadline)
        if index:
            digest.update(b",")
        digest.update(_json(row))
    digest.update(b"]")
    _check(deadline)
    return digest.hexdigest()


def schema_identity(conn: sqlite3.Connection, *, deadline=None) -> str:
    """Hash exact SQLite schema text, including null SQL for autoindexes."""
    rows = conn.execute("SELECT type, name, tbl_name, sql FROM main.sqlite_master "
                        "ORDER BY type COLLATE BINARY, name COLLATE BINARY, tbl_name COLLATE BINARY")
    return _hash_rows(rows, deadline)


def migration_ids(conn: sqlite3.Connection, *, deadline=None) -> list[str]:
    ids = [r[0] for r in _rows(conn, "SELECT id FROM migration ORDER BY id COLLATE BINARY", deadline)]
    if not _ids(ids, allow_schema_init=True):
        raise ValueError("invalid migrations")
    return ids


_ELIGIBLE = """WITH eligible(task_id,user_id) AS (
    SELECT t.id,t.created_by_id FROM tasks t JOIN users u ON u.id=t.created_by_id
    UNION
    SELECT a.task_id,a.user_id FROM task_assignees a
    JOIN tasks t ON t.id=a.task_id JOIN users u ON u.id=a.user_id
), missing AS (
    SELECT e.task_id,e.user_id FROM eligible e WHERE NOT EXISTS (
        SELECT 1 FROM subscriptions s WHERE s.entity_type=3
        AND s.entity_id=e.task_id AND s.user_id=e.user_id)
) """


def aggregates(conn: sqlite3.Connection, *, deadline=None) -> dict[str, Any]:
    """Private acceptance evidence; preserve existing keys and muted choices."""
    def scalar(sql):
        return _rows(conn, sql, deadline)[0][0]
    repeats = _rows(conn, "SELECT id,repeats,repeats_from_current_date FROM tasks "
                    "WHERE repeats IS NOT NULL AND repeats != '' ORDER BY id", deadline)
    subscriptions = _rows(conn, "SELECT id,entity_id,user_id,muted FROM subscriptions "
                          "WHERE entity_type=3 ORDER BY id", deadline)
    missing = scalar(_ELIGIBLE + "SELECT count(*) FROM missing")
    return {"task_count": scalar("SELECT count(*) FROM tasks"),
            "repeat_count": len(repeats), "repeat_hash": _hash_rows(repeats, deadline),
            "task_subscription_rows": len(subscriptions), "missing_eligible_pairs": missing,
            "expected_task_subscription_rows": len(subscriptions) + missing,
            "duplicate_excess": scalar("SELECT coalesce(sum(n-1),0) FROM (SELECT count(*) n "
                                       "FROM subscriptions WHERE entity_type=3 GROUP BY entity_id,user_id)"),
            "existing_subscriptions": subscriptions}


@dataclass(frozen=True, repr=False)
class Result:
    code: str | None
    aggregates: dict[str, Any] | None = None


def compare(snapshot_path: Path | str, baseline: dict[str, Any], *, deadline=None) -> Result:
    """Return a stable refusal separately from private evidence."""
    try:
        with _connect(snapshot_path, deadline) as conn:
            try:
                observed_ids = migration_ids(conn, deadline=deadline)
            except (sqlite3.Error, ValueError):
                _check(deadline)
                return Result("GATE_MIGRATIONS_MISMATCH")
            if observed_ids != baseline["pre_upgrade_migration_ids"]:
                return Result("GATE_MIGRATIONS_MISMATCH")
            schema = schema_identity(conn, deadline=deadline)
            if schema != baseline["schema_identity"]["pre_upgrade"]:
                return Result("GATE_SCHEMA_MISMATCH")
            evidence = aggregates(conn, deadline=deadline)
            evidence.update(migration_ids=baseline["pre_upgrade_migration_ids"], schema_identity=schema)
            return Result(None, evidence)
    except (sqlite3.Error, OSError, ValueError, TypeError, KeyError):
        _check(deadline)
        return Result("GATE_AGGREGATE_FAILED")


def build(pre_path: Path | str, post_path: Path | str, record: dict[str, Any], *, expected_added, deadline=None) -> dict:
    """Build only data-free qualification facts from consolidated copies."""
    if type(expected_added) is not int or expected_added < 0:
        raise core.Fail("BUILD_BASELINE_INVALID")
    with _connect(pre_path, deadline) as pre, _connect(post_path, deadline) as post:
        before = migration_ids(pre, deadline=deadline)
        after = migration_ids(post, deadline=deadline)
        added = sorted(set(after) - set(before))
        if not set(before) <= set(after) or len(added) != expected_added:
            raise core.Fail("GATE_MIGRATIONS_MISMATCH")
        result = {"schema_version": 1, "previous_version": previous_version(record),
                  "previous_image_config": record["rollback"]["image_id"],
                  "pre_upgrade_migration_ids": before, "added_migration_ids": added,
                  "schema_identity": {"algorithm": ALGORITHM,
                                      "pre_upgrade": schema_identity(pre, deadline=deadline),
                                      "target": schema_identity(post, deadline=deadline)}}
    if not validate(result):
        raise core.Fail("GATE_BASELINE_UNREADABLE")
    return result


def _receipt_valid(value: Any, deadline=None) -> bool:
    fields = {"schema_version", "snapshot_sha256", "baseline_sha256", "release_version",
              "config_digest", "baseline", "aggregates"}
    if not isinstance(value, dict) or set(value) != fields:
        return False
    facts = value["baseline"]
    evidence = value["aggregates"]
    counts = {"task_count", "repeat_count", "task_subscription_rows", "missing_eligible_pairs",
              "expected_task_subscription_rows", "duplicate_excess"}
    if (type(value["schema_version"]) is not int or value["schema_version"] != 1
            or not validate(facts) or not isinstance(evidence, dict)
            or set(evidence) != counts | {"repeat_hash", "existing_subscriptions", "migration_ids", "schema_identity"}):
        return False
    rows = evidence["existing_subscriptions"]
    if not isinstance(rows, list):
        return False
    ids = []
    pairs = set()
    for row in rows:
        _check(deadline)
        if (not isinstance(row, list) or len(row) != 4 or not all(type(x) is int for x in row[:3])
                or not (row[3] is None or type(row[3]) is int and row[3] in (0, 1))):
            return False
        ids.append(row[0])
        pairs.add((row[1], row[2]))
    return bool(
        all(isinstance(value[k], str) and _HEX.fullmatch(value[k])
            for k in ("snapshot_sha256", "baseline_sha256"))
        and isinstance(value["release_version"], str) and core._VERSION_RE.fullmatch(value["release_version"])
        and isinstance(value["config_digest"], str) and _CONFIG.fullmatch(value["config_digest"])
        and all(type(evidence[k]) is int and evidence[k] >= 0 for k in counts)
        and isinstance(evidence["repeat_hash"], str) and _HEX.fullmatch(evidence["repeat_hash"])
        and evidence["migration_ids"] == facts["pre_upgrade_migration_ids"]
        and evidence["schema_identity"] == facts["schema_identity"]["pre_upgrade"]
        and evidence["repeat_count"] <= evidence["task_count"]
        and evidence["expected_task_subscription_rows"] == evidence["task_subscription_rows"] + evidence["missing_eligible_pairs"]
        and len(rows) == evidence["task_subscription_rows"] and ids == sorted(set(ids))
        and evidence["duplicate_excess"] == len(rows) - len(pairs))


def write_receipt(snapshot_dir: Path | str, receipt: dict, *, deadline=None) -> None:
    """Create once; a partial/crashed receipt remains a refusal on retry."""
    _check(deadline)
    try:
        if not _receipt_valid(receipt, deadline):
            raise ValueError("receipt")
        path = Path(snapshot_dir).absolute()
        # Reject symlinks in every ancestor; verify the final directory by fd.
        with contextlib.ExitStack() as stack:
            parent = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            stack.callback(os.close, parent)
            for part in path.parts[1:]:
                _check(deadline)
                parent = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                stack.callback(os.close, parent)
            info = os.fstat(parent)
            if stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.geteuid():
                raise ValueError("unsafe parent")
            fd = os.open("baseline.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=parent)
            stack.callback(os.close, fd)
            os.fchmod(fd, 0o600)
            encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                       allow_nan=False)
            for chunk in encoder.iterencode(receipt):
                payload = memoryview(chunk.encode("utf-8"))
                while payload:
                    _check(deadline)
                    written = os.write(fd, payload)
                    if written <= 0:
                        raise OSError("zero progress")
                    payload = payload[written:]
            _check(deadline)
            os.fsync(fd)
            _check(deadline)
            os.fsync(parent)
            _check(deadline)
    except (OSError, ValueError, TypeError) as exc:
        raise core.Fail("GATE_RECEIPT_WRITE_FAILED") from exc


def gate(record: dict, snapshot: dict, *, repository_root=core.REPO_ROOT, deadline=None) -> None:
    """Authenticate, compare, durably bind evidence; never select an image."""
    facts = load_bound(record, repository_root, deadline=deadline)
    result = compare(snapshot["db_path"], facts, deadline=deadline)
    if result.code is not None:
        raise core.Fail(result.code)
    receipt = {"schema_version": 1, "snapshot_sha256": snapshot["db_sha256"],
               "baseline_sha256": record["baseline"]["sha256"],
               "release_version": record["release_version"],
               "config_digest": record["image"]["config_digest"],
               "baseline": facts, "aggregates": result.aggregates}
    write_receipt(snapshot["snapshot_dir"], receipt, deadline=deadline)

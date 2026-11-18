#!/usr/bin/env python3
"""Compare a disposable, stable filesystem copy before the outage."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import os
from pathlib import Path
import shutil
import signal
import sys
import tempfile
import time

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.deploy.vikunja_release import baseline, core, dbsafety


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "PREFLIGHT_USAGE\n")


@contextlib.contextmanager
def _termination_handlers():
    """Route session termination through normal exception cleanup."""
    signals = (signal.SIGTERM, signal.SIGHUP)
    previous = {}

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    try:
        for signum in signals:
            previous[signum] = signal.signal(signum, interrupted)
        yield
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def _remove_private_copy(path, code):
    # A further termination request must not interrupt removal halfway through.
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGHUP})
    try:
        try:
            shutil.rmtree(path)
        except OSError:
            raise core.Fail(code) from None
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


def _copy_round(source: Path, target: Path, deadline: core.Deadline) -> dict:
    """Read DB/WAL bytes only; membership changes invalidate the whole round."""
    names = {dbsafety.DB_NAME}
    wal = dbsafety.DB_NAME + "-wal"
    if os.path.lexists(source / wal):
        names.add(wal)
    hashes = {}
    for name in sorted(names):
        deadline.check("PREFLIGHT")
        fd = dbsafety._open_source(source / name)
        try:
            digest = hashlib.sha256()
            with (target / name).open("xb") as output:
                os.chmod(target / name, 0o600)
                while True:
                    deadline.check("PREFLIGHT")
                    chunk = os.read(fd, 1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    digest.update(chunk)
            hashes[name] = digest.hexdigest()
        finally:
            os.close(fd)
    after = {dbsafety.DB_NAME}
    if os.path.lexists(source / wal):
        after.add(wal)
    if names != after:
        raise FileNotFoundError("copy membership changed")
    return hashes


def preflight(record: dict, *, repository_root=core.REPO_ROOT,
              clock=time.monotonic, snapshot_clock=dbsafety._utc_now) -> tuple[float, float]:
    start = clock()
    deadline = core.Deadline(90, clock)
    parent = None
    try:
        facts = baseline.load_bound(record, repository_root, deadline=deadline)
        root = Path(record["roots"]["private_logs"])
        fd = dbsafety.open_private_root(root, code="PREFLIGHT_ROOT")
        os.close(fd)
        parent = Path(tempfile.mkdtemp(prefix="preflight-", dir=root))
        os.chmod(parent, 0o700)
        previous = None
        agreeing = None
        for index in range(5):
            deadline.check("PREFLIGHT")
            current = parent / str(index)
            current.mkdir(mode=0o700)
            try:
                hashes = _copy_round(Path(record["service"]["data_dir"]), current, deadline)
            except FileNotFoundError:
                hashes = None
            if hashes is not None and hashes == previous:
                agreeing = current
                break
            previous = hashes
            # Only the preceding round is needed for the next comparison.
            shutil.rmtree(current)
        if agreeing is None:
            raise core.Fail("PREFLIGHT_COPY_UNSTABLE")
        consolidation_start = clock()
        snap = dbsafety.snapshot(agreeing, parent / "consolidated", clock=snapshot_clock,
                                 pre_version=baseline.previous_version(record),
                                 running_image_id=record["rollback"]["image_id"], deadline=deadline)
        consolidation_seconds = clock() - consolidation_start
        gate_start = clock()
        gate_deadline = core.Deadline(min(25, deadline.cap(25, "PREFLIGHT")), clock)
        result = baseline.compare(snap["db_path"], facts, deadline=gate_deadline)
        gate_deadline.check("GATE")
        deadline.check("PREFLIGHT")
        if result.code:
            raise core.Fail(result.code)
        return consolidation_seconds, clock() - gate_start
    except core.Fail as exc:
        if clock() - start >= 90 or exc.code in {"GATE_DEADLINE", "SNAPSHOT_DEADLINE", "PREFLIGHT_DEADLINE"}:
            raise core.Fail("PREFLIGHT_OVER_BUDGET") from None
        if exc.code in {"PREFLIGHT_COPY_UNSTABLE", "GATE_BASELINE_UNREADABLE",
                        "GATE_MIGRATIONS_MISMATCH", "GATE_SCHEMA_MISMATCH", "GATE_AGGREGATE_FAILED"}:
            raise core.Fail(exc.code) from None
        raise core.Fail("PREFLIGHT_FAILED") from None
    except (Exception, KeyboardInterrupt):
        raise core.Fail("PREFLIGHT_FAILED") from None
    finally:
        if parent is not None:
            _remove_private_copy(parent, "PREFLIGHT_CLEANUP_FAILED")


@_termination_handlers()
def main(argv=None, *, repository_root=core.REPO_ROOT) -> int:
    parser = _Parser(description=__doc__)
    parser.add_argument("release_record")
    args = parser.parse_args(argv)
    try:
        times = preflight(core.load_release(args.release_record), repository_root=repository_root)
    except core.Fail as exc:
        allowed = {"PREFLIGHT_OVER_BUDGET", "PREFLIGHT_COPY_UNSTABLE", "PREFLIGHT_FAILED",
                   "PREFLIGHT_CLEANUP_FAILED", "GATE_BASELINE_UNREADABLE", "GATE_MIGRATIONS_MISMATCH",
                   "GATE_SCHEMA_MISMATCH", "GATE_AGGREGATE_FAILED"}
        print(exc.code if exc.code in allowed else "PREFLIGHT_FAILED")
        return 1
    except (Exception, KeyboardInterrupt):
        print("PREFLIGHT_FAILED")
        return 1
    print(f"PREFLIGHT_OK consolidation_seconds={times[0]:.3f} gate_seconds={times[1]:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

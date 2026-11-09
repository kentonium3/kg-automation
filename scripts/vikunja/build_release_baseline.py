#!/usr/bin/env python3
"""Build a create-only, data-free qualification from consolidated copies."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.deploy.vikunja_release import baseline, core, dbsafety


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "BUILD_BASELINE_USAGE\n")


def build(pre_copy, post_copy, record, output) -> None:
    try:
        _build(pre_copy, post_copy, record, output)
    except core.Fail as exc:
        allowed = {"BUILD_BASELINE_INVALID", "GATE_MIGRATIONS_MISMATCH", "GATE_BASELINE_UNREADABLE"}
        raise core.Fail(exc.code if exc.code in allowed else "BUILD_BASELINE_FAILED") from None
    except (Exception, KeyboardInterrupt):
        raise core.Fail("BUILD_BASELINE_FAILED") from None


def _build(pre_copy, post_copy, record, output) -> None:
    facts = baseline.build(pre_copy, post_copy, record)
    if (not baseline.validate(facts) or len(facts["added_migration_ids"]) != 10
            or facts["previous_version"] != baseline.previous_version(record)
            or facts["previous_image_config"] != record["rollback"]["image_id"]):
        raise core.Fail("BUILD_BASELINE_INVALID")
    payload = (json.dumps(facts, sort_keys=True, indent=2, ensure_ascii=False,
                          allow_nan=False) + "\n").encode("utf-8")
    destination = Path(output)
    parent = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fd = os.open(destination.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent)
        try:
            os.fchmod(fd, 0o600)
            dbsafety._write_all(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(parent)
    finally:
        os.close(parent)


def main(argv=None) -> int:
    parser = _Parser(description=__doc__)
    parser.add_argument("pre_copy")
    parser.add_argument("post_copy")
    parser.add_argument("release_record")
    parser.add_argument("new_output")
    args = parser.parse_args(argv)
    try:
        build(args.pre_copy, args.post_copy, core.load_release(args.release_record), args.new_output)
    except (Exception, KeyboardInterrupt):
        print("BUILD_BASELINE_FAILED")
        return 1
    print("BUILD_BASELINE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
